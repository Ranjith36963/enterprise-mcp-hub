import csv
import tempfile
from datetime import datetime, timezone

from src.models import Job
from src.storage.csv_export import export_to_csv


def _make_job(**overrides):
    defaults = dict(
        title="AI Engineer",
        company="DeepMind",
        location="London",
        salary_min=70000,
        salary_max=100000,
        apply_url="https://example.com/job",
        source="reed",
        date_found=datetime.now(timezone.utc).isoformat(),
        description="AI role requiring Python",
        match_score=85,
        visa_flag=True,
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_csv_export_creates_file():
    jobs = [_make_job(), _make_job(title="ML Engineer", company="Revolut")]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2


def test_csv_export_correct_headers():
    jobs = [_make_job()]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.reader(f)
        headers = next(reader)
    expected = [
        "job_title", "company", "location", "salary", "salary_type",
        "match_score", "role", "skill", "seniority", "experience",
        "credentials", "location_score", "recency", "semantic", "penalty",
        "apply_url", "source", "date_found", "visa_flag",
        "matched_skills", "missing_required", "missing_preferred",
        "transferable_skills", "job_type", "experience_level",
        "contact_emails",
    ]
    assert headers == expected


def test_csv_export_salary_format():
    jobs = [_make_job(salary_min=60000, salary_max=80000)]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["salary"] == "60000-80000"


def test_csv_export_empty_salary():
    jobs = [_make_job(salary_min=None, salary_max=None)]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["salary"] == ""


# ── Enhanced CSV export tests ──


def test_csv_export_26_columns():
    """CSV has exactly 26 columns matching HEADERS constant."""
    from src.storage.csv_export import HEADERS
    jobs = [_make_job()]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.reader(f)
        headers = next(reader)
    assert len(headers) == 26
    assert headers == HEADERS


def test_csv_export_match_data_parsed():
    """match_data JSON is parsed into per-dimension columns."""
    import json
    match_data = json.dumps({
        "role": 18, "skill": 20, "seniority": 8, "experience": 7,
        "credentials": 3, "location": 10, "recency": 10, "semantic": 8,
        "penalty": 0, "salary_type": "annual",
        "matched": ["Python", "SQL"], "missing_required": ["Kafka"],
        "missing_preferred": ["Go"], "transferable": ["Docker"],
        "contact_emails": ["recruiter@firm.com"],
    })
    jobs = [_make_job(match_data=match_data)]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["role"] == "18"
    assert row["skill"] == "20"
    assert row["salary_type"] == "annual"
    assert "Python" in row["matched_skills"]
    assert "Kafka" in row["missing_required"]
    assert "recruiter@firm.com" in row["contact_emails"]


def test_csv_export_visa_flag():
    """Visa flag column renders 'Yes'/'No' correctly."""
    jobs_yes = [_make_job(visa_flag=True)]
    jobs_no = [_make_job(visa_flag=False)]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs_yes, path)
    with open(path) as f:
        row = list(csv.DictReader(f))[0]
    assert row["visa_flag"] == "Yes"

    export_to_csv(jobs_no, path)
    with open(path) as f:
        row = list(csv.DictReader(f))[0]
    assert row["visa_flag"] == "No"


def test_csv_export_single_salary():
    """Single salary_min or salary_max renders correctly."""
    jobs = [_make_job(salary_min=50000, salary_max=None)]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        row = list(csv.DictReader(f))[0]
    assert row["salary"] == "50000"


def test_csv_export_empty_match_data():
    """Jobs with empty match_data still export without errors."""
    jobs = [_make_job(match_data="")]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    export_to_csv(jobs, path)
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["role"] == ""
