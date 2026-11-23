# Tags: tooling, local-llm, ops-runbook
# Links: scripts/watch-repo-knowledge.ps1, docs/REPO_KNOWLEDGE.md
# Queries: "how is the local embedding runtime started"
$ErrorActionPreference = 'Stop'
$runtimeDir = Join-Path $env:LOCALAPPDATA 'llama.cpp'
$runtimeExe = Join-Path $runtimeDir 'llama-server.exe'
$modelPath = Join-Path $runtimeDir 'models\nomic-embed-text.gguf'
$runtimeMutex = New-Object System.Threading.Mutex($false, 'Global\LlamaCppKeepAlive-embed')
if (-not $runtimeMutex.WaitOne(0)) { $runtimeMutex.Dispose(); exit 0 }
try {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8081/health' -TimeoutSec 3
        if ($health.status -eq 'ok') { exit 0 }
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 503) { exit 0 }
    }
    if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8081 is occupied; no process was stopped.'
    }
    if (-not (Test-Path -LiteralPath $runtimeExe) -or -not (Test-Path -LiteralPath $modelPath)) {
        throw 'Existing llama.cpp/nomic model missing; no model was downloaded.'
    }
    $runtimeArgs = '-m "' + $modelPath + '" --alias nomic-embed-text --host 127.0.0.1 --port 8081 --gpu-layers 0 --embeddings --pooling mean --ctx-size 2048 --batch-size 2048 --ubatch-size 2048 --threads 4 --log-file "' + (Join-Path $runtimeDir 'embed.stdout.log') + '"'
    $runtimeProcess = Start-Process -FilePath $runtimeExe -ArgumentList $runtimeArgs -WorkingDirectory $runtimeDir -WindowStyle Hidden -PassThru
    $runtimeProcess.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
} finally {
    $runtimeMutex.ReleaseMutex()
    $runtimeMutex.Dispose()
}

