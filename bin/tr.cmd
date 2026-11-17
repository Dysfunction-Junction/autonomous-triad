@echo off

@rem Tags: agent, cli, ops-runbook
@rem Links: bin/tr.ps1, triad/agent/cli.py
@rem Queries: "how do I start the agent from cmd", "what happens when the engine is missing"

setlocal
set "ENGINE="
if defined TRIAD_ROOT if exist "%TRIAD_ROOT%\triad\triad_engine.py" set "ENGINE=%TRIAD_ROOT%\triad\triad_engine.py"
if not defined ENGINE if exist "%~dp0..\triad\triad_engine.py" set "ENGINE=%~dp0..\triad\triad_engine.py"
if not defined ENGINE if exist "%USERPROFILE%\.agents\triad\triad_engine.py" set "ENGINE=%USERPROFILE%\.agents\triad\triad_engine.py"
if not defined ENGINE (
  echo triad_engine.py not found. Set TRIAD_ROOT or run scripts\install.ps1. 1>&2
  exit /b 1
)
python "%ENGINE%" agent %*
exit /b %ERRORLEVEL%
