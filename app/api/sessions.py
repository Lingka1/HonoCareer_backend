from typing import Literal
from fastapi import APIRouter,Request
from app.api.common import User,Limit,Cursor,Key,ok
from app.api.contracts import R,Page,SessionCreateDTO,SessionPatchDTO,SessionVO,FinishDTO,FinishVO,CancelVO
from app.services import session
router=APIRouter(prefix='/sessions',tags=['面试会话'])

@router.post('',response_model=R[SessionVO])
def create(body:SessionCreateDTO,request:Request,user:User,idempotency_key:Key):
    return ok(request,session.create(request.app.state.db,user['id'],body,idempotency_key))

@router.get('',response_model=R[Page[SessionVO]])
def listing(request:Request,user:User,mode:Literal['interview']='interview',status:Literal['active','generating_report','completed','failed','cancelled']|None=None,limit:Limit=20,cursor:Cursor=None):
    return ok(request,session.listing(request.app.state.db,request.app.state.settings,user['id'],status,limit,cursor))

@router.get('/{session_id}',response_model=R[SessionVO])
def get(session_id:str,request:Request,user:User):
    return ok(request,session.get(request.app.state.db,user['id'],session_id))

@router.patch('/{session_id}',response_model=R[SessionVO])
def patch(session_id:str,body:SessionPatchDTO,request:Request,user:User):
    return ok(request,session.patch(request.app.state.db,user['id'],session_id,body))

@router.post('/{session_id}/finish',response_model=R[FinishVO])
def finish(session_id:str,body:FinishDTO,request:Request,user:User):
    return ok(request,session.finish(request.app.state.db,user['id'],session_id,body.reason))

@router.post('/{session_id}/cancel',response_model=R[CancelVO])
def cancel(session_id:str,request:Request,user:User):
    return ok(request,session.cancel(request.app.state.db,user['id'],session_id))

@router.delete('/{session_id}',response_model=R[None])
def delete(session_id:str,request:Request,user:User):
    session.delete(request.app.state.db,user['id'],session_id)
    return ok(request)
