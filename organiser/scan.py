"""Walking a folder and collecting the facts we need about each file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import rules


@dataclass
class FileInfo:
    path: str
    name: str
    size: int
    mtime: float
    ext: str
    depth: int = 0
    _sha256: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_entry(cls, entry: os.DirEntry, depth: int = 0) -> "FileInfo":
        stat = entry.stat()
        return cls(
            path=entry.path,
            name=entry.name,
            size=stat.st_size,
            mtime=stat.st_mtime,
            ext=rules.split_extension(entry.name),
            depth=depth,
        )


@dataclass
class ScanResult:
    root: str
    files: list[FileInfo]
    skipped: list[tuple[str, str]]  # (path, why)
    unreadable: list[tuple[str, str]]


def scan(
    root: str,
    max_depth: int = 0,
    ignore_folders: set[str] | None = None,
    progress=None,
) -> ScanResult:
    """Collect files under *root*.

    ``max_depth`` 0 means the folder itself only; 1 also looks one level down.
    Folders the organiser itself creates are skipped so a second run over an
    already-tidy Downloads finds nothing to do.
    """
    root = os.path.abspath(root)
    ignore = {name.lower() for name in (ignore_folders or set())}
    files: list[FileInfo] = []
    skipped: list[tuple[str, str]] = []
    unreadable: list[tuple[str, str]] = []

    def walk(folder: str, depth: int) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
        except OSError as exc:
            unreadable.append((folder, str(exc)))
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth >= max_depth:
                        continue
                    if entry.name.lower() in ignore or entry.name.startswith("."):
                        continue
                    walk(entry.path, depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    if rules.should_skip(entry.name):
                        skipped.append((entry.path, "in-progress or system file"))
                        continue
                    files.append(FileInfo.from_entry(entry, depth))
                    if progress and len(files) % 200 == 0:
                        progress(len(files))
            except OSError as exc:
                unreadable.append((entry.path, str(exc)))

    walk(root, 0)
    if progress:
        progress(len(files))
    return ScanResult(root=root, files=files, skipped=skipped, unreadable=unreadable)
