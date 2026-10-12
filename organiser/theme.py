"""Light and dark looks for the whole window.

Light uses Windows' own "vista" style. Dark uses Tk's "clam" style, the only
built-in one whose colours can all be changed, recoloured to match the graph.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

CHOICES = {"system": "Same as Windows", "light": "Light", "dark": "Dark"}

DARK = {
    "bg": "#1e1f22",
    "surface": "#2b2d31",
    "field": "#25272b",
    "hover": "#35373c",
    "border": "#3a3d44",
    "text": "#dcdde0",
    "muted": "#8b8f98",
    "accent": "#a28bfe",
    "select": "#3f3770",
    "good": "#3fb950",
    "bad": "#f85149",
}
LIGHT = {
    "bg": "SystemButtonFace",
    "field": "SystemWindow",
    "text": "SystemWindowText",
    "select": "SystemHighlight",
    "select_text": "SystemHighlightText",
    "good": "#1a7f37",
    "bad": "#a40e26",
}


def system_prefers_dark() -> bool:
    """True when Windows is set to dark mode for apps."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve(choice: str) -> str:
    """"light" or "dark" for a saved choice, which may be "system"."""
    if choice in ("light", "dark"):
        return choice
    return "dark" if system_prefers_dark() else "light"


def apply(root: tk.Tk, mode: str) -> dict:
    """Restyle every ttk widget for *mode* ("light" or "dark").

    Returns the palette, for the few plain Tk widgets that need colouring by
    hand (the log, for one).
    """
    style = ttk.Style(root)
    if mode == "dark":
        _dark(style)
        palette = DARK
        listbox = (DARK["field"], DARK["text"], DARK["select"], DARK["text"])
    else:
        for name in ("vista", "winnative", "default"):
            try:
                style.theme_use(name)
                break
            except tk.TclError:
                continue
        style.configure("Treeview", rowheight=24)
        palette = LIGHT
        listbox = (LIGHT["field"], LIGHT["text"], LIGHT["select"], LIGHT["select_text"])
    root.configure(background=palette["bg"])
    # Combobox drop-downs are plain Tk listboxes, styled through the option database.
    for option, value in zip(("background", "foreground", "selectBackground",
                              "selectForeground"), listbox):
        root.option_add("*TCombobox*Listbox." + option, value)
    return palette


def _dark(style: ttk.Style) -> None:
    c = DARK
    style.theme_use("clam")
    style.configure(
        ".",
        background=c["bg"], foreground=c["text"], fieldbackground=c["field"],
        bordercolor=c["border"], darkcolor=c["bg"], lightcolor=c["bg"],
        troughcolor=c["field"], selectbackground=c["select"], selectforeground=c["text"],
        insertcolor=c["text"], focuscolor=c["accent"], arrowcolor=c["text"],
    )
    style.map(".", foreground=[("disabled", c["muted"])],
              background=[("disabled", c["bg"])])

    style.configure("TButton", background=c["surface"], padding=(10, 3),
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"])
    style.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["select"]), ("active", c["hover"])],
              lightcolor=[("active", c["hover"])], darkcolor=[("active", c["hover"])])

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground=c["field"], foreground=c["text"],
                        background=c["surface"], lightcolor=c["border"],
                        darkcolor=c["border"], arrowcolor=c["text"], insertcolor=c["text"])
    style.map("TCombobox",
              fieldbackground=[("readonly", c["field"])],
              foreground=[("readonly", c["text"])],
              selectbackground=[("readonly", c["field"])],
              selectforeground=[("readonly", c["text"])],
              background=[("active", c["hover"])])
    style.map("TSpinbox", fieldbackground=[("readonly", c["field"])],
              foreground=[("readonly", c["text"])])

    for widget in ("TCheckbutton", "TRadiobutton"):
        style.configure(widget, background=c["bg"], indicatorbackground=c["field"],
                        indicatorforeground=c["text"], upperbordercolor=c["border"],
                        lowerbordercolor=c["border"])
        style.map(widget,
                  background=[("active", c["bg"])],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["hover"])],
                  indicatorforeground=[("selected", "#ffffff")])

    style.configure("Treeview", background=c["field"], fieldbackground=c["field"],
                    foreground=c["text"], bordercolor=c["border"], rowheight=24)
    style.map("Treeview", background=[("selected", c["select"])],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=c["surface"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"])
    style.map("Treeview.Heading", background=[("active", c["hover"])])

    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], tabmargins=(0, 2, 0, 0))
    style.configure("TNotebook.Tab", background=c["bg"], foreground=c["muted"],
                    bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                    padding=(12, 4))
    style.map("TNotebook.Tab",
              background=[("selected", c["surface"]), ("active", c["hover"])],
              foreground=[("selected", c["text"]), ("active", c["text"])],
              lightcolor=[("selected", c["accent"])])

    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["text"])
    style.configure("TProgressbar", background=c["accent"], troughcolor=c["field"],
                    bordercolor=c["border"], lightcolor=c["accent"], darkcolor=c["accent"])
    style.configure("TScrollbar", background=c["surface"], troughcolor=c["bg"],
                    bordercolor=c["bg"], arrowcolor=c["muted"], lightcolor=c["surface"],
                    darkcolor=c["surface"])
    style.map("TScrollbar", background=[("active", c["hover"])])
    style.configure("TScale", background=c["surface"], troughcolor=c["field"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"])
    style.map("TScale", background=[("active", c["accent"])])
