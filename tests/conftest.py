from __future__ import annotations

import pytest

from clinic import create_app


@pytest.fixture
def app(tmp_path):
    # Fixed planning clock so eligibility/notice tests are stable.
    application = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path / "data"),
            "DEMO_NOW": "2026-10-09T12:00:00",
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
