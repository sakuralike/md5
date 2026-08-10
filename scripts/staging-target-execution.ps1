param(
    [Parameter(Mandatory = $true)][string]$ResourceSource,
    [Parameter(Mandatory = $true)][string]$MysqlSource,
    [Parameter(Mandatory = $true)][string]$RedisSource,
    [string]$Profile = "infra/staging/readiness-profile.example.json",
    [string]$OutputDirectory = ".local/staging-target-execution-wp4-iteration-14",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }

function Resolve-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
    return [IO.Path]::GetFullPath((Join-Path $Root $Value))
}

$ProfilePath = Resolve-ProjectPath $Profile
$ResourceSourcePath = Resolve-ProjectPath $ResourceSource
$MysqlSourcePath = Resolve-ProjectPath $MysqlSource
$RedisSourcePath = Resolve-ProjectPath $RedisSource
$OutputPath = Resolve-ProjectPath $OutputDirectory
$OutputProfile = Join-Path $OutputPath "readiness-profile.json"

foreach ($Path in @($ProfilePath, $ResourceSourcePath, $MysqlSourcePath, $RedisSourcePath)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "required staging source file was not found: $Path"
    }
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
Copy-Item -LiteralPath $ProfilePath -Destination $OutputProfile -Force
$RelativeProfile = [IO.Path]::GetRelativePath($Root, $OutputProfile)
$RelativeOutput = [IO.Path]::GetRelativePath($Root, $OutputPath)

& pwsh (Join-Path $Root "scripts/staging-readiness-plan.ps1") `
    -Profile $RelativeProfile `
    -OutputDirectory $RelativeOutput `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging readiness plan generation failed" }

& $Python (Join-Path $Root "scripts/materialize_staging_execution_evidence.py") `
    --profile $OutputProfile `
    --resource-source $ResourceSourcePath `
    --mysql-source $MysqlSourcePath `
    --redis-source $RedisSourcePath `
    --output-directory $OutputPath
if ($LASTEXITCODE -ne 0) { throw "staging source adapter materialization failed" }

& $Python (Join-Path $Root "scripts/verify_staging_execution_evidence.py") `
    --profile $OutputProfile `
    --plan (Join-Path $OutputPath "staging-readiness-plan.json") `
    --resource-report (Join-Path $OutputPath "resource-trend-report.json") `
    --mysql-report (Join-Path $OutputPath "mysql-ha-failover-report.json") `
    --redis-report (Join-Path $OutputPath "redis-ha-failover-report.json") `
    --output (Join-Path $OutputPath "staging-execution-evidence-summary.json") `
    --write-checksums
if ($LASTEXITCODE -ne 0) { throw "staging execution evidence verification failed" }

$Summary = Get-Content -LiteralPath (Join-Path $OutputPath "staging-execution-evidence-summary.json") -Raw | ConvertFrom-Json
Write-Host "Staging target adapter completed: evidence_kind=$($Summary.evidence_kind), execution_status=$($Summary.execution_status), output=$OutputPath"
