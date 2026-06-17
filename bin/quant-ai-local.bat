@echo off
setlocal
set ROOT=%~dp0..
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\bin\quant-ai-local.ps1" %*

