[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Path
)

# Inspects a collected rollout jsonl and reports whether it is a valid
# single-turn GSB run (exactly one prompt, ended with task_complete).

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Path).Path
if ((Get-Item -LiteralPath $resolved).PSIsContainer) {
    $file = Get-ChildItem -LiteralPath $resolved -Recurse -Filter '*.jsonl' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
} else {
    $file = Get-Item -LiteralPath $resolved
}
if (-not $file) { throw "No jsonl found under $Path" }

$sessionId = $null
$userMessages = New-Object System.Collections.ArrayList
$events = New-Object System.Collections.ArrayList
$index = 0

$reader = New-Object System.IO.StreamReader($file.FullName)
try {
    while (($line = $reader.ReadLine()) -ne $null) {
        $index++
        if ($line -notmatch '"type"') { continue }
        try { $rec = $line | ConvertFrom-Json } catch { continue }
        $payload = $rec.payload
        if ($rec.type -eq 'session_meta' -and -not $sessionId) {
            $sessionId = $payload.session_id
            continue
        }
        if ($rec.type -eq 'response_item' -and $payload.type -eq 'message') {
            $text = ($payload.content | ForEach-Object { $_.text }) -join ' '
            if ($payload.role -eq 'user' -and $text -and $text -notmatch '^\s*<(environment_context|user_instructions|turn_aborted)') {
                $snippet = $text.Trim()
                if ($snippet.Length -gt 60) { $snippet = $snippet.Substring(0, 60) }
                [void]$userMessages.Add("[line $index] $snippet")
            }
        }
        if ($rec.type -eq 'event_msg' -and $payload.type -in @('task_complete', 'turn_aborted')) {
            [void]$events.Add("[line $index] $($payload.type)")
        }
    }
} finally {
    $reader.Dispose()
}

$completed = @($events | Where-Object { $_ -match 'task_complete' }).Count
$aborted = @($events | Where-Object { $_ -match 'turn_aborted' }).Count
$promptCount = $userMessages.Count

$verdict = 'VALID'
$problems = New-Object System.Collections.ArrayList
if ($completed -eq 0) { [void]$problems.Add('no task_complete: the turn never finished'); $verdict = 'INVALID' }
if ($aborted -gt 0) { [void]$problems.Add("$aborted turn_aborted event(s): the turn was interrupted"); $verdict = 'INVALID' }
if ($promptCount -gt 1) { [void]$problems.Add("$promptCount user messages: the session must contain the prompt only"); $verdict = 'INVALID' }
if ($promptCount -eq 0) { [void]$problems.Add('no user prompt found'); $verdict = 'INVALID' }

Write-Host "File:        $($file.FullName)"
Write-Host "SessionID:   $sessionId"
Write-Host "User turns:  $promptCount"
if ($promptCount -gt 0) {
    foreach ($m in $userMessages) { Write-Host "             $m" }
}
Write-Host "task_complete: $completed   turn_aborted: $aborted"
Write-Host "Verdict:     $verdict"
foreach ($p in $problems) { Write-Host "  - $p" }
