import os
import json
import uuid
import pika
from dotenv import load_dotenv
load_dotenv()

creds = pika.PlainCredentials(
    os.getenv("RABBIT_USER"), os.getenv("RABBIT_PASS"))
params = pika.ConnectionParameters(host=os.getenv("RABBIT_HOST"), port=int(
    os.getenv("RABBIT_PORT", 5672)), credentials=creds)
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.queue_declare(queue="task_queue", durable=True)

search_id = "faulttest-" + str(uuid.uuid4())[:6]
task = {"source": "slow_test", "keyword": "recovery",
        "location": "TestLand", "search_id": search_id}
ch.basic_publish(exchange="", routing_key="task_queue", body=json.dumps(task),
                 properties=pika.BasicProperties(delivery_mode=2))
print(f"Published 1 slow_test task. search_id={search_id}")
conn.close()
