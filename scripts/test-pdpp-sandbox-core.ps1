param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Manifest = Join-Path $Root "packages/pdpp-sandbox-core/Cargo.toml"
$Schema = Join-Path $Root "packages/pdpp-sandbox-core/protocol/sandbox-core-v1.schema.json"

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo is required for the Pdpp Sandbox Core contract gate."
}

if (-not (Test-Path -LiteralPath $Manifest) -or -not (Test-Path -LiteralPath $Schema)) {
    throw "Pdpp Sandbox Core manifest or schema is missing."
}

Push-Location $Root
try {
    & cargo fmt --manifest-path $Manifest -- --check
    if ($LASTEXITCODE -ne 0) { throw "Pdpp Sandbox Core formatting check failed." }

    & cargo test --manifest-path $Manifest --locked
    if ($LASTEXITCODE -ne 0) { throw "Pdpp Sandbox Core contract tests failed." }

    & cargo build --manifest-path $Manifest --release --locked
    if ($LASTEXITCODE -ne 0) { throw "Pdpp Sandbox Core release build failed." }

    $schemaDocument = Get-Content -LiteralPath $Schema -Raw | ConvertFrom-Json
    $requiredMethods = @(
        "sandbox.create",
        "sandbox.destroy",
        "process.spawn",
        "process.terminate",
        "fs.grant_read",
        "fs.read_chunk",
        "fs.grant_write",
        "env.sanitize",
        "net.block_outbound",
        "reg.deny_write",
        "canary.run",
        "attest.host",
        "shutdown"
    )
    $schemaMethods = @($schemaDocument.properties.method.enum)
    if (@(Compare-Object $requiredMethods $schemaMethods).Count -ne 0) {
        throw "Pdpp Sandbox Core schema method set does not match the contract."
    }

    $executable = Join-Path $Root "packages/pdpp-sandbox-core/target/release/pdpp-sandbox-core.exe"
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "Pdpp Sandbox Core release executable is missing."
    }
}
finally {
    Pop-Location
}

Write-Host "Pdpp Sandbox Core contract gate passed."
