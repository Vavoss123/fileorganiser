"""Scan-and-plan in one call, and the unattended ``--auto`` run built on it.

The GUI and the automatic run share :func:`scan_and_plan`, so a sign-in tidy
moves exactly what pressing Scan then Apply would have moved. The automatic
run only ever *moves* files (undoable like any other run); it never recycles.
"""

from __future__ import annotations

import os
import time

from . import apply as apply_module
from . import config, plan as plan_module, rules, scan

LOG_LIMIT = 1 << 20  # start a fresh auto.log beyond 1 MB, keeping one old copy


def scan_and_plan(settings: dict, progress=None) -> tuple[scan.ScanResult, plan_module.Plan]:
    result = scan.scan(
        settings["folder"],
        max_depth=settings["max_depth"],
        ignore_folders=set(rules.known_destinations(settings.get("overrides"))),
        progress=progress,
    )
    built = plan_module.build_plan(
        result,
        route_to_libraries=settings["route_to_libraries"],
        overrides=settings.get("overrides"),
        include_other=settings["include_other"],
        settle_seconds=settings.get("settle_seconds", 0),
        date_folders=settings.get("date_folders", "off"),
    )
    return result, built


def log_path() -> str:
    return os.path.join(os.path.dirname(config.config_path()), "auto.log")


def run(settings: dict | None = None, quiet: bool = False) -> apply_module.ApplyReport | None:
    """Tidy the saved folder with the saved settings, logging what happened.

    ``quiet`` skips the log line when there was nothing to do, for the tray,
    which checks every minute.
    """
    settings = settings or config.load()
    folder = settings["folder"]
    lines = []
    report = None
    if not os.path.isdir(folder):
        lines.append("folder not found: {}".format(folder))
    else:
        _result, built = scan_and_plan(settings)
        report = apply_module.apply_moves(built.moves)
        lines.append("{}: {}".format(folder, report.summary))
        lines.extend("  {} -> {}".format(src, dst) for src, dst in report.moved)
        lines.extend("  FAILED {}: {}".format(src, why) for src, why in report.failed)
        if quiet and not report.moved and not report.failed:
            return report
    _append_log(lines)
    return report


def _append_log(lines: list[str]) -> None:
    path = log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path) and os.path.getsize(path) > LOG_LIMIT:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as handle:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            for line in lines:
                handle.write("{}  {}\n".format(stamp, line))
    except OSError:
        pass
