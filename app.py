import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

POSTS_FILE = os.path.join(os.path.dirname(__file__), "posts.json")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


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

    sender_email = os.environ.get("OUTLOOK_EMAIL")
    sender_password = os.environ.get("OUTLOOK_APP_PASSWORD")

    if not sender_email or not sender_password:
        return jsonify({
            "error": "Server is missing OUTLOOK_EMAIL or OUTLOOK_APP_PASSWORD environment variables."
        }), 500

    subject = "Your LinkedIn Post for Review"

    body = (
        f"Hi {name},\n\n"
        "Below is your LinkedIn post draft for review. Please feel free to reach out if you would "
        "like any refinements or if there is anything I can do to make these feel more like you. "
        "Thank you!\n\n"
        "---\n\n"
        f"{post}"
    )

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, email, msg.as_string())
        return jsonify({"success": True})
    except smtplib.SMTPAuthenticationError:
        return jsonify({
            "error": "Authentication failed. Check your OUTLOOK_EMAIL and OUTLOOK_APP_PASSWORD."
        }), 401
    except smtplib.SMTPException as e:
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
