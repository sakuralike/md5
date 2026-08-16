param(
    [string]$PythonCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = if ($PythonCommand) { $PythonCommand } else { Join-Path $Root "apps/api/.venv/Scripts/python.exe" }
$LocalRoot = Join-Path $Root ".local"
$RunRoot = Join-Path $LocalRoot ("production-secrets-contract-" + [guid]::NewGuid().ToString("N"))
$SecretDirectory = Join-Path $RunRoot "secrets"
$Rendered = Join-Path $RunRoot "compose.rendered.yml"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
try {
    Invoke-Checked $Python (Join-Path $PSScriptRoot "manage_production_secrets.py") init --directory $SecretDirectory
    Invoke-Checked $Python (Join-Path $PSScriptRoot "manage_production_secrets.py") verify --directory $SecretDirectory
    $PreviousSecretDirectory = $env:PASSWORD_DETECTIVE_SECRET_DIR
    try {
        $env:PASSWORD_DETECTIVE_SECRET_DIR = $SecretDirectory
        & docker compose `
            -f (Join-Path $Root "docker-compose.yml") `
            -f (Join-Path $Root "docker-compose.production-secrets.yml") `
            --env-file (Join-Path $Root "infra/production/production-secrets.env.example") `
            config | Set-Content -LiteralPath $Rendered -Encoding utf8
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose config failed with exit code $LASTEXITCODE"
        }
    } finally {
        $env:PASSWORD_DETECTIVE_SECRET_DIR = $PreviousSecretDirectory
    }

    $RenderedText = Get-Content -LiteralPath $Rendered -Raw
    $RequiredFragments = @(
        "APP_ENV: production",
        "APP_SECRET_KEY_FILE: /run/secrets/app_secret_key",
        "DATABASE_URL_FILE: /run/secrets/database_url",
        "REDIS_URL_FILE: /run/secrets/redis_url",
        "CANDIDATE_SECRET_KEYRING_FILE: /run/secrets/candidate_secret_keyring",
        "DIRECT_MESSAGE_KEY_VERSION_FILE: /run/secrets/direct_message_key_version",
        "DIRECT_MESSAGE_KEYRING_FILE: /run/secrets/direct_message_keyring",
        "MYSQL_PASSWORD_FILE: /run/secrets/mysql_password",
        "source: redis_password"
    )
    foreach ($Fragment in $RequiredFragments) {
        if (-not $RenderedText.Contains($Fragment)) {
            throw "Rendered compose is missing required fragment: $Fragment"
        }
    }
    foreach ($Name in @("app_secret_key", "mysql_password", "redis_password", "candidate_secret_dedup_key")) {
        $SecretValue = Get-Content -LiteralPath (Join-Path $SecretDirectory $Name) -Raw
        if ($RenderedText.Contains($SecretValue.TrimEnd("`r", "`n"))) {
            throw "Rendered compose leaked a managed secret: $Name"
        }
    }
    Write-Host "Production file-backed secrets contract passed."
} finally {
    if (Test-Path -LiteralPath $RunRoot) {
        $ResolvedRunRoot = (Resolve-Path -LiteralPath $RunRoot).Path
        $ResolvedLocalRoot = (Resolve-Path -LiteralPath $LocalRoot).Path
        if (-not $ResolvedRunRoot.StartsWith($ResolvedLocalRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to delete an unexpected path: $ResolvedRunRoot"
        }
        Remove-Item -LiteralPath $ResolvedRunRoot -Recurse -Force
    }
}
