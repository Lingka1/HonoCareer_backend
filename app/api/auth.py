from fastapi import APIRouter, Request
from app.api.common import User,ok
from app.api.contracts import R,RegisterDTO,RegisterVO,LoginDTO,RefreshDTO,TokensVO
from app.services import auth

router=APIRouter(prefix='/auth',tags=['账号'])

@router.post('/register',response_model=R[RegisterVO])
def register(body:RegisterDTO,request:Request):
    return ok(request,auth.register(request.app.state.db,request.app.state.settings,body))

@router.post('/login',response_model=R[TokensVO])
def login(body:LoginDTO,request:Request):
    return ok(request,auth.login(request.app.state.db,request.app.state.settings,body))

@router.post('/refresh',response_model=R[TokensVO])
def refresh(body:RefreshDTO,request:Request):
    return ok(request,auth.refresh(request.app.state.db,request.app.state.settings,body.refreshToken))

@router.post('/logout',response_model=R[None])
def logout(request:Request,user:User):
    auth.logout(request.app.state.db,user)
    return ok(request)
