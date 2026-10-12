"""Asking GitHub whether a newer release is out.

The only thing sent is an ordinary web request for the public "latest
release" page; nothing about the user or their files. Any failure (offline,
firewall, GitHub down) just means no notice is shown.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.request

from . import __version__

REPOSITORY = "Vavoss123/fileorganiser"
RELEASES_API = "https://api.github.com/repos/{}/releases/latest".format(REPOSITORY)
RELEASES_PAGE = "https://github.com/{}/releases/latest".format(REPOSITORY)


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


def latest_release(timeout: float = 6.0) -> tuple[str, str] | None:
    """(tag, page URL) of the newest release, or None if it can't be fetched."""
    request = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "FileOrganiser/" + __version__},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_tls()) as response:
            data = json.load(response)
        return data["tag_name"], data.get("html_url") or RELEASES_PAGE
    except Exception:  # offline, rate-limited, unexpected reply: stay quiet
        return None


def _tls() -> ssl.SSLContext:
    """Certificates for the HTTPS request. A built Mac app can't always see the
    system's, so use certifi's when it is bundled."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def newer_release() -> tuple[str, str] | None:
    """The newest release if it is newer than this copy, else None."""
    found = latest_release()
    if found and is_newer(found[0]):
        return found
    return None
