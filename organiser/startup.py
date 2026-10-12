"""What happens when the user signs in to Windows: nothing, one tidy, or the tray.

Uses the per-user ``Run`` key, so no admin rights are needed and the entry
shows up (and can be switched off) in Task Manager's Startup apps.
"""

from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FileOrganiser"

#: Sign-in mode -> command-line flag.
MODES = {"auto": "--auto", "tray": "--tray"}


def command_for(mode: str) -> str:
    """The command line for *mode*, whether running as the exe or from source."""
    flag = MODES[mode]
    if getattr(sys, "frozen", False):
        return '"{}" {}'.format(sys.executable, flag)
    folder, exe = os.path.split(sys.executable)
    windowless = os.path.join(folder, "pythonw.exe") if exe.lower() == "python.exe" else sys.executable
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    return '"{}" "{}" {}'.format(windowless, script, flag)


def current_mode(name: str = VALUE_NAME) -> str:
    """"off", "auto" or "tray"."""
    if sys.platform != "win32":
        return "off"
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            command, _type = winreg.QueryValueEx(key, name)
    except OSError:
        return "off"
    for mode, flag in MODES.items():
        if command.rstrip().endswith(flag):
            return mode
    return "off"


def set_mode(mode: str, name: str = VALUE_NAME) -> None:
    import winreg

    if mode == "off":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command_for(mode))
