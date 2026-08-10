[CmdletBinding()]
param(
    [int]$ApiPort = 18150,
    [int]$MySqlPort = 13318,
    [int]$RedisPort = 16381,
    [int]$WorkerCount = 3,
    [int]$DurationSeconds = 60,
    [double]$ProbeIntervalSeconds = 0.2,
    [string]$OutputDirectory = ".local/multi-instance-stability-wp4-iteration-11",
    [string]$PythonCommand = "python",
    [switch]$SkipBuild,
    [switch]$KeepEnvironment
)

$ErrorActionPreference = "Stop"
if ($WorkerCount -lt 3) { throw "WorkerCount must be at least 3" }
if ($DurationSeconds -lt 45) { throw "DurationSeconds must be at least 45" }
$Root = Split-Path -Parent $PSScriptRoot
$ComposeRoot = $Root
$SubstDrive = $null
$OutputPath = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
$ProjectName = "password-detective-stability-$([guid]::NewGuid().ToString('N').Substring(0, 10))"
$ComposeArgs = @("-p", $ProjectName)
$ComposeStarted = $false
$LocationPushed = $false
$ProbeProcess = $null
$PreviousEnv = @{}
$ReportPath = Join-Path $OutputPath "multi-instance-stability-report.json"
$ProbeReportPath = Join-Path $OutputPath "mixed-load-probe.json"
$ProbeStdoutPath = Join-Path $OutputPath "mixed-load-probe.stdout.log"
$ProbeStderrPath = Join-Path $OutputPath "mixed-load-probe.stderr.log"

function Initialize-ComposeRoot {
    if (-not $IsWindows -or $Root -notmatch '[^\u0000-\u007F]') { return }
    $usedDrives = @(Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Name.ToUpperInvariant() })
    foreach ($codePoint in 90..80) {
        $driveName = ([char]$codePoint).ToString()
        if ($usedDrives -contains $driveName) { continue }
        $candidate = "${driveName}:"
        & subst.exe $candidate $Root
        if ($LASTEXITCODE -eq 0) {
            $script:SubstDrive = $candidate
            $script:ComposeRoot = "$candidate\"
            Write-Host "Mapped non-ASCII workspace to $candidate for Docker BuildKit."
            return
        }
    }
    throw "unable to map non-ASCII workspace for Docker BuildKit"
}

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

function Get-RuntimeMetrics {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/api/v1/metrics" -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw "metrics endpoint returned HTTP $($response.StatusCode)" }
    $instances = [regex]::Match($response.Content, '(?m)^password_detective_worker_instances_ready\s+([0-9]+(?:\.[0-9]+)?)\s*$')
    $worker = [regex]::Match($response.Content, '(?m)^password_detective_dependency_up\{dependency="worker"\}\s+([01])\s*$')
    $queue = [regex]::Match($response.Content, '(?m)^password_detective_worker_queue_depth\s+([0-9]+(?:\.[0-9]+)?)\s*$')
    if (-not ($instances.Success -and $worker.Success -and $queue.Success)) { throw "required worker metrics are missing" }
    [pscustomobject]@{
        Instances = [int][double]$instances.Groups[1].Value
        WorkerUp = [int]$worker.Groups[1].Value
        QueueDepth = [int][double]$queue.Groups[1].Value
    }
}

