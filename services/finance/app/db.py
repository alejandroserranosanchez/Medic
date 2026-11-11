"""Database connection for this service only. No booking or payment rules live here."""

import os
from urllib.parse import unquote, urlparse

import pymssql


def connect():
    """Open a connection using DATABASE_URL: mssql://user:password@host:port/database."""
    url = urlparse(os.environ["DATABASE_URL"])
    return pymssql.connect(
        server=url.hostname,
        port=url.port or 1433,
        user=unquote(url.username or ""),
        password=unquote(url.password or ""),
        database=url.path.lstrip("/"),
        login_timeout=5,
        timeout=5,
    )
