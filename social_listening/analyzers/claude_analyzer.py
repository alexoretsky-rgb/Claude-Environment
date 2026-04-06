"""
Claude-powered analysis engine.

Uses claude-opus-4-6 with:
- Adaptive thinking (for nuanced market intelligence)
- Prompt caching on the stable system prompt (~90% cost reduction on repeated calls)
- Batch API for relevance scoring (50% cheaper than synchronous calls)
- Streaming for long synthesis outputs

Architecture: all five analysis types (relevance, pain points, themes,
competitors, prospect language) go through the same _run_analysis() method,
which handles caching, retries, and token tracking consistently.
"""

import json
import logging
import os
import time
from typing import Any

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from ..config import (
    ANALYSIS_MODEL,
    CLASSIFICATION_MODEL,
    BATCH_SIZE,
    RELEVANCE_THRESHOLD,
    COMPETITORS,
)
from ..prompts.system_prompt import SYSTEM_PROMPT
from ..prompts.analysis_prompts import (
    relevance_filter_prompt,
    pain_point_extraction_prompt,
    theme_extraction_prompt,
    competitor_analysis_prompt,
    prospect_language_prompt,
)

logger = logging.getLogger(__name__)


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _parse_json_response(text: str) -> list[dict]:
    """Parse a JSON array from Claude's response text."""
    text = text.strip()
    # Strip markdown code fences if present
    import re
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    # Find the first [ ... ] block
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse JSON array from response: %s...", text[:200])
    return []


def _run_analysis(
    client: anthropic.Anthropic,
    user_prompt: str,
    model: str = ANALYSIS_MODEL,
    max_tokens: int = 8192,
    use_thinking: bool = True,
) -> tuple[list[dict], int]:
    """
    Run a single analysis call with prompt caching on the system prompt.

    Returns (results_list, total_tokens_used).

    Caching strategy:
    - The system prompt is large and never changes → cache it with ephemeral TTL
    - The user prompt changes every call (different signal batches) → no cache marker
    - Cache writes cost 1.25x but subsequent reads cost 0.1x → ROI after 2nd call
    """
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # Cache this stable block
                }
            ],
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if use_thinking and model == ANALYSIS_MODEL:
            kwargs["thinking"] = {"type": "adaptive"}

        response = client.messages.create(**kwargs)

        # Extract text from response
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        results = _parse_json_response(text)
        tokens = (
            response.usage.input_tokens
            + response.usage.output_tokens
            + getattr(response.usage, "cache_creation_input_tokens", 0)
        )

        logger.debug(
            "Analysis call: %d results, %d tokens (cache_read=%d)",
            len(results),
            tokens,
            getattr(response.usage, "cache_read_input_tokens", 0),
        )
        return results, tokens

    except anthropic.RateLimitError:
        logger.warning("Rate limit hit — waiting 60s before retry")
        time.sleep(60)
        return _run_analysis(client, user_prompt, model, max_tokens, use_thinking)
    except anthropic.APIError as e:
        logger.error("API error during analysis: %s", e)
        return [], 0


# ─── Relevance Scoring (uses Batch API for cost efficiency) ────────────────────

