"""File Organiser - a small Windows desktop app for tidying a cluttered folder.

The app always shows you a plan first. Scanning and hashing never change
anything on disk; files move only when you press "Apply selected moves", and
that run can be undone. Duplicates are reported, never deleted.
"""

from __future__ import annotations

import datetime
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organiser import apply as apply_module  # noqa: E402
from organiser import config, duplicates, plan as plan_module, rules, scan  # noqa: E402

CHECK = "✓"
PAD = 10


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
    """Show a file in Explorer (or the platform equivalent)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,{}".format(os.path.normpath(path))])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass


class OrganiserApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=PAD)
        self.master = master
        self.settings = config.load()
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.plan: plan_module.Plan | None = None
        self.duplicate_groups: list[duplicates.DuplicateGroup] = []
        self.version_groups: list[duplicates.VersionGroup] = []
        self.move_for_item: dict[str, plan_module.Move] = {}
        self.children_of: dict[str, list[str]] = {}
        self.path_for_item: dict[str, str] = {}

        self.folder_var = tk.StringVar(value=self.settings["folder"])
        self.depth_var = tk.IntVar(value=self.settings["max_depth"])
        self.libraries_var = tk.BooleanVar(value=self.settings["route_to_libraries"])
        self.other_var = tk.BooleanVar(value=self.settings["include_other"])
        self.duplicates_var = tk.BooleanVar(value=self.settings["find_duplicates"])
        self.status_var = tk.StringVar(value="Pick a folder and press Scan.")

        self.pack(fill="both", expand=True)
        self._build()
        self.after(100, self._drain_events)

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        chooser = ttk.Frame(self)
        chooser.grid(row=0, column=0, sticky="ew")
        chooser.columnconfigure(1, weight=1)
        ttk.Label(chooser, text="Folder to tidy").grid(row=0, column=0, padx=(0, 8))
        entry = ttk.Entry(chooser, textvariable=self.folder_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.bind("<Return>", lambda _e: self.start_scan())
        ttk.Button(chooser, text="Browse…", command=self.browse).grid(row=0, column=2, padx=6)
        self.scan_button = ttk.Button(chooser, text="Scan", command=self.start_scan)
        self.scan_button.grid(row=0, column=3)

        options = ttk.Labelframe(self, text="Options", padding=8)
        options.grid(row=1, column=0, sticky="ew", pady=(PAD, PAD))
        ttk.Label(options, text="Look into subfolders:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(
            options, from_=0, to=4, width=4, textvariable=self.depth_var, state="readonly"
        ).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Checkbutton(
            options,
            text="Send photos, videos and documents to my user libraries",
            variable=self.libraries_var,
        ).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Checkbutton(
            options,
            text="Collect unrecognised files in “Other”",
            variable=self.other_var,
        ).grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            options, text="Look for duplicates", variable=self.duplicates_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        self.tabs.add(self._build_plan_tab(), text="Plan")
        self.tabs.add(self._build_duplicates_tab(), text="Duplicates")
        self.tabs.add(self._build_versions_tab(), text="Possible versions")
        self.tabs.add(self._build_log_tab(), text="Log")

        footer = ttk.Frame(self)
        footer.grid(row=3, column=0, sticky="ew", pady=(PAD, 0))
        footer.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(footer, mode="determinate", length=180)
        self.progress.grid(row=0, column=0, padx=(0, 10))
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=1, sticky="w")
        self.undo_button = ttk.Button(
            footer, text="Undo last run", command=self.undo_last, state="disabled"
        )
        self.undo_button.grid(row=0, column=2, padx=6)
        self.apply_button = ttk.Button(
            footer, text="Apply selected moves", command=self.apply_plan, state="disabled"
        )
        self.apply_button.grid(row=0, column=3)
        if apply_module.list_journals():
            self.undo_button.configure(state="normal")

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
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w", stretch=column == columns[-1])
        tree.heading("#0", text="File")
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
        ttk.Button(bar, text="Show in Explorer", command=self._reveal_plan_selection).pack(
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
        self.plan_tree.bind("<Double-1>", lambda _e: self._reveal_plan_selection())
        self.plan_tree.tag_configure("bucket", font=("Segoe UI", 9, "bold"))
        return page

    def _build_duplicates_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(
            page,
            text=(
                "Identical content, proven byte for byte. This app never deletes anything "
                "— the suggestion below is for you to act on."
            ),
            wraplength=900,
        ).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(page)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(bar, text="Show in Explorer", command=self._reveal_duplicate_selection).pack(
            side="left"
        )
        ttk.Button(
            bar, text="Copy suggested deletions", command=self._copy_suggested_deletions
        ).pack(side="left", padx=6)
        self.duplicate_summary = ttk.Label(bar, text="")
        self.duplicate_summary.pack(side="right")

        frame, self.duplicate_tree = self._tree(
            page,
            ("verdict", "size", "modified", "folder"),
            ("Suggestion", "Size", "Modified", "Folder"),
            (120, 80, 145, 190),
        )
        frame.grid(row=2, column=0, sticky="nsew")
        self.duplicate_tree.bind("<Double-1>", lambda _e: self._reveal_duplicate_selection())
        self.duplicate_tree.tag_configure("group", font=("Segoe UI", 9, "bold"))
        self.duplicate_tree.tag_configure("keep", foreground="#1a7f37")
        self.duplicate_tree.tag_configure("extra", foreground="#a40e26")
        return page

    def _build_versions_tab(self) -> ttk.Frame:
        page = ttk.Frame(self, padding=8)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        ttk.Label(
            page,
            text=(
                "Names that look like the same thing but hold different content — likely "
                "successive versions. A hint only: check before you throw anything away."
            ),
            wraplength=900,
        ).grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(page)
        bar.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Button(bar, text="Show in Explorer", command=self._reveal_version_selection).pack(
            side="left"
        )
        self.version_summary = ttk.Label(bar, text="")
        self.version_summary.pack(side="right")
        frame, self.version_tree = self._tree(
            page,
            ("verdict", "size", "modified", "folder"),
            ("Note", "Size", "Modified", "Folder"),
            (120, 80, 145, 190),
        )
        frame.grid(row=2, column=0, sticky="nsew")
        self.version_tree.bind("<Double-1>", lambda _e: self._reveal_version_selection())
        self.version_tree.tag_configure("group", font=("Segoe UI", 9, "bold"))
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

    def current_settings(self) -> dict:
        return {
            "folder": self.folder_var.get(),
            "max_depth": int(self.depth_var.get()),
            "route_to_libraries": bool(self.libraries_var.get()),
            "include_other": bool(self.other_var.get()),
            "find_duplicates": bool(self.duplicates_var.get()),
            "overrides": self.settings.get("overrides", {}),
        }

    def _busy(self, busy: bool) -> None:
        self.scan_button.configure(state="disabled" if busy else "normal")
        if busy:
            self.apply_button.configure(state="disabled")
            self.undo_button.configure(state="disabled")
            return
        self._refresh_apply_state()
        if apply_module.list_journals():
            self.undo_button.configure(state="normal")

    # -------------------------------------------------------------------- scan

    def start_scan(self) -> None:
        folder = self.folder_var.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("File Organiser", "Not a folder:\n{}".format(folder))
            return
        if self.worker and self.worker.is_alive():
            return
        self.settings = self.current_settings()
        config.save(self.settings)
        self._busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set("Scanning {}…".format(folder))
        self.log("Scanning {} (depth {})".format(folder, self.settings["max_depth"]))
        self.worker = threading.Thread(
            target=self._scan_worker, args=(self.settings,), daemon=True
        )
        self.worker.start()

    def _scan_worker(self, settings: dict) -> None:
        try:
            result = scan.scan(
                settings["folder"],
                max_depth=settings["max_depth"],
                ignore_folders=set(rules.known_destinations()),
                progress=lambda n: self.events.put(("status", "Found {} files…".format(n))),
            )
            built = plan_module.build_plan(
                result,
                route_to_libraries=settings["route_to_libraries"],
                overrides=settings.get("overrides"),
                include_other=settings["include_other"],
            )
            groups: list[duplicates.DuplicateGroup] = []
            if settings["find_duplicates"]:
                self.events.put(("status", "Comparing files for duplicates…"))
                groups = duplicates.find_duplicates(
                    result.files,
                    progress=lambda done, total: self.events.put(("progress", (done, total))),
                    unreadable=built.unreadable,
                )
            versions = duplicates.find_possible_versions(result.files, groups)
            self.events.put(("scanned", (built, groups, versions)))
        except Exception as exc:  # a GUI should never die on an awkward folder
            self.events.put(("error", str(exc)))

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

    def _show_results(self, built, groups, versions) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.plan = built
        self.duplicate_groups = groups
        self.version_groups = versions
        self.path_for_item = {}
        self._fill_plan_tree()
        self._fill_duplicate_tree()
        self._fill_version_tree()
        self._busy(False)

        wasted = sum(group.wasted for group in groups)
        message = "{} file(s) to move · {} already in place".format(
            len(built.moves), len(built.already_tidy)
        )
        if groups:
            message += " · {} duplicate set(s), {} wasted".format(
                len(groups), human_size(wasted)
            )
        self.status_var.set(message)
        self.log(message)
        for path, why in built.skipped:
            self.log("  left alone ({}): {}".format(why, path))
        for path, why in built.unreadable:
            self.log("  could not read: {} - {}".format(path, why))

    def _fill_plan_tree(self) -> None:
        tree = self.plan_tree
        tree.delete(*tree.get_children())
        self.move_for_item.clear()
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
                text="“{}” · {} files".format(group.stem, len(group.files)),
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

    def _refresh_apply_state(self) -> None:
        count = len(self.plan.selected) if self.plan else 0
        self.apply_button.configure(
            state="normal" if count else "disabled",
            text="Apply {} move(s)".format(count) if count else "Apply selected moves",
        )

    def _selected_path(self, tree: ttk.Treeview) -> str | None:
        item = tree.focus()
        if not item:
            return None
        if tree is self.plan_tree:
            move = self.move_for_item.get(item)
            return move.source if move else None
        return self.path_for_item.get(item)

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

    def _copy_suggested_deletions(self) -> None:
        lines = [info.path for group in self.duplicate_groups for info in group.redundant]
        if not lines:
            messagebox.showinfo("File Organiser", "No duplicates to list.")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set("Copied {} path(s) to the clipboard.".format(len(lines)))

    # ------------------------------------------------------------------- apply

    def apply_plan(self) -> None:
        if not self.plan or not self.plan.selected:
            return
        moves = list(self.plan.selected)
        buckets = sorted({move.bucket for move in moves})
        preview = "\n".join("  • {}".format(bucket) for bucket in buckets[:12])
        if len(buckets) > 12:
            preview += "\n  • …and {} more".format(len(buckets) - 12)
        if not messagebox.askokcancel(
            "Apply moves",
            "Move {} file(s) into:\n\n{}\n\n"
            "Nothing is deleted, and this run can be undone.".format(len(moves), preview),
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
        self.status_var.set(report.summary + " — rescanning…")
        self._busy(False)
        if report.failed:
            messagebox.showwarning(
                "File Organiser",
                "{} file(s) could not be moved. See the Log tab.".format(len(report.failed)),
            )
        self.start_scan()

    def undo_last(self) -> None:
        journals = apply_module.list_journals()
        if not journals:
            messagebox.showinfo("File Organiser", "There is nothing to undo.")
            return
        latest = journals[0]
        if not messagebox.askokcancel(
            "Undo last run",
            "Put the files from the last run back where they were?\n\n{}".format(
                os.path.basename(latest)
            ),
        ):
            return
        report = apply_module.undo(latest)
        self.log("Undo: {}".format(report.summary))
        for source, why in report.failed:
            self.log("  skipped {}: {}".format(source, why))
        self.status_var.set("Undo complete — {}".format(report.summary))
        if not apply_module.list_journals():
            self.undo_button.configure(state="disabled")
        self.start_scan()


def _sharpen_on_high_dpi() -> None:
    """Ask Windows not to bitmap-stretch the window on a scaled display."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> None:
    _sharpen_on_high_dpi()
    root = tk.Tk()
    root.title("File Organiser")
    root.geometry("1040x700")
    root.minsize(860, 560)
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    style.configure("Treeview", rowheight=24)
    app = OrganiserApp(root)
    root.protocol(
        "WM_DELETE_WINDOW", lambda: (config.save(app.current_settings()), root.destroy())
    )
    root.mainloop()


if __name__ == "__main__":
    main()
