from app.services.common import paginate

def settings(database,user_id,enabled=None):
    with database.transaction() as db:
        if enabled is not None: db.execute('UPDATE users SET memory_enabled=? WHERE id=?',(int(enabled),user_id))
        return {'enabled':bool(db.execute('SELECT memory_enabled FROM users WHERE id=?',(user_id,)).fetchone()[0])}

def listing(database,config,user_id,limit,cursor):
    rows=[{'memoryId':r['id'],'content':r['content'],'source':{'sessionId':r['session_id']},'createdAt':r['created_at']} for r in database.all('SELECT * FROM memories WHERE user_id=?',(user_id,))]
    return paginate(rows,limit,cursor,f'memories:{user_id}',config.jwt_secret,('createdAt','memoryId'))

def clear(database,user_id):
    with database.transaction() as db: db.execute('DELETE FROM memories WHERE user_id=?',(user_id,))
