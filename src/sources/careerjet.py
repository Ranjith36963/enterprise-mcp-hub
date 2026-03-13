"""Careerjet — global job search engine with free JSON API.

Free API, no key required. Supports 60+ countries.
URL: https://www.careerjet.co.uk/partners/api/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_search_queries, get_search_locations
from src.config.settings import USER_AGENT

logger = logging.getLogger("job360.sources.careerjet")

# Map common locations to Careerjet locale codes
_LOCALE_MAP = {
    "uk": "en_GB",
    "united kingdom": "en_GB",
    "london": "en_GB",
    "us": "en_US",
    "usa": "en_US",
    "united states": "en_US",
    "canada": "en_US",
    "germany": "de_DE",
    "france": "fr_FR",
    "india": "en_IN",
    "australia": "en_AU",
    "remote": "en_GB",
}


class CareerjetSource(BaseJobSource):
    name = "careerjet"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        seen_urls: set[str] = set()
        queries = get_search_queries(limit=3)
        locations = get_search_locations()

        # Determine locale
        locale = "en_GB"  # default
        for loc in locations:
            loc_key = loc.lower().strip()
            if loc_key in _LOCALE_MAP:
                locale = _LOCALE_MAP[loc_key]
                break

        location_str = locations[0] if locations else ""

        for query in queries:
            params = {
                "keywords": query,
                "location": location_str,
                "locale_code": locale,
                "sort": "date",
                "pagesize": 50,
                "page": 1,
                "user_ip": "0.0.0.0",
                "user_agent": USER_AGENT,
                "affid": "job360",
            }
            data = await self._get_json(
                "http://public.api.careerjet.net/search",
                params=params,
            )
            if not data or "jobs" not in data:
                continue
            for item in data["jobs"]:
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                sal = item.get("salary", "")
                jobs.append(Job(
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("locations", ""),
                    description=item.get("description", ""),
                    apply_url=url,
                    source=self.name,
                    date_found=item.get("date", "") or datetime.now(timezone.utc).isoformat(),
                ))
        logger.info(f"Careerjet: found {len(jobs)} jobs")
        return jobs
