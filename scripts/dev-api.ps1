$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$Python = Join-Path $Api ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) { throw "请先运行 scripts/setup-api.ps1" }

$env:APP_ENV = $env:APP_ENV ?? "local"
$env:AUTO_CREATE_TABLES = $env:AUTO_CREATE_TABLES ?? "true"
Push-Location $Api
try { & $Python -m uvicorn password_detective.main:app --reload --host 127.0.0.1 --port 8000 }
finally { Pop-Location }
