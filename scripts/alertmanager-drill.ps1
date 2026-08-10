[CmdletBinding()]
param(
    [int]$AlertmanagerPort = 19093,
    [int]$ReceiverPort = 18091,
    [int]$TimeoutSeconds = 90,
    [string]$OutputDirectory = ".local/alertmanager-wp4-iteration-9",
    [switch]$KeepEnvironment
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "docker-compose.yml"
$MonitoringComposeFile = Join-Path $Root "infra/monitoring/docker-compose.monitoring.yml"
$OutputPath = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
$ReportPath = Join-Path $OutputPath "alertmanager-report.json"
$ProjectName = "password-detective-alertmanager-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
$ComposeArgs = @("-p", $ProjectName, "-f", $ComposeFile, "-f", $MonitoringComposeFile, "--profile", "monitoring")
$ComposeStarted = $false
$LocationPushed = $false
$PreviousEnv = @{}
$SensitiveMarker = "synthetic-alert-secret-do-not-persist"

function Invoke-ComposeChecked {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose @ComposeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($Arguments -join ' ')" }
}

function Invoke-ComposeBestEffort {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & docker compose @ComposeArgs @Arguments 2>&1
    [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Assert-HostPortAvailable {
    param([int]$Port, [string]$Service)
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners.Port -contains $Port) { throw "$Service host port $Port is already in use" }
}

function Wait-Until {
    param([scriptblock]$Probe, [scriptblock]$Condition, [int]$TimeoutSeconds, [string]$Description)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try { $value = & $Probe } catch { $value = $null }
        if (& $Condition $value) { return $value }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "timeout waiting for $Description"
}

function Get-ReceiverEvents {
    Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$ReceiverPort/events" -TimeoutSec 5
}

function Send-Alert {
    param([datetime]$StartsAt, [datetime]$EndsAt)
    $alert = @{
        labels = @{
            alertname = "PasswordDetectiveSyntheticNotificationDrill"
            severity = "warning"
            service = "worker"
            environment = "integration"
        }
        annotations = @{
            summary = "Synthetic Alertmanager notification drill"
            description = "Synthetic alert used only to verify firing, deduplication and recovery delivery."
            runbook = "docs/runbooks/wp4-alertmanager.md"
            secret_value = $SensitiveMarker
        }
        startsAt = $StartsAt.ToUniversalTime().ToString("o")
        endsAt = $EndsAt.ToUniversalTime().ToString("o")
        generatorURL = "http://prometheus:9090/graph"
    }
    $body = ConvertTo-Json -InputObject @($alert) -Depth 10 -Compress
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$AlertmanagerPort/api/v2/alerts" -ContentType "application/json" -Body $body -TimeoutSec 10 | Out-Null
}

function Write-Report {
    param([hashtable]$Report)
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
    $Report | ConvertTo-Json -Depth 30 | Set-Content -Encoding utf8 $ReportPath
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
$Report = @{
    schema = "alertmanager-drill-v1"
    status = "failed"
    started_at = [DateTime]::UtcNow.ToString("o")
    checks = @{}
    timings = @{}
}
try {
    Assert-HostPortAvailable -Port $AlertmanagerPort -Service "Alertmanager"
    Assert-HostPortAvailable -Port $ReceiverPort -Service "Alert receiver"
    $envValues = @{
        APP_SECRET_KEY = "synthetic-alertmanager-drill-secret-20260810"
        ALERTMANAGER_PORT = "$AlertmanagerPort"
        ALERT_RECEIVER_PORT = "$ReceiverPort"
    }
    foreach ($entry in $envValues.GetEnumerator()) {
        $PreviousEnv[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key)
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
    Push-Location $Root
    $LocationPushed = $true
    $ComposeStarted = $true
    Invoke-ComposeChecked -Arguments @("up", "--detach", "--wait", "--wait-timeout", "180", "alert-receiver", "alertmanager") | Out-Null
    $readyStart = [DateTime]::UtcNow
    $alertmanagerReady = Wait-Until -Description "Alertmanager readiness" -TimeoutSeconds 30 -Probe { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$AlertmanagerPort/-/ready" -TimeoutSec 5).StatusCode } -Condition { param($value) $value -eq 200 }
    $receiverReady = Wait-Until -Description "notification gateway readiness" -TimeoutSeconds 30 -Probe { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ReceiverPort/health" -TimeoutSec 5).StatusCode } -Condition { param($value) $value -eq 200 }
    $Report.checks.readiness = @{ status = "passed"; alertmanager_http = $alertmanagerReady; receiver_http = $receiverReady }
    $Report.timings.readiness_seconds = [math]::Round(([DateTime]::UtcNow - $readyStart).TotalSeconds, 3)

    $startsAt = [DateTime]::UtcNow
    $firingStart = [DateTime]::UtcNow
    Send-Alert -StartsAt $startsAt -EndsAt $startsAt.AddMinutes(10)
    Start-Sleep -Milliseconds 500
    Send-Alert -StartsAt $startsAt -EndsAt $startsAt.AddMinutes(10)
    $firingEvents = Wait-Until -Description "one firing notification" -TimeoutSeconds $TimeoutSeconds -Probe { Get-ReceiverEvents } -Condition { param($value) $null -ne $value -and @($value.events | Where-Object { $_.status -eq "firing" }).Count -ge 1 }
    Start-Sleep -Seconds 7
    $afterDuplicateWindow = Get-ReceiverEvents
    $firingCount = @($afterDuplicateWindow.events | Where-Object { $_.status -eq "firing" }).Count
    if ($firingCount -ne 1) { throw "expected one grouped firing notification, observed $firingCount" }
    $Report.checks.firing = @{ status = "passed"; submitted = 2; delivered = $firingCount; duplicate_suppressed = $true }
    $Report.timings.firing_seconds = [math]::Round(([DateTime]::UtcNow - $firingStart).TotalSeconds, 3)

    $recoveryStart = [DateTime]::UtcNow
    Send-Alert -StartsAt $startsAt -EndsAt ([DateTime]::UtcNow.AddSeconds(-1))
    $resolvedEvents = Wait-Until -Description "resolved notification" -TimeoutSeconds $TimeoutSeconds -Probe { Get-ReceiverEvents } -Condition { param($value) $null -ne $value -and @($value.events | Where-Object { $_.status -eq "resolved" }).Count -ge 1 }
    $resolvedCount = @($resolvedEvents.events | Where-Object { $_.status -eq "resolved" }).Count
    if ($resolvedCount -ne 1) { throw "expected one resolved notification, observed $resolvedCount" }
    $Report.checks.recovery = @{ status = "passed"; delivered = $resolvedCount; send_resolved = $true }
    $Report.timings.recovery_seconds = [math]::Round(([DateTime]::UtcNow - $recoveryStart).TotalSeconds, 3)

    $eventsJson = ConvertTo-Json -InputObject $resolvedEvents -Depth 30 -Compress
    if ($eventsJson -match [regex]::Escape($SensitiveMarker)) { throw "sensitive marker persisted in notification evidence" }
    if ($eventsJson -notmatch [regex]::Escape("[REDACTED]")) { throw "notification gateway did not record a redaction marker" }
    $deliveryIds = @($resolvedEvents.events | ForEach-Object { $_.delivery_id })
    if ($deliveryIds.Count -ne (@($deliveryIds | Select-Object -Unique)).Count) { throw "delivery identifiers are not unique" }
    $Report.checks.redaction = @{ status = "passed"; raw_marker_absent = $true; redaction_marker_present = $true }
    $Report.checks.delivery_ids = @{ status = "passed"; total = $deliveryIds.Count; unique = (@($deliveryIds | Select-Object -Unique)).Count }
    $Report.notification_events = $resolvedEvents.events
    $Report.status = "passed"
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Host "Alertmanager drill passed. Evidence: $ReportPath"
} catch {
    $Report.error_code = "alertmanager_drill_failed"
    $Report.error_message = $_.Exception.Message -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
    if ($ComposeStarted) {
        $Report.diagnostics = @{
            compose_ps = ((Invoke-ComposeBestEffort -Arguments @("ps", "-a")).Output -join "`n")
            alertmanager_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "alertmanager")).Output -join "`n") -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
            receiver_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "alert-receiver")).Output -join "`n") -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
        }
    }
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Error $_
    exit 1
} finally {
    if ($ComposeStarted -and -not $KeepEnvironment) { Invoke-ComposeBestEffort -Arguments @("down", "--volumes", "--remove-orphans") | Out-Null }
    foreach ($entry in $PreviousEnv.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value) }
    if ($LocationPushed) { Pop-Location }
    if ($KeepEnvironment) { Write-Host "Alertmanager drill environment kept: $ProjectName" }
}
