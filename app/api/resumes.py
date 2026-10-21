from typing import Annotated
from urllib.parse import quote
from fastapi import APIRouter,Request,UploadFile,File,Response
from app.api.common import User,Limit,Cursor,Key,ok
from app.api.contracts import R,Page,ResumeVO,ResumeParseVO,ParseJobVO,ParsedPatchDTO
from app.services import resume
from app.services.common import owned
router=APIRouter(prefix='/resumes',tags=['简历上下文'])

@router.post('',response_model=R[ResumeVO])
async def upload(request:Request,user:User,idempotency_key:Key,file:Annotated[UploadFile,File()]):
    content=await file.read(request.app.state.settings.max_file_bytes+1)
    await file.close()
    return ok(request,resume.upload(request.app.state.db,request.app.state.settings,user['id'],file.filename or 'resume',content,idempotency_key))

@router.get('',response_model=R[Page[ResumeVO]])
def listing(request:Request,user:User,limit:Limit=20,cursor:Cursor=None):
    return ok(request,resume.listing(request.app.state.db,request.app.state.settings,user['id'],limit,cursor))

@router.get('/{resume_id}',response_model=R[ResumeVO])
def get(resume_id:str,request:Request,user:User):
    return ok(request,resume.get(request.app.state.db,user['id'],resume_id))

@router.get('/{resume_id}/file',response_class=Response,responses={200:{'content':{'application/octet-stream':{}}}})
def file(resume_id:str,request:Request,user:User):
    with request.app.state.db.transaction() as db: row=owned(db,'resumes',resume_id,user['id'])
    return Response(row['file_data'],media_type=row['mime_type'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['file_name']),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.post('/{resume_id}/parse',response_model=R[ParseJobVO])
def parse(resume_id:str,request:Request,user:User):
    return ok(request,resume.parse(request.app.state.db,user['id'],resume_id))

@router.get('/{resume_id}/parse',response_model=R[ResumeParseVO])
def parse_result(resume_id:str,request:Request,user:User):
    return ok(request,resume.parse_result(request.app.state.db,user['id'],resume_id))

@router.patch('/{resume_id}/parsed-content',response_model=R[ResumeVO])
def patch(resume_id:str,body:ParsedPatchDTO,request:Request,user:User):
    return ok(request,resume.patch(request.app.state.db,user['id'],resume_id,body))

@router.post('/{resume_id}/confirm',response_model=R[ResumeVO])
def confirm(resume_id:str,request:Request,user:User):
    return ok(request,resume.confirm(request.app.state.db,user['id'],resume_id))

@router.delete('/{resume_id}',response_model=R[None])
def delete(resume_id:str,request:Request,user:User):
    resume.delete(request.app.state.db,user['id'],resume_id)
    return ok(request)
