[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [string]$RemoteUrl
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$bundle = Join-Path $taskDirResolved 'baseline.bundle'

if (-not (Test-Path -LiteralPath $bundle)) {
    throw "Missing baseline bundle: $bundle"
}

if (-not $RemoteUrl) {
    $RemoteUrl = (git -C $repoRoot remote get-url origin 2>$null)
}
if (-not $RemoteUrl) {
    throw "No remote URL. Pass -RemoteUrl or configure origin in $repoRoot."
}

$temp = Join-Path $env:TEMP ("gsb-base-push-" + [guid]::NewGuid().ToString('N'))
git clone --branch base --single-branch $bundle $temp | Out-Null

try {
    git -C $temp remote remove origin 2>$null
    git -C $temp remote add origin $RemoteUrl

    $branch = "task/$taskId/base"
    git -C $temp push origin "HEAD:refs/heads/$branch"

    $localSha = (git -C $temp rev-parse HEAD).Trim()
    $remoteLine = git -C $temp ls-remote origin "refs/heads/$branch"
    $remoteSha = ($remoteLine -split '\s+')[0]

    Write-Host "Local SHA:  $localSha"
    Write-Host "Remote SHA: $remoteSha"

    if ($localSha -ne $remoteSha) {
        throw "Remote verification failed."
    }

    $baseUrl = $RemoteUrl -replace '\.git$',''
    Write-Host "Base permalink: $baseUrl/commit/$localSha"
}
finally {
    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
