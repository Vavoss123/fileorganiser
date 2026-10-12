"""Carrying out an approved plan, and reversing it.

Every applied run writes a journal file first, so a run can always be undone
even if the app is closed in between. Files are only ever *moved* - nothing in
this project deletes user data.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field

from .config import journal_dir
from .plan import Move


@dataclass
class ApplyReport:
    moved: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    journal_path: str | None = None

    @property
    def summary(self) -> str:
        parts = [f"{len(self.moved)} file(s) moved"]
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


def _folders_to_create(folder: str) -> list[str]:
    """Every ancestor of *folder* that does not exist yet, deepest first.

    ``os.makedirs`` creates parents silently; the journal has to know about
    them too, or an undo leaves behind empty shells like ``Apps``.
    """
    missing: list[str] = []
    current = os.path.abspath(folder)
    while current and not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return missing


def _free_destination(destination: str) -> str:
    if not os.path.exists(destination):
        return destination
    folder, name = os.path.split(destination)
    stem, ext = os.path.splitext(name)
    counter = 2
    while True:
        candidate = os.path.join(folder, f"{stem} ({counter}){ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def apply_moves(moves: list[Move], progress=None) -> ApplyReport:
    report = ApplyReport()
    entries: list[dict[str, str]] = []
    created_folders: list[str] = []

    for index, move in enumerate(moves, start=1):
        source = move.source
        try:
            if not os.path.isfile(source):
                report.failed.append((source, "file is no longer there"))
                continue
            if not os.path.isdir(move.destination_folder):
                created_folders.extend(_folders_to_create(move.destination_folder))
                os.makedirs(move.destination_folder, exist_ok=True)
            destination = _free_destination(move.destination)
            shutil.move(source, destination)
            report.moved.append((source, destination))
            entries.append({"from": source, "to": destination})
        except (OSError, shutil.Error) as exc:
            report.failed.append((source, str(exc)))
        if progress:
            progress(index, len(moves))

    if entries:
        report.journal_path = _write_journal(entries, created_folders)
    return report


def _write_journal(entries: list[dict[str, str]], created_folders: list[str]) -> str:
    folder = journal_dir()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("%Y%m%d-%H%M%S") + ".json")
    payload = {
        "created": time.time(),
        "created_folders": created_folders,
        "moves": entries,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def list_journals() -> list[str]:
    folder = journal_dir()
    if not os.path.isdir(folder):
        return []
    return sorted(
        (os.path.join(folder, name) for name in os.listdir(folder) if name.endswith(".json")),
        reverse=True,
    )


def undo(journal_path: str) -> ApplyReport:
    """Move everything in a journal back where it came from."""
    report = ApplyReport(journal_path=journal_path)
    with open(journal_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    for entry in reversed(payload.get("moves", [])):
        source, destination = entry["to"], entry["from"]
        try:
            if not os.path.isfile(source):
                report.failed.append((source, "moved or renamed since; left alone"))
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.move(source, _free_destination(destination))
            report.moved.append((source, destination))
        except (OSError, shutil.Error) as exc:
            report.failed.append((source, str(exc)))

    for folder in sorted(set(payload.get("created_folders", [])), key=len, reverse=True):
        try:
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass

    if not report.failed:
        try:
            os.replace(journal_path, journal_path + ".undone")
        except OSError:
            pass
    return report
