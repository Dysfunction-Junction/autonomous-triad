# Tags: verification, tooling, ops-runbook
# Links: scripts/install.ps1, triad/cli/doctor.py
# Queries: "how do I check the install is healthy", "what does verify run"

<#
.SYNOPSIS
    Runs automated verification of the Triad installation.
#>

$ErrorActionPreference = "Stop"

Write-Host "Running Triad verification..." -ForegroundColor Cyan
triad doctor
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nTriad advisory council is healthy (at least one enabled advisor is usable)." -ForegroundColor Green
} else {
    Write-Host "`nTriad verification reported a problem: no enabled advisor is currently usable." -ForegroundColor Red
}
exit $LASTEXITCODE
