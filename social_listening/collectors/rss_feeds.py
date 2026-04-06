"""
RSS / Atom feed collector for industry publications.

Parses standard RSS 2.0 and Atom 1.0 feeds from attractions, museum,
ski, and live-entertainment trade publications. No API key required.
"""

import logging
import urllib.request
import urllib.error
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

from ..config import RSS_FEEDS, RSS_ARTICLE_LIMIT

logger = logging.getLogger(__name__)

USER_AGENT = "accesso-social-listening-agent/1.0 (market intelligence)"

# XML namespaces encountered in RSS / Atom feeds
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}


def _safe_text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_date(raw: str) -> str:
    """Parse RFC-2822 (RSS) or ISO-8601 (Atom) date strings into ISO format."""
    if not raw:
        return datetime.utcnow().isoformat()
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except Exception:
        return raw


def _fetch_feed(url: str) -> ET.Element | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
        return ET.fromstring(content)
    except urllib.error.HTTPError as e:
        logger.warning("HTTP %s fetching feed %s", e.code, url)
    except ET.ParseError as e:
        logger.warning("XML parse error for %s: %s", url, e)
    except Exception as e:
        logger.warning("Error fetching feed %s: %s", url, e)
    return None


def _parse_rss_channel(root: ET.Element, feed_meta: dict, limit: int) -> list[dict[str, Any]]:
    """Parse RSS 2.0 channel items."""
    items = root.findall(".//item")[:limit]
    signals = []
    for item in items:
        title = _safe_text(item.find("title"))
        link = _safe_text(item.find("link"))
        description = _safe_text(item.find("description"))
        # Prefer content:encoded if available (full article body)
        content_encoded = item.find("content:encoded", NS)
        body = _safe_text(content_encoded) if content_encoded is not None else description
        # Strip simple HTML tags from body (no external dep)
        body = _strip_html(body)[:3000]
        pub_date = _safe_text(item.find("pubDate"))
        author = _safe_text(item.find("author")) or _safe_text(item.find("dc:creator", NS))
        categories = [c.text for c in item.findall("category") if c.text]

        if not title and not link:
            continue

        signals.append(_make_signal(feed_meta, title, link, body, pub_date, author, categories))
    return signals


def _parse_atom_feed(root: ET.Element, feed_meta: dict, limit: int) -> list[dict[str, Any]]:
    """Parse Atom 1.0 entries."""
    entries = root.findall("atom:entry", NS)[:limit]
    signals = []
    for entry in entries:
        title_el = entry.find("atom:title", NS)
        title = _safe_text(title_el)
        # Link href in Atom
        link_el = entry.find("atom:link", NS)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = _safe_text(entry.find("atom:summary", NS))
        content_el = entry.find("atom:content", NS)
        body = _strip_html(_safe_text(content_el) if content_el is not None else summary)[:3000]
        pub_date = _safe_text(entry.find("atom:published", NS)) or _safe_text(
            entry.find("atom:updated", NS)
        )
        author_el = entry.find("atom:author/atom:name", NS)
        author = _safe_text(author_el)
        categories = [
            c.get("term", "") for c in entry.findall("atom:category", NS) if c.get("term")
        ]

        if not title and not link:
            continue

        signals.append(_make_signal(feed_meta, title, link, body, pub_date, author, categories))
    return signals


def _make_signal(
    feed_meta: dict, title: str, link: str, body: str, pub_date: str, author: str, categories: list
) -> dict[str, Any]:
    return {
        "source": "rss",
        "source_id": link or title,
        "publication": feed_meta["name"],
        "market": feed_meta["market"],
        "url": link,
        "title": title,
        "body": body,
        "author": author,
        "categories": categories,
        "collected_at": datetime.utcnow().isoformat(),
        "published_at": _parse_date(pub_date),
        "raw": {
            "feed_url": feed_meta["url"],
        },
    }


def _strip_html(text: str) -> str:
    """Very lightweight HTML tag stripper — avoids importing html.parser for simplicity."""
    import re
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all other tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect(
    feeds: list[dict] | None = None,
    limit: int = RSS_ARTICLE_LIMIT,
) -> list[dict[str, Any]]:
    """
    Collect articles from all configured RSS/Atom feeds.

    Args:
        feeds: Override the default feed list (list of dicts with name/url/market).
        limit: Max articles per feed.

    Returns:
        List of normalized signal dicts.
    """
    feeds = feeds or RSS_FEEDS
    signals = []

    for feed_meta in feeds:
        logger.info("Fetching RSS feed: %s", feed_meta["name"])
        root = _fetch_feed(feed_meta["url"])
        if root is None:
            continue

        # Detect RSS 2.0 vs Atom 1.0
        tag = root.tag.lower()
        if "feed" in tag or root.tag == "{http://www.w3.org/2005/Atom}feed":
            feed_signals = _parse_atom_feed(root, feed_meta, limit)
        else:
            feed_signals = _parse_rss_channel(root, feed_meta, limit)

        signals.extend(feed_signals)
        logger.info("  → %d articles from %s", len(feed_signals), feed_meta["name"])

    logger.info("RSS: collected %d signals from %d feeds", len(signals), len(feeds))
    return signals
