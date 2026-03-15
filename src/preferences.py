"""User Preferences — the second input layer beyond the CV.

The CV captures what the user HAS done (proven strengths).
Preferences capture what the user WANTS and CAN do:
- Additional job titles they'd accept (e.g. "AI Platform Engineer" when CV says "AI Engineer")
- Skills they know but didn't list on CV (e.g. Azure/GCP when CV only mentions AWS)
- Preferred locations beyond what's on the CV
- About me / career objective text
- Projects they've worked on (extra keyword signal)
- Certifications and licenses
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config.settings import USER_PREFERENCES_PATH

logger = logging.getLogger("job360.preferences")

# Default empty preferences structure
_EMPTY_PREFERENCES = {
    "job_titles": [],
    "skills": [],
    "locations": [],
    "about_me": "",
    "projects": [],
    "certifications": [],
    "updated_at": "",
}


def load_preferences(path: Path | None = None) -> dict | None:
    """Load user preferences from JSON. Returns None if file doesn't exist."""
    src = path or USER_PREFERENCES_PATH
    if not src.exists():
        return None
    try:
        data = json.loads(src.read_text())
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load preferences: %s", e)
        return None


def save_preferences(prefs: dict, path: Path | None = None) -> Path:
    """Save user preferences as JSON. Returns the path written to."""
    dest = path or USER_PREFERENCES_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    dest.write_text(json.dumps(prefs, indent=2))
    logger.info("User preferences saved to %s", dest)
    return dest


def get_empty_preferences() -> dict:
    """Return a fresh empty preferences dict."""
    return dict(_EMPTY_PREFERENCES)
