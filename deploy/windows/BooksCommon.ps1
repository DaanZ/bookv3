<#
    Shared helpers for the Windows autostart scripts. Dot-source it:

        . (Join-Path $PSScriptRoot "BooksCommon.ps1")

    Adapted from the Ambience playbook (docs/windows-autostart-playbook.md in
    that repository). The trap this file exists for, stated plainly:
    Stop-ScheduledTask terminates the PowerShell wrapper but *not* the uvicorn
    process it launched, because the child is detached and survives. The task
    then reports "Ready" while the old build is still serving, and the next
    Start-ScheduledTask finds the port busy and declines. A stop/start cycle
    therefore looks successful and changes nothing. Restarting has to go after
    the listener itself, which is what these helpers do.
#>

function Get-BooksRepoRoot {
    <# The repository this script lives in. #>
    param([string]$ScriptRoot = $PSScriptRoot)
    return (Split-Path -Parent (Split-Path -Parent $ScriptRoot))
}

function Get-BooksPort {
    <#
        Port the autostart is configured for: explicit argument, else the
        registered task's own arguments, else BOOKS_PORT from .env, else 8770.
        Reading it back from the task is what keeps a restart pointed at the
        port the installer chose.

        8770 rather than 8001: 8001 is the development API, 8000 is held by an
        unrelated service on this machine, and 3000 is Vite. The always-on copy
        must not fight the one you are editing against.
    #>
    param(
        [int]$Port = 0,
        [string]$RepoRoot,
        [string]$TaskName = "BookReader"
    )
    if ($Port -gt 0) { return $Port }

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        foreach ($action in $task.Actions) {
            $arguments = $action.Arguments
            if ($arguments -and $arguments -match '-Port\s+(\d+)') { return [int]$Matches[1] }
        }
    }

    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile -Encoding utf8) {
            if ($line -match '^\s*BOOKS_PORT\s*=\s*(\d+)') { return [int]$Matches[1] }
        }
    }
    return 8770
}

function Get-BooksPython {
    <#
        The interpreter to launch with. pythonw runs without allocating a
        console, which is what keeps the logon silent; python.exe would flash a
        window at every start.

        A virtualenv is preferred but not required, because this repository has
        none and runs against the system install. Returns $null if nothing
        usable is found, so the caller can say so rather than failing obscurely.
    #>
    param([string]$RepoRoot)

    foreach ($candidate in @(
        (Join-Path $RepoRoot ".venv/Scripts/pythonw.exe"),
        (Join-Path $RepoRoot ".venv/Scripts/python.exe")
    )) {
        if (Test-Path $candidate) { return $candidate }
    }

    foreach ($name in @("pythonw.exe", "python.exe")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

function Get-BooksListener {
    <#
        The process listening on the port, plus whether it belongs to this
        repository. Anything else must never be killed: 8000, 8001 and 3000 on
        this machine are other things, and a restart that shot one of those
        down would be far worse than a failed restart.

        Ownership is decided on the *command line*, not the executable path. A
        Windows virtualenv contains no interpreter, and this repository does not
        even have a virtualenv: the running image reports itself as the base
        install under C:\Program Files\WindowsApps\..., so matching the path
        against the repository never matches.

        The command line is made to carry the answer. Start-Books.ps1 passes
        uvicorn `--app-dir <RepoRoot>`, which it needs anyway to import api.main
        from the right place, and which guarantees the repository path appears
        in the command line whether or not a virtualenv is in play. Both halves
        are required: the path, and the entry point.
    #>
    param([int]$Port, [string]$RepoRoot)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connection) { return $null }

    $processId = $connection[0].OwningProcess
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $commandLine = $null
    try {
        $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $processId" `
            -ErrorAction SilentlyContinue).CommandLine
    } catch { }

    $isOurs = $false
    if ($commandLine) {
        $isOurs = ($commandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -and
                  ($commandLine.IndexOf("api.main:app", [StringComparison]::OrdinalIgnoreCase) -ge 0)
    }

    return [pscustomobject]@{
        ProcessId   = $processId
        Name        = if ($process) { $process.ProcessName } else { "unknown" }
        CommandLine = $commandLine
        IsOurs      = $isOurs
    }
}

function Stop-BooksListener {
    <#
        Stop the task and the process actually holding the port. Returns the
        pid that was stopped, or 0 if nothing was running.

        Refuses to touch a listener that is not ours and returns -1, so the
        caller can report the clash rather than silently doing nothing.
    #>
    param(
        [int]$Port,
        [string]$RepoRoot,
        [string]$TaskName = "BookReader",
        [int]$TimeoutSeconds = 20
    )

    # Stop the task first so its restart-on-failure setting does not race us by
    # relaunching the moment the listener dies.
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch { }
    }

    $listener = Get-BooksListener -Port $Port -RepoRoot $RepoRoot
    if (-not $listener) { return 0 }

    if (-not $listener.IsOurs) {
        Write-Warning ("Port {0} is held by {1} (pid {2}), which is not from {3}. Leaving it alone." -f
            $Port, $listener.Name, $listener.ProcessId, $RepoRoot)
        return -1
    }

    Stop-Process -Id $listener.ProcessId -Force -ErrorAction SilentlyContinue

    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Get-BooksListener -Port $Port -RepoRoot $RepoRoot)) { return $listener.ProcessId }
    }
    Write-Warning ("Port {0} was still held {1}s after stopping pid {2}." -f
        $Port, $TimeoutSeconds, $listener.ProcessId)
    return $listener.ProcessId
}

function Wait-BooksHealthy {
    <#
        Poll /api/health until it answers. Returns $true if it came up.

        /api/health is the one endpoint that asks nobody who they are. Every
        other route now needs a profile and a device token, and a 401 would be
        indistinguishable from a server that is up but locked.
    #>
    param([int]$Port, [string]$Probe = "127.0.0.1", [int]$TimeoutSeconds = 90)

    for ($i = 1; $i -le $TimeoutSeconds; $i++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri "http://${Probe}:${Port}/api/health" `
                -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
    }
    return $false
}
