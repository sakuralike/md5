[CmdletBinding()]
param(
    [string]$OutputDirectory = ".local/recovery-wp4-iteration-6",
    [string]$ProjectName = "password-detective-recovery",
    [int]$ApiPort = 18120,
    [int]$MySqlPort = 13316,
    [int]$RedisPort = 16379,
    [switch]$KeepEnvironment,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputPath = Join-Path $Root $OutputDirectory
$ReportPath = Join-Path $OutputPath "recovery-report.json"
$LogPath = Join-Path $OutputPath "recovery-drill.log"
$ComposeArgs = @("compose", "--project-name", $ProjectName)
$ApiBase = "http://127.0.0.1:$ApiPort/api/v1"
$RunId = [DateTime]::UtcNow.ToString("yyyyMMddHHmmss")
$SyntheticUsername = "recovery_$RunId"
$SyntheticEmail = "recovery_$RunId@example.com"
$SyntheticPassword = "RecoveryPass_$RunId`1"
$EnvironmentKeys = @("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "APP_SECRET_KEY", "APP_ENV", "NOTIFICATION_BACKEND", "PRIVACY_JOB_BACKEND", "RATE_LIMIT_BACKEND", "MYSQL_PORT", "REDIS_PORT", "API_PORT", "WEB_PORT", "ADMIN_PORT")
$PreviousEnvironment = @{}
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$ComposeRoot = $Root
$SubstDrive = $null
$LocationPushed = $false

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
Start-Transcript -Path $LogPath -Force | Out-Null

function Initialize-ComposeRoot {
    if ($Root -notmatch '[^\u0000-\u007F]') { return }
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

function Set-RecoveryEnvironment {
    foreach ($key in $EnvironmentKeys) { $PreviousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process") }
    $env:MYSQL_PASSWORD = "synthetic_recovery_mysql"
    $env:MYSQL_ROOT_PASSWORD = "synthetic_recovery_root"
    $env:APP_SECRET_KEY = "synthetic-recovery-app-secret-key-32-plus"
    $env:APP_ENV = "integration"
    $env:NOTIFICATION_BACKEND = "log"
    $env:PRIVACY_JOB_BACKEND = "celery"
    $env:RATE_LIMIT_BACKEND = "redis"
    $env:MYSQL_PORT = "$MySqlPort"
    $env:REDIS_PORT = "$RedisPort"
    $env:API_PORT = "$ApiPort"
    $env:WEB_PORT = "0"
    $env:ADMIN_PORT = "0"
}

function Restore-Environment {
    foreach ($key in $EnvironmentKeys) {
        $value = $PreviousEnvironment[$key]
        if ($null -eq $value) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue } else { Set-Item "Env:$key" $value }
    }
}

function Invoke-ComposeChecked {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = & docker @ComposeArgs @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE`n$($output -join "`n")" }
    return @($output)
}

function Invoke-ComposeBestEffort {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = & docker @ComposeArgs @Arguments 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Convert-ResponseJson {
    param([string]$Content)
    if ([string]::IsNullOrWhiteSpace($Content)) { return $null }
    try { return $Content | ConvertFrom-Json -Depth 20 } catch { return $null }
}

function Invoke-ApiRequest {
    param(
        [Parameter(Mandatory)][ValidateSet("GET", "POST")][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [hashtable]$Headers = @{},
        [object]$Body
    )
    $requestHeaders = @{}
    foreach ($key in $Headers.Keys) { $requestHeaders[$key] = $Headers[$key] }
    $jsonBody = $null
    if ($null -ne $Body) { $jsonBody = $Body | ConvertTo-Json -Compress -Depth 20 }
    try {
        $params = @{ Uri = "$ApiBase$Path"; Method = $Method; Headers = $requestHeaders; TimeoutSec = 30; UseBasicParsing = $true; SkipHttpErrorCheck = $true }
        if ($null -ne $jsonBody) { $params.Body = $jsonBody; $params.ContentType = "application/json" }
        $response = Invoke-WebRequest @params
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Json = (Convert-ResponseJson $response.Content); Raw = $response.Content }
    } catch {
        return [pscustomobject]@{ Status = 0; Json = $null; Raw = $_.Exception.Message }
    }
}

function Get-ErrorCode {
    param($Response)
    if ($null -ne $Response.Json -and $null -ne $Response.Json.code) { return [string]$Response.Json.code }
    if ($null -ne $Response.Json -and $null -ne $Response.Json.detail -and $null -ne $Response.Json.detail.code) { return [string]$Response.Json.detail.code }
    return ""
}

function Wait-Until {
    param(
        [Parameter(Mandatory)][scriptblock]$Probe,
        [Parameter(Mandatory)][scriptblock]$Condition,
        [int]$TimeoutSeconds = 180,
        [int]$IntervalSeconds = 2,
        [string]$Description = "condition"
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $value = & $Probe
        if (& $Condition $value) { return $value }
        Start-Sleep -Seconds $IntervalSeconds
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "timeout waiting for $Description"
}

function Get-Field {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    return $Object.$Name
}

function Write-Report {
    param([hashtable]$Report)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($ReportPath, ($Report | ConvertTo-Json -Depth 20), $encoding)
}

Initialize-ComposeRoot
Push-Location $ComposeRoot
$LocationPushed = $true
Set-RecoveryEnvironment
$Report = @{
    schema = "recovery-drill-v1"
    status = "failed"
    run_id = $RunId
    started_at = [DateTime]::UtcNow.ToString("o")
    summary = @{ passed = 0; failed = 3 }
    timings = @{ mysql_rpo_seconds = 0; mysql_rto_seconds = 0; redis_rto_seconds = 0; worker_rto_seconds = 0 }
    checks = @{}
}
$ComposeStarted = $false
try {
    if (-not $SkipBuild) { Invoke-ComposeChecked @("down", "--volumes", "--remove-orphans") | Out-Null }
    $upArgs = @("up", "--detach", "--wait", "--wait-timeout", "900", "mysql", "redis", "api", "worker")
    if (-not $SkipBuild) { $upArgs = @("up", "--build", "--detach", "--wait", "--wait-timeout", "900", "mysql", "redis", "api", "worker") }
    Invoke-ComposeChecked $upArgs | Out-Null
    $ComposeStarted = $true

    $register = Invoke-ApiRequest -Method POST -Path "/auth/register" -Body @{ username = $SyntheticUsername; email = $SyntheticEmail; password = $SyntheticPassword }
    if ($register.Status -notin @(200, 201)) { throw "synthetic registration failed: HTTP $($register.Status) $(Get-ErrorCode $register)" }
    $login = Invoke-ApiRequest -Method POST -Path "/auth/login" -Body @{ login = $SyntheticUsername; password = $SyntheticPassword }
    if ($login.Status -ne 200) { throw "synthetic login failed: HTTP $($login.Status) $(Get-ErrorCode $login)" }
    $AccessToken = [string](Get-Field $login.Json "access_token")
    if ([string]::IsNullOrWhiteSpace($AccessToken)) { throw "login response did not contain access token" }
    $AuthHeaders = @{ Authorization = "Bearer $AccessToken" }

    $mysqlRpoStart = [DateTime]::UtcNow
    $backupCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers --events --no-tablespaces --add-drop-table password_detective > /tmp/recovery.sql'
    Invoke-ComposeChecked @("exec", "-T", "mysql", "sh", "-lc", $backupCommand) | Out-Null
    $backupPath = Join-Path $OutputPath "mysql-backup.sql"
    & docker @ComposeArgs cp "mysql:/tmp/recovery.sql" $backupPath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupPath)) { throw "mysql backup copy failed" }
    $backupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath).Hash.ToLowerInvariant()
    $mysqlRpo = ([DateTime]::UtcNow - $mysqlRpoStart).TotalSeconds

    Invoke-ComposeChecked @("stop", "api", "worker") | Out-Null
    $clearStart = [DateTime]::UtcNow
    $clearSql = "DROP DATABASE password_detective; CREATE DATABASE password_detective CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL PRIVILEGES ON password_detective.* TO 'password_detective'@'%'; FLUSH PRIVILEGES;"
    $clearCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "' + $clearSql + '"'
    Invoke-ComposeChecked @("exec", "-T", "mysql", "sh", "-lc", $clearCommand) | Out-Null
    $countSql = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='password_detective';"
    $countCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -uroot -e "' + $countSql + '"'
    $countOutput = Invoke-ComposeChecked @("exec", "-T", "mysql", "sh", "-lc", $countCommand)
    $tableCount = [int](($countOutput -join "`n").Trim())
    if ($tableCount -ne 0) { throw "mysql clear did not remove tables: $tableCount" }
    & docker @ComposeArgs cp $backupPath "mysql:/tmp/recovery.sql" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "mysql backup restore copy failed" }
    $restoreCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot password_detective < /tmp/recovery.sql'
    Invoke-ComposeChecked @("exec", "-T", "mysql", "sh", "-lc", $restoreCommand) | Out-Null
    Invoke-ComposeChecked @("up", "--detach", "--wait", "--wait-timeout", "300", "api", "worker") | Out-Null
    $readyAfterMysql = Wait-Until -Description "API readiness after MySQL restore" -Probe { Invoke-ApiRequest -Method GET -Path "/health/ready" } -Condition { param($r) $r.Status -eq 200 } -TimeoutSeconds 180
    $loginAfterMysql = Invoke-ApiRequest -Method POST -Path "/auth/login" -Body @{ login = $SyntheticUsername; password = $SyntheticPassword }
    if ($loginAfterMysql.Status -ne 200) { throw "login after mysql restore failed: HTTP $($loginAfterMysql.Status)" }
    $mysqlRto = ([DateTime]::UtcNow - $clearStart).TotalSeconds
    $Report.checks.mysql_backup_restore = @{ status = "passed"; table_count_after_clear = $tableCount; marker_restored = $true; backup_sha256 = $backupHash }
    $Report.timings.mysql_rpo_seconds = [math]::Round($mysqlRpo, 3)
    $Report.timings.mysql_rto_seconds = [math]::Round($mysqlRto, 3)

    $redisDownStart = [DateTime]::UtcNow
    Invoke-ComposeChecked @("stop", "redis") | Out-Null
    $liveOutage = Wait-Until -Description "liveness during Redis outage" -Probe { Invoke-ApiRequest -Method GET -Path "/health/live" } -Condition { param($r) $r.Status -eq 200 } -TimeoutSeconds 60 -IntervalSeconds 1
    $readyOutage = Wait-Until -Description "readiness failure during Redis outage" -Probe { Invoke-ApiRequest -Method GET -Path "/health/ready" } -Condition { param($r) $r.Status -eq 503 -and (Get-ErrorCode $r) -eq "health.redis_unavailable" } -TimeoutSeconds 60 -IntervalSeconds 1
    $rateOutage = Invoke-ApiRequest -Method POST -Path "/auth/login" -Body @{ login = $SyntheticUsername; password = $SyntheticPassword }
    if ($rateOutage.Status -ne 503 -or (Get-ErrorCode $rateOutage) -ne "rate_limit.backend_unavailable") { throw "login did not fail closed during Redis outage: HTTP $($rateOutage.Status) $(Get-ErrorCode $rateOutage)" }
    Invoke-ComposeChecked @("start", "redis") | Out-Null
    $readyAfterRedis = Wait-Until -Description "readiness after Redis recovery" -Probe { Invoke-ApiRequest -Method GET -Path "/health/ready" } -Condition { param($r) $r.Status -eq 200 } -TimeoutSeconds 120 -IntervalSeconds 2
    $redisRto = ([DateTime]::UtcNow - $redisDownStart).TotalSeconds
    $Report.checks.redis_loss_recovery = @{ status = "passed"; live_status_during_outage = $liveOutage.Status; ready_status_during_outage = $readyOutage.Status; rate_limit_status_during_outage = $rateOutage.Status; ready_status_after_recovery = $readyAfterRedis.Status }
    $Report.timings.redis_rto_seconds = [math]::Round($redisRto, 3)

    $workerStart = [DateTime]::UtcNow
    Invoke-ComposeChecked @("stop", "worker") | Out-Null
    $idempotencyKey = "recovery-export-$RunId"
    $export = Invoke-ApiRequest -Method POST -Path "/me/privacy/exports" -Headers (@{ Authorization = "Bearer $AccessToken"; "Idempotency-Key" = $idempotencyKey }) -Body @{}
    if ($export.Status -ne 202) { throw "privacy export request failed: HTTP $($export.Status) $(Get-ErrorCode $export)" }
    $exportId = [string](Get-Field $export.Json "id")
    if ([string]::IsNullOrWhiteSpace($exportId)) { throw "privacy export response did not contain id" }
    if ([string](Get-Field $export.Json "status") -ne "pending") { throw "privacy export was not pending before worker restart" }
    Invoke-ComposeChecked @("start", "worker") | Out-Null
    $readyExport = Wait-Until -Description "privacy export worker completion" -Probe { Invoke-ApiRequest -Method GET -Path "/me/privacy/exports/$exportId" -Headers $AuthHeaders } -Condition { param($r) $r.Status -eq 200 -and [string](Get-Field $r.Json "status") -eq "ready" } -TimeoutSeconds 180 -IntervalSeconds 2
    $pingOutput = Invoke-ComposeChecked @("exec", "-T", "worker", "celery", "-A", "password_detective.worker.celery_app", "inspect", "ping", "--timeout=10")
    if (($pingOutput -join "`n") -notmatch "pong") { throw "worker inspect ping did not report pong" }
    $enqueueCode = "from password_detective.worker import celery_app; celery_app.send_task('privacy.build_export', args=['$exportId']); celery_app.send_task('privacy.build_export', args=['$exportId'])"
    Invoke-ComposeChecked @("exec", "-T", "api", "python", "-c", $enqueueCode) | Out-Null
    Start-Sleep -Seconds 3
    $auditSql = "SELECT COUNT(*) FROM audit_logs WHERE action='privacy.export.ready' AND target_id='$exportId';"
    $auditCommand = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -uroot password_detective -e "' + $auditSql + '"'
    $auditOutput = Invoke-ComposeChecked @("exec", "-T", "mysql", "sh", "-lc", $auditCommand)
    $readyEventCount = [int](($auditOutput -join "`n").Trim())
    if ($readyEventCount -ne 1) { throw "privacy export ready audit count was $readyEventCount, expected 1" }
    $workerRto = ([DateTime]::UtcNow - $workerStart).TotalSeconds
    $Report.checks.worker_restart_idempotency = @{ status = "passed"; initial_status = "pending"; final_status = [string](Get-Field $readyExport.Json "status"); ready_event_count = $readyEventCount; worker_ping = "pong" }
    $Report.timings.worker_rto_seconds = [math]::Round($workerRto, 3)

    $Report.status = "passed"
    $Report.summary = @{ passed = 3; failed = 0 }
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Host "Recovery drill passed. Evidence: $ReportPath"
} catch {
    $Report.error_code = "recovery_drill_failed"
    $Report.error_message = $_.Exception.Message -replace "(?i)(password|secret|token|authorization)\s*[:=]\s*[^\s]+", '$1=[redacted]'
    $Report.finished_at = [DateTime]::UtcNow.ToString("o")
    Write-Report $Report
    Write-Error $_
    exit 1
} finally {
    if ($ComposeStarted -and -not $KeepEnvironment) {
        Invoke-ComposeBestEffort @("down", "--volumes", "--remove-orphans") | Out-Null
    }
    if ($KeepEnvironment) { Write-Host "Recovery environment kept: $ProjectName" }
    Restore-Environment
    if ($LocationPushed) { Pop-Location }
    if ($null -ne $SubstDrive) { & subst.exe $SubstDrive /d | Out-Null }
    Stop-Transcript | Out-Null
}


