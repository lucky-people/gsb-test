[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskId,
    [string]$PromptPath,
    [string]$SourceDir,
    [string]$LanguageFramework = "Unknown",
    [string]$TaskType = "",
    [string]$Difficulty = "困难",
    [string]$HarnessVersion = "",
    [string]$RepoUrl = "https://github.com/lucky-people/gsb-test",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

if ($TaskId -notmatch '^[A-Za-z0-9._-]+$') {
    throw "TaskId may only contain letters, digits, dot, underscore and hyphen."
}

$repoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$taskDir = Join-Path $repoRoot "tasks\$TaskId"
if (Test-Path -LiteralPath $taskDir) {
    throw "Task already exists: $taskDir"
}

New-Item -ItemType Directory -Path $taskDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $taskDir 'results\A') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $taskDir 'results\B') -Force | Out-Null

$tempBase = Join-Path $env:TEMP ("gsb-base-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempBase -Force | Out-Null

try {
    if ($SourceDir) {
        $source = (Resolve-Path -LiteralPath $SourceDir).Path
        robocopy $source $tempBase /MIR /XD .git node_modules data .next dist build coverage /XF .env .env.* *.db *.db-shm *.db-wal /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -gt 7) {
            throw "robocopy failed with exit code $LASTEXITCODE"
        }
    }

    $gitignore = Join-Path $tempBase '.gitignore'
    if (-not (Test-Path -LiteralPath $gitignore)) {
        @(
            '.env',
            '.env.*',
            'node_modules/',
            'dist/',
            'build/',
            '.next/',
            'coverage/',
            '*.db',
            '*.db-shm',
            '*.db-wal',
            '.DS_Store',
            'Thumbs.db'
        ) | Set-Content -LiteralPath $gitignore -Encoding ASCII
    }

    git -C $tempBase init | Out-Null
    git -C $tempBase branch -M base | Out-Null
    git -C $tempBase config user.name 'lucky-people'
    git -C $tempBase config user.email '3107734727@qq.com'
    git -C $tempBase add -A
    git -C $tempBase commit -m 'initial snapshot' | Out-Null
    $initialSha = (git -C $tempBase rev-parse HEAD).Trim()

    $bundle = Join-Path $taskDir 'baseline.bundle'
    git -C $tempBase bundle create $bundle base | Out-Null

    if ($PromptPath) {
        Copy-Item -LiteralPath $PromptPath -Destination (Join-Path $taskDir 'prompt.md') -Force
    } else {
        Set-Content -LiteralPath (Join-Path $taskDir 'prompt.md') -Value 'TODO: paste prompt here.' -Encoding UTF8
    }

    $permalink = $(if ($RepoUrl) { "$($RepoUrl.TrimEnd('/'))/commit/$initialSha" } else { '' })
    $meta = [ordered]@{
        task_id = $TaskId
        prompt_file = 'prompt.md'
        task_type = $TaskType
        difficulty = $Difficulty
        language_framework = $LanguageFramework
        harness = 'codex cli'
        harness_version = $HarnessVersion
        os = 'Windows 11'
        reproducible = '无外部依赖'
        repo_url = $RepoUrl
        base_branch = "task/$TaskId/base"
        initial_sha = $initialSha
        initial_permalink = $permalink
        created_at = (Get-Date).ToString('o')
    }
    $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskDir 'meta.json') -Encoding UTF8

    foreach ($run in @('A','B')) {
        $open = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\open-run.ps1`" -TaskDir `"%~dp0.`" -Run $run %*`r`n"
        $runAndUpload = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\run-and-upload.ps1`" -TaskDir `"%~dp0.`" -Run $run %*`r`n"
        $collect = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\collect-run.ps1`" -TaskDir `"%~dp0.`" -Run $run %*`r`n"
        $reset = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\reset-run.ps1`" -TaskDir `"%~dp0.`" -Run $run %*`r`n"
        [System.IO.File]::WriteAllText((Join-Path $taskDir "open-$run.cmd"), $open, [System.Text.Encoding]::ASCII)
        [System.IO.File]::WriteAllText((Join-Path $taskDir "run-$run.cmd"), $runAndUpload, [System.Text.Encoding]::ASCII)
        [System.IO.File]::WriteAllText((Join-Path $taskDir "collect-$run.cmd"), $collect, [System.Text.Encoding]::ASCII)
        [System.IO.File]::WriteAllText((Join-Path $taskDir "reset-$run.cmd"), $reset, [System.Text.Encoding]::ASCII)
    }

    $pushBase = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\push-base.ps1`" -TaskDir `"%~dp0.`" %*`r`n"
    [System.IO.File]::WriteAllText((Join-Path $taskDir 'push-base.cmd'), $pushBase, [System.Text.Encoding]::ASCII)

    # Demo launchers: replay the delivered artifact in its workspace so the run
    # can be recorded by hand.
    foreach ($run in @('A', 'B')) {
        $demo = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0..\..\tools\run-demo.ps1`" -TaskDir `"%~dp0.`" -Run $run %*`r`n"
        [System.IO.File]::WriteAllText((Join-Path $taskDir "demo-$run.cmd"), $demo, [System.Text.Encoding]::ASCII)
    }

    Write-Host "Task created: $taskDir"
    Write-Host "Initial snapshot SHA: $initialSha"
    Write-Host "Bundle: $bundle"
    Write-Host "Launchers: open-A.cmd, open-B.cmd"
}
finally {
    if (Test-Path -LiteralPath $tempBase) {
        Remove-Item -LiteralPath $tempBase -Recurse -Force
    }
}
