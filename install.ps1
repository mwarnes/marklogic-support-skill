<#
.SYNOPSIS
  Install, update, check or remove the MarkLogic support skills for pi, Claude Code, Codex and GitHub Copilot (Windows).

.DESCRIPTION
  Links (directory junctions, no administrator rights or Developer Mode needed) or copies the folders under
  skills\ into:
    %USERPROFILE%\.agents\skills\<skill>   read by pi, Codex and GitHub Copilot
    %USERPROFILE%\.claude\skills\<skill>   read by Claude Code (and by GitHub Copilot)
  Same behaviour as install.sh. This script has not been run in the project's automated tests.

.PARAMETER Command   install (default) | update | status | uninstall
.PARAMETER Agents    comma list of: pi, claude, codex, copilot, all (default all)
.PARAMETER Copy      copy the skill folders instead of linking (re-run update to refresh)
.PARAMETER Force     replace a real folder of the same name, keeping a .bak-<time> copy
.PARAMETER NoPull    update: do not run git pull first
.PARAMETER CleanLegacy  move superseded command files (ticket/kcs/kcs-review .md) aside to .bak-<time>

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command update
#>
[CmdletBinding()]
param(
    [ValidateSet('install', 'update', 'status', 'uninstall')][string]$Command = 'install',
    [string]$Agents = 'all',
    [switch]$Copy,
    [switch]$Force,
    [switch]$NoPull,
    [switch]$CleanLegacy
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Mark = '.installed-by-marklogic-support-skill'
$script:Problems = 0

function Say($m) { Write-Output $m }
function Problem($m) { Write-Warning $m; $script:Problems++ }

# --- targets ---------------------------------------------------------------------------------------
$Targets = New-Object System.Collections.Generic.List[string]
function Add-Target($p) { if (-not $Targets.Contains($p)) { $Targets.Add($p) } }
foreach ($a in ($Agents -split ',')) {
    switch ($a.Trim().ToLower()) {
        'all'     { Add-Target (Join-Path $HOME '.agents\skills'); Add-Target (Join-Path $HOME '.claude\skills') }
        { $_ -in 'pi', 'codex', 'copilot' } { Add-Target (Join-Path $HOME '.agents\skills') }
        'claude'  { Add-Target (Join-Path $HOME '.claude\skills') }
        default   { [Console]::Error.WriteLine("unknown agent '$a' (use pi, claude, codex, copilot or all)"); exit 2 }
    }
}

function Get-Skills {
    Get-ChildItem -Directory (Join-Path $Repo 'skills') |
        Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } | ForEach-Object { $_.Name }
}

function Get-LinkTarget($path) {
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType) { return [string]($item.Target | Select-Object -First 1) }
    return $null
}

function Remove-Link($path) { [System.IO.Directory]::Delete($path, $false) }    # removes the junction, not its contents

function Test-RepoLink($path, $name) {    # dangling, or a link into <clone>\skills\<name> of a checkout of this repo
    $t = Get-LinkTarget $path
    if (-not $t) { return $false }
    if (-not (Test-Path -LiteralPath $t)) { return $true }
    $leaf = Split-Path -Leaf $t
    $skillsDir = Split-Path -Parent $t
    if ($leaf -ne $name -or (Split-Path -Leaf $skillsDir) -ne 'skills') { return $false }
    return (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $skillsDir) 'install.ps1'))
}

function Test-Ours($path) {
    $t = Get-LinkTarget $path
    if ($t) { return $t.StartsWith((Join-Path $Repo 'skills'), [System.StringComparison]::OrdinalIgnoreCase) }
    return (Test-Path -LiteralPath (Join-Path $path $Mark))
}

function Install-One($name, $tdir) {
    $src = Join-Path (Join-Path $Repo 'skills') $name
    $dest = Join-Path $tdir $name
    New-Item -ItemType Directory -Force -Path $tdir | Out-Null
    $existing = Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    if ($existing) {
        $lt = Get-LinkTarget $dest
        if ($lt) {
            if (-not $Copy -and $lt -eq $src) { Say "ok        $dest"; return }
            if (Test-RepoLink $dest $name) { Remove-Link $dest; Say "relinked  $dest (was -> $lt)" }
            elseif ($Force) { Move-Item -LiteralPath $dest -Destination "$dest.bak-$Stamp"; Say "backed up $dest -> $dest.bak-$Stamp" }
            else { Problem "$dest is a link to $lt that this installer did not create; re-run with -Force to replace it (a backup is kept)"; return }
        }
        elseif (Test-Path -LiteralPath (Join-Path $dest $Mark)) { Remove-Item -Recurse -Force -LiteralPath $dest }
        elseif ($Force) { Move-Item -LiteralPath $dest -Destination "$dest.bak-$Stamp"; Say "backed up $dest -> $dest.bak-$Stamp" }
        else { Problem "$dest exists and is not managed by this installer; re-run with -Force to replace it (a backup is kept)"; return }
    }
    if ($Copy) {
        Copy-Item -Recurse -LiteralPath $src -Destination $dest
        New-Item -ItemType File -Path (Join-Path $dest $Mark) | Out-Null
        Say "copied    $dest"
    }
    else {
        try { New-Item -ItemType Junction -Path $dest -Target $src | Out-Null }
        catch { Problem "could not create the junction $dest ($($_.Exception.Message)); re-run with -Copy"; return }
        Say "linked    $dest -> $src"
    }
}

