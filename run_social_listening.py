#!/usr/bin/env python3
"""
accesso Social Listening Agent — CLI Runner

Usage:
  python run_social_listening.py collect              # Collect signals from all sources
  python run_social_listening.py analyze              # Analyze stored unscored signals
  python run_social_listening.py report               # Generate weekly intelligence report
  python run_social_listening.py run                  # Full pipeline: collect → analyze → report
  python run_social_listening.py stats                # Show database statistics
  python run_social_listening.py --help               # Show all options

Options:
  --sources reddit,rss,youtube,web    Comma-separated source list (default: all)
  --no-batch                          Use synchronous scoring (slower, no batch API)
  --lookback-days N                   Days to look back for report (default: 7)
  --db PATH                           Custom database path
  --log-level DEBUG|INFO|WARNING      Log verbosity (default: INFO)
  --dry-run                           Collect but don't save to DB (preview mode)

Environment variables required:
  ANTHROPIC_API_KEY    — Claude API key (required for analyze/report steps)
  YOUTUBE_API_KEY      — YouTube Data API v3 key (optional; skipped if absent)

Example cron (weekly, Mondays at 6 AM UTC):
  0 6 * * 1 cd /path/to/project && python run_social_listening.py run >> logs/social_listening.log 2>&1
"""

import argparse
import logging
import os
import sys
from datetime import datetime


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_collect(args, db) -> int:
    """Collect signals from specified sources and store in DB."""
    from social_listening.collectors import reddit, rss_feeds, youtube, web_search

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    logger = logging.getLogger("runner.collect")

    run_id = db.start_run(sources)
    logger.info("Started collection run #%d for sources: %s", run_id, sources)

    all_signals = []
    error = None

    try:
        if "reddit" in sources:
            logger.info("=== Collecting Reddit ===")
            signals = reddit.collect()
            all_signals.extend(signals)
            logger.info("Reddit: %d signals", len(signals))

        if "rss" in sources:
            logger.info("=== Collecting RSS Feeds ===")
            signals = rss_feeds.collect()
            all_signals.extend(signals)
            logger.info("RSS: %d signals", len(signals))

        if "youtube" in sources:
            logger.info("=== Collecting YouTube ===")
            signals = youtube.collect()
            all_signals.extend(signals)
            logger.info("YouTube: %d signals", len(signals))

        if "web" in sources or "web_search" in sources:
            logger.info("=== Collecting Web Search ===")
            signals = web_search.collect()
            all_signals.extend(signals)
            logger.info("Web search: %d signals", len(signals))

    except Exception as e:
        error = str(e)
        logger.exception("Collection error: %s", e)

    if args.dry_run:
        logger.info("DRY RUN: Would save %d signals (not saving)", len(all_signals))
        for sig in all_signals[:5]:
            logger.info("  Sample: [%s] %s", sig.get("source"), sig.get("title", "")[:80])
        db.fail_run(run_id, "dry_run")
        return 0

    # Save to DB
    saved = db.save_signals(all_signals, run_id=run_id)
    if error:
        db.fail_run(run_id, error)
    else:
        db.complete_run(run_id, signals_collected=len(all_signals), signals_relevant=0)

    logger.info("Saved %d new signals (run #%d)", saved, run_id)
    return run_id


def cmd_analyze(args, db) -> None:
    """Score and analyze unscored signals."""
    from social_listening.analyzers.claude_analyzer import (
        score_relevance_sync, score_relevance_batch,
        extract_pain_points, extract_themes,
        analyze_competitors, extract_prospect_language,
    )
    from social_listening.config import RELEVANCE_THRESHOLD, ANALYSIS_MODEL

    logger = logging.getLogger("runner.analyze")

    # Get unscored signals
    unscored = db.get_unscored_signals(limit=500)
    logger.info("Found %d unscored signals to score", len(unscored))

    if not unscored:
        logger.info("No unscored signals — nothing to analyze")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Score relevance
    logger.info("Scoring relevance (%s)...", "batch" if not args.no_batch else "sync")
    if args.no_batch:
        scores = score_relevance_sync(client, unscored)
    else:
        scores = score_relevance_batch(client, unscored)

    # Update DB with scores
    db.batch_update_relevance(scores, threshold=RELEVANCE_THRESHOLD)
    relevant_count = sum(1 for _, score in scores if score >= RELEVANCE_THRESHOLD)
    logger.info("Scored %d signals: %d relevant", len(scores), relevant_count)

    # Get all relevant signals for deep analysis
    lookback = getattr(args, "lookback_days", 7)
    relevant = db.get_relevant_signals(since_days=lookback)
    logger.info("Running deep analysis on %d relevant signals", len(relevant))

    if not relevant:
        logger.warning("No relevant signals found — skipping deep analysis")
        return

    run_id = None  # Analysis not tied to a specific run here

    # Pain points
    pain_points, tokens = extract_pain_points(client, relevant)
    db.save_analysis("pain_points", pain_points, run_id=run_id, model=ANALYSIS_MODEL,
                     signal_count=len(relevant), tokens_used=tokens)
    logger.info("Saved %d pain points", len(pain_points))

    # Themes
    themes, tokens = extract_themes(client, relevant)
    db.save_analysis("themes", themes, run_id=run_id, model=ANALYSIS_MODEL,
                     signal_count=len(relevant), tokens_used=tokens)
    logger.info("Saved %d themes", len(themes))

    # Competitor insights
    competitor_insights, tokens = analyze_competitors(client, relevant)
    db.save_analysis("competitor_insights", competitor_insights, run_id=run_id,
                     model=ANALYSIS_MODEL, signal_count=len(relevant), tokens_used=tokens)
    logger.info("Saved %d competitor insights", len(competitor_insights))

    # Prospect language
    prospect_language, tokens = extract_prospect_language(client, relevant)
    db.save_analysis("prospect_language", prospect_language, run_id=run_id,
                     model=ANALYSIS_MODEL, signal_count=len(relevant), tokens_used=tokens)
    logger.info("Saved %d language patterns", len(prospect_language))


