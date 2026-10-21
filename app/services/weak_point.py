import json
from app.services.common import ServiceError, dump, now, owned, paginate, uid

def view(row):
    return {'weakPointId':row['id'],'sessionId':row['session_id'],'mode':'interview','dimensionKey':row['dimension_key'],
            'messageIds':json.loads(row['message_ids']),'note':row['note'],'createdAt':row['created_at']}

def create(database,user_id,session_id,body):
    with database.transaction() as db:
        session=owned(db,'sessions',session_id,user_id)
        if session['status']!='completed': raise ServiceError(409,'SESSION_STATE_CONFLICT','请在报告完成后标记弱项')
        for message_id in body.messageIds:
            if not db.execute('SELECT 1 FROM messages WHERE id=? AND session_id=?',(message_id,session_id)).fetchone():
                raise ServiceError(422,'INVALID_EVIDENCE','证据消息不属于当前会话')
        previous=db.execute('SELECT * FROM weak_points WHERE session_id=? AND dimension_key=? AND message_ids=? AND note=?',(session_id,body.dimensionKey,dump(body.messageIds),body.note)).fetchone()
        if previous: return view(dict(previous))
        resource_id=uid('wp')
        db.execute('INSERT INTO weak_points VALUES (?,?,?,?,?,?,?)',(resource_id,session_id,user_id,body.dimensionKey,dump(body.messageIds),body.note,now()))
        return view(owned(db,'weak_points',resource_id,user_id))

def listing(database,settings,user_id,limit,cursor):
    rows=[view(r) for r in database.all('SELECT * FROM weak_points WHERE user_id=?',(user_id,))]
    return paginate(rows,limit,cursor,f'weak-points:{user_id}',settings.jwt_secret,('createdAt','weakPointId'))

def delete(database,user_id,resource_id):
    with database.transaction() as db:
        owned(db,'weak_points',resource_id,user_id)
        db.execute('DELETE FROM weak_points WHERE id=?',(resource_id,))
