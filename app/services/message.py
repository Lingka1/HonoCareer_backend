import json
from app.services.common import ServiceError, dump, fingerprint, now, owned, paginate, uid

def view(row):
    return {'messageId':row['id'],'sessionId':row['session_id'],'seq':row['seq'],'role':row['role'],
            'kind':row['kind'],'content':row['content'],'inputMode':row['input_mode'],'stage':row['stage'],
            'audioId':row['audio_id'],'createdAt':row['created_at']}

def append_event(db,response_id,event,payload):
    seq=db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE response_id=?',(response_id,)).fetchone()[0]
    event_id,stamp=uid('evt'),now()
    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(event_id,response_id,seq,event,dump(payload),stamp))
    return event_id

def submit(database,user_id,session_id,body):
    digest=fingerprint(body.model_dump(mode='json'))
    with database.transaction() as db:
        session=owned(db,'sessions',session_id,user_id)
        previous=db.execute('SELECT * FROM responses WHERE session_id=? AND client_message_id=?',(session_id,body.clientMessageId)).fetchone()
        if previous:
            if previous['request_hash']!=digest: raise ServiceError(409,'IDEMPOTENCY_CONFLICT','clientMessageId 已用于不同消息')
            return {'userMessageId':previous['user_message_id'],'responseId':previous['id'],'status':'queued'}
        if session['status']!='active': raise ServiceError(409,'SESSION_STATE_CONFLICT','会话已结束或取消')
        if db.execute("SELECT 1 FROM responses WHERE session_id=? AND status IN ('queued','processing')",(session_id,)).fetchone():
            raise ServiceError(409,'SESSION_STATE_CONFLICT','请等待当前问题生成完成')
        seq=db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM messages WHERE session_id=?',(session_id,)).fetchone()[0]
        message_id,response_id,stamp=uid('msg'),uid('rsp'),now()
        db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)',(message_id,session_id,seq,'user',body.kind,body.content,body.inputMode,session['stage'],body.audioId,stamp))
        db.execute('INSERT INTO responses VALUES (?,?,?,?,?,?,?)',(response_id,session_id,body.clientMessageId,digest,message_id,'queued',stamp))
        append_event(db,response_id,'queued',{})
        db.execute('UPDATE sessions SET updated_at=? WHERE id=?',(stamp,session_id))
        return {'userMessageId':message_id,'responseId':response_id,'status':'queued'}

def listing(database,settings,user_id,session_id,limit,cursor):
    with database.transaction() as db:
        owned(db,'sessions',session_id,user_id)
        rows=[view(dict(r)) for r in db.execute('SELECT * FROM messages WHERE session_id=?',(session_id,))]
    # The cursor points backwards; each individual page is displayed chronologically.
    result=paginate(rows,limit,cursor,f'messages:{user_id}:{session_id}',settings.jwt_secret,('seq','messageId'))
    result['items'].reverse()
    return result

def validate_stream(database,user_id,session_id,response_id,last_event_id):
    with database.transaction() as db:
        owned(db,'sessions',session_id,user_id)
        response=db.execute('SELECT * FROM responses WHERE id=? AND session_id=?',(response_id,session_id)).fetchone()
        if not response: raise ServiceError(404,'NOT_FOUND','响应不存在')
        if not last_event_id: return 0
        event=db.execute('SELECT seq FROM events WHERE id=? AND response_id=?',(last_event_id,response_id)).fetchone()
        if not event: raise ServiceError(400,'VALIDATION_ERROR','Last-Event-ID 不属于当前响应')
        return event['seq']

def event_view(row):
    return {'eventId':row['id'],'responseId':row['response_id'],'timestamp':row['created_at'],'payload':json.loads(row['payload'])}
