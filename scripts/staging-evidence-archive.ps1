param(
    [Parameter(Mandatory = $true)][string]$EvidenceDirectory,
    [string]$OutputDirectory = ".local/staging-evidence-archive",
    [string]$CandidateCommit = "",
    [string]$SealedAt = "",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }

function Resolve-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
    return [IO.Path]::GetFullPath((Join-Path $Root $Value))
}

$EvidencePath = Resolve-ProjectPath $EvidenceDirectory
$OutputPath = Resolve-ProjectPath $OutputDirectory
if (-not (Test-Path -LiteralPath $EvidencePath -PathType Container)) {
    throw "staging evidence directory was not found: $EvidencePath"
}
if (-not $SealedAt) {
    $SealedAt = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$Arguments = @(
    (Join-Path $Root "scripts/seal_staging_evidence_archive.py"),
    "--evidence-directory", $EvidencePath,
    "--output-directory", $OutputPath,
    "--sealed-at", $SealedAt
)
if ($CandidateCommit) {
    $Arguments += @("--candidate-commit", $CandidateCommit)
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "staging evidence archive sealing failed" }

$ManifestPath = Join-Path $OutputPath "staging-evidence-archive-manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "Staging evidence archive sealed: status=$($Manifest.status), handoff_status=$($Manifest.handoff_status), output=$OutputPath"
