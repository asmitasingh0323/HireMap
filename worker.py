import os
import sys
import json
import time
import threading
import pika
from dotenv import load_dotenv
from fetchers import FETCHERS
from db_utils import save_jobs, record_task_status
from connections import get_rabbit_connection

load_dotenv()

TASK_QUEUE = "task_queue"

# Each worker gets an ID so we can see which one did what
WORKER_ID = sys.argv[1] if len(sys.argv) > 1 else f"worker-{os.getpid()}"


def connect():
    return get_rabbit_connection()


HEARTBEAT_QUEUE = "heartbeat_queue"
HEARTBEAT_INTERVAL = 3  # seconds between heartbeats


def start_heartbeat():
    """Background thread: publishes a heartbeat for this worker every few seconds."""
    conn = get_rabbit_connection()
    ch = conn.channel()
    ch.queue_declare(queue=HEARTBEAT_QUEUE, durable=True)
    while True:
        msg = {"worker_id": WORKER_ID, "timestamp": time.time()}
        try:
            ch.basic_publish(
                exchange="", routing_key=HEARTBEAT_QUEUE, body=json.dumps(msg)
            )
        except Exception as e:
            print(f"[{WORKER_ID}] heartbeat error: {e}")
            break
        time.sleep(HEARTBEAT_INTERVAL)


def process_task(ch, method, properties, body):
    task = json.loads(body)
    source = task["source"]
    keyword = task.get("keyword")
    location = task.get("location")
    search_id = task.get("search_id", "manual")

    print(f"[{WORKER_ID}] Received task: source={source}, keyword={keyword}, location={location}")
    start = time.time()

    try:
        fetch_fn = FETCHERS.get(source)
        if not fetch_fn:
            print(f"[{WORKER_ID}] Unknown source '{source}', discarding task.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        jobs = fetch_fn(keyword=keyword, location=location)
        inserted, skipped = save_jobs(jobs, search_id)
        duration = round(time.time() - start, 2)
        print(f"[{WORKER_ID}] DONE source={source}: fetched={len(jobs)}, "
              f"inserted={inserted}, skipped_dupes={skipped}, time={duration}s")

        # Record task completion in the DB (even if 0 jobs found) so the API knows this source finished.
        # ON CONFLICT keeps it idempotent if a task is ever retried.
        record_task_status(search_id, source, WORKER_ID, len(jobs), inserted)

        # ACK only after data is safely saved — this is the fault-tolerance guarantee
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[{WORKER_ID}] ERROR on source={source}: {e}")
        # ACK gracefully so a failing source doesn't requeue forever (per your report 4)
        ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    # Skip heartbeat in the cloud (no local monitor there; saves a RabbitMQ connection)
    if os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true":
        hb_thread = threading.Thread(target=start_heartbeat, daemon=True)
        hb_thread.start()

    print(f"[{WORKER_ID}] connecting to RabbitMQ...", flush=True)
    conn = connect()
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)
    print(f"[{WORKER_ID}] connected, queue declared", flush=True)

    # Fair dispatch: don't give a worker a new task until it ACKs the current one
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=TASK_QUEUE, on_message_callback=process_task)

    print(f"[{WORKER_ID}] Waiting for tasks. Press CTRL+C to exit.", flush=True)
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        print(f"[{WORKER_ID}] Shutting down.", flush=True)
        ch.stop_consuming()
    except Exception as e:
        import traceback
        print(f"[{WORKER_ID}] CONSUME LOOP ERROR: {e}", flush=True)
        traceback.print_exc()
    conn.close()


if __name__ == "__main__":
    main()
