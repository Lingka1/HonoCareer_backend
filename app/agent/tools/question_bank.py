"""A real, curated local question-bank search with scene/stage/tag ranking."""
QUESTIONS = [
 ('job-intro','employment','self_introduction','motivation','你为什么选择这个岗位？请结合一段具体经历说明你的优势。'),
 ('job-project','employment','experience_followup','backend api Python Java SQL','请选一个最有代表性的项目，说明你的职责、关键取舍及可量化的结果。'),
 ('job-debug','employment','experience_followup','backend api 性能 排查','项目中遇到过最难定位的问题是什么？你怎样验证根因并评估修复效果？'),
 ('job-team','employment','experience_followup','协作 产品 设计 前端','请介绍一次团队意见不一致的经历，说明你采取的行动及最终结果。'),
 ('job-situation','employment','situational_questions','风险 优先级','如果上线前发现核心功能有风险，而交付时间不变，你会如何处理？'),
 ('job-feedback','employment','situational_questions','沟通 客户','如果需求方临时提出变化，你会如何澄清需求并与团队协商？'),
 ('job-ask','employment','candidate_questions','','关于岗位职责、团队协作或成长支持，你希望向面试官了解什么？'),
 ('vol-intro','volunteer','self_introduction','动机 服务','你为什么希望参加这次志愿服务？你的经历能带来哪些帮助？'),
 ('vol-exp','volunteer','experience_followup','服务 沟通','请介绍一次帮助他人的经历，说明你如何判断对方的真实需要以及服务结果。'),
 ('vol-team','volunteer','experience_followup','组织 团队','请分享一次活动协作经历，你具体承担了什么任务，如何确保按时完成？'),
 ('vol-situation','volunteer','situational_questions','冲突 应急','如果服务现场有人情绪激动，同时排队人数不断增加，你会怎样处理？'),
 ('vol-time','volunteer','situational_questions','时间 责任','如果志愿排班与紧急课程任务冲突，你会如何安排并沟通？'),
 ('vol-ask','volunteer','candidate_questions','','对于服务内容、排班或岗前培训，你有什么希望了解的问题？'),
 ('club-intro','club','self_introduction','兴趣 动机','你为什么选择这个社团？希望投入哪些能力和时间？'),
 ('club-exp','club','experience_followup','项目 兴趣','请分享一次与社团方向有关的实践，你承担了什么角色，有哪些具体成果？'),
 ('club-team','club','experience_followup','协作 活动','请介绍一次与不同意见的同学合作的经历，你是如何推进任务的？'),
 ('club-situation','club','situational_questions','活动 组织','如果活动临近但核心成员临时无法到场，你会怎样调整分工并保证活动进行？'),
 ('club-time','club','situational_questions','时间 学习','如果社团任务与课程安排冲突，你会如何排序并与负责人沟通？'),
 ('club-ask','club','candidate_questions','','关于社团的项目、分工或新人培养，你想进一步了解什么？'),
]

def search(scene,stage,keywords='',used_ids=()):
    tokens=[s.lower() for s in keywords.split() if s]
    candidates=[]
    for identifier,item_scene,item_stage,tags,question in QUESTIONS:
        if item_scene==scene and item_stage==stage:
            score=sum(token in (tags+' '+question).lower() for token in tokens) - (100 if identifier in used_ids else 0)
            candidates.append((score,identifier,question))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    return [{'questionId':x[1],'question':x[2],'source':'curated_local_bank'} for x in candidates[:2]]
