"""Clearing out files the user has agreed they don't need.

Everything goes to the Recycle Bin (or the Mac Trash), never a permanent delete, and every file
is re-checked first: the scan may be minutes old by the time the user acts.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from . import duplicates, rules, system
from .recycle import send_to_recycle_bin
from .scan import FileInfo

#: The bucket installers are filed under, and the folder looked in for old ones.
INSTALLERS = "Installers"


@dataclass
class RecycleReport:
    recycled: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    freed: int = 0

    @property
    def summary(self) -> str:
        parts = ["{} file(s) sent to the {}".format(len(self.recycled), system.BIN)]
        if self.failed:
            parts.append("{} left alone".format(len(self.failed)))
        return ", ".join(parts)


def recycle_duplicates(
    groups: list[duplicates.DuplicateGroup], recycler=send_to_recycle_bin
) -> RecycleReport:
    """Recycle every redundant copy, but only while its keeper still matches.

    A copy is only removed if the file being kept is still there with the
    same content, and the copy itself is unchanged since the scan.
    """
    report = RecycleReport()
    for group in groups:
        keeper = group.keeper.path
        if not _matches(keeper, group.digest):
            for info in group.redundant:
                report.failed.append((info.path, "the copy being kept has changed or moved"))
            continue
        for info in group.redundant:
            if not _matches(info.path, group.digest):
                report.failed.append((info.path, "changed or moved since the scan"))
                continue
            _recycle(info.path, info.size, report, recycler)
    return report


def old_installers(files: list[FileInfo], days: float = 30, now: float | None = None) -> list[FileInfo]:
    """Setup files not touched for *days*, usually already installed, or never will be.

    Goes by extension, not by where the file sits, so the built-in rule is
    used even if the user sends ``.exe`` somewhere of their own.
    """
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    seen: set[str] = set()
    out = []
    for info in files:
        key = os.path.normcase(info.path)
        if key in seen or rules.TYPE_RULES.get(info.ext) != INSTALLERS or info.mtime >= cutoff:
            continue
        seen.add(key)
        out.append(info)
    out.sort(key=lambda f: f.mtime)
    return out


def recycle_files(paths_and_sizes: list[tuple[str, int]], recycler=send_to_recycle_bin) -> RecycleReport:
    report = RecycleReport()
    for path, size in paths_and_sizes:
        if not os.path.isfile(path):
            report.failed.append((path, "no longer there"))
            continue
        _recycle(path, size, report, recycler)
    return report


def _recycle(path: str, size: int, report: RecycleReport, recycler) -> None:
    try:
        recycler(path)
    except OSError as exc:
        report.failed.append((path, str(exc)))
        return
    report.recycled.append(path)
    report.freed += size


def _matches(path: str, digest: str) -> bool:
    try:
        return os.path.isfile(path) and duplicates.file_hash(path) == digest
    except OSError:
        return False
