"""The Finance HTTP client. These tests do not open a database or a real socket."""

import io
import urllib.error

import pytest

from app.finance_client import FinanceCallError, post_receivable, timeout_seconds


def test_timeout_setting_stays_finite(monkeypatch):
    monkeypatch.setenv("FINANCE_TIMEOUT_SECONDS", "0")
    assert timeout_seconds() == 3.0
    monkeypatch.setenv("FINANCE_TIMEOUT_SECONDS", "4")
    assert timeout_seconds() == 4.0


def test_missing_address_is_reported(monkeypatch):
    monkeypatch.delenv("FINANCE_SERVICE_URL", raising=False)
    with pytest.raises(FinanceCallError) as caught:
        post_receivable({"source_booking_id": 1})
    assert caught.value.kind == "unconfigured"


def test_connection_refused_and_timeout_are_distinct(monkeypatch):
    monkeypatch.setenv("FINANCE_SERVICE_URL", "http://finance.internal")

    def refuse(*_args, **_kwargs):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr("app.finance_client.urllib.request.urlopen", refuse)
    with pytest.raises(FinanceCallError) as refused:
        post_receivable({"source_booking_id": 1})
    assert refused.value.kind == "refused"

    def time_out(*_args, **_kwargs):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr("app.finance_client.urllib.request.urlopen", time_out)
    with pytest.raises(FinanceCallError) as timed:
        post_receivable({"source_booking_id": 1})
    assert timed.value.kind == "timeout"


def test_empty_and_invalid_json_become_an_empty_object(monkeypatch):
    monkeypatch.setenv("FINANCE_SERVICE_URL", "http://finance.internal")

    class Response:
        def __init__(self, status, raw):
            self.status = status
            self.raw = raw

        def read(self):
            return self.raw

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    replies = [
        Response(200, b""),
        Response(201, b"not-json"),
        Response(200, b"[1, 2]"),
    ]

    def succeed(*_args, **_kwargs):
        return replies.pop(0)

    monkeypatch.setattr("app.finance_client.urllib.request.urlopen", succeed)
    assert post_receivable({"source_booking_id": 1}) == (200, {})
    assert post_receivable({"source_booking_id": 1}) == (201, {})
    assert post_receivable({"source_booking_id": 1}) == (200, {})

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "http://finance.internal/receivables",
            400,
            "bad",
            {},
            io.BytesIO(b"{"),
        )

    monkeypatch.setattr("app.finance_client.urllib.request.urlopen", fail)
    assert post_receivable({"source_booking_id": 1}) == (400, {})


def test_http_error_is_returned_to_the_caller(monkeypatch):
    monkeypatch.setenv("FINANCE_SERVICE_URL", "http://finance.internal")

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "http://finance.internal/receivables",
            409,
            "conflict",
            {},
            io.BytesIO(b'{"error":"different details"}'),
        )

    monkeypatch.setattr("app.finance_client.urllib.request.urlopen", fail)
    status, body = post_receivable({"source_booking_id": 1})
    assert status == 409
    assert body["error"] == "different details"