def score_relevance_batch(
    client: anthropic.Anthropic,
    signals: list[dict],
    threshold: float = RELEVANCE_THRESHOLD,
) -> list[tuple[int, float]]:
    """
    Score signals for relevance using the Batch API (50% cheaper).

    Splits signals into BATCH_SIZE chunks. Each chunk is one batch request.
    Returns list of (signal_db_id, score) tuples.

    Note: Batch API is asynchronous — we poll until completion.
    For large runs this could take minutes. That's acceptable for a
    background intelligence pipeline.
    """
    if not signals:
        return []

    # Split into chunks
    chunks = [signals[i : i + BATCH_SIZE] for i in range(0, len(signals), BATCH_SIZE)]
    all_scores: list[tuple[int, float]] = []

    for chunk_idx, chunk in enumerate(chunks):
        logger.info(
            "Scoring relevance chunk %d/%d (%d signals)",
            chunk_idx + 1, len(chunks), len(chunk),
        )

        # Build batch requests — one per chunk (each chunk asks to score multiple signals at once)
        requests = [
            Request(
                custom_id=f"relevance-chunk-{chunk_idx}",
                params=MessageCreateParamsNonStreaming(
                    model=CLASSIFICATION_MODEL,  # Haiku for cost efficiency on scoring
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": relevance_filter_prompt(chunk)}],
                ),
            )
        ]

        # Submit batch
        try:
            batch = client.messages.batches.create(requests=requests)
        except anthropic.APIError as e:
            logger.error("Batch creation failed: %s", e)
            continue

        # Poll for completion (max 10 min)
        max_wait = 600
        waited = 0
        while waited < max_wait:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            sleep_time = min(10, max_wait - waited)
            time.sleep(sleep_time)
            waited += sleep_time
            logger.debug("Batch %s: %s (waited %ds)", batch.id, batch.processing_status, waited)

        if batch.processing_status != "ended":
            logger.error("Batch %s timed out", batch.id)
            continue

        # Process results
        for result in client.messages.batches.results(batch.id):
            if result.result.type != "succeeded":
                logger.warning("Batch result %s failed: %s", result.custom_id, result.result)
                continue

            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            scores = _parse_json_response(text)

            for score_obj in scores:
                if not isinstance(score_obj, dict):
                    continue
                idx = score_obj.get("id")
                relevance = float(score_obj.get("relevance", 0.0))
                if idx is not None and 0 <= idx < len(chunk):
                    signal = chunk[idx]
                    db_id = signal.get("id")
                    if db_id is not None:
                        all_scores.append((int(db_id), relevance))

    return all_scores


def score_relevance_sync(
    client: anthropic.Anthropic,
    signals: list[dict],
    threshold: float = RELEVANCE_THRESHOLD,
) -> list[tuple[int, float]]:
    """
    Score signals synchronously (no Batch API).
    Use when you need results immediately (e.g., during interactive runs).
    """
    if not signals:
        return []

    chunks = [signals[i : i + BATCH_SIZE] for i in range(0, len(signals), BATCH_SIZE)]
    all_scores: list[tuple[int, float]] = []

    for chunk_idx, chunk in enumerate(chunks):
        logger.info("Scoring chunk %d/%d synchronously", chunk_idx + 1, len(chunks))
        results, _ = _run_analysis(
            client,
            relevance_filter_prompt(chunk),
            model=CLASSIFICATION_MODEL,
            max_tokens=2048,
            use_thinking=False,
        )
        for score_obj in results:
            if not isinstance(score_obj, dict):
                continue
            idx = score_obj.get("id")
            relevance = float(score_obj.get("relevance", 0.0))
            if idx is not None and 0 <= idx < len(chunk):
                db_id = chunk[idx].get("id")
                if db_id is not None:
                    all_scores.append((int(db_id), relevance))

    return all_scores


# ─── Deep Analysis Functions ───────────────────────────────────────────────────

def extract_pain_points(
    client: anthropic.Anthropic,
    signals: list[dict],
    run_id: int | None = None,
) -> tuple[list[dict], int]:
    """Extract structured pain points from relevant signals."""
    if not signals:
        return [], 0

    logger.info("Extracting pain points from %d signals", len(signals))
    chunks = [signals[i : i + BATCH_SIZE] for i in range(0, len(signals), BATCH_SIZE)]
    all_pain_points: list[dict] = []
    total_tokens = 0

    for chunk in chunks:
        results, tokens = _run_analysis(
            client,
            pain_point_extraction_prompt(chunk),
            max_tokens=8192,
        )
        all_pain_points.extend(results)
        total_tokens += tokens

    logger.info("Extracted %d pain points (%d tokens)", len(all_pain_points), total_tokens)
    return all_pain_points, total_tokens


def extract_themes(
    client: anthropic.Anthropic,
    signals: list[dict],
) -> tuple[list[dict], int]:
    """Identify emerging themes across all relevant signals."""
    if not signals:
        return [], 0

    logger.info("Extracting themes from %d signals", len(signals))
    # For themes, we want the model to see across all signals — use larger chunks
    chunk_size = min(50, len(signals))
    chunks = [signals[i : i + chunk_size] for i in range(0, len(signals), chunk_size)]
    all_themes: list[dict] = []
    total_tokens = 0

    for chunk in chunks:
        results, tokens = _run_analysis(
            client,
            theme_extraction_prompt(chunk),
            max_tokens=6144,
        )
        all_themes.extend(results)
        total_tokens += tokens

    logger.info("Extracted %d themes (%d tokens)", len(all_themes), total_tokens)
    return all_themes, total_tokens


