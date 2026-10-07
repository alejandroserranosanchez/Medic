from __future__ import annotations

import pytest

from clinic import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path / "data"),
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
