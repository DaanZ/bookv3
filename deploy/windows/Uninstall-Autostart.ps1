<#
.SYNOPSIS
    Stop the reader starting itself at logon, and stop it now if it is running.

.DESCRIPTION
    Removes the scheduled task created by Install-Autostart.ps1. Leaves the
    repository, the books, the profiles and the logs alone - this only undoes
    the autostart.

.PARAMETER TaskName
    Name in Task Scheduler. Defaults to "BookReader".

.PARAMETER KeepRunning
    Leave the current instance running instead of stopping it.

.EXAMPLE
    .\deploy\windows\Uninstall-Autostart.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = "BookReader",
    [switch]$KeepRunning
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "BooksCommon.ps1")

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Output "No scheduled task named '$TaskName' - nothing to remove."
} else {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed the '$TaskName' scheduled task."
}

if ($KeepRunning) { exit 0 }

# Stopping the task kills the PowerShell wrapper; uvicorn is a child process
# and outlives it, so the listener is what actually has to go. Matching on the
# executable path would not work: this repository has no virtualenv, so the
# process reports itself as the system Python under Program Files\WindowsApps.
# Stop-BooksListener matches the command line, which carries --app-dir <repo>
# and api.main:app.
$RepoRoot = Get-BooksRepoRoot
$Port = Get-BooksPort -RepoRoot $RepoRoot -TaskName $TaskName
$stoppedPid = Stop-BooksListener -Port $Port -RepoRoot $RepoRoot -TaskName $TaskName

if ($stoppedPid -gt 0) {
    Write-Output "Stopped the running instance (pid $stoppedPid) on port $Port."
} elseif ($stoppedPid -eq 0) {
    Write-Output "No reader process was running on port $Port."
}
