"""Source de veille générique : flux RSS/Atom.

Utilisée pour Product Hunt et les médias tech tunisiens. Parsing avec la
bibliothèque standard `xml.etree` : aucune dépendance supplémentaire, et pas de
paquet à surveiller pour les failles.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from ...domain.entities.trend import TrendItem, TrendOrigin
from ...domain.ports.search import TechSourcePort

logger = logging.getLogger(__name__)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_TAG_PATTERN = re.compile(r"<[^>]+>")

#: Flux par défaut, tous publics et gratuits.
DEFAULT_GLOBAL_FEEDS = (
    "https://www.producthunt.com/feed",
    "https://n8n.io/blog/rss.xml",
)


def _clean_html(text: str) -> str:
    return _TAG_PATTERN.sub("", text or "").replace("&nbsp;", " ").strip()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class RssSource(TechSourcePort):
    """Agrège un ou plusieurs flux RSS/Atom."""

    def __init__(
        self,
        feeds: tuple[str, ...] | list[str],
        *,
        origin: TrendOrigin = TrendOrigin.GLOBAL_TECH,
        label: str = "RSS",
        limit: int = 15,
        timeout_s: int = 20,
        user_agent: str = "blogseo/1.0",
    ) -> None:
        self.feeds = list(feeds)
        self.origin = origin
        self.name = label
        self.limit = limit
        self.timeout_s = timeout_s
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch(self, *, limit: int | None = None) -> list[TrendItem]:
        target = limit or self.limit
        items: list[TrendItem] = []
        for feed in self.feeds:
            items.extend(self._fetch_feed(feed))
        items.sort(key=lambda i: i.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        result = items[:target]
        logger.info("[%s] %s signal(aux) sur %s flux", self.name, len(result), len(self.feeds))
        return result

    def _fetch_feed(self, url: str) -> list[TrendItem]:
        try:
            response = self._session.get(url, timeout=self.timeout_s)
            if response.status_code >= 400:
                logger.warning("Flux %s → HTTP %s", url, response.status_code)
                return []
            root = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            logger.warning("Flux %s illisible : %s", url, exc)
            return []

        entries = root.findall(".//item")
        if entries:
            return [self._from_rss(e, url) for e in entries]
        return [self._from_atom(e, url) for e in root.findall("atom:entry", _ATOM_NS)]

    def _from_rss(self, entry, feed_url: str) -> TrendItem:
        def text(tag: str) -> str:
            node = entry.find(tag)
            return (node.text or "") if node is not None else ""

        return TrendItem(
            title=_clean_html(text("title")),
            url=text("link").strip() or feed_url,
            source=self._feed_label(feed_url),
            origin=self.origin,
            summary=_clean_html(text("description"))[:300],
            published_at=_parse_date(text("pubDate")),
        )

    def _from_atom(self, entry, feed_url: str) -> TrendItem:
        title_node = entry.find("atom:title", _ATOM_NS)
        link_node = entry.find("atom:link", _ATOM_NS)
        summary_node = entry.find("atom:summary", _ATOM_NS)
        updated_node = entry.find("atom:updated", _ATOM_NS)
        return TrendItem(
            title=_clean_html(title_node.text if title_node is not None else ""),
            url=(link_node.get("href") if link_node is not None else "") or feed_url,
            source=self._feed_label(feed_url),
            origin=self.origin,
            summary=_clean_html(summary_node.text if summary_node is not None else "")[:300],
            published_at=_parse_date(updated_node.text if updated_node is not None else None),
        )

    @staticmethod
    def _feed_label(url: str) -> str:
        return re.sub(r"^www\.", "", url.split("/")[2]) if "//" in url else url
