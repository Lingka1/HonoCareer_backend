from fastapi import APIRouter,Request
from app.api.common import User,Limit,Cursor,ok
from app.api.contracts import R,Page,MemorySettingsDTO,MemoryVO
from app.services import memory
router=APIRouter(prefix='/users/me',tags=['长期记忆'])

@router.get('/memory-settings',response_model=R[MemorySettingsDTO])
def settings(request:Request,user:User):
    return ok(request,memory.settings(request.app.state.db,user['id']))

@router.patch('/memory-settings',response_model=R[MemorySettingsDTO])
def patch(body:MemorySettingsDTO,request:Request,user:User):
    return ok(request,memory.settings(request.app.state.db,user['id'],body.enabled))

@router.get('/memories',response_model=R[Page[MemoryVO]])
def listing(request:Request,user:User,limit:Limit=20,cursor:Cursor=None):
    return ok(request,memory.listing(request.app.state.db,request.app.state.settings,user['id'],limit,cursor))

@router.delete('/memories',response_model=R[None])
def clear(request:Request,user:User):
    memory.clear(request.app.state.db,user['id'])
    return ok(request)
