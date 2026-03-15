"""Relocate.me — jobs with relocation support.

Free JSON API, no key needed.
Covers: tech jobs globally that offer visa sponsorship / relocation packages.
URL: https://relocate.me/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_relevance_keywords

logger = logging.getLogger("job360.sources.relocate_me")


class RelocateMeSource(BaseJobSource):
    name = "relocate_me"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        keywords = get_relevance_keywords()
        data = await self._get_json("https://relocate.me/api/jobs")
        if not data or not isinstance(data, list):
            # Try alternative endpoint
            data_wrapper = await self._get_json("https://relocate.me/api/v1/jobs")
            if data_wrapper and isinstance(data_wrapper, dict):
                data = data_wrapper.get("data", data_wrapper.get("jobs", []))
            elif data_wrapper and isinstance(data_wrapper, list):
                data = data_wrapper
            else:
                return []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("position", "")
            company = item.get("company", "") or item.get("company_name", "")
            if isinstance(company, dict):
                company = company.get("name", "")
            desc = item.get("description", "")
            location = item.get("location", "") or item.get("city", "")
            if isinstance(location, dict):
                location = location.get("name", "")
            url = item.get("url", "") or item.get("apply_url", "")
            if not url:
                slug = item.get("slug", item.get("id", ""))
                url = f"https://relocate.me/jobs/{slug}" if slug else ""
            if not url:
                continue

            # Relevance filter
            text = f"{title} {desc} {company}".lower()
            if not any(kw in text for kw in keywords):
                continue

            date_found = item.get("published_at", "") or item.get("created_at", "") or datetime.now(timezone.utc).isoformat()
            jobs.append(Job(
                title=title,
                company=company,
                location=location,
                description=desc[:500] if desc else "",
                apply_url=url,
                source=self.name,
                date_found=date_found,
            ))
        logger.info(f"RelocateMe: found {len(jobs)} relevant jobs")
        return jobs
