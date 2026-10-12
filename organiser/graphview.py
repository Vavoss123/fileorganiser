"""An interactive, animated view of :mod:`organiser.graph`, in the style of
Obsidian's graph view.

Scroll to zoom, drag the background to pan, drag a dot to pull it about.
Hovering a dot lights up what it is linked to. Right-click a file to include
or skip it, double-click to show it in Explorer.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import graph as graph_module
from .plan import Move

BACKGROUND = "#1e1f22"
EDGE = "#3c3f46"
EDGE_ACTIVE = "#a28bfe"
ACCENT = "#a28bfe"
TEXT = "#d4d6db"
MUTED = "#7f848e"
DUPLICATE = "#ff6b6b"
ROOT = "#e8e9ec"
FONT = ("Segoe UI", 9)
FOLDER_FONT = ("Segoe UI", 9, "bold")

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


class GraphView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_toggle: Callable[[Move], None] | None = None,
        on_reveal: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_toggle = on_toggle
        self.on_reveal = on_reveal
        self.plan = None
        self.duplicate_groups = []
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
        self.node_items: list[int] = []
        self.label_items: list[int] = []
        self.edge_items: list[int] = []
        self.label_state: list[tuple | None] = []
        self.arrow_state: list[str] = []
        self.edge_width = 0.0
        self.colours: dict[str, str] = {}

        self.search_var = tk.StringVar()
        self.files_var = tk.BooleanVar(value=True)
        self.in_place_var = tk.BooleanVar(value=False)
        self.duplicates_var = tk.BooleanVar(value=True)
        self.arrows_var = tk.BooleanVar(value=True)
        self.fade_var = tk.DoubleVar(value=0.45)
        self.size_var = tk.DoubleVar(value=0.4)
        self.thickness_var = tk.DoubleVar(value=0.3)
        self.center_var = tk.DoubleVar(value=self.sim.center)
        self.repel_var = tk.DoubleVar(value=self.sim.repel)
        self.link_var = tk.DoubleVar(value=self.sim.link)
        self.distance_var = tk.DoubleVar(value=self.sim.distance)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=BACKGROUND, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.panel = self._scrolling(self._build_panel)
        self.panel.grid(row=0, column=1, sticky="ns")
        self.panel_button = tk.Button(
            self.canvas, text="⚙", command=self._toggle_panel, relief="flat",
            background=BACKGROUND, foreground=TEXT, activebackground="#2b2d31",
            activeforeground=TEXT, borderwidth=0, font=("Segoe UI", 12), cursor="hand2",
        )
        self.gear = self.canvas.create_window(0, 0, window=self.panel_button, anchor="ne",
                                              tags="chrome")
        self.info = self.canvas.create_text(14, 12, anchor="nw", fill=TEXT, font=FONT,
                                            text="", tags="chrome")
        self.hint = self.canvas.create_text(
            14, 0, anchor="sw", fill=MUTED, font=FONT, tags="chrome",
            text="Scroll to zoom · drag to pan · right-click a file to include or skip it "
                 "· double-click to show in Explorer",
        )
        self.empty = self.canvas.create_text(0, 0, fill=MUTED, font=("Segoe UI", 11),
                                             text="Scan a folder to see its graph.")

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

    # ------------------------------------------------------------------ panel

    def _scrolling(self, build) -> ttk.Frame:
        """Wrap the settings panel so it scrolls when the window is short."""
        outer = ttk.Frame(self)
        outer.rowconfigure(0, weight=1)
        holder = tk.Canvas(outer, width=250, highlightthickness=0, borderwidth=0,
                           background=ttk.Style().lookup("TFrame", "background") or "#f0f0f0")
        holder.grid(row=0, column=0, sticky="ns")
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

        section("Forces", open_=False)
        slider("Center force", self.center_var, self._forces_changed)
        slider("Repel force", self.repel_var, self._forces_changed)
        slider("Link force", self.link_var, self._forces_changed)
        slider("Link distance", self.distance_var, self._forces_changed)
        return panel

    def _toggle_panel(self) -> None:
        if self.panel.winfo_ismapped():
            self.panel.grid_remove()
        else:
            self.panel.grid()

    def _fill_legend(self) -> None:
        for child in self.legend.winfo_children():
            child.destroy()
        counts: dict[str, int] = {}
        for node in self.graph.nodes:
            if node.kind == "folder" and node.parent == self.graph.index.get("root"):
                counts[node.group] = node.count
        ordered = sorted(counts.items(), key=lambda kv: -kv[1])
        for position, (group, count) in enumerate(ordered):
            row, column = divmod(position, 2)
            cell = ttk.Frame(self.legend)
            cell.grid(row=row, column=column, sticky="w", padx=(0, 8))
            dot = tk.Canvas(cell, width=10, height=10, highlightthickness=0,
                            background=ttk.Style().lookup("TFrame", "background") or "#f0f0f0")
            dot.create_oval(1, 1, 9, 9, fill=self.colour_for(group), outline="")
            dot.pack(side="left", padx=(0, 4))
            ttk.Label(cell, text="{} {}".format(group, count)).pack(side="left")

    def colour_for(self, group: str) -> str:
        if not group:
            return ROOT
        if group not in self.colours:
            spare = [c for c in SPARE_COLOURS if c not in self.colours.values()]
            self.colours[group] = GROUP_COLOURS.get(group) or (spare or SPARE_COLOURS)[0]
        return self.colours[group]

    # ------------------------------------------------------------------- data

    def set_data(self, plan, duplicate_groups=()) -> None:
        self.plan = plan
        self.duplicate_groups = list(duplicate_groups)
        self.view_touched = False
        self._rebuild(keep_positions=False)

    def _rebuild(self, keep_positions: bool = True) -> None:
        if self.plan is None:
            return
        old = {node.key: (node.x, node.y) for node in self.graph.nodes} if keep_positions else {}
        self.graph = graph_module.build_graph(
            self.plan,
            self.duplicate_groups,
            show_files=self.files_var.get(),
            show_in_place=self.in_place_var.get(),
            show_duplicates=self.duplicates_var.get(),
        )
        for node in self.graph.nodes:
            if node.key in old:
                node.x, node.y = old[node.key]
        self.sim = graph_module.Simulation(self.graph)
        self._forces_changed(reheat=False)
        self.sim.reheat(0.6 if old else 1.0)
        self.hover = self.selected = self.dragging = None
        self.ticks = 0
        self._create_items()
        self._fill_legend()
        self.restyle()
        self._start()

    def _create_items(self) -> None:
        canvas = self.canvas
        canvas.delete("graph")
        self.edge_items = [
            canvas.create_line(0, 0, 0, 0, fill=EDGE, tags=("graph", "edge"),
                               dash=(4, 3) if edge.kind == "duplicate" else ())
            for edge in self.graph.edges
        ]
        self.node_items = []
        self.label_items = []
        for node in self.graph.nodes:
            self.node_items.append(canvas.create_oval(0, 0, 0, 0, tags=("graph", "node")))
            self.label_items.append(canvas.create_text(
                0, 0, anchor="n", text=node.label, state="hidden", tags=("graph", "label"),
                font=FONT if node.kind == "file" else FOLDER_FONT,
            ))
        self.label_state = [None] * len(self.graph.nodes)
        self.arrow_state = ["none"] * len(self.graph.edges)
        self.edge_width = 0.0
        canvas.tag_raise("node")
        canvas.tag_raise("label")
        canvas.tag_raise("chrome")
        canvas.itemconfigure(self.empty, state="hidden" if self.graph.nodes else "normal")
        message = ""
        if self.graph.truncated:
            message = "Too many files to draw one by one, so only folders are shown."
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
        if not self.winfo_ismapped() or not (self.sim.running or self.dragging is not None):
            self.ticking = False
            self.render()
            return
        self.sim.step()
        self.ticks += 1
        if self.ticks == 60 and not self.view_touched:
            self.fit()
        self.render()
        self.after(16, self._tick)

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
        self.zoom = max(min((width - 80) / span_x, (height - 80) / span_y, 2.5), 0.05)
        middle_x, middle_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self.offset = [width / 2 - middle_x * self.zoom, height / 2 - middle_y * self.zoom]
        self.render()

    # ----------------------------------------------------------------- drawing

    def render(self) -> None:
        canvas = self.canvas
        nodes = self.graph.nodes
        if len(self.node_items) != len(nodes):
            return
        screen = [self.to_screen(node.x, node.y) for node in nodes]
        radii = [self.radius(node) for node in nodes]

        arrows = self.arrows_var.get()
        width = 0.4 + self.thickness_var.get() * 3.5
        width = round(max(width * min(self.zoom, 1.5) ** 0.5, 0.5), 1)
        if width != self.edge_width:  # reconfiguring every line each frame is slow
            self.edge_width = width
            head = width ** 0.5
            canvas.itemconfigure("edge", width=width,
                                 arrowshape=(6 * head + 3, 7 * head + 3, 2 * head + 1.5))
        for position, (item, edge) in enumerate(zip(self.edge_items, self.graph.edges)):
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
            else:
                start = threshold * (0.12 if node.heavy else 1.0)
                strength = min(max((self.zoom - start) / (start * 0.6), 0.0), 1.0)
                if lit:
                    strength *= 0.25
            item = self.label_items[index]
            if strength <= 0.02:
                state = ("hidden",)
            else:
                state = ("normal", blend(BACKGROUND, TEXT, strength))
            if state != self.label_state[index]:
                if state[0] == "hidden":
                    canvas.itemconfigure(item, state="hidden")
                else:
                    canvas.itemconfigure(item, state="normal", fill=state[1])
                self.label_state[index] = state
            if state[0] == "normal":
                canvas.coords(item, x, y + r + 3)

        canvas.coords(self.hint, 14, canvas.winfo_height() - 10)
        canvas.coords(self.empty, canvas.winfo_width() / 2, canvas.winfo_height() / 2)
        canvas.coords(self.gear, canvas.winfo_width() - 8, 8)

    def _lit(self) -> set[int]:
        focus = self.hover if self.hover is not None else self.dragging
        if focus is None:
            return set()
        return {focus, *self.graph.nodes[focus].neighbours}

    def restyle(self) -> None:
        """Recolour after hover, search or include changes."""
        canvas = self.canvas
        nodes = self.graph.nodes
        if len(self.node_items) != len(nodes):
            return
        lit = self._lit()
        query = self.search_var.get().strip().lower()
        for index, node in enumerate(nodes):
            colour = self.colour_for(node.group)
            if node.kind == "file" and node.move is None:
                colour = blend(colour, BACKGROUND, 0.55)  # already in place
            dim = (lit and index not in lit) or (query and query not in node.label.lower())
            if dim:
                colour = blend(colour, BACKGROUND, 0.8)
            fill, outline, border = colour, "", 0
            if node.move is not None and not node.move.include:
                fill, outline, border = BACKGROUND, colour, 1.5
            if node.duplicate:
                outline, border = blend(DUPLICATE, BACKGROUND, 0.8 if dim else 0.0), 2
            if index == self.hover or index == self.selected:
                outline, border = ACCENT, 2.5
            canvas.itemconfigure(self.node_items[index], fill=fill, outline=outline, width=border)

        for item, edge in zip(self.edge_items, self.graph.edges):
            active = lit and edge.a in lit and edge.b in lit and (
                self.hover in (edge.a, edge.b) or self.dragging in (edge.a, edge.b)
            )
            if edge.kind == "duplicate":
                colour = DUPLICATE if active else blend(DUPLICATE, BACKGROUND, 0.55)
            else:
                colour = EDGE_ACTIVE if active else EDGE
            if lit and not active:
                colour = blend(colour, BACKGROUND, 0.6)
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
        return "{}\n{} · {} file(s) · {}".format(node.label, what, node.count,
                                                 human_size(node.size))

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
        if self.dragging is None and self.pan_from is None:
            self._set_hover(self.node_at(event.x, event.y))

    def _on_press(self, event) -> None:
        self.pressed_at = (event.x, event.y)
        self.moved = False
        index = self.node_at(event.x, event.y)
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
        elif not self.moved:
            self.selected = None
            self._set_info("")
        self.dragging = None
        self.pan_from = None
        self.restyle()

    def _on_double(self, event) -> None:
        index = self.node_at(event.x, event.y)
        if index is not None and self.on_reveal and self.graph.nodes[index].path:
            self.on_reveal(self.graph.nodes[index].path)

    def _on_right_click(self, event) -> None:
        index = self.node_at(event.x, event.y)
        if index is None:
            return
        node = self.graph.nodes[index]
        if node.move is not None and self.on_toggle:
            self.on_toggle(node.move)
            self._set_info(self._describe(index))
            self.restyle()

    def _on_wheel(self, event) -> None:
        self._zoom_at(event.x, event.y, 1.1 ** (event.delta / 120))

    def _zoom_at(self, x: int, y: int, factor: float) -> None:
        wx, wy = self.to_world(x, y)
        self.zoom = min(max(self.zoom * factor, 0.05), 8.0)
        self.offset = [x - wx * self.zoom, y - wy * self.zoom]
        self.view_touched = True
        self.render()
