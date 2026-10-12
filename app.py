"""File Organiser - a small Windows and macOS app for tidying a cluttered folder.

The app always shows you a plan first. Scanning and hashing never change
anything on disk; files move only when you press "Tidy", and
that run can be undone. Nothing is ever permanently deleted: duplicates go to
the Recycle Bin (the Trash on a Mac), and only when you ask.
"""

from __future__ import annotations

import datetime
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organiser import apply as apply_module  # noqa: E402
from organiser import auto, cleanup, config, duplicates, plan as plan_module, rules, scan, startup, tray  # noqa: E402,E501
from organiser import system, theme, updates  # noqa: E402
from organiser.graphview import GraphView  # noqa: E402

CHECK = "✓"
DATE_CHOICES = {"off": "Off", "year": "By year", "month": "By year and month"}
STARTUP_CHOICES = {
    "off": "Do nothing",
    "auto": "Tidy once",
    "tray": "Keep tidying from the tray",
}
PAD = 10

#: Keyboard shortcuts, as shown in the welcome screen: (keys, what they do).
SHORTCUTS = (
    (system.MOD + "O", "Choose a folder"),
    ("F5", "Scan the folder"),
    ("Esc", "Stop a scan"),
    (system.MOD + ("Return" if system.MAC else "Enter"), "Tidy the ticked files"),
    (system.MOD + "Z", "Undo a tidy"),
    ("F1", "Show the welcome screen again"),
)


class ScanCancelled(Exception):
    """Raised inside the scan thread when the user presses Cancel."""
WINDOW_PAD = 18


def plural(count: int, one: str, many: str | None = None) -> str:
    """"1 file", "3 files"."""
    return "{:,} {}".format(count, one if count == 1 else (many or one + "s"))


class Tooltip:
    """A short explanation that appears when the mouse rests on a widget."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 450) -> None:
        self.widget, self.text, self.delay = widget, text, delay
        self.window: tk.Toplevel | None = None
        self.pending: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._hide()
        self.pending = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        self.pending = None
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry("+{}+{}".format(x, y))
        ttk.Label(self.window, text=self.text, style="Tooltip.TLabel", wraplength=320,
                  justify="left").pack()

    def _hide(self, _event=None) -> None:
        if self.pending:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


def human_size(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def timestamp(mtime: float) -> str:
    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def display_folder(path: str, root: str | None) -> str:
    """The folder part of *path*, shortened against the scanned root."""
    folder = os.path.dirname(path)
    if root:
        try:
            relative = os.path.relpath(folder, root)
        except ValueError:  # different drive
            return folder
        if not relative.startswith(".."):
            return "(this folder)" if relative == "." else relative
    return folder


def reveal(path: str) -> None:
    """Show a file in Explorer or Finder."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,{}".format(os.path.normpath(path))])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass


def open_path(path: str, parent: tk.Misc | None = None) -> None:
    """Open a file in its usual program, or a folder in Explorer or Finder."""
    if not os.path.exists(path):
        messagebox.showinfo(
            "File Organiser",
            "This isn't there any more:\n{}\n\nIt may have been moved or deleted since "
            "the scan. Press Scan to refresh.".format(path),
            parent=parent,
        )
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opening the user's own file is the point
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        messagebox.showerror("File Organiser", "Couldn't open it:\n{}".format(exc), parent=parent)


class OrganiserApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=WINDOW_PAD)
        self.master = master
        self.settings = config.load()
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.plan: plan_module.Plan | None = None
        self.duplicate_groups: list[duplicates.DuplicateGroup] = []
        self.version_groups: list[duplicates.VersionGroup] = []
        self.old_installers: list[scan.FileInfo] = []
        self.move_for_item: dict[str, plan_module.Move] = {}
        self.item_for_move: dict[int, str] = {}
        self.children_of: dict[str, list[str]] = {}
        self.path_for_item: dict[str, str] = {}

        self.folder_var = tk.StringVar(value=self.settings["folder"])
        self.depth_var = tk.IntVar(value=self.settings["max_depth"])
        self.libraries_var = tk.BooleanVar(value=self.settings["route_to_libraries"])
        self.other_var = tk.BooleanVar(value=self.settings["include_other"])
        self.duplicates_var = tk.BooleanVar(value=self.settings["find_duplicates"])
        self.date_var = tk.StringVar(
            value=DATE_CHOICES.get(self.settings.get("date_folders"), DATE_CHOICES["off"])
        )
        self.startup_var = tk.StringVar(value=STARTUP_CHOICES[startup.current_mode()])
        self.status_var = tk.StringVar(
            value="Choose a folder, then press Scan folder. Nothing changes until you press Tidy."
        )
        self.advanced_var = tk.BooleanVar(value=bool(self.settings.get("advanced")))
        self.theme_var = tk.StringVar(
            value=theme.CHOICES.get(self.settings.get("theme"), theme.CHOICES["system"])
        )
        self.show_graph_after_scan = False
        self.cancel_scan_event = threading.Event()
        self.updates_var = tk.BooleanVar(value=bool(self.settings.get("check_updates", True)))
        self.palette = theme.apply(master, theme.resolve(self.settings.get("theme", "system")))

        self.pack(fill="both", expand=True)
        self._build()
        self._colour_plain_widgets()
        self._bind_shortcuts()
        self.after(100, self._drain_events)
        if self.updates_var.get():
            threading.Thread(target=self._update_worker, daemon=True).start()
        if not self.settings.get("welcomed"):
            self.after(400, self.show_welcome)

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build_header().grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._build_folder_card().grid(row=1, column=0, sticky="ew")
        self._build_summary().grid(row=2, column=0, sticky="ew", pady=(12, 12))

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=3, column=0, sticky="nsew")
        self.graph_view = GraphView(
            self, on_toggle=self._toggle_move, on_reveal=reveal,
            on_open=lambda path: open_path(path, self),
            settings=self.settings.get("graph"),
            mode=theme.resolve(self.settings.get("theme", "system")),
        )
        self.tabs.add(self.graph_view, text="Map")
        self.plan_page = self._build_plan_tab()
        self.tabs.add(self.plan_page, text="Files to move")
        self.duplicates_page = self._build_duplicates_tab()
        self.tabs.add(self.duplicates_page, text="Duplicates")
        self.versions_page = self._build_versions_tab()
        self.tabs.add(self.versions_page, text="Similar names")
        self.installers_page = self._build_installers_tab()
        self.tabs.add(self.installers_page, text="Old installers")
        self.log_page = self._build_log_tab()
        self.tabs.add(self.log_page, text="Activity")

        footer = ttk.Frame(self)
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress = ttk.Progressbar(footer, mode="determinate", length=220)
        self.progress.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.progress.grid_remove()
        self.undo_button = ttk.Button(
            footer, text="Undo a tidy…", command=self.undo_last, state="disabled"
        )
        self.undo_button.grid(row=0, column=1, rowspan=2, padx=8)
        Tooltip(self.undo_button, "Put files back where they were before an earlier tidy.")
        self.apply_button = ttk.Button(
            footer, text="Tidy files", command=self.apply_plan, state="disabled",
            style="Accent.TButton",
        )
        self.apply_button.grid(row=0, column=2, rowspan=2)
        if apply_module.list_journals():
            self.undo_button.configure(state="normal")
        self._show_advanced(self.advanced_var.get())

    def _build_header(self) -> ttk.Frame:
        header = ttk.Frame(self)
        header.columnconfigure(1, weight=1)
        try:  # the app's own icon, when Pillow is there
            from PIL import ImageTk

            from organiser.icon import make_image

            self._header_icon = ImageTk.PhotoImage(make_image(44))
            ttk.Label(header, image=self._header_icon).grid(row=0, column=0, rowspan=2,
                                                            padx=(0, 12))
        except Exception:
            pass
        ttk.Label(header, text="File Organiser", style="Title.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            header, style="Muted.TLabel",
            text="Sorts a messy folder into tidy ones. Nothing is deleted, "
                 "and you can undo every tidy.",
        ).grid(row=1, column=1, columnspan=2, sticky="w")

        right = ttk.Frame(header)
        right.grid(row=0, column=2, sticky="ne")
        self.update_link = ttk.Label(right, style="Link.TLabel", cursor="hand2")
        help_button = ttk.Button(right, text="?  How it works", style="Small.TButton",
                                 command=self.show_welcome)
        help_button.pack(side="right")
        Tooltip(help_button, "A quick tour of the app, and its keyboard shortcuts. (F1)")
        look = ttk.Button(right, text="◐  Theme", style="Small.TButton")
        look.configure(command=lambda: self._theme_popup(look))
        look.pack(side="right", padx=(0, 6))
        return header

    def _update_worker(self) -> None:
        found = updates.newer_release()
        if found:
            self.events.put(("update", found))

    def _show_update(self, tag: str, url: str) -> None:
        self.update_link.configure(text="✦ Version {} is out, get it here".format(
            tag.lstrip("v")))
        self.update_link.bind("<Button-1>", lambda _e: webbrowser.open(url))
        self.update_link.pack(side="right", padx=(0, 14))
        Tooltip(self.update_link, "Opens the download page on GitHub. You're on version "
                                  "{}.".format(updates.__version__))

    def show_welcome(self) -> None:
        dialog = WelcomeDialog(self.master, self.palette)
        self.master.wait_window(dialog)
        if not self.settings.get("welcomed"):
            self.settings["welcomed"] = True
            config.save(self.current_settings())

    def _bind_shortcuts(self) -> None:
        root = self.master
        mod = system.TK_MOD
        root.bind("<{}-o>".format(mod), lambda _e: self.browse())
        root.bind("<{}-O>".format(mod), lambda _e: self.browse())
        root.bind("<F5>", lambda _e: self.start_scan(show_graph=True))
        root.bind("<Escape>", lambda _e: self.cancel_scan())
        root.bind("<{}-Return>".format(mod), lambda _e: self.apply_plan())
        root.bind("<{}-z>".format(mod), lambda _e: self.undo_last())
        root.bind("<F1>", lambda _e: self.show_welcome())

    def _theme_popup(self, button: ttk.Button) -> None:
        menu = tk.Menu(self, tearoff=False, **self._menu_colours())
        for label in theme.CHOICES.values():
            menu.add_radiobutton(label=label, variable=self.theme_var, value=label,
                                 command=self._change_theme)
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def _build_folder_card(self) -> ttk.Frame:
        card = ttk.Frame(self, style="Card.TFrame", padding=(16, 14))
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Which folder needs tidying?", style="CardHeading.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        entry = ttk.Entry(card, textvariable=self.folder_var)
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        entry.bind("<Return>", lambda _e: self.start_scan(show_graph=True))
        ttk.Button(card, text="Browse…", command=self.browse).grid(
            row=1, column=1, padx=8, pady=(8, 0)
        )
        self.scan_button = ttk.Button(
            card, text="Scan folder", style="Accent.TButton",
            command=lambda: self.start_scan(show_graph=True),
        )
        self.scan_button.grid(row=1, column=2, pady=(8, 0))
        Tooltip(self.scan_button, "Looks through the folder and shows what would go where. "
                                  "Nothing is moved yet.")

        picks = ttk.Frame(card, style="CardBody.TFrame")
        picks.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(picks, text="Quick picks:", style="CardNote.TLabel").pack(side="left")
        for name in ("Downloads", "Desktop", "Documents", "Pictures"):
            path = os.path.join(os.path.expanduser("~"), name)
            if os.path.isdir(path):
                link = ttk.Label(picks, text=name, style="CardLink.TLabel", cursor="hand2")
                link.pack(side="left", padx=(10, 0))
                link.bind("<Button-1>", lambda _e, p=path: self.folder_var.set(p))
        self.advanced_link = ttk.Label(picks, style="CardLink.TLabel", cursor="hand2")
        self.advanced_link.pack(side="right")
        self.advanced_link.bind(
            "<Button-1>", lambda _e: self._show_advanced(not self.advanced_var.get())
        )

        self.advanced = self._build_options(card)
        self.advanced.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        return card

    def _build_options(self, parent: ttk.Frame) -> ttk.Frame:
        """The settings most people never need, hidden until asked for."""
        options = ttk.Frame(parent, style="CardBody.TFrame")
        ttk.Separator(options).grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 10))

        def label(column: int, text: str, tip: str) -> None:
            widget = ttk.Label(options, text=text, style="Card.TLabel")
            widget.grid(row=1, column=column, sticky="w", padx=(0 if column == 0 else 22, 8))
            Tooltip(widget, tip)

        def check(column: int, text: str, variable, tip: str) -> None:
            widget = ttk.Checkbutton(options, text=text, variable=variable,
                                     style="Card.TCheckbutton")
            widget.grid(row=2, column=column, columnspan=2, sticky="w", pady=(10, 0),
                        padx=(0 if column == 0 else 22, 0))
            Tooltip(widget, tip)

        label(0, "Include subfolders", "0 tidies only the files sitting directly in the "
              "folder. Higher numbers also pick up files inside its subfolders, that many "
              "levels deep. Folders this app made are always left alone.")
        depth = ttk.Frame(options, style="CardBody.TFrame")
        depth.grid(row=1, column=1, sticky="w")
        ttk.Spinbox(depth, from_=0, to=4, width=3, textvariable=self.depth_var,
                    state="readonly").pack(side="left")
        ttk.Label(depth, text="levels deep", style="CardNote.TLabel").pack(side="left", padx=6)

        label(2, "Photos and videos", "Put photos and videos into folders by the date "
              "they were last changed, such as Pictures/2026/10.")
        ttk.Combobox(options, textvariable=self.date_var, values=list(DATE_CHOICES.values()),
                     state="readonly", width=18).grid(row=1, column=3, sticky="w")
        if system.WINDOWS or system.MAC:
            label(4, "When I sign in", "Let the app tidy this folder for you each time you "
                  "sign in" + (", or keep watching it from the system tray."
                               if system.WINDOWS else "."))
            choices = [STARTUP_CHOICES["off"], STARTUP_CHOICES["auto"]]
            if tray.available():
                choices.append(STARTUP_CHOICES["tray"])
            startup_box = ttk.Combobox(options, textvariable=self.startup_var, values=choices,
                                       state="readonly", width=24)
            startup_box.grid(row=1, column=5, sticky="w")
            startup_box.bind("<<ComboboxSelected>>", lambda _e: self._change_startup())

        check(0, "Look for duplicate files", self.duplicates_var,
              "Compares file contents to find exact copies. Turn off to scan huge folders "
              "faster.")
        check(2, "Sort unknown types into 'Other'", self.other_var,
              "Off leaves files the app doesn't recognise where they are.")
        check(4, "Use my Mac folders" if system.MAC else "Use my Windows libraries",
              self.libraries_var,
              "Send photos to Pictures, videos to {}, music to Music and documents to "
              "Documents in your user folder, instead of folders inside the one being "
              "tidied.".format("Movies" if system.MAC else "Videos"))
        rules = ttk.Button(options, text="Custom rules…", command=self.edit_rules,
                           style="Small.TButton")
        rules.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        updates_box = ttk.Checkbutton(options, text="Tell me when there's a new version",
                                      variable=self.updates_var, style="Card.TCheckbutton")
        updates_box.grid(row=3, column=2, columnspan=2, sticky="w", pady=(10, 0),
                         padx=(22, 0))
        Tooltip(updates_box, "Once each time the app opens, ask GitHub whether a newer "
                             "version is out. Nothing about you or your files is sent.")
        options.columnconfigure(5, weight=1)
        Tooltip(rules, "Choose your own folder for any file type, for example .pdf to "
                       "Documents/Receipts.")
        return options

    def _show_advanced(self, show: bool) -> None:
        self.advanced_var.set(show)
        if show:
            self.advanced.grid()
            self.tabs.tab(self.log_page, state="normal")
        else:
            self.advanced.grid_remove()
            if self.tabs.select() == str(self.log_page):
                self.tabs.select(self.graph_view)
            self.tabs.tab(self.log_page, state="hidden")
        self.advanced_link.configure(text="▾ Fewer options" if show else "▸ More options")

    def _build_summary(self) -> ttk.Frame:
        """Cards saying, at a glance, what a scan found. Click one for the details."""
        row = ttk.Frame(self)
        self.cards: dict[str, tuple[ttk.Label, ttk.Label]] = {}
        specs = (
            ("move", "Files to sort", lambda: self.tabs.select(self.graph_view)),
            ("tidy", "Already in place", None),
            ("duplicates", "Duplicate copies", lambda: self.tabs.select(self.duplicates_page)),
            ("installers", "Old installers", lambda: self.tabs.select(self.installers_page)),
        )
        for column, (key, title, action) in enumerate(specs):
            row.columnconfigure(column, weight=1, uniform="cards")
            card = ttk.Frame(row, style="Card.TFrame", padding=(14, 8))
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
            parts = (
                ttk.Label(card, text=title, style="CardTitle.TLabel"),
                ttk.Label(card, text="–", style="CardValue.TLabel"),
                ttk.Label(card, text="Scan to find out", style="CardNote.TLabel"),
            )
            for part in parts:
                part.pack(anchor="w")
            self.cards[key] = (parts[1], parts[2])
            if action:
                for widget in (card, *parts):
                    widget.configure(cursor="hand2")
                    widget.bind("<Button-1>", lambda _e, a=action: a())
                card.bind("<Enter>", lambda _e, c=card: c.configure(style="Hover.Card.TFrame"))
                card.bind("<Leave>", lambda _e, c=card: self._unhover(c))
        return row

    @staticmethod
    def _unhover(card: ttk.Frame) -> None:
        # Moving onto the card's own text also "leaves" the card; ignore that.
        under = card.winfo_containing(*card.winfo_pointerxy())
        if under is None or not str(under).startswith(str(card)):
            card.configure(style="Card.TFrame")

    def _set_card(self, key: str, value: str, note: str) -> None:
        value_label, note_label = self.cards[key]
        value_label.configure(text=value)
        note_label.configure(text=note)

    def _tree(self, parent: tk.Widget, columns, headings, widths):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=bar.set)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading, anchor="w")
            tree.column(column, width=width, anchor="w", stretch=column == columns[-1])
        tree.heading("#0", text="File", anchor="w")
        tree.column("#0", width=380, stretch=True)
        return frame, tree

    def _build_plan_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        bar = ttk.Frame(page)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(bar, text="Select none", command=lambda: self._set_all(False)).pack(
            side="left", padx=6
        )
        ttk.Button(bar, text="Show in " + system.FILE_MANAGER, command=self._reveal_plan_selection).pack(
            side="left", padx=6
        )
        self.plan_summary = ttk.Label(bar, text="Nothing scanned yet.")
        self.plan_summary.pack(side="right")

        frame, self.plan_tree = self._tree(
            page,
            ("include", "destination", "size"),
            ("Move", "Goes to", "Size"),
            (58, 240, 90),
        )
        self.plan_tree.column("include", anchor="center", width=58, stretch=False)
        frame.grid(row=1, column=0, sticky="nsew")
        self.plan_tree.bind("<Button-1>", self._on_plan_click)
        self.plan_tree.bind("<space>", lambda _e: self._toggle(self.plan_tree.focus()))
        self._bind_open(self.plan_tree)
        self.plan_tree.tag_configure("bucket", font=(theme.FAMILY, 10, "bold"))
        return page

    def _build_duplicates_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(
            page,
            text=(
                "Identical content, proven byte for byte. Copies marked 'safe to delete' "
                "can be sent to the {}, so you can still restore them.".format(system.BIN)
            ),
            wraplength=900,
        ).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(page)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(bar, text="Show in " + system.FILE_MANAGER, command=self._reveal_duplicate_selection).pack(
            side="left"
        )
        self.recycle_duplicates_button = ttk.Button(
            bar,
            text="Send duplicates to " + system.BIN,
            command=self._recycle_duplicates,
            state="disabled",
        )
        self.recycle_duplicates_button.pack(side="left", padx=6)
        ttk.Button(
            bar, text="Copy suggested deletions", command=self._copy_suggested_deletions
        ).pack(side="left")
        self.duplicate_summary = ttk.Label(bar, text="")
        self.duplicate_summary.pack(side="right")

        frame, self.duplicate_tree = self._tree(
            page,
            ("verdict", "size", "modified", "folder"),
            ("Suggestion", "Size", "Modified", "Folder"),
            (140, 80, 150, 190),
        )
        frame.grid(row=2, column=0, sticky="nsew")
        self._bind_open(self.duplicate_tree)
        self.duplicate_tree.tag_configure("group", font=(theme.FAMILY, 10, "bold"))
        return page

    def _build_versions_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(
            page,
            text=(
                "Names that look like the same thing but hold different content, likely "
                "successive versions. A hint only: check before you throw anything away."
            ),
            wraplength=900,
        ).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(page)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(bar, text="Show in " + system.FILE_MANAGER, command=self._reveal_version_selection).pack(
            side="left"
        )
        self.version_summary = ttk.Label(bar, text="")
        self.version_summary.pack(side="right")
        frame, self.version_tree = self._tree(
            page,
            ("verdict", "size", "modified", "folder"),
            ("Note", "Size", "Modified", "Folder"),
            (140, 80, 150, 190),
        )
        frame.grid(row=2, column=0, sticky="nsew")
        self._bind_open(self.version_tree)
        self.version_tree.tag_configure("group", font=(theme.FAMILY, 10, "bold"))
        return page

    def _build_installers_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(
            page,
            text=(
                "Setup files untouched for {} days or more. Most have done their job, "
                "and can be downloaded again if you need them."
            ).format(self.settings.get("installer_age_days", 30)),
            wraplength=900,
        ).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(page)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(bar, text="Show in " + system.FILE_MANAGER, command=self._reveal_installer_selection).pack(
            side="left"
        )
        self.recycle_installers_button = ttk.Button(
            bar,
            text="Send all to " + system.BIN,
            command=self._recycle_installers,
            state="disabled",
        )
        self.recycle_installers_button.pack(side="left", padx=6)
        self.installer_summary = ttk.Label(bar, text="")
        self.installer_summary.pack(side="right")
        frame, self.installer_tree = self._tree(
            page,
            ("size", "modified", "folder"),
            ("Size", "Modified", "Folder"),
            (80, 145, 260),
        )
        frame.grid(row=2, column=0, sticky="nsew")
        self._bind_open(self.installer_tree)
        return page

    def _build_log_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        self.log_text = tk.Text(page, wrap="none", height=10)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(page, orient="vertical", command=self.log_text.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=bar.set, state="disabled")
        return page

    # ----------------------------------------------------------------- helpers

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def browse(self) -> None:
        chosen = filedialog.askdirectory(
            initialdir=self.folder_var.get() or config.default_folder(),
            title="Choose a folder to tidy",
        )
        if chosen:
            self.folder_var.set(os.path.normpath(chosen))

    def _theme_choice(self) -> str:
        return next((k for k, v in theme.CHOICES.items() if v == self.theme_var.get()), "system")

    def _change_theme(self) -> None:
        mode = theme.resolve(self._theme_choice())
        self.palette = theme.apply(self.master, mode)
        self._colour_plain_widgets()
        self.graph_view.set_theme(mode)
        config.save(self.current_settings())

    def _colour_plain_widgets(self) -> None:
        """Colour the few plain Tk widgets that ttk styles cannot reach."""
        palette = self.palette
        self.log_text.configure(
            background=palette["field"], foreground=palette["text"],
            insertbackground=palette["text"], selectbackground=palette["select"],
            relief="flat", borderwidth=1,
        )
        self.duplicate_tree.tag_configure("keep", foreground=palette["good"])
        self.duplicate_tree.tag_configure("extra", foreground=palette["bad"])

    def edit_rules(self) -> None:
        dialog = RulesDialog(self.master, self.settings.get("overrides", {}))
        self.master.wait_window(dialog)
        if dialog.result is not None:
            self.settings["overrides"] = dialog.result
            config.save(self.current_settings())
            self.log("Custom rules: {}".format(
                ", ".join(".{} → {}".format(e, f) for e, f in sorted(dialog.result.items()))
                or "none"
            ))

    def _change_startup(self) -> None:
        current = startup.current_mode()
        wanted = next(k for k, v in STARTUP_CHOICES.items() if v == self.startup_var.get())
        if wanted == current:
            return
        how = {
            "auto": "Each time you sign in, File Organiser will tidy",
            "tray": "File Organiser will sit in the tray and, every minute, tidy",
        }
        if wanted != "off" and not messagebox.askokcancel(
            "When I sign in",
            "{}\n{}\nwith the options shown here, without asking first.\n\n"
            "It only moves files, never deletes them, and each run can be undone from "
            "Undo… A log is kept at\n{}".format(how[wanted], self.folder_var.get(), auto.log_path()),
        ):
            self.startup_var.set(STARTUP_CHOICES[current])
            return
        try:
            if wanted != "off":
                self.settings = self.current_settings()
                config.save(self.settings)  # the sign-in run uses what is saved
            startup.set_mode(wanted)
        except OSError as exc:
            self.startup_var.set(STARTUP_CHOICES[startup.current_mode()])
            messagebox.showerror("File Organiser", str(exc))
            return
        self.log("When I sign in: {}".format(STARTUP_CHOICES[wanted]))
        if wanted == "tray":
            subprocess.Popen(startup.command_for("tray"))  # start it now, not just next time

    def current_settings(self) -> dict:
        # Start from the stored settings so ones with no control on screen
        # (custom rules, settle time, installer age) survive a save.
        settings = dict(self.settings)
        settings.update({
            "folder": self.folder_var.get(),
            "max_depth": int(self.depth_var.get()),
            "route_to_libraries": bool(self.libraries_var.get()),
            "include_other": bool(self.other_var.get()),
            "find_duplicates": bool(self.duplicates_var.get()),
            "date_folders": next(
                (k for k, v in DATE_CHOICES.items() if v == self.date_var.get()), "off"
            ),
            "theme": self._theme_choice(),
            "graph": self.graph_view.settings(),
            "advanced": bool(self.advanced_var.get()),
            "check_updates": bool(self.updates_var.get()),
        })
        return settings

    def _busy(self, busy: bool) -> None:
        self.scan_button.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.grid()
        else:
            self.progress.grid_remove()
            self.scan_button.configure(text="Scan folder", style="Accent.TButton",
                                       command=lambda: self.start_scan(show_graph=True))
        if busy:
            self.apply_button.configure(state="disabled")
            self.undo_button.configure(state="disabled")
            return
        self._refresh_apply_state()
        if apply_module.list_journals():
            self.undo_button.configure(state="normal")

    # -------------------------------------------------------------------- scan

    def start_scan(self, show_graph: bool = False) -> None:
        """Scan the chosen folder. *show_graph* opens the Map tab when the
        results arrive; rescans after moving or undoing leave the tab alone."""
        folder = self.folder_var.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("File Organiser", "Not a folder:\n{}".format(folder))
            return
        if self.worker and self.worker.is_alive():
            return
        self.settings = self.current_settings()
        config.save(self.settings)
        self.show_graph_after_scan = show_graph
        self.cancel_scan_event.clear()
        self._busy(True)
        self.scan_button.configure(text="Stop scan", style="TButton", state="normal",
                                   command=self.cancel_scan)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set("Scanning {}…".format(folder))
        self.log("Scanning {} (depth {})".format(folder, self.settings["max_depth"]))
        self.worker = threading.Thread(
            target=self._scan_worker, args=(self.settings,), daemon=True
        )
        self.worker.start()

    def cancel_scan(self) -> None:
        if self.worker and self.worker.is_alive() and self.scan_button.cget("text") == "Stop scan":
            self.cancel_scan_event.set()
            self.status_var.set("Stopping…")

    def _scan_worker(self, settings: dict) -> None:
        def check() -> None:
            if self.cancel_scan_event.is_set():
                raise ScanCancelled

        def found(count: int) -> None:
            check()
            self.events.put(("status", "Found {:,} files…".format(count)))

        def compared(done: int, total: int) -> None:
            check()
            self.events.put(("progress", (done, total)))

        try:
            result, built = auto.scan_and_plan(settings, progress=found)
            check()
            groups: list[duplicates.DuplicateGroup] = []
            if settings["find_duplicates"]:
                self.events.put(("status", "Comparing files for duplicates…"))
                groups = duplicates.find_duplicates(
                    result.files, progress=compared, unreadable=built.unreadable,
                )
            check()
            versions = duplicates.find_possible_versions(result.files, groups)
            installers = cleanup.old_installers(
                result.files + self._already_filed_installers(settings),
                days=settings.get("installer_age_days", 30),
            )
            self.events.put(("scanned", (built, groups, versions, installers)))
        except ScanCancelled:
            self.events.put(("cancelled", None))
        except Exception as exc:  # a GUI should never die on an awkward folder
            self.events.put(("error", str(exc)))

    @staticmethod
    def _already_filed_installers(settings: dict) -> list[scan.FileInfo]:
        """Installers a previous run filed away, which the main scan skips."""
        folder = os.path.join(settings["folder"], cleanup.INSTALLERS)
        if not os.path.isdir(folder):
            return []
        return scan.scan(folder, max_depth=1).files

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    done, total = payload
                    self.progress.stop()
                    self.progress.configure(
                        mode="determinate", maximum=max(total, 1), value=done
                    )
                elif kind == "scanned":
                    self._show_results(*payload)
                elif kind == "applied":
                    self._after_apply(payload)
                elif kind == "cancelled":
                    self.progress.stop()
                    self._busy(False)
                    self.status_var.set("Scan stopped. Nothing was changed.")
                    self.log("Scan stopped by user")
                elif kind == "update":
                    self._show_update(*payload)
                elif kind == "error":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self._busy(False)
                    self.status_var.set("Something went wrong.")
                    self.log("Error: {}".format(payload))
                    messagebox.showerror("File Organiser", payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    # ----------------------------------------------------------------- results

    def _show_results(self, built, groups, versions, installers) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.plan = built
        self.duplicate_groups = groups
        self.version_groups = versions
        self.old_installers = installers
        self.path_for_item = {}
        self._fill_plan_tree()
        self._fill_duplicate_tree()
        self._fill_version_tree()
        self._fill_installer_tree()
        self.graph_view.set_data(built, groups)
        if self.show_graph_after_scan and built.moves:
            self.tabs.select(self.graph_view)
        self._busy(False)

        wasted = sum(group.wasted for group in groups)
        message = "{} file(s) to move · {} already in place".format(
            len(built.moves), len(built.already_tidy)
        )
        if groups:
            message += " · {} duplicate set(s), {} wasted".format(
                len(groups), human_size(wasted)
            )
        self.log(message)
        self._fill_cards()
        if built.moves:
            self.status_var.set(
                "Untick anything you'd rather leave where it is, then press Tidy."
            )
        else:
            self.status_var.set("This folder is already tidy. Nothing needs to move.")
        for path, why in built.skipped:
            self.log("  left alone ({}): {}".format(why, path))
        for path, why in built.unreadable:
            self.log("  could not read: {} - {}".format(path, why))

    def _fill_cards(self) -> None:
        built = self.plan
        folders = len({move.bucket for move in built.moves})
        self._set_card(
            "move", plural(len(built.moves), "file"),
            "into {}".format(plural(folders, "folder")) if built.moves else "Nothing to sort",
        )
        self._set_card("tidy", plural(len(built.already_tidy), "file"),
                       "won't be moved")
        copies = sum(len(group.redundant) for group in self.duplicate_groups)
        wasted = sum(group.wasted for group in self.duplicate_groups)
        if self.settings.get("find_duplicates", True):
            self._set_card("duplicates", plural(copies, "copy", "copies"),
                           "{} could be freed".format(human_size(wasted)) if copies
                           else "None found")
        else:
            self._set_card("duplicates", "–", "Turned off in More options")
        installer_size = sum(info.size for info in self.old_installers)
        self._set_card("installers", plural(len(self.old_installers), "file"),
                       "{} could be freed".format(human_size(installer_size))
                       if self.old_installers else "None found")

    def _fill_plan_tree(self) -> None:
        tree = self.plan_tree
        tree.delete(*tree.get_children())
        self.move_for_item.clear()
        self.item_for_move.clear()
        self.children_of.clear()

        buckets: dict[str, list[plan_module.Move]] = {}
        for move in self.plan.moves:
            buckets.setdefault(move.bucket, []).append(move)

        for bucket, moves in buckets.items():
            total = sum(move.info.size for move in moves)
            parent = tree.insert(
                "",
                "end",
                text="{}  ({})".format(bucket, len(moves)),
                values=(
                    CHECK,
                    display_folder(
                        os.path.join(moves[0].destination_folder, "x"), self.plan.root
                    ),
                    human_size(total),
                ),
                open=len(buckets) <= 6,
                tags=("bucket",),
            )
            kids = []
            for move in moves:
                name = move.info.name
                if move.renamed:
                    name += "   → {}".format(os.path.basename(move.destination))
                item = tree.insert(
                    parent,
                    "end",
                    text=name,
                    values=(CHECK, bucket, human_size(move.info.size)),
                )
                self.move_for_item[item] = move
                self.item_for_move[id(move)] = item
                kids.append(item)
            self.children_of[parent] = kids

        total_size = sum(move.info.size for move in self.plan.moves)
        self.plan_summary.configure(
            text="{} file(s), {} across {} folder(s)".format(
                len(self.plan.moves), human_size(total_size), len(buckets)
            )
        )
        self._refresh_apply_state()

    def _fill_duplicate_tree(self) -> None:
        tree = self.duplicate_tree
        tree.delete(*tree.get_children())
        root = self.plan.root if self.plan else None
        for group in self.duplicate_groups:
            node = tree.insert(
                "",
                "end",
                text="{} identical copies · {}".format(len(group.files), group.keeper.name),
                values=(
                    "free {}".format(human_size(group.wasted)),
                    human_size(group.keeper.size),
                    "",
                    "",
                ),
                open=True,
                tags=("group",),
            )
            for index, info in enumerate(group.files):
                verdict = "keep this one" if index == 0 else "safe to delete"
                item = tree.insert(
                    node,
                    "end",
                    text=info.name,
                    values=(
                        verdict,
                        human_size(info.size),
                        timestamp(info.mtime),
                        display_folder(info.path, root),
                    ),
                    tags=("keep" if index == 0 else "extra",),
                )
                self.path_for_item[item] = info.path
        wasted = sum(group.wasted for group in self.duplicate_groups)
        self.recycle_duplicates_button.configure(
            state="normal" if self.duplicate_groups else "disabled"
        )
        self.duplicate_summary.configure(
            text="{} set(s) · {} recoverable".format(
                len(self.duplicate_groups), human_size(wasted)
            )
            if self.duplicate_groups
            else "No duplicates found."
        )

    def _fill_version_tree(self) -> None:
        tree = self.version_tree
        tree.delete(*tree.get_children())
        root = self.plan.root if self.plan else None
        for group in self.version_groups:
            node = tree.insert(
                "",
                "end",
                text="'{}' · {} files".format(group.stem, len(group.files)),
                values=("different content", "", "", ""),
                open=True,
                tags=("group",),
            )
            for index, info in enumerate(group.files):
                item = tree.insert(
                    node,
                    "end",
                    text=info.name,
                    values=(
                        "newest" if index == 0 else "older",
                        human_size(info.size),
                        timestamp(info.mtime),
                        display_folder(info.path, root),
                    ),
                )
                self.path_for_item[item] = info.path
        self.version_summary.configure(
            text="{} group(s)".format(len(self.version_groups))
            if self.version_groups
            else "Nothing similar."
        )

    def _fill_installer_tree(self) -> None:
        tree = self.installer_tree
        tree.delete(*tree.get_children())
        root = self.plan.root if self.plan else None
        for info in self.old_installers:
            item = tree.insert(
                "",
                "end",
                text=info.name,
                values=(human_size(info.size), timestamp(info.mtime), display_folder(info.path, root)),
            )
            self.path_for_item[item] = info.path
        total = sum(info.size for info in self.old_installers)
        self.recycle_installers_button.configure(
            state="normal" if self.old_installers else "disabled"
        )
        self.installer_summary.configure(
            text="{} installer(s) · {}".format(len(self.old_installers), human_size(total))
            if self.old_installers
            else "No old installers."
        )

    # --------------------------------------------------------------- selection

    def _on_plan_click(self, event) -> None:
        if self.plan_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.plan_tree.identify_column(event.x) != "#1":
            return
        item = self.plan_tree.identify_row(event.y)
        if item:
            self._toggle(item)

    def _toggle(self, item: str) -> None:
        if not item:
            return
        self._set_item(item, self.plan_tree.set(item, "include") != CHECK)
        self._refresh_apply_state()
        self.graph_view.refresh()

    def _toggle_move(self, move: plan_module.Move) -> None:
        """Include or skip one file, from a right-click in the graph."""
        item = self.item_for_move.get(id(move))
        if item:
            self._set_item(item, not move.include)
            self._refresh_apply_state()

    def _set_item(self, item: str, included: bool) -> None:
        self.plan_tree.set(item, "include", CHECK if included else "")
        if item in self.move_for_item:
            self.move_for_item[item].include = included
        for child in self.children_of.get(item, []):
            self._set_item(child, included)
        parent = self.plan_tree.parent(item)
        if parent:
            siblings = self.children_of.get(parent, [])
            any_on = any(self.plan_tree.set(s, "include") == CHECK for s in siblings)
            self.plan_tree.set(parent, "include", CHECK if any_on else "")

    def _set_all(self, included: bool) -> None:
        for parent in self.plan_tree.get_children():
            self._set_item(parent, included)
        self._refresh_apply_state()
        self.graph_view.refresh()

    def _refresh_apply_state(self) -> None:
        count = len(self.plan.selected) if self.plan else 0
        self.apply_button.configure(
            state="normal" if count else "disabled",
            text="Tidy {}".format(plural(count, "file")) if count else "Tidy files",
        )

    def _selected_path(self, tree: ttk.Treeview) -> str | None:
        item = tree.focus()
        if not item:
            return None
        if tree is self.plan_tree:
            move = self.move_for_item.get(item)
            return move.source if move else None
        return self.path_for_item.get(item)

    def _bind_open(self, tree: ttk.Treeview) -> None:
        """Double-click or Enter opens a file; right-click offers a menu."""

        def on_double(event) -> None:
            # In the Plan tab, double-clicking the tick box only ticks it.
            if tree is self.plan_tree and tree.identify_column(event.x) == "#1":
                return
            self._open_selection(tree)

        tree.bind("<Double-1>", on_double)
        tree.bind("<Return>", lambda _e: self._open_selection(tree))
        system.bind_right_click(tree, lambda e: self._tree_menu(tree, e))

    def _open_selection(self, tree: ttk.Treeview) -> None:
        path = self._selected_path(tree)
        if path:
            open_path(path, self)

    def _tree_menu(self, tree: ttk.Treeview, event) -> None:
        item = tree.identify_row(event.y)
        if not item:
            return
        tree.selection_set(item)
        tree.focus(item)
        path = self._selected_path(tree)
        if not path:
            return
        menu = tk.Menu(self, tearoff=False, **self._menu_colours())
        menu.add_command(label="Open", command=lambda: open_path(path, self))
        menu.add_command(label="Show in " + system.FILE_MANAGER, command=lambda: reveal(path))
        menu.add_command(label="Open containing folder",
                         command=lambda: open_path(os.path.dirname(path), self))
        if tree is self.plan_tree:
            move = self.move_for_item.get(item)
            menu.add_separator()
            menu.add_command(label="Skip this file" if move.include else "Include this file",
                             command=lambda: self._toggle(item))
        menu.tk_popup(event.x_root, event.y_root)

    def _menu_colours(self) -> dict:
        palette = self.palette
        return {"background": palette["surface"], "foreground": palette["text"],
                "activebackground": palette["accent"],
                "activeforeground": palette["accent_text"], "borderwidth": 0}

    def _reveal_plan_selection(self) -> None:
        path = self._selected_path(self.plan_tree)
        if path:
            reveal(path)

    def _reveal_duplicate_selection(self) -> None:
        path = self._selected_path(self.duplicate_tree)
        if path:
            reveal(path)

    def _reveal_version_selection(self) -> None:
        path = self._selected_path(self.version_tree)
        if path:
            reveal(path)

    def _reveal_installer_selection(self) -> None:
        path = self._selected_path(self.installer_tree)
        if path:
            reveal(path)

    def _recycle_installers(self) -> None:
        files = self.old_installers
        if not files or (self.worker and self.worker.is_alive()):
            return
        if not messagebox.askokcancel(
            "Send old installers to " + system.BIN,
            "Send {} installer(s) ({}) to the {bin}?\n\n"
            "You can restore them from the {bin}.".format(
                len(files), human_size(sum(f.size for f in files)), bin=system.BIN
            ),
        ):
            return
        self._after_recycle(cleanup.recycle_files([(f.path, f.size) for f in files]))

    def _copy_suggested_deletions(self) -> None:
        lines = [info.path for group in self.duplicate_groups for info in group.redundant]
        if not lines:
            messagebox.showinfo("File Organiser", "No duplicates to list.")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set("Copied {} path(s) to the clipboard.".format(len(lines)))

    def _recycle_duplicates(self) -> None:
        groups = self.duplicate_groups
        count = sum(len(group.redundant) for group in groups)
        if not count or (self.worker and self.worker.is_alive()):
            return
        wasted = sum(group.wasted for group in groups)
        if not messagebox.askokcancel(
            "Send duplicates to " + system.BIN,
            "Send {} duplicate file(s) ({}) to the {bin}?\n\n"
            "One copy of each is kept. Each file is checked again first, and "
            "you can restore them from the {bin}.".format(count, human_size(wasted),
                                                          bin=system.BIN),
        ):
            return
        self._after_recycle(cleanup.recycle_duplicates(groups))

    def _after_recycle(self, report: cleanup.RecycleReport) -> None:
        self.log("{} ({} freed)".format(report.summary, human_size(report.freed)))
        for path in report.recycled:
            self.log("  recycled {}".format(path))
        for path, why in report.failed:
            self.log("  kept {}: {}".format(path, why))
        if report.failed:
            messagebox.showwarning(
                "File Organiser",
                "{} file(s) were left alone. See the Log tab.".format(len(report.failed)),
            )
        self.start_scan()

    # ------------------------------------------------------------------- apply

    def apply_plan(self) -> None:
        if not self.plan or not self.plan.selected or self._working():
            return
        moves = list(self.plan.selected)
        buckets = sorted({move.bucket for move in moves})
        preview = "\n".join("  • {}".format(bucket) for bucket in buckets[:12])
        if len(buckets) > 12:
            preview += "\n  • …and {} more".format(len(buckets) - 12)
        if not messagebox.askokcancel(
            "Tidy files",
            "Move {} into:\n\n{}\n\n"
            "Nothing is deleted, and you can undo this with Undo a tidy….".format(
                plural(len(moves), "file"), preview),
        ):
            return
        self._busy(True)
        self.progress.configure(mode="determinate", maximum=len(moves), value=0)
        self.status_var.set("Moving files…")
        self.worker = threading.Thread(target=self._apply_worker, args=(moves,), daemon=True)
        self.worker.start()

    def _apply_worker(self, moves) -> None:
        try:
            report = apply_module.apply_moves(
                moves,
                progress=lambda done, total: self.events.put(("progress", (done, total))),
            )
            self.events.put(("applied", report))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _after_apply(self, report) -> None:
        self.log(report.summary)
        for source, destination in report.moved:
            self.log("  {} -> {}".format(source, destination))
        for source, why in report.failed:
            self.log("  FAILED {}: {}".format(source, why))
        if report.journal_path:
            self.log("  undo journal: {}".format(report.journal_path))
        self.status_var.set(report.summary + ". Rescanning…")
        self._busy(False)
        if report.failed:
            messagebox.showwarning(
                "File Organiser",
                "{} file(s) could not be moved. See the Log tab.".format(len(report.failed)),
            )
        self.start_scan()

    def _working(self) -> bool:
        """True while a scan or a tidy is running (shortcuts skip the buttons' checks)."""
        return bool(self.worker and self.worker.is_alive())

    def undo_last(self) -> None:
        if self._working():
            return
        history = apply_module.run_history()
        if not history:
            messagebox.showinfo("File Organiser", "There is nothing to undo.")
            return
        dialog = HistoryDialog(self.master, history)
        self.master.wait_window(dialog)
        if not dialog.result:
            return
        report = apply_module.undo(dialog.result.path)
        self.log("Undo of run from {}: {}".format(
            timestamp(dialog.result.created), report.summary
        ))
        for source, why in report.failed:
            self.log("  skipped {}: {}".format(source, why))
        self.status_var.set("Undo complete: {}".format(report.summary))
        if not apply_module.list_journals():
            self.undo_button.configure(state="disabled")
        self.start_scan()


class WelcomeDialog(tk.Toplevel):
    """A short tour for first-time users, also shown by "How it works"."""

    STEPS = (
        ("Choose a folder",
         "Downloads is picked for you. You can choose any folder with Browse…, "
         "or click a quick pick."),
        ("Scan and have a look",
         "Scan folder shows a map of where every file would go. Nothing moves yet. "
         "Untick anything you'd rather leave where it is."),
        ("Tidy",
         "Tidy moves the files into neat folders. Changed your mind? Undo a tidy puts "
         "them all back."),
    )

    def __init__(self, master: tk.Misc, palette: dict) -> None:
        super().__init__(master)
        self.title("Welcome to File Organiser")
        self.transient(master)
        self.resizable(False, False)
        self.configure(background=palette["bg"])

        page = ttk.Frame(self, padding=24)
        page.pack(fill="both", expand=True)
        ttk.Label(page, text="Tidy a messy folder in three steps",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(page, style="Muted.TLabel",
                  text="Nothing is ever deleted, and every tidy can be undone.").pack(
            anchor="w", pady=(2, 16))

        for number, (title, text) in enumerate(self.STEPS, start=1):
            card = ttk.Frame(page, style="Card.TFrame", padding=(14, 12))
            card.pack(fill="x", pady=(0, 10))
            badge = tk.Canvas(card, width=34, height=34, highlightthickness=0,
                              background=palette["surface"])
            badge.create_oval(2, 2, 32, 32, fill=palette["accent"], outline="")
            badge.create_text(17, 17, text=str(number), fill=palette["accent_text"],
                              font=(theme.FAMILY, 12, "bold"))
            badge.pack(side="left", padx=(0, 14), anchor="n")
            words = ttk.Frame(card, style="CardBody.TFrame")
            words.pack(side="left", fill="x", expand=True)
            ttk.Label(words, text=title, style="CardHeading.TLabel").pack(anchor="w")
            ttk.Label(words, text=text, style="Card.TLabel", wraplength=420,
                      justify="left").pack(anchor="w", pady=(2, 0))

        keys = ttk.Frame(page)
        keys.pack(fill="x", pady=(6, 0))
        ttk.Label(keys, text="Keyboard shortcuts", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        for index, (combo, what) in enumerate(SHORTCUTS):
            row, column = divmod(index, 2)
            ttk.Label(keys, text=combo, font=(theme.FAMILY, 9, "bold")).grid(
                row=row + 1, column=column * 2, sticky="w", padx=(0, 8))
            ttk.Label(keys, text=what, style="Muted.TLabel").grid(
                row=row + 1, column=column * 2 + 1, sticky="w", padx=(0, 24))

        start = ttk.Button(page, text="Get started", style="Accent.TButton",
                           command=self.destroy)
        start.pack(anchor="e", pady=(18, 0))
        start.focus_set()
        self.bind("<Return>", lambda _e: self.destroy())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry("+{}+{}".format(max(x, 0), max(y, 0)))
        self.grab_set()


class HistoryDialog(tk.Toplevel):
    """Pick a past run to undo. The newest is selected, so Enter undoes it."""

    def __init__(self, master: tk.Misc, history: list[apply_module.RunSummary]) -> None:
        super().__init__(master)
        self.title("Undo a run")
        self.transient(master)
        self.minsize(560, 300)
        self.result: apply_module.RunSummary | None = None
        self.by_item: dict[str, apply_module.RunSummary] = {}

        page = ttk.Frame(self, padding=PAD)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        ttk.Label(
            page,
            text="Files go back where they came from. Files you have moved or "
            "renamed since are left where they are.",
            wraplength=540,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        tree = ttk.Treeview(page, columns=("when", "files", "from"), show="headings",
                            height=10, selectmode="browse")
        tree.heading("when", text="When")
        tree.heading("files", text="Files")
        tree.heading("from", text="Moved from")
        tree.column("when", width=140, stretch=False)
        tree.column("files", width=60, stretch=False, anchor="e")
        tree.grid(row=1, column=0, sticky="nsew")
        for run in history:
            item = tree.insert("", "end", values=(timestamp(run.created), run.moves,
                                                  run.source_folder))
            self.by_item[item] = run
        first = tree.get_children()[0]
        tree.selection_set(first)
        tree.focus(first)
        self.tree = tree

        buttons = ttk.Frame(page)
        buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Undo selected run", command=self._choose).pack(
            side="right", padx=6
        )
        tree.bind("<Double-1>", lambda _e: self._choose())
        self.bind("<Return>", lambda _e: self._choose())
        self.bind("<Escape>", lambda _e: self.destroy())
        tree.focus_set()
        self.grab_set()

    def _choose(self) -> None:
        selected = self.tree.selection()
        if selected:
            self.result = self.by_item[selected[0]]
            self.destroy()


class RulesDialog(tk.Toplevel):
    """Edit the user's own extension → folder rules, which beat the built-ins."""

    def __init__(self, master: tk.Misc, overrides: dict[str, str]) -> None:
        super().__init__(master)
        self.title("Custom rules")
        self.transient(master)
        self.resizable(True, True)
        self.minsize(460, 360)
        self.rules = dict(overrides)
        self.result: dict[str, str] | None = None

        page = ttk.Frame(self, padding=PAD)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        ttk.Label(
            page,
            text="Send a file type somewhere of your choosing. These win over the "
            "built-in rules. Folders are inside the folder being tidied.",
            wraplength=430,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.tree = ttk.Treeview(
            page, columns=("folder",), show="tree headings", height=8, selectmode="browse"
        )
        self.tree.heading("#0", text="Extension")
        self.tree.heading("folder", text="Goes to")
        self.tree.column("#0", width=110, stretch=False)
        self.tree.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(page)
        form.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        form.columnconfigure(3, weight=1)
        ttk.Label(form, text="Extension").grid(row=0, column=0)
        self.ext_var = tk.StringVar()
        ext_entry = ttk.Entry(form, textvariable=self.ext_var, width=10)
        ext_entry.grid(row=0, column=1, padx=(6, 12))
        ttk.Label(form, text="Goes to").grid(row=0, column=2)
        self.folder_var = tk.StringVar()
        ttk.Combobox(
            form, textvariable=self.folder_var, values=rules.known_destinations()
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        buttons = ttk.Frame(page)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Add / update", command=self._add).pack(side="left")
        ttk.Button(buttons, text="Remove", command=self._remove).pack(side="left", padx=6)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right", padx=6)

        self._refresh()
        ext_entry.focus_set()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for ext, folder in sorted(self.rules.items()):
            self.tree.insert("", "end", iid=ext, text="." + ext, values=(folder,))

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if selected:
            self.ext_var.set(selected[0])
            self.folder_var.set(self.rules[selected[0]])

    def _add(self) -> None:
        try:
            ext, folder = rules.clean_rule(self.ext_var.get(), self.folder_var.get())
        except ValueError as exc:
            messagebox.showerror("Custom rules", str(exc), parent=self)
            return
        self.rules[ext] = folder
        self._refresh()
        self.tree.selection_set(ext)
        self.tree.see(ext)

    def _remove(self) -> None:
        for ext in self.tree.selection():
            self.rules.pop(ext, None)
        self.ext_var.set("")
        self.folder_var.set("")
        self._refresh()

    def _save(self) -> None:
        self.result = self.rules
        self.destroy()


def _sharpen_on_high_dpi() -> None:
    """Ask Windows not to bitmap-stretch the window on a scaled display."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _smoke_test(root: tk.Tk, app: "OrganiserApp", folder: str) -> None:
    """Exercise the real window briefly, then exit 0, or 1 on any error.

    The release workflow runs the built app this way, so a build that can't
    open its window, scan or draw the map is never published.
    """
    errors: list[str] = []

    def failed(kind, value, trace) -> None:
        import traceback

        errors.append("".join(traceback.format_exception(kind, value, trace)))

    root.report_callback_exception = failed

    def finish() -> None:
        if not app.plan or not app.plan.moves:
            errors.append("the scan found nothing to move")
        print("\n".join(errors) or "smoke test passed: {} moves planned".format(
            len(app.plan.moves) if app.plan else 0))
        root.destroy()
        sys.exit(1 if errors else 0)

    app.folder_var.set(folder)
    root.after(500, lambda: app.start_scan(show_graph=True))
    root.after(4000, app.graph_view.play)
    root.after(9000, finish)


def main() -> None:
    smoke = None
    if "--smoke-test" in sys.argv[1:]:
        import tempfile

        smoke = tempfile.mkdtemp()
        os.environ["LOCALAPPDATA"] = os.path.join(smoke, "settings")  # leave real ones alone
        os.makedirs(os.path.join(smoke, "messy"))
        for name in ("photo.jpg", "notes.pdf", "song.mp3", "archive.zip", "photo copy.jpg"):
            with open(os.path.join(smoke, "messy", name), "wb") as handle:
                handle.write(b"same" if "photo" in name else name.encode())
        config.save(dict(config.load(), welcomed=True, check_updates=False, settle_seconds=0))
    if "--auto" in sys.argv[1:]:
        auto.run()
        return
    if "--tray" in sys.argv[1:]:
        tray.run()
        return
    _sharpen_on_high_dpi()
    root = tk.Tk()
    root.title("File Organiser")
    root.geometry("1180x840")
    root.minsize(940, 680)
    try:  # the app's own icon instead of Tk's feather, when Pillow is there
        from PIL import ImageTk

        from organiser.icon import make_image

        root._icon = ImageTk.PhotoImage(make_image(64))
        root.iconphoto(True, root._icon)
    except Exception:
        pass
    app = OrganiserApp(root)

    def close() -> None:
        config.save(app.current_settings())
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    if smoke:
        _smoke_test(root, app, os.path.join(smoke, "messy"))
    if system.MAC:
        root.createcommand("tk::mac::Quit", close)  # Cmd+Q and the app menu's Quit
        root.createcommand("tk::mac::ShowHelp", app.show_welcome)
    root.mainloop()


if __name__ == "__main__":
    main()
