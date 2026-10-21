import json
from app.api.contracts import DETAILS
from app.services.common import ServiceError, dump, fingerprint, idem_get, idem_put, now, owned, paginate, uid

def view(row):
    detail = json.loads(row['detail'])
    required = {'employment':'targetRole','volunteer':'activityType','club':'targetClub'}[row['type']]
    return {'profileId':row['id'],'type':row['type'],'displayName':row['display_name'],
            'baseInfo':json.loads(row['base_info']),'detail':detail,'version':row['version'],
            'completionStatus':'ready' if detail.get(required) else 'draft',
            'createdAt':row['created_at'],'updatedAt':row['updated_at']}

def create(database,user_id,body,key):
    data=body.model_dump(mode='json'); digest=fingerprint(data)
    with database.transaction() as db:
        resource_id=idem_get(db,user_id,'profiles',key,digest)
        if resource_id:
            return view(owned(db,'profiles',resource_id,user_id))
        resource_id,stamp=uid('prf'),now()
        db.execute('INSERT INTO profiles VALUES (?,?,?,?,?,?,1,?,?)',(resource_id,user_id,data['type'],data['displayName'],dump(data['baseInfo']),dump(data['detail']),stamp,stamp))
        idem_put(db,user_id,'profiles',key,digest,resource_id)
        return view(owned(db,'profiles',resource_id,user_id))

def get(database,user_id,profile_id):
    with database.transaction() as db:
        return view(owned(db,'profiles',profile_id,user_id))

def listing(database,settings,user_id,type,limit,cursor):
    rows=[view(x) for x in database.all('SELECT * FROM profiles WHERE user_id=?',(user_id,)) if not type or x['type']==type]
    return paginate(rows,limit,cursor,f'profiles:{user_id}:{type}',settings.jwt_secret,('updatedAt','profileId'))

def matches(database,settings,user_id,scene,limit,cursor):
    result=listing(database,settings,user_id,scene,limit,cursor)
    for item in result['items']:
        item.update(matchReason='画像类型与当前面试场景一致',isRecommended=item['completionStatus']=='ready')
    return result

def patch(database,user_id,profile_id,body):
    data=body.model_dump(exclude_unset=True,mode='json')
    with database.transaction() as db:
        old=owned(db,'profiles',profile_id,user_id)
        if old['version']!=body.version:
            raise ServiceError(409,'PROFILE_VERSION_CONFLICT','画像已更新，请刷新后重试')
        base={**json.loads(old['base_info']),**data.get('baseInfo',{})}
        detail=DETAILS[old['type']].model_validate({**json.loads(old['detail']),**data.get('detail',{})}).model_dump()
        db.execute('UPDATE profiles SET display_name=?,base_info=?,detail=?,version=version+1,updated_at=? WHERE id=?', (data.get('displayName',old['display_name']),dump(base),dump(detail),now(),profile_id))
        return view(owned(db,'profiles',profile_id,user_id))

def delete(database,user_id,profile_id):
    with database.transaction() as db:
        owned(db,'profiles',profile_id,user_id)
        db.execute('DELETE FROM profiles WHERE id=?',(profile_id,))

def import_resume(database,user_id,profile_id,body):
    with database.transaction() as db:
        profile=owned(db,'profiles',profile_id,user_id)
        resume=owned(db,'resumes',body.resumeId,user_id)
        if profile['type']!='employment':
            raise ServiceError(422,'PROFILE_TYPE_MISMATCH','简历导入仅用于求职画像')
        if resume['status']!='confirmed':
            raise ServiceError(422,'MATERIAL_NOT_CONFIRMED','请先确认简历解析结果')
        content=json.loads(resume['parsed_content']); base=json.loads(profile['base_info']); detail=json.loads(profile['detail'])
        for field in body.selectedFields:
            if field=='skills':
                detail['skills']=content.get(field,[])
            elif field=='projects':
                detail['projectExperience']=[(p['name']+' '+p.get('description','')).strip() for p in content.get(field,[])]
            elif field=='education' and content.get(field):
                item=content[field][0]
                for k in ('school','major','degree'):
                    if item.get(k): base[k]=item[k]
            elif field=='certificates':
                detail['certificates']=content.get(field,[])
        if base==json.loads(profile['base_info']) and detail==json.loads(profile['detail']):
            return view(profile)
        db.execute('UPDATE profiles SET base_info=?,detail=?,version=version+1,updated_at=? WHERE id=?',(dump(base),dump(detail),now(),profile_id))
        return view(owned(db,'profiles',profile_id,user_id))
