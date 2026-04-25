"""Step-1 gate check: WorkerSettings.functions must include the Step-1 task set.

Specifically: enrich_job_task (Cohort B B10 closure) must be registered
alongside score_and_ingest. If either is missing, ARQ won't dispatch
the task at runtime and the multi-tenant enrichment path is dead.

Exits 0 on success, 1 on missing entries. Used by `make verify-step-1`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def main() -> int:
    from src.workers.settings import WorkerSettings  # noqa: E402

    names = [getattr(f, "__name__", str(f)) for f in WorkerSettings.functions]
    required = {"enrich_job_task", "score_and_ingest"}
    missing = required - set(names)

    if missing:
        print(f"FAIL: WorkerSettings.functions missing: {missing}")
        print(f"  Currently registered: {names}")
        return 1

    print(f"OK: WorkerSettings.functions includes {sorted(required)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
