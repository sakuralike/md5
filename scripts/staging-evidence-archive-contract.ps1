param(
    [string]$OutputDirectory = ".local/staging-evidence-archive-contract-wp4-iteration-16",
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Output = if ([IO.Path]::IsPathRooted($OutputDirectory)) { [IO.Path]::GetFullPath($OutputDirectory) } else { [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory)) }
$Python = if ($PythonCommand) { $PythonCommand } elseif (Test-Path (Join-Path $Root "apps/api/.venv/Scripts/python.exe")) { Join-Path $Root "apps/api/.venv/Scripts/python.exe" } else { "python" }
$Evidence = $Output
$Archive = Join-Path $Output "archive"

& pwsh (Join-Path $Root "scripts/staging-target-adapter-contract.ps1") `
    -OutputDirectory $Evidence `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging target adapter contract failed before archive sealing" }

& pwsh (Join-Path $Root "scripts/staging-evidence-archive.ps1") `
    -EvidenceDirectory $Evidence `
    -OutputDirectory $Archive `
    -SealedAt "2026-08-10T05:00:00Z" `
    -PythonCommand $Python
if ($LASTEXITCODE -ne 0) { throw "staging evidence archive contract failed" }

$ManifestPath = Join-Path $Archive "staging-evidence-archive-manifest.json"
$ArchivePath = Join-Path $Archive "staging-evidence-archive.zip"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Manifest.status -ne "contract-sealed" -or $Manifest.handoff_status -ne "blocked-by-contract-fixture") {
    throw "contract fixture archive must remain blocked from approval handoff"
}
if ($Manifest.execution_status -ne "not-run" -or $Manifest.go_no_go_status -ne "pending-evidence") {
    throw "contract fixture archive must remain not-run and pending-evidence"
}
if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
    throw "staging evidence archive ZIP was not created"
}
Write-Host "Staging evidence archive contract is valid and remains blocked until target evidence exists. Output: $Output"
