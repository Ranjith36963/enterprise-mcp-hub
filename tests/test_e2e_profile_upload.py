"""End-to-end test for the CV upload → profile retrieval flow.

Converts Task #24 (originally "manual Playwright verification") into durable
regression coverage. Exercises the full round-trip a user triggers from the
frontend's Profile page:

    1. POST /api/profile with multipart(cv file + preferences JSON)
    2. API calls parse_cv_async(), saves profile, returns ProfileResponse
    3. GET /api/profile re-reads the saved profile and returns the same shape

Why this is better than manual Playwright against a running frontend:

* Hermetic — no LLM API key, no running servers, no Chrome instance.
* Catches regressions in CI automatically.
* Verifies the exact contract the frontend's CV viewer depends on
  (highlights list, scoring-semantic vs display-only field separation).
* Runs in ~1s instead of a 2-minute browser boot + LLM call.

What this does NOT cover (and intentionally so):

* Real LLM extraction quality — tested separately in test_profile.py with
  _llm_result_to_cvdata() unit tests.
* Frontend rendering — Playwright browser testing is still the right tool
  for pixel-level UI verification; this test ensures the API delivers the
  data shape the UI needs, which is the load-bearing contract.
* PDF parsing — extract_text() has its own tests; here we mock parse_cv_async
  at the API boundary since the API itself doesn't care about PDF internals.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.profile.models import CVData, UserPreferences, UserProfile


# ---------------------------------------------------------------------------
# Shared fixture: a realistic CVData that mirrors what parse_cv_async returns
# after a successful LLM call. Uses the post-H1-split field layout so this
# test locks in the scoring-semantic vs display-only separation.
# ---------------------------------------------------------------------------

_FAKE_CV_DATA = CVData(
    raw_text="Ada Lovelace\nAI Engineer | London, UK\n\n"
             "SKILLS: Python, PyTorch, TensorFlow, LangChain, RAG\n\n"
             "EXPERIENCE:\n"
             "Senior AI Engineer at DeepMind (2023-present)\n"
             "- Published paper on transformer interpretability\n"
             "- Led team of 4 researchers",
    # Scoring-semantic fields — flow into SearchConfig and influence matching
    skills=["Python", "PyTorch", "TensorFlow", "LangChain", "RAG"],
    job_titles=["Senior AI Engineer"],
    companies=["DeepMind"],
    education=["BSc Computing, Imperial College London"],
    certifications=["AWS Solutions Architect"],
    summary="AI Engineer with 8 years building LLM systems",
    experience_text="Senior AI Engineer at DeepMind — led team of 4",
    # Display-only fields — used by CV viewer highlights, NOT for scoring
    name="Ada Lovelace",
    headline="AI Engineer | London",
    location="London, UK",
    achievements=[
        "Published paper on transformer interpretability",
        "Led team of 4 researchers",
    ],
)


def _fake_pdf_bytes() -> bytes:
    """Return a minimal byte payload that looks like a PDF file.

    The API doesn't actually read the bytes (parse_cv_async is mocked), so
    a %PDF header is enough to satisfy any mimetype sniffing the ASGI
    multipart parser might do.
    """
    return b"%PDF-1.4\n% fake CV for tests"


# ---------------------------------------------------------------------------
# POST /api/profile — upload CV, verify the response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_cv_returns_full_cvdetail_with_highlights():
    """Uploading a CV must return a CVDetail populated with the new H1 fields
    plus a merged `highlights` list the frontend uses for neon highlighting.
    """
    saved_profiles: list[UserProfile] = []

    def _capture_save(profile: UserProfile) -> str:
        """Intercept save_profile so we don't touch disk, but remember what was saved."""
        saved_profiles.append(profile)
        return "data/user_profile.json"

    with patch(
        "src.api.routes.profile.parse_cv_async",
        new=AsyncMock(return_value=_FAKE_CV_DATA),
    ), patch(
        "src.api.routes.profile.load_profile",
        return_value=None,  # fresh upsert — no prior profile
    ), patch(
        "src.api.routes.profile.save_profile",
        side_effect=_capture_save,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"cv": ("test_cv.pdf", BytesIO(_fake_pdf_bytes()), "application/pdf")}
            resp = await client.post("/api/profile", files=files)

    assert resp.status_code == 200, f"upsert failed: {resp.text}"
    body = resp.json()

    # ProfileSummary sanity — is_complete and skill count reflect the uploaded CV
    assert body["summary"]["is_complete"] is True
    assert body["summary"]["skills_count"] == 5
    assert "Senior AI Engineer" in body["summary"]["job_titles"]

    # CVDetail presence and scoring-semantic fields
    cv_detail = body["cv_detail"]
    assert cv_detail is not None, "cv_detail must be populated when a CV was uploaded"
    assert cv_detail["skills"] == ["Python", "PyTorch", "TensorFlow", "LangChain", "RAG"]
    assert cv_detail["job_titles"] == ["Senior AI Engineer"]
    assert cv_detail["companies"] == ["DeepMind"]
    assert cv_detail["education"] == ["BSc Computing, Imperial College London"]
    assert cv_detail["certifications"] == ["AWS Solutions Architect"]
    assert cv_detail["summary_text"] == "AI Engineer with 8 years building LLM systems"
    assert "DeepMind" in cv_detail["experience_text"]

    # Display-only fields (H1 split) — frontend uses these for header + highlights
    assert cv_detail["name"] == "Ada Lovelace"
    assert cv_detail["headline"] == "AI Engineer | London"
    assert cv_detail["location"] == "London, UK"
    assert cv_detail["achievements"] == [
        "Published paper on transformer interpretability",
        "Led team of 4 researchers",
    ]

    # Highlights — the load-bearing frontend contract. Must merge scoring-semantic
    # + display-only fields so the CV viewer can neon-highlight ANY extracted term
    # (names, locations, skills, companies, achievements) in the raw_text.
    highlights = cv_detail["highlights"]
    assert "Ada Lovelace" in highlights, "name must appear in highlights"
    assert "AI Engineer | London" in highlights, "headline must appear in highlights"
    assert "London, UK" in highlights, "location must appear in highlights"
    assert "Python" in highlights, "skills must appear in highlights"
    assert "DeepMind" in highlights, "companies must appear in highlights"
    assert "Senior AI Engineer" in highlights, "titles must appear in highlights"
    assert "Published paper on transformer interpretability" in highlights, \
        "achievements must appear in highlights"

    # save_profile was called exactly once with a profile containing the uploaded CV
    assert len(saved_profiles) == 1
    saved = saved_profiles[0]
    assert saved.cv_data.name == "Ada Lovelace"
    assert saved.cv_data.skills == ["Python", "PyTorch", "TensorFlow", "LangChain", "RAG"]
    # Scoring-semantic vs display-only separation held through the save path —
    # name must NOT appear in the skills field (H1 regression guard)
    assert "Ada Lovelace" not in saved.cv_data.skills
    assert "Ada Lovelace" not in saved.cv_data.job_titles


