"""The plan as a force-directed graph: where every file is going.

The scanned folder sits in the middle, destination folders branch off it, and
each file is a dot tied to the folder it will move into. Copies of the same
file are linked to each other. A folder can be folded, which hides the files
and folders inside it behind the one dot.

Pure data and arithmetic, no Tk, so it can be tested. :mod:`organiser.graphview`
draws it.
"""

from __future__ import annotations

import math
import os
import random
from collections import Counter
from dataclasses import dataclass, field

from .plan import Move, Plan

#: Tk cannot animate many more files than this. Bigger scans start with their
#: largest folders folded.
MAX_FILE_NODES = 1000

ALPHA_MIN = 0.005
ALPHA_DECAY = 0.03
VELOCITY_DECAY = 0.6
MAX_SPEED = 60.0
REPEL_CUTOFF = 320.0  # beyond this, only folders push each other apart


@dataclass
class Node:
    key: str
    label: str
    kind: str                 # "root", "folder" or "file"
    group: str                # top-level folder, used for colour ("" for the root)
    weight: float = 1.0       # relative size, before the user's node-size setting
    path: str | None = None
    move: Move | None = None  # set for files the plan would move
    size: int = 0
    count: int = 0            # files at or below a folder
    parent: int | None = None  # the folder above a folder
    collapsed: bool = False   # a folded folder
    hidden: int = 0           # files folded away inside it
    duplicate: bool = False
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    fixed: bool = False
    neighbours: set[int] = field(default_factory=set)

    @property
    def heavy(self) -> bool:
        return self.kind != "file"


@dataclass
class Edge:
    a: int
    b: int
    kind: str  # "tree" (folder to folder), "move", "in-place" or "duplicate"


class Graph:
    def __init__(self, seed: int = 7) -> None:
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.index: dict[str, int] = {}
        self.truncated = False
        self.collapsed: set[str] = set()  # folder keys that are folded
        self._random = random.Random(seed)

    def add_node(self, node: Node, near: int | None = None, spread: float = 80.0) -> int:
        """Add *node*, placed at a random spot around node *near*."""
        if node.key in self.index:
            return self.index[node.key]
        angle = self._random.uniform(0, 2 * math.pi)
        distance = self._random.uniform(0.5, 1.0) * spread
        if near is not None:
            node.x = self.nodes[near].x + math.cos(angle) * distance
            node.y = self.nodes[near].y + math.sin(angle) * distance
        self.index[node.key] = len(self.nodes)
        self.nodes.append(node)
        return self.index[node.key]

    def add_edge(self, a: int, b: int, kind: str) -> None:
        if a == b or b in self.nodes[a].neighbours:
            return
        self.edges.append(Edge(a, b, kind))
        self.nodes[a].neighbours.add(b)
        self.nodes[b].neighbours.add(a)

    def folder(self, bucket: str) -> int:
        """The node for *bucket* ("Pictures/2026"), creating its parents too."""
        parent = self.index["root"]
        parts = [part for part in bucket.split("/") if part]
        for depth in range(len(parts)):
            key = folder_key(parts[: depth + 1])
            if key not in self.index:
                index = self.add_node(
                    Node(key=key, label=parts[depth], kind="folder", group=parts[0],
                         parent=parent),
                    near=parent,
                    spread=220.0 if depth == 0 else 120.0,
                )
                self.add_edge(parent, index, "tree")
            parent = self.index[key]
        return parent


def folder_key(parts: list[str]) -> str:
    return "folder:" + "/".join(parts).lower()


def _parts(bucket: str | None) -> list[str]:
    return [part for part in (bucket or "").split("/") if part]


def auto_collapse(entries, max_files: int) -> set[str]:
    """Fold the biggest top-level folders until at most *max_files* show."""
    totals = Counter(folder_key(parts[:1]) for parts, *_rest in entries if parts)
    shown, collapsed = len(entries), set()
    for key, count in totals.most_common():
        if shown <= max_files:
            break
        collapsed.add(key)
        shown -= count
    return collapsed


def _file_weight(size: int) -> float:
    return 0.7 + min(math.log10(size + 1) / 8, 0.9)


def _relative_folder(path: str, root: str) -> str | None:
    """*path*'s folder relative to *root*, with "/" separators, or None if outside."""
    try:
        relative = os.path.relpath(os.path.dirname(path), root)
    except ValueError:  # different drive
        return None
    if relative.startswith(".."):
        return None
    return "" if relative == "." else relative.replace(os.sep, "/")


