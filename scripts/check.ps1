param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$Python = Join-Path $Api ".venv/Scripts/python.exe"
$Pnpm = (Get-Command pnpm -ErrorAction SilentlyContinue)?.Source

if (-not (Test-Path $Python)) { & (Join-Path $PSScriptRoot "setup-api.ps1") }
if (-not $Pnpm) { throw "未找到 pnpm。" }

if (-not $SkipInstall -or -not (Test-Path (Join-Path $Root "node_modules"))) {
    Push-Location $Root
    try { & $Pnpm install --frozen-lockfile }
    finally { Pop-Location }
}

Push-Location $Api
try {
    & $Python -m ruff check src tests
    & $Python -m pytest --cov=password_detective --cov-fail-under=80
} finally { Pop-Location }

Push-Location $Root
try {
    & $Pnpm typecheck
    & $Pnpm test
    & $Pnpm build
    dotnet build ./apps/desktop-windows/PasswordDetective.Desktop.csproj --configuration Release
} finally { Pop-Location }

Write-Host "全部检查通过。"
