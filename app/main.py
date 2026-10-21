"""FastAPI entry point and application lifespan for the interview backend."""
from contextlib import asynccontextmanager
from pathlib import Path
import logging
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from pydantic import ValidationError
from app.api import auth,users,profiles,resumes,sessions,messages,reports,weak_points,memories
from app.api.contracts import ErrorVO
from app.api.middleware import BodyLimitMiddleware,RateLimiter
from app.agent.orchestrator import Orchestrator
from app.config import Settings
from app.db.session import Database
from app.llm.deepseek import DeepSeekProvider
from app.llm.demo import DemoProvider
from app.services.common import ServiceError,uid

WEB=Path(__file__).parent/'web'
logger=logging.getLogger(__name__)

def create_app(settings=None,provider=None):
    settings=settings or Settings.from_env()
    @asynccontextmanager
    async def lifespan(app):
        settings.prepare()
        database=Database(settings.database_path); database.initialize()
        client=provider or (DemoProvider() if settings.llm_provider=='demo' else DeepSeekProvider(settings))
        app.state.db,app.state.settings,app.state.provider=database,settings,client
        app.state.worker=Orchestrator(database,settings,client)
        await app.state.worker.start()
        try: yield
        finally: await app.state.worker.stop()

    application=FastAPI(title='HonoCareer 面试后端',version='1.0.0',lifespan=lifespan,
                        description='求职、志愿者、社团模拟面试。Bearer 鉴权，JSON R 包装；SSE 为 text/event-stream。',
                        responses={code:{'model':ErrorVO} for code in (400,401,403,404,409,413,415,422,429,500,503)})
    application.state.limiter=RateLimiter()

    @application.exception_handler(ServiceError)
    async def business_error(request,error):
        result={'code':error.code,'message':error.message,'requestId':getattr(request.state,'request_id',uid('req'))}
        if error.details: result['details']=error.details
        return JSONResponse(result,status_code=error.status,headers={'Retry-After':'60'} if error.status==429 else {'WWW-Authenticate':'Bearer'} if error.status==401 else {})

    async def validation_error(request,error):
        details=[{'field':'.'.join(str(x) for x in item['loc']),'reason':item['msg']} for item in error.errors()]
        return await business_error(request,ServiceError(400,'VALIDATION_ERROR','请求参数不符合接口约定',details))
    application.add_exception_handler(RequestValidationError,validation_error)
    application.add_exception_handler(ValidationError,validation_error)

    @application.exception_handler(HTTPException)
    async def http_error(request,error):
        return await business_error(request,ServiceError(error.status_code,'NOT_FOUND' if error.status_code==404 else 'HTTP_ERROR','接口不存在' if error.status_code==404 else '请求方法或格式不支持'))

    @application.exception_handler(Exception)
    async def unknown_error(request,error):
        logger.error('Request failed: %s',type(error).__name__)
        return await business_error(request,ServiceError(500,'INTERNAL_ERROR','服务暂时异常，请稍后重试'))

    application.add_middleware(BodyLimitMiddleware,max_bytes=settings.max_file_bytes+512*1024)

    @application.middleware('http')
    async def request_context(request,call_next):
        request.state.request_id=uid('req')
        try:
            if request.method=='POST' and request.url.path in ('/api/v1/auth/login','/api/v1/auth/register','/api/v1/auth/refresh'):
                application.state.limiter.consume('auth:'+(request.client.host if request.client else 'unknown'),20)
            response=await call_next(request)
        except ServiceError as error:
            response=await business_error(request,error)
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        if request.url.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control','no-store')
        return response

    application.add_middleware(CORSMiddleware,allow_origins=list(settings.allowed_origins),allow_credentials=False,
                               allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Authorization','Content-Type','Idempotency-Key','Last-Event-ID'],expose_headers=['X-Request-ID','Retry-After'])
    for module in (auth,users,profiles,resumes,sessions,messages,reports,weak_points,memories):
        application.include_router(module.router,prefix='/api/v1')

    @application.get('/health',tags=['服务状态'])
    def health(request:Request):
        database_ok=bool(request.app.state.db.one('SELECT 1 AS ok'))
        return {'code':0,'message':'ok','data':{'status':'ok' if database_ok else 'degraded','provider':request.app.state.provider.name,
                'llmConfigured':request.app.state.provider.name=='demo' or bool(settings.deepseek_api_key),'registrationEnabled':settings.registration_enabled},'requestId':request.state.request_id}

    if WEB.is_dir():
        application.mount('/assets',StaticFiles(directory=WEB),name='assets')
        @application.get('/',include_in_schema=False)
        def home(): return FileResponse(WEB/'index.html')
    return application

app=create_app()
