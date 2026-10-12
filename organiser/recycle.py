"""Sending files to the Windows Recycle Bin - recoverable, never a hard delete."""

from __future__ import annotations

import os
import sys


def send_to_recycle_bin(path: str) -> None:
    """Recycle one file, raising ``OSError`` if it did not end up in the bin.

    If Windows cannot recycle the file (too big for the bin, or a drive
    without one) it asks the user rather than deleting it outright.
    """
    if sys.platform != "win32":
        raise OSError("the Recycle Bin is only available on Windows")

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
