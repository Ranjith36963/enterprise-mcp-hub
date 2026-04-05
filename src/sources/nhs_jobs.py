import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource

logger = logging.getLogger("job360.sources.nhs_jobs")

class NHSJobsSource(BaseJobSource):
    """UK NHS Jobs via XML API."""
    name = "nhs_jobs"

    async def fetch_jobs(self) -> list[Job]:
        if not self.search_queries:
            logger.info("NHS Jobs: no search queries configured, skipping")
            return []
        jobs = []
        seen_ids: set[str] = set()

        queries = self.search_queries[:5]  # Cap to avoid rate limits
        for query in queries:
            xml_text = await self._get_text(
                "https://www.jobs.nhs.uk/api/v1/search_xml",
                params={"keywords": query, "page": "1"},
            )
            if not xml_text:
                continue
            for job in self._parse_xml(xml_text):
                key = job.apply_url
                if key not in seen_ids:
                    seen_ids.add(key)
                    jobs.append(job)

        logger.info(f"NHS Jobs: found {len(jobs)} relevant jobs")
        return jobs

    def _parse_xml(self, xml_text: str) -> list[Job]:
        jobs = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"NHS Jobs: XML parse error: {e}")
            return []

        # NHS API uses <vacancyDetails> not <vacancy>
        for vacancy in root.iter("vacancyDetails"):
            title = (vacancy.findtext("title") or "").strip()
            employer = (vacancy.findtext("employer") or "").strip()
            location = (vacancy.findtext("locations") or "").strip()
            salary = (vacancy.findtext("salary") or "").strip()
            close_date = (vacancy.findtext("closeDate") or "").strip()
            post_date = (vacancy.findtext("postDate") or "").strip()
            reference = (vacancy.findtext("reference") or "").strip()
            url = (vacancy.findtext("url") or "").strip()
            description = (vacancy.findtext("description") or "").strip()
            job_type = (vacancy.findtext("type") or "").strip()

            text = f"{title} {description} {salary}".lower()
            if not self._relevance_match(text):
                continue

            apply_url = url or f"https://beta.jobs.nhs.uk/candidate/jobadvert/{reference}"

            salary_min, salary_max = self._parse_salary(salary)
            date_found = self._parse_date(post_date or close_date)

            jobs.append(Job(
                title=title,
                company=employer or "NHS",
                location=location or "UK",
                description=description or f"{title} - {salary}" if salary else title,
                apply_url=apply_url,
                source=self.name,
                date_found=date_found,
                salary_min=salary_min,
                salary_max=salary_max,
            ))

        return jobs

    @staticmethod
    def _parse_salary(salary_str: str) -> tuple:
        if not salary_str:
            return None, None
        import re
        # Handle hourly rates like "£45.00 to £70.00"
        nums = re.findall(r"[\d,.]+", salary_str)
        parsed = []
        for n in nums:
            try:
                val = float(n.replace(",", ""))
                if val >= 10000:
                    parsed.append(val)  # Annual
                elif val >= 5:
                    parsed.append(val * 1760)  # Hourly -> annual
            except ValueError:
                continue
        if len(parsed) >= 2:
            return float(min(parsed)), float(max(parsed))
        if len(parsed) == 1:
            return float(parsed[0]), None
        return None, None

    @staticmethod
    def _parse_date(date_str: str) -> str:
        if not date_str:
            return datetime.now(timezone.utc).isoformat()
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(date_str.strip()[:26], fmt)
                return dt.isoformat()
            except ValueError:
                continue
        return datetime.now(timezone.utc).isoformat()
