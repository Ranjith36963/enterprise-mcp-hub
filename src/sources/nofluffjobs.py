"""NoFluffJobs — European IT job board with transparent salaries.

Free JSON API, no key needed.
Covers: IT/tech jobs in Poland, Europe — with mandatory salary disclosure.
URL: https://nofluffjobs.com/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_relevance_keywords

logger = logging.getLogger("job360.sources.nofluffjobs")


class NoFluffJobsSource(BaseJobSource):
    name = "nofluffjobs"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        keywords = get_relevance_keywords()
        data = await self._get_json("https://nofluffjobs.com/api/posting")
        if not data:
            return []
        items = data if isinstance(data, list) else data.get("postings", data.get("data", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("name", "")
            company = item.get("company", "")
            if isinstance(company, dict):
                company = company.get("name", "")
            location = item.get("location", "")
            if isinstance(location, dict):
                places = location.get("places", [])
                location = ", ".join(
                    p.get("city", "") for p in places if isinstance(p, dict)
                ) if places else "Remote"
            elif isinstance(location, list):
                location = ", ".join(str(l) for l in location[:3])

            desc = item.get("technology", "")
            if isinstance(desc, list):
                desc = ", ".join(str(t) for t in desc)
            elif not isinstance(desc, str):
                desc = ""

            text = f"{title} {desc} {company}".lower()
            if not any(kw in text for kw in keywords):
                continue

            slug = item.get("url", "") or item.get("id", "")
            url = f"https://nofluffjobs.com/job/{slug}" if slug and not slug.startswith("http") else slug
            if not url:
                continue

            # Salary info (NoFluffJobs requires salary disclosure)
            salary = item.get("salary", {})
            sal_min = None
            sal_max = None
            if isinstance(salary, dict):
                sal_min = salary.get("from")
                sal_max = salary.get("to")
                try:
                    sal_min = float(sal_min) if sal_min else None
                    sal_max = float(sal_max) if sal_max else None
                except (ValueError, TypeError):
                    sal_min = sal_max = None

            date_found = item.get("posted", "") or item.get("renewed", "") or datetime.now(timezone.utc).isoformat()
            jobs.append(Job(
                title=title,
                company=company if isinstance(company, str) else "",
                location=location if isinstance(location, str) else "Europe",
                salary_min=sal_min,
                salary_max=sal_max,
                description=desc[:500],
                apply_url=url,
                source=self.name,
                date_found=date_found,
            ))
        logger.info(f"NoFluffJobs: found {len(jobs)} relevant jobs")
        return jobs
