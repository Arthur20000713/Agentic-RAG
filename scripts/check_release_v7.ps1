[CmdletBinding()]
param(
    [string]$PythonPath = '',
    [string]$JdkHome = '',
    [string]$OutputDir = '.tmp_tests\v7-release',
    [string]$BaseUrl = 'http://127.0.0.1:8080',
    [switch]$SkipJava,
    [switch]$SkipPython,
    [switch]$SkipStatic,
    [switch]$SkipCompose,
    [switch]$SkipResilience,
    [switch]$SkipImageScan,
    [switch]$IncludePerformance,
    [double]$PerformanceDurationSeconds = 300,
    [string]$AdminUsername = 'admin',
    [string]$AdminPassword = 'p3-test-admin-password'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $root '.venv\Scripts\python.exe'
}
if ([string]::IsNullOrWhiteSpace($JdkHome)) {
    $jdkRoot = Join-Path $root '.tmp\p2-tools\jdk17'
    $bundledJdk = Get-ChildItem -LiteralPath $jdkRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
        Select-Object -First 1
    $JdkHome = if ($null -ne $bundledJdk) { $bundledJdk.FullName } else { $jdkRoot }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable not found: $PythonPath"
}
if (-not $SkipJava -and -not (Test-Path -LiteralPath (Join-Path $JdkHome 'bin\java.exe'))) {
    throw "JDK 17 not found: $JdkHome"
}
if ($PerformanceDurationSeconds -le 0) {
    throw 'PerformanceDurationSeconds must be greater than zero'
}

$resolvedOutputDir = if ([IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $root $OutputDir
}
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null
$summaryPath = Join-Path $resolvedOutputDir 'release-summary.json'
$steps = [System.Collections.Generic.List[object]]::new()
$skippedSteps = [System.Collections.Generic.List[string]]::new()

function Invoke-ReleaseStep {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $safeName = $Name -replace '[^A-Za-z0-9_.-]', '_'
    $logPath = Join-Path $resolvedOutputDir "$safeName.log"
    Write-Host "== $Name =="
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $output | Out-File -LiteralPath $logPath -Encoding utf8
    $steps.Add([pscustomobject]@{
        name = $Name
        status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
        exitCode = $exitCode
        log = $logPath
    })
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode. See $logPath"
    }
}

function Invoke-StaticChecks {
    $ErrorActionPreference = 'Continue'
    $logPath = Join-Path $resolvedOutputDir 'static-contracts.log'
    $messages = [System.Collections.Generic.List[string]]::new()
    $failed = $false

    $jsFiles = & rg --files -g '*.js'
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to enumerate JavaScript files with rg'
    }
    foreach ($file in $jsFiles) {
        $output = & node --check $file 2>&1
        if ($LASTEXITCODE -ne 0) {
            $failed = $true
            $messages.Add("node --check failed: $file")
            foreach ($line in $output) { $messages.Add([string]$line) }
        }
    }

    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'scripts') -Filter '*.ps1') {
        $tokens = $null
        $errors = $null
        [Management.Automation.Language.Parser]::ParseFile(
            $file.FullName,
            [ref]$tokens,
            [ref]$errors
        ) | Out-Null
        if ($errors.Count -gt 0) {
            $failed = $true
            foreach ($parseError in $errors) {
                $messages.Add("$($file.Name): $($parseError.Message)")
            }
        }
    }

    $diffOutput = & git diff --check 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
        foreach ($line in $diffOutput) { $messages.Add([string]$line) }
    }
    if (-not $failed) {
        $messages.Add("PASS: $($jsFiles.Count) JavaScript files, PowerShell parser, git diff --check")
    }
    $messages | Out-File -LiteralPath $logPath -Encoding utf8
    $steps.Add([pscustomobject]@{
        name = 'static-contracts'
        status = if ($failed) { 'FAIL' } else { 'PASS' }
        exitCode = if ($failed) { 1 } else { 0 }
        log = $logPath
    })
    if ($failed) {
        throw "Static checks failed. See $logPath"
    }
}

