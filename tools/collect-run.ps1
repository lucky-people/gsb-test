[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run
)

$ErrorActionPreference = 'Stop'
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$runDir = Join-Path $taskDirResolved $Run
$codexHome = Join-Path $taskDirResolved ".codex-home\$Run"
$metaPath = Join-Path $taskDirResolved 'meta.json'

if (-not (Test-Path -LiteralPath $metaPath)) {
    throw "Missing meta.json: $metaPath"
}
$meta = Get-Content -Raw -LiteralPath $metaPath | ConvertFrom-Json

$sessionsRoot = Join-Path $codexHome 'sessions'
if (-not (Test-Path -LiteralPath $sessionsRoot)) {
    throw "No session directory: $sessionsRoot"
}

$rollout = Get-ChildItem -LiteralPath $sessionsRoot -Recurse -Filter 'rollout-*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $rollout) {
    throw "No rollout file found under $sessionsRoot"
}

$sessionId = $null
foreach ($line in Get-Content -LiteralPath $rollout.FullName) {
    try {
        $obj = $line | ConvertFrom-Json
    } catch {
        continue
    }
    if ($obj.type -eq 'session_meta' -and $obj.payload.session_id) {
        $sessionId = $obj.payload.session_id
        break
    }
}
if (-not $sessionId) {
    throw "Could not find session_id in $($rollout.FullName)"
}

$resultDir = Join-Path $taskDirResolved "results\$Run"
New-Item -ItemType Directory -Path $resultDir -Force | Out-Null
$trajectoryPath = Join-Path $resultDir "$sessionId.jsonl"
Copy-Item -LiteralPath $rollout.FullName -Destination $trajectoryPath -Force

$promptPath = Join-Path $taskDirResolved 'prompt.md'
if (Test-Path -LiteralPath $promptPath) {
    Copy-Item -LiteralPath $promptPath -Destination (Join-Path $resultDir 'prompt.md') -Force
}

$initialSha = $meta.initial_sha
if (-not $initialSha) {
    throw "meta.json missing initial_sha"
}

git -C $runDir add -A
$tree = (git -C $runDir write-tree).Trim()
$artifactSha = (git -C $runDir commit-tree $tree -p $initialSha -m "artifact $Run").Trim()
git -C $runDir update-ref "refs/heads/task/$taskId/$Run" $artifactSha
git -C $runDir reset --hard $artifactSha | Out-Null

$summary = [ordered]@{
    task_id = $taskId
    run = $Run
    language_framework = $meta.language_framework
    initial_sha = $initialSha
    initial_permalink = $meta.initial_permalink
    session_id = $sessionId
    trajectory_file = "results/$Run/$sessionId.jsonl"
    artifact_sha = $artifactSha
    artifact_branch = "task/$taskId/$Run"
    collected_at = (Get-Date).ToString('o')
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resultDir 'summary.json') -Encoding UTF8

Write-Host "Collected $Run"
Write-Host "SessionID: $sessionId"
Write-Host "Trajectory: $trajectoryPath"
Write-Host "Artifact SHA: $artifactSha"
Write-Host "Artifact branch: task/$taskId/$Run"
