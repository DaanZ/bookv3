"""A notification-area icon for the book reader, so its state is glanceable.

Windows tucks new icons into the overflow ("hidden icons") tray; drag it onto the
taskbar to keep it visible.

**The icon encodes state, not content.** Sixteen pixels cannot carry a book title
legibly, and the question a tray icon actually answers is *is it up, is it busy, does
it need me*. So that is what the colour says, and the words go in the tooltip and the
menu, where there is room:

    orange  the app's own mark: up, and either idle or summarising (a pale bar
            under the book says which)
    red     a summarising job failed and is waiting for you
    grey    the reader is unreachable

The silhouette is always the mark, and only the ground changes. Two of the four states
keep the brand colour on purpose: "up and idle" and "up and working" are not problems,
and an icon that only looks like itself when nothing is happening is one you stop
recognising in a tray that also holds Ambience.

**It reads counts, not titles.** `/api/health` is the one endpoint that asks nobody
who they are, which is exactly why it must not say which book is being summarised.
Everything else needs a profile and a device token, and this process has neither —
deliberately: a tray icon is a window onto the service, not a reader of the library.

Run it by hand with `python scripts/tray.py`, or let the autostart launch it alongside
the server (`deploy\\windows\\Install-Autostart.ps1 -WithTray`). Quitting the tray
leaves the reader running; it is a window onto the service, not the service itself.

Needs `pystray` and `Pillow`, which are not in requirements.txt because the Linux
deploy has no notification area:

    pip install pystray pillow
"""
import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]

POLL_SECONDS = 20
REQUEST_TIMEOUT = 8

# The mark's own two colours, read out of the icon file rather than guessed:
# #EF8A1E ground, #04181B ink. The tray recolours the first and never the second.
BRAND_GROUND = (239, 138, 30)
BRAND_INK = (4, 24, 27)

# The ground carries the state. At sixteen pixels a corner badge is a handful of
# pixels and the colour of the whole shape is the only thing that reads at a glance —
# so the silhouette stays the app's mark and the background says how it is doing.
#
# Two of the four are the brand colour on purpose. "Up and idle" and "up and working"
# are not problems, and an icon that only looks like itself when nothing is happening
# is an icon you stop recognising. Only the two states worth interrupting for take a
# colour of their own.
COLOURS = {
    "unreachable": (110, 110, 110),
    "failed": (200, 60, 50),
    "working": BRAND_GROUND,
    "idle": BRAND_GROUND,
}

ICON_PATH = REPO_ROOT / "assets" / "bookv3.ico"
FALLBACK_PATH = REPO_ROOT / "web" / "public" / "assets" / "favicon-512.png"

_base_icon = None


def _base():
    """The app mark, the same file a window or the taskbar would show. Loaded once."""
    global _base_icon
    if _base_icon is None:
        from PIL import Image, ImageDraw

        for path in (ICON_PATH, FALLBACK_PATH):
            try:
                image = Image.open(path)
                _base_icon = image.convert("RGBA").resize((64, 64), Image.LANCZOS)
                return _base_icon.copy()
            except Exception:
                continue
        # No icon file at all: a plain rounded square beats no tray.
        fallback = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(fallback).rounded_rectangle((2, 2, 61, 61), 14, fill=BRAND_GROUND + (255,))
        _base_icon = fallback
    return _base_icon.copy()


class TrayState:
    """The last reading, shared between the poller and the menu callbacks."""

    def __init__(self):
        self.lock = threading.Lock()
        self.health = None
        self.error = None

    def update(self, health=None, error=None):
        with self.lock:
            self.health = health
            self.error = error

    def read(self):
        with self.lock:
            return self.health, self.error


