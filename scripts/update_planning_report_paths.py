"""One-shot path-fixer for planning_report.md after the backend/+frontend/src
restructure. Rewrites stale `src/`, `tests/`, `data/`, `frontend/{lib,app,components}/`,
and `src/sources/<name>.py` references to match the post-restructure layout.

Run once, then delete.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "planning_report.md"

# Same category map used by split_sources_by_category.py
CATEGORIES = {
    "apis_keyed": [
        "adzuna", "careerjet", "findwork", "google_jobs",
        "jooble", "jsearch", "reed",
    ],
    "apis_free": [
        "aijobs", "arbeitnow", "devitjobs", "himalayas", "hn_jobs",
        "jobicy", "landingjobs", "remoteok", "remotive", "yc_companies",
    ],
    "ats": [
        "ashby", "greenhouse", "lever", "personio", "pinpoint",
        "recruitee", "smartrecruiters", "successfactors", "workable", "workday",
    ],
    "feeds": [
        "biospace", "findajob", "jobs_ac_uk", "nhs_jobs",
        "realworkfromanywhere", "uni_jobs", "workanywhere", "weworkremotely",
    ],
    "scrapers": [
        "aijobs_ai", "aijobs_global", "bcs_jobs", "climatebase",
        "eightykhours", "jobtensor", "linkedin",
    ],
    "other": ["hackernews", "indeed", "nofluffjobs", "nomis", "themuse"],
}
name_to_cat = {name: cat for cat, names in CATEGORIES.items() for name in names}


def main() -> None:
    content = TARGET.read_text(encoding="utf-8")
    edits = 0

    # 1. Source files first (most specific) — insert category subfolder.
    # Match `src/sources/<name>.py` BEFORE the general `src/` sweep hits it.
    for name, cat in name_to_cat.items():
        old = f"src/sources/{name}.py"
        new = f"src/sources/{cat}/{name}.py"
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            edits += count

    # 2. requirements.txt → backend/pyproject.toml (deps were merged)
    # Only hit the bare-word form; leave `backend/requirements.txt` if it appears.
    content = re.sub(
        r"(?<![\w/])requirements\.txt(?![\w])",
        "backend/pyproject.toml",
        content,
    )

    # 3. Frontend path updates — insert `src/` after `frontend/`.
    #    Order matters: do the most specific first.
    frontend_subdirs = ["lib", "app", "components"]
    for sub in frontend_subdirs:
        old = f"frontend/{sub}/"
        new = f"frontend/src/{sub}/"
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            edits += count

    # 4. Backend top-level: src/, tests/, data/ → backend/src/, backend/tests/, backend/data/
    #    Be careful NOT to double-prefix anything that already starts with `backend/`.
    def prefix_backend(match: re.Match) -> str:
        path = match.group(0)
        # Only prefix if not already preceded by "backend/"
        # The lookbehind in the regex already handled this, so just return.
        return f"backend/{path}"

    # Use negative lookbehind to avoid double-prefixing.
    # Words we care about: src/, tests/, data/
    for prefix in ["src/", "tests/", "data/"]:
        pattern = rf"(?<!backend/)(?<![\w/]){re.escape(prefix)}"
        new_content, n = re.subn(pattern, f"backend/{prefix}", content)
        content = new_content
        edits += n

    TARGET.write_text(content, encoding="utf-8")
    print(f"Rewrote {edits} path references in {TARGET.relative_to(REPO)}")


if __name__ == "__main__":
    main()
