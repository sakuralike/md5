[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [string]$Profile = "infra/staging/readiness-profile.example.json",
    [string[]]$ComposeFiles = @("docker-compose.yml"),
    [string]$ProjectDirectory = "",
    [string]$Output = ".local/staging-topology-preflight-wp4-iteration-21/topology-capacity-preflight.json",
    [switch]$AllowBlocked
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Arguments = @(
    (Join-Path $PSScriptRoot "staging_topology_preflight.py"),
    "--profile", (Join-Path $Root $Profile),
    "--output", (Join-Path $Root $Output)
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
if ($AllowBlocked) { $Arguments += "--allow-blocked" }

Push-Location $Root
try {
    & $PythonCommand @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Staging topology preflight failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Staging topology preflight written: $(Join-Path $Root $Output)"
