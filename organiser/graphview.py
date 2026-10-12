"""An interactive, animated view of :mod:`organiser.graph`, in the style of
Obsidian's graph view.

Scroll to zoom, drag the background to pan, drag a dot to pull it about.
Hovering a dot lights up what it is linked to. Double-click a file to open
it, or a folder to fold or unfold it; right-click anything for a menu. "Before / after" plays the plan: every file starts loose in the
folder being tidied, then flies to where it is going.
"""

from __future__ import annotations

import math
import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import graph as graph_module
from .plan import Move

PALETTES = {
    "dark": {
        "bg": "#1e1f22", "edge": "#3c3f46", "accent": "#a28bfe", "text": "#d4d6db",
        "muted": "#7f848e", "duplicate": "#ff6b6b", "root": "#e8e9ec", "button": "#2b2d31",
    },
    "light": {
        "bg": "#ffffff", "edge": "#d3d5da", "accent": "#7f6df2", "text": "#2e3338",
        "muted": "#8a8f98", "duplicate": "#e5484d", "root": "#3a3d44", "button": "#eef0f3",
    },
}
FONT = ("Segoe UI", 9)
FOLDER_FONT = ("Segoe UI", 9, "bold")
CAPTION_FONT = ("Segoe UI", 15, "bold")

GROUP_COLOURS = {
    "Pictures": "#e5c07b",
    "Videos": "#e06c75",
    "Audio": "#c678dd",
    "Documents": "#61afef",
    "Archives": "#d19a66",
    "Installers": "#f7768e",
    "Code": "#98c379",
    "Apps": "#56b6c2",
    "Other": "#8a8f98",
}
SPARE_COLOURS = ("#ff9e64", "#7aa2f7", "#9ece6a", "#2ac3de", "#bb9af7", "#e0af68",
                 "#73daca", "#f5a97f")
BASE_RADIUS = 4.0

# Before / after timings, in seconds.
HOLD = 1.0      # files sit loose in the folder being tidied
SPREAD = 1.8    # the last file sets off this long after the first
FLIGHT = 0.9    # each file's journey

#: Settings saved between runs: name -> default.
DEFAULTS = {
    "files": True, "in_place": False, "duplicates": True, "arrows": True,
    "fade": 0.45, "size": 0.4, "thickness": 0.3,
    "center": 0.3, "repel": 0.5, "link": 0.5, "distance": 0.4,
    "size_by": "count", "panel": True,
}


def blend(colour: str, other: str, amount: float) -> str:
    """Mix *amount* (0 to 1) of *other* into *colour*."""
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def human_size(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} TB"


