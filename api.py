import os
import json
import uuid
import time
import pika
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

RABBIT_HOST = os.getenv("RABBIT_HOST", "localhost")
RABBIT_PORT = int(os.getenv("RABBIT_PORT", 5672))
RABBIT_USER = os.getenv("RABBIT_USER", "hiremap")
RABBIT_PASS = os.getenv("RABBIT_PASS", "hiremap_pass")
TASK_QUEUE = "task_queue"

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

SOURCES = ["adzuna", "remoteok", "weworkremotely"]

app = Flask(__name__)
CORS(app)  # allow the React frontend to call this API


def publish_tasks(keyword, location, search_id, deadline_ts):
    """Publish one task per source, tagged with search_id and deadline."""
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST, port=RABBIT_PORT, credentials=creds)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)
    for source in SOURCES:
        task = {
            "source": source, "keyword": keyword, "location": location,
            "search_id": search_id, "deadline": deadline_ts,
        }
        ch.basic_publish(
            exchange="", routing_key=TASK_QUEUE, body=json.dumps(task),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    conn.close()


def fetch_results(search_id):
    """Read all jobs stored so far for this search_id."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT title, company, location, skills, salary_min, salary_max,
               job_type, experience_level, posted_date, source
        FROM jobs WHERE search_id = %s ORDER BY source
    """, (search_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def wait_for_completion(search_id, deadline_ts):
    """Poll the task_status table until all sources report done for this search_id,
    or until the deadline passes. Returns the set of completed source names."""
    completed = set()
    while time.time() < deadline_ts and len(completed) < len(SOURCES):
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT source FROM task_status WHERE search_id = %s", (search_id,))
        completed = set(row[0] for row in cur.fetchall())
        cur.close()
        conn.close()
        if len(completed) >= len(SOURCES):
            break
        time.sleep(0.3)
    return completed


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(force=True)
    keyword = data.get("keyword", "").strip()
    location = data.get("location", "").strip()
    deadline_seconds = float(data.get("deadline", 10))  # default 10s SLA

    if not keyword:
        return jsonify({"error": "keyword is required"}), 400

    search_id = str(uuid.uuid4())[:8]
    deadline_ts = time.time() + deadline_seconds

    publish_tasks(keyword, location, search_id, deadline_ts)

    # Wait until the deadline OR until all sources report completion, whichever comes first.
    completed_sources = wait_for_completion(search_id, deadline_ts)

    # Deadline (or early completion) reached: return whatever has landed
    results = fetch_results(search_id)
    sources_with_data = sorted(set(r["source"] for r in results))
    return jsonify({
        "search_id": search_id,
        "keyword": keyword,
        "location": location,
        "deadline_seconds": deadline_seconds,
        "total_results": len(results),
        # sources that FINISHED (even if 0 jobs)
        "completed_sources": sorted(completed_sources),
        "sources_with_data": sources_with_data,           # sources that returned >=1 job
        "complete": len(completed_sources) == len(SOURCES),
        "results": results,
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
