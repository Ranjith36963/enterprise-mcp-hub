"""Dev helper: scan Job360 log files for recent WARN / ERROR / CRITICAL entries.

Usage:
    python backend/scripts/check_logs.py
    python backend/scripts/check_logs.py --hours 48
    python backend/scripts/check_logs.py --log-dir /tmp/logs

Log format (from src/utils/logger.py):
    %(asctime)s [%(levelname)s] %(name)s [run:ABCDEF12]: %(message)s
    e.g. 2026-04-21 12:34:56 [WARNING] job360.sources.reed [run:1a2b3c4d]: ...

Files are created by RotatingFileHandler: job360.log, job360.log.1, ...
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"

_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>WARNING|ERROR|CRITICAL|INFO|DEBUG)\] "
    r"(?P<logger>[^\s:\[]+) "
    r"\[run:(?P<run>[^\]]+)\]: "
    r"(?P<msg>.*)$"
)

LEVELS_OF_INTEREST = {"WARNING", "ERROR", "CRITICAL"}


def _parse_ts(raw: str) -> datetime | None:
    try:
        # Logger writes local time without tz; treat as UTC for "last N hours".
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iter_lines(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line.rstrip("\n")
    except OSError as exc:
        print(f"[warn] cannot read {path}: {exc}", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    args = p.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        print(f"ERROR: log dir not found: {log_dir}")
        return 1

    files = sorted([f for f in log_dir.iterdir() if f.is_file() and f.name.startswith("job360.log")])
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"Log dir: {log_dir}")
    print(f"Files: {len(files)} ({total_bytes:,} bytes total)")
    for f in files:
        print(f"  - {f.name}: {f.stat().st_size:,} bytes")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    counts = {lvl: 0 for lvl in LEVELS_OF_INTEREST}
    recent: list[tuple[datetime, str, str, str]] = []  # (ts, level, logger, msg)

    for path in files:
        for line in _iter_lines(path):
            m = _LINE_RE.match(line)
            if not m:
                continue
            lvl = m.group("level")
            if lvl not in LEVELS_OF_INTEREST:
                continue
            ts = _parse_ts(m.group("ts"))
            if ts is None or ts < cutoff:
                continue
            counts[lvl] += 1
            recent.append((ts, lvl, m.group("logger"), m.group("msg")))

    print(f"\nLast {args.hours}h level counts:")
    for lvl in ("WARNING", "ERROR", "CRITICAL"):
        print(f"  {lvl:9s}: {counts[lvl]}")

    recent.sort(key=lambda r: r[0], reverse=True)
    show = recent[:20]
    print(f"\n20 most recent (of {len(recent)} in window):")
    if not show:
        print("  (none)")
    for ts, lvl, lg, msg in show:
        ts_s = ts.strftime("%Y-%m-%d %H:%M:%S")
        msg_clip = msg if len(msg) <= 140 else msg[:137] + "..."
        print(f"  {ts_s} [{lvl}] {lg}: {msg_clip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
