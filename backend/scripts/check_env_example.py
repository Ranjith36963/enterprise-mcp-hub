"""Diff the env vars referenced by the backend source against .env.example.

Exit 0 when every `os.getenv("X", ...)` / `os.environ.get("X", ...)` / `os.environ["X"]`
call in ``backend/src`` has a matching entry in the repo-root ``.env.example``.
Exit 1 and print the deltas otherwise.

Usage:
    python backend/scripts/check_env_example.py

Rules:
    * Vars set but never read are fine — tools like pre-commit or the LLM
      providers may read them via their own env-var names, which we don't
      want to force into source.
    * Vars read by a test-only module are ignored (tests set their own envs).
    * A hand-maintained ALLOWLIST below captures vars that aren't read by
      backend source but are documented intentionally (e.g. scraper Algolia
      keys with working fallback defaults).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Vars intentionally in .env.example that are not read directly from backend/src.
# Each entry needs a one-line rationale so future contributors don't delete it
# and get surprised when something breaks.
ALLOWLIST = {
    # Documented override surface; scrapers/eightykhours.py reads these,
    # and the defaults are baked into source. Listed in .env.example so
    # operators can rotate when the public keys upstream change.
    "EIGHTYKHOURS_ALGOLIA_APP_ID",
    "EIGHTYKHOURS_ALGOLIA_API_KEY",
}

# Vars set by CI / infra but not read directly from backend/src.
# Typed as set[str] so set-difference below works even when empty.
# SESSION_SECRET is read from backend/src/api/auth_deps.py — NOT allowlist.
INFRA_VARS: set[str] = set()

_GETENV_RE = re.compile(r"""os\.getenv\(\s*['"]([A-Z][A-Z0-9_]*)['"]""")
_ENVIRON_GET_RE = re.compile(r"""os\.environ\.get\(\s*['"]([A-Z][A-Z0-9_]*)['"]""")
_ENVIRON_IDX_RE = re.compile(r"""os\.environ\[\s*['"]([A-Z][A-Z0-9_]*)['"]\s*\]""")
_ENV_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def _collect_source_vars() -> set[str]:
    found: set[str] = set()
    for py_file in BACKEND_SRC.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for regex in (_GETENV_RE, _ENVIRON_GET_RE, _ENVIRON_IDX_RE):
            found.update(regex.findall(text))
    return found


def _collect_env_example_vars() -> set[str]:
    if not ENV_EXAMPLE.exists():
        print(f"ERROR: {ENV_EXAMPLE} not found", file=sys.stderr)
        sys.exit(1)
    found: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE_RE.match(line)
        if match:
            found.add(match.group(1))
    return found


def main() -> int:
    src_vars = _collect_source_vars()
    env_vars = _collect_env_example_vars()

    missing_in_example = sorted(src_vars - env_vars - ALLOWLIST)
    missing_in_source = sorted(env_vars - src_vars - ALLOWLIST - INFRA_VARS)

    ok = True
    if missing_in_example:
        ok = False
        print("FAIL: backend/src reads these vars that are NOT in .env.example:")
        for v in missing_in_example:
            print(f"  - {v}")
    if missing_in_source:
        print("WARN: .env.example lists these vars that are NOT read from backend/src:")
        print("      (may be infra/CI-only; add to ALLOWLIST or INFRA_VARS if intentional)")
        for v in missing_in_source:
            print(f"  - {v}")
        # WARN, not FAIL — unused env vars are a style issue, not a bug.

    if ok:
        covered = len(src_vars & env_vars)
        print(f"OK: all {covered} source-referenced env vars documented in .env.example.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
