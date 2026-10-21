import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from tests.conftest import account,profile,session,send,events,wait_for

@pytest.mark.parametrize('scene',['employment','volunteer','club'])
def test_complete_interview_all_scenes(client,auth,scene):
    current=session(client,auth,scene)
    identifier=current['sessionId']; transitions=[]; journals=[]
    for _ in range(10):
        response=send(client,auth,identifier)
        journal=events(client,auth,identifier,response['responseId'])
        journals.extend(journal)
        transitions += [e['data']['payload']['stage'] for e in journal if e['event']=='stage_changed']
        assert journal[0]['event']=='queued' and journal[-1]['event']=='done'
        assert all(e['data']['eventId']==e['id'] for e in journal)
        assert any(e['event']=='tool_finished' for e in journal)
        current=client.get('/api/v1/sessions/'+identifier,headers=auth).json()['data']
        if current['status']=='completed': break
    assert current['status']=='completed'
    assert transitions==['self_introduction','experience_followup','situational_questions','candidate_questions','review']
    assert any(e['event']=='report_ready' for e in journals)
    report=client.get(f'/api/v1/sessions/{identifier}/report',headers=auth).json()['data']
    messages=client.get(f'/api/v1/sessions/{identifier}/messages?limit=50',headers=auth).json()['data']['items']
    ids={m['messageId'] for m in messages if m['role']=='user'}
    assert len(report['dimensions'])==4
    assert {d['key'] for d in report['dimensions']}=={'expression_clarity','logic','role_match','adaptability'}
    assert all(set(d['evidence'])<=ids and d['evidence'] for d in report['dimensions'])
    assert report['overallScore']==int(sum(d['score'] for d in report['dimensions'])/4+0.5)
    assert report['evaluationSource']=='demo'
    assert [m['seq'] for m in messages]==list(range(1,len(messages)+1))
    assert client.get(f'/api/v1/sessions/{identifier}/report',headers=auth).json()['data']==report

def test_idempotency_same_key_and_client_session_id(client,auth):
    p=profile(client,auth); key=uuid.uuid4().hex
    body={'mode':'interview','scene':'employment','sceneConfig':{'targetRole':'后端开发'},'profileId':p['profileId'],'clientSessionId':uuid.uuid4().hex}
    path='/api/v1/sessions';headers={**auth,'Idempotency-Key':key}
    first=client.post(path,headers=headers,json=body).json()['data']
    assert client.post(path,headers=headers,json=body).json()['data']['sessionId']==first['sessionId']
    assert client.post(path,headers={**auth,'Idempotency-Key':uuid.uuid4().hex},json=body).json()['data']['sessionId']==first['sessionId']
    body['sceneConfig']['targetRole']='前端开发'
    assert client.post(path,headers=headers,json=body).status_code==409
    assert client.post(path,headers={**auth,'Idempotency-Key':uuid.uuid4().hex},json=body).status_code==409

