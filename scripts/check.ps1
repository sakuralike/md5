param(
    [switch]$SkipInstall,
    [switch]$IncludeE2E,
    [switch]$IncludeCrossBrowserE2E,
    [switch]$IncludeSecurity,
    [switch]$IncludeRecovery,
    [switch]$IncludePerformance,
    [switch]$IncludeMonitoring,
    [switch]$IncludeKeyRotation,
    [switch]$IncludeStability,
    [switch]$IncludeStagingReadiness,
    [switch]$IncludeStagingEvidence,
    [switch]$IncludeStagingAdapters
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$Python = Join-Path $Api ".venv/Scripts/python.exe"
$PnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
$Pnpm = if ($PnpmCommand) { $PnpmCommand.Source } else { $null }
$MigrationDatabase = Join-Path $Api ".local/migration-check.db"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $Python)) { & (Join-Path $PSScriptRoot "setup-api.ps1") }
if (-not $Pnpm) { throw "pnpm was not found." }

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
    Invoke-Checked $Pnpm lint
    Invoke-Checked $Pnpm typecheck
    Invoke-Checked $Pnpm test
    Invoke-Checked $Pnpm build
    if ($IncludeSecurity) {
        Invoke-Checked pwsh ./scripts/security-gate.ps1 -PythonCommand $Python
        Invoke-Checked pwsh ./scripts/dast-security-gate.ps1 -PythonCommand $Python
    }
    if ($IncludeRecovery) {
        Invoke-Checked pwsh ./scripts/recovery-drill.ps1
        Invoke-Checked $Python ./scripts/verify_recovery_evidence.py --report ./.local/recovery-wp4-iteration-6/recovery-report.json --write-checksums
    }
    if ($IncludePerformance) {
        Invoke-Checked pwsh ./scripts/performance-baseline.ps1 -PythonCommand $Python
    }
    if ($IncludeKeyRotation) {
        Invoke-Checked $Python ./scripts/candidate-secret-rotation-drill.py
        Invoke-Checked $Python ./scripts/verify_candidate_secret_rotation_evidence.py --report ./.local/candidate-secret-rotation-wp4-iteration-10/rotation-report.json --write-checksums
    }
    if ($IncludeStability) {
        Invoke-Checked $Python -m ruff check ./scripts/multi_instance_stability_probe.py ./scripts/verify_multi_instance_stability_evidence.py ./scripts/tests/test_verify_multi_instance_stability_evidence.py
        Invoke-Checked $Python -m pytest ./scripts/tests/test_verify_multi_instance_stability_evidence.py
        Invoke-Checked pwsh ./scripts/multi-instance-stability-drill.ps1 -PythonCommand $Python
        Invoke-Checked $Python ./scripts/verify_multi_instance_stability_evidence.py --report ./.local/multi-instance-stability-wp4-iteration-11/multi-instance-stability-report.json --write-checksums
    }
    if ($IncludeStagingReadiness) {
        Invoke-Checked $Python -m ruff check ./scripts/verify_staging_readiness_profile.py ./scripts/tests/test_verify_staging_readiness_profile.py
        Invoke-Checked $Python -m pytest ./scripts/tests/test_verify_staging_readiness_profile.py
        Invoke-Checked pwsh ./scripts/staging-readiness-plan.ps1 -PythonCommand $Python
    }
    if ($IncludeStagingEvidence) {
        Invoke-Checked $Python -m ruff check ./scripts/verify_staging_execution_evidence.py ./scripts/tests/test_verify_staging_execution_evidence.py
        Invoke-Checked $Python -m pytest ./scripts/tests/test_verify_staging_execution_evidence.py
        Invoke-Checked pwsh ./scripts/staging-evidence-contract.ps1 -PythonCommand $Python
    }
    if ($IncludeStagingAdapters) {
        Invoke-Checked $Python -m ruff check ./scripts/materialize_staging_execution_evidence.py ./scripts/adapt_staging_platform_exports.py ./scripts/tests/test_materialize_staging_execution_evidence.py ./scripts/tests/test_adapt_staging_platform_exports.py
        Invoke-Checked $Python -m pytest ./scripts/tests/test_materialize_staging_execution_evidence.py ./scripts/tests/test_adapt_staging_platform_exports.py
        Invoke-Checked pwsh ./scripts/staging-target-adapter-contract.ps1 -PythonCommand $Python
        Invoke-Checked pwsh ./scripts/staging-platform-export-contract.ps1 -PythonCommand $Python
    }
    if ($IncludeMonitoring) {
        Invoke-Checked $Python ./scripts/verify_monitoring_config.py --write-checksums
        Invoke-Checked pwsh ./scripts/alertmanager-drill.ps1
        Invoke-Checked $Python ./scripts/verify_alertmanager_evidence.py --report ./.local/alertmanager-wp4-iteration-9/alertmanager-report.json --write-checksums
        Invoke-Checked pwsh ./scripts/worker-backlog-drill.ps1
        Invoke-Checked $Python ./scripts/verify_worker_backlog_evidence.py --report ./.local/worker-backlog-wp4-iteration-8/worker-backlog-report.json --write-checksums
    }
    if ($IncludeCrossBrowserE2E) {
        Invoke-Checked $Pnpm e2e:cross-browser
    } elseif ($IncludeE2E) {
        Invoke-Checked $Pnpm e2e
    }
    Invoke-Checked dotnet build ./apps/desktop-windows/PasswordDetective.Desktop.csproj --configuration Release
    Invoke-Checked dotnet test ./apps/desktop-windows.tests/PasswordDetective.Desktop.Tests.csproj --configuration Release
} finally {
    Pop-Location
}

Write-Host "All checks passed."
