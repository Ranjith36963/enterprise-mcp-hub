"""Python.org Jobs — official Python community job board.

Free RSS feed, no API key. Python-specific roles globally.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.models import Job
from src.sources.base import BaseJobSource, _sanitize_xml
from src.config.settings import MAX_DESCRIPTION_LENGTH

logger = logging.getLogger("job360.sources.pythonjobs")

FEED_URL = "https://www.python.org/jobs/feed/rss/"


class PythonJobsSource(BaseJobSource):
    """Python.org community job board via RSS."""
    name = "pythonjobs"

    async def fetch_jobs(self) -> list[Job]:
        xml_text = await self._get_text(FEED_URL)
        if not xml_text:
            return []

        jobs = self._parse_feed(xml_text)
        logger.info(f"Python.org Jobs: found {len(jobs)} relevant jobs")
        return jobs

    def _parse_feed(self, xml_text: str) -> list[Job]:
        jobs = []
        try:
            root = ET.fromstring(_sanitize_xml(xml_text))
        except ET.ParseError as e:
            logger.warning(f"Python.org Jobs: XML parse error: {e}")
            return []

        channel = root.find("channel")
        if channel is None:
            channel = root

        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            text = f"{title} {description}".lower()
            if not self._relevance_match(text):
                continue

            # Try to extract company from description
            company = "Python.org Jobs"

            date_found = self._parse_date(pub_date)

            jobs.append(Job(
                title=title,
                company=company,
                location="Remote",
                description=description[:MAX_DESCRIPTION_LENGTH],
                apply_url=link,
                source=self.name,
                date_found=date_found,
            ))

        return jobs

    @staticmethod
    def _parse_date(date_str: str) -> str:
        if not date_str:
            return datetime.now(timezone.utc).isoformat()
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(date_str.strip(), fmt).isoformat()
            except ValueError:
                continue
        return datetime.now(timezone.utc).isoformat()
