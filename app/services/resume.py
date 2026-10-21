import hashlib
import json
from pathlib import Path
from app.api.contracts import ParsedContent
from app.services.common import ServiceError, dump, fingerprint, idem_get, idem_put, now, owned, paginate, uid

def view(row,detail=False):
    result={'resumeId':row['id'],'fileName':row['file_name'],'mimeType':row['mime_type'],'status':row['status'],'createdAt':row['created_at'],'updatedAt':row['updated_at']}
    if detail:
        result['parsedContent']=json.loads(row['parsed_content'])
        result['error']=row['error']
    return result

def upload(database,settings,user_id,name,content,key):
    name=Path(name.replace('\\','/')).name
    suffix=Path(name).suffix.lower()
    if suffix not in ('.pdf','.docx'):
        raise ServiceError(415,'UNSUPPORTED_FILE_TYPE','仅支持 PDF 和 DOCX 简历')
    if not content or len(content)>settings.max_file_bytes:
        raise ServiceError(413,'FILE_TOO_LARGE','文件不能为空且不得超过 10MB')
    if suffix=='.pdf' and not content.startswith(b'%PDF-') or suffix=='.docx' and not content.startswith(b'PK'):
        raise ServiceError(415,'UNSUPPORTED_FILE_TYPE','文件格式与扩展名不一致')
    digest=fingerprint({'fileName':name,'sha256':hashlib.sha256(content).hexdigest()})
    with database.transaction() as db:
        resource_id=idem_get(db,user_id,'resumes',key,digest)
        if resource_id: return view(owned(db,'resumes',resource_id,user_id))
        resource_id,stamp=uid('res'),now()
        mime='application/pdf' if suffix=='.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        db.execute('INSERT INTO resumes (id,user_id,file_name,mime_type,file_data,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(resource_id,user_id,name,mime,content,'uploaded',stamp,stamp))
        idem_put(db,user_id,'resumes',key,digest,resource_id)
        return view(owned(db,'resumes',resource_id,user_id))

def get(database,user_id,resource_id):
    with database.transaction() as db: return view(owned(db,'resumes',resource_id,user_id),True)

def listing(database,settings,user_id,limit,cursor):
    rows=[view(r) for r in database.all('SELECT id,file_name,mime_type,status,created_at,updated_at FROM resumes WHERE user_id=?',(user_id,))]
    return paginate(rows,limit,cursor,f'resumes:{user_id}',settings.jwt_secret,('updatedAt','resumeId'))

def parse(database,user_id,resource_id):
    with database.transaction() as db:
        row=owned(db,'resumes',resource_id,user_id)
        if row['job_id'] and row['status']!='failed': return {'jobId':row['job_id'],'status':row['status']}
        job_id=uid('job')
        db.execute("UPDATE resumes SET job_id=?,status='queued',error=NULL,updated_at=? WHERE id=?",(job_id,now(),resource_id))
        return {'jobId':job_id,'status':'queued'}

def parse_result(database,user_id,resource_id):
    with database.transaction() as db:
        row=owned(db,'resumes',resource_id,user_id)
        return {'status':row['status'],'jobId':row['job_id'],'error':row['error'],**ParsedContent.model_validate(json.loads(row['parsed_content'])).model_dump()}

def patch(database,user_id,resource_id,body):
    with database.transaction() as db:
        row=owned(db,'resumes',resource_id,user_id)
        if row['status'] in ('queued','processing'):
            raise ServiceError(409,'RESOURCE_STATE_CONFLICT','解析中，请等待完成后编辑')
        content=ParsedContent.model_validate({**json.loads(row['parsed_content']),**body.model_dump(exclude_unset=True)}).model_dump()
        db.execute("UPDATE resumes SET parsed_content=?,status='review_required',error=NULL,updated_at=? WHERE id=?",(dump(content),now(),resource_id))
        return view(owned(db,'resumes',resource_id,user_id),True)

def confirm(database,user_id,resource_id):
    with database.transaction() as db:
        row=owned(db,'resumes',resource_id,user_id)
        if row['status'] not in ('review_required','confirmed'):
            raise ServiceError(409,'RESOURCE_STATE_CONFLICT','请先解析或手动补充内容')
        db.execute("UPDATE resumes SET status='confirmed',updated_at=? WHERE id=?",(now(),resource_id))
        return view(owned(db,'resumes',resource_id,user_id),True)

def delete(database,user_id,resource_id):
    with database.transaction() as db:
        owned(db,'resumes',resource_id,user_id)
        db.execute('DELETE FROM resumes WHERE id=?',(resource_id,))
