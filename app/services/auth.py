"""PBKDF2 passwords, JWT access tokens and atomic refresh-token rotation."""
import hashlib
import hmac
import secrets
import sqlite3
import time
import jwt
from app.services.common import ServiceError, now, uid

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256${salt}${digest}'

def verify_password(password, encoded):
    try:
        _, salt, _ = encoded.split('$')
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except ValueError:
        return False

def register(database, settings, body):
    if not settings.registration_enabled:
        raise ServiceError(403,'REGISTRATION_DISABLED','当前未开放注册')
    user_id = uid('usr')
    password_hash = hash_password(body.password)
    try:
        with database.transaction() as db:
            db.execute('INSERT INTO users (id,account,password_hash,nickname,created_at) VALUES (?,?,?,?,?)', (user_id,body.account.casefold(),password_hash,body.nickname,now()))
    except sqlite3.IntegrityError:
        raise ServiceError(409,'ACCOUNT_EXISTS','账号已存在，请直接登录') from None
    return {'userId':user_id}

def token_pair(db, settings, user_id, auth_id=None):
    auth_id = auth_id or uid('login')
    refresh = secrets.token_urlsafe(48)
    digest = hashlib.sha256(refresh.encode()).hexdigest()
    db.execute('INSERT INTO auth_sessions VALUES (?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET refresh_hash=excluded.refresh_hash,expires_at=excluded.expires_at', (auth_id,user_id,digest,time.time()+settings.refresh_ttl))
    issued = int(time.time())
    access = jwt.encode({'sub':user_id,'sid':auth_id,'iat':issued,'exp':issued+settings.access_ttl,'iss':'honocareer','aud':'honocareer-client'},settings.jwt_secret,algorithm='HS256')
    return {'accessToken':access,'refreshToken':refresh,'expiresIn':settings.access_ttl}

_DUMMY_HASH = hash_password('dummy-password')

def login(database, settings, body):
    user = database.one('SELECT * FROM users WHERE account=?',(body.account.casefold(),))
    valid = verify_password(body.password, user['password_hash'] if user else _DUMMY_HASH)
    if not user or not valid:
        raise ServiceError(401,'AUTH_INVALID_CREDENTIALS','账号或密码错误')
    with database.transaction() as db:
        result = token_pair(db,settings,user['id'])
    result['user'] = {'userId':user['id'],'nickname':user['nickname']}
    return result

def refresh(database, settings, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database.transaction() as db:
        row = db.execute('SELECT * FROM auth_sessions WHERE refresh_hash=? AND revoked=0 AND expires_at>?',(digest,time.time())).fetchone()
        if not row:
            raise ServiceError(401,'AUTH_REQUIRED','刷新令牌已失效，请重新登录')
        return token_pair(db,settings,row['user_id'],row['id'])

def authenticate(database, settings, token):
    try:
        claims = jwt.decode(token,settings.jwt_secret,algorithms=['HS256'],issuer='honocareer',audience='honocareer-client',options={'require':['exp','iat','sub','sid']})
    except jwt.ExpiredSignatureError:
        raise ServiceError(401,'TOKEN_EXPIRED','登录已过期，请刷新令牌') from None
    except jwt.InvalidTokenError:
        raise ServiceError(401,'AUTH_REQUIRED','无效的访问令牌') from None
    row = database.one('SELECT u.*, a.id AS auth_id FROM users u JOIN auth_sessions a ON a.user_id=u.id WHERE u.id=? AND a.id=? AND a.revoked=0 AND a.expires_at>?',(claims['sub'],claims['sid'],time.time()))
    if not row:
        raise ServiceError(401,'AUTH_REQUIRED','登录已失效，请重新登录')
    return row

def logout(database, user):
    with database.transaction() as db:
        db.execute('UPDATE auth_sessions SET revoked=1 WHERE id=?',(user['auth_id'],))
