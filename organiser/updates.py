"""Finding, downloading and installing newer releases from GitHub.

Checking sends one ordinary web request for the public "latest release" page,
nothing about the user or their files. Any failure (offline, firewall, GitHub
down) just means no notice is shown.

Installing only ever uses a file from this repository's releases, and only
once its SHA-256 matches the checksum GitHub publishes for it. Then:

* the installed Windows app runs the new installer silently, which closes
  this copy and starts the new one;
* the stand-alone ``FileOrganiser.exe`` swaps itself for the new one;
* the Mac app hands over to a small script that waits for it to quit, copies
  the new app out of the disk image over the old one, and opens it.

Running from source, there is nothing to install: the download page opens.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from . import __version__

REPOSITORY = "Vavoss123/fileorganiser"
RELEASES_API = "https://api.github.com/repos/{}/releases/latest".format(REPOSITORY)
RELEASES_PAGE = "https://github.com/{}/releases/latest".format(REPOSITORY)
DOWNLOAD_PREFIX = "https://github.com/{}/releases/download/".format(REPOSITORY)

INSTALLER = "FileOrganiserSetup.exe"
PORTABLE = "FileOrganiser.exe"
MAC_IMAGE = "FileOrganiser-mac.dmg"
MAC_APP = "File Organiser.app"


@dataclass
class Asset:
    name: str
    url: str
    size: int
    sha256: str | None  # lower-case hex, or None if GitHub gave no checksum


@dataclass
class Release:
    tag: str
    page: str
    notes: str = ""
    assets: dict[str, Asset] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return self.tag.lstrip("v")


class UpdateError(Exception):
    """Something went wrong; the message is fit to show the user."""


# ------------------------------------------------------------------ versions

def parse_version(text: str) -> tuple[int, ...] | None:
    """(1, 2, 3) for "v1.2.3" or "1.2.3-beta"; None if there's no number."""
    match = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str = __version__) -> bool:
    new, old = parse_version(latest), parse_version(current)
    if new is None or old is None:
        return False
    width = max(len(new), len(old))  # so 1.3 and 1.3.0 compare equal
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


# ------------------------------------------------------------------- finding

def _tls() -> ssl.SSLContext:
    """Certificates for HTTPS. A built Mac app can't always see the system's,
    so use certifi's when it is bundled."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "FileOrganiser/" + __version__,
    })


def parse_release(data: dict) -> Release:
    assets = {}
    for item in data.get("assets", []):
        digest = item.get("digest") or ""
        assets[item["name"]] = Asset(
            name=item["name"],
            url=item["browser_download_url"],
            size=int(item.get("size") or 0),
            sha256=digest[7:].lower() if digest.startswith("sha256:") else None,
        )
    return Release(tag=data["tag_name"], page=data.get("html_url") or RELEASES_PAGE,
                   notes=data.get("body") or "", assets=assets)


def latest_release(timeout: float = 6.0) -> Release | None:
    """The newest published release, or None if it can't be fetched."""
    try:
        with urllib.request.urlopen(_request(RELEASES_API), timeout=timeout,
                                    context=_tls()) as response:
            return parse_release(json.load(response))
    except Exception:  # offline, rate-limited, unexpected reply: stay quiet
        return None


def newer_release() -> Release | None:
    """The newest release if it is newer than this copy, else None."""
    found = latest_release()
    if found and is_newer(found.tag):
        return found
    return None


# ------------------------------------------------------- what this copy is

def install_kind(executable: str | None = None, frozen: bool | None = None,
                 platform: str = sys.platform) -> str | None:
    """"installer", "portable" or "mac" for a built copy; None from source."""
    executable = executable or sys.executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return None
    if platform == "darwin":
        return "mac" if mac_app_path(executable) else None
    if platform == "win32":
        folder = os.path.normcase(os.path.dirname(os.path.abspath(executable)))
        programs = os.path.normcase(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                                 "Programs"))
        installed = folder.startswith(programs) and os.path.exists(
            os.path.join(folder, "unins000.exe"))
        return "installer" if installed else "portable"
    return None


def asset_for(kind: str | None) -> str | None:
    return {"installer": INSTALLER, "portable": PORTABLE, "mac": MAC_IMAGE}.get(kind or "")


def mac_app_path(executable: str | None = None) -> str | None:
    """The ``.app`` folder this copy runs from (…/X.app/Contents/MacOS/X)."""
    parts = os.path.abspath(executable or sys.executable).split(os.sep)
    for index in range(len(parts) - 1, 0, -1):
        if parts[index].endswith(".app"):
            return os.sep.join(parts[: index + 1])
    return None


