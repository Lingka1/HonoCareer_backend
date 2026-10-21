import asyncio
import json
import time
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.llm.deepseek import DeepSeekProvider
from app.llm.demo import DemoProvider
from app.services.common import ServiceError
from tests.conftest import account,session,send,events,wait_for

class SlowProvider(DemoProvider):
    async def stream(self,messages,context):
        for text in ('第一段','第二段','第三段'):
            await asyncio.sleep(.12)
            yield text

def test_cancel_stops_commits_and_closes_stream(settings):
    with TestClient(create_app(settings,SlowProvider())) as client:
        auth,_=account(client);s=session(client,auth)['sessionId'];accepted=send(client,auth,s)
        time.sleep(.05)
        assert client.post(f'/api/v1/sessions/{s}/cancel',headers=auth).status_code==200
        journal=events(client,auth,s,accepted['responseId'])
        assert journal[-2]['event']=='error' and journal[-1]['event']=='done'
        assert journal[-2]['data']['payload']['code']=='SESSION_CANCELLED'
        time.sleep(.45)
        assert client.app.state.db.one('SELECT COUNT(*) AS n FROM messages WHERE session_id=? AND role=?',(s,'assistant'))['n']==1
        assert client.get('/api/v1/sessions/'+s,headers=auth).json()['data']['status']=='cancelled'

def test_restart_replays_interrupted_response_without_duplicate_question(settings):
    with TestClient(create_app(settings,SlowProvider())) as client:
        auth,_=account(client);s=session(client,auth)['sessionId'];accepted=send(client,auth,s)
        for _ in range(50):
            if client.app.state.db.one('SELECT status FROM responses WHERE id=?',(accepted['responseId'],))['status']=='processing':break
            time.sleep(.01)
    with TestClient(create_app(settings)) as client:
        journal=events(client,auth,s,accepted['responseId'])
        assert any(e['event']=='error' and e['data']['payload']['code']=='AGENT_INTERRUPTED' for e in journal)
        assert client.app.state.db.one('SELECT COUNT(*) AS n FROM messages WHERE session_id=?',(s,))['n']==2

class BrokenScoreProvider(DemoProvider):
    broken=True
    async def score(self,context):
        result=await super().score(context)
        if self.broken:result['dimensions'][0]['evidence']=['invented-evidence']
        return result

def test_fabricated_report_evidence_rejected_and_retryable(settings):
    provider=BrokenScoreProvider()
    with TestClient(create_app(settings,provider)) as client:
        auth,_=account(client);s=session(client,auth)['sessionId'];accepted=send(client,auth,s);events(client,auth,s,accepted['responseId'])
        first=client.post(f'/api/v1/sessions/{s}/finish',headers=auth,json={'reason':'user_end'}).json()['data']
        assert wait_for(client,auth,s)['status']=='failed'
        assert client.get(f'/api/v1/sessions/{s}/report',headers=auth).status_code==503
        provider.broken=False
        retry=client.post(f'/api/v1/sessions/{s}/finish',headers=auth,json={'reason':'user_end'}).json()['data']
        assert retry['reportId']==first['reportId']
        assert wait_for(client,auth,s)['status']=='completed'

def test_missing_cloud_credentials_is_explicit(settings):
    settings.llm_provider='deepseek';settings.deepseek_api_key=''
    with TestClient(create_app(settings)) as client:
        auth,_=account(client);s=session(client,auth)['sessionId'];accepted=send(client,auth,s)
        journal=events(client,auth,s,accepted['responseId'])
        error=next(e for e in journal if e['event']=='error')
        assert error['data']['payload']['code']=='AGENT_UNAVAILABLE'
        assert 'API Key' in error['data']['payload']['message']
        assert client.app.state.db.one('SELECT COUNT(*) AS n FROM messages WHERE session_id=?',(s,))['n']==2

def test_deepseek_wire_protocol_unicode_and_json(settings):
    settings.deepseek_api_key='synthetic-test-key';captured=[]
    async def transport(request):
        captured.append(json.loads(request.content));assert request.headers['authorization']=='Bearer synthetic-test-key'
        if captured[-1]['stream']:
            return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':'你好🌟'}}]},ensure_ascii=False)+'\n\ndata: [DONE]\n\n')
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"dimensions":[]}'}}]})
    async def run():
        provider=DeepSeekProvider(settings,httpx.MockTransport(transport))
        chunks=[x async for x in provider.stream([{'role':'user','content':'你好'}],{})]
        assert ''.join(chunks)=='你好🌟'
        result=await provider.score({'scene':'employment','sceneConfig':{},'messages':[]})
        assert result=={'dimensions':[]}
        await provider.close()
    asyncio.run(run())
    assert captured[0]['model']==settings.deepseek_model and captured[1]['response_format']=={'type':'json_object'}

@pytest.mark.parametrize('status,code',[(429,'RATE_LIMITED'),(500,'AGENT_UNAVAILABLE')])
def test_provider_errors_are_sanitized(settings,status,code):
    settings.deepseek_api_key='never-expose-this'
    async def transport(request):return httpx.Response(status,text='private key / prompt should not escape')
    async def run():
        provider=DeepSeekProvider(settings,httpx.MockTransport(transport))
        with pytest.raises(ServiceError) as error:
            async for _ in provider.stream([],{}): pass
        assert error.value.code==code and 'private' not in error.value.message
        await provider.close()
    asyncio.run(run())

def test_truncated_model_stream_not_saved_as_complete(settings):
    settings.deepseek_api_key='synthetic'
    async def transport(request):return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
    async def run():
        provider=DeepSeekProvider(settings,httpx.MockTransport(transport))
        with pytest.raises(ServiceError):
            async for _ in provider.stream([],{}):pass
        await provider.close()
    asyncio.run(run())

def test_rate_limit_body_limit_and_password_whitespace(client,auth):
    client.app.state.settings.rate_limit=1
    assert client.patch('/api/v1/users/me',headers=auth,json={'nickname':'第一次修改'}).status_code==200
    response=client.patch('/api/v1/users/me',headers=auth,json={'nickname':'第二次修改'})
    assert response.status_code==429 and response.headers['retry-after']=='60'
    # Actual middleware bound = configured max_file_bytes + multipart overhead.
    large=b'x'*(client.app.state.settings.max_file_bytes+512*1024+1)
    assert client.post('/api/v1/auth/login',content=large).status_code==413
    account_id=uuid.uuid4().hex;password='  password-with-spaces  '
    assert client.post('/api/v1/auth/register',json={'account':account_id,'password':password}).status_code==200
    assert client.post('/api/v1/auth/login',json={'account':account_id,'password':password}).status_code==200
    assert client.post('/api/v1/auth/login',json={'account':account_id,'password':password.strip()}).status_code==401
