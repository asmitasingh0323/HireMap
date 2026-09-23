import os
import sys
import json
import time
import threading
import pika
from dotenv import load_dotenv
from db_utils import (save_jobs, record_task_status, ensure_schema,
                      expire_stale_jobs, jobs_needing_interpretation,
                      save_interpretation, jobs_to_recheck, record_url_check)
from liveness import check_jobs
from interpreter import interpret_job, ModelError, model_is_available
from connections import get_rabbit_connection
from adapters import get_adapter

load_dotenv()

# Two queues, because the two kinds of work have very different speeds.
# Crawls and freshness checks take seconds and a person is waiting for them;
# reading a description with the model takes up to a minute. Sharing one
# queue meant a dashboard search waited behind the model. They are separate
# now, so slow AI work can never delay a search.
TASK_QUEUE = "task_queue"              # crawls, freshness
INTERPRET_QUEUE = "interpret_queue"    # model work only

# Each worker gets an ID so we can see which one did what
WORKER_ID = sys.argv[1] if len(sys.argv) > 1 else f"worker-{os.getpid()}"

# "python worker.py ai-1 --interpret" runs a worker that ONLY does model work
INTERPRET_ONLY = "--interpret" in sys.argv


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

    task_type = task.get("type", "crawl")
    print(f"[{WORKER_ID}] Received {task_type} task: source={source}, "
          f"keyword={keyword}, location={location}")
    start = time.time()

    try:
        if task_type == "freshness":
            # Freshness check: no fetching, just retire listings this source
            # has stopped showing in its crawls.
            expired = expire_stale_jobs(source=source)
            duration = round(time.time() - start, 2)
            print(f"[{WORKER_ID}] DONE freshness source={source}: "
                  f"expired={expired}, time={duration}s")
            record_task_status(search_id, f"{source}-freshness", WORKER_ID,
                               0, expired)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        if task_type == "liveness":
            # Ask the source whether each stored link still exists. Requests
            # are spaced by that source's own rate limit, inside check_jobs.
            batch = int(task.get("batch", 5))
            jobs = jobs_to_recheck(source, limit=batch)
            live, gone, unknown = check_jobs(
                jobs, source,
                on_result=lambda job, verdict, code:
                    record_url_check(job["fingerprint"], verdict, code))
            duration = round(time.time() - start, 2)
            print(f"[{WORKER_ID}] DONE liveness source={source}: "
                  f"checked={len(jobs)}, live={live}, gone={gone}, "
                  f"unclear={unknown}, time={duration}s")
            record_task_status(search_id, f"{source}-liveness", WORKER_ID,
                               len(jobs), gone)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        if task_type == "interpret":
            # Interpretation: no fetching either. Take jobs that have a
            # description but no decoded fields, and run the model on them.
            batch = int(task.get("batch", 5))
            jobs = jobs_needing_interpretation(limit=batch, source=source)
            done = failed = 0
            for job in jobs:
                try:
                    result = interpret_job(job)
                    save_interpretation(
                        job["fingerprint"], result["skills"],
                        result["seniority"], result["work_arrangement"],
                        result["model"],
                        preferred_skills=result.get("preferred_skills"),
                        salary_min=result.get("salary_min"),
                        salary_max=result.get("salary_max"),
                        salary_basis=result.get("salary_basis"))
                    done += 1
                except ModelError as e:
                    # A job the model cannot read must not stop the batch.
                    print(f"[{WORKER_ID}]   skipped '{job['title']}': {e}")
                    failed += 1
            duration = round(time.time() - start, 2)
            print(f"[{WORKER_ID}] DONE interpret source={source}: "
                  f"interpreted={done}, failed={failed}, time={duration}s")
            record_task_status(search_id, f"{source}-interpret", WORKER_ID,
                               len(jobs), done)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        adapter = get_adapter(source)
        if not adapter:
            print(f"[{WORKER_ID}] Unknown source '{source}', discarding task.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # collect() = fetch from the source, then normalize the fields
        jobs = adapter.collect(keyword=keyword, location=location)
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
        # Keep only the first part of the message; the URL part contains API keys
        short_error = str(e).split(" for url:")[0]
        print(f"[{WORKER_ID}] ERROR on source={source}: {short_error}")
        # Still mark this source as finished (with the error) so the API
        # doesn't wait for it until the deadline.
        try:
            record_task_status(search_id, source, WORKER_ID,
                               0, 0, error=short_error)
        except Exception as db_err:
            print(f"[{WORKER_ID}] could not record failure: {db_err}")
        # ACK so a failing source doesn't requeue forever
        ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    # Make sure the database has every column this code writes to
    ensure_schema()

    # Skip heartbeat in the cloud (no local monitor there; saves a RabbitMQ connection)
    if os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true":
        hb_thread = threading.Thread(target=start_heartbeat, daemon=True)
        hb_thread.start()

    queue_name = INTERPRET_QUEUE if INTERPRET_ONLY else TASK_QUEUE
    role = "interpretation only" if INTERPRET_ONLY else "crawls and freshness"

    print(f"[{WORKER_ID}] connecting to RabbitMQ...", flush=True)
    conn = connect()
    ch = conn.channel()
    # Declare both, so whichever worker starts first creates them
    ch.queue_declare(queue=TASK_QUEUE, durable=True)
    ch.queue_declare(queue=INTERPRET_QUEUE, durable=True)
    print(f"[{WORKER_ID}] connected, listening on '{queue_name}' ({role})",
          flush=True)

    # Fair dispatch: don't give a worker a new task until it ACKs the current one
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=queue_name, on_message_callback=process_task)

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
