# HonoCareer 面试后端

基于 FastAPI、SQLite 和 DeepSeek 的面试模拟后端。已实现求职、志愿者、社团三场景的完整文字面试：画像与已确认简历上下文、六阶段推进、动态追问、真实题库检索、持久化 SSE、四维评分及证据、历史、弱项与可控长期记忆。

附带响应式中文 Web 联调界面。ArkUI-X / ArkTS 原生客户端继续使用独立 HonoCareer_frontend 仓库；答辩模块保留原目录占位，未混入面试实现。

## 快速启动

使用 Python 3.12：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
```

编辑 `.env`，配置 `DEEPSEEK_API_KEY` 和至少32字符的 `JWT_SECRET`，然后：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

没有模型Key时，可以明确使用本地演示模式验证流程：

```powershell
.\start.ps1 -Demo
```

本地演示的界面与报告会标注“规则演示”，不会声称生成了真实云端AI评价。默认配置始终是 DeepSeek；缺少Key时返回明确错误。模型Key只存在服务端。

| 地址 | 内容 |
| --- | --- |
| http://127.0.0.1:8000/ | 面试训练台、流式对话、评分复盘、历史、弱项与记忆 |
| http://127.0.0.1:8000/docs | 可直接调试的 Swagger 接口文档 |
| http://127.0.0.1:8000/redoc | ReDoc 阅读版 |
| http://127.0.0.1:8000/openapi.json | 完整类型定义 |
| http://127.0.0.1:8000/health | 数据库和模型配置状态 |

首次进入界面注册账号即可开始；可通过 `REGISTRATION_ENABLED=false` 关闭自注册。未接入验证码渠道，因此不要求不存在的验证码。

## 接入约定

基础路径 `/api/v1`，除注册、登录、刷新令牌外使用 `Authorization: Bearer <accessToken>`。所有JSON成功响应为 `{code,message,data,requestId}`，列表为 `data:{items,nextCursor,hasMore}`。SSE为 `text/event-stream`，支持 `Last-Event-ID` 续传，重新订阅不会重复请求模型。

会话流程：开场 → 自我介绍 → 经历追问 → 情景提问 → 反问 → 复盘。服务端决定推进，经历与情景阶段可对证据不足追加一次追问。会话创建以 Idempotency-Key / clientSessionId 幂等；消息以 clientMessageId 幂等。后台任务独立于订阅运行，报告异步生成并校验评分证据。

语音按仓库原有分工由设备端完成 ASR/TTS。后端接收经用户确认的转写文本，并保留 inputMode=voice 与 modality=voice。Web界面的录音/朗读只在浏览器支持时可用，不替代鸿蒙真机验收。

## 目录与职责

```text
app/
  api/          HTTP、鉴权入口、DTO/VO与统一响应
  services/     账号、画像、简历、会话、消息、报告、弱项、记忆
  db/           SQLite模型、短事务、外键和唯一索引
  agent/        阶段状态机、上下文编排、真实工具、评分校验
  llm/          DeepSeek流适配与显式演示provider
  parsers/      PDF/Word保守文本提取，缺失资料不虚构
  web/          无外部CDN的响应式中文联调界面
tests/          面试端到端、鉴权隔离、幂等、续传和恢复测试
docs/           中文约定、开发说明与生成的OpenAPI
scripts/        Schema导出工具
```

## 测试与文档

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\export_openapi.py
```

- [接口文档](docs/接口文档.md)：路径、参数、类型、错误码、SSE与飞书草案修正。
- [后端开发文档](docs/后端开发文档.md)：分层、队列、模型、存储与客户端接入。
- [OpenAPI](docs/openapi.json)：由实际路由和Pydantic生成，无悬空引用。

## 当前运行边界

采用单实例SQLite和单个uvicorn worker，最多4个并行后台任务。多进程部署前需要任务租约/共享队列与共享限流器。数据库、原文件及本地随机JWT密钥保存在忽略的 `data/`；`.env` 与密钥不提交。生产环境需配置TLS、独立JWT密钥、备份和服务端数据保留策略。

真实云端端到端验收需要项目方DeepSeek Key；测试使用可注入provider及HTTP协议模拟。扫描件OCR、答辩、鸿蒙真机语音以及ArkUI-X三端安装编译尚未在本次实现中验收。
