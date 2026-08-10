[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$WebUrl = "http://localhost:5173",
    [string]$AdminUrl = "http://localhost:5174",
    [int]$TimeoutSec = 20,
    [switch]$SkipAuth
)

$ErrorActionPreference = "Stop"

function Normalize-BaseUrl {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value.TrimEnd('/')
}

function Assert-HttpStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Actual,
        [int]$Expected = 200
    )
    if ($Actual -ne $Expected) {
        throw "$Name returned HTTP $Actual; expected HTTP $Expected"
    }
}

function Invoke-JsonPost {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$Body
    )
    return Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -ContentType "application/json" `
        -TimeoutSec $TimeoutSec `
        -Body ($Body | ConvertTo-Json -Compress)
}

$Api = Normalize-BaseUrl $BaseUrl
$Web = Normalize-BaseUrl $WebUrl
$Admin = Normalize-BaseUrl $AdminUrl
$Results = [ordered]@{}

$Live = Invoke-RestMethod -Method Get -Uri "$Api/api/v1/health/live" -TimeoutSec $TimeoutSec
if ($Live.status -ne "ok") { throw "API liveness payload is not healthy" }
$Results.api_live = "passed"

$Ready = Invoke-RestMethod -Method Get -Uri "$Api/api/v1/health/ready" -TimeoutSec $TimeoutSec
if ($Ready.status -ne "ready" -or $Ready.database -ne "ok" -or $Ready.rate_limit -ne "ok") {
    throw "API readiness payload is not ready"
}
$Results.api_ready = "passed"

$WebHealth = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$Web/api/v1/health/live" -TimeoutSec $TimeoutSec
Assert-HttpStatus -Name "web API proxy" -Actual $WebHealth.StatusCode
$Results.web_api_proxy = "passed"

$AdminHealth = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$Admin/api/v1/health/live" -TimeoutSec $TimeoutSec
Assert-HttpStatus -Name "admin API proxy" -Actual $AdminHealth.StatusCode
$Results.admin_api_proxy = "passed"

$WebPage = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$Web/" -TimeoutSec $TimeoutSec
Assert-HttpStatus -Name "web page" -Actual $WebPage.StatusCode
if ($WebPage.Content -notmatch "<title>密码侦探社</title>") { throw "web page title mismatch" }
$Results.web_page = "passed"

$AdminPage = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "$Admin/" -TimeoutSec $TimeoutSec
Assert-HttpStatus -Name "admin page" -Actual $AdminPage.StatusCode
if ($AdminPage.Content -notmatch "<title>密码侦探社管理端</title>") { throw "admin page title mismatch" }
$Results.admin_page = "passed"

if (-not $SkipAuth) {
    $Suffix = [Guid]::NewGuid().ToString("N").Substring(0, 12)
    $Username = "staging_smoke_$Suffix"
    $Email = "$Username@synthetic.example.com"
    $Password = "SyntheticStaging123!"
    $null = Invoke-JsonPost -Uri "$Api/api/v1/auth/register" -Body @{
        username = $Username
        email = $Email
        password = $Password
    }
    $Results.auth_register = "passed"

    $Tokens = Invoke-JsonPost -Uri "$Api/api/v1/auth/login" -Body @{
        login = $Username
        password = $Password
    }
    if ([string]::IsNullOrWhiteSpace($Tokens.access_token)) { throw "auth login did not return an access token" }
    $Results.auth_login = "passed"

    $Profile = Invoke-RestMethod `
        -Method Get `
        -Uri "$Api/api/v1/me/profile" `
        -Headers @{ Authorization = "Bearer $($Tokens.access_token)" } `
        -TimeoutSec $TimeoutSec
    if ($Profile.username -ne $Username) { throw "profile username mismatch" }
    $Results.auth_profile = "passed"
}

Write-Host ("Staging smoke passed: {0}" -f (($Results.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "))
