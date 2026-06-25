import os
import sys
import json
import time
import threading
import subprocess
import pika
from dotenv import load_dotenv
from connections import get_rabbit_connection

load_dotenv()

HEARTBEAT_QUEUE = "heartbeat_queue"

# Tuning knobs
DEAD_AFTER = 9          # seconds without a heartbeat => worker considered dead
CHECK_INTERVAL = 3      # how often the monitor checks the registry
MIN_WORKERS = 2         # keep at least this many workers alive

# Registry: worker_id -> last heartbeat timestamp
last_seen = {}
lock = threading.Lock()
respawn_count = 0


def connect():
    return get_rabbit_connection()


def consume_heartbeats():
    """Background thread: update last_seen whenever a heartbeat arrives."""
    conn = connect()
    ch = conn.channel()
    ch.queue_declare(queue=HEARTBEAT_QUEUE, durable=True)

    def on_heartbeat(ch, method, properties, body):
        msg = json.loads(body)
        with lock:
            last_seen[msg["worker_id"]] = msg["timestamp"]
        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=50)
    ch.basic_consume(queue=HEARTBEAT_QUEUE, on_message_callback=on_heartbeat)
    ch.start_consuming()


def spawn_worker():
    """Start a fresh worker process as a replacement."""
    global respawn_count
    respawn_count += 1
    new_id = f"respawned-{respawn_count}"
    print(f"[monitor] Spawning replacement worker: {new_id}")
    # Launch 'python worker.py <new_id>' as a detached background process
    subprocess.Popen([sys.executable, "worker.py", new_id])
    # Pre-register it so we don't immediately spawn again before its first heartbeat
    with lock:
        last_seen[new_id] = time.time()


def monitor_loop():
    print(
        f"[monitor] Started. DEAD_AFTER={DEAD_AFTER}s, MIN_WORKERS={MIN_WORKERS}")
    while True:
        time.sleep(CHECK_INTERVAL)
        now = time.time()
        with lock:
            alive = []
            dead = []
            for wid, ts in list(last_seen.items()):
                if now - ts <= DEAD_AFTER:
                    alive.append(wid)
                else:
                    dead.append(wid)
            # Drop dead workers from the registry
            for wid in dead:
                del last_seen[wid]

        if dead:
            print(f"[monitor] Detected DEAD workers: {dead}")
        print(f"[monitor] Alive workers ({len(alive)}): {alive}")

        # Maintain the minimum pool size
        while len(alive) < MIN_WORKERS:
            spawn_worker()
            alive.append("(pending)")


if __name__ == "__main__":
    # Heartbeat consumer runs in the background; monitor loop runs in the foreground
    t = threading.Thread(target=consume_heartbeats, daemon=True)
    t.start()
    monitor_loop()
