[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [int]$DurationSeconds = 60,
    [int]$SampleIntervalSeconds = 15,
    [int]$TimeoutSeconds = 15,
    [string]$ApiMetricsUrl = "http://127.0.0.1:8000/api/v1/metrics",
    [string[]]$ComposeFiles = @("docker-compose.yml"),
    [string]$ProjectDirectory = "",
    [string]$OutputDirectory = ".local/staging-resource-observation-wp4-iteration-19"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutputPath = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
$ObservationPath = Join-Path $OutputPath "resource-observation.json"
$VerificationPath = Join-Path $OutputPath "resource-observation-verification.json"
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$CollectorArguments = @(
    (Join-Path $PSScriptRoot "collect_staging_resource_observation.py"),
    "--api-metrics-url", $ApiMetricsUrl,
    "--duration-seconds", "$DurationSeconds",
    "--sample-interval-seconds", "$SampleIntervalSeconds",
    "--timeout-seconds", "$TimeoutSeconds",
    "--output", $ObservationPath
)
$ResolvedComposeFiles = @(
    $ComposeFiles |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
if ($ResolvedComposeFiles.Count -eq 0) {
    throw "at least one Compose file is required"
}
foreach ($ComposeFile in $ResolvedComposeFiles) {
    $CollectorArguments += @("--compose-file", $ComposeFile)
}
if (-not [string]::IsNullOrWhiteSpace($ProjectDirectory)) {
    $CollectorArguments += @("--project-directory", $ProjectDirectory)
}

Push-Location $Root
try {
    & $PythonCommand @CollectorArguments
    if ($LASTEXITCODE -ne 0) { throw "resource observation collector failed with exit code $LASTEXITCODE" }
    & $PythonCommand (Join-Path $PSScriptRoot "verify_staging_resource_observation.py") `
        --input $ObservationPath `
        --output $VerificationPath `
        --write-checksums
    if ($LASTEXITCODE -ne 0) { throw "resource observation verifier failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Staging resource observation passed: $ObservationPath"
