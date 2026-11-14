# PowerShell wrapper for the Triad agent REPL.
# Resolution order: TRIAD_ROOT env -> repo checkout next to this script -> ~/.agents install
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

$candidates = @()
if ($env:TRIAD_ROOT) { $candidates += (Join-Path $env:TRIAD_ROOT "triad\triad_engine.py") }
$candidates += (Join-Path (Split-Path -Parent $PSScriptRoot) "triad\triad_engine.py")
$candidates += (Join-Path $env:USERPROFILE ".agents\triad\triad_engine.py")

$engine = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $engine) {
    Write-Error "triad_engine.py not found. Set TRIAD_ROOT or run scripts/install.ps1."
    exit 1
}

if ($MyInvocation.ExpectingInput) {
    $input | & python $engine agent @args
} else {
    & python $engine agent @args
}
exit $LASTEXITCODE