def build_graph(
    plan: Plan,
    duplicate_groups=(),
    show_files: bool = True,
    show_in_place: bool = False,
    show_duplicates: bool = True,
    max_files: int = MAX_FILE_NODES,
    collapsed: set[str] | None = None,
    size_by: str = "count",
) -> Graph:
    """Build the graph for *plan*.

    *collapsed* holds the keys of folded folders; None folds the biggest ones
    when there are more than *max_files* files. *size_by* is "count" (dots
    grow with the number of files) or "space" (with the disk space they use).
    """
    graph = Graph()
    root_name = os.path.basename(os.path.normpath(plan.root)) or plan.root
    graph.add_node(Node(key="root", label=root_name, kind="root", group="", path=plan.root))

    entries: list[tuple[list[str], object, str, Move | None]] = []
    for move in plan.moves:
        entries.append((_parts(move.bucket), move.info, "move", move))
    if show_in_place:
        for info in plan.already_tidy:
            entries.append((_parts(_relative_folder(info.path, plan.root)), info, "in-place", None))

    if collapsed is None:
        collapsed = auto_collapse(entries, max_files) if show_files else set()
    graph.collapsed = set(collapsed)

    placed: list[tuple[int, object, str, Move | None]] = []  # (folder, info, edge kind, move)
    for parts, info, kind, move in entries:
        hidden = False
        where = move.destination_folder if move else os.path.dirname(info.path)
        for depth in range(len(parts)):
            if folder_key(parts[: depth + 1]) in graph.collapsed:
                for _ in range(len(parts) - depth - 1):  # the folded folder's own path
                    where = os.path.dirname(where)
                parts, hidden = parts[: depth + 1], True
                break
        folder = graph.folder("/".join(parts))
        # Fill in this folder's path and its parents'. They may not exist on disk
        # until the moves are applied.
        index = folder
        while graph.nodes[index].kind == "folder" and graph.nodes[index].path is None:
            graph.nodes[index].path = where
            where = os.path.dirname(where)
            index = graph.nodes[index].parent
        if hidden:
            graph.nodes[folder].collapsed = True
            graph.nodes[folder].hidden += 1
        else:
            placed.append((folder, info, kind, move))
        index: int | None = folder
        while index is not None:  # count the file against every folder above it
            graph.nodes[index].count += 1
            graph.nodes[index].size += info.size
            index = graph.nodes[index].parent

    files_drawn = show_files and len(placed) <= max_files
    graph.truncated = show_files and not files_drawn
    if files_drawn:
        for folder, info, kind, move in placed:
            index = graph.add_node(
                Node(
                    key="file:" + os.path.normcase(info.path),
                    label=info.name,
                    kind="file",
                    group=graph.nodes[folder].group,
                    path=info.path,
                    move=move,
                    size=info.size,
                ),
                near=folder,
                spread=60.0,
            )
            graph.add_edge(index, folder, kind)

        for group in duplicate_groups:
            present = [graph.index.get("file:" + os.path.normcase(info.path)) for info in group.files]
            present = [index for index in present if index is not None]
            if len(present) < 2:
                continue
            for index in present:
                graph.nodes[index].duplicate = True
            if show_duplicates:
                for other in present[1:]:
                    graph.add_edge(present[0], other, "duplicate")

    _set_weights(graph, size_by)
    return graph


def _set_weights(graph: Graph, size_by: str) -> None:
    folders = [node for node in graph.nodes if node.kind == "folder"]
    files = [node for node in graph.nodes if node.kind == "file"]
    biggest_folder = max((node.size for node in folders), default=0) or 1
    biggest_file = max((node.size for node in files), default=0) or 1
    for node in graph.nodes:
        if node.kind == "root":
            node.weight = 3.2
        elif size_by == "space":
            # Area, not width, follows the size, so a file twice as big looks it.
            share = node.size / (biggest_folder if node.kind == "folder" else biggest_file)
            node.weight = (1.2 + 3.8 * math.sqrt(share)) if node.kind == "folder"                 else (0.5 + 2.7 * math.sqrt(share))
        elif node.kind == "folder":
            node.weight = min(1.6 + math.sqrt(node.count) * 0.3, 5.0)
        else:
            node.weight = _file_weight(node.size)


