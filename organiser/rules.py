"""Mapping from file extensions to the folder a file belongs in.

Two kinds of rule:

* ``TYPE_RULES`` - generic media/document buckets (Pictures, Videos, ...).
* ``APP_RULES``  - project files that only one application opens. These go
  under ``Apps/<Application>`` so a stray ``.blend`` lands next to its
  siblings instead of in a generic "3D" pile.

``APP_RULES`` wins when an extension appears in both.
"""

from __future__ import annotations

import os
import sys

TYPE_RULES: dict[str, str] = {}
APP_RULES: dict[str, str] = {}


def _add(table: dict[str, str], destination: str, extensions: str) -> None:
    for ext in extensions.split():
        table[ext.lower()] = destination


_add(TYPE_RULES, "Pictures", "jpg jpeg png gif bmp tiff tif webp heic heif ico avif jfif jpe")
_add(TYPE_RULES, "Pictures/Raw", "cr2 cr3 nef arw dng raf orf rw2 pef srw")
_add(TYPE_RULES, "Pictures/Vector", "svg")
_add(TYPE_RULES, "Pictures/Screenshots", "")  # populated by name heuristics
_add(TYPE_RULES, "Videos", "mp4 mkv avi mov wmv flv webm m4v mpg mpeg mpe 3gp ts m2ts vob ogv")
_add(TYPE_RULES, "Audio", "mp3 wav flac aac ogg oga m4a wma opus aiff aif mid midi amr")
_add(TYPE_RULES, "Documents", "pdf doc docx odt rtf txt md markdown tex pages xps djvu")
_add(TYPE_RULES, "Documents/Spreadsheets", "xls xlsx xlsm xlsb csv tsv ods numbers")
_add(TYPE_RULES, "Documents/Presentations", "ppt pptx pptm odp key")
_add(TYPE_RULES, "Documents/Ebooks", "epub mobi azw azw3 fb2 cbz cbr")
_add(TYPE_RULES, "Archives", "zip rar 7z tar gz tgz bz2 tbz2 xz zst lz4 cab arj lzh")
_add(TYPE_RULES, "Installers", "exe msi msix msixbundle appx appxbundle appinstaller msu "
                               "pkg mpkg")
_add(TYPE_RULES, "Disk Images", "iso img vhd vhdx dmg bin cue nrg")
if sys.platform == "darwin":
    # On a Mac, a .dmg is how most apps are downloaded: once installed, it's done.
    _add(TYPE_RULES, "Installers", "dmg")
_add(TYPE_RULES, "Code", "py js mjs cjs ts tsx jsx java kt c cc cpp cxx h hpp cs go rs rb php "
                         "swift lua pl r scala sh bash zsh ps1 psm1 sql vb asm")
_add(TYPE_RULES, "Code/Data", "json yaml yml toml ini cfg conf xml env proto graphql")
_add(TYPE_RULES, "Code/Web", "html htm css scss sass less vue svelte astro")
_add(TYPE_RULES, "Code/Notebooks", "ipynb rmd qmd")
_add(TYPE_RULES, "Fonts", "ttf otf woff woff2 eot fon pfb")
_add(TYPE_RULES, "Torrents", "torrent magnet")
_add(TYPE_RULES, "Shortcuts", "lnk url webloc desktop")
_add(TYPE_RULES, "3D/Models", "stl obj fbx dae 3ds gltf glb ply abc usd usdz usda usdc")
_add(TYPE_RULES, "3D/Printing", "gcode 3mf bgcode gx")

