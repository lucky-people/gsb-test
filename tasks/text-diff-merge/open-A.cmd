@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\tools\open-run.ps1" -TaskDir "%~dp0." -Run A %*
