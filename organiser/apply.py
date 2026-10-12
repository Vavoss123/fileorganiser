"""Carrying out an approved plan, and reversing it.

Every applied run keeps a journal, written line by line as files move, so a
run can be undone even if the app is closed, or crashes, in between. Files are only ever *moved*, nothing in
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


class _Journal:
    """An append-only record of one run, flushed to disk after every line.

    One JSON object per line: a header, then ``{"folder": ...}`` before the
    first move that needed it and ``{"from": ..., "to": ...}`` after each move.
    Writing as we go means a run cut short by a crash or power cut can still
    be undone up to the last file that actually moved.
    """

    def __init__(self) -> None:
        self.path: str | None = None
        self._handle = None

    def write(self, record: dict) -> None:
        if self._handle is None:
            folder = journal_dir()
            os.makedirs(folder, exist_ok=True)
            self.path = _fresh_journal_path(folder)
            self._handle = open(self.path, "w", encoding="utf-8")
            self._write({"created": time.time(), "version": 2})
        self._write(record)

    def _write(self, record: dict) -> None:
        self._handle.write(json.dumps(record) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()


def _fresh_journal_path(folder: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, stamp + ".jsonl")
    counter = 2
    while os.path.exists(path):
        path = os.path.join(folder, "{}-{}.jsonl".format(stamp, counter))
        counter += 1
    return path


def apply_moves(moves: list[Move], progress=None) -> ApplyReport:
    report = ApplyReport()
    journal = _Journal()
    try:
        for index, move in enumerate(moves, start=1):
            source = move.source
            try:
                if not os.path.isfile(source):
                    report.failed.append((source, "file is no longer there"))
                    continue
                if not os.path.isdir(move.destination_folder):
                    # Recorded before creating, so an interrupted run still
                    # knows which (possibly empty) folders are ours to remove.
                    for folder in _folders_to_create(move.destination_folder):
                        journal.write({"folder": folder})
                    os.makedirs(move.destination_folder, exist_ok=True)
                destination = _free_destination(move.destination)
                shutil.move(source, destination)
                report.moved.append((source, destination))
                journal.write({"from": source, "to": destination})
            except (OSError, shutil.Error) as exc:
                report.failed.append((source, str(exc)))
            if progress:
                progress(index, len(moves))
    finally:
        journal.close()

    report.journal_path = journal.path
    return report


def read_journal(journal_path: str) -> dict:
    """Load a journal in either format into ``{created, created_folders, moves}``."""
    with open(journal_path, encoding="utf-8") as handle:
        if not journal_path.endswith(".jsonl"):
            return json.load(handle)
        payload: dict = {"created": None, "created_folders": [], "moves": []}
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                break  # a line torn by a crash; everything before it is good
            if "created" in record:
                payload["created"] = record["created"]
            elif "folder" in record:
                payload["created_folders"].append(record["folder"])
            elif "from" in record and "to" in record:
                payload["moves"].append(record)
        return payload


def list_journals() -> list[str]:
    folder = journal_dir()
    if not os.path.isdir(folder):
        return []
    paths = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith((".json", ".jsonl"))
    ]
    # Newest first. By modification time, because "…-2.jsonl" (a second run
    # in the same second) would sort before its sibling by name.
    return sorted(paths, key=lambda p: (os.path.getmtime(p), p), reverse=True)


@dataclass
class RunSummary:
    path: str
    created: float
    moves: int
    source_folder: str  # where the files came from, e.g. the Downloads folder


def summarise(journal_path: str) -> RunSummary:
    payload = read_journal(journal_path)
    moves = payload.get("moves", [])
    folders = [os.path.dirname(entry["from"]) for entry in moves]
    try:
        source = os.path.commonpath(folders) if folders else ""
    except ValueError:  # different drives
        source = folders[0]
    created = payload.get("created") or os.path.getmtime(journal_path)
    return RunSummary(journal_path, created, len(moves), source)


def run_history() -> list[RunSummary]:
    """Every run that can still be undone, newest first."""
    out = []
    for path in list_journals():
        try:
            out.append(summarise(path))
        except (OSError, ValueError, KeyError):
            continue
    return out


def undo(journal_path: str) -> ApplyReport:
    """Move everything in a journal back where it came from."""
    report = ApplyReport(journal_path=journal_path)
    payload = read_journal(journal_path)

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
