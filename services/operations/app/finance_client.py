"""HTTP call from Operations to Finance. The address comes from the environment."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from socket import timeout as SocketTimeout


class FinanceCallError(Exception):
    def __init__(self, kind: str, status: int | None = None, detail: str = ""):
        super().__init__(detail or kind)
        self.kind = kind
        self.status = status
        self.detail = detail


def timeout_seconds() -> float:
    """A finite limit. A missing or unusable setting stays at 3 seconds, never unlimited."""
    raw = os.environ.get("FINANCE_TIMEOUT_SECONDS", "3")
    try:
        value = float(raw)
    except ValueError:
        return 3.0
    if value <= 0 or value > 30:
        return 3.0
    return value


def post_receivable(payload: dict) -> tuple[int, dict]:
    base = os.environ.get("FINANCE_SERVICE_URL", "").strip().rstrip("/")
    if not base:
        raise FinanceCallError("unconfigured", detail="FINANCE_SERVICE_URL is not set")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/receivables",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds()) as response:
            return response.status, _json(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json(exc.read())
    except SocketTimeout as exc:
        raise FinanceCallError("timeout", detail=str(exc)) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, SocketTimeout)):
            raise FinanceCallError("timeout", detail=str(reason)) from exc
        if isinstance(reason, ConnectionRefusedError):
            raise FinanceCallError("refused", detail="finance refused the connection") from exc
        text = str(reason).lower()
        if "timed out" in text:
            raise FinanceCallError("timeout", detail=str(reason)) from exc
        if "refused" in text:
            raise FinanceCallError("refused", detail="finance refused the connection") from exc
        raise FinanceCallError("unreachable", detail=str(reason)) from exc


def _json(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
