[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir
)

# Builds the GSB submission sheet for one task from meta.json and the
# collected per-run summary.json files. ASCII-only script: the Chinese
# labels live in tools/submission-template.txt and are read as UTF-8.

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf

$meta = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $taskDirResolved 'meta.json') | ConvertFrom-Json

function Get-RunValue {
    param([string]$Run, [string]$Field, [string]$Fallback = '(待补充)')
    $p = Join-Path $taskDirResolved "results\$Run\summary.json"
    if (-not (Test-Path -LiteralPath $p)) { return $Fallback }
    $summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $p | ConvertFrom-Json
    $value = $summary.$Field
    if (-not $value) { return $Fallback }
    return [string]$value
}

function Get-RunValidity {
    param([string]$Run)
    $p = Join-Path $taskDirResolved "results\$Run\summary.json"
    if (-not (Test-Path -LiteralPath $p)) { return '未采集 / missing' }
    $summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $p | ConvertFrom-Json
    if ($summary.run_valid -eq $true) { return '通过 / single prompt + task_complete' }
    return "不通过 / $($summary.validity_note)"
}

$notes = @()
foreach ($run in @('A', 'B')) {
    $p = Join-Path $taskDirResolved "results\$run\summary.json"
    if (-not (Test-Path -LiteralPath $p)) {
        $notes += "run $run has no collected summary.json"
        continue
    }
    $summary = Get-Content -Raw -Encoding UTF8 -LiteralPath $p | ConvertFrom-Json
    if ($summary.run_valid -ne $true) {
        $notes += "run $run must be re-run: $($summary.validity_note)"
    }
    if ($summary.artifact_note) {
        $notes += "run $run artifact: $($summary.artifact_note)"
    }
}
if ($notes.Count -eq 0) { $notes += 'A/B 均通过校验' }

$values = [ordered]@{
    task_id                = $taskId
    prompt_file            = $meta.prompt_file
    task_type              = $(if ($meta.task_type) { $meta.task_type } else { '' })
    difficulty             = $(if ($meta.difficulty) { $meta.difficulty } else { '' })
    language_framework     = $meta.language_framework
    harness_version        = $(if ($meta.harness_version) { $meta.harness_version } else { '' })
    os                     = $(if ($meta.os) { $meta.os } else { 'Windows 11' })
    reproducible           = $(if ($meta.reproducible) { $meta.reproducible } else { '' })
    initial_permalink      = $(if ($meta.initial_permalink) { $meta.initial_permalink } else { $meta.initial_sha })
    a_session_id           = Get-RunValue -Run 'A' -Field 'session_id'
    a_trajectory_url       = Get-RunValue -Run 'A' -Field 'trajectory_url'
    a_artifact_permalink   = Get-RunValue -Run 'A' -Field 'artifact_permalink'
    b_session_id           = Get-RunValue -Run 'B' -Field 'session_id'
    b_trajectory_url       = Get-RunValue -Run 'B' -Field 'trajectory_url'
    b_artifact_permalink   = Get-RunValue -Run 'B' -Field 'artifact_permalink'
    a_valid                = Get-RunValidity -Run 'A'
    b_valid                = Get-RunValidity -Run 'B'
    notes                  = ($notes -join ' | ')
}

$templatePath = Join-Path $PSScriptRoot 'submission-template.txt'
$template = [System.IO.File]::ReadAllText($templatePath, [System.Text.Encoding]::UTF8)
$text = $template
foreach ($key in $values.Keys) {
    $text = $text.Replace('{{' + $key + '}}', [string]$values[$key])
}

$outPath = Join-Path $taskDirResolved 'submission.md'
[System.IO.File]::WriteAllText($outPath, $text, (New-Object System.Text.UTF8Encoding($false)))
Write-Host $text
Write-Host "Saved to $outPath"
