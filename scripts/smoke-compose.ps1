param([switch]$KeepEnvironment)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$StartedAt = Get-Date
$SyntheticSuffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
$env:APP_SECRET_KEY = "synthetic-compose-secret-key-for-M1-gate-2026"
$env:MYSQL_PASSWORD = "synthetic_mysql_local"
$env:MYSQL_ROOT_PASSWORD = "synthetic_root_local"

function Invoke-DockerCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose 执行失败（退出码 $LASTEXITCODE）：$($Arguments -join ' ')"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未找到 Docker。请安装并启动 Docker Desktop 后重新执行。"
}

Push-Location $Root
try {
    Write-Host "清理本项目 Compose 环境（包含项目数据卷）..."
    Invoke-DockerCompose down --volumes --remove-orphans
    Invoke-DockerCompose up --build --detach --wait --wait-timeout 900

    $live = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready"
    if ($live.status -ne "ready") { throw "API 未就绪。" }

    $username = "compose_$SyntheticSuffix"
    $email = "$username@example.invalid"
    $password = "SyntheticCompose123!"
    Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/register" `
        -ContentType "application/json" `
        -Body (@{ username = $username; email = $email; password = $password } | ConvertTo-Json)
    $tokens = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login" `
        -ContentType "application/json" `
        -Body (@{ login = $username; password = $password } | ConvertTo-Json)
    if (-not $tokens.access_token) { throw "登录未返回访问令牌。" }

    $web = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5173/"
    $admin = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5174/"
    if ($web.StatusCode -ne 200 -or $admin.StatusCode -ne 200) {
        throw "Web 或 Admin 未正常响应。"
    }

    $elapsed = (Get-Date) - $StartedAt
    if ($elapsed.TotalMinutes -gt 30) { throw "从空环境到登录耗时超过 30 分钟。" }
    Write-Host ("M1 Compose 冒烟通过，耗时 {0:n1} 分钟。" -f $elapsed.TotalMinutes)
} finally {
    if (-not $KeepEnvironment) {
        Invoke-DockerCompose down --volumes --remove-orphans
    }
    Pop-Location
}
