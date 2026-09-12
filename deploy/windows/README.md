# Running the reader as a Windows background service

Starts at logon, no console window, restarts cleanly when the code changes.

Adapted from the Ambience playbook (`docs/windows-autostart-playbook.md` in that
repository). The traps it documents are Windows-level, and every one of them
still applies here — read it before changing these scripts, because most of
them *fail silently and report success*.

```powershell
.\deploy\windows\Install-Autostart.ps1     # register it
Start-ScheduledTask -TaskName BookReader   # start now, don't wait for a reboot
.\deploy\windows\Restart-Books.ps1 -Rebuild   # after a change under web/
.\deploy\windows\Stop-Books.ps1            # stop now, keep the autostart
.\deploy\windows\Uninstall-Autostart.ps1   # stop it starting itself
```

| Script | Does |
| --- | --- |
| `Install-Autostart.ps1` | Registers a Task Scheduler task that runs at logon |
| `Start-Books.ps1` | The runner: reads config, guards against duplicates, rotates logs, launches uvicorn windowlessly |
| `Restart-Books.ps1` | Stops the real process and starts again, with optional `-Rebuild` / `-Install` |
| `Stop-Books.ps1` | Stops it now, leaving the autostart registered |
| `Uninstall-Autostart.ps1` | Removes the task |
| `BooksCommon.ps1` | Shared helpers, dot-sourced |

No admin rights at any point.

## What is different about this app

**It is the production shape, not the development one.** One uvicorn process
serves the API *and* `web\dist` together — there is no Vite and no proxy. A
change under `web/` is invisible until the bundle is rebuilt, which is what
`Restart-Books.ps1 -Rebuild` is for. `./dev.sh` remains the way to work on it.

**Port 8770.** Not 8000 (an unrelated service on this machine), not 8001 (the
development API), not 3000 (Vite). The always-on copy must not fight the one
you are editing against, and the runner *declines* rather than fighting if the
port is taken.

**It binds 0.0.0.0, not localhost.** The point of this app is reading on a
tablet that is not this machine. That is only defensible because the reader now
authenticates: there is no guest, every request names a profile, and a profile
with a PIN must present a device token minted by that PIN.

> A profile **without** a PIN is an open door with a name on it. Set one before
> trusting this on a network you share. `BOOKS_BIND=127.0.0.1` in `.env` keeps
> the library on this machine instead.

**There is no virtualenv here**, so the playbook's second trap bites harder than
it did for Ambience: the running image is
`C:\...\WindowsApps\pythonw3.13.exe`, and nothing on the command line would name
this repository. The runner therefore passes uvicorn `--app-dir <repo>`, which
it needs anyway to import `api.main`, and which makes the ownership check
possible at all. Both halves are required before anything is killed — the
repository path *and* `api.main:app` — because a restart that shot down the
wrong listener is far worse than one that fails.

**`/api/health` is the only endpoint that asks nobody who they are.** Every
other route needs a profile and a token, and a 401 is not the same as "down".

## Settings

`.env`, both optional:

```
BOOKS_PORT=8770
BOOKS_BIND=0.0.0.0
```

The port registered into the task wins over `.env`, so the restart scripts stay
pointed at whatever the installer chose.

## Logs

The task has no console to print to. Three files, rotated at 5MB, because
`Start-Process -RedirectStandardOutput` **truncates** its target — a shared file
would erase everything the wrapper wrote the moment the server launched.

| File | Contents |
| --- | --- |
| `logs\autostart.log` | What the wrapper decided |
| `logs\books.err.log` | The server itself — where uvicorn logs |
| `logs\books.log` | uvicorn stdout, usually quiet |

## Verified on this machine

Everything below was run, not assumed:

- [x] Task registers without an admin prompt
- [x] `Start-ScheduledTask` brings it up; `/api/health` answers `{"ok":true,"books":275}`
- [x] Launches under `pythonw3.13.exe`, so no console window appears
- [x] Running the runner a second time declines: *"Port 8770 is already in use by pythonw3.13 (pid 14348); not starting a second copy"*
- [x] Restart prints a **different** pid (14348 → 6012 → 13296 → 5848)
- [x] A marker added to `/api/health` appeared after a restart and was gone after reverting — the restart genuinely loads new code
- [x] Logs contain the wrapper's lines *and* uvicorn's startup output
- [ ] Reboot — the only test of the trigger itself, and the one you have to do

## Not done

No tray icon. The playbook's is optional, `pystray` and `Pillow` are not
installed here, and a books tray wants its own design — colour for reachable /
working / error, tooltip for the count. Worth having; not written yet.
