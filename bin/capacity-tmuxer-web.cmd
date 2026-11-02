@echo off
rem capacity-tmuxer-web (cmd.exe): starts the Chinese web UI.
call "%~dp0capacity-tmuxer.cmd" web %*
exit /b %errorlevel%
