import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Import and run the existing worker logic in a background thread
import worker


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"worker alive")

    def log_message(self, *args):
        pass  # silence per-request logging


def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[worker_web] health server listening on {port}")
    server.serve_forever()


if __name__ == "__main__":
    # Start the worker consumer loop in a background thread
    t = threading.Thread(target=worker.main, daemon=True)
    t.start()
    # Run the health server in the foreground (keeps Render happy)
    run_health_server()
