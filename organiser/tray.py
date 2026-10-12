"""A tray icon that keeps the folder tidy while it runs.

Every minute it does what the automatic run does - scan with the saved
settings and move what the plan says - so new downloads are filed once they
have settled. Like every run it only moves files and can be undone.

Needs ``pystray`` and Pillow; :func:`available` says whether they are there.
"""

from __future__ import annotations

import subprocess
import sys
import threading

from . import auto, config

INTERVAL = 60  # seconds between checks
MUTEX_NAME = "Local\\FileOrganiserTray"


def available() -> bool:
    try:
        import pystray  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _already_running() -> bool:
    """Hold a named mutex for the life of the process; True if someone else has it."""
    if sys.platform != "win32":
        return False
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    _already_running.handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def _open_window() -> None:
    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        import os

        app = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
        command = [sys.executable, app]
    subprocess.Popen(command)


class TrayWatcher:
    def __init__(self) -> None:
        import pystray

        from .icon import make_image

        self.watching = True
        self.forced = False
        self.wake = threading.Event()
        self.stopping = False
        self.icon = pystray.Icon(
            "FileOrganiser",
            make_image(64),
            "File Organiser",
            menu=pystray.Menu(
                pystray.MenuItem("Open File Organiser", lambda: _open_window(), default=True),
                pystray.MenuItem("Tidy now", self._tidy_now),
                pystray.MenuItem(
                    "Keep tidying", self._toggle, checked=lambda _item: self.watching
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        self.icon.run(setup=self._setup)

    def _setup(self, icon) -> None:
        # Only start tidying once the icon exists, so the first notification
        # has somewhere to appear.
        icon.visible = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self.stopping:
            if self.watching or self.forced:
                self.forced = False
                self._tidy()
            self.wake.wait(INTERVAL)
            self.wake.clear()

    def _tidy(self) -> None:
        try:
            report = auto.run(config.load(), quiet=True)
        except Exception as exc:  # keep watching through an awkward moment
            auto._append_log(["tray: {}".format(exc)])
            return
        if report and report.moved:
            self.icon.title = "File Organiser: filed {} file(s) just now".format(len(report.moved))
            try:
                self.icon.notify(
                    "Filed {} new file(s). Undo… in the app puts them back.".format(
                        len(report.moved)
                    ),
                    "File Organiser",
                )
            except Exception:
                pass

    def _tidy_now(self) -> None:
        self.forced = True  # even while paused
        self.wake.set()

    def _toggle(self) -> None:
        self.watching = not self.watching
        self.icon.title = "File Organiser" + ("" if self.watching else " (paused)")
        if self.watching:
            self.wake.set()

    def _quit(self) -> None:
        self.stopping = True
        self.wake.set()
        self.icon.stop()


def run() -> None:
    if _already_running():
        return
    TrayWatcher().run()
