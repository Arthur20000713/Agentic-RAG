[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$OutputDir = ".tmp_tests\v5_release",
    [switch]$IncludeRealRag,
    [switch]$IncludeLocalModel,
    [switch]$IncludeLora,
    [string]$LoraDatasetPath = "data\v5\lora_dataset_splits.json",
    [string]$LoraRegistryPath = "data\v3\model_registry.json",
    [string]$LoraModelId = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonPath)) {
    throw "Python executable not found: $PythonPath"
}

$ResolvedOutputDir = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $ResolvedOutputDir | Out-Null
$Summary = @()

function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $SafeName = $Name -replace "[^A-Za-z0-9_.-]", "_"
    $LogPath = Join-Path $ResolvedOutputDir "$SafeName.log"
    Write-Host "== $Name =="
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = & $PythonPath @Arguments 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    $Output | Out-File -FilePath $LogPath -Encoding utf8
    $script:Summary += [ordered]@{
        name = $Name
        exit_code = $ExitCode
        log = $LogPath
        command = "$PythonPath $($Arguments -join ' ')"
    }
    if ($ExitCode -ne 0) {
        throw "$Name failed with exit code $ExitCode. See $LogPath"
    }
}

Invoke-PythonStep "v5_static_check" @("scripts\check_v5.py", "--stage", "full")
Invoke-PythonStep "pytest_offline" @("-m", "pytest", "-m", "not rag_server and not local_model", "-q")
Invoke-PythonStep "v2_offline_docs_contract" @("scripts\check_v2.py", "--offline", "--frontend-contract", "--docs")
Invoke-PythonStep "v3_full_check" @("scripts\check_v3.py", "--stage", "full")
Invoke-PythonStep "v4_2_full_check" @("scripts\check_v4_2.py", "--stage", "full")

$V5EvalDir = Join-Path $ResolvedOutputDir "v5_eval"
Invoke-PythonStep "v5_eval" @("scripts\run_eval.py", "--mode", "v5", "--optional", "--output-dir", $V5EvalDir)
Invoke-PythonStep "v5_quality_gate" @("scripts\check_v5.py", "--stage", "gate", "--report", (Join-Path $V5EvalDir "eval_result.json"))

if ($IncludeRealRag) {
    if ([string]::IsNullOrWhiteSpace($env:RAG_SERVER_PATH)) {
        throw "IncludeRealRag requires RAG_SERVER_PATH to be set."
    }
    $RealRagDir = Join-Path $ResolvedOutputDir "real_rag_eval"
    Invoke-PythonStep "real_rag_pytest" @("-m", "pytest", "-m", "rag_server", "-q")
    Invoke-PythonStep "real_rag_eval_optional" @("scripts\run_eval.py", "--mode", "real", "--optional", "--output-dir", $RealRagDir)
}

if ($IncludeLocalModel) {
    $LocalModelReport = Join-Path $ResolvedOutputDir "local_model_smoke.json"
    Invoke-PythonStep "local_model_contracts" @("scripts\check_v5.py", "--stage", "local-model")
    Invoke-PythonStep "local_model_required_smoke" @("scripts\run_local_model_smoke.py", "--output", $LocalModelReport)
}

if ($IncludeLora) {
    Invoke-PythonStep "lora_dataset_check" @("scripts\check_lora_dataset.py", "--input", $LoraDatasetPath)
    Invoke-PythonStep "lora_training_dry_run" @("scripts\train_lora_adapter.py", "--config", "config\lora_training.yaml", "--dry-run", "--json")
    if (-not [string]::IsNullOrWhiteSpace($LoraModelId)) {
        Invoke-PythonStep "lora_adapter_eval_optional" @(
            "scripts\evaluate_lora_adapter.py",
            "--registry",
            $LoraRegistryPath,
            "--model-id",
            $LoraModelId,
            "--optional"
        )
    }
}

$SummaryPath = Join-Path $ResolvedOutputDir "release_check_summary.json"
$Summary | ConvertTo-Json -Depth 5 | Out-File -FilePath $SummaryPath -Encoding utf8
Write-Host "V5 release checks passed. Summary: $SummaryPath"
