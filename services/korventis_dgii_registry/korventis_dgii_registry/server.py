"""HTTP health service. No padrón download. No public PostgreSQL."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .config import redact_database_url
from .migrate import apply_migrations, schema_status


_logger = logging.getLogger(__name__)


def build_health_payload(settings):
    payload = {
        "status": "ok",
        "service": "korventis-dgii-registry",
        "version": __version__,
        "mode": settings.mode,
        "auto_import": bool(settings.auto_import),
        "bind": settings.bind,
        "database": redact_database_url(settings.database_url),
    }
    try:
        status = schema_status(settings.database_url)
        payload.update(
            {
                "postgres": True,
                "schema_version": (
                    status["migrations"][-1] if status["migrations"] else None
                ),
                "registry": status["registry"],
                "active_versions": status["active_versions"],
                "auto_import_enabled": status["auto_import_enabled"],
            }
        )
        if settings.auto_import:
            payload["auto_import_note"] = (
                "Flag present but commit 1 never downloads the official ZIP"
            )
    except Exception as exc:  # noqa: BLE001
        payload["status"] = "unready"
        payload["postgres"] = False
        payload["error"] = str(exc)
    return payload


class HealthHandler(BaseHTTPRequestHandler):
    settings = None

    def log_message(self, format, *args):
        message = format % args
        if "://" in message and "@" in message:
            return
        _logger.info("%s", message)

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
            self._send(
                200,
                {
                    "status": "ok",
                    "service": "korventis-dgii-registry",
                    "version": __version__,
                    "mode": self.settings.mode,
                },
            )
            return
        if path == "/health/ready":
            payload = build_health_payload(self.settings)
            code = 200 if payload.get("status") == "ok" else 503
            self._send(code, payload)
            return
        self._send(404, {"status": "not_found", "path": path})


def make_server(settings):
    HealthHandler.settings = settings
    return ThreadingHTTPServer((settings.bind, settings.port), HealthHandler)


def serve(settings):
    applied = apply_migrations(settings.database_url)
    _logger.info("Migrations applied this boot: %s", applied or "none")
    if settings.auto_import:
        _logger.warning(
            "KORVENTIS_DGII_AUTO_IMPORT is set; commit 1 ignores it and does not download"
        )
    httpd = make_server(settings)
    _logger.info(
        "Listening on %s:%s mode=%s",
        settings.bind,
        settings.port,
        settings.mode,
    )
    httpd.serve_forever()
