param(
    [string]$OutputDirectory = ".local/staging-evidence-contract-wp4-iteration-13",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $Root $OutputDirectory }
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }
$Profile = Join-Path $Root "infra/staging/readiness-profile.example.json"
$Resource = Join-Path $Root "infra/staging/resource-trend-report.example.json"
$Mysql = Join-Path $Root "infra/staging/mysql-ha-failover-report.example.json"
$Redis = Join-Path $Root "infra/staging/redis-ha-failover-report.example.json"

New-Item -ItemType Directory -Force -Path $Output | Out-Null
Copy-Item -LiteralPath $Profile -Destination (Join-Path $Output "readiness-profile.json") -Force
Copy-Item -LiteralPath $Resource -Destination (Join-Path $Output "resource-trend-report.json") -Force
Copy-Item -LiteralPath $Mysql -Destination (Join-Path $Output "mysql-ha-failover-report.json") -Force
Copy-Item -LiteralPath $Redis -Destination (Join-Path $Output "redis-ha-failover-report.json") -Force

$RelativeProfile = [IO.Path]::GetRelativePath($Root, (Join-Path $Output "readiness-profile.json"))
$RelativeOutput = [IO.Path]::GetRelativePath($Root, $Output)
& pwsh (Join-Path $Root "scripts/staging-readiness-plan.ps1") `
    -Profile $RelativeProfile `
    -OutputDirectory $RelativeOutput `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging readiness plan generation failed" }

& $Python (Join-Path $Root "scripts/verify_staging_execution_evidence.py") `
    --profile (Join-Path $Output "readiness-profile.json") `
    --plan (Join-Path $Output "staging-readiness-plan.json") `
    --resource-report (Join-Path $Output "resource-trend-report.json") `
    --mysql-report (Join-Path $Output "mysql-ha-failover-report.json") `
    --redis-report (Join-Path $Output "redis-ha-failover-report.json") `
    --output (Join-Path $Output "staging-execution-evidence-summary.json") `
    --write-checksums
if ($LASTEXITCODE -ne 0) { throw "staging execution evidence verification failed" }

Write-Host "Staging execution evidence contract is valid. Output: $Output"
