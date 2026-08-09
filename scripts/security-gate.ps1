param(
    [string]$PythonCommand = "",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
$PnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
$Pnpm = if ($PnpmCommand) { $PnpmCommand.Source } else { $null }

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
if (-not $Pnpm) { throw "pnpm was not found." }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $Root ".local/security" }
if (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $Root $OutputDirectory
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

$PreviousPythonUtf8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = "1"
Push-Location $Root
try {
    Invoke-Checked -Command $PythonCommand -Arguments @("-m", "ruff", "check", "scripts/dast_security_gate.py", "scripts/verify_security_artifacts.py", "scripts/verify_release_security.py", "scripts/tests/test_dast_security_gate.py", "scripts/tests/test_verify_security_artifacts.py", "scripts/tests/test_verify_release_security.py")
    Invoke-Checked -Command $PythonCommand -Arguments @("-m", "unittest", "discover", "-s", "scripts/tests")
    Invoke-Checked -Command $PythonCommand -Arguments @("scripts/verify_release_security.py", "--directory", (Join-Path $OutputDirectory "release-policy"), "--risk-acceptances", "security/risk-acceptances.json", "--policy-only", "--write-checksums")
    Invoke-Checked -Command $PythonCommand -Arguments @("-m", "bandit", "-r", "apps/api/src", "-ll", "-ii", "-f", "json", "-o", (Join-Path $OutputDirectory "bandit-report.json"))
    Invoke-Checked -Command $PythonCommand -Arguments @("-m", "pip_audit", "--strict", "--format", "json", "--output", (Join-Path $OutputDirectory "api-dependency-audit.json"), $Api)
    Invoke-Checked -Command $PythonCommand -Arguments @("-m", "pip_audit", "--strict", "--format", "cyclonedx-json", "--output", (Join-Path $OutputDirectory "api-sbom.cdx.json"), $Api)

    $NodeAudit = & $Pnpm audit --prod --audit-level high --json
    $NodeAuditExitCode = $LASTEXITCODE
    $NodeAudit | Set-Content -LiteralPath (Join-Path $OutputDirectory "pnpm-audit.json") -Encoding utf8
    if ($NodeAuditExitCode -ne 0) {
        throw "pnpm production dependency audit failed with exit code $NodeAuditExitCode."
    }

    Invoke-Checked -Command $PythonCommand -Arguments @("scripts/verify_security_artifacts.py", "--directory", $OutputDirectory, "--write-checksums")
} finally {
    Pop-Location
    $env:PYTHONUTF8 = $PreviousPythonUtf8
}

Write-Host "Security gate passed. Evidence: $OutputDirectory"