def _luminance(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def make_icon(colour, working=False):
    """The mark, with `colour` swapped in for its orange ground.

    Recoloured per pixel rather than by pasting a shape, so the rounded corners and the
    curve of the book keep their antialiasing: an edge pixel is part ground and part
    ink, and it has to stay part ground and part ink after the swap or the whole mark
    grows a fringe. How much ink a pixel holds is read from its luminance, because the
    two brand colours are far enough apart for that to be unambiguous.
    """
    from PIL import Image, ImageDraw

    image = _base()
    if colour == BRAND_GROUND and not working:
        return image

    ink_lum = _luminance(BRAND_INK)
    ground_lum = _luminance(BRAND_GROUND)
    span = ground_lum - ink_lum

    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            # 1 where the pixel is ink, 0 where it is ground, between on an edge.
            ink = (ground_lum - _luminance((r, g, b))) / span
            ink = 0.0 if ink < 0 else (1.0 if ink > 1 else ink)
            pixels[x, y] = (
                round(BRAND_INK[0] * ink + colour[0] * (1 - ink)),
                round(BRAND_INK[1] * ink + colour[1] * (1 - ink)),
                round(BRAND_INK[2] * ink + colour[2] * (1 - ink)),
                a,
            )

    if working:
        # A pale bar under the book, which reads at 16px where a spinner turns to mush.
        ImageDraw.Draw(image).rounded_rectangle((14, 50, 49, 56), 3, fill=(255, 248, 238, 235))
    return image


def describe(health, error, base):
    """(colour key, working, tooltip). Tooltips cap around 128 characters."""
    if error or health is None:
        return "unreachable", False, f"Book reader - unreachable\n{error or 'no reading yet'}"[:127]

    books = health.get("books", 0)
    jobs = health.get("jobs") or {}
    running = jobs.get("running", 0)
    failed = jobs.get("failed", 0)

    if failed:
        key = "failed"
    elif running:
        key = "working"
    else:
        key = "idle"

    lines = [f"Book reader - {books} books"]
    if running:
        lines.append(f"summarising {running} book{'s' if running != 1 else ''}")
    if failed:
        lines.append(f"{failed} job{'s' if failed != 1 else ''} failed - open the library")
    if not running and not failed:
        lines.append(base)
    return key, bool(running), "\n".join(lines)[:127]


class Tray:
    def __init__(self, port, bind="127.0.0.1"):
        self.base = f"http://{bind}:{port}"
        self.state = TrayState()
        self.icon = None
        self._stop = threading.Event()

    # --- API ------------------------------------------------------------

    def poll_once(self):
        try:
            response = requests.get(f"{self.base}/api/health", timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            self.state.update(health=response.json())
        except Exception as exception:
            self.state.update(error=type(exception).__name__)

    def _poll_loop(self):
        while not self._stop.is_set():
            self.poll_once()
            self.refresh()
            self._stop.wait(POLL_SECONDS)

    def refresh(self):
        if self.icon is None:
            return
        health, error = self.state.read()
        key, working, tooltip = describe(health, error, self.base)
        self.icon.icon = make_icon(COLOURS[key], working)
        self.icon.title = tooltip
        try:
            self.icon.update_menu()
        except Exception:
            # Menu updates are cosmetic; never let one kill the poller.
            pass

    # --- actions --------------------------------------------------------

    def open_reader(self, *_):
        webbrowser.open(self.base + "/")

    def open_library(self, *_):
        # The library screen is inside the app rather than at its own URL, so this
        # opens the reader and leaves the last step to the reader. Better than a link
        # that 404s because it named a route the SPA does not have.
        webbrowser.open(self.base + "/")

    def restart_service(self, *_):
        script = REPO_ROOT / "deploy" / "windows" / "Restart-Books.ps1"

        def run():
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-WindowStyle", "Hidden", "-File", str(script)],
                cwd=str(REPO_ROOT), capture_output=True,
            )
            # The server is down for a moment; a few polls catch it coming back.
            for _ in range(12):
                time.sleep(5)
                self.poll_once()
                self.refresh()
                health, _error = self.state.read()
                if health:
                    break

        threading.Thread(target=run, daemon=True).start()

    def quit(self, *_):
        self._stop.set()
        if self.icon:
            self.icon.stop()

    # --- menu -----------------------------------------------------------

    def _headline(self, *_):
        health, error = self.state.read()
        if error or not health:
            return "Not reachable"
        jobs = health.get("jobs") or {}
        if jobs.get("failed"):
            return f"{jobs['failed']} failed - needs attention"
        if jobs.get("running"):
            return f"Summarising {jobs['running']}"
        return f"{health.get('books', 0)} books - idle"

    def _detail(self, *_):
        health, error = self.state.read()
        if error or not health:
            return f"{self.base} - {error or 'no reading'}"
        return self.base

    def build_menu(self):
        from pystray import Menu, MenuItem

        return Menu(
            MenuItem(self._headline, None, enabled=False),
            MenuItem(self._detail, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Open the reader", self.open_reader, default=True),
            Menu.SEPARATOR,
            MenuItem("Restart the reader", self.restart_service),
            MenuItem("Quit tray (the reader keeps running)", self.quit),
        )

    def run(self):
        import pystray

        self.poll_once()
        health, error = self.state.read()
        key, working, tooltip = describe(health, error, self.base)

        self.icon = pystray.Icon(
            "bookv3",
            icon=make_icon(COLOURS[key], working),
            title=tooltip,
            menu=self.build_menu(),
        )
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.icon.run()


def main():
    parser = argparse.ArgumentParser(description="Notification-area icon for the book reader.")
    parser.add_argument("--port", type=int, default=8770)
    # 0.0.0.0 is what the server binds; it is not an address you can ask.
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    bind = "127.0.0.1" if args.bind in ("0.0.0.0", "") else args.bind

    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("The tray needs pystray and Pillow:  pip install pystray pillow", file=sys.stderr)
        return 1

    Tray(args.port, bind).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
