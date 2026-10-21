import json
from app.services import profile
from app.services.common import ServiceError, dump, fingerprint, idem_get, idem_put, now, owned, paginate, uid

SCENE_LABELS={'employment':'求职','volunteer':'志愿者','club':'社团'}

def view(row,db=None,detail=False):
    snapshot=json.loads(row['profile_snapshot'])
    report=db.execute('SELECT * FROM reports WHERE session_id=?',(row['id'],)).fetchone() if db else None
    result={'sessionId':row['id'],'title':row['title'],'mode':row['mode'],'scene':row['scene'],
            'status':row['status'],'stage':row['stage'],'modality':row['modality'],
            'profileSnapshotVersion':snapshot['version'],'createdAt':row['created_at'],'startedAt':row['created_at'],
            'updatedAt':row['updated_at'],'endedAt':row['ended_at'],'reportId':report['id'] if report else None,
            'reportStatus':('ready' if report['status']=='completed' else 'failed' if report['status']=='failed' else 'pending') if report else None,
            'overallScore':json.loads(report['content'])['overallScore'] if report and report['content'] else None}
    active=db.execute("SELECT id FROM responses WHERE session_id=? AND status IN ('queued','processing','waiting_report') ORDER BY created_at DESC LIMIT 1",(row['id'],)).fetchone() if db else None
    result['activeResponseId']=active['id'] if active else None
    if detail:
        first=db.execute('SELECT content FROM messages WHERE session_id=? AND seq=1',(row['id'],)).fetchone()
        result.update(sceneConfig=json.loads(row['scene_config']),profileSnapshot=snapshot,
                      resumeSnapshot=json.loads(row['resume_snapshot']) if row['resume_snapshot'] else None,
                      firstPrompt=first['content'] if first else '',messagesUrl=f"/api/v1/sessions/{row['id']}/messages")
    return result

