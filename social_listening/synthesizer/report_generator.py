"""
Report synthesizer — combines all analysis results into a decision-ready weekly briefing.

The synthesizer's job is to:
1. Pull the week's pain points, themes, competitor insights, and prospect language from the DB
2. Ask Claude to rank, deduplicate, and surface the highest-signal items
3. Generate concrete content/campaign opportunities
4. Produce a structured report dict that the dashboard can display

Streaming is used here because the synthesis prompt produces long output.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import anthropic

from ..config import (
    ANALYSIS_MODEL,
    REPORT_LOOKBACK_DAYS,
    TOP_N_THEMES,
    TOP_N_PAIN_POINTS,
    TOP_N_OPPORTUNITIES,
    TOP_N_COMPETITOR_INSIGHTS,
)
from ..prompts.system_prompt import SYSTEM_PROMPT
from ..prompts.analysis_prompts import opportunity_synthesis_prompt
from ..analyzers.claude_analyzer import _parse_json_response

logger = logging.getLogger(__name__)


def _deduplicate_and_rank(
    client: anthropic.Anthropic,
    items: list[dict],
    item_type: str,
    top_n: int,
) -> list[dict]:
    """
    Ask Claude to deduplicate, merge, and rank a list of analysis results.
    Returns the top N most impactful items.
    """
    if not items:
        return []

    if len(items) <= top_n:
        return items

    import json
    prompt = f"""You have {len(items)} {item_type} extracted from this week's social listening data.
Many may be duplicates or variations of the same underlying issue.

{item_type.upper()} LIST:
{json.dumps(items, indent=2)[:12000]}

Please:
1. Merge near-duplicate {item_type} into single, stronger entries
2. Rank by: specificity, actionability, and B2B market intelligence value
3. Return the top {top_n} most valuable, deduplicated {item_type}

Return the result as a JSON array with the same schema as the input items.
Preserve all fields. Do not truncate or add commentary. Return only the JSON array."""

    try:
        with client.messages.stream(
            model=ANALYSIS_MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            text = ""
            for chunk in stream.text_stream:
                text += chunk

        results = _parse_json_response(text)
        return results[:top_n]

    except anthropic.APIError as e:
        logger.error("Dedup/rank call failed for %s: %s", item_type, e)
        return items[:top_n]


def _generate_executive_summary(
    client: anthropic.Anthropic,
    pain_points: list[dict],
    themes: list[dict],
    competitor_insights: list[dict],
    opportunities: list[dict],
    signal_count: int,
    date_range: str,
) -> str:
    """Generate a 3–5 sentence executive summary of the week's intelligence."""
    import json
    prompt = f"""Write a concise executive summary (3–5 sentences) of this week's social listening intelligence for accesso leadership.

Date range: {date_range}
Signals analyzed: {signal_count}

Top pain points:
{json.dumps([p.get('pain_point', '') for p in pain_points[:5]], indent=2)}

Top themes:
{json.dumps([t.get('theme', '') for t in themes[:5]], indent=2)}

Competitor highlights:
{json.dumps([c.get('context', '') for c in competitor_insights[:3]], indent=2)}

Top opportunities:
{json.dumps([o.get('title', '') for o in opportunities[:3]], indent=2)}

The summary should:
- Lead with the biggest market movement or opportunity
- Note any urgent competitive signals
- End with the highest-priority action for the week
- Sound like a briefing to a CMO or VP of Product

Return only the summary text — no headers, no bullet points, no JSON."""

    try:
        with client.messages.stream(
            model=ANALYSIS_MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            return "".join(chunk for chunk in stream.text_stream).strip()
    except anthropic.APIError as e:
        logger.error("Summary generation failed: %s", e)
        return "Summary unavailable due to API error."


def generate_report(
    db,  # Database instance — avoid circular import
    lookback_days: int = REPORT_LOOKBACK_DAYS,
    run_id: int | None = None,
) -> dict[str, Any]:
    """
    Generate a complete weekly intelligence report.

    Args:
        db: Database instance with analysis results stored
        lookback_days: How many days of analysis to include
        run_id: Associate report with a specific run (optional)

    Returns:
        Report dict ready for storage and dashboard display.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Date range for this report
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)
    date_range = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"

    logger.info("Generating report for %s", date_range)

    # Pull latest analysis results from DB
    if run_id:
        analyses = db.get_analyses_for_run(run_id)
    else:
        analyses = {
            "pain_points": db.get_latest_analysis("pain_points"),
            "themes": db.get_latest_analysis("themes"),
            "competitor_insights": db.get_latest_analysis("competitor_insights"),
            "prospect_language": db.get_latest_analysis("prospect_language"),
        }

    pain_points_raw = analyses.get("pain_points", [])
    themes_raw = analyses.get("themes", [])
    competitor_insights_raw = analyses.get("competitor_insights", [])
    prospect_language_raw = analyses.get("prospect_language", [])

    # Signal count
    relevant_signals = db.get_relevant_signals(since_days=lookback_days)
    signal_count = len(relevant_signals)

    logger.info(
        "Report inputs: %d pain points, %d themes, %d competitor insights, %d language patterns, %d relevant signals",
        len(pain_points_raw), len(themes_raw), len(competitor_insights_raw),
        len(prospect_language_raw), signal_count,
    )

    # Deduplicate and rank each analysis type
    logger.info("Deduplicating and ranking pain points")
    pain_points = _deduplicate_and_rank(client, pain_points_raw, "pain_points", TOP_N_PAIN_POINTS)

    logger.info("Deduplicating and ranking themes")
    themes = _deduplicate_and_rank(client, themes_raw, "themes", TOP_N_THEMES)

    logger.info("Deduplicating and ranking competitor insights")
    competitor_insights = _deduplicate_and_rank(
        client, competitor_insights_raw, "competitor_insights", TOP_N_COMPETITOR_INSIGHTS
    )

    # Generate opportunities from synthesized data
    logger.info("Generating content and campaign opportunities")
    try:
        with client.messages.stream(
            model=ANALYSIS_MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": opportunity_synthesis_prompt(
                    pain_points, themes, competitor_insights, prospect_language_raw[:10]
                ),
            }],
        ) as stream:
            opp_text = "".join(chunk for chunk in stream.text_stream)
        opportunities = _parse_json_response(opp_text)[:TOP_N_OPPORTUNITIES]
    except anthropic.APIError as e:
        logger.error("Opportunity generation failed: %s", e)
        opportunities = []

    # Generate executive summary
    logger.info("Generating executive summary")
    summary = _generate_executive_summary(
        client, pain_points, themes, competitor_insights, opportunities,
        signal_count, date_range,
    )

    report = {
        "report_type": "weekly",
        "title": f"accesso Market Intelligence Briefing — {date_range}",
        "summary": summary,
        "pain_points": pain_points,
        "themes": themes,
        "competitor_insights": competitor_insights,
        "prospect_language": prospect_language_raw[:15],  # Top 15 language patterns
        "opportunities": opportunities,
        "signal_count": signal_count,
        "date_range_start": start_date.isoformat(),
        "date_range_end": end_date.isoformat(),
        "generated_at": end_date.isoformat(),
    }

    logger.info(
        "Report generated: %d pain points, %d themes, %d opportunities",
        len(pain_points), len(themes), len(opportunities),
    )
    return report
