"""Persistent single-process work queue. SSE subscriptions only read its journal."""
import asyncio
import json
import logging
from app.agent.prompts import interview_messages
from app.agent.state_machine import transition
from app.agent.tools import question_bank, job_description, scorecard
from app.parsers.resume import extract
from app.services.common import ServiceError, dump, now, uid
from app.services.message import append_event
from app.services.session import enqueue_report

logger=logging.getLogger(__name__)

class WorkCancelled(Exception):
    pass

class Orchestrator:
    def __init__(self,database,settings,provider):
        self.db,self.settings,self.provider=database,settings,provider
        self.tasks=set()
        self.loop_task=None

    async def start(self):
        with self.db.transaction() as db:
            for row in db.execute("SELECT id FROM responses WHERE status='processing'").fetchall():
                append_event(db,row['id'],'error',{'code':'AGENT_INTERRUPTED','message':'服务重启中断了本轮生成，请重新提交回答','retryable':True})
                append_event(db,row['id'],'done',{})
                db.execute("UPDATE responses SET status='failed' WHERE id=?",(row['id'],))
            db.execute("UPDATE reports SET status='queued' WHERE status='processing'")
            db.execute("UPDATE resumes SET status='queued' WHERE status='processing'")
        self.loop_task=asyncio.create_task(self.loop())

    async def stop(self):
        if self.loop_task:
            self.loop_task.cancel()
            await asyncio.gather(self.loop_task,return_exceptions=True)
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.provider.close()

    async def loop(self):
        while True:
            while len(self.tasks)<4:
                job=None
                with self.db.transaction() as db:
                    for table in ('responses','reports','resumes'):
                        row=db.execute(f"SELECT id FROM {table} WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                        if row:
                            db.execute(f"UPDATE {table} SET status='processing' WHERE id=? AND status='queued'",(row['id'],))
                            job=(table,row['id']); break
                if not job: break
                task=asyncio.create_task(self.process(*job))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            await asyncio.sleep(self.settings.worker_interval)

    async def process(self,table,identifier):
        try:
            async with asyncio.timeout(self.settings.llm_timeout+30):
                if table=='responses': await self.process_response(identifier)
                elif table=='reports': await self.process_report(identifier)
                else: await self.process_resume(identifier)
        except WorkCancelled:
            pass
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Log exception type only; provider exceptions can contain private prompts.
            logger.warning('Work failed: %s %s',table,type(error).__name__)
            message=error.message if isinstance(error,ServiceError) else '处理失败，请稍后重试'
            code=error.code if isinstance(error,ServiceError) else 'AGENT_UNAVAILABLE'
            self.fail(table,identifier,code,message)

    def emit(self,response_id,event,payload):
        with self.db.transaction() as db:
            row=db.execute("SELECT status FROM responses WHERE id=?",(response_id,)).fetchone()
            if not row or row['status']!='processing': raise WorkCancelled()
            append_event(db,response_id,event,payload)

    def context(self,session_id):
        row=self.db.one('SELECT * FROM sessions WHERE id=?',(session_id,))
        if not row or row['status']=='cancelled': raise WorkCancelled()
        user=self.db.one('SELECT memory_enabled FROM users WHERE id=?',(row['user_id'],))
        memories=self.db.all('SELECT content FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT 10',(row['user_id'],)) if user['memory_enabled'] else []
        weak=self.db.all('SELECT dimension_key,note FROM weak_points WHERE user_id=? ORDER BY created_at DESC LIMIT 10',(row['user_id'],)) if user['memory_enabled'] else []
        return {'session':row,'scene':row['scene'],'sceneConfig':json.loads(row['scene_config']),
                'profile':json.loads(row['profile_snapshot']),'resume':json.loads(row['resume_snapshot']) if row['resume_snapshot'] else None,
                'memories':memories,'weakPoints':weak,
                'messages':self.db.all('SELECT * FROM messages WHERE session_id=? ORDER BY seq',(session_id,))}

    async def process_response(self,response_id):
        response=self.db.one('SELECT * FROM responses WHERE id=?',(response_id,))
        if not response: raise WorkCancelled()
        context=self.context(response['session_id']); session=context['session']
        answer=context['messages'][-1]['content']
        stage,turns=transition(session['stage'],session['stage_turns'],answer)
        context.update(stage=stage,stageTurns=turns)
        self.emit(response_id,'thinking',{})
        tool_call=uid('tool')
        self.emit(response_id,'tool_started',{'toolCallId':tool_call,'toolName':'question_bank.search'})
        keywords=context['sceneConfig'].get('targetRole','')+' '+answer
        context['questions']=question_bank.search(session['scene'],stage,keywords)
        self.emit(response_id,'tool_finished',{'toolCallId':tool_call,'toolName':'question_bank.search','status':'completed','questionIds':[q['questionId'] for q in context['questions']]})
        jd=context['sceneConfig'].get('jobDescription')
        if jd:
            tool_call=uid('tool')
            self.emit(response_id,'tool_started',{'toolCallId':tool_call,'toolName':'job_description.retrieve'})
            context['jd']=job_description.retrieve(jd)
            self.emit(response_id,'tool_finished',{'toolCallId':tool_call,'toolName':'job_description.retrieve','status':'completed'})
        message_id,content=uid('msg'),''
        async for delta in self.provider.stream(interview_messages(context),context):
            if not isinstance(delta,str) or len(content)+len(delta)>12000:
                raise ServiceError(503,'AGENT_UNAVAILABLE','模型回答超出约定长度')
            self.emit(response_id,'message_delta',{'messageId':message_id,'delta':delta,'offset':len(content)})
            content+=delta
        if not content.strip(): raise ServiceError(503,'AGENT_UNAVAILABLE','模型返回空回答，请重试')
        with self.db.transaction() as db:
            current=db.execute('SELECT status FROM responses WHERE id=?',(response_id,)).fetchone()
            if not current or current['status']!='processing': raise WorkCancelled()
            seq=db.execute('SELECT MAX(seq)+1 FROM messages WHERE session_id=?',(session['id'],)).fetchone()[0]
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)',(message_id,session['id'],seq,'assistant','review' if stage=='review' else 'question',content,'text',stage,None,now()))
            db.execute('UPDATE sessions SET stage=?,stage_turns=?,updated_at=? WHERE id=?',(stage,turns,now(),session['id']))
            if stage!=session['stage']: append_event(db,response_id,'stage_changed',{'stage':stage})
            append_event(db,response_id,'message_completed',{'messageId':message_id,'content':content,'stage':stage})
            if stage=='review':
                enqueue_report(db,session['id'])
                db.execute("UPDATE responses SET status='waiting_report' WHERE id=?",(response_id,))
            else:
                append_event(db,response_id,'done',{})
                db.execute("UPDATE responses SET status='completed' WHERE id=?",(response_id,))

    async def process_report(self,report_id):
        report=self.db.one('SELECT * FROM reports WHERE id=?',(report_id,))
        if not report: raise WorkCancelled()
        context=self.context(report['session_id'])
        result=await scorecard.generate(self.provider,context)
        stamp=now()
        result.update(reportId=report_id,sessionId=report['session_id'],mode='interview',status='completed',generatedAt=stamp)
        with self.db.transaction() as db:
            if not db.execute('SELECT 1 FROM reports WHERE id=?',(report_id,)).fetchone(): raise WorkCancelled()
            db.execute("UPDATE reports SET status='completed',content=?,generated_at=? WHERE id=?",(dump(result),stamp,report_id))
            db.execute("UPDATE sessions SET status='completed',updated_at=? WHERE id=?",(stamp,report['session_id']))
            for waiting in db.execute("SELECT id FROM responses WHERE session_id=? AND status='waiting_report'",(report['session_id'],)).fetchall():
                append_event(db,waiting['id'],'report_ready',{'reportId':report_id,'sessionId':report['session_id']})
                append_event(db,waiting['id'],'done',{})
                db.execute("UPDATE responses SET status='completed' WHERE id=?",(waiting['id'],))
            user_id=context['session']['user_id']
            enabled=db.execute('SELECT memory_enabled FROM users WHERE id=?',(user_id,)).fetchone()[0]
            # Store only report-derived dimension tags, never raw passwords or user text.
            if enabled and result['weakPointTags']:
                summary='下次面试重点练习：'+'、'.join(scorecard.DIMENSIONS[k] for k in result['weakPointTags'])
                db.execute('INSERT INTO memories VALUES (?,?,?,?,?)',(uid('mem'),user_id,report['session_id'],summary,stamp))

    async def process_resume(self,resume_id):
        row=self.db.one('SELECT * FROM resumes WHERE id=?',(resume_id,))
        if not row: raise WorkCancelled()
        result=await asyncio.to_thread(extract,row['file_data'],row['file_name'])
        with self.db.transaction() as db:
            db.execute("UPDATE resumes SET status='review_required',parsed_content=?,error=NULL,updated_at=? WHERE id=? AND status='processing'",(dump(result),now(),resume_id))

    def fail(self,table,identifier,code,message):
        with self.db.transaction() as db:
            row=db.execute(f'SELECT * FROM {table} WHERE id=?',(identifier,)).fetchone()
            if not row or row['status'] not in ('processing','waiting_report'): return
            if table=='responses':
                append_event(db,identifier,'error',{'code':code,'message':message,'retryable':True})
                append_event(db,identifier,'done',{})
                db.execute("UPDATE responses SET status='failed' WHERE id=?",(identifier,))
            elif table=='reports':
                db.execute("UPDATE reports SET status='failed',error=? WHERE id=?",(message,identifier))
                db.execute("UPDATE sessions SET status='failed',updated_at=? WHERE id=?",(now(),row['session_id']))
                for waiting in db.execute("SELECT id FROM responses WHERE session_id=? AND status='waiting_report'",(row['session_id'],)).fetchall():
                    append_event(db,waiting['id'],'error',{'code':code,'message':message,'retryable':True})
                    append_event(db,waiting['id'],'done',{})
                    db.execute("UPDATE responses SET status='failed' WHERE id=?",(waiting['id'],))
            else:
                db.execute("UPDATE resumes SET status='failed',error=?,updated_at=? WHERE id=?",(message,now(),identifier))
