"""Shared webui test fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.webui import create_app


@pytest.fixture
def app_factory(tmp_path):
    """Returns a factory that builds an app rooted at tmp_path."""
    def _make(live_db_path: Path | None = None):
        live_db = live_db_path or (tmp_path / "live_empty.db")
        app = create_app(
            live_db=str(live_db),
            webui_db=str(tmp_path / "webui.db"),
            plans_dir=str(tmp_path / "plans"),
            pnl_log=str(tmp_path / "pnl.csv"),
        )
        app.config.update(TESTING=True)
        return app
    return _make
