from typing import Annotated
from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.services.auth import authenticate
from app.services.common import ServiceError

bearer=HTTPBearer(auto_error=False)

def current_user(request:Request,credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)]):
    if not credentials or credentials.scheme.lower()!='bearer':
        raise ServiceError(401,'AUTH_REQUIRED','请使用 Authorization: Bearer <accessToken> 登录')
    user=authenticate(request.app.state.db,request.app.state.settings,credentials.credentials)
    if request.method not in ('GET','HEAD','OPTIONS'):
        request.app.state.limiter.consume('user:'+user['id'],request.app.state.settings.rate_limit)
    return user

User=Annotated[dict,Depends(current_user)]
Limit=Annotated[int,Query(ge=1,le=50)]
Cursor=Annotated[str|None,Query(max_length=2048)]
Key=Annotated[str,Header(alias='Idempotency-Key',min_length=8,max_length=120)]

def ok(request,data=None):
    return {'code':0,'message':'ok','data':data,'requestId':request.state.request_id}
