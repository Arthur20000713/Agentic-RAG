param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8001,
    [string]$Settings = "config\settings.yaml",
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python virtualenv not found: $Python"
    exit 2
}

Push-Location $RepoRoot
try {
    if (-not $SkipDoctor) {
        & $Python scripts\doctor_v6.py --settings $Settings --port $Port
        if ($LASTEXITCODE -ne 0) {
            Write-Error "V6 runtime doctor failed. Fix the reported issue or rerun with -SkipDoctor only for debugging."
            exit $LASTEXITCODE
        }
    }

    Write-Host "Starting Livestock Agentic RAG at http://$HostName`:$Port/app"
    & $Python -m uvicorn backend.app.main:app --host $HostName --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

