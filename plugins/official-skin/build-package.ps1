param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PrivateKey = $env:PDPP_PUBLISHER_PRIVATE_KEY_BASE64
if ([string]::IsNullOrWhiteSpace($PrivateKey) -or [string]::IsNullOrWhiteSpace($env:PDPP_PUBLISHER_KEY_ID)) {
    throw "Set PDPP_PUBLISHER_PRIVATE_KEY_BASE64 and PDPP_PUBLISHER_KEY_ID before building the official plugin package."
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $Root ".local/official-skin/official-skin.pdpkg"
} else {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
}
$PublishDirectory = Join-Path $Root ".local/official-skin/publish-1.0.1"
New-Item -ItemType Directory -Force -Path $PublishDirectory, (Split-Path -Parent $OutputPath) | Out-Null

& dotnet publish (Join-Path $Root "plugins/official-skin/PasswordDetective.OfficialSkin.csproj") `
    --configuration Release --runtime win-x64 --self-contained true /p:PublishSingleFile=true /p:DebugType=None --output $PublishDirectory
if ($LASTEXITCODE -ne 0) { throw "Official skin publish failed." }

& dotnet run --project (Join-Path $Root "tests/pdpp-package-builder/PdppPackageBuilder.csproj") --configuration Release -- `
    (Join-Path $PublishDirectory "password-detective-official-skin.exe") $OutputPath `
    (Join-Path $PSScriptRoot "manifest.template.json") `
    (Join-Path $PSScriptRoot "schemas/apply.schema.json") `
    (Join-Path $PSScriptRoot "sbom.cdx.json") $PrivateKey
if ($LASTEXITCODE -ne 0) { throw "Official skin package build failed." }

Write-Host "Official skin package created: $OutputPath"
