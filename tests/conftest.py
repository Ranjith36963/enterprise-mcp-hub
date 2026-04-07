import pytest
from datetime import datetime, timezone

from src.models import Job


@pytest.fixture
def sample_ai_job():
    return Job(
        title="AI Engineer",
        company="DeepMind",
        location="London, UK",
        salary_min=70000,
        salary_max=100000,
        description=(
            "We are looking for an AI Engineer with experience in Python, PyTorch, "
            "TensorFlow, and LangChain. You will work on RAG pipelines, LLM fine-tuning, "
            "and NLP tasks. Experience with AWS SageMaker, Docker, and Kubernetes preferred. "
            "This role involves Deep Learning and Neural Networks research. "
            "Visa sponsorship available."
        ),
        apply_url="https://deepmind.com/careers/ai-engineer",
        source="greenhouse",
        date_found=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_unrelated_job():
    return Job(
        title="Marketing Manager",
        company="Acme Corp",
        location="New York, US",
        description="Looking for a marketing manager with SEO and social media experience.",
        apply_url="https://acme.com/careers/marketing",
        source="reed",
        date_found=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_duplicate_jobs():
    base = dict(
        title="ML Engineer",
        company="Revolut",
        location="London",
        description="ML Engineer role requiring Python and PyTorch experience.",
        date_found=datetime.now(timezone.utc).isoformat(),
    )
    return [
        Job(**base, apply_url="https://reed.co.uk/jobs/123", source="reed", salary_min=60000, salary_max=80000),
        Job(**base, apply_url="https://adzuna.co.uk/jobs/456", source="adzuna"),
    ]


@pytest.fixture
def sample_visa_job():
    return Job(
        title="Data Scientist",
        company="Faculty AI",
        location="London, UK",
        description="Data Scientist role. We offer visa sponsorship for the right candidate.",
        apply_url="https://faculty.ai/careers/ds",
        source="lever",
        date_found=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_non_uk_job():
    """Job from a non-UK location (London, Ontario) — for location-scoring edge cases."""
    return Job(
        title="Data Scientist",
        company="CanadaTech",
        location="London, Ontario, Canada",
        description="Data science role with Python and SQL.",
        apply_url="https://canadatech.ca/careers/ds",
        source="jsearch",
        date_found=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_empty_description_job():
    """Job with empty description — for scoring and rendering edge cases."""
    return Job(
        title="AI Engineer",
        company="Startup Inc",
        location="London, UK",
        description="",
        apply_url="https://startup.com/jobs/1",
        source="greenhouse",
        date_found=datetime.now(timezone.utc).isoformat(),
    )