def can_install(release: Release, kind: str | None = None) -> bool:
    """True when this copy can update itself to *release* in place."""
    kind = install_kind() if kind is None else kind
    name = asset_for(kind)
    asset = release.assets.get(name) if name else None
    return bool(asset and asset.sha256 and asset.url.startswith(DOWNLOAD_PREFIX))


# --------------------------------------------------------------- downloading

def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset: Asset, progress: Callable[[int, int], None] | None = None,
             folder: str | None = None) -> str:
    """Download *asset* into *folder* (a new temporary one by default) and
    check it against GitHub's checksum. Returns the file's path.

    *progress* is called with (bytes so far, total) and may raise to stop.
    """
    if not asset.url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError("That download isn't from File Organiser's own releases.")
    if not asset.sha256:
        raise UpdateError("GitHub gave no checksum for the update, so it can't be checked.")
    # The name matches housekeeping.UPDATE_DOWNLOADS, which clears these away.
    folder = folder or tempfile.mkdtemp(prefix="FileOrganiser-update-")
    path = os.path.join(folder, asset.name)
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(_request(asset.url), timeout=30,
                                    context=_tls()) as response, open(path, "wb") as out:
            total = int(response.headers.get("Content-Length") or asset.size or 0)
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError("The download didn't finish: {}".format(exc)) from exc
    if digest.hexdigest() != asset.sha256:
        os.remove(path)
        raise UpdateError("The downloaded file doesn't match GitHub's checksum, so it "
                          "wasn't installed. Please try again later.")
    return path


# ---------------------------------------------------------------- installing

def install(path: str, kind: str | None = None) -> None:
    """Start installing the downloaded update. The caller should quit straight
    after: the installer or helper replaces this copy once it has closed."""
    kind = install_kind() if kind is None else kind
    if kind == "installer":
        # Inno Setup closes this copy, installs over it and, because the
        # install is silent, starts the new version when it's done.
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                          "/CLOSEAPPLICATIONS"])
    elif kind == "portable":
        new_exe = replace_portable(sys.executable, path)
        subprocess.Popen([new_exe])
    elif kind == "mac":
        _hand_over_on_mac(path)
    else:
        raise UpdateError("This copy can't update itself.")


def replace_portable(current: str, downloaded: str) -> str:
    """Put *downloaded* where *current* is. Windows lets a running exe be
    renamed, though not overwritten, so the old one steps aside as ``.old``
    (removed at the next start by :func:`clean_up`)."""
    old = current + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
        os.replace(current, old)
    except OSError as exc:
        raise UpdateError("File Organiser can't replace itself in {} ({}). Download "
                          "the new version from GitHub instead.".format(
                              os.path.dirname(current), exc)) from exc
    try:
        shutil.copy2(downloaded, current)
    except OSError as exc:
        os.replace(old, current)  # put things back as they were
        raise UpdateError("Couldn't write the new version: {}".format(exc)) from exc
    return current


MAC_HELPER = """#!/bin/sh
# Wait for File Organiser to quit, then swap in the new app and open it.
while kill -0 "$1" 2>/dev/null; do sleep 0.3; done
mount=$(mktemp -d)
hdiutil attach -nobrowse -readonly -mountpoint "$mount" "$2" || exit 1
rm -rf "$3.new"
if ditto "$mount/$4" "$3.new"; then
    rm -rf "$3" && mv "$3.new" "$3"
fi
hdiutil detach "$mount" -quiet
open "$3"
"""


def _hand_over_on_mac(image: str) -> None:
    app = mac_app_path()
    if not app or not os.access(os.path.dirname(app), os.W_OK):
        raise UpdateError("File Organiser can't replace itself where it is. Download the "
                          "new version from GitHub and drag it into Applications.")
    helper = os.path.join(os.path.dirname(image), "update.sh")
    with open(helper, "w", encoding="utf-8") as handle:
        handle.write(MAC_HELPER)
    subprocess.Popen(["/bin/sh", helper, str(os.getpid()), image, app, MAC_APP],
                     start_new_session=True)


def clean_up() -> None:
    """Remove what a previous portable update left behind."""
    if getattr(sys, "frozen", False):
        try:
            os.remove(sys.executable + ".old")
        except OSError:
            pass


def plain_notes(markdown: str) -> str:
    """Release notes without Markdown's ** and ` marks, for a plain text box."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", markdown)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return re.sub(r"^- ", "• ", text, flags=re.MULTILINE).strip()
