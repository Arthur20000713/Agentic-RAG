[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:8080',
    [string]$AdminUsername = $env:BOOTSTRAP_ADMIN_USERNAME,
    [string]$AdminPassword = $env:BOOTSTRAP_ADMIN_PASSWORD,
    [int]$RecoveryTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$results = [System.Collections.Generic.List[object]]::new()

function Invoke-Compose {
    param([Parameter(Mandatory)][string[]]$ComposeArguments)

    & docker compose @ComposeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($ComposeArguments -join ' ')"
    }
}

function Invoke-Http {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [hashtable]$Headers = @{},
        [string]$Body,
        [int]$TimeoutSeconds = 15
    )

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $request = @{
            UseBasicParsing = $true
            Method = $Method
            Uri = $Uri
            Headers = $Headers
            TimeoutSec = $TimeoutSeconds
        }
        if ($PSBoundParameters.ContainsKey('Body')) {
            $request.ContentType = 'application/json'
            $request.Body = $Body
        }
        $response = Invoke-WebRequest @request
        return [pscustomobject]@{
            Status = [int]$response.StatusCode
            Body = $response.Content
            ElapsedMs = $watch.ElapsedMilliseconds
        }
    } catch {
        $response = $_.Exception.Response
        if ($null -eq $response) {
            throw
        }
        $content = $_.ErrorDetails.Message
        if ([string]::IsNullOrWhiteSpace($content)) {
            $stream = $response.GetResponseStream()
            $reader = [System.IO.StreamReader]::new($stream)
            try {
                $content = $reader.ReadToEnd()
            } finally {
                $reader.Dispose()
                $stream.Dispose()
            }
        }
        return [pscustomobject]@{
            Status = [int]$response.StatusCode
            Body = $content
            ElapsedMs = $watch.ElapsedMilliseconds
        }
    } finally {
        $watch.Stop()
    }
}

function Wait-HttpStatus {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][int]$ExpectedStatus,
        [int]$TimeoutSeconds = $RecoveryTimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-Http -Method GET -Uri $Uri -TimeoutSeconds 5
            if ($response.Status -eq $ExpectedStatus) {
                return $response
            }
        } catch {
            if ($ExpectedStatus -eq 0) {
                return $null
            }
        }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Timed out waiting for HTTP $ExpectedStatus from $Uri"
}

function Assert-Status {
    param(
        [Parameter(Mandatory)]$Response,
        [Parameter(Mandatory)][int]$ExpectedStatus,
        [Parameter(Mandatory)][string]$Step
    )

    if ($Response.Status -ne $ExpectedStatus) {
        throw "$Step expected HTTP $ExpectedStatus but received $($Response.Status): $($Response.Body)"
    }
}

function Start-DependencyAndWait {
    param([Parameter(Mandatory)][string]$Service)

    Invoke-Compose -ComposeArguments @('start', $Service)
    Wait-HttpStatus -Uri "$BaseUrl/actuator/health/readiness" -ExpectedStatus 200 | Out-Null
}

if ([string]::IsNullOrWhiteSpace($AdminUsername) -or
        [string]::IsNullOrWhiteSpace($AdminPassword)) {
    throw 'BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD are required'
}

