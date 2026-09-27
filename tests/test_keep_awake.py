"""docker/keep_awake.py: the Render instance keeps itself awake by visiting its own public URL."""

import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "docker" / "keep_awake.py"


def serve(statuses):
    """A local stand-in for the public URL; answers with the given statuses, then 200s."""
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(statuses.pop(0) if statuses else 200)
            self.end_headers()
            self.wfile.write(b"body{}")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hits


def run_until(hits, count, env):
    process = subprocess.Popen([sys.executable, str(SCRIPT)], env=env, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 10
    try:
        while len(hits) < count and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        process.kill()
        process.wait()


def render_env(server):
    return {
        **os.environ,
        "RENDER_EXTERNAL_URL": f"http://127.0.0.1:{server.server_port}/",
        "KEEP_AWAKE_SECONDS": "0.1",
    }


def test_pings_a_static_file_through_the_public_url_again_and_again():
    server, hits = serve([])
    run_until(hits, 3, render_env(server))
    server.shutdown()
    assert hits[:3] == ["/static/climate/css/app.css"] * 3


def test_a_failed_ping_does_not_stop_the_loop():
    server, hits = serve([500, 503])
    run_until(hits, 3, render_env(server))
    server.shutdown()
    assert len(hits) >= 3


def test_does_nothing_outside_render():
    env = {k: v for k, v in os.environ.items() if k != "RENDER_EXTERNAL_URL"}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, timeout=10)
    assert result.returncode == 0  # exits straight away instead of looping
