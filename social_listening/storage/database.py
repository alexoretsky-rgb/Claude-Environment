"""
SQLite storage layer for the social listening agent.

Schema:
  signals     — raw collected content (Reddit posts, RSS articles, YouTube videos, web search hits)
  analyses    — Claude's structured analysis results (pain points, themes, etc.)
  reports     — synthesized weekly briefings
  runs        — collection run audit log

Design choice: SQLite is zero-dependency and perfectly adequate for the volume
we expect (hundreds to low thousands of signals per week). When scale demands it,
swap the connection string for PostgreSQL with minimal code changes.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default database location — sits next to the package, outside version control
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "social_listening.db"


class Database:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read performance
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS signals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    source          TEXT NOT NULL,          -- reddit, rss, youtube, web_search
                    source_id       TEXT,                   -- original ID from the source
                    url             TEXT,
                    title           TEXT,
                    body            TEXT,
                    author          TEXT,
                    published_at    TEXT,
                    collected_at    TEXT NOT NULL,
                    run_id          INTEGER,
                    relevance_score REAL DEFAULT NULL,      -- set after AI scoring
                    is_relevant     INTEGER DEFAULT NULL,   -- 1/0 after threshold filtering
                    metadata        TEXT DEFAULT '{}',      -- JSON blob for source-specific fields
                    UNIQUE(source, source_id)
                );

                CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
                CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at);
                CREATE INDEX IF NOT EXISTS idx_signals_relevant ON signals(is_relevant);
                CREATE INDEX IF NOT EXISTS idx_signals_run ON signals(run_id);

                CREATE TABLE IF NOT EXISTS analyses (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          INTEGER,
                    analysis_type   TEXT NOT NULL,  -- pain_points, themes, competitors, language, opportunities
                    results         TEXT NOT NULL,  -- JSON array of analysis objects
                    model           TEXT,
                    signal_count    INTEGER,
                    created_at      TEXT NOT NULL,
                    tokens_used     INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_analyses_run ON analyses(run_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_type ON analyses(analysis_type);

                CREATE TABLE IF NOT EXISTS reports (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          INTEGER,
                    report_type     TEXT DEFAULT 'weekly',
                    title           TEXT,
                    summary         TEXT,
                    pain_points     TEXT DEFAULT '[]',
                    themes          TEXT DEFAULT '[]',
                    competitor_insights TEXT DEFAULT '[]',
                    prospect_language   TEXT DEFAULT '[]',
                    opportunities   TEXT DEFAULT '[]',
                    signal_count    INTEGER DEFAULT 0,
                    date_range_start TEXT,
                    date_range_end  TEXT,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at      TEXT NOT NULL,
                    completed_at    TEXT,
                    status          TEXT DEFAULT 'running',  -- running, completed, failed
                    sources         TEXT DEFAULT '[]',       -- JSON list of sources collected
                    signals_collected INTEGER DEFAULT 0,
                    signals_relevant  INTEGER DEFAULT 0,
                    error_message   TEXT
                );
            """)
        logger.debug("Database schema initialized at %s", self.db_path)

    # ─── Run management ───────────────────────────────────────────────────────

    def start_run(self, sources: list[str]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at, sources, status) VALUES (?, ?, 'running')",
                (datetime.utcnow().isoformat(), json.dumps(sources)),
            )
            return cur.lastrowid

    def complete_run(self, run_id: int, signals_collected: int, signals_relevant: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE runs SET completed_at=?, status='completed',
                   signals_collected=?, signals_relevant=? WHERE id=?""",
                (datetime.utcnow().isoformat(), signals_collected, signals_relevant, run_id),
            )

    def fail_run(self, run_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET completed_at=?, status='failed', error_message=? WHERE id=?",
                (datetime.utcnow().isoformat(), error[:1000], run_id),
            )

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Signal storage ────────────────────────────────────────────────────────

    def save_signals(self, signals: list[dict[str, Any]], run_id: int | None = None) -> int:
        """Insert signals, skipping duplicates (source + source_id unique constraint)."""
        inserted = 0
        with self._connect() as conn:
            for signal in signals:
                # Separate known columns from extra metadata
                metadata = {
                    k: v for k, v in signal.items()
                    if k not in {"source", "source_id", "url", "title", "body", "author",
                                 "published_at", "collected_at"}
                }
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO signals
                           (source, source_id, url, title, body, author, published_at,
                            collected_at, run_id, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            signal.get("source", ""),
                            signal.get("source_id", signal.get("url", "")),
                            signal.get("url", ""),
                            signal.get("title", "")[:500],
                            signal.get("body", "")[:5000],
                            signal.get("author", ""),
                            signal.get("published_at", ""),
                            signal.get("collected_at", datetime.utcnow().isoformat()),
                            run_id,
                            json.dumps(metadata),
                        ),
                    )
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1
                except sqlite3.Error as e:
                    logger.warning("Failed to insert signal %s: %s", signal.get("url"), e)
        logger.info("Saved %d new signals (skipped %d duplicates)", inserted, len(signals) - inserted)
        return inserted

    def update_relevance(self, signal_id: int, score: float, threshold: float = 0.4) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE signals SET relevance_score=?, is_relevant=? WHERE id=?",
                (score, 1 if score >= threshold else 0, signal_id),
            )

    def batch_update_relevance(self, scores: list[tuple[int, float]], threshold: float = 0.4) -> None:
        """Update relevance scores for multiple signals at once."""
        with self._connect() as conn:
            conn.executemany(
                "UPDATE signals SET relevance_score=?, is_relevant=? WHERE id=?",
                [(score, 1 if score >= threshold else 0, sid) for sid, score in scores],
            )

    def get_unscored_signals(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM signals WHERE relevance_score IS NULL
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_relevant_signals(
        self,
        since_days: int = 7,
        sources: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Fetch relevant signals for analysis, optionally filtered by source."""
        cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat()
        with self._connect() as conn:
            if sources:
                placeholders = ",".join("?" * len(sources))
                rows = conn.execute(
                    f"""SELECT * FROM signals
                        WHERE is_relevant=1 AND collected_at >= ?
                        AND source IN ({placeholders})
                        ORDER BY collected_at DESC LIMIT ?""",
                    [cutoff, *sources, limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM signals
                       WHERE is_relevant=1 AND collected_at >= ?
                       ORDER BY collected_at DESC LIMIT ?""",
                    (cutoff, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_signals_for_run(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Analysis storage ──────────────────────────────────────────────────────

    def save_analysis(
        self,
        analysis_type: str,
        results: list[dict],
        run_id: int | None = None,
        model: str = "",
        signal_count: int = 0,
        tokens_used: int = 0,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO analyses
                   (run_id, analysis_type, results, model, signal_count, created_at, tokens_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, analysis_type, json.dumps(results), model, signal_count,
                 datetime.utcnow().isoformat(), tokens_used),
            )
            return cur.lastrowid

    def get_latest_analysis(self, analysis_type: str) -> list[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT results FROM analyses WHERE analysis_type=?
                   ORDER BY id DESC LIMIT 1""",
                (analysis_type,),
            ).fetchone()
            if row:
                return json.loads(row["results"])
            return []

    def get_analyses_for_run(self, run_id: int) -> dict[str, list]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT analysis_type, results FROM analyses WHERE run_id=?", (run_id,)
            ).fetchall()
            return {r["analysis_type"]: json.loads(r["results"]) for r in rows}

    # ─── Report storage ────────────────────────────────────────────────────────

    def save_report(self, report: dict, run_id: int | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO reports
                   (run_id, report_type, title, summary, pain_points, themes,
                    competitor_insights, prospect_language, opportunities,
                    signal_count, date_range_start, date_range_end, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    report.get("report_type", "weekly"),
                    report.get("title", ""),
                    report.get("summary", ""),
                    json.dumps(report.get("pain_points", [])),
                    json.dumps(report.get("themes", [])),
                    json.dumps(report.get("competitor_insights", [])),
                    json.dumps(report.get("prospect_language", [])),
                    json.dumps(report.get("opportunities", [])),
                    report.get("signal_count", 0),
                    report.get("date_range_start", ""),
                    report.get("date_range_end", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cur.lastrowid

    def get_latest_report(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            report = dict(row)
            for field in ["pain_points", "themes", "competitor_insights",
                          "prospect_language", "opportunities"]:
                report[field] = json.loads(report.get(field) or "[]")
            return report

    def get_reports(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, signal_count, created_at, report_type FROM reports ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Dashboard stats ───────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total_signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            relevant_signals = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE is_relevant=1"
            ).fetchone()[0]
            total_reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            sources = conn.execute(
                "SELECT source, COUNT(*) as count FROM signals GROUP BY source"
            ).fetchall()
            last_run = conn.execute(
                "SELECT started_at, status FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return {
                "total_signals": total_signals,
                "relevant_signals": relevant_signals,
                "total_reports": total_reports,
                "total_runs": total_runs,
                "signals_by_source": {r["source"]: r["count"] for r in sources},
                "last_run": dict(last_run) if last_run else None,
            }
