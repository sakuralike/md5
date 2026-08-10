param(
    [string]$OutputDirectory = ".local/staging-target-adapter-contract-wp4-iteration-14",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { [IO.Path]::GetFullPath($OutputDirectory) } else { [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory)) }
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }
$Profile = Join-Path $Root "infra/staging/readiness-profile.example.json"
$Sources = Join-Path $Output "sources"

New-Item -ItemType Directory -Force -Path $Sources | Out-Null
& $Python (Join-Path $Root "scripts/materialize_staging_execution_evidence.py") `
    --profile $Profile `
    --emit-contract-sources $Sources
if ($LASTEXITCODE -ne 0) { throw "staging adapter contract source generation failed" }

& pwsh (Join-Path $Root "scripts/staging-target-execution.ps1") `
    -Profile $Profile `
    -ResourceSource (Join-Path $Sources "resource-source.json") `
    -MysqlSource (Join-Path $Sources "mysql-ha-source.json") `
    -RedisSource (Join-Path $Sources "redis-ha-source.json") `
    -OutputDirectory $Output `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging target adapter contract failed" }

$Summary = Get-Content -LiteralPath (Join-Path $Output "staging-execution-evidence-summary.json") -Raw | ConvertFrom-Json
if ($Summary.evidence_kind -ne "contract-fixture" -or $Summary.execution_status -ne "not-run") {
    throw "contract fixture must remain not-run and cannot be promoted to target execution evidence"
}
Write-Host "Staging target adapter contract is valid and remains not-run. Output: $Output"
