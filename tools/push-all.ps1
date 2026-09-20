[CmdletBinding()]
param(
    [string]$RepoUrl = "https://github.com/lucky-people/gsb-test.git",
    [string]$ProxyUrl = "",
    [int]$Attempts = 20,
    [int]$DelaySeconds = 20,
    [string]$RepoRoot = ""
)

# Pushes the runner repo plus every task snapshot branch to GitHub and then
# verifies the remote SHAs. Retries on network failure, which happens often
# when GitHub is reached without a proxy.

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$repoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

# a stale proxy in the environment or in the global config breaks every call
foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'GIT_HTTP_PROXY', 'GIT_HTTPS_PROXY')) {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
$proxyArgs = @('-c', "http.https://github.com/.proxy=$ProxyUrl")

$refs = @('refs/heads/main')
$refs += (git -C $repoRoot for-each-ref --format='%(refname)' 'refs/heads/task/*')

Write-Host "Repository : $RepoUrl"
Write-Host "Refs       : $($refs -join ', ')"
Write-Host ""

$pending = $refs
for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    if ($pending.Count -eq 0) { break }
    Write-Host "=== attempt $attempt ($($pending.Count) ref(s) left) ==="
    $stillPending = @()
    foreach ($ref in $pending) {
        $short = $ref -replace '^refs/heads/', ''
        $refspec = "${ref}:${ref}"
        $force = @()
        if ($short -eq 'main') { $force = @('--force') }
        Write-Host "-> push $short"
        git -C $repoRoot @proxyArgs push @force $RepoUrl $refspec 2>&1 | ForEach-Object { Write-Host "   $_" }
        if ($LASTEXITCODE -ne 0) { $stillPending += $ref }
    }
    $pending = $stillPending
    if ($pending.Count -gt 0 -and $attempt -lt $Attempts) {
        Write-Host "retrying in $DelaySeconds s..."
        Start-Sleep -Seconds $DelaySeconds
    }
}

if ($pending.Count -gt 0) {
    Write-Warning "These refs could not be pushed: $($pending -join ', ')"
    Write-Warning "Start the local proxy (Clash Verge, port 7897) and run this script again, for example:"
    Write-Warning "  powershell -NoProfile -ExecutionPolicy Bypass -File tools\push-all.ps1 -ProxyUrl http://127.0.0.1:7897"
    exit 1
}

$remote = git -C $repoRoot @proxyArgs ls-remote --heads $RepoUrl
Write-Host ""
Write-Host "=== remote heads ==="
$remote | ForEach-Object { Write-Host $_ }

$ok = $true
foreach ($ref in $refs) {
    $short = $ref -replace '^refs/heads/', ''
    $local = (git -C $repoRoot rev-parse $ref).Trim()
    $line = $remote | Where-Object { $_ -match "refs/heads/$([regex]::Escape($short))$" }
    $remoteSha = ($line -split '\s+')[0]
    if ($remoteSha -eq $local) {
        Write-Host "OK   $short $local"
    } else {
        Write-Host "DIFF $short local=$local remote=$remoteSha"
        $ok = $false
    }
}

if (-not $ok) { exit 1 }
Write-Host "All refs are in sync."
