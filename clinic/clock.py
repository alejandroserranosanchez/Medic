"""Single clock for planning decisions. Europe/Madrid course context; MVP stores local naive datetimes."""

from __future__ import annotations

import os
from datetime import datetime

from flask import current_app, has_app_context

from clinic.timeutil import parse_datetime_local


def now() -> datetime:
    """Return 'current' time. DEMO_NOW (ISO local) overrides the system clock for demos/tests."""
    raw = None
    if has_app_context():
        raw = current_app.config.get("DEMO_NOW")
    if not raw:
        raw = os.environ.get("DEMO_NOW")
    if raw:
        return parse_datetime_local(str(raw))
    return datetime.now().replace(microsecond=0)
