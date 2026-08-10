param(
    [string]$Profile = "infra/staging/readiness-profile.example.json",
    [Parameter(Mandatory = $true)][string]$ResourceExport,
    [Parameter(Mandatory = $true)][string]$MysqlExport,
    [Parameter(Mandatory = $true)][string]$RedisExport,
    [string]$OutputDirectory = ".local/staging-platform-export-execution",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }

function Resolve-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $Root $Path))
}

$ProfilePath = Resolve-ProjectPath $Profile
$ResourceExportPath = Resolve-ProjectPath $ResourceExport
$MysqlExportPath = Resolve-ProjectPath $MysqlExport
$RedisExportPath = Resolve-ProjectPath $RedisExport
$OutputPath = Resolve-ProjectPath $OutputDirectory
$SourcePath = Join-Path $OutputPath "sources"

foreach ($Path in @($ProfilePath, $ResourceExportPath, $MysqlExportPath, $RedisExportPath)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "required staging platform export was not found: $Path"
    }
}

New-Item -ItemType Directory -Force -Path $SourcePath | Out-Null
& $Python (Join-Path $Root "scripts/adapt_staging_platform_exports.py") `
    --profile $ProfilePath `
    --resource-export $ResourceExportPath `
    --mysql-export $MysqlExportPath `
    --redis-export $RedisExportPath `
    --output-directory $SourcePath
if ($LASTEXITCODE -ne 0) { throw "staging platform export adaptation failed" }

& pwsh (Join-Path $Root "scripts/staging-target-execution.ps1") `
    -Profile $ProfilePath `
    -ResourceSource (Join-Path $SourcePath "resource-source.json") `
    -MysqlSource (Join-Path $SourcePath "mysql-ha-source.json") `
    -RedisSource (Join-Path $SourcePath "redis-ha-source.json") `
    -OutputDirectory $OutputPath `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging platform export evidence execution failed" }

$Summary = Get-Content -LiteralPath (Join-Path $OutputPath "staging-execution-evidence-summary.json") -Raw | ConvertFrom-Json
Write-Host "Staging platform export execution completed: evidence_kind=$($Summary.evidence_kind), execution_status=$($Summary.execution_status), output=$OutputPath"
