"""Cross-platform Python equivalent of `make verify-step-0`.

Windows developers often don't have GNU `make` installed. Running
``python backend/scripts/verify_step_0.py`` from the repo root runs the same
gate checks as the Makefile target and writes ``.claude/step-0-verified.txt``
on success. Use this when ``make verify-step-0`` isn't available.

Exit code: 0 when every check passes, 1 otherwise. Prints a terse
green/red table at the end so a human can scan pass/fail at a glance.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SENTINEL = REPO_ROOT / ".claude" / "step-0-verified.txt"

REQUIRED_FILES = [
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "backend" / "README.md",
    REPO_ROOT / "frontend" / "README.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "troubleshooting.md",
    REPO_ROOT / ".gitattributes",
    REPO_ROOT / "setup.bat",
    REPO_ROOT / "backend" / "scripts" / "bootstrap_dev.py",
    REPO_ROOT / "backend" / "migrations" / "0010_run_log_observability.up.sql",
    REPO_ROOT / "backend" / "migrations" / "0010_run_log_observability.down.sql",
]


def _run(cmd: list[str], cwd: Path, timeout: int = 1500) -> tuple[bool, str]:
    """Run a subprocess, streaming output live + capturing the last line for the summary.

    Stream-then-summarize avoids the pipe-buffering slowdown observed on Windows
    when running pytest under ``capture_output=True`` (a 320s direct run
    stretched past 600s under capture). The summary line is the final non-empty
    stdout line the subprocess emitted.
    """
    try:
        proc = subprocess.Popen(  # noqa: S603  # trusted — cmd built from literals
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        return False, f"LAUNCH ERROR: {exc}"
    last_line = ""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            stripped = line.strip()
            if stripped:
                last_line = stripped
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, f"TIMEOUT (>{timeout}s)"
    return proc.returncode == 0, last_line


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    print("==> gate 1/4: pytest")
    ok, line = _run(
        [sys.executable, "-m", "pytest", "tests/", "--ignore=tests/test_main.py", "-q", "-p", "no:randomly", "--tb=no"],
        cwd=BACKEND_DIR,
    )
    results.append(("pytest", ok, line))

    print("==> gate 2/4: env parity")
    ok, line = _run(
        [sys.executable, "scripts/check_env_example.py"],
        cwd=BACKEND_DIR,
    )
    results.append(("env parity", ok, line))

    print("==> gate 3/4: migrations status")
    ok, line = _run(
        [sys.executable, "-m", "migrations.runner", "status"],
        cwd=BACKEND_DIR,
    )
    results.append(("migrations status", ok, line))

    print("==> gate 4/4: docs inventory")
    missing = [str(f.relative_to(REPO_ROOT)) for f in REQUIRED_FILES if not f.exists()]
    ok = not missing
    line = "all present" if ok else f"missing: {', '.join(missing)}"
    results.append(("docs inventory", ok, line))

    print()
    print(f"{'check':<25} {'state':<6} notes")
    print("-" * 72)
    all_ok = True
    for name, ok, line in results:
        state = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{name:<25} {state:<6} {line[:40]}")

    if not all_ok:
        print("\nSTEP-0 gate FAILED — see output above.")
        return 1

    SENTINEL.parent.mkdir(parents=True, exist_ok=True)
    try:
        sha = subprocess.check_output(  # noqa: S603, S607  # trusted git call
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        sha = "unknown"
    SENTINEL.write_text(f"{sha}\n", encoding="utf-8")
    print(f"\nSTEP-0 GREEN: {sha}")
    print(f"Sentinel written to {SENTINEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
