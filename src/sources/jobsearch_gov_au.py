"""Australian Government Job Search — free API.

No API key needed. JSON REST API.
Covers: all jobs posted through Australian government job services.
URL: https://jobsearch.gov.au/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_search_queries, get_search_locations

logger = logging.getLogger("job360.sources.jobsearch_gov_au")


class JobSearchGovAUSource(BaseJobSource):
    name = "jobsearch_gov_au"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        seen_urls: set[str] = set()
        queries = get_search_queries(limit=3)

        # Only fetch if user profile mentions Australia
        locations = get_search_locations()
        au_relevant = any(
            loc.lower() in ("australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "au")
            for loc in locations
        )
        if not au_relevant:
            logger.debug("JobSearchGovAU: no AU locations in profile, skipping")
            return []

        for query in queries:
            params = {
                "keywords": query,
                "pageSize": 50,
                "page": 1,
            }
            data = await self._get_json(
                "https://jobsearch.gov.au/api/v1/search",
                params=params,
            )
            if not data or "data" not in data:
                continue
            for item in data.get("data", []):
                url = item.get("teaser", {}).get("url", "") if isinstance(item.get("teaser"), dict) else ""
                if not url:
                    url = f"https://jobsearch.gov.au/job/{item.get('id', '')}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                sal_text = item.get("salary", "")
                location = item.get("location", {})
                if isinstance(location, dict):
                    location = location.get("label", "Australia")
                jobs.append(Job(
                    title=item.get("title", ""),
                    company=item.get("employer", ""),
                    location=location if isinstance(location, str) else "Australia",
                    description=item.get("description", "")[:500],
                    apply_url=url,
                    source=self.name,
                    date_found=item.get("datePosted", "") or datetime.now(timezone.utc).isoformat(),
                ))
        logger.info(f"JobSearchGovAU: found {len(jobs)} jobs")
        return jobs
