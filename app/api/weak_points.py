from typing import Literal
from fastapi import APIRouter,Request
from app.api.common import User,Limit,Cursor,ok
from app.api.contracts import R,Page,WeakPointDTO,WeakPointVO
from app.services import weak_point
router=APIRouter(tags=['面试弱项'])

@router.post('/sessions/{session_id}/weak-points',response_model=R[WeakPointVO])
def create(session_id:str,body:WeakPointDTO,request:Request,user:User):
    return ok(request,weak_point.create(request.app.state.db,user['id'],session_id,body))

@router.get('/weak-points',response_model=R[Page[WeakPointVO]])
def listing(request:Request,user:User,mode:Literal['interview']='interview',limit:Limit=20,cursor:Cursor=None):
    return ok(request,weak_point.listing(request.app.state.db,request.app.state.settings,user['id'],limit,cursor))

@router.delete('/weak-points/{weak_point_id}',response_model=R[None])
def delete(weak_point_id:str,request:Request,user:User):
    weak_point.delete(request.app.state.db,user['id'],weak_point_id)
    return ok(request)
