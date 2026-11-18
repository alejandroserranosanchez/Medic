from app.main import app


def test_health_is_200_when_the_database_answers(monkeypatch):
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

    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setattr("app.main.connect", lambda: Connection())
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "abc123"}


def test_health_is_503_when_the_database_is_unreachable(monkeypatch):
    # Nothing listens on port 1: the service must report itself unhealthy, not crash.
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/finance")
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
