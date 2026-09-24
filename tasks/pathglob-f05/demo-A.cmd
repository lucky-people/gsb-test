@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\tools\run-demo.ps1" -TaskDir "%~dp0." -Run A %*
