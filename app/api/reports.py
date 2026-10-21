from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from app.api.common import User,ok
from app.api.contracts import R,ReportVO
from app.services import report
router=APIRouter(prefix='/sessions',tags=['面试复盘'])

@router.get('/{session_id}/report',response_model=R[ReportVO],responses={202:{'description':'REPORT_PENDING'}})
def get(session_id:str,request:Request,user:User):
    result=report.get(request.app.state.db,user['id'],session_id)
    if result is None:
        return JSONResponse({'code':'REPORT_PENDING','message':'报告尚未生成，请稍后查询','data':None,'requestId':request.state.request_id},status_code=202,headers={'Retry-After':'1'})
    return ok(request,result)
