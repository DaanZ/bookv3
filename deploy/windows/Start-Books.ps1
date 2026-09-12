<#
.SYNOPSIS
    Start the book reader silently, for autostart at logon.

.DESCRIPTION
    Launched by the scheduled task that Install-Autostart.ps1 registers, and
    equally usable by hand. It resolves the repository from its own location,
    reads the bind address and port from .env, refuses to start a second copy,
    rotates its logs and then runs uvicorn under pythonw.exe so no console
    window appears.

    This is the *production* shape of the app, not the development one: one
    uvicorn process serves the API and the built bundle in web\dist together,
    so there is no Vite and no proxy. Changes to web/ need ./build.sh (or
    Restart-Books.ps1 -Rebuild) before they are visible.

    Output goes to logs\ rather than a terminal, because at logon there is no
    terminal to read.

.PARAMETER Port
    Overrides BOOKS_PORT from .env. Defaults to 8770 — 8000 belongs to another
    service on this machine, 8001 is the development API and 3000 is Vite.

.PARAMETER Bind
    Overrides BOOKS_BIND from .env. Defaults to 0.0.0.0, because the whole
    point of this app is reading on a tablet that is not this machine. That is
    only defensible because the reader now has real authentication: there is no
    guest, every request names a profile, and a profile with a PIN must present
    a device token minted by that PIN. Set it to 127.0.0.1 if you would rather
    the library never left this laptop.

.PARAMETER OpenReader
    Also open the reader in the default browser once the server answers.

.EXAMPLE
    .\deploy\windows\Start-Books.ps1 -Port 8770 -OpenReader
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$Bind = "",
    [switch]$OpenReader
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $RepoRoot "logs"
# This script's own log, separate from the two below: Start-Process truncates
# the files it redirects into, so a shared file would lose everything the
# wrapper wrote the moment the server launched.
$RunnerLog = Join-Path $LogDir "autostart.log"
$OutFile = Join-Path $LogDir "books.log"
$ErrFile = Join-Path $LogDir "books.err.log"
$MaxLogBytes = 5MB

function Write-Line {
    param([string]$Message)
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "$stamp  $Message"
    Write-Output $line
    try { Add-Content -Path $RunnerLog -Value $line -Encoding utf8 } catch { }
}

# --- environment ------------------------------------------------------------

function Read-DotEnv {
    <#
        Minimal KEY=VALUE reader, used only for the two settings below. The
        application reads .env properly through python-dotenv; this is just
        enough to find out where to listen.
    #>
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path $Path)) { return $values }
    foreach ($line in Get-Content -Path $Path -Encoding utf8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $split = $trimmed.IndexOf("=")
        if ($split -lt 1) { continue }
        $key = $trimmed.Substring(0, $split).Trim()
        $value = $trimmed.Substring($split + 1).Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $values[$key] = $value
    }
    return $values
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# Rotate before writing, so a machine left running does not fill the disk.
foreach ($file in @($RunnerLog, $OutFile, $ErrFile)) {
    if ((Test-Path $file) -and ((Get-Item $file).Length -gt $MaxLogBytes)) {
        $previous = "$file.1"
        if (Test-Path $previous) { Remove-Item $previous -Force }
        Move-Item $file $previous -Force
    }
}

$dotenv = Read-DotEnv (Join-Path $RepoRoot ".env")

if ($Port -le 0) {
    if ($dotenv.ContainsKey("BOOKS_PORT") -and $dotenv["BOOKS_PORT"] -match '^\d+$') {
        $Port = [int]$dotenv["BOOKS_PORT"]
    } else {
        $Port = 8770
    }
}
if ($Bind -eq "") {
    if ($dotenv.ContainsKey("BOOKS_BIND") -and $dotenv["BOOKS_BIND"] -ne "") {
        $Bind = $dotenv["BOOKS_BIND"]
    } else {
        $Bind = "0.0.0.0"
    }
}
# 0.0.0.0 is not a address you can ask for a health check.
$Probe = if ($Bind -eq "0.0.0.0") { "127.0.0.1" } else { $Bind }

# --- preconditions ----------------------------------------------------------

. (Join-Path $PSScriptRoot "BooksCommon.ps1")

$Python = Get-BooksPython -RepoRoot $RepoRoot
if (-not $Python) {
    Write-Line "No Python found on PATH and no virtualenv at $RepoRoot\.venv."
    exit 1
}

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    $owner = (Get-Process -Id $listening[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Line "Port $Port is already in use by $owner (pid $($listening[0].OwningProcess)); not starting a second copy."
    exit 0
}

# Without the bundle the API answers and every page is a 404: this process is
# the only thing serving the reader, so an unbuilt web\dist is not a detail.
if (-not (Test-Path (Join-Path $RepoRoot "web/dist/index.html"))) {
    Write-Line "web/dist is not built — the API will answer but there is no reader to open. Run ./build.sh"
}

# --- run --------------------------------------------------------------------

Write-Line "Starting the reader on ${Bind}:${Port} (repo $RepoRoot)"

# --app-dir does two jobs. It makes api.main importable from the right place
# whatever the working directory, and it puts the repository path on the
# command line — which is how Get-BooksListener recognises this process as ours
# later. Without a virtualenv there is nothing else on that command line that
# names this repository, so a restart could not tell our server from anyone's.
#
# Forward slashes deliberately: a backslash before a letter is an escape
# waiting to be interpreted by something downstream, and \t in a path is how
# the playbook's seventh trap starts.
$arguments = @(
    "-m", "uvicorn", "api.main:app",
    "--app-dir", $RepoRoot,
    "--host", $Bind,
    "--port", "$Port"
)
$process = Start-Process -FilePath $Python `
    -ArgumentList $arguments `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $OutFile `
    -RedirectStandardError $ErrFile `
    -WindowStyle Hidden `
    -PassThru

Write-Line "uvicorn started as pid $($process.Id)"

# Start-Process reports the launch, not the outcome: a bad argument or a
# missing module still returns a pid. Confirm it actually answers.
if (Wait-BooksHealthy -Port $Port -Probe $Probe -TimeoutSeconds 45) {
    Write-Line "Answering on http://${Probe}:${Port}/api/health"
} else {
    Write-Line "It did not answer within 45s. See $ErrFile"
}

if ($OpenReader) { Start-Process "http://${Probe}:${Port}/" }

# Stay alive alongside uvicorn so Task Scheduler reports the task as running
# and its restart-on-failure setting has something to watch.
#
# WaitForExit() rather than Wait-Process: the latter waits but leaves the
# Process object stale, so ExitCode reads back empty.
$process.WaitForExit()
$code = $process.ExitCode
Write-Line "uvicorn exited with code $code"
exit $code
