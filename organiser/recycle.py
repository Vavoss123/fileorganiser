"""Sending files to the Recycle Bin (Windows) or the Trash (macOS) -
recoverable, never a hard delete."""

from __future__ import annotations

import os
import subprocess
import sys


def send_to_recycle_bin(path: str) -> None:
    """Recycle one file, raising ``OSError`` if it did not end up in the bin.

    If Windows cannot recycle the file (too big for the bin, or a drive
    without one) it asks the user rather than deleting it outright.
    """
    if sys.platform == "darwin":
        _trash_on_mac(path)
        return
    if sys.platform != "win32":
        raise OSError("the Trash is only supported on Windows and macOS")

    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 0x0003
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040
    FOF_NOERRORUI = 0x0400
    FOF_WANTNUKEWARNING = 0x4000  # overrides NOCONFIRMATION if it can't recycle

    path = os.path.abspath(path)
    operation = SHFILEOPSTRUCTW(
        hwnd=None,
        wFunc=FO_DELETE,
        pFrom=path + "\0",  # the API wants a double-NUL-terminated list
        pTo=None,
        fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        | FOF_WANTNUKEWARNING,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError("Windows could not recycle the file (code 0x{:x})".format(result))
    if operation.fAnyOperationsAborted:
        raise OSError("cancelled")
    if os.path.exists(path):
        raise OSError("the file is still there")


def _trash_on_mac(path: str) -> None:
    """Ask Finder to move *path* to the Trash, so "Put Back" works as usual.

    The first time, macOS asks the user to let File Organiser control Finder.
    If they say no, the file stays where it is and this raises.
    """
    path = os.path.abspath(path)
    script = (
        "on run argv\n"
        "  tell application \"Finder\" to delete (POSIX file (item 1 of argv) as alias)\n"
        "end run"
    )
    result = subprocess.run(["osascript", "-e", script, path],
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise OSError("Finder could not move it to the Trash: "
                      + (result.stderr.strip() or "code {}".format(result.returncode)))
    if os.path.exists(path):
        raise OSError("the file is still there")
