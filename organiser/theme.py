"""Light and dark looks for the whole window.

Both are built on Tk's "clam" style, the only built-in one whose colours can
all be changed, so the two themes share one design: soft background, white
(or dark grey) cards, and a purple accent that matches the graph.

Besides recolouring the standard widgets, this defines a few named styles the
window uses: ``Accent.TButton`` for the main action, ``Card.TFrame`` and its
labels for summary cards, ``Title.TLabel``, ``Muted.TLabel`` and
``Link.TLabel``.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

CHOICES = {"system": "Same as Windows", "light": "Light", "dark": "Dark"}

LIGHT = {
    "bg": "#f4f5f7",
    "surface": "#ffffff",
    "field": "#ffffff",
    "hover": "#eceef2",
    "border": "#dcdfe5",
    "text": "#1f2328",
    "muted": "#646b76",
    "accent": "#6c5ce7",
    "accent_hover": "#5a4bd6",
    "accent_text": "#ffffff",
    "select": "#e7e3ff",
    "select_text": "#1f2328",
    "good": "#1a7f37",
    "bad": "#c4262e",
}
DARK = {
    "bg": "#1e1f22",
    "surface": "#2b2d31",
    "field": "#25272b",
    "hover": "#35373c",
    "border": "#3a3d44",
    "text": "#dcdde0",
    "muted": "#959aa3",
    "accent": "#7c6cf2",
    "accent_hover": "#8f81ff",
    "accent_text": "#ffffff",
    "select": "#3f3770",
    "select_text": "#ffffff",
    "good": "#3fb950",
    "bad": "#f85149",
}
FAMILY = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"


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


def _fonts() -> None:
    if sys.platform != "win32":
        return
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=FAMILY, size=10)
        except tk.TclError:
            pass


def apply(root: tk.Tk, mode: str) -> dict:
    """Restyle every ttk widget for *mode* ("light" or "dark").

    Returns the palette, for the few plain Tk widgets that need colouring by
    hand (the log, menus).
    """
    c = DARK if mode == "dark" else LIGHT
    _fonts()
    style = ttk.Style(root)
    style.theme_use("clam")
    _base(style, c)
    _named(style, c)
    root.configure(background=c["bg"])
    # Combobox drop-downs are plain Tk listboxes, styled through the option database.
    root.option_add("*TCombobox*Listbox.background", c["field"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["accent_text"])
    root.option_add("*TCombobox*Listbox.font", (FAMILY, 10))
    return c


def _base(style: ttk.Style, c: dict) -> None:
    style.configure(
        ".",
        background=c["bg"], foreground=c["text"], fieldbackground=c["field"],
        bordercolor=c["border"], darkcolor=c["bg"], lightcolor=c["bg"],
        troughcolor=c["field"], selectbackground=c["accent"],
        selectforeground=c["accent_text"], insertcolor=c["text"], focuscolor=c["accent"],
        arrowcolor=c["text"], font=(FAMILY, 10),
    )
    style.map(".", foreground=[("disabled", c["muted"])], background=[("disabled", c["bg"])])

    style.configure("TButton", background=c["surface"], padding=(12, 5),
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
                    focusthickness=0, focuscolor=c["surface"])
    style.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["select"]), ("active", c["hover"])],
              lightcolor=[("active", c["hover"])], darkcolor=[("active", c["hover"])],
              focuscolor=[("active", c["hover"])])

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground=c["field"], foreground=c["text"],
                        background=c["surface"], lightcolor=c["border"], padding=5,
                        darkcolor=c["border"], arrowcolor=c["muted"], insertcolor=c["text"],
                        selectbackground=c["select"], selectforeground=c["select_text"])
        style.map(widget, lightcolor=[("focus", c["accent"])], darkcolor=[("focus", c["accent"])],
                  bordercolor=[("focus", c["accent"])])
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
                        indicatorforeground=c["accent_text"], upperbordercolor=c["border"],
                        lowerbordercolor=c["border"], indicatormargin=(0, 0, 8, 0),
                        indicatorsize=15,
                        focusthickness=0)
        style.map(widget,
                  background=[("active", c["bg"])],
                  indicatorbackground=[("selected", c["accent"]), ("active", c["hover"])])

    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["text"], bordercolor=c["border"], rowheight=26,
                    lightcolor=c["border"], darkcolor=c["border"])
    style.map("Treeview", background=[("selected", c["select"])],
              foreground=[("selected", c["select_text"])])
    style.configure("Treeview.Heading", background=c["bg"], foreground=c["muted"],
                    bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                    relief="flat", padding=(6, 4), font=(FAMILY, 9))
    style.map("Treeview.Heading", background=[("active", c["hover"])])

    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=c["bg"], foreground=c["muted"],
                    bordercolor=c["bg"], lightcolor=c["bg"], darkcolor=c["bg"],
                    padding=(14, 6), font=(FAMILY, 10))
    style.map("TNotebook.Tab",
              background=[("selected", c["surface"]), ("active", c["hover"])],
              foreground=[("selected", c["text"]), ("active", c["text"])],
              bordercolor=[("selected", c["border"])],
              lightcolor=[("selected", c["accent"])])

    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["text"])
    style.configure("TProgressbar", background=c["accent"], troughcolor=c["hover"],
                    bordercolor=c["bg"], lightcolor=c["accent"], darkcolor=c["accent"],
                    thickness=6)
    style.configure("TScrollbar", background=c["hover"], troughcolor=c["bg"],
                    bordercolor=c["bg"], arrowcolor=c["muted"], lightcolor=c["hover"],
                    darkcolor=c["hover"], gripcount=0)
    style.map("TScrollbar", background=[("active", c["border"])])
    style.configure("TScale", background=c["accent"], troughcolor=c["hover"],
                    bordercolor=c["bg"], lightcolor=c["accent"], darkcolor=c["accent"],
                    sliderlength=14)
    style.map("TScale", background=[("active", c["accent_hover"])])
    style.configure("TMenubutton", background=c["bg"], foreground=c["muted"],
                    bordercolor=c["bg"], lightcolor=c["bg"], darkcolor=c["bg"],
                    arrowcolor=c["muted"], padding=(8, 4))
    style.map("TMenubutton", background=[("active", c["hover"])],
              foreground=[("active", c["text"])])


def _named(style: ttk.Style, c: dict) -> None:
    style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_text"],
                    bordercolor=c["accent"], lightcolor=c["accent"], darkcolor=c["accent"],
                    font=(FAMILY, 10, "bold"), padding=(18, 7), focuscolor=c["accent"])
    style.map("Accent.TButton",
              background=[("disabled", c["hover"]), ("pressed", c["accent_hover"]),
                          ("active", c["accent_hover"])],
              foreground=[("disabled", c["muted"])],
              bordercolor=[("disabled", c["border"])],
              lightcolor=[("disabled", c["hover"]), ("active", c["accent_hover"])],
              darkcolor=[("disabled", c["hover"]), ("active", c["accent_hover"])],
              focuscolor=[("active", c["accent_hover"])])
    style.configure("Small.TButton", padding=(8, 2), font=(FAMILY, 9))

    style.configure("Card.TFrame", background=c["surface"], bordercolor=c["border"],
                    lightcolor=c["border"], darkcolor=c["border"], relief="solid",
                    borderwidth=1)
    style.configure("Hover.Card.TFrame", bordercolor=c["accent"], lightcolor=c["accent"],
                    darkcolor=c["accent"])
    for name, extra in (("Card.TLabel", {}),
                        ("CardTitle.TLabel", {"foreground": c["muted"],
                                              "font": (FAMILY, 9)}),
                        ("CardValue.TLabel", {"font": (FAMILY, 15, "bold")}),
                        ("CardNote.TLabel", {"foreground": c["muted"], "font": (FAMILY, 9)}),
                        ("CardHeading.TLabel", {"font": (FAMILY, 11, "bold")}),
                        ("CardLink.TLabel", {"foreground": c["accent"]})):
        style.configure(name, background=c["surface"], foreground=c["text"])
        style.configure(name, **extra)
    style.configure("Card.TCheckbutton", background=c["surface"])
    style.map("Card.TCheckbutton", background=[("active", c["surface"])])
    style.configure("CardBody.TFrame", background=c["surface"])  # rows inside a card

    style.configure("Title.TLabel", font=(FAMILY, 17, "bold"))
    style.configure("Muted.TLabel", foreground=c["muted"])
    style.configure("Link.TLabel", foreground=c["accent"])
    style.configure("Tooltip.TLabel", background=c["text"], foreground=c["bg"],
                    padding=(8, 5), font=(FAMILY, 9))
