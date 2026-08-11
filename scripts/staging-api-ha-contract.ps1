[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [string]$Report = ".local/staging-api-ha-wp4-iteration-23/contract-report.json"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    & $PythonCommand ./scripts/verify_staging_api_ha.py --report $Report --write-checksums
    if ($LASTEXITCODE -ne 0) { throw "Staging API HA contract failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Staging API HA contract passed: $(Join-Path $Root $Report)"
