param(
    [Parameter(Mandatory = $true)]
    [string]$Batch,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$GoldenSet = "tests\fixtures\real_golden_v4_2\all.json"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    [Console]::Error.WriteLine("Project virtual environment not found: $Python")
    exit 2
}

if (-not $env:RAG_SERVER_PATH) {
    [Console]::Error.WriteLine("RAG_SERVER_PATH is required for real batch regression. Set it to the sibling RAG-SERVER path.")
    exit 2
}

if (-not (Test-Path (Join-Path $Root $Batch))) {
    [Console]::Error.WriteLine("Batch file not found: $Batch")
    exit 2
}

& $Python scripts\check_v4_2.py --stage full
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python -m pytest -m rag_server -q
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python scripts\run_eval.py --mode real --optional --batch $Batch --golden-set $GoldenSet --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python scripts\check_v4_2.py --stage gate --report (Join-Path $OutputDir "eval_result.json") --batch $Batch
exit $LASTEXITCODE
