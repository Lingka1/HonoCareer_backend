"""Server-owned bounded stages, with one extra evidence follow-up when needed."""
import re
STAGES=('opening','self_introduction','experience_followup','situational_questions','candidate_questions','review')
LABELS=dict(zip(STAGES,('开场','自我介绍','经历追问','情景提问','反问','复盘')))

def transition(stage,stage_turns,answer):
    if stage not in STAGES: raise ValueError('Unknown stage')
    lacks_evidence=len(answer)<100 or not re.search(r'\d|结果|最终|因此|改进|完成|影响',answer)
    if stage in ('experience_followup','situational_questions') and stage_turns<2 and lacks_evidence:
        return stage,stage_turns+1
    return STAGES[min(STAGES.index(stage)+1,len(STAGES)-1)],1
