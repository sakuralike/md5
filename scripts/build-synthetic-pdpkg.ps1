param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [System.IO.Path]::GetFullPath((Join-Path $Root ".local/pdpp-example"))
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $OutputRoot "synthetic-echo.pdpkg"
} else {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
}
$PublishDirectory = Join-Path $OutputRoot "publish"
New-Item -ItemType Directory -Path $PublishDirectory -Force | Out-Null

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

Invoke-Checked -Command dotnet -Arguments @(
    "publish"
    (Join-Path $Root "tests/fixtures/pdpp/csharp/PdppSyntheticPlugin.csproj")
    "--configuration", "Release"
    "--runtime", "win-x64"
    "--self-contained", "true"
    "/p:PublishSingleFile=true"
    "/p:DebugType=None"
    "--output", $PublishDirectory
)

Invoke-Checked -Command dotnet -Arguments @(
    "run"
    "--project", (Join-Path $Root "tests/pdpp-package-builder/PdppPackageBuilder.csproj")
    "--configuration", "Release"
    "--"
    (Join-Path $PublishDirectory "pdpp-synthetic-plugin.exe")
    $OutputPath
)

Write-Host "Synthetic plugin package created: $OutputPath"
