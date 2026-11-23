"""Request logging. These tests do not open a database."""

import re

from app.main import app

LINE = re.compile(r"^(GET|POST|OPTIONS) (/[^\s]*) (\d{3}) (\d+)ms$")


def test_a_successful_health_check_is_logged(monkeypatch, capsys):
    class Cursor:
        def __init__(self):
            self.rowcount = 1

        def execute(self, *_args):
            return None

        def fetchone(self):
            return (1,)

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.main.connect", lambda: Connection())
    response = app.test_client().get("/health")
    assert response.status_code == 200
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("GET /health")]
    assert len(lines) == 1
    match = LINE.match(lines[0])
    assert match is not None
    assert match.group(1) == "GET"
    assert match.group(2) == "/health"
    assert match.group(3) == "200"
    assert int(match.group(4)) >= 0
    assert "DATABASE_URL" not in lines[0]
    assert "password" not in lines[0].lower()


def test_a_failed_request_is_logged(capsys):
    response = app.test_client().post("/receivables", json={"procedure_code": "GASTRO"})
    assert response.status_code == 400
    lines = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("POST /receivables")
    ]
    assert len(lines) == 1
    match = LINE.match(lines[0])
    assert match is not None
    assert match.group(3) == "400"
    assert "GASTRO" not in lines[0]
