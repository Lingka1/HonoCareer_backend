import json
from app.services.common import ServiceError, owned

def get(database,user_id,session_id):
    with database.transaction() as db:
        session=owned(db,'sessions',session_id,user_id)
        report=db.execute('SELECT * FROM reports WHERE session_id=?',(session_id,)).fetchone()
        if not report or report['status'] in ('queued','processing'):
            if session['status']=='cancelled': raise ServiceError(409,'SESSION_STATE_CONFLICT','取消的会话没有评分报告')
            return None
        if report['status']=='failed': raise ServiceError(503,'AGENT_UNAVAILABLE',report['error'] or '报告生成失败，请再次结束会话重试')
        return json.loads(report['content'])
