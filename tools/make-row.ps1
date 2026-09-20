[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [string]$Uid = '',
    [string]$Submitter = '',
    [string]$OutPath = ''
)

# Builds the 26-column GSB sheet row for one task from meta.json and the
# collected per-run summary.json files, so the row can be pasted into the
# Feishu table without hand-copying values.
#
# ASCII-only script: the Chinese column headers live in tools/row-headers.txt
# and are always read as UTF-8.

$ErrorActionPreference = 'Stop'
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$taskId = Split-Path $taskDirResolved -Leaf

$headersPath = Join-Path $PSScriptRoot 'row-headers.txt'
$headers = @([System.IO.File]::ReadAllLines($headersPath, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() -ne '' })
if ($headers.Count -ne 26) {
    throw "Expected 26 column headers in $headersPath, found $($headers.Count)."
}

$metaPath = Join-Path $taskDirResolved 'meta.json'
if (-not (Test-Path -LiteralPath $metaPath)) { throw "Missing meta.json: $metaPath" }
$meta = Get-Content -Raw -Encoding UTF8 -LiteralPath $metaPath | ConvertFrom-Json

$promptPath = Join-Path $taskDirResolved 'prompt.md'
$prompt = ''
if (Test-Path -LiteralPath $promptPath) {
    $prompt = [System.IO.File]::ReadAllText($promptPath, [System.Text.Encoding]::UTF8).Trim()
}

function Get-Summary {
    param([string]$Run)
    $path = Join-Path $taskDirResolved "results\$Run\summary.json"
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    return (Get-Content -Raw -Encoding UTF8 -LiteralPath $path | ConvertFrom-Json)
}

function Get-Field {
    param($Summary, [string]$Name)
    if ($null -eq $Summary) { return '' }
    $value = $Summary.$Name
    if ($null -eq $value) { return '' }
    return [string]$value
}

$summaryA = Get-Summary -Run 'A'
$summaryB = Get-Summary -Run 'B'

$harness = 'Codex CLI'
if ($meta.harness -and ([string]$meta.harness).ToLower().Contains('claude')) { $harness = 'Claude Code' }

$initial = Get-Field -Summary $null -Name 'initial_permalink'
if ($meta.initial_permalink) { $initial = [string]$meta.initial_permalink }
elseif ($meta.initial_sha) { $initial = [string]$meta.initial_sha }

$notes = New-Object System.Collections.ArrayList
foreach ($pair in @(@('A', $summaryA), @('B', $summaryB))) {
    $run = $pair[0]
    $summary = $pair[1]
    if ($null -eq $summary) { [void]$notes.Add("run $run not collected"); continue }
    if ($summary.run_valid -ne $true) { [void]$notes.Add("run $run invalid: $($summary.validity_note)") }
}

$values = @(
    $Uid,
    $prompt,
    $(if ($meta.task_type) { [string]$meta.task_type } else { '' }),
    $(if ($meta.difficulty) { [string]$meta.difficulty } else { '' }),
    $(if ($meta.language_framework) { [string]$meta.language_framework } else { '' }),
    $harness,
    $(if ($meta.harness_version) { [string]$meta.harness_version } else { '' }),
    $(if ($meta.os) { [string]$meta.os } else { 'Windows 11' }),
    $(if ($meta.reproducible) { [string]$meta.reproducible } else { '' }),
    $initial,
    (Get-Field -Summary $summaryA -Name 'session_id'),
    (Get-Field -Summary $summaryA -Name 'trajectory_file'),
    (Get-Field -Summary $summaryA -Name 'artifact_permalink'),
    (Get-Field -Summary $summaryA -Name 'video_path'),
    (Get-Field -Summary $summaryB -Name 'session_id'),
    (Get-Field -Summary $summaryB -Name 'trajectory_file'),
    (Get-Field -Summary $summaryB -Name 'artifact_permalink'),
    (Get-Field -Summary $summaryB -Name 'video_path'),
    '',
    '',
    '',
    ($notes -join ' | '),
    $Submitter,
    (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'),
    '',
    ''
)

if ($values.Count -ne $headers.Count) {
    throw "Value/header count mismatch: $($values.Count) values, $($headers.Count) headers."
}

if (-not $OutPath) { $OutPath = Join-Path $taskDirResolved 'row' }

$quote = {
    param([string]$Text)
    if ($null -eq $Text) { $Text = '' }
    return ('"' + ($Text -replace '"', '""') + '"')
}

$csvLines = @()
$csvLines += (($headers | ForEach-Object { & $quote $_ }) -join ',')
$csvLines += (($values | ForEach-Object { & $quote $_ }) -join ',')
$csvPath = "$OutPath.csv"
[System.IO.File]::WriteAllText($csvPath, (($csvLines -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))

$tsvValues = $values | ForEach-Object { (([string]$_) -replace "`r`n", '\n') -replace "`n", '\n' }
$tsvPath = "$OutPath.tsv"
[System.IO.File]::WriteAllText($tsvPath, (($headers -join "`t") + "`r`n" + ($tsvValues -join "`t") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))

Write-Host ''
Write-Host ('Row for task {0}' -f $taskId)
Write-Host ('  CSV (import into the sheet): {0}' -f $csvPath)
Write-Host ('  TSV (single line to paste) : {0}' -f $tsvPath)
if ($notes.Count -gt 0) {
    Write-Host ('  Warnings: {0}' -f ($notes -join ' | '))
}
Write-Host ''
Write-Host ($headers -join "`t")
Write-Host ($tsvValues -join "`t")