def cmd_report(args, db) -> None:
    """Generate and save a weekly intelligence report."""
    from social_listening.synthesizer.report_generator import generate_report

    logger = logging.getLogger("runner.report")
    lookback = getattr(args, "lookback_days", 7)

    logger.info("Generating weekly intelligence report (lookback: %d days)", lookback)
    report = generate_report(db, lookback_days=lookback)

    report_id = db.save_report(report)
    logger.info("Report #%d saved: %s", report_id, report["title"])

    # Print summary to stdout
    print("\n" + "=" * 70)
    print(report["title"])
    print("=" * 70)
    print(f"\nSIGNALS ANALYZED: {report['signal_count']}")
    print(f"\nEXECUTIVE SUMMARY:\n{report['summary']}")

    print(f"\nTOP PAIN POINTS ({len(report['pain_points'])}):")
    for i, pp in enumerate(report["pain_points"][:5], 1):
        print(f"  {i}. [{pp.get('category', '')}] {pp.get('pain_point', '')[:100]}")

    print(f"\nEMERGING THEMES ({len(report['themes'])}):")
    for t in report["themes"][:5]:
        print(f"  • {t.get('theme', '')} [{t.get('momentum', '')}]")

    print(f"\nOPPORTUNITIES ({len(report['opportunities'])}):")
    for o in report["opportunities"]:
        print(f"  [{o.get('priority', '').upper()}] {o.get('title', '')}")

    print("\n" + "=" * 70 + "\n")


def cmd_run(args, db) -> None:
    """Full pipeline: collect → analyze → report."""
    logger = logging.getLogger("runner.full")
    logger.info("Starting full social listening pipeline")

    run_id = cmd_collect(args, db)
    cmd_analyze(args, db)
    cmd_report(args, db)

    logger.info("Full pipeline complete")


def cmd_stats(args, db) -> None:
    """Show database statistics."""
    stats = db.get_stats()
    runs = db.get_recent_runs(5)
    reports = db.get_reports(3)

    print("\n=== accesso Social Listening — Stats ===\n")
    print(f"Total signals collected:  {stats['total_signals']}")
    print(f"Relevant signals:         {stats['relevant_signals']}")
    print(f"Total runs:               {stats['total_runs']}")
    print(f"Total reports:            {stats['total_reports']}")

    print("\nSignals by source:")
    for source, count in stats["signals_by_source"].items():
        print(f"  {source:<15} {count}")

    if stats.get("last_run"):
        print(f"\nLast run: {stats['last_run']['started_at']} [{stats['last_run']['status']}]")

    if runs:
        print("\nRecent runs:")
        for run in runs:
            status = run["status"]
            print(f"  #{run['id']} {run['started_at'][:19]} [{status}] "
                  f"{run['signals_collected']} signals")

    if reports:
        print("\nRecent reports:")
        for r in reports:
            print(f"  #{r['id']} {r['created_at'][:19]} — {r['title'][:60]}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="accesso Social Listening Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared options
    def add_common_args(p):
        p.add_argument("--db", default=None, help="Database file path")
        p.add_argument("--log-level", default="INFO", help="Log level")

    # collect
    p_collect = subparsers.add_parser("collect", help="Collect signals from sources")
    add_common_args(p_collect)
    p_collect.add_argument("--sources", default="reddit,rss,youtube,web",
                           help="Comma-separated sources (default: reddit,rss,youtube,web)")
    p_collect.add_argument("--dry-run", action="store_true",
                           help="Preview collection without saving")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze stored signals")
    add_common_args(p_analyze)
    p_analyze.add_argument("--no-batch", action="store_true",
                           help="Use sync scoring instead of Batch API")
    p_analyze.add_argument("--lookback-days", type=int, default=7)

    # report
    p_report = subparsers.add_parser("report", help="Generate intelligence report")
    add_common_args(p_report)
    p_report.add_argument("--lookback-days", type=int, default=7)

    # run (full pipeline)
    p_run = subparsers.add_parser("run", help="Full pipeline: collect + analyze + report")
    add_common_args(p_run)
    p_run.add_argument("--sources", default="reddit,rss,youtube,web")
    p_run.add_argument("--no-batch", action="store_true")
    p_run.add_argument("--lookback-days", type=int, default=7)
    p_run.add_argument("--dry-run", action="store_true")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show database statistics")
    add_common_args(p_stats)

    args = parser.parse_args()
    setup_logging(args.log_level)

    # Check required env vars for analyze/report steps
    if args.command in ("analyze", "report", "run"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ERROR: ANTHROPIC_API_KEY environment variable is required for this command.")
            print("  export ANTHROPIC_API_KEY=your-key-here")
            sys.exit(1)

    # Initialize database
    from social_listening.storage.database import Database
    db = Database(db_path=args.db)

    # Dispatch
    commands = {
        "collect": cmd_collect,
        "analyze": cmd_analyze,
        "report": cmd_report,
        "run": cmd_run,
        "stats": cmd_stats,
    }
    commands[args.command](args, db)


if __name__ == "__main__":
    main()
