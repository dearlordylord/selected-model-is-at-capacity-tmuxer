@echo off
rem capacity-tmuxer (cmd.exe): runs the Python version, no bash needed.
rem   capacity-tmuxer.cmd 43 44        watch sessions
rem   capacity-tmuxer.cmd web --auto   Chinese web UI
setlocal
set PYTHONUTF8=1
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0capacity-tmuxer.py" %*
) else (
  py -3 "%~dp0capacity-tmuxer.py" %*
)
exit /b %errorlevel%
