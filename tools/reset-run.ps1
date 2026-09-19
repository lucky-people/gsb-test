[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run
)

$ErrorActionPreference = 'Stop'
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$runDir = Join-Path $taskDirResolved $Run
$codexHome = Join-Path $taskDirResolved ".codex-home\$Run"

if (Test-Path -LiteralPath $runDir) {
    Remove-Item -LiteralPath $runDir -Recurse -Force
}
if (Test-Path -LiteralPath $codexHome) {
    Remove-Item -LiteralPath $codexHome -Recurse -Force
}

Write-Host "Reset $Run done."
