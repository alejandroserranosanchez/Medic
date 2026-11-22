"""Allow the browser UI from one configured origin.

UI_ORIGIN is the full origin, such as http://localhost:8080.
A request with no Origin header is a server-side call and is left alone.
A request that names a different origin is rejected.
This service never answers with a wildcard origin.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Content-Type, Accept"


def ui_origin() -> str:
    return os.environ.get("UI_ORIGIN", "").strip().rstrip("/")


def apply_cors(app: Flask) -> None:
    @app.before_request
    def cors_gate():
        origin = request.headers.get("Origin", "")
        if not origin:
            return None
        allowed = ui_origin()
        if origin != allowed:
            return jsonify({"error": "origin not allowed"}), 403
        if request.method == "OPTIONS":
            response = app.response_class(status=204)
            allow(response, origin)
            return response
        return None

    @app.after_request
    def add_cors(response):
        origin = request.headers.get("Origin", "")
        allowed = ui_origin()
        if origin and allowed and origin == allowed:
            allow(response, origin)
        return response


def allow(response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
    response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
    response.headers["Vary"] = "Origin"
