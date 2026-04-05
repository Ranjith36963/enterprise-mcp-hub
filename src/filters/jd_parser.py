"""Parse structured information from job descriptions.

Two levels of extraction:
1. detect_job_type() — quick label (Full-time, Contract, etc.)
2. parse_jd() — full structured ParsedJD with required/preferred skills,
   experience years, qualifications, and section text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Job type detection (existing) ─────────────────────────────────────

# Job type patterns — ordered by specificity (most specific first)
_JOB_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Fixed Term", re.compile(
        r'\b(fixed[\s-]?term|ftc|fixed[\s-]?term[\s-]?contract)\b', re.IGNORECASE)),
    ("Freelance", re.compile(
        r'\b(freelance|freelancer|self[\s-]?employed)\b', re.IGNORECASE)),
    ("Contract", re.compile(
        r'\b(contract(?:or)?|contracting)\b', re.IGNORECASE)),
    ("Part-time", re.compile(
        r'\b(part[\s-]?time)\b', re.IGNORECASE)),
    ("Permanent", re.compile(
        r'\b(permanent|perm)\b', re.IGNORECASE)),
    ("Full-time", re.compile(
        r'\b(full[\s-]?time)\b', re.IGNORECASE)),
]


def detect_job_type(text: str) -> str:
    """Extract job type from title + description text.

    Returns the first (most specific) match, or "" if none found.
    """
    for label, pattern in _JOB_TYPE_PATTERNS:
        if pattern.search(text):
            return label
    return ""


# ── Structured JD parsing ────────────────────────────────────────────


@dataclass
class ParsedJD:
    """Structured representation of a job description."""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    experience_years: Optional[int] = None       # minimum years required
    qualifications: list[str] = field(default_factory=list)
    responsibilities: str = ""
    benefits: str = ""
    salary_mentioned: bool = False
    seniority_signal: str = ""  # "entry", "mid", "senior", "lead", "executive"
    salary_min: Optional[float] = None     # extracted from JD text (GBP annual)
    salary_max: Optional[float] = None     # extracted from JD text (GBP annual)
    salary_type: str = ""                  # "annual", "daily", "hourly", "weekly", "ote"
    contact_emails: list[str] = field(default_factory=list)


# ── JD section detection ─────────────────────────────────────────────

_JD_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "required": re.compile(
        r'^(?:requirements?|essential|must[\s-]?have|required|'
        r'what\s+you(?:\'ll)?\s+need|what\s+we(?:\'re)?\s+looking\s+for|'
        r'minimum\s+qualifications?|key\s+requirements?)\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE,
    ),
    "preferred": re.compile(
        r'^(?:nice[\s-]?to[\s-]?have|desirable|preferred|bonus|'
        r'advantageous|ideally|optional|additional)\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE,
    ),
    "responsibilities": re.compile(
        r'^(?:responsibilities|duties|what\s+you(?:\'ll)?\s+do|'
        r'the\s+role|role\s+overview|about\s+the\s+role|key\s+duties)\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE,
    ),
    "qualifications": re.compile(
        r'^(?:qualifications?|education|credentials?|'
        r'academic\s+requirements?)\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE,
    ),
    "benefits": re.compile(
        r'^(?:benefits?|perks|what\s+we\s+offer|package|compensation)\s*[:\-]?\s*$',
        re.IGNORECASE | re.MULTILINE,
    ),
}

# ── Experience year extraction ────────────────────────────────────────

_EXPERIENCE_RE = re.compile(
    r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)',
    re.IGNORECASE,
)

# Alternative: "at least 5 years"
_EXPERIENCE_ALT_RE = re.compile(
    r'(?:at\s+least|minimum|min)\s+(\d+)\s*(?:years?|yrs?)',
    re.IGNORECASE,
)

# ── Salary detection ─────────────────────────────────────────────────

_SALARY_RE = re.compile(
    r'(?:£|GBP)\s*[\d,]+|[\d,]+\s*(?:per\s+annum|p\.?a\.?|salary)',
    re.IGNORECASE,
)

# Conversion constants for non-annual salary types
_WORKING_DAYS_PER_YEAR = 220
_WORKING_HOURS_PER_YEAR = 1760   # 220 days × 8 hours
_WORKING_WEEKS_PER_YEAR = 48

# ── OTE (On-Target Earnings) — must match before other patterns ──
# "£50k base + £20k OTE" → captures OTE portion as max
_SALARY_OTE_BASE_RE = re.compile(
    r'£\s*(\d{2,3})\s*k\s*(?:base|basic)\s*.*?£\s*(\d{2,3})\s*k\s*(?:OTE|ote|on[\s-]?target)',
    re.IGNORECASE,
)
# "OTE £80,000" or "up to £80k OTE" or "£80k OTE"
_SALARY_OTE_RE = re.compile(
    r'(?:OTE|on[\s-]?target[\s-]?earnings?)\s*(?:of\s+)?£\s*(\d{2,3}[,.]?\d{3}|\d{2,3}\s*k)',
    re.IGNORECASE,
)
_SALARY_OTE_SUFFIX_RE = re.compile(
    r'£\s*(\d{2,3}[,.]?\d{3}|\d{2,3}\s*k)\s*(?:OTE|on[\s-]?target)',
    re.IGNORECASE,
)

# ── Daily contractor rates ──
# "£400-£600 per day", "£400-£600 p/d"
_SALARY_DAILY_RANGE_RE = re.compile(
    r'£\s*(\d{2,4})\s*[-–to]+\s*£?\s*(\d{2,4})\s*(?:per\s+day|p/?d|daily|/day)',
    re.IGNORECASE,
)
# "£500 per day", "£500/day", "£500 p/d", "£500 daily"
_SALARY_DAILY_RE = re.compile(
    r'£\s*(\d{2,4})\s*(?:per\s+day|p/?d|daily|/day)',
    re.IGNORECASE,
)

# ── Hourly rates ──
# "£25-£35 per hour", "£25-£35/hr"
_SALARY_HOURLY_RANGE_RE = re.compile(
    r'£\s*(\d{1,3}(?:\.\d{1,2})?)\s*[-–to]+\s*£?\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:per\s+hour|p/?h|/hour|/hr|hourly)',
    re.IGNORECASE,
)
# "£25/hour", "£30 p/h", "£25 per hour"
_SALARY_HOURLY_RE = re.compile(
    r'£\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:per\s+hour|p/?h|/hour|/hr|hourly)',
    re.IGNORECASE,
)

# ── Weekly rates ──
# "£2,000 per week", "£2k/week", "£2,000 pw"
_SALARY_WEEKLY_RANGE_RE = re.compile(
    r'£\s*(\d{1,2}[,.]?\d{3}|\d{1,2}\s*k)\s*[-–to]+\s*£?\s*(\d{1,2}[,.]?\d{3}|\d{1,2}\s*k)\s*(?:per\s+week|p/?w|/week|weekly|pw)',
    re.IGNORECASE,
)
_SALARY_WEEKLY_RE = re.compile(
    r'£\s*(\d{1,2}[,.]?\d{3}|\d{1,2}\s*k)\s*(?:per\s+week|p/?w|/week|weekly|pw)',
    re.IGNORECASE,
)

# ── Annual salary patterns (existing, kept in order) ──
# Salary range extraction: "£60,000 - £80,000"
_SALARY_RANGE_RE = re.compile(
    r'£\s*(\d{2,3}[,.]?\d{3})\s*[-–to]+\s*£?\s*(\d{2,3}[,.]?\d{3})',
    re.IGNORECASE,
)
# "£50k - £70k" variant
_SALARY_K_RANGE_RE = re.compile(
    r'£\s*(\d{2,3})\s*k\s*[-–to]+\s*£?\s*(\d{2,3})\s*k',
    re.IGNORECASE,
)
# Single salary: "£45,000 per annum"
_SALARY_SINGLE_RE = re.compile(
    r'£\s*(\d{2,3}[,.]?\d{3})\s*(?:per\s+annum|p\.?a\.?|annual)',
    re.IGNORECASE,
)
# Single k notation: "£45k"
_SALARY_SINGLE_K_RE = re.compile(
    r'£\s*(\d{2,3})\s*k\b',
    re.IGNORECASE,
)

# ── Seniority signals ────────────────────────────────────────────────

_JD_SENIORITY_SIGNALS: dict[str, list[str]] = {
    "entry": ["entry level", "graduate", "junior", "trainee", "intern",
              "no experience required", "0-1 year", "0-2 year"],
    "mid": ["mid-level", "mid level", "2-5 year", "3-5 year",
            "some experience"],
    "senior": ["senior", "experienced", "5+ year", "5-10 year",
               "significant experience"],
    "lead": ["lead", "principal", "staff", "head of", "manager",
             "team lead", "10+ year"],
    "executive": ["director", "vp", "vice president", "chief",
                  "c-level", "executive"],
}

# ── Inline required/preferred signal words ────────────────────────────

_REQUIRED_SIGNALS = re.compile(
    r'\b(?:essential|required|must[\s-]?have|mandatory|necessary|critical)\b',
    re.IGNORECASE,
)

_PREFERRED_SIGNALS = re.compile(
    r'\b(?:desirable|nice[\s-]?to[\s-]?have|preferred|bonus|advantageous|ideally)\b',
    re.IGNORECASE,
)

# ── Skill extraction from bullet points ───────────────────────────────

_BULLET_RE = re.compile(r'^[\s]*[-•·▪*]\s*(.+)$', re.MULTILINE)

# Qualification patterns
_QUAL_RE = re.compile(
    r'\b(PhD|DPhil|MSc|MA|MEng|MBA|BSc|BA|BEng|LLB|PGCE|PGDip|PGCert'
    r'|NVQ|BTEC|HND|HNC|ACCA|CIMA|CFA|CIPD|PRINCE2|PMP|ITIL'
    r'|AWS\s+Certif|Azure\s+Certif|GCP\s+Certif'
    r'|Chartered|Fellow|MRICS|MCSP|RGN|RMN)\b',
    re.IGNORECASE,
)

# Skill-like items in bullet points — covers ALL professional domains
_SKILL_ITEM_RE = re.compile(
    r'\b(?:'
    # ── Technology & Software ──
    r'Python|Java|JavaScript|TypeScript|React|Angular|Vue|Node\.?js|'
    r'Docker|Kubernetes|AWS|Azure|GCP|SQL|PostgreSQL|MySQL|MongoDB|Redis|'
    r'TensorFlow|PyTorch|Spark|Airflow|Snowflake|dbt|Kafka|'
    r'Git|CI/CD|REST|GraphQL|Agile|Scrum|Jira|'
    r'Salesforce|HubSpot|Excel|Tableau|Power\s*BI|SAP|'
    r'C\+\+|C#|\.NET|Go|Rust|Scala|Ruby|PHP|Swift|Kotlin|'
    r'HTML|CSS|SASS|Webpack|Vite|'
    r'Machine Learning|Deep Learning|NLP|Computer Vision|'
    r'Data Analysis|Data Engineering|DevOps|SRE|'
    # ── Healthcare & Nursing ──
    r'NHS|CQC|Patient Care|Clinical Assessment|Wound Management|'
    r'Medication Administration|Triage|Safeguarding|NMC|BLS|ALS|ILS|'
    r'Infection Control|Care Planning|Palliative Care|Mental Health|'
    r'Phlebotomy|Cannulation|ECG|Catheterisation|Tracheostomy|'
    r'Health and Safety|Manual Handling|Nursing|Midwifery|'
    # ── Finance & Accounting ──
    r'ACCA|CIMA|CFA|IFRS|GAAP|FP&A|AML|KYC|'
    r'Financial Modelling|Financial Analysis|Budgeting|Forecasting|'
    r'Treasury|Tax|VAT|PAYE|Bookkeeping|Xero|Sage|QuickBooks|'
    r'Investment Banking|Portfolio Management|Risk Analysis|'
    r'Corporate Finance|Mergers and Acquisitions|Due Diligence|'
    r'Credit Risk|Market Risk|Basel|Solvency|'
    # ── Legal ──
    r'Conveyancing|Litigation|Contract Law|Employment Law|'
    r'Corporate Law|Intellectual Property|Family Law|Criminal Law|'
    r'Legal Research|Case Management|SRA|LPC|BPTC|'
    r'Dispute Resolution|Arbitration|Mediation|Regulatory Compliance|'
    # ── Engineering (Civil/Structural/Mechanical) ──
    r'AutoCAD|SolidWorks|Revit|BIM|Tekla|ETABS|SAP2000|STAAD|'
    r'Structural Analysis|Finite Element|Geotechnical|Surveying|'
    r'Construction Management|NEC|JCT|CDM|Building Regulations|'
    r'HVAC|PLC|SCADA|CAD|PCB|P&ID|'
    # ── Marketing & Digital ──
    r'SEO|SEM|PPC|Google Analytics|Google Ads|Meta Ads|'
    r'Content Marketing|Social Media Marketing|Email Marketing|'
    r'CRM|Marketing Automation|A/B Testing|Conversion Rate|'
    r'Brand Strategy|Copywriting|Digital Strategy|'
    # ── HR & People ──
    r'CIPD|Recruitment|Talent Acquisition|ATS|Payroll|'
    r'Employee Relations|L&D|DEI|Onboarding|HRIS|Workday|'
    r'Performance Management|Compensation|Benefits Administration|'
    # ── Project Management ──
    r'PRINCE2|PMP|Six\s*Sigma|Lean|'
    r'Stakeholder Management|Change Management|Benefits Realisation|'
    r'Programme Management|PMO|Earned Value|'
    # ── Cybersecurity ──
    r'CISSP|CISM|CEH|OSCP|SIEM|Splunk|'
    r'Penetration Testing|Vulnerability Assessment|Incident Response|'
    r'Threat Intelligence|SOC|NIST|ISO\s*27001|Firewall|IDS|IPS|'
    # ── Environmental & Sustainability ──
    r'ESG|Carbon Footprint|Lifecycle Assessment|ISO\s*14001|'
    r'Environmental Impact Assessment|BREEAM|Sustainability Reporting|'
    r'Net Zero|Circular Economy|Renewable Energy|'
    # ── General Professional ──
    r'GDPR|Compliance|Risk Management|Audit|'
    r'Stakeholder Engagement|Report Writing|Presentation Skills|'
    r'Leadership|Team Management|Strategic Planning|'
    r'Business Development|Account Management|Negotiation'
    r')\b',
    re.IGNORECASE,
)


def _find_jd_sections(text: str) -> dict[str, str]:
    """Split job description into named sections."""
    matches = []
    for section_name, pattern in _JD_SECTION_PATTERNS.items():
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), section_name))

    if not matches:
        return {}

    matches.sort(key=lambda x: x[0])
    sections: dict[str, str] = {}
    for i, (start, end, name) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        sections[name] = text[end:next_start].strip()

    return sections


def _extract_skills_from_section(text: str) -> list[str]:
    """Extract skill/technology mentions from a JD section."""
    found: set[str] = set()
    for m in _SKILL_ITEM_RE.finditer(text):
        found.add(m.group(0))
    return sorted(found)


def _extract_qualifications(text: str) -> list[str]:
    """Extract qualification/certification mentions."""
    found: set[str] = set()
    for m in _QUAL_RE.finditer(text):
        found.add(m.group(0))
    return sorted(found)


def _extract_experience_years(text: str) -> Optional[int]:
    """Extract minimum years of experience required."""
    m = _EXPERIENCE_RE.search(text)
    if m:
        return int(m.group(1))
    m = _EXPERIENCE_ALT_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _parse_k_or_full(raw: str) -> float:
    """Parse a value like '50k', '50,000', or '50.000' into a float."""
    raw = raw.strip()
    if raw.lower().endswith("k"):
        return float(raw[:-1].strip()) * 1000
    return float(raw.replace(",", "").replace(".", ""))


def _extract_salary(text: str) -> tuple[Optional[float], Optional[float], str]:
    """Extract salary from JD text, converting to GBP annual equivalent.

    Tries patterns in priority order (most-specific first):
    OTE → daily → hourly → weekly → annual range → annual k range → annual single

    Returns:
        (salary_min, salary_max, salary_type)
        salary_type: "ote", "daily", "hourly", "weekly", "annual", or ""
    """
    # ── OTE patterns ──
    m = _SALARY_OTE_BASE_RE.search(text)
    if m:
        base = float(m.group(1)) * 1000
        ote = float(m.group(2)) * 1000
        return base, base + ote, "ote"

    m = _SALARY_OTE_RE.search(text)
    if m:
        val = _parse_k_or_full(m.group(1))
        return None, val, "ote"

    m = _SALARY_OTE_SUFFIX_RE.search(text)
    if m:
        val = _parse_k_or_full(m.group(1))
        return None, val, "ote"

    # ── Daily rates → convert to annual ──
    m = _SALARY_DAILY_RANGE_RE.search(text)
    if m:
        lo = float(m.group(1)) * _WORKING_DAYS_PER_YEAR
        hi = float(m.group(2)) * _WORKING_DAYS_PER_YEAR
        return lo, hi, "daily"

    m = _SALARY_DAILY_RE.search(text)
    if m:
        val = float(m.group(1)) * _WORKING_DAYS_PER_YEAR
        return val, None, "daily"

    # ── Hourly rates → convert to annual ──
    m = _SALARY_HOURLY_RANGE_RE.search(text)
    if m:
        lo = float(m.group(1)) * _WORKING_HOURS_PER_YEAR
        hi = float(m.group(2)) * _WORKING_HOURS_PER_YEAR
        return lo, hi, "hourly"

    m = _SALARY_HOURLY_RE.search(text)
    if m:
        val = float(m.group(1)) * _WORKING_HOURS_PER_YEAR
        return val, None, "hourly"

    # ── Weekly rates → convert to annual ──
    m = _SALARY_WEEKLY_RANGE_RE.search(text)
    if m:
        lo = _parse_k_or_full(m.group(1)) * _WORKING_WEEKS_PER_YEAR
        hi = _parse_k_or_full(m.group(2)) * _WORKING_WEEKS_PER_YEAR
        return lo, hi, "weekly"

    m = _SALARY_WEEKLY_RE.search(text)
    if m:
        val = _parse_k_or_full(m.group(1)) * _WORKING_WEEKS_PER_YEAR
        return val, None, "weekly"

    # ── Annual patterns (existing) ──
    m = _SALARY_RANGE_RE.search(text)
    if m:
        lo = float(m.group(1).replace(",", "").replace(".", ""))
        hi = float(m.group(2).replace(",", "").replace(".", ""))
        return lo, hi, "annual"

    m = _SALARY_K_RANGE_RE.search(text)
    if m:
        lo = float(m.group(1)) * 1000
        hi = float(m.group(2)) * 1000
        return lo, hi, "annual"

    # Single annual value
    m = _SALARY_SINGLE_RE.search(text)
    if m:
        val = float(m.group(1).replace(",", "").replace(".", ""))
        return val, None, "annual"

    m = _SALARY_SINGLE_K_RE.search(text)
    if m:
        val = float(m.group(1)) * 1000
        return val, None, "annual"

    return None, None, ""


def _detect_seniority(text: str) -> str:
    """Detect seniority level from JD text."""
    text_lower = text.lower()
    # Check from most senior to least — return highest match
    for level in ("executive", "lead", "senior", "mid", "entry"):
        for signal in _JD_SENIORITY_SIGNALS[level]:
            if signal in text_lower:
                return level
    return ""


def _classify_inline_skills(text: str) -> tuple[list[str], list[str]]:
    """Classify skills as required or preferred based on surrounding context.

    Scans each line/paragraph for required/preferred signal words,
    then extracts any skill mentions within that context.
    """
    required: set[str] = set()
    preferred: set[str] = set()

    # Split into paragraphs/sentences
    chunks = re.split(r'\n\n|\.\s+', text)
    for chunk in chunks:
        skills = set()
        for m in _SKILL_ITEM_RE.finditer(chunk):
            skills.add(m.group(0))
        if not skills:
            continue

        if _REQUIRED_SIGNALS.search(chunk):
            required.update(skills)
        elif _PREFERRED_SIGNALS.search(chunk):
            preferred.update(skills)
        else:
            # Default: treat as required (most JDs list requirements)
            required.update(skills)

    return sorted(required), sorted(preferred)


# ── Email extraction ────────────────────────────────────────────────

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

_EMAIL_BLACKLIST_PREFIXES = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "info", "privacy", "support", "help", "admin",
    "careers", "jobs", "recruitment", "hr",
    "webmaster", "postmaster", "mailer-daemon",
})

_EMAIL_BLACKLIST_DOMAINS = frozenset({
    "example.com", "example.org", "test.com", "sentry.io",
    "wixpress.com", "googleusercontent.com",
})


def _extract_emails(text: str) -> list[str]:
    """Extract likely recruiter/contact emails, filtering false positives."""
    raw = _EMAIL_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for email in raw:
        email_lower = email.lower()
        if email_lower in seen:
            continue
        seen.add(email_lower)
        local, _, domain = email_lower.partition("@")
        if local in _EMAIL_BLACKLIST_PREFIXES:
            continue
        if domain in _EMAIL_BLACKLIST_DOMAINS:
            continue
        result.append(email)
    return result


def parse_jd(description: str, user_skills: list[str] | None = None) -> ParsedJD:
    """Parse a job description into structured components.

    Extracts required/preferred skills, experience requirements,
    qualifications, and seniority signals.

    Args:
        description: Raw job description text.
        user_skills: Optional list of the user's own skills. When provided,
            the parser scans for these skills (with synonym matching) after
            the hardcoded regex extraction — making it domain-agnostic.
    """
    if not description or len(description) < 20:
        return ParsedJD()

    result = ParsedJD()

    # Try section-based extraction first
    sections = _find_jd_sections(description)

    if sections:
        # Section-based skill classification
        if "required" in sections:
            result.required_skills = _extract_skills_from_section(sections["required"])
        if "preferred" in sections:
            result.preferred_skills = _extract_skills_from_section(sections["preferred"])
        if "responsibilities" in sections:
            result.responsibilities = sections["responsibilities"][:500]
        if "qualifications" in sections:
            result.qualifications = _extract_qualifications(sections["qualifications"])
        if "benefits" in sections:
            result.benefits = sections["benefits"][:500]

        # If no section-based skills found, try inline classification
        if not result.required_skills and not result.preferred_skills:
            req, pref = _classify_inline_skills(description)
            result.required_skills = req
            result.preferred_skills = pref
    else:
        # No section headers — use inline signal classification
        req, pref = _classify_inline_skills(description)
        result.required_skills = req
        result.preferred_skills = pref

    # Phase 4A: scan for user's own skills (domain-agnostic matching)
    if user_skills:
        _enrich_with_user_skills(description, sections, result, user_skills)

    # Also scan qualifications section for skills
    if "qualifications" in sections and not result.qualifications:
        result.qualifications = _extract_qualifications(sections["qualifications"])
    # Fallback: scan entire text for qualifications
    if not result.qualifications:
        result.qualifications = _extract_qualifications(description)

    # Experience years
    result.experience_years = _extract_experience_years(description)

    # Salary extraction + mention flag
    result.salary_min, result.salary_max, result.salary_type = _extract_salary(description)
    result.salary_mentioned = result.salary_min is not None or bool(_SALARY_RE.search(description))

    # Seniority signal
    result.seniority_signal = _detect_seniority(description)

    # Email extraction (filter common false positives)
    result.contact_emails = _extract_emails(description)

    return result


def _enrich_with_user_skills(
    description: str,
    sections: dict[str, str],
    result: ParsedJD,
    user_skills: list[str],
) -> None:
    """Scan JD for user's skills using synonym matching, add any new finds.

    Classifies found skills as required or preferred based on which JD section
    they appear in. If no sections exist, defaults to required.
    """
    from src.filters.description_matcher import text_contains_with_synonyms

    already_found = {s.lower() for s in result.required_skills + result.preferred_skills}

    for skill in user_skills:
        if skill.lower() in already_found:
            continue
        if not text_contains_with_synonyms(description, skill):
            continue

        # Classify based on section context
        added = False
        if sections:
            if "preferred" in sections and text_contains_with_synonyms(
                sections["preferred"], skill
            ):
                result.preferred_skills.append(skill)
                added = True
            elif "required" in sections and text_contains_with_synonyms(
                sections["required"], skill
            ):
                result.required_skills.append(skill)
                added = True

        if not added:
            # Found in description but not in a specific section → required
            result.required_skills.append(skill)
        already_found.add(skill.lower())
