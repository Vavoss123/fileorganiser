# File Organiser

A small desktop app for Windows and Mac that tidies up a messy folder.
Downloads, usually.

Pictures go in `Pictures`, PDFs in `Documents`, `.blend` files in
`Apps/Blender`, and so on for about 20 kinds of file and 50 programs. It also
finds duplicate files and old installers you've forgotten about.

It shows you the plan before it moves anything, any run can be undone, and it
never deletes anything outright. The most it will do is send duplicates or old
installers to the Recycle Bin, and only when you press the button.

## Download

Get the latest version from the
[Releases page](https://github.com/Vavoss123/fileorganiser/releases/latest)
(look under **Assets**):

- `FileOrganiserSetup.exe` is the normal Windows installer. It installs for
  your account only, so it doesn't need admin rights.
- `FileOrganiser.exe` runs without installing, e.g. off a USB stick.
- `FileOrganiser-mac.dmg` is for Macs with Apple silicon (M1 or later). Open
  it and drag the app into Applications. Intel Macs can run it from source.

None of them are code-signed, so expect a warning the first time.

On Windows, SmartScreen says "Windows protected your PC". Click **More info**,
then **Run anyway**.

On a Mac, macOS says it can't check the app for malicious software. Press
**Done**, go to **System Settings > Privacy & Security**, scroll down and press
**Open Anyway**. You only have to do this once. The first time you bin
something, macOS also asks if the app can control Finder. Say OK, that's how
**Put Back** keeps working.

## Using it

1. Pick a folder (it starts on Downloads) and press **Scan folder**. Scanning
   doesn't change anything.
2. Look over the plan. **Files to move** lists every file and where it's going,
   and **Map** draws the same thing as an Obsidian-style graph. Untick anything
   you want left alone.
3. Press **Tidy**.

If you change your mind, **Undo a tidy…** puts any earlier run back. Files
you've moved or renamed since then are left where they are.

The scan also fills in a few other tabs:

- **Duplicates** groups files with identical contents, whatever they're
  called. One copy in each group is kept (the one without "copy" or "(1)" in
  its name, or the oldest) and the rest can go to the Recycle Bin in one go.
  Each file is checked again just before it's binned.
- **Similar names** shows things like `essay.docx`, `essay (1).docx` and
  `essay_final.docx` that aren't identical. It's only there so you can see
  them, the app won't touch them.
- **Old installers** lists `.exe`, `.msi` and similar files that haven't been
  modified for 30 days.

On the map you can scroll to zoom, drag to pan, and double-click a folder to
fold it up. **Before / after** animates every file flying to its new folder
(nothing moves on disk until you press Tidy). The gear button opens a side
panel with filters and display settings.

**More options** has the less common settings: how many levels of subfolders
to scan, year or month folders for photos and videos, sending pictures, videos,
music and documents to your Windows libraries instead of folders inside the
scanned one, moving files you haven't touched for 3, 6 or 12 months into an
`Archive` folder, and tidying automatically when you sign in. Hover over any
of them for an explanation.

**Custom rules…** lets you add your own rules, and they win over the built-in
ones. You can go by words in the name (`invoice, receipt` to
`Documents/Receipts` catches `Invoice 2026-03.pdf` but not `reinvoiced.pdf`,
and `*` works as a wildcard) or by file type (`.pdf` to `Documents/Receipts`).
There are a few ready-made ones to start from.

**◐ Theme** switches between light and dark and lets you pick an accent colour.

Shortcuts: Ctrl+O picks a folder, F5 scans, Esc stops a scan, Ctrl+Enter tidies
and Ctrl+Z undoes. On a Mac it's ⌘ instead of Ctrl.

### Trying it out

If you'd rather not point it at your real files first:

```
python scripts\make_demo_folder.py
```

That makes about 40 messy files in `%TEMP%\fileorganiser-demo` (duplicates, a
few versions of the same essay, a half-finished download, some old installers).
Scan that folder instead.

## Where files go

| Folder | Examples |
| --- | --- |
| `Pictures` | jpg, png, gif, webp, heic (screenshots get their own subfolder) |
| `Videos` | mp4, mkv, mov, avi, webm |
| `Audio` | mp3, flac, wav, m4a, ogg |
| `Documents` | pdf, docx, txt, md, plus subfolders for spreadsheets, slides and ebooks |
| `Archives` | zip, rar, 7z, tar, gz |
| `Installers` | exe, msi, msix, appx |
| `Disk Images` | iso, img, vhd, dmg |
| `Code` | py, js, cs, json, html, ipynb |
| `3D` | stl, obj, fbx, gcode, 3mf |
| `Apps/<program>` | `.psd` to Photoshop, `.flp` to FL Studio, `.unitypackage` to Unity, and about 50 more |
| `Other` | anything it doesn't recognise (you can turn this off) |

There are a few more (fonts, torrents, shortcuts, raw photos). The full list is
in [`organiser/rules.py`](organiser/rules.py).

It leaves unfinished downloads (`.crdownload`, `.part` and so on), system files
like `desktop.ini` and Office lock files, and hidden folders alone. It also
skips anything changed in the last 2 minutes, because some browsers write
straight to the final filename while the download is still going.

If a file with the same name is already at the destination, the new one is
renamed to `name (2).ext`. Nothing gets overwritten.

## Tidying automatically

Under More options, **When I sign in** can be set to:

- **Tidy once**, which runs one tidy in the background each time you sign in,
  with no window.
- **Keep tidying from the tray**, which leaves an icon by the clock and files
  new downloads every minute once they've sat unchanged for 2 minutes. Right-click
  it to pause, tidy now or quit. Windows only.

Automatic runs use your saved options and custom rules, only ever move files
(they never bin anything), and show up under Undo like any other run. They log
to `%LOCALAPPDATA%\FileOrganiser\auto.log`. It's an ordinary startup entry, so
you can also switch it off from Task Manager.

## Updates

When there's a new release an **Update to …** button appears at the top of the
window. **Update now** downloads it, checks it against the SHA-256 checksum
GitHub publishes, installs it and restarts. Your settings and undo history
stay put. If it can't update itself (say you're running from source) it opens
the download page instead.

