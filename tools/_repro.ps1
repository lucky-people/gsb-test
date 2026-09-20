$ErrorActionPreference = 'Stop'
Write-Host ("PSVersion=" + $PSVersionTable.PSVersion.ToString())
$Record = $true
$RecordPath = Join-Path $env:TEMP 'gsb-repro\A.mp4'
$RecordRegion = 'full'
$recording = $null
if ($Record) {
    . (Join-Path $PSScriptRoot 'record-screen.ps1')
    $recordDir = Split-Path -Parent $RecordPath
    if ($recordDir -and -not (Test-Path -LiteralPath $recordDir)) {
        New-Item -ItemType Directory -Force -Path $recordDir | Out-Null
    }
    $region = Get-RecordRegion -Name $RecordRegion
    Write-Host ("region is null: " + ($null -eq $region))
    $cmd = Get-Command Start-ScreenRecording
    Write-Host ("command type: " + $cmd.CommandType)
    Write-Host ("parameters: " + (($cmd.Parameters.Keys | Sort-Object) -join ','))
    Write-Host ("module: " + $cmd.ModuleName + " source: " + $cmd.Source)
    Write-Host "--- definition head ---"
    Write-Host ($cmd.Definition.Substring(0, [Math]::Min(600, $cmd.Definition.Length)))
    Write-Host "--- end ---"
    Write-Host ("RecordPath value: [" + $RecordPath + "]")
    if ($region) {
        $recording = Start-ScreenRecording -OutPath $RecordPath -OffsetX $region.X -OffsetY $region.Y -Width $region.Width -Height $region.Height
    } else {
        $recording = Start-ScreenRecording -OutPath $RecordPath
    }
}
Write-Host ("recording started: " + ($null -ne $recording))
