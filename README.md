# File Organiser

A desktop app for Windows and Mac that tidies a cluttered folder, usually
Downloads.

It sorts files into folders by type (pictures, videos, documents and so on),
gives project files from specific programs their own folder (`Apps/Blender`,
`Apps/Photoshop` and about 50 more), finds duplicate files, and flags old
installers you probably no longer need.

You always see a plan before anything happens, every run can be undone, and
nothing is ever permanently deleted.

## Contents

- [Features](#features)
- [Installing](#installing)
- [Quick start](#quick-start)
- [Using the app](#using-the-app)
- [Where files go](#where-files-go)
- [Automatic tidying](#automatic-tidying)
- [Safety](#safety)
- [Settings and data](#settings-and-data)
- [Command line](#command-line)
- [Building from source](#building-from-source)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)

## Features

- Sorts files into about 20 type folders and 50 application folders.
- Shows the full plan first. Untick anything you want left where it is.
- Undo any past run, even one that was interrupted by a crash.
- Finds exact duplicates (same content, any name) and sends the extra copies
  to the Recycle Bin.
- Points out files that look like different versions of the same thing, such
  as `essay.docx` and `essay (1).docx`.
- Flags installers that haven't been touched for 30 days.
- Your own rules, by file type (`.pdf` to `Documents/Receipts`) or by words in
  the name (anything with "invoice" in it to `Documents/Receipts`).
- Can move files you haven't touched for months into an Archive folder.
- Updates itself in one click when a new version is out.
- Optional year or month folders for photos and videos.
- Can tidy automatically when you sign in, or keep tidying from the system tray.
- A graph view of the plan, like Obsidian's, with a before/after animation.
- Light and dark themes.

## Installing

Download it from the
[Releases page](https://github.com/Vavoss123/fileorganiser/releases/latest),
under **Assets**. Everything there is built automatically from this repository
by GitHub Actions.

| Download | For | Notes |
| --- | --- | --- |
| `FileOrganiserSetup.exe` | Windows | Normal use. Adds a Start Menu shortcut and an uninstall entry. |
| `FileOrganiser.exe` | Windows | Runs without installing, e.g. from a USB stick. |
| `FileOrganiser-mac.dmg` | Mac with Apple silicon (M1 or newer) | Open it and drag File Organiser into Applications. |
| `python app.py` | Either, with Python 3.10+ | Development. |

You can also build them yourself (see
[Building from source](#building-from-source)).

### On a Mac

The app isn't signed with an Apple developer certificate, so the first time
you open it macOS says it can't check it for malicious software. To open it
anyway:

1. Open File Organiser once and press **Done** on the warning.
2. Go to **System Settings → Privacy & Security**, scroll down, and press
   **Open Anyway** next to "File Organiser was blocked".
3. Confirm with your password. From then on it opens normally.

The first time you send duplicates or old installers to the Trash, macOS asks
whether File Organiser may control Finder; say **OK**. The app asks Finder to
do it so that **Put Back** works as usual.

Macs with an Intel processor (from before late 2020) aren't supported by the
download; run it from source instead.

What differs on a Mac: "When I sign in" offers **Tidy once** only (no tray
watcher), **Use my Mac folders** sends videos to `Movies`, `.dmg` and `.pkg`
files count as old installers, shortcuts use ⌘ instead of Ctrl, and settings
live in `~/Library/Application Support/FileOrganiser`.

### On Windows

The installer installs for your user account only, so it doesn't ask for
administrator rights. It goes to `%LOCALAPPDATA%\Programs\File Organiser`.

**Windows SmartScreen:** the files aren't code-signed, so the first time you
run one Windows may show "Windows protected your PC". Click **More info**, then
**Run anyway**.

## Quick start

1. Open File Organiser. It starts with your Downloads folder selected. The
   first time, a short welcome explains the three steps; **? How it works**
   shows it again.
2. Press **Scan folder**. Nothing is changed yet. On a big folder you can
   press **Stop scan** (or Esc) at any time.
3. Look at the map, or the **Files to move** list. Untick anything you want to
   leave alone.
4. Press **Tidy**. The files are moved.
5. Changed your mind? Press **Undo a tidy…** and pick the run.

To try it without touching your own files, create a demo folder:

```
python scripts\make_demo_folder.py
```

This creates about 40 messy files in `%TEMP%\fileorganiser-demo`, including
duplicates, versions of the same essay, an unfinished download and old
installers. Point the app at that folder and press **Scan folder**.

## Using the app

### Choosing a folder

Type a path, press **Browse…**, or click one of the quick picks (Downloads,
Desktop, Documents, Pictures). Then press **Scan folder** (or Enter). The app
remembers the folder and all options for next time.

After a scan, four cards sum up what it found: files to sort, files already in
place, duplicate copies and old installers. Click a card to see the details.

**◐ Theme** in the top corner switches between light, dark, and the same as
Windows.

### More options

Most people never need these, so they stay hidden until you click **More
options**. Rest the mouse on any of them for an explanation. Opening them also
shows the **Activity** tab. The app remembers whether they're open.

| Option | What it does |
| --- | --- |
| Include subfolders | How many levels of subfolders to include. 0 means only the files directly in the folder. Folders the app created itself are always skipped. |
| Photos and videos | Off, by year (`Pictures/2026`) or by year and month (`Pictures/2026/10`). Uses the date each file was last modified. |
| When I sign in | Do nothing, tidy once, or keep tidying from the tray. See [Automatic tidying](#automatic-tidying). |
| Look for duplicate files | Compares file contents. Turn off to make scans of huge folders faster. |
| Sort unknown types into 'Other' | Off leaves files with unknown extensions where they are. |
| Use my Windows libraries | Moves pictures to `~\Pictures`, videos to `~\Videos`, audio to `~\Music` and documents to `~\Documents` instead of subfolders of the scanned folder. Everything else stays in the scanned folder. |
| Archive old files | Off, or files not changed for 3 months, 6 months or a year go to `Archive/<their usual folder>` inside the folder being tidied. Installers are left out, since they're offered for the bin instead. |
| Tell me when there's a new version | See [Updates](#updates). **Check now** looks straight away. |
| Custom rules… | Choose your own folder by words in the name or by file type. See below. |

### Files to move tab

Lists every file that will move, grouped by destination folder. Click the tick
in the **Move** column (or press Space) to include or exclude a file. Unticking
a group heading unticks everything in it.

In this tab and the Duplicates, Similar names and Old installers tabs,
double-click a file (or press Enter) to open it in its usual program.
Right-click a file for **Open**, **Show in Explorer** and **Open containing
folder**.

If a file with the same name already exists at the destination, the incoming
file is renamed to `name (2).ext`. The new name is shown in the plan. Existing
files are never overwritten.

### Map tab

The same plan drawn as a map, in the style of Obsidian's graph view. The
folder being tidied sits in the middle, each destination folder branches off
it, and every file is a dot with an arrow to the folder it will move into.
Colours follow the top-level folder (Pictures, Documents and so on). Copies of
the same file are joined by a dashed red line. The app opens this tab when a
scan finds something to move.

- Press **Before / after** to watch the plan happen: every file starts loose
  in the folder being tidied, then flies to the folder it is going to.
  Nothing moves on disk.
- Scroll to zoom, drag the background to pan, and drag a dot to pull it about.
- Hover a dot to light up what it is linked to. Click it to see its details.
- Double-click a file to open it in its usual program.
- Right-click a file for **Open**, **Show in Explorer**, and **Skip** or
  **Include**. Skipping also unticks it in the Files to move tab, and skipped files are
  drawn hollow. Right-click a folder to open it in Explorer (once it exists)
  or to fold it.
- Double-click a folder to fold its files away into it, and again to unfold
  it. Folded folders wear a ring and show how many files they hold. Scans
  with more than 1,000 files start with their biggest folders folded.

The panel on the right (hide it with the gear button) has:

- **Filters**: a search box, and switches for files, files already in place
  and duplicate links.
- **Groups**: the colour of each top-level folder, with its file count or size.
- **Display**: whether dot size shows the number of files or the disk space
  they take up, arrows, label fading, dot size and line thickness.
  **Animate** shakes the graph up and lets it settle again, **Fit** brings
  everything into view, and **Fold all** / **Unfold all** do what they say.
- **Forces**: how strongly things pull together or push apart.

The panel settings are remembered between runs.

### Duplicates tab

Groups of files with exactly the same content, whatever their names. For
example, `victor cv 1.pdf` and `victor stokoe cv.pdf` are found as long as the
bytes match.

In each group one file is marked **keep this one**. It's the copy without a
`copy` or `(1)` marker in its name, and if there's a tie, the oldest. The others
are marked **safe to delete**.

- **Send duplicates to Recycle Bin** moves all the "safe to delete" copies to
  the Recycle Bin. Each file is checked again first. If the file being kept,
  or the copy, has changed since the scan, it's left alone.
- **Copy suggested deletions** copies their paths to the clipboard instead, if
  you'd rather deal with them yourself.

To keep scans fast, files are compared by size first, then by the first 64 KB,
and only read in full when those match.

### Similar names tab

Files whose names look like versions of the same thing but whose contents
differ, for example `essay.docx`, `essay (1).docx` and `essay_final.docx`. The
newest is listed first. This tab is only for information: the app doesn't act
on it. Names with dates or times in them (such as screenshots) aren't grouped
together.

### Old installers tab

Installers (`.exe`, `.msi`, `.msix` and similar) that haven't been modified for
30 days or more. It also looks inside the `Installers` folder from previous
runs. **Send all to Recycle Bin** clears them out.

### Activity tab

Shown when **More options** is open. Everything the app did in this session: every move, anything it skipped and
why, and anything it couldn't read.

### Keyboard shortcuts

| Keys | Does |
| --- | --- |
| Ctrl+O | Choose a folder |
| F5 | Scan the folder |
| Esc | Stop a scan |
| Ctrl+Enter | Tidy the ticked files |
| Ctrl+Z | Undo a tidy |
| F1 | Show the welcome screen again |

### Updates

When a newer version is published on GitHub, an **Update to …** button appears
at the top of the window. It shows what's new and offers:

- **Update now** downloads the new version, checks it against the SHA-256
  checksum GitHub publishes for it, installs it and restarts the app. Your
  settings and undo history are kept. The installed Windows app runs the new
  installer quietly; the stand-alone `FileOrganiser.exe` swaps itself for the
  new one; the Mac app copies the new one over itself from the disk image.
- **Later** asks again next time.
- **Skip this version** stays quiet until the one after.

A download that doesn't match its checksum, or doesn't come from this
project's releases, is never installed. If the app can't update itself (run
from source, or from a folder it can't write to), the download page opens
instead.

The check is one request to GitHub's public releases page each time the app
opens. Nothing about you or your files is sent. Turn it off with **Tell me
when there's a new version** under **More options**, or look yourself with
**Check now**.

### Undo

**Undo a tidy…** lists every run that can still be undone, newest first. Pick one
and the files go back where they came from. Any folders the run created are
removed if they're now empty. Files you've moved or renamed since then are
left where they are, and the log says so.

### Custom rules

**Custom rules…** has two tabs. Your rules take priority over the built-in
ones, and folders are always inside the folder being tidied (drive letters and
`..` aren't allowed). Press **Save** when you're done.

**By name** sends files whose names contain certain words to a folder,
whatever kind of file they are. Type the words, separated by commas (any one
is enough), and a folder, then press **Add / update**. `invoice, receipt` to
`Documents/Receipts` catches `Invoice 2026-03.pdf` and `amazon_receipts.png`,
but not `reinvoiced.pdf`. Several words in a row (`boarding pass`) must appear
together. Use `*` for anything, as in `IMG_*.jpg`. The **Ideas** buttons add
ready-made rules for receipts, statements, travel, CVs, contracts and
wallpapers. Name rules are checked first, top to bottom; **Move up** and
**Move down** change the order.

**By file type** sends an extension (`pdf` or `.pdf`) to a folder of your
choice (`Documents/Receipts`).

## Where files go

| Folder | Examples |
| --- | --- |
| `Pictures` | jpg, png, gif, webp, heic |
| `Pictures/Screenshots` | images whose names start with `Screenshot`, `Capture` or `Snip` |
| `Pictures/Raw`, `Pictures/Vector` | cr2, nef, dng · svg |
| `Videos` | mp4, mkv, mov, avi, webm |
| `Audio` | mp3, flac, wav, m4a, ogg |
| `Documents` | pdf, docx, txt, md, rtf |
| `Documents/Spreadsheets`, `/Presentations`, `/Ebooks` | xlsx, csv · pptx · epub, mobi |
| `Archives` | zip, rar, 7z, tar, gz |
| `Installers` | exe, msi, msix, appx |
| `Disk Images` | iso, img, vhd, dmg |
| `Code`, `Code/Data`, `Code/Web`, `Code/Notebooks` | py, js, cs · json, yaml · html, css · ipynb |
| `Fonts`, `Torrents`, `Shortcuts` | ttf, otf · torrent · lnk, url |
| `3D/Models`, `3D/Printing` | stl, obj, fbx · gcode, 3mf |
| `Apps/<program>` | `.blend` to Blender, `.psd` to Photoshop, `.flp` to FL Studio, `.unitypackage` to Unity, `.kdenlive` to Kdenlive, and about 50 more |
| `Other` | anything not recognised (can be turned off) |

The app always leaves these alone:

- Unfinished downloads: `.crdownload`, `.part`, `.partial`, `.tmp` and similar.
- System files: `desktop.ini`, `Thumbs.db`, and Office lock files like `~$report.docx`.
- Any file changed in the last 2 minutes, because some browsers save straight
  to the final name while still downloading.
- Hidden folders (names starting with `.`).

The complete list of rules is in [`organiser/rules.py`](organiser/rules.py).

## Automatic tidying

The **When I sign in** option has three settings.

| Setting | What happens |
| --- | --- |
| Do nothing | The default. The app only runs when you open it. |
| Tidy once | Each time you sign in to Windows, one tidy runs in the background using your saved options. No window opens. |
| Keep tidying from the tray | An icon sits in the notification area and tidies every minute. New downloads are filed once they've been unchanged for 2 minutes. A notification tells you when files were moved. |

The tray icon's right-click menu has **Open File Organiser**, **Tidy now**,
**Keep tidying** (untick to pause) and **Quit**. Only one tray icon can run at
a time.

Things to know:

- Automatic runs use the options you last saved in the app, including custom
  rules and date folders.
- They only move files. They never send anything to the Recycle Bin.
- Each automatic run appears under **Undo a tidy…** like any other.
- What they did is written to `%LOCALAPPDATA%\FileOrganiser\auto.log`.
- The setting is a normal Windows startup entry, so you can also turn it off in
  Task Manager under **Startup apps**.
- The tray option only appears if the app was built with tray support (the
  `.exe` files always are).

## Safety

- **Nothing happens without a plan.** Scanning only reads files.
- **Nothing is overwritten.** Name clashes get a `(2)`, `(3)` suffix.
- **Nothing is permanently deleted.** The only removal is to the Recycle Bin,
  and only when you press one of the Recycle Bin buttons. If a file is too big
  for the Recycle Bin, Windows asks you before deleting it.
- **Every run can be undone.** The undo record is saved after every single
  file moves, so even a run cut short by a crash or power cut can be undone up
  to the last file that moved.
- **Files are re-checked before recycling.** A duplicate is only removed if it
  still matches the copy being kept.

## Settings and data

Everything is stored in `%LOCALAPPDATA%\FileOrganiser\`:

| Path | Contents |
| --- | --- |
| `settings.json` | Your folder, options, theme and map settings. |
| `journal\*.jsonl` | One undo record per run. Undone runs are renamed to `.undone`. Older versions used `.json`; these can still be undone. |
| `auto.log` | Log of automatic and tray runs. Starts afresh after 1 MB, keeping one `auto.log.old`. |
| `runtime\_MEI…` | Windows only: the single-file app unpacks itself here while it runs (about 60 MB) and removes it when it closes. |

The app tidies up after itself each time it starts. It removes undo records
older than six months, copies in `runtime` left by a crash or a forced close,
and update downloads in your temp folder. It only touches its own files, and
never anything in use. While it runs it uses around 50 MB of memory, which
doesn't grow over time.

A few settings have no control in the app. You can change them in
`settings.json` while the app is closed:

| Setting | Default | Meaning |
| --- | --- | --- |
| `settle_seconds` | `120` | Files changed more recently than this are left alone. |
| `installer_age_days` | `30` | How old an installer must be to appear under Old installers. |
| `overrides` | `{}` | Your file type rules, e.g. `{"pdf": "Documents/Receipts"}`. Easier to edit with **Custom rules…**. |
| `name_rules` | `[]` | Your name rules, e.g. `[["invoice, receipt", "Documents/Receipts"]]`, checked in order. Easier to edit with **Custom rules…**. |
| `welcomed` | `false` | Set back to `false` to see the welcome screen at the next start. |
| `journal_days` | `180` | Undo records older than this many days are removed. `0` keeps them all. |

## Command line

```
FileOrganiser.exe            open the window
FileOrganiser.exe --auto     tidy once with saved settings, no window, then exit
FileOrganiser.exe --tray     start the tray icon
```

When running from source, use `python app.py` with the same flags.
`run.bat` opens the window without a console.

The engine doesn't depend on the window, so it can also be used from Python:

```python
from organiser import apply, plan, rules, scan

result = scan.scan(r"C:\Users\Victor\Downloads",
                   ignore_folders=set(rules.known_destinations()))
proposal = plan.build_plan(result, settle_seconds=120)
for move in proposal.moves:
    print(move.info.name, "->", move.bucket)
# apply.apply_moves(proposal.moves)   # actually move the files
```

## Building from source

Requirements:

- Python 3.10 or newer, with tkinter (included in the python.org installer).
- For the tray icon: `pip install pystray pillow`. Without them the app works
  but the tray option is hidden.
- For the installer: [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  (`winget install JRSoftware.InnoSetup`).

Then run:

```
build.bat
```

This installs PyInstaller, pystray and Pillow if needed, draws the icon,
builds `dist\FileOrganiser.exe`, and then, if Inno Setup is installed, builds
`dist\FileOrganiserSetup.exe` from [`installer.iss`](installer.iss).

Close the app before building, otherwise Windows won't let the old exe be
replaced. The installer version number is set at the top of `installer.iss`,
or by the `APP_VERSION` environment variable if it is set.

### Building the Mac app

On a Mac with Python 3.10 or newer (from python.org, so Tk is included):

```
sh build_mac.sh
```

This makes `dist/File Organiser.app` and `dist/FileOrganiser-mac.dmg`.

### Publishing a release

[`.github/workflows/release.yml`](.github/workflows/release.yml) builds the
Windows `.exe` files and the Mac `.dmg` on GitHub's machines, opens each built
app once to check it works (`--smoke-test`), and attaches them to a release.
Every push runs these builds and checks; only a version tag publishes. To
publish version 1.4:

1. Set `__version__ = "1.4"` in [`organiser/__init__.py`](organiser/__init__.py).
   The app compares this with the newest release to decide whether to show
   the update notice.
2. Add a `## v1.4` section at the top of [`CHANGELOG.md`](CHANGELOG.md),
   written for the people who use the app. It becomes the release notes
   (`python scripts/release_notes.py v1.4` shows how they will look). Commit
   both changes.
3. Tag and push:

   ```
   git tag v1.4
   git push origin master v1.4
   ```

The tests run first, and the tag must match `__version__`; if either check
fails, nothing is published. The version in the
tag is stamped on the installer. Running the workflow by hand from the
**Actions** tab builds the files without releasing them; they appear under
the run's **Artifacts**.

## Tests

```
python -m unittest discover -s tests -v
```

The tests use temporary folders and a temporary settings folder, so your real
files, settings and undo history are never touched. One test briefly adds and
removes a test entry in the Windows startup list.

## Project layout

```
app.py                       the window, and the --auto and --tray entry points
organiser/
  rules.py                   extension to folder rules, custom rule checks
  scan.py                    reading a folder: names, sizes, dates
  plan.py                    deciding where each file goes
  apply.py                   moving files, undo records, undo
  duplicates.py              finding duplicates and possible versions
  graph.py                   the plan as a graph, and its force layout
  graphview.py               the Map tab: drawing and interaction
  theme.py                   the light and dark looks, tick boxes included
  updates.py                 finding, checking and installing updates
  housekeeping.py            clearing old undo records and leftover files
  system.py                  the differences between Windows and macOS
  cleanup.py                 Recycle Bin clear-outs, old installers
  recycle.py                 the Recycle Bin (Windows) and Trash (Mac)
  auto.py                    scan and plan in one step, the --auto run
  startup.py                 the "When I sign in" startup entry or Login Item
  tray.py                    the tray icon
  icon.py                    draws the app icon
  config.py                  settings file and data folder
scripts/make_demo_folder.py  creates a messy folder to try the app on
scripts/release_notes.py     one version's notes from CHANGELOG.md, for GitHub
tests/test_organiser.py      tests
build.bat                    builds the Windows exe and installer
build_mac.sh                 builds the Mac app and disk image
installer.iss                Inno Setup installer script
.github/workflows/release.yml builds and publishes releases on GitHub
run.bat                      opens the app from source without a console
```

## Troubleshooting

**A file wasn't moved.** Check the Activity tab (under **More options**). Common reasons: it was changed in
the last 2 minutes, it's an unfinished download, it's open in another program,
or it's already in the right folder.

**Undo skipped some files.** Files that were moved, renamed or deleted after
the run are left alone so nothing gets overwritten. The Activity tab lists them.

**The tray icon doesn't appear.** Windows sometimes hides new tray icons. Click
the `^` arrow next to the clock, or turn the icon on in Settings >
Personalisation > Taskbar > Other system tray icons.

**Build fails with "Access is denied" on `FileOrganiser.exe`.** The app is still
running. Close it, and quit the tray icon if it's running, then build again.

**Windows warns before running the exe.** See the SmartScreen note under
[Installing](#installing).

## Uninstalling

If you used the installer, uninstall from **Settings > Apps > Installed apps**.
This also removes the sign-in entry and stops the tray icon if it's running.

Your settings and undo records in `%LOCALAPPDATA%\FileOrganiser\` are kept in
case you reinstall. Delete that folder to remove them too.

If you used the standalone exe, set **When I sign in** to **Do nothing**, then
delete the exe.
