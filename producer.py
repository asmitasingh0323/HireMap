import os
import json
import uuid
import pika
from dotenv import load_dotenv

load_dotenv()

RABBIT_HOST = os.getenv("RABBIT_HOST", "localhost")
RABBIT_USER = os.getenv("RABBIT_USER", "hiremap")
RABBIT_PASS = os.getenv("RABBIT_PASS", "hiremap_pass")
TASK_QUEUE = "task_queue"

SOURCES = ["adzuna", "remoteok", "weworkremotely"]


def publish_tasks(keyword, location):
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(host=RABBIT_HOST,  port=int(
        os.getenv("RABBIT_PORT", 5672)), credentials=creds)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)

    search_id = str(uuid.uuid4())[:8]
    print(
        f"Publishing tasks for search_id={search_id} (keyword='{keyword}', location='{location}')")

    for source in SOURCES:
        task = {
            "source": source,
            "keyword": keyword,
            "location": location,
            "search_id": search_id,
        }
        ch.basic_publish(
            exchange="",
            routing_key=TASK_QUEUE,
            body=json.dumps(task),
            properties=pika.BasicProperties(
                delivery_mode=2),  # persist message
        )
        print(f"  -> queued task for {source}")

    conn.close()
    print(f"All tasks published. search_id={search_id}")
    return search_id


if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "python developer"
    location = sys.argv[2] if len(sys.argv) > 2 else "Bellevue"
    publish_tasks(keyword, location)
