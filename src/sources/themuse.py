"""The Muse — curated job board with free public API.

No API key required. JSON REST API.
Covers: tech, marketing, finance, healthcare, education — global.
URL: https://www.themuse.com/developers/api/v2
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_search_queries, get_search_locations, get_relevance_keywords

logger = logging.getLogger("job360.sources.themuse")


class TheMuseSource(BaseJobSource):
    name = "themuse"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        seen_urls: set[str] = set()
        queries = get_search_queries(limit=3)
        locations = get_search_locations()[:2] or ["Flexible / Remote"]
        keywords = get_relevance_keywords()

        for query in queries:
            # The Muse API uses "category" and "location" params
            # but also supports free-text via "page" browsing
            params = {
                "page": "0",
                "descending": "true",
            }
            # Add location if available
            if locations:
                params["location"] = locations[0]

            data = await self._get_json(
                "https://www.themuse.com/api/public/jobs",
                params=params,
            )
            if not data or "results" not in data:
                continue
            for item in data["results"]:
                title = item.get("name", "")
                company_obj = item.get("company", {})
                company = company_obj.get("name", "") if isinstance(company_obj, dict) else ""
                locs = item.get("locations", [])
                location = ", ".join(
                    loc.get("name", "") for loc in locs if isinstance(loc, dict)
                ) or "Unknown"
                desc = item.get("contents", "")
                url = item.get("refs", {}).get("landing_page", "")
                pub_date = item.get("publication_date", "")

                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                # Relevance filter
                text = f"{title} {desc} {company}".lower()
                if not any(kw in text for kw in keywords):
                    continue

                # Strip HTML from description
                import re
                clean_desc = re.sub(r"<[^>]+>", " ", desc)[:500]

                date_found = pub_date or datetime.now(timezone.utc).isoformat()

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    description=clean_desc,
                    apply_url=url,
                    source=self.name,
                    date_found=date_found,
                ))

        logger.info(f"TheMuse: found {len(jobs)} relevant jobs")
        return jobs