function Status-One($name, $tdir) {
    $src = Join-Path (Join-Path $Repo 'skills') $name
    $dest = Join-Path $tdir $name
    $lt = Get-LinkTarget $dest
    if ($lt) {
        if ($lt -eq $src) { Say "ok        $dest" }
        elseif (Test-RepoLink $dest $name) { Say "stale     $dest -> $lt (run: powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command update)"; $script:Problems++ }
        else { Say "conflict  $dest is a link to $lt that this installer did not create"; $script:Problems++ }
    }
    elseif (Test-Path -LiteralPath (Join-Path $dest $Mark)) { Say "copy      $dest (refresh with: powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command update -Copy)" }
    elseif (Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue) { Say "conflict  $dest is not managed by this installer"; $script:Problems++ }
    else { Say "missing   $dest"; $script:Problems++ }
}

function Uninstall-One($name, $tdir) {
    $dest = Join-Path $tdir $name
    if (Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue) {
        if (Test-Ours $dest) {
            if (Get-LinkTarget $dest) { Remove-Link $dest } else { Remove-Item -Recurse -Force -LiteralPath $dest }
            Say "removed   $dest"
        }
        else { Say "kept      $dest (not installed by this repo)" }
    }
}

function Show-Legacy {
    foreach ($d in @((Join-Path $HOME '.claude\commands'), (Join-Path $HOME '.pi\agent\prompts'), (Join-Path $HOME '.codex\prompts'))) {
        foreach ($n in 'ticket', 'kcs', 'kcs-review') {
            $f = Join-Path $d "$n.md"
            if (-not (Test-Path -LiteralPath $f)) { continue }
            if ($CleanLegacy) { Move-Item -LiteralPath $f -Destination "$f.bak-$Stamp"; Say "moved     $f -> $f.bak-$Stamp (superseded by the $n skill)" }
            else { Say "legacy    $f is superseded by the '$n' skill; remove it with -CleanLegacy" }
        }
    }
}

function Show-Deps {
    if (-not ((Get-Command python3 -ErrorAction SilentlyContinue) -or (Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue))) {
        Problem 'Python 3 not found: the analysis and ticket scripts need it (install from https://www.python.org/downloads/)'
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Warning "git not found: needed for 'update'" }
    if (-not (Get-Command pandoc -ErrorAction SilentlyContinue)) { Say 'note      pandoc not found: /kcs cannot write the Word/HTML versions until it is installed (https://pandoc.org/installing.html)' }
}

function Get-Commit { try { (& git -C $Repo rev-parse --short HEAD 2>$null) } catch { 'unknown' } }

# --- run -------------------------------------------------------------------------------------------
if ($Command -eq 'update' -and -not $NoPull) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Error 'git is required for update (or use -NoPull)'; exit 1 }
    $before = Get-Commit
    & git -C $Repo pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Error 'git pull failed; fix the repository (local changes? no network?) and re-run, or use -NoPull'; exit 1 }
    $after = Get-Commit
    if ($before -eq $after) { Say "repository already at $after" } else { Say "repository updated $before -> $after" }
}

$Skills = @(Get-Skills)
if ($Skills.Count -eq 0) { Write-Error "no skills found under $Repo\skills"; exit 1 }

switch ($Command) {
    { $_ -in 'install', 'update' } {
        foreach ($t in $Targets) { foreach ($s in $Skills) { Install-One $s $t } }
        Show-Legacy; Show-Deps
    }
    'status' {
        Say "repository $Repo at $(Get-Commit)"
        foreach ($t in $Targets) { foreach ($s in $Skills) { Status-One $s $t } }
        Show-Legacy; Show-Deps
    }
    'uninstall' {
        foreach ($t in $Targets) { foreach ($s in $Skills) { Uninstall-One $s $t } }
    }
}

if ($script:Problems -gt 0) { exit 1 }
exit 0
