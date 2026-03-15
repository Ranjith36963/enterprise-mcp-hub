"""DevITJobs — European tech job board with free API.

No API key needed. JSON API.
Covers: developer/IT jobs across Europe.
URL: https://devitjobs.com/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_relevance_keywords

logger = logging.getLogger("job360.sources.devitjobs")


class DevITJobsSource(BaseJobSource):
    name = "devitjobs"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        keywords = get_relevance_keywords()
        data = await self._get_json("https://devitjobs.com/api/jobsLight")
        if not data or not isinstance(data, list):
            return []
        for item in data:
            title = item.get("title", "")
            company = item.get("companyName", "")
            desc = item.get("description", "")
            text = f"{title} {desc} {company}".lower()
            if not any(kw in text for kw in keywords):
                continue
            url = item.get("url", "")
            if not url:
                slug = item.get("slug", "")
                url = f"https://devitjobs.com/jobs/{slug}" if slug else ""
            if not url:
                continue
            sal_min = item.get("salaryFrom")
            sal_max = item.get("salaryTo")
            try:
                sal_min = float(sal_min) if sal_min else None
                sal_max = float(sal_max) if sal_max else None
            except (ValueError, TypeError):
                sal_min = sal_max = None
            location = item.get("cityName", "") or item.get("country", "") or "Europe"
            date_found = item.get("createdAt", "") or datetime.now(timezone.utc).isoformat()
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
        logger.info(f"DevITJobs: found {len(jobs)} relevant jobs")
        return jobs
