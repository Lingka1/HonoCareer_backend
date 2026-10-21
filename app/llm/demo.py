"""Explicit local demo mode. Never masquerades as a cloud model."""
import asyncio
from app.agent.tools.scorecard import demo_scorecard

class DemoProvider:
    name='demo'
    async def stream(self,messages,context):
        stage=context['stage']
        answer=context['messages'][-1]['content']
        if stage=='review':
            text='本次模拟面试已结束。谢谢你的认真回答，接下来将整理四个维度的表现、回答证据和下一次练习建议。'
        else:
            question=context['questions'][min(context.get('stageTurns',1)-1,len(context['questions'])-1)]['question']
            if context.get('stageTurns',1)>1:
                question='请围绕刚才的经历补充：你个人做出的关键行动是什么，如何判断最终结果？'
            text=f'你提到了“{answer[:36]}”。{question}'
        for offset in range(0,len(text),8):
            await asyncio.sleep(0.008)
            yield text[offset:offset+8]
    async def score(self,context):
        return demo_scorecard(context)
    async def close(self):
        pass
