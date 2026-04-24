"""Bootstrap developer smoke test for Job360.

Runs the end-to-end happy path against a locally running FastAPI backend to
prove a fresh clone is wired correctly. Zero backend-module imports — only
``httpx`` + ``fpdf2`` + stdlib — so this script runs even before the backend
package is installed in the active interpreter.

Workflow:
  1. GET /api/health (bail early if backend not reachable)
  2. Generate a tiny PDF CV with fpdf2
  3. POST /api/auth/register with a timestamp-suffixed email (idempotent reruns)
  4. POST /api/profile multipart (CV + preferences JSON form field)
  5. POST /api/search?source=arbeitnow (cheap single-source run)
  6. Poll GET /api/search/{run_id}/status up to 60s
  7. GET /api/jobs?min_score=30 and print the feed count

Usage:
    python scripts/bootstrap_dev.py
    python scripts/bootstrap_dev.py --api-url http://localhost:8000

Requires: ``pip install httpx fpdf2``
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone

import httpx
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def banner(step: int, msg: str) -> None:
    print(f"==> Step {step}: {msg}", flush=True)


def fail(msg: str, resp: httpx.Response | None = None) -> None:
    print(f"[bootstrap] FAILED: {msg}", file=sys.stderr, flush=True)
    if resp is not None:
        print(f"    HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr, flush=True)
    sys.exit(1)


def make_cv_pdf_bytes() -> bytes:
    """Render a tiny plain-text CV PDF in memory. Mirrors the
    ``_make_plain_cv_pdf`` helper in tests/test_linkedin_github.py."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in [
        "Jane Bootstrap",
        "jane.bootstrap@example.com",
        "Senior ML Engineer",
        "",
        "Skills: Python, FastAPI, PyTorch, Docker, AWS.",
        "",
        "Acme AI, 2020-2024: Built RAG pipelines and LLM fine-tuning stacks.",
        "University of Cambridge, BSc Computer Science.",
    ]:
        pdf.cell(0, 6, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # fpdf2's .output() returns a bytearray when no path is passed.
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--source",
        default="arbeitnow",
        help="Single source to run for cheap smoke (default: arbeitnow)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=60,
        help="Max seconds to poll search status (default: 60)",
    )
    args = parser.parse_args()

    base = args.api_url.rstrip("/")

    # Persist cookies across calls via a single Client instance.
    with httpx.Client(base_url=base, timeout=30.0, follow_redirects=True) as client:
        # ----- Step 1: health --------------------------------------------
        banner(1, f"Health check against {base}/api/health")
        try:
            r = client.get("/api/health")
        except httpx.HTTPError as e:
            fail(f"Cannot reach backend at {base}. Is it running? ({e})")
        if r.status_code != 200:
            fail("Health check returned non-200", r)
        print(f"    ok: {r.json()}", flush=True)

        # ----- Step 2: build CV ------------------------------------------
        banner(2, "Generating in-memory PDF CV")
        cv_bytes = make_cv_pdf_bytes()
        print(f"    ok: {len(cv_bytes)} bytes", flush=True)

        # ----- Step 3: register -------------------------------------------
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        email = f"bootstrap+{ts}@job360.local"
        password = "bootstrap-s3cret-pw"
        banner(3, f"Registering user {email}")
        r = client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        if r.status_code != 201:
            fail("Register failed", r)
        user = r.json()
        print(f"    ok: user_id={user.get('id')}", flush=True)
        if not client.cookies.get("job360_session"):
            fail("Register did not set job360_session cookie")

        # ----- Step 4: upload profile ------------------------------------
        banner(4, "Uploading CV + preferences")
        prefs = {
            "target_job_titles": ["Senior Software Engineer"],
            "preferred_locations": ["London", "Remote"],
            "additional_skills": [],
        }
        files = {"cv": ("bootstrap_cv.pdf", cv_bytes, "application/pdf")}
        data = {"preferences": json.dumps(prefs)}
        r = client.post("/api/profile", files=files, data=data)
        if r.status_code != 200:
            fail("Profile upload failed", r)
        profile = r.json()
        summary = profile.get("summary") or {}
        print(
            f"    ok: skills_count={summary.get('skills_count')} " f"job_titles={summary.get('job_titles')}",
            flush=True,
        )

        # ----- Step 5: kick off search -----------------------------------
        banner(5, f"Starting search (source={args.source})")
        r = client.post("/api/search", params={"source": args.source})
        if r.status_code != 200:
            fail("Search start failed", r)
        run_id = r.json().get("run_id")
        if not run_id:
            fail("Search response missing run_id")
        print(f"    ok: run_id={run_id}", flush=True)

        # ----- Step 6: poll status ---------------------------------------
        banner(6, f"Polling /api/search/{run_id}/status (up to {args.poll_timeout}s)")
        deadline = time.monotonic() + args.poll_timeout
        last_status = None
        terminal = {"completed", "done", "failed"}
        while time.monotonic() < deadline:
            r = client.get(f"/api/search/{run_id}/status")
            if r.status_code != 200:
                fail("Status poll failed", r)
            body = r.json()
            last_status = body.get("status")
            progress = body.get("progress", "")
            print(f"    status={last_status} progress={progress}", flush=True)
            if last_status in terminal:
                break
            time.sleep(2)
        else:
            fail(f"Search did not reach terminal state within {args.poll_timeout}s")

        if last_status == "failed":
            fail(f"Search run failed: {body.get('progress')}")

        # ----- Step 7: fetch jobs ----------------------------------------
        banner(7, "Fetching feed rows (min_score=30)")
        r = client.get("/api/jobs", params={"min_score": 30})
        if r.status_code != 200:
            fail("Jobs fetch failed", r)
        jobs = r.json().get("jobs", [])

    print(f"Bootstrap complete. {len(jobs)} feed rows.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
