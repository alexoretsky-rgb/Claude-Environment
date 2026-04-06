"""
Web search collector — uses Claude's built-in web_search server-side tool.

This lets Claude search the live web for industry conversations, news, operator
discussions, and competitor mentions. Unlike scraping, Claude synthesizes the
results inline, so each search query produces a structured signal with Claude's
interpretation baked in.

Cost note: web_search uses claude-opus-4-6 API tokens. Budget accordingly.
Each query is a separate API call.
"""

import os
import logging
from datetime import datetime
from typing import Any

import anthropic

from ..config import WEB_SEARCH_QUERIES, WEB_SEARCH_RESULT_LIMIT, ANALYSIS_MODEL
from ..prompts.system_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_search_prompt(query: str) -> str:
    return f"""Search the web for: "{query}"

Focus on:
1. Recent discussions, articles, or forum posts from attractions operators, venue managers, museum professionals, ski resort operators, or live entertainment venue staff
2. Pain points, technology challenges, or vendor complaints mentioned by operators
3. Technology trends, new product launches, or competitor news
4. Industry analyst reports or surveys about venue technology

For each relevant result you find, extract:
- The key insight or pain point expressed
- Who is saying it (operator type, job role if visible)
- The source URL and publication date
- Any competitor names or product names mentioned

Return a structured JSON array with these fields for each result:
{{
  "insight": "...",        // the key finding in 1-2 sentences
  "speaker_type": "...",   // e.g. "attractions operator", "industry analyst", "venue manager"
  "pain_point": "...",     // the problem or challenge described (or null)
  "competitor_mentioned": "...",  // competitor name if mentioned (or null)
  "url": "...",
  "published_date": "...", // approximate date or "unknown"
  "relevance": 0.0         // 0.0 to 1.0: how relevant to B2B attractions technology buyers
}}

Return ONLY the JSON array, no other text. If no relevant results found, return [].
"""


def collect(
    queries: list[str] | None = None,
    limit: int = WEB_SEARCH_RESULT_LIMIT,
    client: anthropic.Anthropic | None = None,
) -> list[dict[str, Any]]:
    """
    Run web searches via Claude and collect structured signals.

    Args:
        queries: Override the default query list.
        limit: Max results to request per query (hint to Claude).
        client: Anthropic client (created if not provided).

    Returns:
        List of normalized signal dicts.
    """
    import json

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot run web search collection")
        return []

    client = client or anthropic.Anthropic(api_key=api_key)
    queries = queries or WEB_SEARCH_QUERIES
    signals = []

    for query in queries:
        logger.info("Web search: %r", query)
        try:
            response = client.messages.create(
                model=ANALYSIS_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[
                    {"type": "web_search_20260209", "name": "web_search"},
                ],
                messages=[{"role": "user", "content": _build_search_prompt(query)}],
            )

            # Extract text blocks from response (Claude returns JSON in text block)
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            # Parse JSON results
            text = text.strip()
            if text.startswith("["):
                results = json.loads(text)
            else:
                # Claude may wrap in markdown code block
                import re
                match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
                if match:
                    results = json.loads(match.group(1))
                else:
                    logger.warning("Could not parse web search results for query: %r", query)
                    continue

            for result in results[:limit]:
                if not isinstance(result, dict):
                    continue
                signals.append({
                    "source": "web_search",
                    "source_id": result.get("url", query),
                    "search_query": query,
                    "url": result.get("url", ""),
                    "title": result.get("insight", "")[:200],
                    "body": result.get("insight", ""),
                    "speaker_type": result.get("speaker_type", ""),
                    "pain_point": result.get("pain_point"),
                    "competitor_mentioned": result.get("competitor_mentioned"),
                    "relevance_score": float(result.get("relevance", 0.5)),
                    "collected_at": datetime.utcnow().isoformat(),
                    "published_at": result.get("published_date", "unknown"),
                    "raw": {"query": query},
                })

        except json.JSONDecodeError as e:
            logger.warning("JSON parse error for query %r: %s", query, e)
        except anthropic.APIError as e:
            logger.error("Anthropic API error during web search: %s", e)
        except Exception as e:
            logger.error("Unexpected error during web search for %r: %s", query, e)

    logger.info("Web search: collected %d signals from %d queries", len(signals), len(queries))
    return signals
