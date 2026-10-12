"""Finding files that are the same, and files that look like versions of each other.

Two separate signals, deliberately kept apart:

* **Exact duplicates** - byte-identical content, proven by SHA-256. Safe to
  act on, and this is what catches ``victor cv 1.pdf`` vs
  ``victor stokoe cv.pdf``: the names differ, the bytes do not.
* **Possible versions** - names that normalise to the same thing but whose
  content differs. A hint for a human, never more than that.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .scan import FileInfo

CHUNK = 1 << 20
QUICK_BYTES = 1 << 16

#: Unambiguous "this is a copy" suffixes: " - Copy", " copy 2", " (1)", "_final", " v2".
_EXPLICIT_MARKERS = re.compile(
    r"(\s*[-_]?\s*copy(\s*\(?\d+\)?)?$)"
    r"|(\s*\(\d+\)$)"
    r"|(\s*[-_]?\s*(final|new|latest|updated|v\d+)$)",
    re.IGNORECASE,
)

#: A short trailing number, as in "victor cv 1" or "logo-2". Stripped at most
#: once, and only up to two digits, so a timestamped name such as
#: "Screenshot 2026-03-11 141022" is not eroded down to "screenshot".
_TRAILING_INDEX = re.compile(r"[\s_-]+\d{1,2}$")


def _hash(path: str, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    read = 0
    with open(path, "rb") as handle:
        while True:
            want = CHUNK if limit is None else min(CHUNK, limit - read)
            if want <= 0:
                break
            block = handle.read(want)
            if not block:
                break
            digest.update(block)
            read += len(block)
    return digest.hexdigest()


def content_hash(info: FileInfo) -> str:
    if info._sha256 is None:
        info._sha256 = _hash(info.path)
    return info._sha256


def normalised_stem(name: str) -> str:
    """Strip copy markers and punctuation so near-identical names collide."""
    stem = os.path.splitext(name)[0].lower()
    previous = None
    while stem != previous:
        previous = stem
        stem = _EXPLICIT_MARKERS.sub("", stem).strip()
    stripped = _TRAILING_INDEX.sub("", stem).strip()
    if stripped:
        stem = stripped
    stem = re.sub(r"[^a-z0-9]+", " ", stem).strip()
    return stem


def _copy_marker_penalty(name: str) -> int:
    return 0 if normalised_stem(name) == os.path.splitext(name)[0].lower().strip() else 1


@dataclass
class DuplicateGroup:
    digest: str
    files: list[FileInfo]
    keeper: FileInfo = field(init=False)

    def __post_init__(self) -> None:
        self.files = sorted(self.files, key=self._rank)
        self.keeper = self.files[0]

    @staticmethod
    def _rank(info: FileInfo) -> tuple:
        # Prefer a name with no "copy"/"(1)" marker, then the oldest file
        # (likeliest the original), then the shallower, shorter name.
        return (
            _copy_marker_penalty(info.name),
            info.mtime,
            info.depth,
            len(info.name),
            info.name.lower(),
        )

    @property
    def redundant(self) -> list[FileInfo]:
        return self.files[1:]

    @property
    def wasted(self) -> int:
        return self.files[0].size * len(self.redundant)


@dataclass
class VersionGroup:
    stem: str
    files: list[FileInfo]

    def __post_init__(self) -> None:
        self.files = sorted(self.files, key=lambda f: f.mtime, reverse=True)

    @property
    def newest(self) -> FileInfo:
        return self.files[0]


def find_duplicates(
    files: list[FileInfo],
    progress=None,
    unreadable: list[tuple[str, str]] | None = None,
) -> list[DuplicateGroup]:
    """Group byte-identical files, cheapest test first.

    Size, then a hash of the first 64 KiB, then the full hash - so most files
    are never read in full.
    """
    by_size: dict[int, list[FileInfo]] = defaultdict(list)
    for info in files:
        if info.size > 0:
            by_size[info.size].append(info)

    candidates = [group for group in by_size.values() if len(group) > 1]
    done = 0
    total = sum(len(group) for group in candidates)
    groups: list[DuplicateGroup] = []

    for same_size in candidates:
        by_quick: dict[str, list[FileInfo]] = defaultdict(list)
        for info in same_size:
            try:
                by_quick[_hash(info.path, QUICK_BYTES)].append(info)
            except OSError as exc:
                if unreadable is not None:
                    unreadable.append((info.path, str(exc)))
            done += 1
            if progress and done % 25 == 0:
                progress(done, total)

        for quick_group in by_quick.values():
            if len(quick_group) < 2:
                continue
            if quick_group[0].size <= QUICK_BYTES:
                # Already hashed in full by the quick pass.
                groups.append(DuplicateGroup(digest=content_hash(quick_group[0]), files=quick_group))
                continue
            by_full: dict[str, list[FileInfo]] = defaultdict(list)
            for info in quick_group:
                try:
                    by_full[content_hash(info)].append(info)
                except OSError as exc:
                    if unreadable is not None:
                        unreadable.append((info.path, str(exc)))
            for digest, full_group in by_full.items():
                if len(full_group) > 1:
                    groups.append(DuplicateGroup(digest=digest, files=full_group))

    if progress:
        progress(total, total)
    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups


def find_possible_versions(
    files: list[FileInfo],
    duplicate_groups: list[DuplicateGroup] | None = None,
    min_stem_length: int = 4,
) -> list[VersionGroup]:
    """Same-ish name, different content - probably successive versions."""
    already = set()
    for group in duplicate_groups or []:
        already.update(f.path for f in group.files)

    by_stem: dict[tuple[str, str], list[FileInfo]] = defaultdict(list)
    for info in files:
        if info.path in already:
            continue
        stem = normalised_stem(info.name)
        if len(stem) >= min_stem_length:
            by_stem[(stem, info.ext)].append(info)

    out = [
        VersionGroup(stem=stem, files=group)
        for (stem, _ext), group in by_stem.items()
        if len(group) > 1
    ]
    out.sort(key=lambda g: (-len(g.files), g.stem))
    return out
