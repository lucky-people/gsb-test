@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\tools\run-and-upload.ps1" -TaskDir "%~dp0." -Run B -RecordRegion right %*
