param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [System.IO.Path]::GetFullPath((Join-Path $Root ".local/pdpp-conformance"))
$RootPrefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if (-not $OutputRoot.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "PDPP output path escaped the repository root."
}

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

foreach ($command in @("dotnet", "go", "cargo", "uvx")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required for the PDPP language conformance gate."
    }
}

if (Test-Path -LiteralPath $OutputRoot) {
    Remove-Item -LiteralPath $OutputRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$CSharpOutput = Join-Path $OutputRoot "csharp"
Invoke-Checked -Command dotnet -Arguments @(
    "publish"
    (Join-Path $Root "tests/fixtures/pdpp/csharp/PdppSyntheticPlugin.csproj")
    "--configuration", "Release"
    "--runtime", "win-x64"
    "--self-contained", "true"
    "/p:PublishSingleFile=true"
    "/p:DebugType=None"
    "--output", $CSharpOutput
)
$CSharpExecutable = Join-Path $CSharpOutput "pdpp-synthetic-plugin.exe"

$GoOutput = Join-Path $OutputRoot "go"
New-Item -ItemType Directory -Path $GoOutput | Out-Null
$GoExecutable = Join-Path $GoOutput "pdpp-go.exe"
$PreviousCgo = $env:CGO_ENABLED
try {
    $env:CGO_ENABLED = "0"
    Push-Location (Join-Path $Root "tests/fixtures/pdpp/go")
    try {
        Invoke-Checked -Command go -Arguments @(
            "build", "-trimpath", "-ldflags", "-s -w", "-o", $GoExecutable, "."
        )
    } finally {
        Pop-Location
    }
} finally {
    $env:CGO_ENABLED = $PreviousCgo
}

$RustTarget = Join-Path $OutputRoot "rust-target"
$RustOutput = Join-Path $OutputRoot "rust"
New-Item -ItemType Directory -Path $RustOutput | Out-Null
Invoke-Checked -Command cargo -Arguments @(
    "build"
    "--locked"
    "--release"
    "--manifest-path", (Join-Path $Root "tests/fixtures/pdpp/rust/Cargo.toml")
    "--target-dir", $RustTarget
)
$RustExecutable = Join-Path $RustOutput "pdpp-rust.exe"
Copy-Item -LiteralPath (Join-Path $RustTarget "release/pdpp-synthetic-rust.exe") -Destination $RustExecutable

$PythonOutput = Join-Path $OutputRoot "python"
$PythonWork = Join-Path $OutputRoot "python-work"
$PythonSpec = Join-Path $OutputRoot "python-spec"
New-Item -ItemType Directory -Path $PythonOutput, $PythonWork, $PythonSpec | Out-Null
Invoke-Checked -Command uvx -Arguments @(
    "--from", "pyinstaller==6.16.0"
    "pyinstaller"
    "--clean"
    "--noconfirm"
    "--onefile"
    "--name", "pdpp-python"
    "--distpath", $PythonOutput
    "--workpath", $PythonWork
    "--specpath", $PythonSpec
    (Join-Path $Root "tests/fixtures/pdpp/python/pdpp_plugin.py")
)
$PythonExecutable = Join-Path $PythonOutput "pdpp-python.exe"

$MatrixPath = Join-Path $OutputRoot "matrix.json"
@(
    @{ plugin_id = "synthetic.csharp"; language = "csharp"; executable_path = $CSharpExecutable }
    @{ plugin_id = "synthetic.go"; language = "go"; executable_path = $GoExecutable }
    @{ plugin_id = "synthetic.rust"; language = "rust"; executable_path = $RustExecutable }
    @{ plugin_id = "synthetic.python"; language = "python"; executable_path = $PythonExecutable }
) | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $MatrixPath -Encoding utf8NoBOM

Invoke-Checked -Command dotnet -Arguments @(
    "run"
    "--project", (Join-Path $Root "tests/pdpp-conformance/PdppConformance.csproj")
    "--configuration", "Release"
    "--"
    $MatrixPath
)

Write-Host "PDPP language conformance gate passed."
