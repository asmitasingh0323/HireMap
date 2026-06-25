import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"worker alive")

    def log_message(self, *args):
        pass


def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[worker_web] health server listening on {port}", flush=True)
    server.serve_forever()


def run_worker():
    try:
        # Give the worker a fixed ID since there's no command-line arg here
        sys.argv = ["worker.py", "cloud-worker"]
        import worker
        print("[worker_web] starting worker consumer loop...", flush=True)
        worker.main()
    except Exception as e:
        print(f"[worker_web] WORKER CRASHED: {e}", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    # Start the worker loop in a background thread
    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    # Health server in foreground
    run_health_server()
