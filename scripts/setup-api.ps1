$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$VenvPython = Join-Path $Api ".venv/Scripts/python.exe"

if (-not (Test-Path $VenvPython)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "未找到 Python 3.12+。" }
    & $python.Source -m venv (Join-Path $Api ".venv")
}

& $VenvPython -m pip install --disable-pip-version-check -e "$Api[dev]"
Write-Host "API 开发环境已就绪。"