_add(APP_RULES, "Apps/Blender", "blend blend1 blend2 blend3 blend4")
_add(APP_RULES, "Apps/Photoshop", "psd psb")
_add(APP_RULES, "Apps/Illustrator", "ai eps")
_add(APP_RULES, "Apps/InDesign", "indd indt idml")
_add(APP_RULES, "Apps/After Effects", "aep aepx")
_add(APP_RULES, "Apps/Premiere Pro", "prproj prel")
_add(APP_RULES, "Apps/Lightroom", "lrcat lrtemplate xmp")
_add(APP_RULES, "Apps/GIMP", "xcf")
_add(APP_RULES, "Apps/Krita", "kra krz")
_add(APP_RULES, "Apps/Inkscape", "")  # Inkscape uses .svg; stays under Pictures/Vector
_add(APP_RULES, "Apps/Paint.NET", "pdn")
_add(APP_RULES, "Apps/Affinity", "afdesign afphoto afpub")
_add(APP_RULES, "Apps/Figma", "fig")
_add(APP_RULES, "Apps/Sketch", "sketch")
_add(APP_RULES, "Apps/Clip Studio", "clip lip")
_add(APP_RULES, "Apps/Substance", "sbs sbsar spp sbsprs")
_add(APP_RULES, "Apps/DaVinci Resolve", "drp drb")
_add(APP_RULES, "Apps/Kdenlive", "kdenlive")
_add(APP_RULES, "Apps/Vegas Pro", "veg vf")
_add(APP_RULES, "Apps/Audacity", "aup aup3")
_add(APP_RULES, "Apps/FL Studio", "flp")
_add(APP_RULES, "Apps/Ableton Live", "als alp")
_add(APP_RULES, "Apps/Reaper", "rpp")
_add(APP_RULES, "Apps/Logic Pro", "logicx")
_add(APP_RULES, "Apps/Unity", "unitypackage unity unitypackage3d prefab")
_add(APP_RULES, "Apps/Unreal Engine", "uasset umap upk uproject")
_add(APP_RULES, "Apps/Godot", "tscn tres godot")
_add(APP_RULES, "Apps/Maya", "ma mb")
_add(APP_RULES, "Apps/3ds Max", "max")
_add(APP_RULES, "Apps/Cinema 4D", "c4d")
_add(APP_RULES, "Apps/ZBrush", "ztl zpr zbp")
_add(APP_RULES, "Apps/SketchUp", "skp layout")
_add(APP_RULES, "Apps/Fusion 360", "f3d f3z")
_add(APP_RULES, "Apps/SolidWorks", "sldprt sldasm slddrw")
_add(APP_RULES, "Apps/AutoCAD", "dwg dxf dwt")
_add(APP_RULES, "Apps/FreeCAD", "fcstd fcstd1")
_add(APP_RULES, "Apps/KiCad", "kicad_pcb kicad_sch kicad_pro sch brd")
_add(APP_RULES, "Apps/Arduino", "ino")
_add(APP_RULES, "Apps/Minecraft", "mcworld mcpack mcaddon mcmeta")
_add(APP_RULES, "Apps/Android", "apk apks aab")
_add(APP_RULES, "Apps/VS Code", "vsix code-workspace")
_add(APP_RULES, "Apps/Obsidian", "obsidian")
_add(APP_RULES, "Apps/OBS", "obsscene")
_add(APP_RULES, "Apps/MATLAB", "mlx mat slx")
_add(APP_RULES, "Apps/Jupyter", "")
_add(APP_RULES, "Apps/Tableau", "twb twbx")
_add(APP_RULES, "Apps/Power BI", "pbix pbit")
_add(APP_RULES, "Apps/Visio", "vsd vsdx")
_add(APP_RULES, "Apps/OneNote", "one onepkg")
_add(APP_RULES, "Apps/Access", "accdb mdb")
_add(APP_RULES, "Apps/Project", "mpp")
_add(APP_RULES, "Apps/Virtual Machines", "ova ovf vmdk vbox vdi")

# Half-finished downloads and OS bookkeeping: leave strictly alone.
SKIP_EXTENSIONS = {
    "crdownload", "part", "partial", "download", "opdownload", "!ut", "aria2",
    "tmp", "temp", "swp", "lock", "filepart",
}
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "icon\r"}

FALLBACK = "Other"


def split_extension(filename: str) -> str:
    """Return the lowercase extension without the dot ("" if there is none)."""
    return os.path.splitext(filename)[1].lstrip(".").lower()


def is_screenshot(filename: str) -> bool:
    stem = os.path.splitext(filename)[0].lower()
    return stem.startswith(("screenshot", "screen shot", "screen_shot", "capture ", "snip"))


def should_skip(filename: str) -> bool:
    name = filename.lower()
    if name in SKIP_NAMES or name.startswith("~$"):
        return True
    return split_extension(filename) in SKIP_EXTENSIONS


def destination_for(filename: str, overrides: dict[str, str] | None = None) -> str:
    """Return the relative folder a file should live in, e.g. ``Apps/Blender``."""
    ext = split_extension(filename)
    if overrides and ext in overrides:
        return overrides[ext]
    if ext in APP_RULES and APP_RULES[ext]:
        return APP_RULES[ext]
    if ext in TYPE_RULES and TYPE_RULES[ext]:
        if TYPE_RULES[ext] == "Pictures" and is_screenshot(filename):
            return "Pictures/Screenshots"
        return TYPE_RULES[ext]
    return FALLBACK


def known_destinations(overrides: dict[str, str] | None = None) -> list[str]:
    """Every folder the rules can produce, for ignoring on a re-scan."""
    seen = {d for d in list(TYPE_RULES.values()) + list(APP_RULES.values()) if d}
    seen.update((overrides or {}).values())
    seen.add(FALLBACK)
    tops = {d.split("/")[0] for d in seen}
    return sorted(seen | tops)


_BAD_FOLDER_CHARS = set('<>:"|?*')


def clean_rule(extension: str, folder: str) -> tuple[str, str]:
    """Validate a user rule, returning ``("pdf", "Documents/Receipts")``.

    Raises ``ValueError`` with a message fit to show the user. Destinations
    must stay inside the scanned folder: no drive letters, no ``..``.
    """
    ext = extension.strip().lstrip(".").lower()
    if not ext or any(c in ext for c in " /\\.") or any(c in _BAD_FOLDER_CHARS for c in ext):
        raise ValueError("Type an extension such as pdf or .blend")
    parts = [part.strip() for part in folder.replace("\\", "/").split("/")]
    parts = [part for part in parts if part]
    if not parts:
        raise ValueError("Type a folder such as Documents/Receipts")
    for part in parts:
        if part in (".", "..") or any(c in _BAD_FOLDER_CHARS for c in part) or part.endswith("."):
            raise ValueError("'{}' can't be used in a folder name".format(part))
    return ext, "/".join(parts)
