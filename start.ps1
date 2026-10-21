param([switch]$Demo,[int]$Port=8000)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw '请先按 README 创建 .venv 并安装依赖。'
}
if ($Demo) { $env:LLM_PROVIDER='demo' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
