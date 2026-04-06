"""
YouTube collector — uses the YouTube Data API v3.

Requires YOUTUBE_API_KEY environment variable (free, 10,000 quota units/day).
Each search costs 100 units; video detail lookups cost 1 unit each.
At the default settings (9 queries × 5 results), we use ~900 units/run.

If YOUTUBE_API_KEY is not set, collect() returns an empty list with a warning.
"""

import os
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import Any

from ..config import YOUTUBE_QUERIES, YOUTUBE_VIDEO_LIMIT

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def _get_api_key() -> str | None:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    return key if key else None


def _api_get(endpoint: str, params: dict, api_key: str) -> dict:
    """Make a GET request to the YouTube Data API."""
    params["key"] = api_key
    url = f"{YOUTUBE_API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "accesso-social-listening/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.warning("YouTube API HTTP %s: %s", e.code, body[:200])
        return {}
    except Exception as e:
        logger.warning("YouTube API error: %s", e)
        return {}


def _search_videos(query: str, max_results: int, api_key: str) -> list[str]:
    """Search YouTube and return a list of video IDs."""
    params = {
        "part": "id",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 50),
        "relevanceLanguage": "en",
        "order": "date",  # Most recent first for freshness
        "publishedAfter": "2023-01-01T00:00:00Z",  # Only recent content
    }
    data = _api_get("search", params, api_key)
    items = data.get("items", [])
    return [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]


def _get_video_details(video_ids: list[str], api_key: str) -> list[dict]:
    """Fetch snippet + statistics for a list of video IDs."""
    if not video_ids:
        return []
    params = {
        "part": "snippet,statistics",
        "id": ",".join(video_ids),
    }
    data = _api_get("videos", params, api_key)
    return data.get("items", [])


def collect(
    queries: list[str] | None = None,
    limit: int = YOUTUBE_VIDEO_LIMIT,
) -> list[dict[str, Any]]:
    """
    Search YouTube for relevant videos and collect their metadata.

    Args:
        queries: Override the default query list.
        limit: Max videos per query.

    Returns:
        List of normalized signal dicts, or [] if YOUTUBE_API_KEY is not set.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning(
            "YOUTUBE_API_KEY not set — skipping YouTube collection. "
            "Set this env var to enable YouTube signals."
        )
        return []

    queries = queries or YOUTUBE_QUERIES
    seen_ids: set[str] = set()
    signals = []

    for query in queries:
        logger.info("YouTube search: %r", query)
        video_ids = _search_videos(query, max_results=limit, api_key=api_key)

        # Deduplicate across queries
        new_ids = [vid for vid in video_ids if vid not in seen_ids]
        seen_ids.update(new_ids)

        if not new_ids:
            continue

        details = _get_video_details(new_ids, api_key)
        for video in details:
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            video_id = video.get("id", "")

            signals.append({
                "source": "youtube",
                "source_id": video_id,
                "search_query": query,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": snippet.get("title", ""),
                "body": snippet.get("description", "")[:2000],
                "channel": snippet.get("channelTitle", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "collected_at": datetime.utcnow().isoformat(),
                "published_at": snippet.get("publishedAt", ""),
                "raw": {
                    "channel_id": snippet.get("channelId", ""),
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                },
            })

    logger.info("YouTube: collected %d signals from %d queries", len(signals), len(queries))
    return signals
