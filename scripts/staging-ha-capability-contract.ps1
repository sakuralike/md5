param(
    [string]$PythonCommand = "python",
    [string]$OutputPath = ".local/staging-ha-capability-contract-wp4-iteration-26"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Output = if ([System.IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $Root $OutputPath }
$Profile = Join-Path $Root "infra/staging/readiness-profile.example.json"
New-Item -ItemType Directory -Force -Path $Output | Out-Null

$Reports = @()
foreach ($Dependency in @("mysql", "redis")) {
    $Input = Join-Path $Root "infra/staging/$Dependency-ha-target-capability.example.json"
    $Report = Join-Path $Output "$Dependency-capability-verification.json"
    & $PythonCommand (Join-Path $PSScriptRoot "verify_staging_ha_target_capability.py") `
        --input $Input `
        --profile $Profile `
        --dependency $Dependency | Set-Content -LiteralPath $Report -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "HA capability contract failed for $Dependency with exit code $LASTEXITCODE"
    }
    $Reports += $Report
}

$ChecksumLines = foreach ($Report in $Reports) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Report).Hash.ToLowerInvariant()
    "$Hash  $([System.IO.Path]::GetFileName($Report))"
}
$ChecksumLines | Set-Content -LiteralPath (Join-Path $Output "SHA256SUMS") -Encoding utf8
Write-Host "Staging HA capability contract passed: $Output"
