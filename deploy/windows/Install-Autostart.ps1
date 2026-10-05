<#
.SYNOPSIS
    Register the book reader to start automatically when you log on.

.DESCRIPTION
    Creates a Task Scheduler task that runs Start-Books.ps1 at logon.

    **At logon, not at boot.** Task Scheduler offers "At startup", which runs
    under SYSTEM in session 0 - no desktop, no audio endpoint. This app plays
    ambience under the reader and opens in a browser, so session 0 would mean
    the work happening and nothing coming out. Logon costs a few seconds and
    actually works.

    Runs as you, without elevation. Registering the task needs no admin rights.

.PARAMETER Port
    Port to serve on. Defaults to 8770: 8000 belongs to another service on this
    machine, 8001 is the development API and 3000 is Vite. Written into the
    task, not into .env, so the other scripts can read it back.

.PARAMETER DelaySeconds
    How long to wait after logon before starting. The default 30s lets the
    network come up first, so the tablet can reach it on the first try.

.PARAMETER TaskName
    Name in Task Scheduler. Defaults to "BookReader".

.PARAMETER NoTray
    Skip the notification-area icon. It is registered by default, since a
    background service with no visible sign of life is hard to trust.

.PARAMETER OpenReader
    Also open the reader in a browser at every logon. Off by default - a
    browser window opening itself each morning gets old quickly.

.EXAMPLE
    .\deploy\windows\Install-Autostart.ps1
    .\deploy\windows\Install-Autostart.ps1 -Port 8800 -DelaySeconds 60
#>
[CmdletBinding()]
param(
    [int]$Port = 8770,
    [int]$DelaySeconds = 30,
    [string]$TaskName = "BookReader",
    [switch]$OpenReader,
    [switch]$NoTray
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Runner = Join-Path $PSScriptRoot "Start-Books.ps1"

if (-not (Test-Path $Runner)) {
    Write-Error "Cannot find $Runner"
    exit 1
}

. (Join-Path $PSScriptRoot "BooksCommon.ps1")
if (-not (Get-BooksPython -RepoRoot $RepoRoot)) {
    Write-Error "No Python found on PATH and no virtualenv at $RepoRoot\.venv"
    exit 1
}

if (-not (Test-Path (Join-Path $RepoRoot "web/dist/index.html"))) {
    Write-Warning "web/dist is not built. The task will register, but the reader will 404 until you run ./build.sh"
}

$runnerArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`" -Port $Port"
if ($OpenReader) { $runnerArgs += " -OpenReader" }
if (-not $NoTray) { $runnerArgs += " -WithTray" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument $runnerArgs -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# ISO-8601 duration; the cmdlet has no -Delay parameter for a logon trigger.
$trigger.Delay = "PT${DelaySeconds}S"

# Also at unlock, because a logon run can die before it does anything. On 2 October
# the machine came back from an unexpected shutdown, the logon run was killed
# (0xC000013A) before writing a single log line, and RestartCount never stepped in:
# it covers a task that fails to *start*, not an action that exits badly. Nothing ran
# until it was started by hand. Unlocking is the moment someone sits down to read, and
# it costs nothing while the reader is up: MultipleInstances IgnoreNew drops the
# trigger when the task is already running, and the runner declines when the port is
# taken. No repeating trigger instead - each repetition would start a hidden
# PowerShell, which can flash a console window, every few minutes for ever.
$unlockClass = Get-CimClass -Namespace "Root/Microsoft/Windows/TaskScheduler" `
    -ClassName "MSFT_TaskSessionStateChangeTrigger"
$unlock = New-CimInstance -CimClass $unlockClass -ClientOnly
$unlock.StateChange = 8   # TASK_SESSION_UNLOCK
$unlock.UserId = "$env:USERDOMAIN\$env:USERNAME"
$unlock.Enabled = $true

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

# ExecutionTimeLimit defaults to three days, which for something meant to stay
# up is a time bomb; zero disables it. The battery settings matter on a laptop:
# the defaults refuse to start on battery and stop the task when you unplug.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$settings.Hidden = $true

$description = "Serves the book reader at logon (port $Port). Repository: $RepoRoot"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Output "Replacing the existing '$TaskName' task."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger @($trigger, $unlock) -Principal $principal `
    -Settings $settings -Description $description | Out-Null

Write-Output @"

Registered '$TaskName'. The reader will start $DelaySeconds seconds after you log on,
with no window, serving on http://127.0.0.1:$Port/
$(if ($NoTray) { "" } else { "A tray icon appears with it - Windows files new icons under the ^ overflow." })

Right now:
    Start-ScheduledTask -TaskName $TaskName        # start it without rebooting
    Get-ScheduledTask   -TaskName $TaskName | Get-ScheduledTaskInfo

Use the scripts rather than the task to stop and restart. Stop-ScheduledTask kills
the wrapper and leaves uvicorn serving, which looks like it worked and is not:
    .\deploy\windows\Stop-Books.ps1
    .\deploy\windows\Restart-Books.ps1 -Rebuild

Logs (the task has no console to print to):
    $RepoRoot\logs\autostart.log     what the wrapper decided
    $RepoRoot\logs\books.err.log     the server itself, where uvicorn logs
    $RepoRoot\logs\books.log         uvicorn stdout, usually quiet

To stop it starting itself:
    .\deploy\windows\Uninstall-Autostart.ps1

It binds to 0.0.0.0 so a tablet on the same network can read from it. That is only
safe because the reader authenticates: no guest, every request names a profile, and
a profile with a PIN needs a device token minted by that PIN. A profile WITHOUT a PIN
is an open door with a name on it - set one before trusting this on a shared network.
BOOKS_BIND=127.0.0.1 in .env keeps it on this machine instead.
"@