$previousLocation = Get-Location
$pythonStopped = $false
$redisStopped = $false
$mysqlStopped = $false
try {
    Set-Location -LiteralPath $repoRoot
    Wait-HttpStatus -Uri "$BaseUrl/actuator/health/readiness" -ExpectedStatus 200 | Out-Null

    $loginBody = @{
        username = $AdminUsername
        password = $AdminPassword
    } | ConvertTo-Json -Compress
    $login = Invoke-Http `
        -Method POST `
        -Uri "$BaseUrl/api/v1/auth/login" `
        -Headers @{'X-Request-ID' = 'req_p7_resilience_login_0001'} `
        -Body $loginBody
    Assert-Status -Response $login -ExpectedStatus 200 -Step 'admin login'
    $accessToken = ($login.Body | ConvertFrom-Json).data.accessToken
    if ([string]::IsNullOrWhiteSpace($accessToken)) {
        throw 'Admin login did not return an access token'
    }
    $authorized = @{Authorization = "Bearer $accessToken"}

    $metrics = Invoke-Http `
        -Method GET `
        -Uri "$BaseUrl/actuator/prometheus" `
        -Headers $authorized
    Assert-Status -Response $metrics -ExpectedStatus 200 -Step 'Prometheus endpoint'
    if ($metrics.Body -notmatch 'jvm_memory_used_bytes') {
        throw 'Prometheus endpoint did not expose JVM metrics'
    }
    $results.Add([pscustomobject]@{step = 'prometheus'; status = 'PASS'})

    Invoke-Compose -ComposeArguments @('stop', 'python-ai')
    $pythonStopped = $true
    $pythonDown = Wait-HttpStatus `
        -Uri "$BaseUrl/actuator/health/readiness" `
        -ExpectedStatus 503 `
        -TimeoutSeconds 30
    $liveness = Invoke-Http -Method GET -Uri "$BaseUrl/actuator/health/liveness"
    Assert-Status -Response $liveness -ExpectedStatus 200 -Step 'liveness during Python outage'
    $results.Add([pscustomobject]@{
        step = 'python-outage'
        status = 'PASS'
        detectionMs = $pythonDown.ElapsedMs
    })
    Start-DependencyAndWait -Service 'python-ai'
    $pythonStopped = $false

    Invoke-Compose -ComposeArguments @('stop', 'redis')
    $redisStopped = $true
    Wait-HttpStatus `
        -Uri "$BaseUrl/actuator/health/readiness" `
        -ExpectedStatus 503 `
        -TimeoutSeconds 30 | Out-Null
    $redisRequest = Invoke-Http `
        -Method GET `
        -Uri "$BaseUrl/api/v1/system/status" `
        -Headers ($authorized + @{'X-Request-ID' = 'req_p7_redis_outage_0001'})
    Assert-Status -Response $redisRequest -ExpectedStatus 503 -Step 'protected API during Redis outage'
    $redisErrorCode = ($redisRequest.Body | ConvertFrom-Json).error.code
    if ($redisErrorCode -ne 'AUTH_STATE_UNAVAILABLE') {
        throw "Redis outage expected AUTH_STATE_UNAVAILABLE but received ${redisErrorCode}: $($redisRequest.Body)"
    }
    $results.Add([pscustomobject]@{step = 'redis-outage'; status = 'PASS'})
    Start-DependencyAndWait -Service 'redis'
    $redisStopped = $false

    $mysqlRequestId = 'req_p7_mysql_outage_no_python_0001'
    $pythonLogSince = [DateTime]::UtcNow.ToString('o')
    Invoke-Compose -ComposeArguments @('stop', 'mysql')
    $mysqlStopped = $true
    Wait-HttpStatus `
        -Uri "$BaseUrl/actuator/health/readiness" `
        -ExpectedStatus 503 `
        -TimeoutSeconds 30 | Out-Null
    $mysqlRequest = Invoke-Http `
        -Method POST `
        -Uri "$BaseUrl/api/v1/conversations" `
        -Headers ($authorized + @{'X-Request-ID' = $mysqlRequestId}) `
        -Body '{"title":"P7 MySQL outage drill"}' `
        -TimeoutSeconds 20
    Assert-Status -Response $mysqlRequest -ExpectedStatus 503 -Step 'business write during MySQL outage'
    if (($mysqlRequest.Body | ConvertFrom-Json).error.code -ne 'DATASTORE_UNAVAILABLE') {
        throw 'MySQL outage did not return DATASTORE_UNAVAILABLE'
    }
    $pythonLogs = (& docker compose logs --since $pythonLogSince python-ai 2>&1) -join "`n"
    if ($pythonLogs -match [regex]::Escape($mysqlRequestId)) {
        throw 'MySQL outage request reached Python before the Java business write succeeded'
    }
    $results.Add([pscustomobject]@{
        step = 'mysql-outage'
        status = 'PASS'
        javaResponseMs = $mysqlRequest.ElapsedMs
        pythonCalled = $false
    })
    Start-DependencyAndWait -Service 'mysql'
    $mysqlStopped = $false
} finally {
    Set-Location -LiteralPath $repoRoot
    if ($pythonStopped) {
        Invoke-Compose -ComposeArguments @('start', 'python-ai')
    }
    if ($redisStopped) {
        Invoke-Compose -ComposeArguments @('start', 'redis')
    }
    if ($mysqlStopped) {
        Invoke-Compose -ComposeArguments @('start', 'mysql')
    }
    try {
        Wait-HttpStatus `
            -Uri "$BaseUrl/actuator/health/readiness" `
            -ExpectedStatus 200 `
            -TimeoutSeconds $RecoveryTimeoutSeconds | Out-Null
    } finally {
        Set-Location -LiteralPath $previousLocation
    }
}

[pscustomobject]@{
    status = 'PASS'
    checks = $results
} | ConvertTo-Json -Depth 4
