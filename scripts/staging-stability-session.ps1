[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [int]$DurationSeconds = 120,
    [double]$ProbeIntervalSeconds = 1,
    [int]$ProbeWindowSeconds = 30,
    [int]$ResourceSampleIntervalSeconds = 15,
    [int]$WorkerCount = 3,
    [int]$WorkerLossAfterSeconds = 40,
    [int]$WorkerLossDurationSeconds = 20,
    [string]$ApiMetricsUrl = "http://127.0.0.1:8000/api/v1/metrics",
    [string[]]$ComposeFiles = @("docker-compose.yml"),
    [string]$ProjectDirectory = "",
    [string]$Profile = "infra/staging/readiness-profile.example.json",
    [string]$OutputDirectory = ".local/staging-stability-session-wp4-iteration-20",
    [switch]$RequestTargetExecution
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Arguments = @(
    (Join-Path $PSScriptRoot "run_staging_stability_session.py"),
    "--profile", (Join-Path $Root $Profile),
    "--duration-seconds", "$DurationSeconds",
    "--probe-interval-seconds", "$ProbeIntervalSeconds",
    "--probe-window-seconds", "$ProbeWindowSeconds",
    "--resource-sample-interval-seconds", "$ResourceSampleIntervalSeconds",
    "--worker-count", "$WorkerCount",
    "--worker-loss-after-seconds", "$WorkerLossAfterSeconds",
    "--worker-loss-duration-seconds", "$WorkerLossDurationSeconds",
    "--api-metrics-url", $ApiMetricsUrl,
    "--output-directory", (Join-Path $Root $OutputDirectory)
)
$ResolvedComposeFiles = @(
    $ComposeFiles |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
if ($ResolvedComposeFiles.Count -eq 0) { throw "at least one Compose file is required" }
foreach ($ComposeFile in $ResolvedComposeFiles) { $Arguments += @("--compose-file", $ComposeFile) }
if (-not [string]::IsNullOrWhiteSpace($ProjectDirectory)) {
    $Arguments += @("--project-directory", $ProjectDirectory)
}
if ($RequestTargetExecution) { $Arguments += "--request-target-execution" }

Push-Location $Root
try {
    & $PythonCommand @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Staging stability session failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Staging stability session passed: $(Join-Path $Root $OutputDirectory)"
