"""Turning a scan into a list of proposed moves.

Nothing here touches the disk. The GUI shows the plan, the user approves it,
and only then does :mod:`organiser.apply` act on it.
"""

from __future__ import annotations

import datetime
import os
import sys
import time
from dataclasses import dataclass

from . import rules
from .scan import FileInfo, ScanResult

#: Buckets routed to the user's own folders when ``route_to_libraries``.
#: A Mac calls the videos folder "Movies".
_VIDEOS = "Movies" if sys.platform == "darwin" else "Videos"
LIBRARY_ROOTS = {
    "Pictures": "Pictures",
    "Pictures/Raw": "Pictures",
    "Pictures/Vector": "Pictures",
    "Pictures/Screenshots": "Pictures",
    "Videos": _VIDEOS,
    "Audio": "Music",
    "Documents": "Documents",
    "Documents/Spreadsheets": "Documents",
    "Documents/Presentations": "Documents",
    "Documents/Ebooks": "Documents",
}


#: Top-level buckets that ``date_folders`` splits by year or month.
DATED_BUCKETS = ("Pictures", "Videos")


def _date_parts(mtime: float, date_folders: str) -> list[str]:
    if date_folders not in ("year", "month"):
        return []
    when = datetime.datetime.fromtimestamp(mtime)
    return [f"{when:%Y}"] if date_folders == "year" else [f"{when:%Y}", f"{when:%m}"]


@dataclass
class Move:
    info: FileInfo
    destination_folder: str   # absolute
    destination: str          # absolute, including filename
    bucket: str               # e.g. "Apps/Blender"
    renamed: bool = False
    include: bool = True

    @property
    def source(self) -> str:
        return self.info.path


@dataclass
class Plan:
    root: str
    moves: list[Move]
    already_tidy: list[FileInfo]
    skipped: list[tuple[str, str]]
    unreadable: list[tuple[str, str]]

    @property
    def selected(self) -> list[Move]:
        return [m for m in self.moves if m.include]


def _unique_destination(folder: str, name: str, taken: set[str]) -> tuple[str, bool]:
    """Pick a free filename in *folder*, suffixing " (2)" and so on."""
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    if candidate.lower() not in taken and not os.path.exists(candidate):
        taken.add(candidate.lower())
        return candidate, False
    counter = 2
    while True:
        candidate = os.path.join(folder, f"{stem} ({counter}){ext}")
        if candidate.lower() not in taken and not os.path.exists(candidate):
            taken.add(candidate.lower())
            return candidate, True
        counter += 1


def build_plan(
    result: ScanResult,
    route_to_libraries: bool = False,
    home: str | None = None,
    overrides: dict[str, str] | None = None,
    include_other: bool = True,
    settle_seconds: float = 0,
    now: float | None = None,
    date_folders: str = "off",
) -> Plan:
    """Decide where each scanned file should go.

    With ``route_to_libraries`` set, media and documents are sent to the real
    user folders (``~/Pictures`` etc.) and everything else stays in subfolders
    of the scanned root.

    Files modified less than ``settle_seconds`` ago are left alone: some
    browsers and download tools write straight to the final filename, so a
    fresh file may still be arriving.

    ``date_folders`` ("off", "year" or "month") files photos and videos under
    the date they were last modified, e.g. ``Pictures/2026/10``.
    """
    home = home or os.path.expanduser("~")
    moves: list[Move] = []
    already_tidy: list[FileInfo] = []
    taken: set[str] = set()
    skipped = list(result.skipped)
    now = time.time() if now is None else now

    for info in result.files:
        if settle_seconds and now - info.mtime < settle_seconds:
            skipped.append((info.path, "changed in the last few minutes, may still be downloading"))
            continue
        bucket = rules.destination_for(info.name, overrides)
        if bucket == rules.FALLBACK and not include_other:
            already_tidy.append(info)
            continue

        if route_to_libraries and bucket in LIBRARY_ROOTS:
            library = LIBRARY_ROOTS[bucket]
            tail = bucket.split("/", 1)[1] if "/" in bucket else ""
            base = os.path.join(home, library, tail) if tail else os.path.join(home, library)
        else:
            base = os.path.join(result.root, *bucket.split("/"))

        if bucket.split("/")[0] in DATED_BUCKETS:
            parts = _date_parts(info.mtime, date_folders)
            if parts:
                base = os.path.join(base, *parts)
                bucket = "/".join([bucket, *parts])

        base = os.path.abspath(base)
        if os.path.abspath(os.path.dirname(info.path)) == base:
            already_tidy.append(info)
            continue

        destination, renamed = _unique_destination(base, info.name, taken)
        moves.append(
            Move(
                info=info,
                destination_folder=base,
                destination=destination,
                bucket=bucket,
                renamed=renamed,
            )
        )

    moves.sort(key=lambda m: (m.bucket.lower(), m.info.name.lower()))
    return Plan(
        root=result.root,
        moves=moves,
        already_tidy=already_tidy,
        skipped=skipped,
        unreadable=result.unreadable,
    )
