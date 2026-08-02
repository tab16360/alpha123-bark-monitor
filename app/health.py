from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import threading
from typing import Callable, Dict, Optional, Union

logger = logging.getLogger("alpha_monitor.health")


class HealthState:
    """Thread-safe state container for health metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self.last_success_at: Optional[str] = None
        self.consecutive_failures: int = 0
        self.event_count_getter: Optional[Callable[[], int]] = None

    def update_success(self, timestamp_iso: str) -> None:
        with self._lock:
            self.last_success_at = timestamp_iso
            self.consecutive_failures = 0

    def increment_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1

    def get_status_dict(self) -> Dict[str, Union[str, int]]:
        with self._lock:
            evt_count = 0
            if self.event_count_getter:
                try:
                    evt_count = self.event_count_getter()
                except Exception:
                    evt_count = 0

            return {
                "status": "ok" if self.consecutive_failures < 3 else "warning",
                "last_success_at": self.last_success_at or "",
                "consecutive_failures": self.consecutive_failures,
                "event_count": evt_count,
            }


global_health_state = HealthState()


class HealthHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            status_data = global_health_state.get_status_dict()
            body_bytes = json.dumps(status_data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format: str, *args: tuple) -> None:
        # Silence standard HTTP access logging to keep application logs clean
        pass


def start_health_server(port: int = 18181) -> Optional[HTTPServer]:
    """Start lightweight health HTTP server in a daemon thread."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHTTPRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server listening on http://0.0.0.0:{port}/health")
        return server
    except Exception as e:
        logger.error(f"Failed to start health server on port {port}: {e}")
        return None
