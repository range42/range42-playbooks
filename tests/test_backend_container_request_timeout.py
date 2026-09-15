"""Installer readiness must accept a healthy response beyond one host's budget."""

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time

FILES = (
    Path(__file__).resolve().parents[1]
    / "bundles/admin/software.install.deployer_api_backend/files"
)


def consumer():
    sys.path.insert(0, str(FILES))
    try:
        spec = importlib.util.spec_from_file_location(
            "container_apply_timeout", FILES / "container_apply.py"
        )
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result
    finally:
        sys.path.remove(str(FILES))


def test_healthy_readiness_slower_than_three_seconds_is_accepted():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/v1/health/ready"
            time.sleep(3.15)
            body = json.dumps({"ready": True}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass  # Expected on the original three-second installer timeout.

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = consumer().request(
            {"listen_address": "127.0.0.1", "port": server.server_port},
            "/v1/health/ready",
            authenticated=False,
        )
        assert result == {"ready": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_readiness_budget_is_bounded_and_other_probes_stay_short(monkeypatch):
    module = consumer()
    seen = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b"{}"

    def urlopen(request, timeout):
        seen.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    plan = {"listen_address": "::", "port": 8000}
    for path in ["/v1/health/ready", "/v1/health", "/v1/admin/maintenance"]:
        module.request(plan, path, authenticated=False)
    assert seen == [
        ("http://[::1]:8000/v1/health/ready", 45),
        ("http://[::1]:8000/v1/health", 3),
        ("http://[::1]:8000/v1/admin/maintenance", 3),
    ]
