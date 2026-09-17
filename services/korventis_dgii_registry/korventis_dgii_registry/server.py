"""HTTP health service. No padrón download. No public PostgreSQL."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .migrate import apply_migrations, probe_readiness


_logger = logging.getLogger(__name__)

LIVE_PAYLOAD = {
    "status": "ok",
    "service": "korventis-dgii-registry",
}


class HealthHandler(BaseHTTPRequestHandler):
    settings = None

    def log_message(self, format, *args):
        _logger.info("%s %s", self.command, self.path.split("?", 1)[0])

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, dict(LIVE_PAYLOAD))
            return
        if path == "/health/ready":
            payload = probe_readiness(self.settings)
            code = 200 if payload.get("status") == "ok" else 503
            self._send(code, payload)
            return
        self._send(404, {"status": "not_found"})


def make_server(settings):
    HealthHandler.settings = settings
    return ThreadingHTTPServer((settings.bind, settings.port), HealthHandler)


def serve(settings):
    try:
        applied = apply_migrations(settings)
    except Exception as exc:  # noqa: BLE001
        _logger.error("migration failed (%s)", type(exc).__name__)
        raise SystemExit(1)
    _logger.info("Migrations applied this boot: %s", applied or "none")
    if settings.auto_import:
        _logger.warning(
            "KORVENTIS_DGII_AUTO_IMPORT is set; this service does not download"
        )
    httpd = make_server(settings)
    _logger.info("Listening on %s:%s", settings.bind, settings.port)
    httpd.serve_forever()
