#!/usr/bin/env python3
"""Warn when ``backend/data/logs/`` grows past safety thresholds.

Usage:
    python scripts/log_rotation_check.py [--max-bytes 524288000] \
        [--max-file-bytes 52428800] [--max-age-days 30] [--logs-dir PATH]

Exits 0 when under all thresholds, 1 with a warning message otherwise.
Stdlib only — safe to run in a cron, pre-commit hook, or CI smoke job.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

DEFAULT_LOGS_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB total
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB per file
DEFAULT_MAX_AGE_DAYS = 30


def _human(n: int) -> str:
    """Render a byte count using binary SI units."""
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _gather_files(logs_dir: Path) -> list[Path]:
    if not logs_dir.exists():
        return []
    return [p for p in logs_dir.rglob("*") if p.is_file()]


def check(
    logs_dir: Path,
    max_bytes: int,
    max_file_bytes: int,
    max_age_days: int,
) -> tuple[int, list[str]]:
    """Return ``(exit_code, warnings)``; exit_code is 1 when any threshold is hit."""
    warnings: list[str] = []

    if not logs_dir.exists():
        # Missing logs dir is fine (clean checkout) — exit 0.
        return 0, [f"logs dir not present at {logs_dir} — nothing to check"]

    files = _gather_files(logs_dir)
    total_bytes = sum(f.stat().st_size for f in files)
    now = time.time()
    max_age_seconds = max_age_days * 86400

    if total_bytes > max_bytes:
        warnings.append(
            f"total log size {_human(total_bytes)} exceeds "
            f"--max-bytes {_human(max_bytes)} (across {len(files)} files)"
        )

    for path in files:
        stat = path.stat()
        if stat.st_size > max_file_bytes:
            warnings.append(
                f"file {path.name} is {_human(stat.st_size)} " f"(> --max-file-bytes {_human(max_file_bytes)})"
            )
        age_seconds = now - stat.st_mtime
        if age_seconds > max_age_seconds:
            age_days = age_seconds / 86400
            warnings.append(f"file {path.name} is {age_days:.1f} days old " f"(> --max-age-days {max_age_days})")

    return (1 if warnings else 0), warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", type=Path, default=DEFAULT_LOGS_DIR)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    args = parser.parse_args()

    exit_code, warnings = check(
        logs_dir=args.logs_dir,
        max_bytes=args.max_bytes,
        max_file_bytes=args.max_file_bytes,
        max_age_days=args.max_age_days,
    )

    if exit_code == 0:
        print(f"log_rotation_check: OK — {args.logs_dir}")
        if warnings:
            # info-only note (e.g. missing dir)
            for w in warnings:
                print(f"  note: {w}")
    else:
        print(f"log_rotation_check: WARN — {args.logs_dir}", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