# ---------------------------------------------------------------------------
# POST /api/profile — LLM failure path must return 503, not 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_cv_llm_failure_returns_503():
    """C2 + the API route's RuntimeError handler: when parse_cv_async raises,
    the API must return HTTP 503 with a human-readable detail, never 500.
    """
    with patch(
        "src.api.routes.profile.parse_cv_async",
        new=AsyncMock(side_effect=RuntimeError(
            "All LLM providers failed: Gemini: quota; Groq: timeout"
        )),
    ), patch(
        "src.api.routes.profile.load_profile",
        return_value=None,
    ), patch(
        "src.api.routes.profile.save_profile",
        return_value="data/user_profile.json",
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"cv": ("broken.pdf", BytesIO(_fake_pdf_bytes()), "application/pdf")}
            resp = await client.post("/api/profile", files=files)

    assert resp.status_code == 503, \
        f"LLM failures must surface as 503 Service Unavailable, got {resp.status_code}"
    body = resp.json()
    assert "All LLM providers failed" in body["detail"], \
        "detail must include the underlying error for debuggability"


# ---------------------------------------------------------------------------
# POST /api/profile → GET /api/profile round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_then_get_returns_same_profile():
    """Upload a CV, then GET the profile, and verify both responses have the
    same CVDetail shape. This pins the contract that the frontend can rely
    on for a page refresh after upload without losing highlight data.
    """
    saved_state: dict[str, UserProfile | None] = {"profile": None}

    def _save(profile: UserProfile) -> str:
        saved_state["profile"] = profile
        return "data/user_profile.json"

    def _load() -> UserProfile | None:
        return saved_state["profile"]

    with patch(
        "src.api.routes.profile.parse_cv_async",
        new=AsyncMock(return_value=_FAKE_CV_DATA),
    ), patch(
        "src.api.routes.profile.load_profile",
        side_effect=_load,
    ), patch(
        "src.api.routes.profile.save_profile",
        side_effect=_save,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # POST — upload
            files = {"cv": ("test_cv.pdf", BytesIO(_fake_pdf_bytes()), "application/pdf")}
            post_resp = await client.post("/api/profile", files=files)
            assert post_resp.status_code == 200

            # GET — retrieve
            get_resp = await client.get("/api/profile")
            assert get_resp.status_code == 200

    post_body = post_resp.json()
    get_body = get_resp.json()

    # Both responses must have the same CVDetail shape — page refresh after
    # upload should not lose any fields.
    assert post_body["cv_detail"]["name"] == get_body["cv_detail"]["name"]
    assert post_body["cv_detail"]["skills"] == get_body["cv_detail"]["skills"]
    assert post_body["cv_detail"]["highlights"] == get_body["cv_detail"]["highlights"]
    assert post_body["cv_detail"]["achievements"] == get_body["cv_detail"]["achievements"]
    assert post_body["summary"]["skills_count"] == get_body["summary"]["skills_count"]


# ---------------------------------------------------------------------------
# POST /api/profile with preferences only — no CV — should still work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_preferences_only_no_cv():
    """Submitting preferences without a CV must succeed and return a profile
    with no cv_detail (since nothing was parsed). This is the path the
    frontend Preferences form uses when the user hasn't uploaded a CV yet.
    """
    import json as jsonlib
    saved_profiles: list[UserProfile] = []

    def _save(profile: UserProfile) -> str:
        saved_profiles.append(profile)
        return "data/user_profile.json"

    prefs_payload = jsonlib.dumps({
        "target_job_titles": ["ML Engineer", "Data Scientist"],
        "additional_skills": ["python", "sql"],
        "preferred_locations": ["London", "Remote"],
        "salary_min": 80000,
        "salary_max": 120000,
    })

    with patch(
        "src.api.routes.profile.load_profile",
        return_value=None,
    ), patch(
        "src.api.routes.profile.save_profile",
        side_effect=_save,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/profile",
                data={"preferences": prefs_payload},
            )

    assert resp.status_code == 200, f"preferences-only upsert failed: {resp.text}"
    body = resp.json()

    # Summary reflects the preferences
    assert body["summary"]["is_complete"] is True  # target_job_titles satisfies is_complete
    # cv_detail MUST be None when no CV was parsed — the route emits
    # cv_detail=cv_detail if cv.raw_text else None
    assert body["cv_detail"] is None
    # Preferences round-tripped
    assert body["preferences"]["target_job_titles"] == ["ML Engineer", "Data Scientist"]
    assert body["preferences"]["preferred_locations"] == ["London", "Remote"]
    assert body["preferences"]["salary_min"] == 80000

    # Save happened exactly once
    assert len(saved_profiles) == 1
    assert saved_profiles[0].preferences.target_job_titles == ["ML Engineer", "Data Scientist"]
