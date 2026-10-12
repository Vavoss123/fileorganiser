"""Where settings and undo journals live, and loading/saving settings."""

from __future__ import annotations

import json
import os

APP_NAME = "FileOrganiser"

DEFAULTS: dict = {
    "folder": "",
    "max_depth": 0,
    "route_to_libraries": False,
    "include_other": True,
    "find_duplicates": True,
    "overrides": {},          # extension -> destination folder
    "settle_seconds": 120,    # leave files this fresh alone
    "date_folders": "off",    # "off", "year" or "month" for photos and videos
    "installer_age_days": 30, # installers older than this are offered for the bin
}


def _base_dir() -> str:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, APP_NAME)


def config_path() -> str:
    return os.path.join(_base_dir(), "settings.json")


def journal_dir() -> str:
    return os.path.join(_base_dir(), "journal")


def default_folder() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.path.expanduser("~")


def load() -> dict:
    settings = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if not settings["folder"]:
        settings["folder"] = default_folder()
    return settings


def save(settings: dict) -> None:
    try:
        os.makedirs(_base_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as handle:
            json.dump({k: settings.get(k, v) for k, v in DEFAULTS.items()}, handle, indent=2)
    except OSError:
        pass
