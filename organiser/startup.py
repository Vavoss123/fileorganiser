"""What happens when the user signs in: nothing, one tidy, or the tray.

On Windows this is the per-user ``Run`` key, so no admin rights are needed and
the entry shows up (and can be switched off) in Task Manager's Startup apps.

On macOS it is a launch agent in ``~/Library/LaunchAgents``, which macOS runs
at login and lists under System Settings > General > Login Items. Only "tidy
once" is offered there; the tray watcher is Windows-only.
"""

from __future__ import annotations

import os
import plistlib
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FileOrganiser"
AGENT_LABEL = "io.github.vavoss123.fileorganiser"

#: Sign-in mode -> command-line flag.
MODES = {"auto": "--auto", "tray": "--tray"}


def arguments_for(mode: str) -> list[str]:
    """The program and arguments for *mode*, whether built or run from source."""
    flag = MODES[mode]
    if getattr(sys, "frozen", False):
        return [sys.executable, flag]
    folder, exe = os.path.split(sys.executable)
    windowless = os.path.join(folder, "pythonw.exe") if exe.lower() == "python.exe" else sys.executable
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    return [windowless, script, flag]


def command_for(mode: str) -> str:
    """:func:`arguments_for` as one Windows command line."""
    return " ".join('"{}"'.format(part) if part.startswith(("/", "\\")) or ":" in part
                    or " " in part else part for part in arguments_for(mode))


def _agent_path(name: str) -> str:
    label = AGENT_LABEL if name == VALUE_NAME else "{}.{}".format(AGENT_LABEL, name.lower())
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", label + ".plist")


def current_mode(name: str = VALUE_NAME) -> str:
    """"off", "auto" or "tray"."""
    if sys.platform == "darwin":
        try:
            with open(_agent_path(name), "rb") as handle:
                arguments = plistlib.load(handle).get("ProgramArguments", [])
        except (OSError, ValueError):
            return "off"
        return next((mode for mode, flag in MODES.items() if flag in arguments), "off")
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
    if sys.platform == "darwin":
        _set_mac_mode(mode, name)
        return
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


def _set_mac_mode(mode: str, name: str) -> None:
    path = _agent_path(name)
    if mode == "off":
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    agent = {
        "Label": os.path.splitext(os.path.basename(path))[0],
        "ProgramArguments": arguments_for(mode),
        "RunAtLoad": True,
        "ProcessType": "Background",
    }
    with open(path, "wb") as handle:
        plistlib.dump(agent, handle)
