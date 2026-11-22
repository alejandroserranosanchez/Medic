"""Browser origin rules. These tests do not open a database."""

from app.main import app

ALLOWED = "http://localhost:8080"


def test_preflight_from_the_configured_origin_is_allowed(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    response = app.test_client().options(
        "/receivables",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED
    assert response.headers["Access-Control-Allow-Origin"] != "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert "OPTIONS" in response.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]


def test_a_different_origin_is_rejected(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    response = app.test_client().options(
        "/receivables",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_a_missing_origin_setting_allows_nobody(monkeypatch):
    monkeypatch.delenv("UI_ORIGIN", raising=False)
    response = app.test_client().options(
        "/receivables",
        headers={"Origin": ALLOWED},
    )
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_an_allowed_get_receives_the_origin_header(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/finance")
    response = app.test_client().get("/health", headers={"Origin": ALLOWED})
    assert response.status_code == 503
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED


def test_an_unknown_origin_is_rejected_before_the_database(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    response = app.test_client().get("/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "origin not allowed"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_health_without_an_origin_is_not_blocked(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/finance")
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_options_without_an_origin_is_not_a_cors_rejection(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    response = app.test_client().options("/health")
    assert response.status_code != 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_server_side_post_without_an_origin_is_not_blocked(monkeypatch):
    monkeypatch.setenv("UI_ORIGIN", ALLOWED)
    response = app.test_client().post("/receivables", json={})
    assert response.status_code == 400
    assert "origin" not in response.get_json()["error"]
