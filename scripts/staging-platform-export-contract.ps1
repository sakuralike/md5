param(
    [string]$OutputDirectory = ".local/staging-platform-export-contract-wp4-iteration-15",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { [IO.Path]::GetFullPath($OutputDirectory) } else { [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory)) }
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }
$Profile = Join-Path $Root "infra/staging/readiness-profile.example.json"
$Exports = Join-Path $Output "platform-exports"

New-Item -ItemType Directory -Force -Path $Exports | Out-Null
& $Python (Join-Path $Root "scripts/adapt_staging_platform_exports.py") `
    --profile $Profile `
    --emit-contract-exports $Exports
if ($LASTEXITCODE -ne 0) { throw "staging platform export contract generation failed" }

& pwsh (Join-Path $Root "scripts/staging-platform-export-execution.ps1") `
    -Profile $Profile `
    -ResourceExport (Join-Path $Exports "prometheus-resource-export.json") `
    -MysqlExport (Join-Path $Exports "mysql-ha-platform-export.json") `
    -RedisExport (Join-Path $Exports "redis-ha-platform-export.json") `
    -OutputDirectory $Output `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging platform export contract failed" }

$Summary = Get-Content -LiteralPath (Join-Path $Output "staging-execution-evidence-summary.json") -Raw | ConvertFrom-Json
if ($Summary.evidence_kind -ne "contract-fixture" -or $Summary.execution_status -ne "not-run") {
    throw "platform export contract must remain not-run and cannot be promoted to target execution evidence"
}
Write-Host "Staging platform export contract is valid and remains not-run. Output: $Output"
