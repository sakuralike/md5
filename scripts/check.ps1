param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$Python = Join-Path $Api ".venv/Scripts/python.exe"
$Pnpm = (Get-Command pnpm -ErrorAction SilentlyContinue)?.Source
$MigrationDatabase = Join-Path $Api ".local/migration-check.db"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败（退出码 $LASTEXITCODE）：$Command $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $Python)) { & (Join-Path $PSScriptRoot "setup-api.ps1") }
if (-not $Pnpm) { throw "未找到 pnpm。" }

if (-not $SkipInstall -or -not (Test-Path (Join-Path $Root "node_modules"))) {
    Push-Location $Root
    try { Invoke-Checked $Pnpm install --frozen-lockfile }
    finally { Pop-Location }
}

Push-Location $Api
try {
    Invoke-Checked $Python -m ruff check src tests
    Invoke-Checked $Python -m pytest --cov=password_detective --cov-fail-under=80

    $PreviousAppEnv = $env:APP_ENV
    $PreviousSecret = $env:APP_SECRET_KEY
    $PreviousDatabaseUrl = $env:DATABASE_URL
    try {
        if (Test-Path -LiteralPath $MigrationDatabase) {
            Remove-Item -LiteralPath $MigrationDatabase -Force
        }
        $env:APP_ENV = "test"
        $env:APP_SECRET_KEY = "synthetic-local-migration-secret"
        $env:DATABASE_URL = "sqlite:///./.local/migration-check.db"
        Invoke-Checked $Python -m alembic upgrade head
        Invoke-Checked $Python -m alembic downgrade base
        Invoke-Checked $Python -m alembic upgrade head
    } finally {
        $env:APP_ENV = $PreviousAppEnv
        $env:APP_SECRET_KEY = $PreviousSecret
        $env:DATABASE_URL = $PreviousDatabaseUrl
        if (Test-Path -LiteralPath $MigrationDatabase) {
            Remove-Item -LiteralPath $MigrationDatabase -Force
        }
    }
} finally {
    Pop-Location
}

Push-Location $Root
try {
    Invoke-Checked $Pnpm typecheck
    Invoke-Checked $Pnpm test
    Invoke-Checked $Pnpm build
    Invoke-Checked dotnet build ./apps/desktop-windows/PasswordDetective.Desktop.csproj --configuration Release
} finally {
    Pop-Location
}

Write-Host "全部检查通过。"