def create(database,user_id,body,key):
    data=body.model_dump(mode='json'); digest=fingerprint(data)
    with database.transaction() as db:
        resource_id=idem_get(db,user_id,'sessions',key,digest)
        if resource_id: return view(owned(db,'sessions',resource_id,user_id),db,True)
        previous=db.execute('SELECT * FROM sessions WHERE user_id=? AND client_session_id=?',(user_id,body.clientSessionId)).fetchone()
        if previous:
            if previous['request_hash']!=digest:
                raise ServiceError(409,'IDEMPOTENCY_CONFLICT','clientSessionId 已用于不同请求')
            idem_put(db,user_id,'sessions',key,digest,previous['id'])
            return view(dict(previous),db,True)
        snapshot=profile.view(owned(db,'profiles',body.profileId,user_id))
        if snapshot['type']!=body.scene:
            raise ServiceError(422,'PROFILE_TYPE_MISMATCH','画像类型与面试场景不匹配')
        resume_snapshot=None
        if body.resumeId:
            resume=owned(db,'resumes',body.resumeId,user_id)
            if resume['status']!='confirmed':
                raise ServiceError(422,'MATERIAL_NOT_CONFIRMED','请先确认简历解析结果')
            resume_snapshot={'resumeId':resume['id'],'fileName':resume['file_name'],'parsedContent':json.loads(resume['parsed_content'])}
        target={'employment':body.sceneConfig.targetRole,'volunteer':body.sceneConfig.activityType,'club':body.sceneConfig.targetClub}[body.scene]
        title=f'{target} · {SCENE_LABELS[body.scene]}面试'[:120]
        resource_id,stamp=uid('sess'),now()
        db.execute('INSERT INTO sessions (id,user_id,client_session_id,request_hash,title,mode,scene,scene_config,profile_snapshot,resume_snapshot,modality,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (resource_id,user_id,body.clientSessionId,digest,title,'interview',body.scene,dump(data['sceneConfig']),dump(snapshot),dump(resume_snapshot) if resume_snapshot else None,body.modality,'active','opening',stamp,stamp))
        first=f'你好，欢迎参加{target}的模拟面试。请先用一分钟介绍自己，重点说明与你申请方向相关的经历，以及你希望在本次面试中展示的优势。'
        db.execute('INSERT INTO messages VALUES (?,?,1,?,?,?,?,?,?,?)',(uid('msg'),resource_id,'assistant','question',first,'text','opening',None,stamp))
        idem_put(db,user_id,'sessions',key,digest,resource_id)
        return view(owned(db,'sessions',resource_id,user_id),db,True)

def get(database,user_id,resource_id):
    with database.transaction() as db: return view(owned(db,'sessions',resource_id,user_id),db,True)

def listing(database,settings,user_id,status,limit,cursor):
    with database.transaction() as db:
        rows=[view(dict(r),db) for r in db.execute('SELECT * FROM sessions WHERE user_id=?',(user_id,)) if not status or r['status']==status]
    return paginate(rows,limit,cursor,f'sessions:{user_id}:{status}',settings.jwt_secret,('updatedAt','sessionId'))

def patch(database,user_id,resource_id,body):
    data=body.model_dump(exclude_unset=True)
    with database.transaction() as db:
        row=owned(db,'sessions',resource_id,user_id)
        if 'modality' in data and row['status']!='active':
            raise ServiceError(409,'SESSION_STATE_CONFLICT','仅进行中的会话可以切换对话方式')
        db.execute('UPDATE sessions SET title=?,modality=?,updated_at=? WHERE id=?',(data.get('title',row['title']),data.get('modality',row['modality']),now(),resource_id))
        return view(owned(db,'sessions',resource_id,user_id),db,True)

def enqueue_report(db,session_id):
    report=db.execute('SELECT * FROM reports WHERE session_id=?',(session_id,)).fetchone()
    if not report:
        report_id=uid('rpt')
        db.execute('INSERT INTO reports (id,session_id,status,created_at) VALUES (?,?,?,?)',(report_id,session_id,'queued',now()))
    else:
        report_id=report['id']
        if report['status']=='failed':
            db.execute("UPDATE reports SET status='queued',error=NULL WHERE id=?",(report_id,))
    db.execute("UPDATE sessions SET status='generating_report',stage='review',ended_at=COALESCE(ended_at,?),updated_at=? WHERE id=?",(now(),now(),session_id))
    return report_id

def finish(database,user_id,resource_id,reason):
    with database.transaction() as db:
        row=owned(db,'sessions',resource_id,user_id)
        if row['status']=='cancelled': raise ServiceError(409,'SESSION_STATE_CONFLICT','已取消的会话不能生成报告')
        pending=db.execute("SELECT 1 FROM responses WHERE session_id=? AND status IN ('queued','processing')",(resource_id,)).fetchone()
        if pending: raise ServiceError(409,'SESSION_STATE_CONFLICT','当前回答正在处理，请完成后结束')
        if row['status'] in ('completed','generating_report'):
            report=db.execute('SELECT id FROM reports WHERE session_id=?',(resource_id,)).fetchone()
            return {'status':row['status'],'reportId':report['id']}
        report_id=enqueue_report(db,resource_id)
        return {'status':'generating_report','reportId':report_id}

def cancel(database,user_id,resource_id):
    from app.services.message import append_event
    with database.transaction() as db:
        row=owned(db,'sessions',resource_id,user_id)
        if row['status']=='cancelled': return {'status':'cancelled','cancelledAt':row['ended_at']}
        if row['status']!='active': raise ServiceError(409,'SESSION_STATE_CONFLICT','仅进行中的会话可以取消')
        stamp=now()
        for response in db.execute("SELECT id FROM responses WHERE session_id=? AND status IN ('queued','processing')",(resource_id,)).fetchall():
            append_event(db,response['id'],'error',{'code':'SESSION_CANCELLED','message':'会话已取消','retryable':False})
            append_event(db,response['id'],'done',{})
            db.execute("UPDATE responses SET status='cancelled' WHERE id=?",(response['id'],))
        db.execute("UPDATE sessions SET status='cancelled',ended_at=?,updated_at=? WHERE id=?",(stamp,stamp,resource_id))
        return {'status':'cancelled','cancelledAt':stamp}

def delete(database,user_id,resource_id):
    with database.transaction() as db:
        row=owned(db,'sessions',resource_id,user_id)
        if row['status'] in ('active','generating_report'):
            raise ServiceError(409,'SESSION_STATE_CONFLICT','请先结束或取消会话')
        db.execute('DELETE FROM sessions WHERE id=?',(resource_id,))
