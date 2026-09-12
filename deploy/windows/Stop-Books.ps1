<#
.SYNOPSIS
    Stop the reader now, without unregistering the autostart.

.DESCRIPTION
    Stops the scheduled task *and* the uvicorn process it launched. Both are
    needed: Stop-ScheduledTask on its own leaves uvicorn running detached and
    still holding the port, while reporting the task as stopped.

    The autostart stays registered, so it comes back at the next logon. To stop
    that too, use Uninstall-Autostart.ps1.

.PARAMETER Port
    Port to stop. Defaults to the task's own argument, else BOOKS_PORT from
    .env, else 8770.

.PARAMETER TaskName
    Task to stop. Defaults to "BookReader".

.EXAMPLE
    .\deploy\windows\Stop-Books.ps1
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$TaskName = "BookReader"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "BooksCommon.ps1")

$RepoRoot = Get-BooksRepoRoot
$Port = Get-BooksPort -Port $Port -RepoRoot $RepoRoot -TaskName $TaskName

$stoppedPid = Stop-BooksListener -Port $Port -RepoRoot $RepoRoot -TaskName $TaskName

if ($stoppedPid -eq -1) { exit 1 }
if ($stoppedPid -eq 0) {
    Write-Output "Nothing was running on port $Port."
} else {
    Write-Output "Stopped the reader (pid $stoppedPid) on port $Port."
    Write-Output "It will start again at your next logon; Uninstall-Autostart.ps1 prevents that."
}