def test_message_retry_does_not_generate_twice(client,auth):
    s=session(client,auth)['sessionId']; key=uuid.uuid4().hex
    first=send(client,auth,s,clientMessageId=key)
    assert send(client,auth,s,clientMessageId=key)==first
    journal=events(client,auth,s,first['responseId'])
    assert send(client,auth,s,clientMessageId=key)==first
    response=client.post(f'/api/v1/sessions/{s}/messages',headers=auth,json={'clientMessageId':key,'content':'另一个回答','inputMode':'text'})
    assert response.status_code==409
    messages=client.get(f'/api/v1/sessions/{s}/messages',headers=auth).json()['data']['items']
    assert len(messages)==3
    marker=journal[len(journal)//2]['id']
    replay=events(client,auth,s,first['responseId'],marker)
    original_ids=[e['id'] for e in journal]; index=original_ids.index(marker)
    assert [e['id'] for e in replay]==original_ids[index+1:]
    assert events(client,auth,s,first['responseId'],journal[-1]['id'])==[]
    assert client.get(f"/api/v1/sessions/{s}/responses/{first['responseId']}/events",headers={**auth,'Last-Event-ID':'invalid'}).status_code==400

def test_background_work_does_not_require_subscription(client,auth):
    s=session(client,auth)['sessionId']; response=send(client,auth,s)
    end=time.monotonic()+4
    while time.monotonic()<end:
        row=client.app.state.db.one('SELECT status FROM responses WHERE id=?',(response['responseId'],))
        if row['status']=='completed': break
        time.sleep(.02)
    assert row['status']=='completed'
    assert len(events(client,auth,s,response['responseId']))>3

def test_simultaneous_messages_reject_overlap(client,auth):
    s=session(client,auth)['sessionId']
    def request(_): return client.post(f'/api/v1/sessions/{s}/messages',headers=auth,json={'clientMessageId':uuid.uuid4().hex,'content':'并行请求测试','inputMode':'text'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(request,range(2)))
    assert sorted(statuses)==[200,409]

def test_finish_report_and_cancel_contracts(client,auth):
    s=session(client,auth)['sessionId']
    assert client.get(f'/api/v1/sessions/{s}/report',headers=auth).status_code==202
    assert client.delete('/api/v1/sessions/'+s,headers=auth).status_code==409
    first=client.post(f'/api/v1/sessions/{s}/finish',headers=auth,json={'reason':'user_end'}).json()['data']
    wait_for(client,auth,s)
    second=client.post(f'/api/v1/sessions/{s}/finish',headers=auth,json={'reason':'user_end'}).json()['data']
    assert second['reportId']==first['reportId']
    report=client.get(f'/api/v1/sessions/{s}/report',headers=auth).json()['data']
    assert report['overallScore']==0 and report['evaluationSource']=='insufficient_evidence'
    assert client.post(f'/api/v1/sessions/{s}/cancel',headers=auth).status_code==409
    assert client.patch('/api/v1/sessions/'+s,headers=auth,json={'modality':'voice'}).status_code==409
    cancelled=session(client,auth)['sessionId']
    one=client.post(f'/api/v1/sessions/{cancelled}/cancel',headers=auth).json()['data']
    assert client.post(f'/api/v1/sessions/{cancelled}/cancel',headers=auth).json()['data']==one
    assert client.post(f'/api/v1/sessions/{cancelled}/finish',headers=auth,json={'reason':'user_end'}).status_code==409
    assert client.post(f'/api/v1/sessions/{cancelled}/messages',headers=auth,json={'clientMessageId':uuid.uuid4().hex,'content':'hello'}).status_code==409
    assert client.delete('/api/v1/sessions/'+cancelled,headers=auth).status_code==200

def test_profile_snapshot_and_pagination(client,auth):
    p=profile(client,auth); s=session(client,auth,profile_id=p['profileId'])
    response=client.patch('/api/v1/profiles/'+p['profileId'],headers=auth,json={'version':1,'detail':{'targetRole':'数据分析'}})
    assert response.status_code==200,response.text
    assert client.patch('/api/v1/profiles/'+p['profileId'],headers=auth,json={'version':1,'displayName':'过期修改'}).status_code==409
    assert client.delete('/api/v1/profiles/'+p['profileId'],headers=auth).status_code==200
    snapshot=client.get('/api/v1/sessions/'+s['sessionId'],headers=auth).json()['data']['profileSnapshot']
    assert snapshot['version']==1 and snapshot['detail']['targetRole']=='后端开发'
    for i in range(3):profile(client,auth,name='画像'+str(i))
    page=client.get('/api/v1/profiles?limit=2',headers=auth).json()['data']
    assert page['hasMore'] and page['nextCursor']
    second=client.get('/api/v1/profiles',params={'limit':2,'cursor':page['nextCursor']},headers=auth).json()['data']
    assert len(second['items'])==1 and not second['hasMore']
    assert not ({x['profileId'] for x in page['items']}&{x['profileId'] for x in second['items']})
    assert client.get('/api/v1/sessions',params={'cursor':page['nextCursor']},headers=auth).status_code==400

def test_account_isolation_every_resource(client,auth):
    s=session(client,auth); accepted=send(client,auth,s['sessionId'])
    other,_=account(client)
    for path in [f"/sessions/{s['sessionId']}",f"/sessions/{s['sessionId']}/messages",f"/sessions/{s['sessionId']}/report",f"/sessions/{s['sessionId']}/responses/{accepted['responseId']}/events",f"/profiles/{s['profileSnapshot']['profileId']}"]:
        assert client.get('/api/v1'+path,headers=other).status_code==404,path
    assert client.get('/api/v1/sessions',headers=other).json()['data']['items']==[]
    assert client.post(f"/api/v1/sessions/{s['sessionId']}/cancel",headers=other).status_code==404

def test_empty_patch_and_scene_validation(client,auth):
    s=session(client,auth)
    for path,body in [('/users/me',{}),('/profiles/'+s['profileSnapshot']['profileId'],{'version':1}),('/sessions/'+s['sessionId'],{})]:
        response=client.patch('/api/v1'+path,headers=auth,json=body)
        assert response.status_code==400 and response.json()['code']=='VALIDATION_ERROR'
    assert client.patch('/api/v1/profiles/'+s['profileSnapshot']['profileId'],headers=auth,json={'version':1,'detail':{'inventedField':1}}).status_code==400
    assert client.get('/api/v1/profiles/matches?scene=thesis&mode=interview',headers=auth).status_code==400
    assert client.get('/api/v1/profiles?limit=0',headers=auth).status_code==400
    body={'mode':'interview','scene':'club','profileId':s['profileSnapshot']['profileId'],'sceneConfig':{'targetClub':'机器人社'},'clientSessionId':uuid.uuid4().hex}
    assert client.post('/api/v1/sessions',headers={**auth,'Idempotency-Key':uuid.uuid4().hex},json=body).status_code==422
