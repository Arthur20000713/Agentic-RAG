[CmdletBinding()]
param(
    [string]$PythonPath = '',
    [string]$OutputDir = '.tmp_tests\p7-security',
    [ValidateSet('auto', 'docker-scout', 'trivy')]
    [string]$Scanner = 'auto',
    [string[]]$Images = @(
        'livestock-enterprise-platform-java-app:latest',
        'livestock-enterprise-platform-python-ai:latest'
    ),
    [string]$TrivyImage = 'aquasec/trivy:0.66.0',
    [switch]$SkipImageScan
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $root '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable not found: $PythonPath"
}

$resolvedOutputDir = if ([IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $root $OutputDir
}
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null
$sourceReport = Join-Path $resolvedOutputDir 'source-secrets.json'
$summaryPath = Join-Path $resolvedOutputDir 'security-summary.json'
$results = [System.Collections.Generic.List[object]]::new()

function Invoke-CapturedCommand {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$LogPath
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $output | Out-File -LiteralPath $LogPath -Encoding utf8
    return [pscustomobject]@{ExitCode = $exitCode; Output = $output}
}

function Get-TrivyFindingCount {
    param([Parameter(Mandatory)][string]$ReportPath)

    if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) {
        return $null
    }
    try {
        $report = Get-Content -Raw -LiteralPath $ReportPath | ConvertFrom-Json
    } catch {
        return $null
    }
    $count = 0
    foreach ($result in @($report.Results)) {
        $vulnerabilityProperty = $result.PSObject.Properties['Vulnerabilities']
        if ($null -ne $vulnerabilityProperty) {
            $count += @($vulnerabilityProperty.Value).Count
        }
    }
    return $count
}

function Invoke-ScoutScan {
    param(
        [Parameter(Mandatory)][string]$Image,
        [Parameter(Mandatory)][string]$SafeName
    )

    $reportPath = Join-Path $resolvedOutputDir "$SafeName.scout.sarif.json"
    $logPath = Join-Path $resolvedOutputDir "$SafeName.scout.log"
    $run = Invoke-CapturedCommand -FilePath 'docker' -LogPath $logPath -Arguments @(
        'scout', 'cves', '--format', 'sarif', '--only-fixed',
        '--only-severity', 'critical,high', '--exit-code',
        '--output', $reportPath, "local://$Image"
    )
    if ($run.ExitCode -eq 0) {
        return [pscustomobject]@{Available = $true; Passed = $true; Findings = 0; Report = $reportPath; Log = $logPath}
    }
    if ($run.ExitCode -eq 2 -and (Test-Path -LiteralPath $reportPath)) {
        return [pscustomobject]@{Available = $true; Passed = $false; Findings = $null; Report = $reportPath; Log = $logPath}
    }
    return [pscustomobject]@{Available = $false; Passed = $false; Findings = $null; Report = $reportPath; Log = $logPath}
}

