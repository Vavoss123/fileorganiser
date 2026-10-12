"""The differences between Windows and macOS, in one place.

Names the user sees (Explorer or Finder, Recycle Bin or Trash), how the mouse
reports right-clicks and scrolling, and the keyboard modifier for shortcuts.
"""

from __future__ import annotations

import sys

MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"

FILE_MANAGER = "Finder" if MAC else "Explorer" if WINDOWS else "the file manager"
BIN = "Recycle Bin" if WINDOWS else "Trash"
#: Shown in tooltips and the welcome screen: "⌘O" on a Mac, "Ctrl+O" elsewhere.
MOD = "⌘" if MAC else "Ctrl+"
#: The Tk modifier behind MOD.
TK_MOD = "Command" if MAC else "Control"

#: Mouse events that mean "right-click". On a Mac, Tk calls the right button
#: 2, and Control-click means the same thing.
RIGHT_CLICK = ("<Button-2>", "<Button-3>", "<Control-Button-1>") if MAC else ("<Button-3>",)


def bind_right_click(widget, handler) -> None:
    for sequence in RIGHT_CLICK:
        widget.bind(sequence, handler)


def wheel_steps(event) -> float:
    """How far the wheel turned, in notches (positive is away from the user).

    Windows reports 120 per notch. A Mac reports small numbers, many times a
    second on a trackpad, so each one counts for a fraction of a notch.
    """
    if MAC:
        return event.delta / 4
    return event.delta / 120
