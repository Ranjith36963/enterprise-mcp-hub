"""Landing.jobs — European tech job board with free API.

Free JSON API, no key needed.
Covers: tech/engineering jobs across Europe, with visa/relocation info.
URL: https://landing.jobs/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_relevance_keywords

logger = logging.getLogger("job360.sources.landingjobs")


class LandingJobsSource(BaseJobSource):
    name = "landingjobs"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        keywords = get_relevance_keywords()
        data = await self._get_json("https://landing.jobs/api/v1/jobs?limit=100&offset=0")
        if not data:
            return []
        items = data if isinstance(data, list) else data.get("data", data.get("jobs", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("name", "")
            company = item.get("company", "")
            if isinstance(company, dict):
                company = company.get("name", "")
            desc = item.get("description", "")
            location = item.get("city", "") or item.get("location", "")
            url = item.get("url", "") or item.get("apply_url", "")
            if not url:
                slug = item.get("slug", item.get("id", ""))
                url = f"https://landing.jobs/job/{slug}" if slug else ""
            if not url:
                continue

            text = f"{title} {desc} {company}".lower()
            if not any(kw in text for kw in keywords):
                continue

            sal_min = item.get("salary_from") or item.get("gross_salary_low")
            sal_max = item.get("salary_to") or item.get("gross_salary_high")
            try:
                sal_min = float(sal_min) if sal_min else None
                sal_max = float(sal_max) if sal_max else None
            except (ValueError, TypeError):
                sal_min = sal_max = None

            date_found = item.get("published_at", "") or item.get("created_at", "") or datetime.now(timezone.utc).isoformat()
            jobs.append(Job(
                title=title,
                company=company,
                location=location,
                salary_min=sal_min,
                salary_max=sal_max,
                description=desc[:500] if desc else "",
                apply_url=url,
                source=self.name,
                date_found=date_found,
            ))
        logger.info(f"LandingJobs: found {len(jobs)} relevant jobs")
        return jobs
