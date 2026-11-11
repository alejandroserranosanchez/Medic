from app.main import app


def test_health_is_503_when_the_database_is_unreachable(monkeypatch):
    # Nothing listens on port 1: the service must report itself unhealthy, not crash.
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/operations")
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
