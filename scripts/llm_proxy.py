#!/usr/bin/env python3
"""Stable OpenAI-compatible proxy with automatic upstream model discovery."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UPSTREAM = os.environ.get("LLM_PROXY_UPSTREAM", "http://127.0.0.1:8000/v1").rstrip("/")
HOST = os.environ.get("LLM_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("LLM_PROXY_PORT", "8900"))
TIMEOUT = float(os.environ.get("LLM_PROXY_TIMEOUT_SECONDS", "180"))


def active_model() -> str:
    """Return the first model currently advertised by the upstream server."""
    with urlopen(f"{UPSTREAM}/v1/models", timeout=10) as response:
        payload = json.loads(response.read())
    models = payload.get("data", [])
    if not models or not isinstance(models[0].get("id"), str):
        raise RuntimeError("Upstream did not advertise an active model")
    return models[0]["id"]


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            try:
                model = active_model()
                self._json(200, {"status": "ok", "model_available": bool(model)})
            except Exception as exc:  # noqa: BLE001
                self._json(503, {"status": "unavailable", "detail": str(exc)})
            return
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward(rewrite_model=True)

    def _forward(self, rewrite_model: bool = False) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        if rewrite_model and body and self.path.startswith("/v1/"):
            try:
                payload = json.loads(body)
                if isinstance(payload, dict) and "model" in payload:
                    payload["model"] = active_model()
                    body = json.dumps(payload).encode()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        request = Request(
            f"{UPSTREAM}{self.path}",
            data=body,
            headers=headers,
            method=self.command,
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                response_body = response.read()
                self.send_response(response.status)
                self._response_headers(response.headers, len(response_body))
                self.end_headers()
                self.wfile.write(response_body)
        except HTTPError as exc:
            response_body = exc.read()
            self.send_response(exc.code)
            self._response_headers(exc.headers, len(response_body))
            self.end_headers()
            self.wfile.write(response_body)
        except (URLError, OSError, RuntimeError) as exc:
            self._json(502, {"error": {"message": f"Upstream unavailable: {exc}"}})

    def _response_headers(self, headers, length: int) -> None:
        for key, value in headers.items():
            if key.lower() not in {"content-length", "connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(length))
        self.send_header("Connection", "close")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, message: str, *args: object) -> None:
        print(f"{self.address_string()} - {message % args}", flush=True)


if __name__ == "__main__":
    print(f"LLM proxy listening on http://{HOST}:{PORT}; upstream={UPSTREAM}", flush=True)
    ThreadingHTTPServer((HOST, PORT), ProxyHandler).serve_forever()