Checking is one request to GitHub's releases page when the app opens, and
nothing about you or your files is sent. You can turn it off under More
options.

## Settings

Settings and undo history are kept in `%LOCALAPPDATA%\FileOrganiser\`, or
`~/Library/Application Support/FileOrganiser` on a Mac. Undo records older
than six months are cleared out automatically.

A few settings aren't in the app. You can edit them in `settings.json` while
the app is closed:

| Setting | Default | |
| --- | --- | --- |
| `settle_seconds` | `120` | Files changed more recently than this are left alone. |
| `installer_age_days` | `30` | How old an installer has to be to count as old. |
| `journal_days` | `180` | How long undo records are kept. `0` keeps them forever. |
| `welcomed` | `false` | Set back to `false` to see the welcome screen again. |

## Command line

```
FileOrganiser.exe            open the window
FileOrganiser.exe --auto     tidy once with saved settings and exit
FileOrganiser.exe --tray     start the tray icon
```

From source it's `python app.py` with the same flags (`run.bat` opens the
window without a console).

The engine in `organiser/` doesn't depend on the window, so you can use it from
Python too:

```python
from organiser import apply, plan, rules, scan

result = scan.scan(r"C:\Users\Victor\Downloads",
                   ignore_folders=set(rules.known_destinations()))
proposal = plan.build_plan(result, settle_seconds=120)
for move in proposal.moves:
    print(move.info.name, "->", move.bucket)
# apply.apply_moves(proposal.moves)   # actually move the files
```

## Building

You need Python 3.10 or newer with tkinter (the python.org installer includes
it). For the tray icon, `pip install pystray pillow`. Without them the tray
option is just hidden. For the Windows installer you also need
[Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`).

On Windows, run `build.bat`. It installs PyInstaller and friends if they're
missing and builds `dist\FileOrganiser.exe`, plus `dist\FileOrganiserSetup.exe`
if Inno Setup is there. Close the app first or Windows won't let it replace the
old exe.

On a Mac, run `sh build_mac.sh` to get `dist/File Organiser.app` and
`dist/FileOrganiser-mac.dmg`.

### Releasing

GitHub Actions ([`release.yml`](.github/workflows/release.yml)) builds and
smoke-tests the Windows and Mac versions on every push, but only publishes a
release for a version tag. To release 1.4:

1. Set `__version__ = "1.4"` in [`organiser/__init__.py`](organiser/__init__.py).
   The app compares this against the latest release to decide whether to
   offer an update.
2. Add a `## v1.4` section to the top of [`CHANGELOG.md`](CHANGELOG.md). That
   becomes the release notes (`python scripts/release_notes.py v1.4` shows a
   preview). Commit both.
3. Tag it and push:

   ```
   git tag v1.4
   git push origin master v1.4
   ```

If the tests fail or the tag doesn't match `__version__`, nothing gets
published.

## Tests

```
python -m unittest discover -s tests -v
```

They work in temporary folders with a temporary settings folder, so your real
files and undo history aren't touched. One test briefly adds and removes a
Windows startup entry.

## Troubleshooting

**A file didn't move.** Open More options and check the Activity tab. Usually
it was changed in the last 2 minutes, is still downloading, is open in another
program, or is already in the right place.

**The tray icon isn't showing.** Windows likes to hide new tray icons. Click
the `^` next to the clock, or turn it on in Settings > Personalisation >
Taskbar > Other system tray icons.

**The build fails with "Access is denied".** The app (or its tray icon) is
still running. Quit it and build again.

## Uninstalling

If you used the installer, remove it from Settings > Apps > Installed apps.
That also removes the sign-in entry. If you used the standalone exe, set
**When I sign in** back to **Do nothing** and delete the exe.

Your settings and undo history stay in `%LOCALAPPDATA%\FileOrganiser\` in case
you come back. Delete that folder if you don't want them.
