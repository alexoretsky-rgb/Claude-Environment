"""
Task-specific analysis prompt templates.

Each function returns the user-turn content for a specific analysis task.
Dynamic data (signal text, batch contents) is injected here — NOT in the system prompt.
"""

import json
from typing import Any


def relevance_filter_prompt(signals: list[dict[str, Any]]) -> str:
    """Score a batch of signals for relevance to accesso's markets and use cases."""
    signals_text = json.dumps(
        [{"id": i, "title": s.get("title", ""), "body": (s.get("body", "") or "")[:500]}
         for i, s in enumerate(signals)],
        indent=2,
    )
    return f"""Score each of the following signals for relevance to accesso's B2B market intelligence needs.

Signals to evaluate:
{signals_text}

For each signal, return a JSON object with:
- "id": the signal index (integer)
- "relevance": float 0.0–1.0 (0 = completely irrelevant, 1.0 = highly actionable insight)
- "reason": one sentence explaining the score

Scoring guide:
- 0.8–1.0: Directly discusses operator pain points, technology decisions, competitor products, or market trends in accesso's verticals
- 0.5–0.8: Relates to the industry or technology space but may be tangential
- 0.2–0.5: Loosely related — could be industry-adjacent noise
- 0.0–0.2: Consumer complaint, off-topic, spam, or irrelevant

Return a JSON array of score objects. Example:
[{{"id": 0, "relevance": 0.85, "reason": "Attractions operator discussing ERP/POS replacement cycle."}}]
"""


def pain_point_extraction_prompt(signals: list[dict[str, Any]]) -> str:
    """Extract structured pain points from a batch of signals."""
    signals_text = "\n\n---\n\n".join(
        f"[{i}] SOURCE: {s.get('source', 'unknown')} | URL: {s.get('url', 'n/a')}\n"
        f"TITLE: {s.get('title', '')}\n"
        f"BODY: {(s.get('body', '') or '')[:800]}"
        for i, s in enumerate(signals)
    )
    return f"""Analyze these industry signals and extract specific operational pain points that operators in accesso's target markets are experiencing.

{signals_text}

For each distinct pain point identified, return a JSON object with:
- "pain_point": concise description of the problem (1–2 sentences, operator's perspective)
- "category": one of [ticketing, ecommerce, pos, queuing, analytics, data, staffing, revenue, guest_experience, technology_migration, compliance, integration, other]
- "market_segment": most relevant segment [attractions, museums, ski, live_entertainment, general_venues, all]
- "severity": estimated urgency [critical, high, medium, low]
- "operator_quote": the most compelling direct quote from the source, or null
- "source_url": the signal URL
- "accesso_relevance": how this connects to an accesso solution (1 sentence)
- "suggested_action": recommended action for accesso marketing, product, or sales (1 sentence)

Return a JSON array of pain point objects. Only include genuine pain points — skip generic complaints without actionable signal.
"""


def theme_extraction_prompt(signals: list[dict[str, Any]]) -> str:
    """Identify emerging themes and topics across a batch of signals."""
    signals_text = "\n\n---\n\n".join(
        f"[{i}] {s.get('source', '')} | {s.get('title', '')}\n{(s.get('body', '') or '')[:600]}"
        for i, s in enumerate(signals)
    )
    return f"""Identify the major emerging themes and topics across these industry signals.

{signals_text}

Return a JSON array where each object represents one theme:
- "theme": concise theme name (3–6 words)
- "description": what this theme is about and why it's emerging (2–3 sentences)
- "signal_count": estimated number of signals in this batch that touch this theme (integer)
- "momentum": [rising, stable, declining] — your assessment of trajectory
- "market_segments": list of segments where this theme is strongest
- "accesso_angle": how accesso could engage with this theme (content, product, sales)
- "example_quotes": up to 3 verbatim quotes or paraphrases from the signals

Return only the JSON array.
"""


def competitor_analysis_prompt(signals: list[dict[str, Any]], competitors: list[str]) -> str:
    """Extract competitor mentions and sentiment from signals."""
    competitor_list = ", ".join(competitors)
    signals_text = "\n\n---\n\n".join(
        f"[{i}] {s.get('source', '')} | {s.get('title', '')}\n{(s.get('body', '') or '')[:800]}"
        for i, s in enumerate(signals)
    )
    return f"""Scan these signals for mentions of accesso's competitors: {competitor_list}

Also flag any mentions of accesso itself.

{signals_text}

For each competitor mention found, return a JSON object:
- "competitor": competitor name as mentioned
- "mention_type": [positive, negative, neutral, comparison, feature_gap, pricing, contract_renewal]
- "context": what was said about this competitor (1–3 sentences)
- "operator_type": type of operator mentioning them, if discernible
- "competitive_insight": what accesso sales/product should know about this mention
- "source_url": URL of the signal
- "verbatim_quote": the most relevant direct quote, or null

Return a JSON array. If no competitor mentions are found, return [].
"""


def prospect_language_prompt(signals: list[dict[str, Any]]) -> str:
    """Extract the exact language prospects use to describe their challenges."""
    signals_text = "\n\n---\n\n".join(
        f"[{i}] {s.get('source', '')} | {s.get('title', '')}\n{(s.get('body', '') or '')[:600]}"
        for i, s in enumerate(signals)
    )
    return f"""Extract the exact language that operators and buyers in accesso's target markets use to describe their technology challenges, needs, and goals.

{signals_text}

This language will be used by accesso's marketing team for:
- Website copy and value proposition messaging
- Ad creative and LinkedIn content
- Sales email sequences
- Webinar and content titles

For each compelling phrase or pattern identified, return a JSON object:
- "phrase": the exact quote or close paraphrase
- "category": what this phrase expresses [pain_point, desired_outcome, buying_trigger, vendor_frustration, success_metric, technology_concern]
- "operator_voice": the type of person saying this (e.g., "attractions director of operations")
- "messaging_opportunity": how accesso could mirror this language in marketing materials (1 sentence)
- "channel": best channel for this message [linkedin, email, website, events, content]

Return a JSON array of the most impactful phrases only (not every phrase — prioritize specificity and authenticity).
"""


def opportunity_synthesis_prompt(
    pain_points: list[dict],
    themes: list[dict],
    competitor_insights: list[dict],
    prospect_language: list[dict],
) -> str:
    """Synthesize all analysis into concrete content and campaign opportunities."""
    context = json.dumps({
        "top_pain_points": pain_points[:10],
        "top_themes": themes[:8],
        "competitor_insights": competitor_insights[:8],
        "prospect_language_samples": prospect_language[:10],
    }, indent=2)

    return f"""Based on this week's social listening analysis, identify the highest-priority content and campaign opportunities for accesso's marketing, product marketing, and sales teams.

Analysis context:
{context}

For each opportunity, return a JSON object:
- "opportunity_type": [content_piece, campaign_angle, webinar_topic, product_positioning, sales_playbook, competitive_response, partner_story]
- "title": specific, actionable title for this opportunity (e.g., "Webinar: How Museums Are Solving Timed-Entry Chaos")
- "description": what this opportunity is and why it's timely (2–3 sentences)
- "priority": [urgent, high, medium] — based on momentum and competitive relevance
- "target_audience": internal team + external audience [e.g., "Marketing team → Museum directors of visitor experience"]
- "suggested_angle": the specific message or hook to lead with
- "evidence": 1–2 data points from the analysis supporting this opportunity
- "next_step": the immediate concrete action to take (1 sentence)

Return a JSON array, ordered by priority (urgent first). Limit to the 6 most compelling opportunities.
"""
