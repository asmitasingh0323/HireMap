import requests
import socketio
import time

API = "https://hiremap-ffey.onrender.com"

sio = socketio.Client()
results = {"jobs": 0, "complete": False}


@sio.on("source_done")
def on_source_done(data):
    print(f"  source done: {data['source']} ({data['count']} jobs)")
    results["jobs"] += data["count"]


@sio.on("search_complete")
def on_complete(data):
    print(
        f"  COMPLETE: {data['total_results']} jobs, sources={data['completed_sources']}")
    results["complete"] = True


print("Connecting to cloud API...")
sio.connect(API)
print("Connected. Sending search...")
requests.post(f"{API}/api/search", json={
    "keyword": "python developer", "location": "Seattle", "deadline": 15
})
# Wait for results to stream back
for _ in range(20):
    time.sleep(1)
    if results["complete"]:
        break
sio.disconnect()
print(f"\nDone. Total jobs received: {results['jobs']}")
