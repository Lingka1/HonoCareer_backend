import re
from app.api.contracts import Scorecard
from app.services.common import ServiceError

DIMENSIONS={'expression_clarity':'表达清晰度','logic':'逻辑性','role_match':'岗位/场景匹配度','adaptability':'应变能力'}

def demo_scorecard(context):
    answers=[m for m in context['messages'] if m['role']=='user']
    text='\n'.join(m['content'] for m in answers)
    evidence=[m['id'] for m in answers]
    if not answers:
        return {'dimensions':[{'key':key,'label':label,'score':0,'evidence':[],'strengths':['尚无可评价的回答'],'issues':['本次未提交回答，证据不足'],'suggestions':['完成一段自我介绍并回答经历和情景问题后再查看评分']} for key,label in DIMENSIONS.items()],
                'summary':'未提交回答，无法评估面试能力。','actionItems':['先完成一次有实际回答的模拟面试']}
    scores={
        'expression_clarity':min(90,35+len(text)//25),
        'logic':min(90,35+sum(x in text for x in ['首先','其次','因此','结果','目标','行动','最后'])*7),
        'role_match':min(90,40+len(text)//50+10*bool(context.get('profile'))),
        'adaptability':min(90,35+sum(m['stage']=='situational_questions' for m in answers)*18),
    }
    suggestions={'expression_clarity':'用60秒按背景、个人职责和结果组织一次自我介绍',
                 'logic':'用 STAR 结构重讲一个项目，补充一个可核实的结果指标',
                 'role_match':'选出场景要求的两项能力，为每项准备一个具体事例',
                 'adaptability':'练习一次突发冲突情景，说明优先级、沟通对象与备选方案'}
    return {'dimensions':[{'key':key,'label':label,'score':scores[key],'evidence':evidence,
            'strengths':['已提供可供复盘的实际回答'],'issues':['需要进一步补充个人行动与结果证据'],
            'suggestions':[suggestions[key]]} for key,label in DIMENSIONS.items()],
            'summary':'本地规则演示评分：用于验证流程与证据引用，不代表云端 AI 对能力的评估。',
            'actionItems':[suggestions['logic'],suggestions['adaptability']]}

async def generate(provider,context):
    answers=[m for m in context['messages'] if m['role']=='user']
    raw=await provider.score(context) if answers else demo_scorecard(context)
    try:
        result=Scorecard.model_validate(raw).model_dump()
        if {d['key'] for d in result['dimensions']}!=set(DIMENSIONS): raise ValueError('dimension mismatch')
        allowed={m['id'] for m in answers}
        for dimension in result['dimensions']:
            if set(dimension['evidence'])-allowed: raise ValueError('fabricated evidence')
            if answers and not dimension['evidence']: raise ValueError('missing evidence')
            dimension['label']=DIMENSIONS[dimension['key']]
        result['overallScore']=int(sum(d['score'] for d in result['dimensions'])/4+0.5)
        result['weakPointTags']=[d['key'] for d in result['dimensions'] if d['score']<70]
        result['evaluationSource']=provider.name if answers else 'insufficient_evidence'
        return result
    except ValueError:
        raise ServiceError(503,'AGENT_UNAVAILABLE','评分格式或证据无效，请重新生成报告') from None
