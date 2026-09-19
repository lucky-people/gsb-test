[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$TaskDir,
    [Parameter(Mandatory=$true)][ValidateSet('A','B')][string]$Run,
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$taskDirResolved = (Resolve-Path -LiteralPath $TaskDir).Path
$tasksRoot = (Resolve-Path -LiteralPath (Join-Path $repoRoot 'tasks')).Path

if (-not $taskDirResolved.StartsWith($tasksRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "TaskDir must be under $tasksRoot"
}

$bundle = Join-Path $taskDirResolved 'baseline.bundle'
if (-not (Test-Path -LiteralPath $bundle)) {
    throw "Missing baseline bundle: $bundle"
}

$taskId = Split-Path $taskDirResolved -Leaf
$runDir = Join-Path $taskDirResolved $Run
$codexHomeRoot = Join-Path $taskDirResolved ".codex-home\$Run"
$runToken = Get-Date -Format 'yyyyMMdd-HHmmss'
$codexHome = Join-Path $codexHomeRoot $runToken

if (Test-Path -LiteralPath $runDir) {
    try {
        Remove-Item -LiteralPath $runDir -Recurse -Force -ErrorAction Stop
    } catch {
        throw "Could not reset $runDir. Close any running Codex windows and try again. $($_.Exception.Message)"
    }
}
New-Item -ItemType Directory -Path $codexHomeRoot -Force | Out-Null
New-Item -ItemType Directory -Path $codexHome -Force | Out-Null
[System.IO.File]::WriteAllText((Join-Path $codexHomeRoot 'current.txt'), $codexHome, (New-Object System.Text.UTF8Encoding($false)))

git clone --branch base --single-branch $bundle $runDir | Out-Null
git -C $runDir switch -c "task/$taskId/$Run" | Out-Null
git -C $runDir remote remove origin 2>$null
git -C $runDir config user.name 'lucky-people'
git -C $runDir config user.email '3107734727@qq.com'

$configDir = Join-Path $repoRoot 'tools\config'
foreach ($name in @('auth.json','relay_model_catalog.json','relay_base_instructions.txt')) {
    $src = Join-Path $configDir $name
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Missing CLI template file: $src"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $codexHome $name) -Force
}

$codexHomeForToml = $codexHome.Replace('\','/')
$configTemplate = Get-Content -Raw -LiteralPath (Join-Path $configDir 'config.template.toml')
$configText = $configTemplate.Replace('__CODEX_HOME__', $codexHomeForToml)
$trustKey = $runDir.ToLowerInvariant()
$configText += "`r`n[projects.'$trustKey']`r`ntrust_level = `"trusted`"`r`n"
[System.IO.File]::WriteAllText((Join-Path $codexHome 'config.toml'), $configText, (New-Object System.Text.UTF8Encoding($false)))

$envFile = Join-Path $configDir '.env.local'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile. Copy .env.local.template and fill SUPER_RELAY_KEY."
}

$key = $null
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*SUPER_RELAY_KEY\s*=\s*(.+?)\s*$') {
        $key = $Matches[1].Trim('"').Trim("'")
    }
}
if (-not $key) {
    throw "SUPER_RELAY_KEY not found in $envFile"
}

$envNames = @([Environment]::GetEnvironmentVariables().Keys)
foreach ($name in $envNames) {
    if ($name -like 'CODEX_*' -or $name -like 'OPENAI_*') {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }
}

$env:CODEX_HOME = $codexHome
$env:SUPER_RELAY_KEY = $key

$codexExe = Join-Path $env:APPDATA 'npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'
if (-not (Test-Path -LiteralPath $codexExe)) {
    $codexExe = 'codex'
}

Write-Host "Starting Codex CLI $Run"
Write-Host "Workspace: $runDir"
Write-Host "CODEX_HOME: $codexHome"

if ($PrepareOnly) {
    Write-Host "PrepareOnly specified; Codex CLI was not launched."
    exit 0
}

& $codexExe -C $runDir --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust
