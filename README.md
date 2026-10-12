# File Organiser

A small Windows desktop app that tidies a cluttered folder — Downloads, usually.
It sorts files into sensible folders (pictures with pictures, videos with
videos), gives application project files a home of their own (`Apps/Blender`,
`Apps/Photoshop`, …), and points out duplicates you could delete.

Nothing happens until you say so. A scan only reads; files move when you press
**Apply**, and that run can be undone. **The app never deletes anything** —
duplicates are reported for you to act on.

## Running it

Needs Python 3.10+ with tkinter, which the standard python.org installer
includes. No packages to install.

```
run.bat                 # double-click, or
python app.py           # same thing with a console attached
```

To build a standalone `dist\FileOrganiser.exe` (no Python needed to run it):

```
build.bat
```

To try it without touching your real files:

```
python scripts\make_demo_folder.py
```

That writes ~40 believably messy files (including two CVs with identical
content under different names) to `%TEMP%\fileorganiser-demo`. Point the app at
that folder and press **Scan**.

## How it works

**Scan** walks the folder, decides a destination for every file, and shows you
the plan grouped by destination. Untick anything you want left alone — ticking
a group heading toggles everything under it.

Three things are deliberately left out of the plan:

- half-finished downloads (`.crdownload`, `.part`, `.tmp`) and OS clutter
  (`Thumbs.db`, `~$draft.docx`),
- folders the organiser itself creates, so a second run on a tidy folder finds
  nothing to do,
- subfolders, unless you raise **Look into subfolders** above 0.

**Apply** moves the ticked files. If a file with that name is already at the
destination, the incoming one becomes `name (2).ext` — an existing file is
never overwritten. Every run writes a journal to
`%LOCALAPPDATA%\FileOrganiser\journal\`, and **Undo last run** replays it
backwards, removing any folders it created along the way.

### Where files go

| Bucket | Examples |
| --- | --- |
| `Pictures`, `Pictures/Raw`, `Pictures/Vector`, `Pictures/Screenshots` | jpg, png, heic · cr2, dng · svg · `Screenshot …` |
| `Videos`, `Audio` | mp4, mkv, mov · mp3, flac, wav |
| `Documents` + `/Spreadsheets`, `/Presentations`, `/Ebooks` | pdf, docx, txt · xlsx, csv · pptx · epub |
| `Apps/<Application>` | `.blend` → Blender, `.psd` → Photoshop, `.flp` → FL Studio, `.unitypackage` → Unity, ~50 more |
| `3D/Models`, `3D/Printing` | stl, obj, fbx · gcode, 3mf |
| `Archives`, `Installers`, `Disk Images`, `Fonts`, `Torrents` | zip, 7z · exe, msi · iso · ttf · torrent |
| `Code` + `/Data`, `/Web`, `/Notebooks` | py, cs, rs · json, yaml · html, css · ipynb |
| `Other` | anything unrecognised (switchable off) |

Tick **Send photos, videos and documents to my user libraries** to route media
and documents to `~\Pictures`, `~\Videos`, `~\Music` and `~\Documents` instead
of into subfolders of the scanned folder. Application files always stay next to
where they were found.

The full mapping lives in [`organiser/rules.py`](organiser/rules.py) — one
table per rule kind, easy to extend.

### Duplicates, and near-duplicates

Two separate signals, kept apart on purpose:

- **Duplicates** — byte-identical, proven with SHA-256. This is what catches
  `victor cv 1.pdf` and `victor stokoe cv.pdf`: the names differ, the bytes do
  not. The comparison is cheap first and thorough only where it has to be —
  group by size, then hash the first 64 KiB, then hash in full — so most files
  are never read end to end. The copy the app suggests keeping is the one whose
  name carries no `copy`/`(1)` marker, oldest first as a tie-break. **Copy
  suggested deletions** puts the rest on your clipboard.
- **Possible versions** — names that normalise to the same thing but hold
  different content, e.g. `essay.docx` and `essay (1).docx`. A hint for a human
  and nothing more. Timestamped names are left distinct, so two screenshots
  taken minutes apart are not mistaken for versions of each other.

## Layout

```
app.py                     tkinter window: plan, duplicates, versions, log
organiser/rules.py         extension → folder, and what to leave alone
organiser/scan.py          walking a folder, collecting sizes and times
organiser/plan.py          proposed moves, name-clash resolution
organiser/duplicates.py    hashing, grouping, name normalisation
organiser/apply.py         carrying out a plan, journalling, undo
organiser/config.py        settings and journal locations
scripts/make_demo_folder.py
tests/test_organiser.py    27 tests, engine only, no GUI needed
```

The engine knows nothing about tkinter, so it is usable from a script or a
scheduled task as well:

```python
from organiser import scan, plan, duplicates, apply, rules

result = scan.scan(r"C:\Users\Victor\Downloads",
                   ignore_folders=set(rules.known_destinations()))
proposal = plan.build_plan(result)
for move in proposal.moves:
    print(move.info.name, "->", move.bucket)
# apply.apply_moves(proposal.moves)   # only when you mean it
```

## Tests

```
python -m unittest discover -s tests -v
```

They run against temporary folders — no real file is touched.

## Ideas not built yet

- A right-click rule editor in the GUI (the `overrides` setting is already read
  from `settings.json`, extension → folder).
- Dated archive folders for the long tail, e.g. `Archives/2024`.
- Image-similarity duplicates (resized or re-encoded copies), which content
  hashing cannot see.
- Run on a schedule and notify, rather than organise silently.