def ease(t: float) -> float:
    """Ease in and out (cubic), for 0 <= t <= 1."""
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class GraphView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_toggle: Callable[[Move], None] | None = None,
        on_reveal: Callable[[str], None] | None = None,
        on_open: Callable[[str], None] | None = None,
        settings: dict | None = None,
        mode: str = "dark",
    ) -> None:
        super().__init__(master)
        self.on_toggle = on_toggle
        self.on_reveal = on_reveal
        self.on_open = on_open
        self.mode = mode
        self.c = PALETTES[mode]
        self.plan = None
        self.duplicate_groups = []
        self.collapsed: set[str] | None = None  # None until the first build picks some
        self.graph = graph_module.Graph()
        self.sim = graph_module.Simulation(self.graph)
        self.zoom = 1.0
        self.offset = [0.0, 0.0]
        self.hover: int | None = None
        self.selected: int | None = None
        self.dragging: int | None = None
        self.pan_from: tuple[int, int] | None = None
        self.pressed_at: tuple[int, int] | None = None
        self.moved = False
        self.view_touched = False
        self.ticks = 0
        self.ticking = False
        self.tween: dict | None = None
        self.progress: dict[int, float] = {}
        self.node_items: list[int] = []
        self.label_items: list[int] = []
        self.edge_items: list[int] = []
        self.label_state: list[tuple | None] = []
        self.arrow_state: list[str] = []
        self.edge_hidden: list[bool] = []
        self.edge_width = 0.0
        self.colours: dict[str, str] = {}

        saved = dict(DEFAULTS)
        for name, value in (settings or {}).items():
            default = DEFAULTS.get(name)
            if default is None:
                continue
            if isinstance(default, float) and isinstance(value, (int, float))                     and not isinstance(value, bool):
                saved[name] = value
            elif type(value) is type(default):
                saved[name] = value
        clamp = lambda v: min(max(float(v), 0.0), 1.0)  # noqa: E731
        self.search_var = tk.StringVar()
        self.files_var = tk.BooleanVar(value=saved["files"])
        self.in_place_var = tk.BooleanVar(value=saved["in_place"])
        self.duplicates_var = tk.BooleanVar(value=saved["duplicates"])
        self.arrows_var = tk.BooleanVar(value=saved["arrows"])
        self.fade_var = tk.DoubleVar(value=clamp(saved["fade"]))
        self.size_var = tk.DoubleVar(value=clamp(saved["size"]))
        self.thickness_var = tk.DoubleVar(value=clamp(saved["thickness"]))
        self.center_var = tk.DoubleVar(value=clamp(saved["center"]))
        self.repel_var = tk.DoubleVar(value=clamp(saved["repel"]))
        self.link_var = tk.DoubleVar(value=clamp(saved["link"]))
        self.distance_var = tk.DoubleVar(value=clamp(saved["distance"]))
        self.size_by_var = tk.StringVar(
            value=saved["size_by"] if saved["size_by"] in ("count", "space") else "count"
        )

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.panel = self._scrolling(self._build_panel)
        self.panel.grid(row=0, column=1, sticky="ns")
        if not saved["panel"]:
            self.panel.grid_remove()
            self.panel_wanted = False

        self.play_button = self._canvas_button("▶  Before / after", self.play)
        self.gear_button = self._canvas_button("⚙", self._toggle_panel, font=("Segoe UI", 12))
        self.gear = self.canvas.create_window(0, 0, window=self.gear_button, anchor="ne",
                                              tags="chrome")
        self.play_item = self.canvas.create_window(0, 0, window=self.play_button, anchor="ne",
                                                   tags="chrome")
        self.info = self.canvas.create_text(14, 12, anchor="nw", font=FONT, text="",
                                            tags="chrome")
        self.caption = self.canvas.create_text(14, 10, anchor="nw", font=CAPTION_FONT, text="",
                                               tags="chrome")
        self.hint = self.canvas.create_text(
            14, 0, anchor="sw", font=FONT, tags="chrome",
            text="Scroll to zoom · drag to pan · double-click a file to open it, or a folder "
                 "to fold it · right-click for more",
        )
        self.empty = self.canvas.create_text(0, 0, font=("Segoe UI", 11),
                                             text="Choose a folder above and press Scan folder."
                                                  "\n\nYou'll see a map of where every file "
                                                  "would go. Nothing moves until you press Tidy.",
                                             justify="center")
        self.set_theme(mode)

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-1>", self._on_double)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.1))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.1))
        self.bind("<Map>", lambda _e: self._start())

    def _canvas_button(self, text: str, command, font=FONT) -> tk.Button:
        return tk.Button(self.canvas, text=text, command=command, relief="flat", borderwidth=0,
                         font=font, cursor="hand2", padx=8, pady=2)

    # ------------------------------------------------------------- settings

    def settings(self) -> dict:
        """The panel's current settings, for saving between runs."""
        return {
            "files": self.files_var.get(), "in_place": self.in_place_var.get(),
            "duplicates": self.duplicates_var.get(), "arrows": self.arrows_var.get(),
            "fade": round(self.fade_var.get(), 3), "size": round(self.size_var.get(), 3),
            "thickness": round(self.thickness_var.get(), 3),
            "center": round(self.center_var.get(), 3), "repel": round(self.repel_var.get(), 3),
            "link": round(self.link_var.get(), 3), "distance": round(self.distance_var.get(), 3),
            "size_by": self.size_by_var.get(), "panel": self.panel_wanted,
        }

    def set_theme(self, mode: str) -> None:
        self.mode = mode
        self.c = c = PALETTES[mode]
        self.canvas.configure(background=c["bg"])
        for button in (self.play_button, self.gear_button):
            button.configure(background=c["button"], foreground=c["text"],
                             activebackground=blend(c["button"], c["accent"], 0.25),
                             activeforeground=c["text"])
        self.canvas.itemconfigure(self.info, fill=c["text"])
        self.canvas.itemconfigure(self.caption, fill=c["text"])
        self.canvas.itemconfigure(self.hint, fill=c["muted"])
        self.canvas.itemconfigure(self.empty, fill=c["muted"])
        self.menu_colours = {
            "background": c["button"], "foreground": c["text"],
            "activebackground": blend(c["button"], c["accent"], 0.45),
            "activeforeground": c["text"], "borderwidth": 0,
        } if mode == "dark" else {}
        panel_bg = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        self.panel_holder.configure(background=panel_bg)
        self.label_state = [None] * len(self.label_items)
        self._fill_legend()
        self.restyle()

    # ------------------------------------------------------------------ panel

    def _scrolling(self, build) -> ttk.Frame:
        """Wrap the settings panel so it scrolls when the window is short."""
        outer = ttk.Frame(self)
        outer.rowconfigure(0, weight=1)
        holder = tk.Canvas(outer, width=250, highlightthickness=0, borderwidth=0)
        holder.grid(row=0, column=0, sticky="ns")
        self.panel_holder = holder
        bar = ttk.Scrollbar(outer, orient="vertical", command=holder.yview)
        holder.configure(yscrollcommand=bar.set)
        panel = build(holder)
        window = holder.create_window(0, 0, window=panel, anchor="nw")

        def update(_event=None) -> None:
            holder.configure(scrollregion=(0, 0, panel.winfo_reqwidth(), panel.winfo_reqheight()))
            holder.itemconfigure(window, width=holder.winfo_width())
            if panel.winfo_reqheight() > holder.winfo_height():
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid_remove()
                holder.yview_moveto(0)

        def wheel(event) -> None:
            if panel.winfo_reqheight() > holder.winfo_height():
                holder.yview_scroll(int(-event.delta / 120), "units")

        panel.bind("<Configure>", update)
        holder.bind("<Configure>", update)
        outer.bind("<Enter>", lambda _e: outer.bind_all("<MouseWheel>", wheel))
        outer.bind("<Leave>", lambda _e: outer.unbind_all("<MouseWheel>"))
        return outer

    def _build_panel(self, parent: tk.Misc) -> ttk.Frame:
        panel = ttk.Frame(parent, padding=(10, 6))
        body: ttk.Frame = panel

        def section(title: str, open_: bool = True) -> None:
            """A heading that folds its controls away when clicked, as in Obsidian."""
            nonlocal body
            header = ttk.Label(panel, font=("Segoe UI", 9, "bold"), cursor="hand2")
            header.pack(fill="x", pady=(8, 2))
            content = ttk.Frame(panel)

            def show(visible: bool) -> None:
                header.configure(text=("▾  " if visible else "▸  ") + title)
                if visible:
                    content.pack(fill="x", after=header)
                else:
                    content.pack_forget()

            header.bind("<Button-1>", lambda _e: show(not content.winfo_ismapped()))
            show(open_)
            body = content

        def check(text: str, variable: tk.BooleanVar, command) -> None:
            ttk.Checkbutton(body, text=text, variable=variable, command=command).pack(anchor="w")

        def slider(text: str, variable: tk.DoubleVar, command) -> None:
            ttk.Label(body, text=text).pack(anchor="w", pady=(4, 0))
            ttk.Scale(body, from_=0.0, to=1.0, variable=variable,
                      command=lambda _v: command()).pack(fill="x")

        section("Filters")
        ttk.Entry(body, textvariable=self.search_var).pack(fill="x", pady=(0, 4))
        self.search_var.trace_add("write", lambda *_a: self.restyle())
        check("Files", self.files_var, self._rebuild)
        check("Files already in place", self.in_place_var, self._rebuild)
        check("Duplicate links", self.duplicates_var, self._rebuild)

        section("Groups")
        self.legend = body

        section("Display")
        ttk.Label(body, text="Dot size shows").pack(anchor="w")
        for value, text in (("count", "Number of files"), ("space", "Disk space")):
            ttk.Radiobutton(body, text=text, value=value, variable=self.size_by_var,
                            command=self._rebuild).pack(anchor="w")
        check("Arrows", self.arrows_var, self.render)
        slider("Text fade threshold", self.fade_var, self.render)
        slider("Node size", self.size_var, self.render)
        slider("Link thickness", self.thickness_var, self.render)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(buttons, text="Animate", command=self.animate).grid(row=0, column=0, sticky="ew")
        ttk.Button(buttons, text="Fit", command=self.fit).grid(row=0, column=1, sticky="ew",
                                                              padx=(6, 0))
        folds = ttk.Frame(body)
        folds.pack(fill="x", pady=(6, 0))
        folds.columnconfigure((0, 1), weight=1)
        ttk.Button(folds, text="Fold all", command=lambda: self._fold_all(True)).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(folds, text="Unfold all", command=lambda: self._fold_all(False)).grid(
            row=0, column=1, sticky="ew", padx=(6, 0))

        section("Forces", open_=False)
        slider("Center force", self.center_var, self._forces_changed)
        slider("Repel force", self.repel_var, self._forces_changed)
        slider("Link force", self.link_var, self._forces_changed)
        slider("Link distance", self.distance_var, self._forces_changed)
        self.panel_wanted = True
        return panel

    def _toggle_panel(self) -> None:
        if self.panel.winfo_ismapped():
            self.panel.grid_remove()
            self.panel_wanted = False
        else:
            self.panel.grid()
            self.panel_wanted = True

    def _fill_legend(self) -> None:
        for child in self.legend.winfo_children():
            child.destroy()
        totals: dict[str, int] = {}
        for node in self.graph.nodes:
            if node.kind == "folder" and node.parent == self.graph.index.get("root"):
                totals[node.group] = node.size if self.size_by_var.get() == "space" else node.count
        background = ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"
        ordered = sorted(totals.items(), key=lambda kv: -kv[1])
        columns = 1 if self.size_by_var.get() == "space" else 2  # sizes need the width
        for position, (group, total) in enumerate(ordered):
            row, column = divmod(position, columns)
            cell = ttk.Frame(self.legend)
            cell.grid(row=row, column=column, sticky="w", padx=(0, 8))
            dot = tk.Canvas(cell, width=10, height=10, highlightthickness=0, background=background)
            dot.create_oval(1, 1, 9, 9, fill=self.colour_for(group), outline="")
            dot.pack(side="left", padx=(0, 4))
            amount = human_size(total) if self.size_by_var.get() == "space" else str(total)
            ttk.Label(cell, text="{} {}".format(group, amount)).pack(side="left")

    def colour_for(self, group: str) -> str:
        if not group:
            return self.c["root"]
        if group not in self.colours:
            spare = [c for c in SPARE_COLOURS if c not in self.colours.values()]
            self.colours[group] = GROUP_COLOURS.get(group) or (spare or SPARE_COLOURS)[0]
        return self.colours[group]

    # ------------------------------------------------------------------- data

    def set_data(self, plan, duplicate_groups=()) -> None:
        self.plan = plan
        self.duplicate_groups = list(duplicate_groups)
        self.collapsed = None
        self.view_touched = False
        self._rebuild(keep_positions=False)

    def _rebuild(self, keep_positions: bool = True) -> None:
        if self.plan is None:
            return
        self._stop_tween()
        old = {node.key: (node.x, node.y) for node in self.graph.nodes} if keep_positions else {}
        self.graph = graph_module.build_graph(
            self.plan,
            self.duplicate_groups,
            show_files=self.files_var.get(),
            show_in_place=self.in_place_var.get(),
            show_duplicates=self.duplicates_var.get(),
            collapsed=self.collapsed,
            size_by=self.size_by_var.get(),
        )
        self.collapsed = set(self.graph.collapsed)
        for node in self.graph.nodes:
            if node.key in old:
                node.x, node.y = old[node.key]
            elif old and node.parent is None and node.kind == "file":
                # A newly unfolded file: start it on its folder, not somewhere random.
                folder = next(self.graph.nodes[n] for n in node.neighbours
                              if self.graph.nodes[n].kind != "file")
                if folder.key in old:
                    node.x += old[folder.key][0] - folder.x
                    node.y += old[folder.key][1] - folder.y
        self.sim = graph_module.Simulation(self.graph)
        self._forces_changed(reheat=False)
        self.sim.reheat(0.6 if old else 1.0)
        self.hover = self.selected = self.dragging = None
        self.ticks = 0
        self._create_items()
        self._fill_legend()
        self.restyle()
        self._start()

    def _fold_all(self, fold: bool) -> None:
        if self.plan is None:
            return
        self.collapsed = {
            node.key for node in self.graph.nodes
            if node.kind == "folder" and node.parent == self.graph.index.get("root")
        } if fold else set()
        self._rebuild()

    def _create_items(self) -> None:
        canvas = self.canvas
        canvas.delete("graph")
        self.edge_items = [
            canvas.create_line(0, 0, 0, 0, tags=("graph", "edge"),
                               dash=(4, 3) if edge.kind == "duplicate" else ())
            for edge in self.graph.edges
        ]
        self.node_items = []
        self.label_items = []
        for node in self.graph.nodes:
            label = node.label
            if node.collapsed:
                label += "  +{}".format(node.hidden)
            self.node_items.append(canvas.create_oval(0, 0, 0, 0, tags=("graph", "node")))
            self.label_items.append(canvas.create_text(
                0, 0, anchor="n", text=label, state="hidden", tags=("graph", "label"),
                font=FONT if node.kind == "file" else FOLDER_FONT,
            ))
        self.label_state = [None] * len(self.graph.nodes)
        self.arrow_state = ["none"] * len(self.graph.edges)
        self.edge_hidden = [False] * len(self.graph.edges)
        self.edge_width = 0.0
        canvas.tag_raise("node")
        canvas.tag_raise("label")
        canvas.tag_raise("chrome")
        canvas.itemconfigure(self.empty, state="hidden" if self.graph.nodes else "normal")
        message = ""
        if self.graph.truncated:
            message = ("Too many files open to draw one by one, so only folders are shown.\n"
                       "Fold some folders (double-click them) to see files again.")
        elif any(node.collapsed for node in self.graph.nodes) and self.ticks == 0:
            message = "Big folders start folded. Double-click one to open it."
        self._set_info(message)

    def refresh(self) -> None:
        """Call after the plan's include ticks change elsewhere."""
        self.restyle()

    # --------------------------------------------------------------- simulation

    def _forces_changed(self, reheat: bool = True) -> None:
        self.sim.center = self.center_var.get()
        self.sim.repel = self.repel_var.get()
        self.sim.link = self.link_var.get()
        self.sim.distance = self.distance_var.get()
        if reheat:
            self.sim.reheat(0.5)
            self._start()

    def animate(self) -> None:
        """Shake everything up and let it settle again, like Obsidian's button."""
        self._stop_tween()
        for node in self.graph.nodes:
            node.vx += (hash(node.key) % 41 - 20) * 1.5
            node.vy += (hash(node.key[::-1]) % 41 - 20) * 1.5
        self.sim.reheat(1.0)
        self._start()

    def _start(self) -> None:
        if not self.ticking and self.winfo_ismapped():
            self.ticking = True
            self.after(16, self._tick)

    def _tick(self) -> None:
        busy = self.sim.running or self.dragging is not None or self.tween is not None
        if not self.winfo_ismapped() or not busy:
            self.ticking = False
            self.render()
            return
        if self.tween is not None:
            self._advance_tween()
        else:
            self.sim.step()
            self.ticks += 1
            if self.ticks == 60 and not self.view_touched:
                self.fit()
        self.render()
        self.after(16, self._tick)

    # ------------------------------------------------------------ before / after

    def play(self) -> None:
        """Show every file loose in the folder being tidied, then fly each one
        to the folder it is going to."""
        nodes = self.graph.nodes
        files = [i for i, node in enumerate(nodes)
                 if node.kind == "file" and node.move is not None and node.move.include]
        if not files:
            self._set_info("Nothing to move, so nothing to play." if self.plan else
                           "Scan a folder first.")
            return
        self._stop_tween()
        # Let the layout settle first, so the files fly to where they will stay.
        for _ in range(300):
            if not self.sim.running:
                break
            self.sim.step()
        self.sim.alpha = 0.0
        root = nodes[self.graph.index["root"]]
        files.sort(key=lambda i: (nodes[i].move.bucket.lower(), nodes[i].label.lower()))
        spacing = 16.0 * (0.5 + self.size_var.get() * 2.0)
        start_radius = BASE_RADIUS * root.weight * 6
        flights = []
        for order, index in enumerate(files):
            # A sunflower spiral packs the loose files evenly round the root.
            angle = order * 2.39996
            distance = start_radius + spacing * math.sqrt(order + 1)
            start = (root.x + math.cos(angle) * distance, root.y + math.sin(angle) * distance)
            delay = HOLD + SPREAD * order / max(len(files) - 1, 1)
            flights.append((index, start, (nodes[index].x, nodes[index].y), delay))
            nodes[index].x, nodes[index].y = start
        self.tween = {"began": time.perf_counter(), "flights": flights,
                      "count": len(files),
                      "folders": len({nodes[i].move.bucket for i in files})}
        self.progress = {index: 0.0 for index in files}
        self.hover = self.selected = None
        self._set_info("")
        self.restyle()
        if not self.view_touched:
            self.fit()
        self._start()

    def _advance_tween(self) -> None:
        tween = self.tween
        elapsed = time.perf_counter() - tween["began"]
        nodes = self.graph.nodes
        for index, (sx, sy), (tx, ty), delay in tween["flights"]:
            t = min(max((elapsed - delay) / FLIGHT, 0.0), 1.0)
            self.progress[index] = t
            k = ease(t)
            nodes[index].x = sx + (tx - sx) * k
            nodes[index].y = sy + (ty - sy) * k
        root_name = nodes[self.graph.index["root"]].label
        if elapsed < HOLD:
            caption = "Before: {} files loose in {}".format(tween["count"], root_name)
        elif elapsed < HOLD + SPREAD + FLIGHT:
            caption = "Tidying…"
        else:
            caption = "After: {} files in {} folders".format(tween["count"], tween["folders"])
        self.canvas.itemconfigure(self.caption, text=caption)
        if elapsed > HOLD + SPREAD + FLIGHT + 1.6:  # leave the result up for a moment
            self._stop_tween()

    def _stop_tween(self) -> None:
        if self.tween is None:
            return
        for index, _start, (tx, ty), _delay in self.tween["flights"]:
            if self.progress.get(index, 1.0) < 1.0:
                self.graph.nodes[index].x, self.graph.nodes[index].y = tx, ty
        self.tween = None
        self.progress = {}
        self.canvas.itemconfigure(self.caption, text="")
        self.render()

    # ---------------------------------------------------------------- geometry

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x * self.zoom + self.offset[0], y * self.zoom + self.offset[1]

    def to_world(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.offset[0]) / self.zoom, (y - self.offset[1]) / self.zoom

    def radius(self, node: graph_module.Node) -> float:
        scale = 0.5 + self.size_var.get() * 2.0
        return max(BASE_RADIUS * node.weight * scale * self.zoom ** 0.75, 1.5)

    def node_at(self, x: int, y: int) -> int | None:
        best, best_d = None, 0.0
        for index, node in enumerate(self.graph.nodes):
            sx, sy = self.to_screen(node.x, node.y)
            reach = self.radius(node) + 4
            d = (sx - x) ** 2 + (sy - y) ** 2
            if d <= reach * reach and (best is None or d < best_d):
                best, best_d = index, d
        return best

    def fit(self) -> None:
        nodes = self.graph.nodes
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not nodes or width < 50:
            return
        xs = [node.x for node in nodes]
        ys = [node.y for node in nodes]
        span_x = max(max(xs) - min(xs), 1.0)
        span_y = max(max(ys) - min(ys), 1.0)
        self.zoom = max(min((width - 80) / span_x, (height - 100) / span_y, 2.5), 0.05)
        middle_x, middle_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self.offset = [width / 2 - middle_x * self.zoom, height / 2 - middle_y * self.zoom]
        self.render()

    # ----------------------------------------------------------------- drawing

    def render(self) -> None:
        canvas = self.canvas
        nodes = self.graph.nodes
        c = self.c
        width_px, height_px = canvas.winfo_width(), canvas.winfo_height()
        canvas.coords(self.hint, 14, height_px - 10)
        canvas.coords(self.empty, width_px / 2, height_px / 2)
        canvas.coords(self.gear, width_px - 8, 8)
        canvas.coords(self.play_item, width_px - 8 - self.gear_button.winfo_reqwidth() - 6, 8)
        if len(self.node_items) != len(nodes):
            return
        screen = [self.to_screen(node.x, node.y) for node in nodes]
        radii = [self.radius(node) for node in nodes]
        progress = self.progress

        arrows = self.arrows_var.get()
        width = 0.4 + self.thickness_var.get() * 3.5
        width = round(max(width * min(self.zoom, 1.5) ** 0.5, 0.5), 1)
        if width != self.edge_width:  # reconfiguring every line each frame is slow
            self.edge_width = width
            head = width ** 0.5
            canvas.itemconfigure("edge", width=width,
                                 arrowshape=(6 * head + 3, 7 * head + 3, 2 * head + 1.5))
        for position, (item, edge) in enumerate(zip(self.edge_items, self.graph.edges)):
            # While playing, a file's link appears only once it has arrived.
            hidden = progress.get(edge.a, 1.0) < 1.0 or progress.get(edge.b, 1.0) < 1.0
            if hidden != self.edge_hidden[position]:
                canvas.itemconfigure(item, state="hidden" if hidden else "normal")
                self.edge_hidden[position] = hidden
            if hidden:
                continue
            (ax, ay), (bx, by) = screen[edge.a], screen[edge.b]
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1.0
            ux, uy = dx / length, dy / length
            ra, rb = radii[edge.a], radii[edge.b]
            canvas.coords(item, ax + ux * ra, ay + uy * ra, bx - ux * rb, by - uy * rb)
            arrow = "none"
            if arrows and edge.kind in ("move", "tree") and length > ra + rb + 8:
                arrow = "last"
            if arrow != self.arrow_state[position]:
                canvas.itemconfigure(item, arrow=arrow)
                self.arrow_state[position] = arrow

        # Labels fade in as you zoom: folders first, files once you are close.
        threshold = 0.15 + self.fade_var.get() * 2.0
        query = self.search_var.get().strip().lower()
        lit = self._lit()
        for index, node in enumerate(nodes):
            (x, y), r = screen[index], radii[index]
            canvas.coords(self.node_items[index], x - r, y - r, x + r, y + r)
            if index in lit or (query and query in node.label.lower()):
                strength = 1.0
            elif self.tween is not None and node.kind == "file":
                strength = 0.0
            else:
                start = threshold * (0.07 if node.heavy else 1.0)
                strength = min(max((self.zoom - start) / (start * 0.6), 0.0), 1.0)
                if lit:
                    strength *= 0.25
            item = self.label_items[index]
            if strength <= 0.02:
                state = ("hidden",)
            else:
                state = ("normal", blend(c["bg"], c["text"], strength))
            if state != self.label_state[index]:
                if state[0] == "hidden":
                    canvas.itemconfigure(item, state="hidden")
                else:
                    canvas.itemconfigure(item, state="normal", fill=state[1])
                self.label_state[index] = state
            if state[0] == "normal":
                canvas.coords(item, x, y + r + 3)

    def _lit(self) -> set[int]:
        focus = self.hover if self.hover is not None else self.dragging
        if focus is None:
            return set()
        return {focus, *self.graph.nodes[focus].neighbours}

    def restyle(self) -> None:
        """Recolour after hover, search, include or theme changes."""
        canvas = self.canvas
        nodes = self.graph.nodes
        if len(self.node_items) != len(nodes):
            return
        c = self.c
        lit = self._lit()
        query = self.search_var.get().strip().lower()
        for index, node in enumerate(nodes):
            colour = self.colour_for(node.group)
            if node.kind == "file" and node.move is None:
                colour = blend(colour, c["bg"], 0.55)  # already in place
            dim = (lit and index not in lit) or (query and query not in node.label.lower())
            if dim:
                colour = blend(colour, c["bg"], 0.8)
            fill, outline, border = colour, "", 0
            if node.move is not None and not node.move.include:
                fill, outline, border = c["bg"], colour, 1.5
            if node.collapsed:
                # A folded folder wears a ring, like a stack of dots seen from above.
                outline, border = blend(colour, c["text"], 0.45), 3
            if node.duplicate:
                outline, border = blend(c["duplicate"], c["bg"], 0.8 if dim else 0.0), 2
            if index == self.hover or index == self.selected:
                outline, border = c["accent"], 2.5
            canvas.itemconfigure(self.node_items[index], fill=fill, outline=outline, width=border)

        for item, edge in zip(self.edge_items, self.graph.edges):
            active = lit and edge.a in lit and edge.b in lit and (
                self.hover in (edge.a, edge.b) or self.dragging in (edge.a, edge.b)
            )
            if edge.kind == "duplicate":
                colour = c["duplicate"] if active else blend(c["duplicate"], c["bg"], 0.55)
            else:
                colour = c["accent"] if active else c["edge"]
            if lit and not active:
                colour = blend(colour, c["bg"], 0.6)
            canvas.itemconfigure(item, fill=colour)
            if active:
                canvas.tag_raise(item, "edge")
        self.render()

    def _set_info(self, text: str) -> None:
        self.canvas.itemconfigure(self.info, text=text)

    def _describe(self, index: int) -> str:
        node = self.graph.nodes[index]
        if node.kind == "file":
            if node.move is None:
                where = "already in place"
            elif node.move.include:
                where = "→ " + node.move.bucket
            else:
                where = "skipped, stays where it is"
            lines = ["{}   {}".format(node.label, human_size(node.size)), where]
            if node.duplicate:
                lines.append("has an identical copy")
            return "\n".join(lines)
        what = "folder being tidied" if node.kind == "root" else "folder"
        text = "{}\n{} · {} file(s) · {}".format(node.label, what, node.count,
                                                 human_size(node.size))
        if node.collapsed:
            text += "\nfolded: double-click to open"
        return text

    # ------------------------------------------------------------------ events

    def _on_resize(self, _event) -> None:
        if not self.graph.nodes:
            self.offset = [self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2]
        self.render()

    def _set_hover(self, index: int | None) -> None:
        if index == self.hover:
            return
        self.hover = index
        self.canvas.configure(cursor="hand2" if index is not None else "")
        shown = index if index is not None else self.selected
        self._set_info(self._describe(shown) if shown is not None else "")
        self.restyle()

    def _on_motion(self, event) -> None:
        if self.dragging is None and self.pan_from is None and self.tween is None:
            self._set_hover(self.node_at(event.x, event.y))

    def _on_press(self, event) -> None:
        self.pressed_at = (event.x, event.y)
        self.moved = False
        index = self.node_at(event.x, event.y) if self.tween is None else None
        if index is not None:
            self.dragging = index
            self.graph.nodes[index].fixed = True
        else:
            self.pan_from = (event.x, event.y)

    def _on_drag(self, event) -> None:
        if self.pressed_at and abs(event.x - self.pressed_at[0]) + abs(event.y - self.pressed_at[1]) > 3:
            self.moved = True
        if self.dragging is not None:
            node = self.graph.nodes[self.dragging]
            node.x, node.y = self.to_world(event.x, event.y)
            if self.moved:
                self.sim.reheat(0.3)
                self._start()
            self.render()
        elif self.pan_from is not None:
            self.offset[0] += event.x - self.pan_from[0]
            self.offset[1] += event.y - self.pan_from[1]
            self.pan_from = (event.x, event.y)
            self.view_touched = True
            self.render()

    def _on_release(self, event) -> None:
        if self.dragging is not None:
            self.graph.nodes[self.dragging].fixed = False
            if not self.moved:
                self.selected = self.dragging
                self._set_info(self._describe(self.dragging))
        elif not self.moved and self.tween is None:
            self.selected = None
            self._set_info("")
        self.dragging = None
        self.pan_from = None
        self.restyle()

    def _on_double(self, event) -> None:
        index = self.node_at(event.x, event.y)
        if index is None:
            return
        node = self.graph.nodes[index]
        if node.kind == "folder":
            self._fold(index)
        elif node.path and self.on_open:
            self.on_open(node.path)  # a file opens; the root opens in Explorer

    def _fold(self, index: int) -> None:
        self.collapsed ^= {self.graph.nodes[index].key}
        self._rebuild()

    def _toggle_include(self, index: int) -> None:
        node = self.graph.nodes[index]
        if node.move is not None and self.on_toggle:
            self.on_toggle(node.move)
            self._set_info(self._describe(index))
            self.restyle()

    def _on_right_click(self, event) -> None:
        index = self.node_at(event.x, event.y)
        if index is None or self.tween is not None:
            return
        node = self.graph.nodes[index]
        path = node.path
        menu = tk.Menu(self, tearoff=False, **self.menu_colours)

        def command(label: str, action, enabled: bool = True) -> None:
            menu.add_command(label=label, command=action,
                             state="normal" if enabled else "disabled")

        if node.kind == "file":
            command("Open", lambda: self.on_open and self.on_open(path))
            command("Show in Explorer", lambda: self.on_reveal and self.on_reveal(path))
            if node.move is not None:
                menu.add_separator()
                command("Skip this file" if node.move.include else "Include this file",
                        lambda: self._toggle_include(index))
        else:
            exists = bool(path) and os.path.isdir(path)
            command("Open folder" if exists or not path else "Open folder (made when you apply)",
                    lambda: self.on_open and self.on_open(path), exists)
            if node.kind == "folder":
                command("Unfold" if node.collapsed else "Fold", lambda: self._fold(index))
        menu.tk_popup(event.x_root, event.y_root)

    def _on_wheel(self, event) -> None:
        self._zoom_at(event.x, event.y, 1.1 ** (event.delta / 120))

    def _zoom_at(self, x: int, y: int, factor: float) -> None:
        wx, wy = self.to_world(x, y)
        self.zoom = min(max(self.zoom * factor, 0.05), 8.0)
        self.offset = [x - wx * self.zoom, y - wy * self.zoom]
        self.view_touched = True
        self.render()
