import os
import json
import uuid
import time
import datetime
from decimal import Decimal
import threading
import pika
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv
from connections import get_db_connection, get_rabbit_connection

load_dotenv()

TASK_QUEUE = "task_queue"

SOURCES = ["adzuna", "remoteok", "weworkremotely"]


def jsonable(rows):
    """Convert DB rows into JSON-safe dicts (dates -> strings, Decimals -> floats)."""
    clean = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
        clean.append(d)
    return clean


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


def publish_tasks(keyword, location, search_id, deadline_ts):
    conn = get_rabbit_connection()
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


def fetch_results_for_source(search_id, source):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT title, company, location, skills, salary_min, salary_max,
               job_type, experience_level, posted_date, source, url
        FROM jobs WHERE search_id = %s AND source = %s
    """, (search_id, source))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_all_results(search_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT title, company, location, skills, salary_min, salary_max,
               job_type, experience_level, posted_date, source, url
        FROM jobs WHERE search_id = %s ORDER BY source
    """, (search_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_completed_sources(search_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT source FROM task_status WHERE search_id = %s", (search_id,))
    done = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()
    return done


def jsonable(rows):
    """Convert DB rows into JSON-safe dicts (dates -> strings, Decimals -> floats)."""
    clean = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
        clean.append(d)
    return clean


def run_search(keyword, location, deadline_seconds, search_id):
    """Background task: publish work, then emit a socket event each time a
    source finishes, and a final event at completion or deadline."""
    deadline_ts = time.time() + deadline_seconds
    socketio.emit("search_started", {
        "search_id": search_id, "keyword": keyword, "location": location,
        "deadline_seconds": deadline_seconds, "sources": SOURCES,
    })

    publish_tasks(keyword, location, search_id, deadline_ts)

    emitted = set()
    while time.time() < deadline_ts and len(emitted) < len(SOURCES):
        done = get_completed_sources(search_id)
        new_sources = done - emitted
        for source in new_sources:
            jobs = fetch_results_for_source(search_id, source)
            socketio.emit("source_done", {
                "search_id": search_id, "source": source,
                "count": len(jobs), "jobs": jsonable(jobs),
            })
            emitted.add(source)
        if len(emitted) >= len(SOURCES):
            break
        socketio.sleep(0.3)

    all_results = fetch_all_results(search_id)
    socketio.emit("search_complete", {
        "search_id": search_id,
        "total_results": len(all_results),
        "completed_sources": sorted(emitted),
        "complete": len(emitted) == len(SOURCES),
    })


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(force=True)
    keyword = data.get("keyword", "").strip()
    location = data.get("location", "").strip()
    deadline_seconds = float(data.get("deadline", 10))
    if not keyword:
        return jsonify({"error": "keyword is required"}), 400

    search_id = str(uuid.uuid4())[:8]
    # Run the search in the background so the HTTP call returns immediately;
    # results stream to the client over the socket.
    socketio.start_background_task(
        run_search, keyword, location, deadline_seconds, search_id)
    return jsonify({"search_id": search_id, "status": "started"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@socketio.on("connect")
def on_connect():
    print("[api] client connected")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port,
                 debug=False, allow_unsafe_werkzeug=True)
