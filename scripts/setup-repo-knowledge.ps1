# Tags: tooling, local-llm, ops-runbook
# Links: scripts/watch-repo-knowledge.ps1, docs/REPO_KNOWLEDGE.md
# Queries: "how do I install automatic local repository indexing"
param(
    [string[]]$Repos = @((Split-Path -Parent $PSScriptRoot)),
    [switch]$NoTask
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$indexScript = Join-Path $repoRoot 'triad\repo_index.py'
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$backgroundPython = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $backgroundPython)) { throw 'pythonw.exe is required for hidden scheduled workers.' }
$stateDir = Join-Path $env:USERPROFILE '.local\share\repo-knowledge'
$binDir = Join-Path $env:USERPROFILE '.local\bin'
New-Item -ItemType Directory -Path $stateDir, $binDir -Force | Out-Null
foreach ($repoPath in $Repos) {
    & $pythonPath $indexScript register --repo $repoPath --state-dir $stateDir
    if ($LASTEXITCODE -ne 0) { throw "Repository registration failed: $repoPath" }
}
$configPath = Join-Path $stateDir 'config.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config | Add-Member -NotePropertyName python_path -NotePropertyValue $pythonPath -Force
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding utf8
$commandText = '@echo off' + [Environment]::NewLine + '"' + $pythonPath + '" "' + $indexScript + '" %*' + [Environment]::NewLine
Set-Content -LiteralPath (Join-Path $binDir 'repo-knowledge.cmd') -Value $commandText -Encoding ascii
$psCommand = '& ''' + $pythonPath.Replace("'", "''") + ''' ''' + $indexScript.Replace("'", "''") + ''' @args' + [Environment]::NewLine + 'exit $LASTEXITCODE'
Set-Content -LiteralPath (Join-Path $binDir 'repo-knowledge.ps1') -Value $psCommand -Encoding utf8
$cartographCmd = Join-Path $stateDir 'cartograph\node_modules\.bin\cartograph.cmd'
if (Test-Path -LiteralPath $cartographCmd) {
    Set-Content -LiteralPath (Join-Path $binDir 'repo-map.cmd') -Value ('@echo off' + [Environment]::NewLine + 'call "' + $cartographCmd + '" %*') -Encoding ascii
}
if (-not $NoTask) {
    $startScript = Join-Path $PSScriptRoot 'start-repo-embedding.ps1'
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    foreach ($indexMode in @('watch', 'backfill')) {
        $taskName = if ($indexMode -eq 'watch') { 'RepoKnowledgeIndexer' } else { 'RepoKnowledgeBackfill' }
        $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existing -and -not @($existing.Actions | Where-Object { $_.Arguments -like "*$repoRoot*" }).Count) {
            throw "A different task already owns $taskName; no task was changed."
        }
        if ($existing -and $existing.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $taskName
            $stopDeadline = (Get-Date).AddSeconds(10)
            while ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running' -and (Get-Date) -lt $stopDeadline) {
                Start-Sleep -Milliseconds 200
            }
            if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') { throw "$taskName has not stopped; retry setup after it exits." }
        }
        # Python is tracked directly so task stop cannot leave an orphan watcher.
        $startAction = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $startScript + '"') -WorkingDirectory $repoRoot
        $workerAction = New-ScheduledTaskAction -Execute $backgroundPython -Argument ('"' + $indexScript + '" ' + $indexMode + ' --state-dir "' + $stateDir + '" --config "' + $configPath + '" --interval 15') -WorkingDirectory $repoRoot
        $actions = if ($indexMode -eq 'watch') { @($startAction, $workerAction) } else { @($workerAction) }
        Register-ScheduledTask -TaskName $taskName -Action $actions -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'Local per-repository tags, embeddings and hybrid search; no external APIs.' -Force | Out-Null
        Start-ScheduledTask -TaskName $taskName
    }
}
Write-Output "Ready: $binDir\repo-knowledge.cmd"
Write-Output "Configuration: $configPath"
