$ErrorActionPreference = 'Continue'
Write-Host ("PSVersion=" + $PSVersionTable.PSVersion.ToString())

function Start-StubRecording {
    param(
        [Parameter(Mandatory = $true)][string]$OutPath,
        [string]$ConfigPath,
        [int]$Framerate = 0,
        [int]$OffsetX = 0,
        [int]$OffsetY = 0,
        [int]$Width = 0,
        [int]$Height = 0,
        [switch]$Quiet
    )
    return ('stub ' + $OutPath)
}

$p = Join-Path $env:TEMP 'gsb-repro\A.mp4'
Write-Host ("stub with same signature: " + (Start-StubRecording -OutPath $p -Quiet))

. (Join-Path $PSScriptRoot 'record-screen.ps1')

Write-Host '--- real call: literal path ---'
try { $x = Start-ScreenRecording -OutPath 'C:\Users\31077\AppData\Local\Temp\gsb-repro\Z.mp4'; Write-Host 'ok' } catch { Write-Host ('ERR: ' + $_.Exception.Message) }

Write-Host '--- real call: variable path ---'
try {
    $x = Start-ScreenRecording -OutPath $p
    Write-Host 'ok'
} catch {
    Write-Host ('ERR: ' + $_.Exception.Message)
    Write-Host '--- stack ---'
    Write-Host $_.ScriptStackTrace
    Write-Host '--- position ---'
    Write-Host $_.InvocationInfo.PositionMessage
}

Write-Host '--- real call: path + Quiet ---'
try { $x = Start-ScreenRecording -OutPath $p -Quiet; Write-Host 'ok' } catch { Write-Host ('ERR: ' + $_.Exception.Message) }

Write-Host '--- PSScriptRoot inside function ---'
function Show-Root { return ('[' + $PSScriptRoot + ']') }
Write-Host (Show-Root)
