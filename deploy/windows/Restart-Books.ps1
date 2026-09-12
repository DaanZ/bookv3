<#
.SYNOPSIS
    Restart the reader so it picks up updated code.

.DESCRIPTION
    Stops whatever is actually serving, then starts it again, and prints the
    old and new process id so you can see the swap happened.

    Doing this by hand does not work, which is why the script exists.
    Stop-ScheduledTask kills the PowerShell wrapper but leaves uvicorn running
    detached; the task then reports "Ready" while the old build still serves,
    and the next Start-ScheduledTask finds the port busy and declines. The
    whole cycle looks successful and changes nothing.

    Python changes need only this. Anything under web/ needs -Rebuild as well:
    this process serves web\dist, which Vite has to regenerate. Dependency
    changes need -Install.

.PARAMETER Port
    Port to restart on. Defaults to whatever the task was registered with, else
    BOOKS_PORT from .env, else 8770.

.PARAMETER Rebuild
    Rebuild the reader bundle first (npm run build in web/).

.PARAMETER Install
    Reinstall Python dependencies first. Needed after requirements.txt changes.

.PARAMETER TaskName
    Task to drive. Defaults to "BookReader". If no such task exists the runner
    is launched directly, so this works before Install-Autostart has run.

.EXAMPLE
    .\deploy\windows\Restart-Books.ps1
    .\deploy\windows\Restart-Books.ps1 -Rebuild
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$Rebuild,
    [switch]$Install,
    [string]$TaskName = "BookReader"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "BooksCommon.ps1")

$RepoRoot = Get-BooksRepoRoot
$Port = Get-BooksPort -Port $Port -RepoRoot $RepoRoot -TaskName $TaskName

Write-Output "Repository : $RepoRoot"
Write-Output "Port       : $Port"

# --- optional rebuilds, before anything is stopped --------------------------
# Done first deliberately: a failed build should leave the old version serving
# rather than take the shelf down while you fix it.

if ($Install) {
    Write-Output ""
    Write-Output "Installing Python dependencies..."
    $pip = Join-Path $RepoRoot ".venv/Scripts/pip.exe"
    if (-not (Test-Path $pip)) {
        $found = Get-Command pip -ErrorAction SilentlyContinue
        $pip = if ($found) { $found.Source } else { $null }
    }
    if (-not $pip) { Write-Error "No pip found."; exit 1 }
    & $pip install -q -r (Join-Path $RepoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed; nothing was restarted."; exit 1 }
}

if ($Rebuild) {
    Write-Output ""
    Write-Output "Rebuilding the reader..."
    & npm --prefix (Join-Path $RepoRoot "web") run build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "The build failed; nothing was restarted and the old bundle is still serving."
        exit 1
    }
}

# --- stop -------------------------------------------------------------------

Write-Output ""
$oldPid = Stop-BooksListener -Port $Port -RepoRoot $RepoRoot -TaskName $TaskName

if ($oldPid -eq -1) { exit 1 }
if ($oldPid -eq 0) {
    Write-Output "Nothing was running on $Port."
} else {
    Write-Output "Stopped pid $oldPid."
}

# --- start ------------------------------------------------------------------

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Started the '$TaskName' task."
} else {
    $runner = Join-Path $PSScriptRoot "Start-Books.ps1"
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", $runner, "-Port", "$Port")
    Write-Output "No '$TaskName' task registered; launched the runner directly."
}

if (-not (Wait-BooksHealthy -Port $Port)) {
    Write-Error "It did not answer on $Port. Check $RepoRoot\logs\books.err.log"
    exit 1
}

$listener = Get-BooksListener -Port $Port -RepoRoot $RepoRoot
$newPid = if ($listener) { $listener.ProcessId } else { 0 }

Write-Output ""
if ($oldPid -gt 0 -and $newPid -eq $oldPid) {
    # Should be impossible now, but saying so beats reporting a restart that
    # did not happen, which is the exact failure this script was written for.
    Write-Error "Still serving pid $oldPid - the restart did not take effect."
    exit 1
}
Write-Output ("Running on http://127.0.0.1:$Port/  (pid {0}{1})" -f $newPid,
    $(if ($oldPid -gt 0) { ", was $oldPid" } else { "" }))
