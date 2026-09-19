[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run,
    [string]$RemoteUrl
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$runDir = Join-Path $taskDirResolved $Run

if (-not $RemoteUrl) {
    $RemoteUrl = (git -C $repoRoot remote get-url origin 2>$null)
}
if (-not $RemoteUrl) {
    throw "No remote URL. Pass -RemoteUrl or configure origin in $repoRoot."
}

git -C $runDir remote remove origin 2>$null
git -C $runDir remote add origin $RemoteUrl

$branch = "task/$taskId/$Run"
git -C $runDir push origin "HEAD:refs/heads/$branch"

$localSha = (git -C $runDir rev-parse HEAD).Trim()
$remoteLine = git -C $runDir ls-remote origin "refs/heads/$branch"
$remoteSha = ($remoteLine -split '\s+')[0]

Write-Host "Local SHA:  $localSha"
Write-Host "Remote SHA: $remoteSha"

if ($localSha -ne $remoteSha) {
    throw "Remote verification failed."
}
