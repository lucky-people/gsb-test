[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run
)

$ErrorActionPreference = 'Stop'
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$runDir = Join-Path $taskDirResolved $Run
$codexHomeRoot = Join-Path $taskDirResolved ".codex-home\$Run"

if (Test-Path -LiteralPath $runDir) {
    try {
        Remove-Item -LiteralPath $runDir -Recurse -Force -ErrorAction Stop
    } catch {
        Write-Warning "Could not remove $runDir. Close any running Codex windows and try again. $($_.Exception.Message)"
    }
}
if (Test-Path -LiteralPath $codexHomeRoot) {
    Get-ChildItem -LiteralPath $codexHomeRoot -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Reset $Run done."
