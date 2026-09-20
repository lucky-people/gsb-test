# record-screen.ps1 - dot-sourceable screen recording helpers (ffmpeg gdigrab).
#
#   . "$PSScriptRoot\record-screen.ps1"
#   $rec = Start-ScreenRecording -OutPath "C:\path\A.mp4"
#   ... run the CLI ...
#   Stop-ScreenRecording -Recording $rec
#
# Kept ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less script files
# as ANSI, so non-ASCII characters here would be mangled. Machine-specific paths
# live in tools/config/record.json, which is always read as UTF-8.

function Get-RecordConfig {
    param([string]$ConfigPath)

    $cfg = [ordered]@{
        enabled   = $true
        ffmpegPath = 'ffmpeg'
        framerate = 10
        crf       = 26
        preset    = 'ultrafast'
        extraArgs = @()
        regions   = $null
    }
    if ($ConfigPath -and (Test-Path -LiteralPath $ConfigPath)) {
        $file = Get-Content -Raw -Encoding UTF8 -LiteralPath $ConfigPath | ConvertFrom-Json
        foreach ($key in @('enabled', 'ffmpegPath', 'framerate', 'crf', 'preset', 'extraArgs', 'regions')) {
            if ($file.PSObject.Properties[$key] -and $null -ne $file.$key) { $cfg[$key] = $file.$key }
        }
    }
    return $cfg
}

function Get-RecordRegion {
    param([string]$Name, [string]$ConfigPath)

    if (-not $Name -or $Name -eq 'full') { return $null }
    if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'config\record.json' }
    $cfg = Get-RecordConfig -ConfigPath $ConfigPath
    if (-not $cfg.regions) { throw "No regions configured in $ConfigPath" }
    $region = $cfg.regions.$Name
    if (-not $region) { throw "Unknown region '$Name' in $ConfigPath" }
    return [pscustomobject]@{
        X      = [int]$region.x
        Y      = [int]$region.y
        Width  = [int]$region.width
        Height = [int]$region.height
    }
}

function Resolve-FfmpegPath {
    param([string]$Configured, [string]$ExeName = 'ffmpeg.exe')

    $candidates = New-Object System.Collections.ArrayList
    if ($Configured) {
        $configuredName = Split-Path -Leaf $Configured
        $configuredDir = Split-Path -Parent $Configured
        if ($configuredName -ieq $ExeName) {
            [void]$candidates.Add($Configured)
        } elseif ($configuredDir) {
            # Sibling tool (ffmpeg.exe -> ffprobe.exe) installed next to it.
            [void]$candidates.Add((Join-Path $configuredDir $ExeName))
        }
    }
    [void]$candidates.Add($ExeName)
    [void]$candidates.Add((Join-Path $env:LOCALAPPDATA ('Microsoft\WinGet\Links\' + $ExeName)))

    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Start-ScreenRecording {
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

    if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'config\record.json' }
    $cfg = Get-RecordConfig -ConfigPath $ConfigPath
    if ($cfg.enabled -ne $true) {
        if (-not $Quiet) { Write-Host 'Recording disabled in record.json; skipping.' }
        return $null
    }

    $ffmpeg = Resolve-FfmpegPath -Configured $cfg.ffmpegPath
    if (-not $ffmpeg) {
        Write-Warning 'ffmpeg not found; skipping screen recording.'
        return $null
    }

    $fps = if ($Framerate -gt 0) { $Framerate } else { [int]$cfg.framerate }
    $dir = Split-Path -Parent $OutPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

    $argList = @('-hide_banner', '-loglevel', 'error', '-f', 'gdigrab', '-framerate', [string]$fps)
    if ($Width -gt 0 -and $Height -gt 0) {
        $argList += @('-offset_x', [string]$OffsetX, '-offset_y', [string]$OffsetY, '-video_size', ('{0}x{1}' -f $Width, $Height))
    }
    $argList += @(
        '-i', 'desktop',
        '-c:v', 'libx264',
        '-preset', [string]$cfg.preset,
        '-crf', [string]$cfg.crf,
        '-pix_fmt', 'yuv420p',
        # A keyframe every 2 seconds at 10 fps: fragments get flushed often
        # enough that an unexpected kill still leaves a playable video.
        '-g', '20'
    )
    if ($cfg.extraArgs) { $argList += @($cfg.extraArgs) }
    # Fragmented MP4: the file stays playable even if ffmpeg is killed instead
    # of stopped gracefully (e.g. the CLI window is closed by hand).
    $argList += @('-movflags', '+frag_keyframe+empty_moov+default_base_moof', '-y', $OutPath)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ffmpeg
    $psi.Arguments = (($argList | ForEach-Object {
                if ([string]$_ -match '\s') { '"' + [string]$_ + '"' } else { [string]$_ }
            }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Milliseconds 1500
    if ($proc.HasExited) {
        Write-Warning ('ffmpeg exited immediately (code ' + $proc.ExitCode + '); no recording for this run.')
        return $null
    }
    if (-not $Quiet) { Write-Host ('Recording started -> ' + $OutPath) }
    return [pscustomobject]@{ Process = $proc; Path = $OutPath; StartedAt = (Get-Date) }
}

function Stop-ScreenRecording {
    param($Recording, [switch]$Quiet)

    if ($null -eq $Recording) { return $null }
    $proc = $Recording.Process
    try {
        $proc.StandardInput.WriteLine('q')
        $proc.StandardInput.Flush()
    } catch { }
    if (-not $proc.WaitForExit(30000)) {
        try { $proc.Kill() } catch { }
        Write-Warning 'ffmpeg did not stop on request and was killed (video may be truncated).'
    }
    $info = Get-RecordingInfo -Path $Recording.Path
    if (-not $Quiet) {
        Write-Host ('Recording stopped -> {0} ({1} MB, {2} s)' -f $info.path, $info.size_mb, $info.duration_s)
    }
    return $info
}

function Get-RecordingInfo {
    param([Parameter(Mandatory = $true)][string]$Path)

    $result = [pscustomobject]@{
        path       = $Path
        exists     = $false
        size_mb    = 0
        duration_s = ''
    }
    if (-not (Test-Path -LiteralPath $Path)) { return $result }
    $item = Get-Item -LiteralPath $Path
    $result.exists = $true
    $result.size_mb = [math]::Round($item.Length / 1MB, 1)

    if (-not $script:RecordScreenFfprobe) {
        $cfg = Get-RecordConfig -ConfigPath (Join-Path $PSScriptRoot 'config\record.json')
        $script:RecordScreenFfprobe = Resolve-FfmpegPath -Configured $cfg.ffmpegPath -ExeName 'ffprobe.exe'
    }
    if ($script:RecordScreenFfprobe) {
        try {
            $out = & $script:RecordScreenFfprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $Path 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $result.duration_s = [math]::Round([double]($out | Select-Object -First 1), 1)
            }
        } catch { }
    }
    return $result
}
