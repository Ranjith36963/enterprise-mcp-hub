"""Lightweight robots.txt compliance checker.

Caches robots.txt per domain for the duration of one run.
Uses stdlib urllib.robotparser — no extra dependencies.
"""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("job360.robots")

# Per-domain cache: domain → (parser, allowed_for_ua)
_cache: dict[str, RobotFileParser | None] = {}


def _domain(url: str) -> str:
    """Extract scheme + netloc from a URL."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


async def fetch_robots(session, url: str) -> RobotFileParser | None:
    """Fetch and parse robots.txt for a URL's domain. Returns cached result."""
    domain = _domain(url)
    if domain in _cache:
        return _cache[domain]

    robots_url = f"{domain}/robots.txt"
    try:
        async with session.get(robots_url, timeout=__import__("aiohttp").ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                text = await resp.text()
                parser = RobotFileParser()
                parser.parse(text.splitlines())
                _cache[domain] = parser
                return parser
            else:
                # No robots.txt or error — allow everything
                _cache[domain] = None
                return None
    except Exception:
        # Network error fetching robots.txt — allow (fail open)
        _cache[domain] = None
        return None


async def is_allowed(session, url: str, user_agent: str) -> bool:
    """Check if a URL is allowed by the domain's robots.txt.

    Returns True if:
    - No robots.txt exists (fail open)
    - robots.txt allows the path for our User-Agent
    - Fetching robots.txt fails (fail open)
    """
    parser = await fetch_robots(session, url)
    if parser is None:
        return True  # No robots.txt or fetch failed — allow
    return parser.can_fetch(user_agent, url)


def clear_cache():
    """Clear the robots.txt cache (call between runs if needed)."""
    _cache.clear()
