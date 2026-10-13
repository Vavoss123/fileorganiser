"""Print one version's notes from CHANGELOG.md, ready for a GitHub release.

    python scripts/release_notes.py v1.3

Takes the lines under "## v1.3" up to the next "## " heading, and joins the
lines of each paragraph or list item back together: GitHub shows every line
break in release notes, so text wrapped for the file would break mid-sentence.
Prints nothing if there is no such section.
"""

from __future__ import annotations

import os
import sys


def section(text: str, tag: str) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if line.strip() == "## " + tag:
            inside = True
        elif inside and line.startswith("## "):
            break
        elif inside:
            lines.append(line.rstrip())
    return lines


def unwrap(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        starts_new = not stripped or stripped.startswith(("- ", "* ", "#")) or not out \
            or not out[-1].strip()
        if starts_new:
            out.append(line)
        else:
            out[-1] = out[-1] + " " + stripped
    return "\n".join(out).strip() + "\n" if any(s.strip() for s in out) else ""


def main() -> None:
    tag = sys.argv[1]
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "CHANGELOG.md")
    with open(path, encoding="utf-8") as handle:
        notes = unwrap(section(handle.read(), tag))
    sys.stdout.buffer.write(notes.encode("utf-8"))  # UTF-8 everywhere, for the ⌘


if __name__ == "__main__":
    main()
