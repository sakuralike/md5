[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [string]$ApiProxyUrl = "http://127.0.0.1:8000",
    [string]$PrometheusUrl = "http://127.0.0.1:9090",
    [string]$GrafanaUrl = "http://127.0.0.1:3000",
    [string]$AlertmanagerUrl = "http://127.0.0.1:9093",
    [string]$AlertReceiverUrl = "http://127.0.0.1:18081",
    [int]$ExpectedApiReplicas = 2,
    [string]$ComposeFiles = "docker-compose.yml,infra/staging/docker-compose.staging.api-ha.yml",
    [string]$ProjectDirectory = "",
    [int]$TimeoutSec = 20
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ResolvedComposeFiles = @(
    $ComposeFiles.Split(',') |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
if ($ResolvedComposeFiles.Count -eq 0) {
    throw "At least one Compose file must be provided"
}
$Proxy = $ApiProxyUrl.TrimEnd('/')
$Ready = Invoke-RestMethod -Method Get -Uri "$Proxy/api/v1/health/ready" -TimeoutSec $TimeoutSec
if ($Ready.status -ne "ready" -or $Ready.database -ne "ok" -or $Ready.rate_limit -ne "ok") {
    throw "API proxy readiness payload is not ready"
}
$Results = [ordered]@{ api_proxy_ready = "passed" }

$PreflightParameters = @{
    PythonCommand = $PythonCommand
    ComposeFiles = $ResolvedComposeFiles
    Output = ".local/staging-api-ha-wp4-iteration-23/topology-preflight.json"
}
if (-not [string]::IsNullOrWhiteSpace($ProjectDirectory)) {
    $PreflightParameters.ProjectDirectory = $ProjectDirectory
}
& (Join-Path $PSScriptRoot "staging-topology-preflight.ps1") @PreflightParameters
if ($LASTEXITCODE -ne 0) { throw "Staging topology preflight failed" }
$Results.topology_preflight = "passed"

& (Join-Path $PSScriptRoot "staging-monitoring-smoke.ps1") `
    -PrometheusUrl $PrometheusUrl `
    -GrafanaUrl $GrafanaUrl `
    -AlertmanagerUrl $AlertmanagerUrl `
    -AlertReceiverUrl $AlertReceiverUrl `
    -ExpectedApiTargetCount $ExpectedApiReplicas `
    -TimeoutSec $TimeoutSec
if ($LASTEXITCODE -ne 0) { throw "Staging monitoring smoke failed" }
$Results.monitoring_targets = "passed"

Write-Host ("Staging API HA smoke passed: {0}" -f (($Results.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "))
