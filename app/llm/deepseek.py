import json
import httpx
from app.agent.prompts import score_messages
from app.services.common import ServiceError

class DeepSeekProvider:
    name='deepseek'
    def __init__(self,settings,transport=None):
        self.settings=settings
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout,connect=10),transport=transport)

    def headers(self):
        if not self.settings.deepseek_api_key:
            raise ServiceError(503,'AGENT_UNAVAILABLE','尚未配置 DeepSeek API Key，请联系服务管理员')
        return {'Authorization':'Bearer '+self.settings.deepseek_api_key,'Content-Type':'application/json'}

    def validate_status(self,response):
        if response.status_code==429:
            raise ServiceError(429,'RATE_LIMITED','模型服务繁忙，请稍后重试')
        if response.is_error:
            raise ServiceError(503,'AGENT_UNAVAILABLE','模型服务暂不可用，请稍后重试')

    async def stream(self,messages,context):
        body={'model':self.settings.deepseek_model,'messages':messages,'stream':True,'max_tokens':900,'temperature':0.7}
        try:
            async with self.client.stream('POST',self.settings.deepseek_base_url.rstrip('/')+'/chat/completions',headers=self.headers(),json=body) as response:
                self.validate_status(response)
                received=False; finished=False
                async for line in response.aiter_lines():
                    if not line.startswith('data:'): continue
                    raw=line[5:].strip()
                    if raw=='[DONE]':
                        finished=True
                        break
                    chunk=json.loads(raw)
                    if chunk.get('error'): raise ValueError('provider returned error')
                    choices=chunk.get('choices') or []
                    if choices:
                        content=choices[0].get('delta',{}).get('content')
                        if content:
                            received=True
                            yield content
                if not received or not finished: raise ValueError('incomplete model answer')
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            raise ServiceError(503,'AGENT_UNAVAILABLE','模型响应中断，请重试本轮回答') from None

    async def score(self,context):
        try:
            response=await self.client.post(self.settings.deepseek_base_url.rstrip('/')+'/chat/completions',headers=self.headers(),json={'model':self.settings.deepseek_model,'messages':score_messages(context),'stream':False,'response_format':{'type':'json_object'},'max_tokens':3000,'temperature':0.2})
            self.validate_status(response)
            return json.loads(response.json()['choices'][0]['message']['content'])
        except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError):
            raise ServiceError(503,'AGENT_UNAVAILABLE','评分响应无效，请重新生成报告') from None

    async def close(self):
        await self.client.aclose()