function Invoke-TrivyScan {
    param(
        [Parameter(Mandatory)][string]$Image,
        [Parameter(Mandatory)][string]$SafeName
    )

    $inspectLog = Join-Path $resolvedOutputDir "$SafeName.inspect.log"
    $inspect = Invoke-CapturedCommand -FilePath 'docker' -LogPath $inspectLog -Arguments @('image', 'inspect', $Image)
    if ($inspect.ExitCode -ne 0) {
        throw "Local image not found: $Image"
    }

    $trivyInspectLog = Join-Path $resolvedOutputDir 'trivy-image.inspect.log'
    $trivyInspect = Invoke-CapturedCommand -FilePath 'docker' -LogPath $trivyInspectLog -Arguments @('image', 'inspect', $TrivyImage)
    if ($trivyInspect.ExitCode -ne 0) {
        $pullLog = Join-Path $resolvedOutputDir 'trivy-image.pull.log'
        $pull = Invoke-CapturedCommand -FilePath 'docker' -LogPath $pullLog -Arguments @('pull', $TrivyImage)
        if ($pull.ExitCode -ne 0) {
            throw "Unable to pull Trivy scanner image. See $pullLog"
        }
    }

    $cacheDir = Join-Path $resolvedOutputDir 'trivy-cache'
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
    $reportPath = Join-Path $resolvedOutputDir "$SafeName.trivy.json"
    $logPath = Join-Path $resolvedOutputDir "$SafeName.trivy.log"
    $run = Invoke-CapturedCommand -FilePath 'docker' -LogPath $logPath -Arguments @(
        'run', '--rm',
        '--mount', "type=bind,source=$resolvedOutputDir,target=/reports",
        '--mount', "type=bind,source=$cacheDir,target=/root/.cache",
        '--mount', 'type=bind,source=//var/run/docker.sock,target=/var/run/docker.sock',
        $TrivyImage,
        'image', '--db-repository', 'ghcr.io/aquasecurity/trivy-db:2',
        '--timeout', '30m', '--scanners', 'vuln', '--ignore-unfixed',
        '--severity', 'HIGH,CRITICAL', '--exit-code', '1',
        '--format', 'json', '--output', "/reports/$SafeName.trivy.json", $Image
    )
    $findingCount = Get-TrivyFindingCount -ReportPath $reportPath
    if ($null -eq $findingCount) {
        throw "Trivy did not produce a valid report for $Image. See $logPath"
    }
    return [pscustomobject]@{
        Available = $true
        Passed = $findingCount -eq 0
        Findings = $findingCount
        Report = $reportPath
        Log = $logPath
        ExitCode = $run.ExitCode
    }
}

Push-Location $root
try {
    & $PythonPath 'scripts\check_p7_security.py' '--root' $root '--json-output' $sourceReport
    if ($LASTEXITCODE -ne 0) {
        throw "Source secret scan failed. See $sourceReport"
    }
    $results.Add([pscustomobject]@{
        target = 'source'
        scanner = 'redaction-safe-source-scan'
        status = 'PASS'
        findings = 0
        report = $sourceReport
    })

    if ($SkipImageScan) {
        $results.Add([pscustomobject]@{
            target = 'container-images'
            scanner = 'none'
            status = 'SKIPPED_EXPLICITLY'
            findings = $null
            report = $null
        })
    } else {
        foreach ($image in $Images) {
            $safeName = $image -replace '[^A-Za-z0-9_.-]', '_'
            $scan = $null
            $usedScanner = $Scanner
            if ($Scanner -in @('auto', 'docker-scout')) {
                $scan = Invoke-ScoutScan -Image $image -SafeName $safeName
                if (-not $scan.Available -and $Scanner -eq 'docker-scout') {
                    throw "Docker Scout is unavailable for $image. See $($scan.Log)"
                }
            }
            if ($null -eq $scan -or -not $scan.Available) {
                $usedScanner = 'trivy'
                $scan = Invoke-TrivyScan -Image $image -SafeName $safeName
            } else {
                $usedScanner = 'docker-scout'
            }
            $status = if ($scan.Passed) { 'PASS' } else { 'FAIL' }
            $results.Add([pscustomobject]@{
                target = $image
                scanner = $usedScanner
                status = $status
                findings = $scan.Findings
                report = $scan.Report
                log = $scan.Log
                policy = 'no fixable HIGH or CRITICAL vulnerabilities'
            })
            if (-not $scan.Passed) {
                throw "Image vulnerability gate failed for $image. See $($scan.Report)"
            }
        }
    }

    [ordered]@{
        status = 'PASS'
        generatedAt = [DateTime]::UtcNow.ToString('o')
        results = $results
    } | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $summaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $summaryPath
} catch {
    [ordered]@{
        status = 'FAIL'
        generatedAt = [DateTime]::UtcNow.ToString('o')
        error = $_.Exception.Message
        results = $results
    } | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $summaryPath -Encoding utf8
    Get-Content -Raw -LiteralPath $summaryPath
    exit 1
} finally {
    Pop-Location
}
