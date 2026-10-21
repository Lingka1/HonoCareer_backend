from fastapi import APIRouter,Request
from app.api.common import User,ok
from app.api.contracts import R,UserPatchDTO,UserVO
from app.services import user as service
router=APIRouter(prefix='/users',tags=['用户'])

@router.get('/me',response_model=R[UserVO])
def get(request:Request,user:User):
    return ok(request,service.view(user))

@router.patch('/me',response_model=R[UserVO])
def patch(body:UserPatchDTO,request:Request,user:User):
    return ok(request,service.patch(request.app.state.db,user['id'],body))
