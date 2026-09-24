@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\tools\push-base.ps1" -TaskDir "%~dp0." %*
