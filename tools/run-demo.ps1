[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run,
    [string]$DemoScript
)

# Runs the artifact demo for one run inside its workspace, so the screen can be
# recorded by hand. No recording is done here.
#
# ASCII-only script; the demo text itself lives in demos/<task-id>/demo.py and
# is read by Python as UTF-8.

$ErrorActionPreference = 'Stop'

try {
    & chcp.com 65001 | Out-Null
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }
$env:PYTHONIOENCODING = 'utf-8'

$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$runDir = Join-Path $taskDirResolved $Run
if (-not (Test-Path -LiteralPath $runDir)) { throw "Run workspace not found: $runDir" }

if (-not $DemoScript) {
    $DemoScript = Join-Path (Join-Path $PSScriptRoot "demos\$taskId") 'demo.py'
}
if (-not (Test-Path -LiteralPath $DemoScript)) {
    throw "No demo script for task $taskId (looked for $DemoScript)"
}

Write-Host ''
Write-Host ("=== DEMO {0}: {1} ===" -f $Run, $taskId)
Write-Host ("Workspace: {0}" -f $runDir)
Write-Host 'Start your screen recording now if you have not already.'
Write-Host ''

Push-Location -LiteralPath $runDir
try {
    & python -X utf8 $DemoScript
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host ''
Write-Host ("Demo finished (exit code {0})." -f $code)
