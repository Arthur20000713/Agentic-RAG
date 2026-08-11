[CmdletBinding()]
param(
    [string]$OutputDir = ".tmp_tests\p2_compose",
    [int]$JavaPort = 8080,
    [string]$MysqlPassword = "p2-test-mysql-password",
    [string]$MysqlRootPassword = "p2-test-root-password",
    [string]$RedisPassword = "p2-test-redis-password",
    [string]$AiServiceToken = "p2-test-ai-service-token-32-characters",
    [string]$AdminUsername = $env:BOOTSTRAP_ADMIN_USERNAME,
    [string]$AdminPassword = $env:BOOTSTRAP_ADMIN_PASSWORD
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ResolvedOutputDir = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $ResolvedOutputDir | Out-Null
$LogPath = Join-Path $ResolvedOutputDir "compose.log"
$SummaryPath = Join-Path $ResolvedOutputDir "summary.json"

$env:JAVA_PORT = $JavaPort.ToString()
$env:MYSQL_PASSWORD = $MysqlPassword
$env:MYSQL_ROOT_PASSWORD = $MysqlRootPassword
$env:REDIS_PASSWORD = $RedisPassword
$env:AI_SERVICE_TOKEN = $AiServiceToken

if ([string]::IsNullOrWhiteSpace($AdminUsername) -or
        [string]::IsNullOrWhiteSpace($AdminPassword)) {
    throw "AdminUsername and AdminPassword are required"
}

function Invoke-ComposeStep {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker compose @Arguments 2>&1 |
            Tee-Object -FilePath $LogPath -Append
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($ExitCode -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $ExitCode"
    }
}

Push-Location $Root
try {
    Invoke-ComposeStep @("config", "--quiet")
    Invoke-ComposeStep @(
        "up",
        "--detach",
        "--build",
        "--wait",
        "--wait-timeout",
        "300"
    )

    $Liveness = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$JavaPort/actuator/health/liveness" `
        -Method Get
    $Readiness = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$JavaPort/actuator/health/readiness" `
        -Method Get
    $LoginBody = @{
        username = $AdminUsername
        password = $AdminPassword
    } | ConvertTo-Json -Compress
    $Login = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$JavaPort/api/v1/auth/login" `
        -Method Post `
        -ContentType "application/json" `
        -Body $LoginBody
    $AccessToken = $Login.data.accessToken
    if ([string]::IsNullOrWhiteSpace($AccessToken)) {
        throw "Admin login did not return an access token"
    }
    $RequestId = "req_compose_smoke_0001"
    $SystemResponse = Invoke-WebRequest `
        -UseBasicParsing `
        -Uri "http://127.0.0.1:$JavaPort/api/v1/system/status" `
        -Headers @{
            "Authorization" = "Bearer $AccessToken"
            "X-Request-ID" = $RequestId
        } `
        -Method Get
    $SystemBody = $SystemResponse.Content | ConvertFrom-Json

    $Bindings = [ordered]@{}
    foreach ($Service in @("mysql", "redis", "python-ai", "java-app")) {
        $ContainerId = (& docker compose ps --quiet $Service).Trim()
        if ([string]::IsNullOrWhiteSpace($ContainerId)) {
            throw "No running container found for $Service"
        }
        $Container = (& docker inspect $ContainerId | ConvertFrom-Json)[0]
        $Published = @()
        if ($null -ne $Container.HostConfig.PortBindings) {
            foreach ($Property in $Container.HostConfig.PortBindings.PSObject.Properties) {
                if ($null -ne $Property.Value) {
                    $Published += $Property.Name
                }
            }
        }
        $Bindings[$Service] = $Published
    }

    if ($Liveness.status -ne "UP" -or $Readiness.status -ne "UP") {
        throw "Java liveness/readiness is not UP"
    }
    foreach ($Dependency in @("mysql", "redis", "pythonAi")) {
        if ($SystemBody.data.dependencies.$Dependency.status -ne "UP") {
            throw "Java dependency status is DOWN: $Dependency"
        }
    }
    if ($SystemResponse.Headers["X-Request-ID"] -ne $RequestId) {
        throw "Java did not echo X-Request-ID"
    }
    if (
        $Bindings["mysql"].Count -ne 0 `
        -or $Bindings["redis"].Count -ne 0 `
        -or $Bindings["python-ai"].Count -ne 0 `
        -or $Bindings["java-app"].Count -ne 1 `
        -or $Bindings["java-app"][0] -ne "8080/tcp"
    ) {
        throw "Only java-app:8080/tcp may be published"
    }

    [ordered]@{
        status = "passed"
        liveness = $Liveness.status
        readiness = $Readiness.status
        dependencies = $SystemBody.data.dependencies
        request_id = $SystemBody.requestId
        authenticated_system_check = $true
        port_bindings = $Bindings
        fake_rag = $true
        log = $LogPath
    } | ConvertTo-Json -Depth 8 |
        Out-File -LiteralPath $SummaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $SummaryPath
}
catch {
    [ordered]@{
        status = "failed"
        error = $_.Exception.Message
        log = $LogPath
    } | ConvertTo-Json -Depth 4 |
        Out-File -LiteralPath $SummaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $SummaryPath
    exit 1
}
finally {
    Pop-Location
}