Push-Location $root
try {
    if (-not $SkipJava) {
        Invoke-ReleaseStep -Name 'java-clean-verify' -FilePath 'powershell.exe' -Arguments @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            (Join-Path $root 'scripts\check_p2_java.ps1'),
            '-JdkHome', $JdkHome,
            '-OutputDir', (Join-Path $resolvedOutputDir 'java')
        )
    } else {
        $skippedSteps.Add('java-clean-verify')
    }
    if (-not $SkipPython) {
        Invoke-ReleaseStep -Name 'python-full-pytest' -FilePath $PythonPath -Arguments @(
            '-m', 'pytest', '-q'
        )
    } else {
        $skippedSteps.Add('python-full-pytest')
    }
    if (-not $SkipStatic) {
        Invoke-StaticChecks
    } else {
        $skippedSteps.Add('static-contracts')
    }

    $env:MYSQL_PASSWORD = 'p7-test-mysql-password'
    $env:MYSQL_ROOT_PASSWORD = 'p7-test-root-password'
    $env:REDIS_PASSWORD = 'p7-test-redis-password'
    $env:AI_SERVICE_TOKEN = 'p7-test-ai-service-token-32-characters'
    $env:JWT_SECRET = 'p7-test-jwt-secret-at-least-64-characters-for-local-release-only-0001'
    $env:BOOTSTRAP_ADMIN_USERNAME = $AdminUsername
    $env:BOOTSTRAP_ADMIN_PASSWORD = $AdminPassword

    if (-not $SkipCompose) {
        Invoke-ReleaseStep -Name 'compose-build-health' -FilePath 'powershell.exe' -Arguments @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            (Join-Path $root 'scripts\check_p2_compose.ps1'),
            '-OutputDir', (Join-Path $resolvedOutputDir 'compose')
        )
    } else {
        $skippedSteps.Add('compose-build-health')
    }
    if (-not $SkipResilience) {
        Invoke-ReleaseStep -Name 'resilience-drills' -FilePath 'powershell.exe' -Arguments @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            (Join-Path $root 'scripts\check_p7_resilience.ps1'),
            '-BaseUrl', $BaseUrl
        )
    } else {
        $skippedSteps.Add('resilience-drills')
    }

    $securityArguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'scripts\check_p7_security.ps1'),
        '-PythonPath', $PythonPath,
        '-OutputDir', (Join-Path $resolvedOutputDir 'security')
    )
    if ($SkipImageScan) {
        $securityArguments += '-SkipImageScan'
        $skippedSteps.Add('container-image-scan')
    }
    Invoke-ReleaseStep -Name 'security-gate' -FilePath 'powershell.exe' -Arguments $securityArguments

    if ($IncludePerformance) {
        Invoke-ReleaseStep -Name 'performance-business-stub' -FilePath $PythonPath -Arguments @(
            'scripts\benchmark_p7.py', '--profile', 'business-stub',
            '--base-url', $BaseUrl,
            '--duration-seconds', $PerformanceDurationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
            '--output', (Join-Path $resolvedOutputDir 'performance-business-stub.json')
        )
        Invoke-ReleaseStep -Name 'performance-ai-stub' -FilePath $PythonPath -Arguments @(
            'scripts\benchmark_p7.py', '--profile', 'ai-stub',
            '--base-url', $BaseUrl,
            '--duration-seconds', $PerformanceDurationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
            '--output', (Join-Path $resolvedOutputDir 'performance-ai-stub.json')
        )
    } else {
        $skippedSteps.Add('performance-profiles-not-requested')
    }

    [ordered]@{
        status = 'PASS'
        generatedAt = [DateTime]::UtcNow.ToString('o')
        steps = $steps
        skippedSteps = $skippedSteps
        notes = @(
            'Image scanning only skips when -SkipImageScan is explicit.',
            'Performance profiles are stub-only here; real AI requires a separate explicit benchmark invocation.'
        )
    } | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $summaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $summaryPath
} catch {
    [ordered]@{
        status = 'FAIL'
        generatedAt = [DateTime]::UtcNow.ToString('o')
        error = $_.Exception.Message
        steps = $steps
        skippedSteps = $skippedSteps
    } | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $summaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $summaryPath
    exit 1
} finally {
    Pop-Location
}
