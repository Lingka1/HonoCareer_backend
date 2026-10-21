import time
import uuid
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=str(tmp_path/'test.db'),jwt_secret='test-secret-'+'x'*48,llm_provider='demo',worker_interval=.01,rate_limit=1000)

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client

def account(client,name=None):
    name=name or uuid.uuid4().hex
    body={'account':name,'password':'Safe-test-password-123','nickname':'测试同学'}
    assert client.post('/api/v1/auth/register',json=body).status_code==200
    response=client.post('/api/v1/auth/login',json={**{k:body[k] for k in ('account','password')},'clientType':'web'})
    assert response.status_code==200,response.text
    tokens=response.json()['data']
    return {'Authorization':'Bearer '+tokens['accessToken']},tokens

@pytest.fixture
def auth(client):
    return account(client)[0]

def profile(client,auth,scene='employment',name='我的画像'):
    details={'employment':{'targetRole':'后端开发','skills':['Python','SQL'],'projectExperience':['校园服务应用']},
             'volunteer':{'activityType':'校园迎新','relevantSkills':['沟通协作']},
             'club':{'targetClub':'机器人社','interests':['编程']}}
    response=client.post('/api/v1/profiles',headers={**auth,'Idempotency-Key':uuid.uuid4().hex},json={'type':scene,'displayName':name,'baseInfo':{'school':'示例大学'},'detail':details[scene]})
    assert response.status_code==200,response.text
    return response.json()['data']

def session(client,auth,scene='employment',profile_id=None,**extra):
    profile_id=profile_id or profile(client,auth,scene)['profileId']
    configs={'employment':{'targetRole':'后端开发','jobDescription':'Python SQL 服务端接口设计'},'volunteer':{'activityType':'校园迎新'},'club':{'targetClub':'机器人社'}}
    body={'mode':'interview','scene':scene,'sceneConfig':configs[scene],'profileId':profile_id,'modality':'text','clientSessionId':uuid.uuid4().hex,**extra}
    response=client.post('/api/v1/sessions',headers={**auth,'Idempotency-Key':uuid.uuid4().hex},json=body)
    assert response.status_code==200,response.text
    return response.json()['data']

def send(client,auth,session_id,content=None,**extra):
    body={'clientMessageId':uuid.uuid4().hex,'kind':'answer','content':content or '我负责校园服务应用的后端接口设计。首先梳理了用户需求和数据模型，其次用 Python 和 SQL 实现核心模块。我们遇到性能问题后，我通过日志分析定位慢查询，增加索引并验证。最终响应时间从800毫秒降低到120毫秒，按时完成交付。我还记录了方案取舍，并与团队复盘结果。','inputMode':'text',**extra}
    response=client.post(f'/api/v1/sessions/{session_id}/messages',headers=auth,json=body)
    assert response.status_code==200,response.text
    return response.json()['data']

def events(client,auth,session_id,response_id,last=None):
    headers={**auth,**({'Last-Event-ID':last} if last else {})}
    response=client.get(f'/api/v1/sessions/{session_id}/responses/{response_id}/events',headers=headers)
    assert response.status_code==200,response.text
    assert response.headers['content-type'].startswith('text/event-stream')
    import json
    result=[]
    for block in response.text.strip().split('\n\n'):
        if not block or block.startswith(':'): continue
        fields=dict(line.split(': ',1) for line in block.splitlines() if ': ' in line)
        result.append({'event':fields['event'],'id':fields['id'],'data':json.loads(fields['data'])})
    return result

def wait_for(client,auth,session_id,statuses=('completed','failed'),timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        response=client.get('/api/v1/sessions/'+session_id,headers=auth)
        data=response.json()['data']
        if data['status'] in statuses:return data
        time.sleep(.025)
    raise AssertionError('Timed out waiting for session state')
