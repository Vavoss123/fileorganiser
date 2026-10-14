"""Clearing away what the app leaves on disk, so it doesn't build up.

Run once at every start (:func:`run`). Each step is careful to leave alone
anything still in use, and none of it ever touches the user's own files.

* Unpacked copies. The single-file Windows app unpacks itself into
  ``%LOCALAPPDATA%\\FileOrganiser\\runtime\\_MEI…`` each time it starts
  (``build.bat`` points it there) and removes that copy when it closes. A
  copy that was force-closed or crashed leaves it behind, about 60 MB.
* Downloaded updates in the temp folder, about 20 MB each.
* Undo history older than ``journal_days`` (180 by default).
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile
import time

from . import config, updates

UPDATE_DOWNLOADS = "FileOrganiser-update-*"


def run(settings: dict | None = None) -> None:
    """Every clean-up step. Failures are ignored: this must never stop the app."""
    settings = settings or config.load()
    for step in (unpacked_copies, update_downloads, updates.clean_up,
                 lambda: old_journals(settings.get("journal_days", 180))):
        try:
            step()
        except Exception:
            pass


def unpacked_copies(folder: str | None = None, current: str | None = None) -> list[str]:
    """Remove leftover ``_MEI…`` folders in our runtime folder; return them.

    A folder still in use (this copy, or the tray running alongside the window)
    can't be renamed on Windows, because its DLLs are open, so trying a rename
    first tells used from abandoned without guessing.
    """
    folder = folder or config.runtime_dir()
    current = os.path.normcase(os.path.abspath(current or getattr(sys, "_MEIPASS", "") or "-"))
    removed = []
    for path in glob.glob(os.path.join(folder, "_MEI*")):
        if os.path.normcase(os.path.abspath(path)) == current or not os.path.isdir(path):
            continue
        doomed = path + ".old"
        try:
            os.rename(path, doomed)
        except OSError:
            continue  # in use by a running copy
        shutil.rmtree(doomed, ignore_errors=True)
        removed.append(path)
    return removed


def update_downloads(folder: str | None = None, min_age: float = 60) -> list[str]:
    """Remove downloaded updates more than *min_age* seconds old (an installer
    that has only just started the new version may still be finishing)."""
    removed = []
    for path in glob.glob(os.path.join(folder or tempfile.gettempdir(), UPDATE_DOWNLOADS)):
        try:
            if time.time() - os.path.getmtime(path) < min_age:
                continue
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            removed.append(path)
    return removed


def old_journals(days: float = 180, folder: str | None = None,
                 now: float | None = None) -> list[str]:
    """Remove undo records older than *days* (0 keeps them all); return them."""
    if not days:
        return []
    folder = folder or config.journal_dir()
    cutoff = (time.time() if now is None else now) - days * 86400
    removed = []
    for path in glob.glob(os.path.join(folder, "*")):
        name = os.path.basename(path)
        if not os.path.isfile(path) or not name.endswith((".json", ".jsonl", ".undone")):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed.append(path)
        except OSError:
            pass
    return removed
