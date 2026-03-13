"""USAJobs — US federal government job board.

Free API with registration key (free, instant).
Covers: all US federal government positions — IT, engineering, science, admin, etc.
URL: https://developer.usajobs.gov/
"""

import logging
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_search_queries, get_search_locations

logger = logging.getLogger("job360.sources.usajobs")


class USAJobsSource(BaseJobSource):
    name = "usajobs"

    def __init__(self, session: aiohttp.ClientSession, api_key: str = "", email: str = ""):
        super().__init__(session)
        self._api_key = api_key
        self._email = email

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._email)

    async def fetch_jobs(self) -> list[Job]:
        if not self.is_configured:
            logger.info("USAJobs: no API key/email, skipping")
            return []
        jobs = []
        headers = {
            "Authorization-Key": self._api_key,
            "User-Agent": self._email,
            "Host": "data.usajobs.gov",
        }
        queries = get_search_queries(limit=3)
        for query in queries:
            params = {
                "Keyword": query,
                "ResultsPerPage": 50,
                "DatePosted": 7,
            }
            # Add location if US-based
            locations = get_search_locations()
            for loc in locations:
                if loc.lower() in ("remote", "us", "usa", "united states"):
                    if loc.lower() == "remote":
                        params["RemoteIndicator"] = "True"
                    break

            data = await self._get_json(
                "https://data.usajobs.gov/api/Search",
                params=params,
                headers=headers,
            )
            if not data:
                continue
            results = data.get("SearchResult", {}).get("SearchResultItems", [])
            for item in results:
                match = item.get("MatchedObjectDescriptor", {})
                title = match.get("PositionTitle", "")
                org = match.get("OrganizationName", "")
                desc = match.get("QualificationSummary", "")
                url = match.get("PositionURI", "")
                locations_list = match.get("PositionLocation", [])
                location = ", ".join(
                    loc.get("CityName", "") + " " + loc.get("CountrySubDivisionCode", "")
                    for loc in locations_list[:3]
                ).strip() or "USA"
                # Salary
                sal = match.get("PositionRemuneration", [{}])
                sal_min = None
                sal_max = None
                if sal:
                    sal_min = sal[0].get("MinimumRange")
                    sal_max = sal[0].get("MaximumRange")
                    try:
                        sal_min = float(sal_min) if sal_min else None
                        sal_max = float(sal_max) if sal_max else None
                    except (ValueError, TypeError):
                        sal_min = sal_max = None
                pub_date = match.get("PublicationStartDate", "") or datetime.now(timezone.utc).isoformat()
                jobs.append(Job(
                    title=title,
                    company=org,
                    location=location,
                    salary_min=sal_min,
                    salary_max=sal_max,
                    description=desc,
                    apply_url=url,
                    source=self.name,
                    date_found=pub_date,
                ))
        logger.info(f"USAJobs: found {len(jobs)} jobs")
        return jobs
