[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ConfigTemplate,
    [int]$TimeoutSeconds = 90,
    [switch]$Quiet
)

# Cheap preflight: one minimal /v1/responses call that proves the relay key,
# base URL and model name work before a 20-minute agent run is started.
# ASCII-only script; keys and Chinese paths live in UTF-8 data files.

$ErrorActionPreference = 'Stop'
if (-not $EnvFile) { $EnvFile = Join-Path $PSScriptRoot 'config\.env.local' }
if (-not $ConfigTemplate) { $ConfigTemplate = Join-Path $PSScriptRoot 'config\config.template.toml' }

if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Missing $EnvFile" }
if (-not (Test-Path -LiteralPath $ConfigTemplate)) { throw "Missing $ConfigTemplate" }

$key = $null
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^\s*SUPER_RELAY_KEY\s*=\s*(.+?)\s*$') { $key = $Matches[1].Trim('"').Trim("'") }
}
if (-not $key) { throw "SUPER_RELAY_KEY not found in $EnvFile" }

$template = Get-Content -Raw -Encoding UTF8 -LiteralPath $ConfigTemplate
$baseUrl = $null
$model = $null
foreach ($line in ($template -split "`n")) {
    $t = $line.Trim()
    if ($t -match '^model\s*=\s*"([^"]+)"') { $model = $Matches[1] }
    if ($t -match '^base_url\s*=\s*"([^"]+)"') { $baseUrl = $Matches[1] }
}
if (-not $baseUrl) { throw "base_url not found in $ConfigTemplate" }
if (-not $model) { throw "model not found in $ConfigTemplate" }

$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
if (-not $curl) { throw 'curl.exe not found; cannot run the relay preflight.' }

$body = '{"model":"' + $model + '","input":"ping"}'
# Windows PowerShell 5.1 strips the inner double quotes when a JSON string is
# passed straight to a native command, so hand the body to curl through a file.
$bodyFile = Join-Path $env:TEMP ('gsb-relay-body-' + [guid]::NewGuid().ToString('N') + '.json')
[System.IO.File]::WriteAllText($bodyFile, $body, (New-Object System.Text.UTF8Encoding($false)))
$code = ''
$snippet = ''
for ($attempt = 1; $attempt -le 3; $attempt++) {
    $outFile = Join-Path $env:TEMP ('gsb-relay-probe-' + [guid]::NewGuid().ToString('N') + '.json')
    try {
        $raw = & $curl.Source -sS -m $TimeoutSeconds -o $outFile -w '%{http_code}' `
            -X POST "$baseUrl/responses" `
            -H "Authorization: Bearer $key" `
            -H 'Content-Type: application/json' `
            -d ("@" + $bodyFile) 2>&1
        $code = ([string]($raw | Select-Object -Last 1)).Trim()
        if (Test-Path -LiteralPath $outFile) {
            $text = [System.IO.File]::ReadAllText($outFile, [System.Text.Encoding]::UTF8)
            if ($text) { $snippet = $text.Substring(0, [Math]::Min(240, $text.Length)) }
        }
    } finally {
        if (Test-Path -LiteralPath $outFile) { Remove-Item -LiteralPath $outFile -Force -ErrorAction SilentlyContinue }
    }
    if ($code -eq '200') { break }
    if ($attempt -lt 3) {
        Write-Host ("relay preflight attempt {0} -> HTTP {1}; retrying in 5s" -f $attempt, $code)
        Start-Sleep -Seconds 5
    }
}
if (Test-Path -LiteralPath $bodyFile) { Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue }

if ($code -ne '200') {
    throw "relay preflight failed: HTTP $code ($baseUrl, model $model) $snippet"
}

if (-not $Quiet) {
    Write-Host 'Relay preflight OK (key + model reachable).'
}
