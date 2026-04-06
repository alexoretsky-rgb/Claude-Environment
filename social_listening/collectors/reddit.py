"""
Reddit collector — uses Reddit's public JSON API (no OAuth required).

Reddit exposes any subreddit listing as JSON by appending `.json` to the URL.
Rate limit: ~1 request/second for unauthenticated requests.
We identify ourselves via a descriptive User-Agent as required by Reddit's API rules.
"""

import time
import logging
import urllib.request
import urllib.error
import json
from datetime import datetime
from typing import Any

from ..config import REDDIT_SUBREDDITS, REDDIT_POST_LIMIT, PAIN_POINT_KEYWORDS, PRODUCT_KEYWORDS

logger = logging.getLogger(__name__)

# Reddit requires a descriptive User-Agent for API access
USER_AGENT = "accesso-social-listening-agent/1.0 (market intelligence; contact@accesso.com)"

# Subreddits most likely to contain operator/professional signal vs. consumer noise
OPERATOR_SIGNAL_SUBREDDITS = {
    "eventprofs", "SaaS", "b2bsales", "hospitality", "smallbusiness", "entrepreneur"
}


def _fetch_subreddit_posts(subreddit: str, limit: int = 25, sort: str = "new") -> list[dict[str, Any]]:
    """Fetch posts from a subreddit using the public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        posts = data.get("data", {}).get("children", [])
        return [p["data"] for p in posts if p.get("kind") == "t3"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("Reddit rate limit hit for r/%s — waiting 60s", subreddit)
            time.sleep(60)
        else:
            logger.warning("HTTP %s fetching r/%s: %s", e.code, subreddit, e)
        return []
    except Exception as e:
        logger.warning("Error fetching r/%s: %s", subreddit, e)
        return []


def _is_relevant(post: dict[str, Any]) -> bool:
    """Quick pre-filter: does this post touch any tracked keywords?"""
    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    all_keywords = PAIN_POINT_KEYWORDS + PRODUCT_KEYWORDS
    return any(kw.lower() in text for kw in all_keywords)


def collect(
    subreddits: list[str] | None = None,
    limit: int = REDDIT_POST_LIMIT,
    sort: str = "new",
    filter_relevant: bool = False,
) -> list[dict[str, Any]]:
    """
    Collect posts from configured subreddits.

    Args:
        subreddits: Override the default subreddit list.
        limit: Posts per subreddit.
        sort: Reddit sort order — "new", "hot", "top".
        filter_relevant: If True, drop posts that don't match any tracked keyword
                         before returning (reduces noise, but may miss edge cases).

    Returns:
        List of normalized signal dicts ready for storage/analysis.
    """
    subreddits = subreddits or REDDIT_SUBREDDITS
    signals = []

    for subreddit in subreddits:
        logger.info("Collecting r/%s (%s, limit=%d)", subreddit, sort, limit)
        posts = _fetch_subreddit_posts(subreddit, limit=limit, sort=sort)

        for post in posts:
            if filter_relevant and not _is_relevant(post):
                continue

            # Normalize into a common signal schema
            signals.append({
                "source": "reddit",
                "source_id": post.get("id", ""),
                "subreddit": subreddit,
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "title": post.get("title", ""),
                "body": post.get("selftext", "")[:2000],  # cap at 2K chars
                "author": post.get("author", "[deleted]"),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0.0),
                "flair": post.get("link_flair_text", ""),
                "is_operator_community": subreddit in OPERATOR_SIGNAL_SUBREDDITS,
                "collected_at": datetime.utcnow().isoformat(),
                "published_at": datetime.utcfromtimestamp(
                    post.get("created_utc", 0)
                ).isoformat(),
                "raw": {
                    "subreddit": post.get("subreddit", ""),
                    "domain": post.get("domain", ""),
                    "is_self": post.get("is_self", True),
                    "over_18": post.get("over_18", False),
                },
            })

        # Respect Reddit's rate limit between subreddits
        time.sleep(1.1)

    logger.info("Reddit: collected %d signals from %d subreddits", len(signals), len(subreddits))
    return signals
