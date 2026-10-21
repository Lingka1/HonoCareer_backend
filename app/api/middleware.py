from collections import defaultdict, deque
import json
import time
from app.services.common import ServiceError, uid

class RateLimiter:
    def __init__(self):
        self.windows=defaultdict(deque)
    def consume(self,key,limit):
        stamp=time.monotonic(); window=self.windows[key]
        while window and window[0]<stamp-60: window.popleft()
        if len(window)>=limit: raise ServiceError(429,'RATE_LIMITED','请求过于频繁，请一分钟后重试')
        window.append(stamp)
        if len(self.windows)>10000:
            self.windows=defaultdict(deque,{k:v for k,v in self.windows.items() if v and v[-1]>stamp-60})

class BodyLimitMiddleware:
    """Bound chunked multipart requests before Starlette writes upload spools."""
    def __init__(self,app,max_bytes):
        self.app,self.max_bytes=app,max_bytes
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PATCH','PUT'):
            return await self.app(scope,receive,send)
        chunks=[]; size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            size+=len(message.get('body',b''))
            if size>self.max_bytes:
                request_id=scope.get('state',{}).get('request_id',uid('req'))
                body=json.dumps({'code':'FILE_TOO_LARGE','message':'请求体超过允许大小','requestId':request_id}).encode()
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
                await send({'type':'http.response.body','body':body})
                return
            chunks.append(message.get('body',b''))
            if not message.get('more_body',False): break
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)
