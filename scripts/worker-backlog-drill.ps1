[CmdletBinding()]
param(
    [int]$ApiPort = 18140,
    [int]$MySqlPort = 13317,
    [int]$RedisPort = 16380,
    [int]$QueueSize = 24,
    [int]$DrainTimeoutSeconds = 120,
    [string]$OutputDirectory = ".local/worker-backlog-wp4-iteration-8",
    [switch]$SkipBuild,
    [switch]$KeepEnvironment
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "docker-compose.yml"
$OutputPath = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
$ProjectName = "password-detective-backlog-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
$ComposeArgs = @("-p", $ProjectName, "-f", $ComposeFile)
$ComposeStarted = $false
$LocationPushed = $false
$PreviousEnv = @{}
$ReportPath = Join-Path $OutputPath "worker-backlog-report.json"

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
        $value = & $Probe
        if (& $Condition $value) { return $value }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "timeout waiting for $Description"
}

function Get-QueueDepth {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/api/v1/metrics"
    if ($response.StatusCode -ne 200) { throw "metrics endpoint returned HTTP $($response.StatusCode)" }
    $match = [regex]::Match($response.Content, '(?m)^password_detective_worker_queue_depth\s+([0-9]+(?:\.[0-9]+)?)\s*$')
    if (-not $match.Success) { throw "worker queue depth metric is missing" }
    return [int][double]$match.Groups[1].Value
}

function Write-Report {
    param([hashtable]$Report)
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
    $Report | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $ReportPath
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
$Report = @{
    schema = "worker-backlog-drill-v1"
    status = "failed"
    queue_size = $QueueSize
    started_at = [DateTime]::UtcNow.ToString("o")
    checks = @{}
    timings = @{}
}
try {
    foreach ($port in @(@{ value = $ApiPort; name = "API" }, @{ value = $MySqlPort; name = "MySQL" }, @{ value = $RedisPort; name = "Redis" })) {
        Assert-HostPortAvailable -Port $port.value -Service $port.name
    }
    $envValues = @{
        APP_SECRET_KEY = "synthetic-worker-backlog-secret-20260810"
        API_PORT = "$ApiPort"
        MYSQL_PORT = "$MySqlPort"
        REDIS_PORT = "$RedisPort"
        PRIVACY_JOB_BACKEND = "celery"
    }
    foreach ($entry in $envValues.GetEnumerator()) {
        $PreviousEnv[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key)
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
    Push-Location $Root
    $LocationPushed = $true
    if (-not $SkipBuild) { Invoke-ComposeChecked -Arguments @("down", "--volumes", "--remove-orphans") | Out-Null }
    $up = @("up", "--detach", "--wait", "--wait-timeout", "900", "mysql", "redis", "api")
    if (-not $SkipBuild) { $up = @("up", "--build", "--detach", "--wait", "--wait-timeout", "900", "mysql", "redis", "api") }
    $ComposeStarted = $true
    Invoke-ComposeChecked -Arguments $up | Out-Null

    $enqueueStart = [DateTime]::UtcNow
    $enqueueCode = "from password_detective.worker import celery_app; [celery_app.send_task('observability.noop', args=[f'wp4-backlog-{i}']) for i in range($QueueSize)]"
    Invoke-ComposeChecked -Arguments @("exec", "-T", "api", "python", "-c", $enqueueCode) | Out-Null
    $queuedDepth = Wait-Until -Description "queue backlog to become visible" -TimeoutSeconds 30 -Probe { Get-QueueDepth } -Condition { param($value) $value -ge $QueueSize }
    $Report.checks.enqueue = @{ status = "passed"; requested = $QueueSize; observed_depth = $queuedDepth }
    $Report.timings.enqueue_seconds = [math]::Round(([DateTime]::UtcNow - $enqueueStart).TotalSeconds, 3)

    $workerStart = [DateTime]::UtcNow
    Invoke-ComposeChecked -Arguments @("up", "--detach", "--wait", "--wait-timeout", "180", "worker") | Out-Null
    $workerReady = Wait-Until -Description "worker readiness log" -TimeoutSeconds 30 -Probe { Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "worker") } -Condition { param($value) $value.ExitCode -eq 0 -and ($value.Output -join "`n") -match "(?i)ready\." }
    $drainedDepth = Wait-Until -Description "worker queue to drain" -TimeoutSeconds $DrainTimeoutSeconds -Probe { Get-QueueDepth } -Condition { param($value) $value -eq 0 }
    $Report.checks.drain = @{ status = "passed"; observed_depth = $drainedDepth; worker_ready = "ready" }
    $Report.timings.drain_seconds = [math]::Round(([DateTime]::UtcNow - $workerStart).TotalSeconds, 3)
    $Report.status = "passed"
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Host "Worker backlog drill passed. Evidence: $ReportPath"
} catch {
    $Report.error_code = "worker_backlog_drill_failed"
    $Report.error_message = $_.Exception.Message -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
    if ($ComposeStarted) {
        $Report.diagnostics = @{
            compose_ps = ((Invoke-ComposeBestEffort -Arguments @("ps", "-a")).Output -join "`n")
            api_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "api")).Output -join "`n") -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
            worker_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "worker")).Output -join "`n") -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
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
    if ($KeepEnvironment) { Write-Host "Worker backlog environment kept: $ProjectName" }
}
