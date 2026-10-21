import asyncio
import time
from typing import Annotated
from fastapi import APIRouter,Header,Request
from fastapi.responses import StreamingResponse
from app.api.common import User,Limit,Cursor,ok
from app.api.contracts import R,Page,MessageCreateDTO,MessageVO,MessageAcceptedVO
from app.services import message
from app.services.common import dump
router=APIRouter(prefix='/sessions',tags=['面试消息与 SSE'])

@router.post('/{session_id}/messages',response_model=R[MessageAcceptedVO])
def submit(session_id:str,body:MessageCreateDTO,request:Request,user:User):
    return ok(request,message.submit(request.app.state.db,user['id'],session_id,body))

@router.get('/{session_id}/messages',response_model=R[Page[MessageVO]])
def listing(session_id:str,request:Request,user:User,limit:Limit=20,cursor:Cursor=None):
    return ok(request,message.listing(request.app.state.db,request.app.state.settings,user['id'],session_id,limit,cursor))

@router.get('/{session_id}/responses/{response_id}/events',response_class=StreamingResponse,
            responses={200:{'description':'SSE journal; event discriminates each JSON data envelope.','content':{'text/event-stream':{'schema':{'type':'string'}}}}})
async def events(session_id:str,response_id:str,request:Request,user:User,last_event_id:Annotated[str|None,Header(alias='Last-Event-ID',max_length=120)]=None):
    database=request.app.state.db
    last_seq=message.validate_stream(database,user['id'],session_id,response_id,last_event_id)
    async def stream():
        nonlocal last_seq
        heartbeat=time.monotonic()
        while not await request.is_disconnected():
            # Read the journal and terminal state in one snapshot, so a concurrent
            # completion cannot make us close before emitting its final events.
            with database.transaction() as db:
                rows=[dict(row) for row in db.execute('SELECT * FROM events WHERE response_id=? AND seq>? ORDER BY seq',(response_id,last_seq))]
                current=db.execute('SELECT status FROM responses WHERE id=?',(response_id,)).fetchone()
            for row in rows:
                last_seq=row['seq']
                yield f"id: {row['id']}\nevent: {row['event']}\ndata: {dump(message.event_view(row))}\n\n"
            if not current or current['status'] in ('completed','failed','cancelled'): break
            if time.monotonic()-heartbeat>15:
                yield ': heartbeat\n\n'; heartbeat=time.monotonic()
            await asyncio.sleep(0.04)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache, no-store','X-Accel-Buffering':'no'})
