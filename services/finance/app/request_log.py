"""One stdout line per HTTP request. No bodies, patients, or secrets."""

from __future__ import annotations

import time

from flask import Flask, g, request


def apply_request_logging(app: Flask) -> None:
    @app.before_request
    def mark_request_start():
        g.request_started = time.perf_counter()

    @app.after_request
    def log_request(response):
        started = getattr(g, "request_started", None)
        duration_ms = int(round((time.perf_counter() - started) * 1000)) if started is not None else 0
        print(
            f"{request.method} {request.path} {response.status_code} {duration_ms}ms",
            flush=True,
        )
        return response