function Write-Report {
    param([hashtable]$Report)
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
    $Report | ConvertTo-Json -Depth 30 | Set-Content -Encoding utf8 $ReportPath
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
$Report = @{
    schema = "multi-instance-stability-drill-v1"
    status = "failed"
    started_at = [DateTime]::UtcNow.ToString("o")
    configuration = @{
        worker_count = $WorkerCount
        duration_seconds = $DurationSeconds
        probe_interval_seconds = $ProbeIntervalSeconds
    }
    checks = @{}
    timings = @{}
}
try {
    foreach ($port in @(@{ value = $ApiPort; name = "API" }, @{ value = $MySqlPort; name = "MySQL" }, @{ value = $RedisPort; name = "Redis" })) {
        Assert-HostPortAvailable -Port $port.value -Service $port.name
    }
    $envValues = @{
        APP_SECRET_KEY = "synthetic-multi-instance-stability-secret-20260810"
        API_PORT = "$ApiPort"
        MYSQL_PORT = "$MySqlPort"
        REDIS_PORT = "$RedisPort"
        PRIVACY_JOB_BACKEND = "celery"
        CELERY_WORKER_CONCURRENCY = "2"
        DATABASE_POOL_SIZE = "10"
        DATABASE_MAX_OVERFLOW = "20"
        DATABASE_POOL_TIMEOUT_SECONDS = "30"
        DATABASE_POOL_RECYCLE_SECONDS = "300"
    }
    foreach ($entry in $envValues.GetEnumerator()) {
        $PreviousEnv[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key)
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
    Initialize-ComposeRoot
    Push-Location $ComposeRoot
    $LocationPushed = $true
    if (-not $SkipBuild) { Invoke-ComposeChecked -Arguments @("down", "--volumes", "--remove-orphans") | Out-Null }
    $up = @("up", "--detach", "--wait", "--wait-timeout", "900", "--scale", "worker=$WorkerCount", "mysql", "redis", "api", "scheduler", "worker")
    if (-not $SkipBuild) { $up = @("up", "--build", "--detach", "--wait", "--wait-timeout", "900", "--scale", "worker=$WorkerCount", "mysql", "redis", "api", "scheduler", "worker") }
    $ComposeStarted = $true
    $startup = [DateTime]::UtcNow
    Invoke-ComposeChecked -Arguments $up | Out-Null
    $initial = Wait-Until -Description "$WorkerCount worker heartbeats" -TimeoutSeconds 90 -Probe { Get-RuntimeMetrics } -Condition { param($value) $value.Instances -ge $WorkerCount -and $value.WorkerUp -eq 1 }
    $Report.checks.initial_workers = @{ status = "passed"; requested = $WorkerCount; observed = $initial.Instances }
    $Report.timings.startup_seconds = [math]::Round(([DateTime]::UtcNow - $startup).TotalSeconds, 3)

    $databaseUrl = "mysql+pymysql://password_detective:password_detective_local@127.0.0.1:$MySqlPort/password_detective"
    $redisUrl = "redis://127.0.0.1:$RedisPort/0"
    $probeArguments = @(
        (Join-Path $Root "scripts/multi_instance_stability_probe.py"),
        "--api-url", "http://127.0.0.1:$ApiPort",
        "--database-url", $databaseUrl,
        "--redis-url", $redisUrl,
        "--duration-seconds", "$DurationSeconds",
        "--interval-seconds", "$ProbeIntervalSeconds",
        "--output", $ProbeReportPath
    )
    $processParameters = @{
        FilePath = $PythonCommand
        ArgumentList = $probeArguments
        PassThru = $true
        RedirectStandardOutput = $ProbeStdoutPath
        RedirectStandardError = $ProbeStderrPath
    }
    if ($IsWindows) { $processParameters.WindowStyle = "Hidden" }
    $ProbeProcess = Start-Process @processParameters

    Start-Sleep -Seconds ([math]::Max(8, [math]::Min(15, [int]($DurationSeconds / 3))))
    $workerIds = @((Invoke-ComposeBestEffort -Arguments @("ps", "-q", "worker")).Output | Where-Object { $_ -match '^[a-f0-9]{12,}$' })
    if ($workerIds.Count -lt $WorkerCount) { throw "compose returned only $($workerIds.Count) worker containers" }
    & docker stop $workerIds[0] | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "failed to stop one worker container" }
    $degraded = Wait-Until -Description "degraded worker count" -TimeoutSeconds 45 -Probe { Get-RuntimeMetrics } -Condition { param($value) $value.Instances -eq ($WorkerCount - 1) -and $value.WorkerUp -eq 1 }
    $Report.checks.single_worker_loss = @{
        status = "passed"
        expected = $WorkerCount - 1
        observed = $degraded.Instances
        worker_dependency_up = $degraded.WorkerUp
    }

    & docker rm $workerIds[0] | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "failed to remove the stopped worker container" }
    $replacementStart = [DateTime]::UtcNow
    Invoke-ComposeChecked -Arguments @("up", "--detach", "--no-deps", "--no-recreate", "--scale", "worker=$WorkerCount", "worker") | Out-Null
    $recovered = Wait-Until -Description "replacement worker heartbeat" -TimeoutSeconds 90 -Probe { Get-RuntimeMetrics } -Condition { param($value) $value.Instances -ge $WorkerCount -and $value.WorkerUp -eq 1 }
    $Report.checks.worker_replacement = @{ status = "passed"; requested = $WorkerCount; observed = $recovered.Instances }
    $Report.timings.worker_replacement_seconds = [math]::Round(([DateTime]::UtcNow - $replacementStart).TotalSeconds, 3)

    if (-not $ProbeProcess.WaitForExit(($DurationSeconds + 120) * 1000)) {
        Stop-Process -Id $ProbeProcess.Id -Force
        throw "mixed-load probe timed out"
    }
    if ($ProbeProcess.ExitCode -ne 0) { throw "mixed-load probe failed with exit code $($ProbeProcess.ExitCode)" }
    $ProbeProcess = $null
    $Probe = Get-Content -LiteralPath $ProbeReportPath -Raw | ConvertFrom-Json -AsHashtable
    if ($Probe.status -ne "passed" -or [int]$Probe.error_count -ne 0) { throw "mixed-load probe report did not pass" }
    $Report.probe = $Probe

    $drained = Wait-Until -Description "Celery queue to drain" -TimeoutSeconds 90 -Probe { Get-RuntimeMetrics } -Condition { param($value) $value.QueueDepth -eq 0 }
    $Report.checks.queue_drained = @{ status = "passed"; observed_depth = $drained.QueueDepth }
    $ready = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/api/v1/health/ready" -TimeoutSec 10
    if ($ready.StatusCode -ne 200) { throw "final readiness returned HTTP $($ready.StatusCode)" }
    $Report.checks.final_readiness = @{ status = "passed"; http_status = $ready.StatusCode }
    $Report.status = "passed"
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Host "Multi-instance stability drill passed. Evidence: $ReportPath"
} catch {
    $Report.error_code = "multi_instance_stability_drill_failed"
    $Report.error_message = $_.Exception.Message -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
    if ($ComposeStarted) {
        $Report.diagnostics = @{
            compose_ps = ((Invoke-ComposeBestEffort -Arguments @("ps", "-a")).Output -join "`n")
            api_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "--tail", "100", "api")).Output -join "`n")
            worker_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "--tail", "150", "worker")).Output -join "`n")
            scheduler_logs = ((Invoke-ComposeBestEffort -Arguments @("logs", "--no-color", "--tail", "100", "scheduler")).Output -join "`n")
        }
    }
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Error $_
    exit 1
} finally {
    if ($null -ne $ProbeProcess -and -not $ProbeProcess.HasExited) { Stop-Process -Id $ProbeProcess.Id -Force }
    if ($ComposeStarted -and -not $KeepEnvironment) { Invoke-ComposeBestEffort -Arguments @("down", "--volumes", "--remove-orphans") | Out-Null }
    foreach ($entry in $PreviousEnv.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value) }
    if ($LocationPushed) { Pop-Location }
    if ($null -ne $SubstDrive) { & subst.exe $SubstDrive /D | Out-Null }
    if ($KeepEnvironment) { Write-Host "Multi-instance stability environment kept: $ProjectName" }
}
