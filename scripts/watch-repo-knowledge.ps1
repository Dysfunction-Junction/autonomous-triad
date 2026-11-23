# Tags: tooling, local-llm, ops-runbook
# Links: triad/repo_index.py, scripts/start-repo-embedding.ps1
# Queries: "what runs automatic repository indexing at logon"
$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $env:USERPROFILE '.local\share\repo-knowledge'
$configPath = Join-Path $stateDir 'config.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$indexScript = Join-Path $PSScriptRoot '..\triad\repo_index.py'
# This helper only starts the embedding role. It never restarts the Exocortex daemon.
& (Join-Path $PSScriptRoot 'start-repo-embedding.ps1')
& $config.python_path $indexScript watch --state-dir $stateDir --config $configPath --interval 15
exit $LASTEXITCODE

