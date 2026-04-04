import json
import os
import urllib.request
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

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

    payload = json.dumps({"email": email, "body": body}).encode("utf-8")

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


if __name__ == "__main__":
    app.run(debug=True)