class Simulation:
    """A small d3-style force layout: links, many-body repulsion, centring.

    The four settings run from 0 to 1, like the sliders that drive them.
    """

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.alpha = 1.0
        self.center = 0.3
        self.repel = 0.5
        self.link = 0.5
        self.distance = 0.4

    @property
    def running(self) -> bool:
        return self.alpha > ALPHA_MIN

    def reheat(self, alpha: float = 1.0) -> None:
        self.alpha = max(self.alpha, alpha)

    def step(self) -> None:
        nodes = self.graph.nodes
        if not nodes:
            self.alpha = 0.0
            return
        alpha = self.alpha
        self._links(nodes, alpha)
        self._repel(nodes, alpha)
        pull = self.center * 0.04 * alpha
        for node in nodes:
            if node.fixed:
                node.vx = node.vy = 0.0
                continue
            node.vx = (node.vx - node.x * pull) * VELOCITY_DECAY
            node.vy = (node.vy - node.y * pull) * VELOCITY_DECAY
            speed = math.hypot(node.vx, node.vy)
            if speed > MAX_SPEED:
                node.vx *= MAX_SPEED / speed
                node.vy *= MAX_SPEED / speed
            node.x += node.vx
            node.y += node.vy
        self.alpha += (0.0 - self.alpha) * ALPHA_DECAY
        if self.alpha < ALPHA_MIN:
            self.alpha = 0.0

    def _links(self, nodes: list[Node], alpha: float) -> None:
        base = 30 + self.distance * 200
        strength = 0.05 + self.link * 0.7
        for edge in self.graph.edges:
            a, b = nodes[edge.a], nodes[edge.b]
            if edge.kind == "tree":
                length, k = base * 2.6, strength
            elif edge.kind == "duplicate":
                length, k = base * 1.2, strength * 0.25
            else:
                length, k = base * 0.55, strength
            dx = (b.x + b.vx) - (a.x + a.vx)
            dy = (b.y + b.vy) - (a.y + a.vy)
            distance = math.hypot(dx, dy) or 0.01
            shift = (distance - length) / distance * alpha * k
            dx *= shift
            dy *= shift
            degree_a, degree_b = len(a.neighbours), len(b.neighbours)
            bias = degree_a / (degree_a + degree_b)  # the busier end moves less
            b.vx -= dx * bias
            b.vy -= dy * bias
            a.vx += dx * (1 - bias)
            a.vy += dy * (1 - bias)

    def _repel(self, nodes: list[Node], alpha: float) -> None:
        charge = (10 + self.repel * 300) * alpha
        strength = [charge * node.weight * (8.0 if node.heavy else 1.0) for node in nodes]
        xs = [node.x for node in nodes]
        ys = [node.y for node in nodes]
        vx = [0.0] * len(nodes)
        vy = [0.0] * len(nodes)
        cutoff2 = REPEL_CUTOFF * REPEL_CUTOFF

        def push(i: int, j: int) -> None:
            dx, dy = xs[j] - xs[i], ys[j] - ys[i]
            d2 = dx * dx + dy * dy
            if d2 < 1.0:  # on top of each other: nudge apart in a fixed direction
                dx, dy, d2 = 0.5 + (i % 7) * 0.1, 0.5 - (j % 5) * 0.1, 1.0
            vx[i] -= dx * strength[j] / d2
            vy[i] -= dy * strength[j] / d2
            vx[j] += dx * strength[i] / d2
            vy[j] += dy * strength[i] / d2

        # Near neighbours, found through a grid so big graphs stay quick. The
        # pair loop is written out by hand because it runs millions of times.
        cells: dict[tuple[int, int], list[int]] = {}
        for i in range(len(nodes)):
            cells.setdefault((int(xs[i] // REPEL_CUTOFF), int(ys[i] // REPEL_CUTOFF)), []).append(i)
        for (cx, cy), members in cells.items():
            for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 1)):
                same = (ox, oy) == (0, 0)
                others = members if same else cells.get((cx + ox, cy + oy))
                if not others:
                    continue
                for position, i in enumerate(members):
                    xi, yi, si = xs[i], ys[i], strength[i]
                    fx = fy = 0.0
                    for j in (others[position + 1:] if same else others):
                        dx, dy = xs[j] - xi, ys[j] - yi
                        d2 = dx * dx + dy * dy
                        if d2 >= cutoff2:
                            continue
                        if d2 < 1.0:
                            push(i, j)
                            continue
                        sj = strength[j] / d2
                        fx -= dx * sj
                        fy -= dy * sj
                        si_d2 = si / d2
                        vx[j] += dx * si_d2
                        vy[j] += dy * si_d2
                    vx[i] += fx
                    vy[i] += fy

        # Folders also push each other from afar, which spreads the clusters out.
        heavy = [i for i, node in enumerate(nodes) if node.heavy]
        for position, i in enumerate(heavy):
            for j in heavy[position + 1:]:
                dx, dy = xs[j] - xs[i], ys[j] - ys[i]
                if dx * dx + dy * dy >= cutoff2:
                    push(i, j)

        for node, dvx, dvy in zip(nodes, vx, vy):
            node.vx += dvx
            node.vy += dvy
