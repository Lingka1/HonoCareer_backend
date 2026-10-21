from typing import Literal
from fastapi import APIRouter,Request
from app.api.common import User,Limit,Cursor,Key,ok
from app.api.contracts import R,Page,Scene,ProfileCreateDTO,ProfilePatchDTO,ProfileVO,ProfileMatchVO,ResumeImportDTO
from app.services import profile
router=APIRouter(prefix='/profiles',tags=['面试画像'])

@router.get('',response_model=R[Page[ProfileVO]])
def listing(request:Request,user:User,type:Scene|None=None,limit:Limit=20,cursor:Cursor=None):
    return ok(request,profile.listing(request.app.state.db,request.app.state.settings,user['id'],type,limit,cursor))

@router.get('/matches',response_model=R[Page[ProfileMatchVO]])
def matches(request:Request,user:User,scene:Scene,mode:Literal['interview']='interview',limit:Limit=20,cursor:Cursor=None):
    return ok(request,profile.matches(request.app.state.db,request.app.state.settings,user['id'],scene,limit,cursor))

@router.post('',response_model=R[ProfileVO])
def create(body:ProfileCreateDTO,request:Request,user:User,idempotency_key:Key):
    return ok(request,profile.create(request.app.state.db,user['id'],body,idempotency_key))

@router.get('/{profile_id}',response_model=R[ProfileVO])
def get(profile_id:str,request:Request,user:User):
    return ok(request,profile.get(request.app.state.db,user['id'],profile_id))

@router.patch('/{profile_id}',response_model=R[ProfileVO])
def patch(profile_id:str,body:ProfilePatchDTO,request:Request,user:User):
    return ok(request,profile.patch(request.app.state.db,user['id'],profile_id,body))

@router.delete('/{profile_id}',response_model=R[None])
def delete(profile_id:str,request:Request,user:User):
    profile.delete(request.app.state.db,user['id'],profile_id)
    return ok(request)

@router.post('/{profile_id}/resume-import',response_model=R[ProfileVO])
def import_resume(profile_id:str,body:ResumeImportDTO,request:Request,user:User):
    return ok(request,profile.import_resume(request.app.state.db,user['id'],profile_id,body))
