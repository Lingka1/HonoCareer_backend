def view(user):
    account = user['account']
    masked = account[:1] + '***' + ('@' + account.split('@',1)[1] if '@' in account else '')
    return {'userId':user['id'],'nickname':user['nickname'],'avatarUrl':user['avatar_url'],'emailMasked':masked,'createdAt':user['created_at']}

def patch(database, user_id, body):
    fields = body.model_dump(exclude_unset=True)
    mapping = {'nickname':'nickname','avatarUrl':'avatar_url'}
    with database.transaction() as db:
        for name,value in fields.items():
            db.execute(f'UPDATE users SET {mapping[name]}=? WHERE id=?',(value,user_id))
        return view(dict(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()))
