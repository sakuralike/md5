param(
    [string]$PythonCommand = "",
    [int]$Port = 18130,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"

if (-not $PythonCommand) {
    $VenvPython = Join-Path $Api ".venv/Scripts/python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $PythonCommand = $VenvPython
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if ($Python) { $PythonCommand = $Python.Source }
    }
}
if (-not $PythonCommand) { throw "Python was not found." }
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $Root ".local/performance-wp4-iteration-7"
}
if (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $Root $OutputDirectory
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$DatabasePath = Join-Path $OutputDirectory "performance-runtime.db"
if (Test-Path -LiteralPath $DatabasePath) {
    Remove-Item -LiteralPath $DatabasePath -Force
}
$DatabaseUrlPath = [System.IO.Path]::GetFullPath($DatabasePath).Replace("\", "/")
$BaseUrl = "http://127.0.0.1:$Port"
$StdoutLog = Join-Path $OutputDirectory "api.stdout.log"
$StderrLog = Join-Path $OutputDirectory "api.stderr.log"
$ReportPath = Join-Path $OutputDirectory "performance-report.json"

$EnvironmentNames = @(
    "APP_ENV",
    "APP_SECRET_KEY",
    "DATABASE_URL",
    "RATE_LIMIT_BACKEND",
    "NOTIFICATION_BACKEND",
    "AUTO_CREATE_TABLES",
    "CORS_ORIGINS",
    "OBSERVABILITY_METRICS_ENABLED",
    "PYTHONUTF8"
)
$PreviousEnvironment = @{}
foreach ($Name in $EnvironmentNames) {
    $PreviousEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}

$Server = $null
try {
    $env:APP_ENV = "integration"
    $env:APP_SECRET_KEY = "synthetic-wp4-performance-secret-key"
    $env:DATABASE_URL = "sqlite:///$DatabaseUrlPath"
    $env:RATE_LIMIT_BACKEND = "memory"
    $env:NOTIFICATION_BACKEND = "memory"
    $env:AUTO_CREATE_TABLES = "true"
    $env:CORS_ORIGINS = "http://localhost:5173,http://localhost:5174"
    $env:OBSERVABILITY_METRICS_ENABLED = "true"
    $env:PYTHONUTF8 = "1"

    $StartParameters = @{
        FilePath = $PythonCommand
        ArgumentList = @(
            "-m", "uvicorn", "password_detective.main:app",
            "--host", "127.0.0.1", "--port", "$Port", "--no-access-log"
        )
        WorkingDirectory = $Api
        RedirectStandardOutput = $StdoutLog
        RedirectStandardError = $StderrLog
        PassThru = $true
    }
    if ($IsWindows) { $StartParameters["WindowStyle"] = "Hidden" }
    $Server = Start-Process @StartParameters

    $Ready = $false
    for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
        if ($Server.HasExited) {
            throw "Performance API process exited before readiness. See $StderrLog"
        }
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/v1/health/ready" -TimeoutSec 2
            if ($Response.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) { throw "Performance API did not become ready at $BaseUrl." }

    & $PythonCommand (Join-Path $Root "scripts/performance_probe.py") `
        --base-url $BaseUrl `
        --output $ReportPath
    if ($LASTEXITCODE -ne 0) {
        throw "Performance probe failed with exit code $LASTEXITCODE."
    }

    & $PythonCommand (Join-Path $Root "scripts/verify_performance_evidence.py") `
        --report $ReportPath `
        --write-checksums
    if ($LASTEXITCODE -ne 0) {
        throw "Performance evidence verification failed with exit code $LASTEXITCODE."
    }
} finally {
    if ($Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force
        $Server.WaitForExit()
    }
    foreach ($Name in $EnvironmentNames) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousEnvironment[$Name], "Process")
    }
}

Write-Host "Performance and observability gate passed. Evidence: $OutputDirectory"
