[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run,
    [switch]$SkipPush,
    [switch]$NoRecord,
    [ValidateSet('full','left','right')][string]$RecordRegion = 'full'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf
$summaryPath = Join-Path $taskDirResolved "results\$Run\summary.json"

function Push-MainResults {
    $relativeResults = "tasks/$taskId/results"
    git -C $repoRoot add $relativeResults
    git -C $repoRoot diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git -C $repoRoot commit -m "update $taskId $Run results" | Out-Null
    } else {
        Write-Host "No main-branch result changes to commit."
    }

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        git -C $repoRoot push origin main
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "git push origin main failed after 3 attempts."
}

Write-Host ""
Write-Host "=== GSB $Run RUN ==="
Write-Host "Task: $taskId"
Write-Host "Workspace will be reset before launch."
Write-Host ""

$recordPath = Join-Path $taskDirResolved "results\$Run\$Run.mp4"
$openArgs = @{ TaskDir = $taskDirResolved; Run = $Run }
if (-not $NoRecord) {
    $openArgs['Record'] = $true
    $openArgs['RecordPath'] = $recordPath
    $openArgs['RecordRegion'] = $RecordRegion
}
& (Join-Path $PSScriptRoot 'open-run.ps1') @openArgs

Write-Host ""
Write-Host "CLI exited. Collecting session and artifact snapshot..."

& (Join-Path $PSScriptRoot 'collect-run.ps1') -TaskDir $taskDirResolved -Run $Run

if (-not $SkipPush) {
    Write-Host ""
    Write-Host "Pushing base snapshot and $Run artifact..."

    try {
        & (Join-Path $PSScriptRoot 'push-base.ps1') -TaskDir $taskDirResolved
        Write-Host "[OK] base snapshot push"
    } catch {
        Write-Warning "[FAIL] base snapshot push: $($_.Exception.Message)"
    }

    try {
        & (Join-Path $PSScriptRoot 'push-run.ps1') -TaskDir $taskDirResolved -Run $Run
        Write-Host "[OK] $Run artifact push"
    } catch {
        Write-Warning "[FAIL] $Run artifact push: $($_.Exception.Message)"
    }

    try {
        Push-MainResults
        Write-Host "[OK] main-branch results push"
    } catch {
        Write-Warning "[FAIL] main-branch results push: $($_.Exception.Message)"
    }
}

if (Test-Path -LiteralPath $summaryPath) {
    $summary = Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
    $remoteUrl = git -C $repoRoot remote get-url origin 2>$null
    $baseUrl = $remoteUrl -replace '\.git$',''
    $trajectoryPath = Join-Path $taskDirResolved $summary.trajectory_file

    Write-Host ""
    Write-Host "=== RESULT ==="
    Write-Host "Task: $taskId"
    Write-Host "Run: $Run"
    Write-Host "Language/Framework: $($summary.language_framework)"
    Write-Host "Initial SHA: $($summary.initial_sha)"
    Write-Host "SessionID: $($summary.session_id)"
    Write-Host "Trajectory: $trajectoryPath"
    Write-Host "Artifact SHA: $($summary.artifact_sha)"
    Write-Host "Artifact branch: $($summary.artifact_branch)"
    if ($baseUrl) {
        Write-Host "Initial permalink: $baseUrl/commit/$($summary.initial_sha)"
        Write-Host "Artifact permalink: $baseUrl/commit/$($summary.artifact_sha)"
    }
    if (Test-Path -LiteralPath $recordPath) {
        $video = Get-Item -LiteralPath $recordPath
        Write-Host ("Recording: {0} ({1} MB)" -f $video.FullName, [math]::Round($video.Length / 1MB, 1))
    } else {
        Write-Host "Recording: (none)"
    }
}

if ($SkipPush) {
    Write-Host ""
    Write-Host "SkipPush specified. Local results are ready; push later with:"
    Write-Host "  .\push-base.cmd"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\push-run.ps1`" -TaskDir `"$taskDirResolved`" -Run $Run"
}
