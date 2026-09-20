[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run
)

$ErrorActionPreference = 'Stop'
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$runDir = Join-Path $taskDirResolved $Run
$codexHomeRoot = Join-Path $taskDirResolved ".codex-home\$Run"
$currentHomeFile = Join-Path $codexHomeRoot 'current.txt'
if (Test-Path -LiteralPath $currentHomeFile) {
    $codexHome = (Get-Content -Raw -LiteralPath $currentHomeFile).Trim()
} else {
    $codexHome = $codexHomeRoot
}
if (-not (Test-Path -LiteralPath $codexHome)) {
    $latestHome = Get-ChildItem -LiteralPath $codexHomeRoot -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestHome) {
        $codexHome = $latestHome.FullName
    }
}
$metaPath = Join-Path $taskDirResolved 'meta.json'

if (-not (Test-Path -LiteralPath $metaPath)) {
    throw "Missing meta.json: $metaPath"
}
$meta = Get-Content -Raw -Encoding UTF8 -LiteralPath $metaPath | ConvertFrom-Json

$sessionsRoot = Join-Path $codexHome 'sessions'
if (-not (Test-Path -LiteralPath $sessionsRoot)) {
    throw "No session directory: $sessionsRoot"
}

$rollout = Get-ChildItem -LiteralPath $sessionsRoot -Recurse -Filter 'rollout-*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $rollout) {
    throw "No rollout file found under $sessionsRoot"
}

$sessionId = $null
$reader = New-Object System.IO.StreamReader($rollout.FullName)
try {
    for ($i = 0; $i -lt 20; $i++) {
        $line = $reader.ReadLine()
        if ($null -eq $line) {
            break
        }
        if ($line -match '"type"\s*:\s*"session_meta"' -and $line -match '"session_id"\s*:\s*"([^"]+)"') {
            $sessionId = $Matches[1]
            break
        }
    }
}
finally {
    $reader.Dispose()
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

$userTurnCount = 0
$completedCount = 0
$abortedCount = 0
$validityReader = New-Object System.IO.StreamReader($rollout.FullName)
try {
    while (($line = $validityReader.ReadLine()) -ne $null) {
        if ($line -notmatch '"type"') { continue }
        try { $rec = $line | ConvertFrom-Json } catch { continue }
        if ($rec.type -eq 'response_item' -and $rec.payload.type -eq 'message' -and $rec.payload.role -eq 'user') {
            $text = ($rec.payload.content | ForEach-Object { $_.text }) -join ' '
            if ($text -and $text -notmatch '^\s*<(environment_context|user_instructions|turn_aborted)') {
                $userTurnCount++
            }
        }
        if ($rec.type -eq 'event_msg' -and $rec.payload.type -eq 'task_complete') { $completedCount++ }
        if ($rec.type -eq 'event_msg' -and $rec.payload.type -eq 'turn_aborted') { $abortedCount++ }
    }
}
finally {
    $validityReader.Dispose()
}

$runValid = ($userTurnCount -eq 1 -and $completedCount -ge 1 -and $abortedCount -eq 0)
$validityNote = "user turns=$userTurnCount, task_complete=$completedCount, turn_aborted=$abortedCount"
if (-not $runValid) {
    $validityNote = "INVALID run, redo in a fresh window: " + $validityNote
}

$repoUrl = $meta.repo_url
$artifactPermalink = $(if ($repoUrl) { "$($repoUrl.TrimEnd('/'))/commit/$artifactSha" } else { '' })
$initialPermalink = $(if ($meta.initial_permalink) { $meta.initial_permalink } elseif ($repoUrl) { "$($repoUrl.TrimEnd('/'))/commit/$initialSha" } else { '' })
$trajectoryUrl = ''
if ($repoUrl) {
    $rawBase = $repoUrl.TrimEnd('/') -replace '^https://github\.com/', 'https://raw.githubusercontent.com/'
    $trajectoryUrl = "$rawBase/main/tasks/$taskId/results/$Run/$sessionId.jsonl"
}

$videoPath = Join-Path $resultDir "$Run.mp4"
$videoFile = ''
$videoDuration = ''
if (Test-Path -LiteralPath $videoPath) {
    $videoFile = "$Run.mp4"
    try {
        . (Join-Path $PSScriptRoot 'record-screen.ps1')
        $videoInfo = Get-RecordingInfo -Path $videoPath
        $videoDuration = $videoInfo.duration_s
    } catch { }
}

$summary = [ordered]@{
    task_id = $taskId
    run = $Run
    language_framework = $meta.language_framework
    initial_sha = $initialSha
    initial_permalink = $initialPermalink
    session_id = $sessionId
    trajectory_file = "results/$Run/$sessionId.jsonl"
    trajectory_url = $trajectoryUrl
    artifact_sha = $artifactSha
    artifact_permalink = $artifactPermalink
    artifact_branch = "task/$taskId/$Run"
    video_file = $videoFile
    video_path = $(if ($videoFile) { $videoPath } else { '' })
    video_duration_s = $videoDuration
    run_valid = $runValid
    validity_note = $validityNote
    collected_at = (Get-Date).ToString('o')
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resultDir 'summary.json') -Encoding UTF8

Write-Host "Collected $Run"
Write-Host "SessionID: $sessionId"
Write-Host "Trajectory: $trajectoryPath"
Write-Host "Artifact SHA: $artifactSha"
Write-Host "Artifact branch: task/$taskId/$Run"
Write-Host "Run valid: $runValid ($validityNote)"
if (-not $runValid) {
    Write-Warning "This run cannot be submitted as-is. Close the window, run reset-$Run.cmd, then start a fresh window and paste the prompt only."
}
