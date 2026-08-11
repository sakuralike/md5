[CmdletBinding()]
param(
    [string]$PrometheusUrl = "http://127.0.0.1:9090",
    [string]$GrafanaUrl = "http://127.0.0.1:3000",
    [string]$AlertmanagerUrl = "http://127.0.0.1:9093",
    [string]$AlertReceiverUrl = "http://127.0.0.1:18081",
    [string]$Environment = "staging",
    [int]$ExpectedApiTargetCount = 1,
    [int]$TimeoutSec = 20
)

$ErrorActionPreference = "Stop"

function Normalize-BaseUrl {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value.TrimEnd('/')
}

function Assert-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Uri
    )
    $Response = Invoke-WebRequest -UseBasicParsing -Method Get -Uri $Uri -TimeoutSec $TimeoutSec
    if ($Response.StatusCode -ne 200) {
        throw "$Name returned HTTP $($Response.StatusCode); expected HTTP 200"
    }
}

$Prometheus = Normalize-BaseUrl $PrometheusUrl
$Grafana = Normalize-BaseUrl $GrafanaUrl
$Alertmanager = Normalize-BaseUrl $AlertmanagerUrl
$Receiver = Normalize-BaseUrl $AlertReceiverUrl
$Results = [ordered]@{}

Assert-HttpOk -Name "Prometheus readiness" -Uri "$Prometheus/-/ready"
$Results.prometheus_ready = "passed"

$Targets = Invoke-RestMethod -Method Get -Uri "$Prometheus/api/v1/targets?state=active" -TimeoutSec $TimeoutSec
if ($Targets.status -ne "success") {
    throw "Prometheus targets API did not return success"
}
$ApiTargets = @($Targets.data.activeTargets | Where-Object {
    $_.labels.job -eq "password-detective-api" -and $_.labels.environment -eq $Environment
})
if ($ExpectedApiTargetCount -lt 1) {
    throw "ExpectedApiTargetCount must be at least 1"
}
if ($ApiTargets.Count -ne $ExpectedApiTargetCount) {
    throw "expected $ExpectedApiTargetCount password-detective-api targets for environment '$Environment'; found $($ApiTargets.Count)"
}
$UnhealthyTargets = @($ApiTargets | Where-Object { $_.health -ne "up" })
if ($UnhealthyTargets.Count -gt 0) {
    throw "$($UnhealthyTargets.Count) password-detective-api target(s) are not up"
}
$Results.prometheus_target = "passed"

$Query = [Uri]::EscapeDataString("up{job=`"password-detective-api`",environment=`"$Environment`"}")
$Up = Invoke-RestMethod -Method Get -Uri "$Prometheus/api/v1/query?query=$Query" -TimeoutSec $TimeoutSec
$UpSeries = @($Up.data.result)
$UnhealthySeries = @($UpSeries | Where-Object { [double]$_.value[1] -ne 1 })
if ($Up.status -ne "success" -or $UpSeries.Count -ne $ExpectedApiTargetCount -or $UnhealthySeries.Count -gt 0) {
    throw "Prometheus up query did not return $ExpectedApiTargetCount healthy staging API series"
}
$Results.prometheus_query = "passed"

$GrafanaHealth = Invoke-RestMethod -Method Get -Uri "$Grafana/api/health" -TimeoutSec $TimeoutSec
if ($GrafanaHealth.database -ne "ok" -or [string]::IsNullOrWhiteSpace($GrafanaHealth.version)) {
    throw "Grafana health payload is not ready"
}
$Results.grafana_health = "passed"

Assert-HttpOk -Name "Alertmanager readiness" -Uri "$Alertmanager/-/ready"
$Results.alertmanager_ready = "passed"

$ReceiverHealth = Invoke-RestMethod -Method Get -Uri "$Receiver/health" -TimeoutSec $TimeoutSec
if ($ReceiverHealth.status -ne "ok") {
    throw "alert receiver health payload is not ready"
}
$Results.alert_receiver = "passed"

Write-Host ("Staging monitoring smoke passed: {0}" -f (($Results.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "))
