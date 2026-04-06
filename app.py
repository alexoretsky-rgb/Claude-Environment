import json
import os
import urllib.request
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# ─── Social Listening DB (lazy-loaded) ────────────────────────────────────────
_social_db = None

def get_social_db():
    global _social_db
    if _social_db is None:
        from social_listening.storage.database import Database
        _social_db = Database()
    return _social_db

POSTS_FILE = os.path.join(os.path.dirname(__file__), "posts.json")

MAKE_WEBHOOK_URL = "https://hook.us2.make.com/cu277bjgm47xwcrv1u597pnl7xyxf2ry"


def load_posts():
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/posts")
def get_posts():
    try:
        posts = load_posts()
        return jsonify(posts)
    except FileNotFoundError:
        return jsonify({"error": "posts.json not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "posts.json is not valid JSON"}), 400


@app.route("/api/send", methods=["POST"])
def send_email():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    post = data.get("post", "").strip()

    if not name or not email or not post:
        return jsonify({"error": "Missing required fields"}), 400

    body = (
        f"Hi {name},\n\n"
        "Below is your LinkedIn post draft for review. Please feel free to reach out if you would "
        "like any refinements or if there is anything I can do to make these feel more like you. "
        "Thank you!\n\n"
        "---\n\n"
        f"{post}"
    )

    payload = json.dumps({
        "recipients": [{"emailAddress": {"address": email}}],
        "email": email,
        "body": body
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            MAKE_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to send: {str(e)}"}), 500


# ─── Social Listening Dashboard Routes ────────────────────────────────────────

@app.route("/social")
def social_dashboard():
    return render_template("social_dashboard.html")


@app.route("/api/social/report")
def api_social_report():
    """Return the latest intelligence report as JSON."""
    try:
        db = get_social_db()
        report = db.get_latest_report()
        if not report:
            return jsonify({
                "error": "No reports yet. Run: python run_social_listening.py run"
            }), 404
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/stats")
def api_social_stats():
    """Return database statistics and recent run history."""
    try:
        db = get_social_db()
        stats = db.get_stats()
        stats["recent_runs"] = db.get_recent_runs(limit=5)
        stats["recent_reports"] = db.get_reports(limit=5)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/signals")
def api_social_signals():
    """Return recent relevant signals (paginated)."""
    try:
        db = get_social_db()
        lookback = int(request.args.get("days", 7))
        source = request.args.get("source")
        limit = min(int(request.args.get("limit", 50)), 200)

        sources = [source] if source else None
        signals = db.get_relevant_signals(since_days=lookback, sources=sources, limit=limit)
        return jsonify({"signals": signals, "count": len(signals)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/social/run", methods=["POST"])
def api_social_run():
    """
    Trigger a collection/analysis run in the background.

    POST body (JSON, all optional):
      { "sources": "reddit,rss", "steps": "collect,analyze,report" }

    Returns immediately with run_id. Check /api/social/stats for status.
    Note: For production, replace threading with Celery or a task queue.
    """
    import threading
    import subprocess
    import sys

    data = request.get_json() or {}
    sources = data.get("sources", "reddit,rss,youtube,web")
    steps = data.get("steps", "run")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({
            "error": "ANTHROPIC_API_KEY not set on server — cannot run analysis"
        }), 400

    def run_pipeline():
        cmd = [sys.executable, "run_social_listening.py", steps, "--sources", sources]
        try:
            subprocess.run(cmd, cwd=os.path.dirname(__file__), timeout=1800)
        except Exception as e:
            app.logger.error("Pipeline run failed: %s", e)

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "message": f"Pipeline '{steps}' started for sources: {sources}. Check /api/social/stats for progress.",
    })


if __name__ == "__main__":
    app.run(debug=True)
