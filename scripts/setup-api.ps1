$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root "apps/api"
. (Join-Path $PSScriptRoot "lib/Resolve-ApiVenvPython.ps1")

function Resolve-HostPython {
    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $installedPythonRoot = Join-Path $env:LOCALAPPDATA "Programs/Python"
        if (Test-Path -LiteralPath $installedPythonRoot -PathType Container) {
            $candidates += Get-ChildItem -LiteralPath $installedPythonRoot -Directory |
                Sort-Object LastWriteTime -Descending |
                ForEach-Object { Join-Path $_.FullName "python.exe" }
        }
    }

    $commandPython = Get-Command python -ErrorAction SilentlyContinue
    if ($commandPython) {
        $candidates += $commandPython.Source
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        & $candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }

    return $null
}

$VenvPython = Resolve-ApiVenvPython -ApiPath $Api
$requiresWindowsVenvRepair = $IsWindows -and $VenvPython -and $VenvPython -match "[\\\\/]\\.venv[\\\\/]bin[\\\\/]python\\.exe$"
if (-not $VenvPython -or $requiresWindowsVenvRepair) {
    $python = Resolve-HostPython
    if (-not $python) { throw "未找到 Python 3.12+。" }
    & $python -m venv --clear (Join-Path $Api ".venv")
    if ($LASTEXITCODE -ne 0) { throw "创建 API 虚拟环境失败。" }
    $VenvPython = Resolve-ApiVenvPython -ApiPath $Api
}

if (-not $VenvPython) { throw "API 虚拟环境中未找到 Python 可执行文件。" }

& $VenvPython -m pip install --disable-pip-version-check -e "$Api[dev]"
if ($LASTEXITCODE -ne 0) { throw "安装 API 开发依赖失败。" }
Write-Host "API 开发环境已就绪。"