def analyze_competitors(
    client: anthropic.Anthropic,
    signals: list[dict],
    competitors: list[str] = COMPETITORS,
) -> tuple[list[dict], int]:
    """Find and analyze competitor mentions across signals."""
    if not signals:
        return [], 0

    logger.info("Scanning %d signals for competitor mentions", len(signals))
    chunks = [signals[i : i + BATCH_SIZE] for i in range(0, len(signals), BATCH_SIZE)]
    all_mentions: list[dict] = []
    total_tokens = 0

    for chunk in chunks:
        results, tokens = _run_analysis(
            client,
            competitor_analysis_prompt(chunk, competitors),
            max_tokens=6144,
        )
        all_mentions.extend(results)
        total_tokens += tokens

    logger.info("Found %d competitor mentions (%d tokens)", len(all_mentions), total_tokens)
    return all_mentions, total_tokens


def extract_prospect_language(
    client: anthropic.Anthropic,
    signals: list[dict],
) -> tuple[list[dict], int]:
    """Extract the exact language prospects use to describe their challenges."""
    if not signals:
        return [], 0

    logger.info("Extracting prospect language from %d signals", len(signals))
    chunks = [signals[i : i + BATCH_SIZE] for i in range(0, len(signals), BATCH_SIZE)]
    all_phrases: list[dict] = []
    total_tokens = 0

    for chunk in chunks:
        results, tokens = _run_analysis(
            client,
            prospect_language_prompt(chunk),
            max_tokens=4096,
        )
        all_phrases.extend(results)
        total_tokens += tokens

    logger.info("Extracted %d language patterns (%d tokens)", len(all_phrases), total_tokens)
    return all_phrases, total_tokens


def run_full_analysis(
    signals: list[dict],
    run_id: int | None = None,
    use_batch_scoring: bool = True,
) -> dict[str, Any]:
    """
    Run the complete analysis pipeline on a set of signals.

    Steps:
    1. Score all signals for relevance (batch API)
    2. Filter to relevant signals
    3. Extract pain points, themes, competitor mentions, prospect language

    Returns a dict with all analysis results and token usage summary.
    """
    client = _get_client()

    # Step 1: Score relevance
    logger.info("Step 1/5: Scoring relevance for %d signals", len(signals))
    if use_batch_scoring:
        scores = score_relevance_batch(client, signals)
    else:
        scores = score_relevance_sync(client, signals)

    # Build score map
    score_map = {db_id: score for db_id, score in scores}

    # Step 2: Filter to relevant
    relevant = [
        s for s in signals
        if score_map.get(s.get("id", -1), 0.0) >= RELEVANCE_THRESHOLD
    ]
    logger.info("Step 2/5: %d/%d signals passed relevance threshold", len(relevant), len(signals))

    if not relevant:
        logger.warning("No relevant signals found — analysis complete with no results")
        return {
            "scores": scores,
            "relevant_count": 0,
            "pain_points": [],
            "themes": [],
            "competitor_insights": [],
            "prospect_language": [],
            "total_tokens": 0,
        }

    # Steps 3–6: Deep analysis (can run sequentially — each needs different signals subset)
    logger.info("Step 3/5: Extracting pain points")
    pain_points, t1 = extract_pain_points(client, relevant, run_id)

    logger.info("Step 4/5: Extracting themes")
    themes, t2 = extract_themes(client, relevant)

    logger.info("Step 5/5: Analyzing competitors + prospect language")
    competitor_insights, t3 = analyze_competitors(client, relevant)
    prospect_language, t4 = extract_prospect_language(client, relevant)

    total_tokens = t1 + t2 + t3 + t4

    return {
        "scores": scores,
        "relevant_count": len(relevant),
        "pain_points": pain_points,
        "themes": themes,
        "competitor_insights": competitor_insights,
        "prospect_language": prospect_language,
        "total_tokens": total_tokens,
    }
