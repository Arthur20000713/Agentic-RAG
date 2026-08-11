[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$JdkHome,
    [string]$OutputDir = ".tmp_tests\p2_java_verify"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$JavaApp = Join-Path $Root "java-app"
$ResolvedJdk = Resolve-Path -LiteralPath $JdkHome
$JavaExecutable = Join-Path $ResolvedJdk "bin\java.exe"
if (-not (Test-Path -LiteralPath $JavaExecutable)) {
    throw "Java 17 executable not found: $JavaExecutable"
}

$ResolvedOutputDir = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $ResolvedOutputDir | Out-Null
$LogPath = Join-Path $ResolvedOutputDir "maven_verify.log"
$SummaryPath = Join-Path $ResolvedOutputDir "summary.json"

$env:JAVA_HOME = $ResolvedJdk.Path
$env:PATH = "$(Join-Path $ResolvedJdk 'bin');$env:PATH"

Push-Location $JavaApp
try {
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = & ".\mvnw.cmd" "-B" "-ntp" "clean" "verify" 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
}
finally {
    Pop-Location
}

$Output | Out-File -LiteralPath $LogPath -Encoding utf8
[ordered]@{
    status = if ($ExitCode -eq 0) { "passed" } else { "failed" }
    exit_code = $ExitCode
    java_home = $ResolvedJdk.Path
    command = "mvnw.cmd -B -ntp clean verify"
    log = $LogPath
} | ConvertTo-Json -Depth 4 | Out-File -LiteralPath $SummaryPath -Encoding utf8

Get-Content -Raw -LiteralPath $SummaryPath
exit $ExitCode
