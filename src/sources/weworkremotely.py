"""We Work Remotely — one of the largest remote job boards.

Free RSS feed, no API key needed.
Covers: programming, design, marketing, devops, business, customer support.
URL: https://weworkremotely.com/
"""

import logging
import re
from datetime import datetime, timezone

import aiohttp

from src.models import Job
from src.sources.base import BaseJobSource
from src.filters.skill_matcher import get_relevance_keywords

logger = logging.getLogger("job360.sources.weworkremotely")

# RSS categories to fetch
_CATEGORIES = [
    "programming",
    "design",
    "devops-sysadmin",
    "business",
    "customer-support",
    "marketing",
    "product",
]

# Simple regex to parse RSS items (avoid xml dependency)
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_FIELD_RE = {
    "title": re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>", re.DOTALL),
    "link": re.compile(r"<link>(.*?)</link>"),
    "company": re.compile(r"<company><!\[CDATA\[(.*?)\]\]></company>", re.DOTALL),
    "pubDate": re.compile(r"<pubDate>(.*?)</pubDate>"),
    "description": re.compile(r"<description><!\[CDATA\[(.*?)\]\]></description>", re.DOTALL),
}


def _extract_field(item_xml: str, field: str) -> str:
    match = _FIELD_RE.get(field, re.compile("")).search(item_xml)
    if match:
        return match.group(1).strip()
    # Fallback: try without CDATA
    fallback = re.search(rf"<{field}>(.*?)</{field}>", item_xml, re.DOTALL)
    return fallback.group(1).strip() if fallback else ""


class WeWorkRemotelySource(BaseJobSource):
    name = "weworkremotely"

    async def fetch_jobs(self) -> list[Job]:
        jobs = []
        seen_urls: set[str] = set()
        keywords = get_relevance_keywords()

        for category in _CATEGORIES:
            url = f"https://weworkremotely.com/categories/{category}.rss"
            xml = await self._get_text(url)
            if not xml:
                continue
            for item_match in _ITEM_RE.finditer(xml):
                item_xml = item_match.group(1)
                title = _extract_field(item_xml, "title")
                link = _extract_field(item_xml, "link")
                company = _extract_field(item_xml, "company")
                desc = _extract_field(item_xml, "description")
                pub_date = _extract_field(item_xml, "pubDate")

                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                # Relevance filter
                text = f"{title} {desc} {company}".lower()
                if not any(kw in text for kw in keywords):
                    continue

                # Parse date
                date_found = datetime.now(timezone.utc).isoformat()
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        date_found = parsedate_to_datetime(pub_date).isoformat()
                    except Exception:
                        pass

                # Strip HTML from description
                clean_desc = re.sub(r"<[^>]+>", " ", desc)[:500]

                jobs.append(Job(
                    title=title,
                    company=company,
                    location="Remote",
                    description=clean_desc,
                    apply_url=link,
                    source=self.name,
                    date_found=date_found,
                ))

        logger.info(f"WeWorkRemotely: found {len(jobs)} relevant jobs")
        return jobs
