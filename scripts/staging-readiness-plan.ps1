param(
    [string]$Profile = "infra/staging/readiness-profile.example.json",
    [string]$OutputDirectory = ".local/staging-readiness-wp4-iteration-12",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $PythonCommand) {
    $VenvPython = Join-Path $Root "apps/api/.venv/Scripts/python.exe"
    $PythonCommand = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
}
$ProfilePath = [IO.Path]::GetFullPath((Join-Path $Root $Profile))
$OutputPath = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
$PlanPath = Join-Path $OutputPath "staging-readiness-plan.json"

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
& $PythonCommand (Join-Path $Root "scripts/verify_staging_readiness_profile.py") `
    --profile $ProfilePath `
    --repository-root $Root `
    --output $PlanPath `
    --write-checksums
if ($LASTEXITCODE -ne 0) { throw "staging readiness contract validation failed" }
Write-Host "Staging readiness contract is valid. Plan: $PlanPath"
