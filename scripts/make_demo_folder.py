"""Create a messy demo folder so the app can be tried without touching real files.

    python scripts/make_demo_folder.py [target]

Default target: %TEMP%\fileorganiser-demo
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time

CV = b"VICTOR STOKOE\nCurriculum Vitae\n" + b"experience " * 400
INVOICE = b"%PDF-1.4 invoice " + b"0" * 2000

FILES: list[tuple[str, bytes]] = [
    ("holiday-1.jpg", b"JPEGDATA" + os.urandom(4000)),
    ("holiday-2.jpg", b"JPEGDATA" + os.urandom(4000)),
    ("Screenshot 2026-03-11 141022.png", b"PNG" + os.urandom(1200)),
    ("Screenshot 2026-03-12 090533.png", b"PNG" + os.urandom(1200)),
    ("logo.svg", b"<svg/>"),
    ("gameplay.mp4", b"MP4" + os.urandom(20000)),
    ("lecture recording.mkv", b"MKV" + os.urandom(18000)),
    ("podcast ep12.mp3", b"ID3" + os.urandom(9000)),
    ("victor cv 1.pdf", CV),
    ("victor stokoe cv.pdf", CV),
    ("victor cv - Copy.pdf", CV),
    ("coursework essay.docx", b"draft one " * 300),
    ("coursework essay (1).docx", b"draft two, rather longer " * 320),
    ("invoice-8821.pdf", INVOICE),
    ("invoice-8821 (1).pdf", INVOICE),
    ("budget 2026.xlsx", b"XLSX" + os.urandom(3000)),
    ("reading list.txt", b"books"),
    ("donut.blend", b"BLENDER" + os.urandom(15000)),
    ("donut.blend1", b"BLENDER" + os.urandom(15000)),
    ("character rig.blend", b"BLENDER" + os.urandom(21000)),
    ("poster draft.psd", b"8BPS" + os.urandom(12000)),
    ("thumbnail.psd", b"8BPS" + os.urandom(11000)),
    ("beat idea.flp", b"FLhd" + os.urandom(5000)),
    ("edit v2.kdenlive", b"<mlt/>"),
    ("benchy.stl", b"solid benchy" + os.urandom(7000)),
    ("bracket.gcode", b"G28" + os.urandom(2500)),
    ("setup.exe", b"MZ" + os.urandom(30000)),
    ("drivers.msi", b"MSI" + os.urandom(16000)),
    ("archive.zip", b"PK\x03\x04" + os.urandom(9000)),
    ("ubuntu.iso", b"ISO" + os.urandom(40000)),
    ("scraper.py", b"import requests\n"),
    ("data.json", b'{"a": 1}'),
    ("index.html", b"<!doctype html>"),
    ("Inter.ttf", b"\x00\x01\x00\x00ttf"),
    ("linux-mint.torrent", b"d8:announce"),
    ("mystery-file.qzx", b"???"),
    ("README", b"no extension here"),
    ("big-download.iso.crdownload", b"half a file"),
    ("Thumbs.db", b"thumbs"),
]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        tempfile.gettempdir(), "fileorganiser-demo"
    )
    os.makedirs(target, exist_ok=True)
    random.seed(7)
    for name, content in FILES:
        path = os.path.join(target, name)
        with open(path, "wb") as handle:
            handle.write(content)
        # Spread files over the last year or so, as a real Downloads would be.
        # (The app leaves just-modified files alone, so fresh ones would hide.)
        when = time.time() - random.uniform(1, 400) * 86400
        os.utime(path, (when, when))
    print("Demo folder ready:", target)
    print(len(FILES), "files written.")


if __name__ == "__main__":
    main()
