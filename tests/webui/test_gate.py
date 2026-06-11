"""Tests for the lightweight math + passphrase access gate.

The gate is active only when a passphrase is configured (via the
``gate_pass`` create_app arg or ``BEIDAN_GATE_PASS`` env). When active,
every page except the gate itself (and static assets) requires the
visitor to answer a simple arithmetic question AND supply the fixed
passphrase before the session is granted.
"""
from pathlib import Path

import pytest

from src.webui.app import create_app

PASS = "let-me-in"


def _gated_app(tmp_path: Path):
    app = create_app(
        live_db=str(tmp_path / "live.db"),
        webui_db=str(tmp_path / "webui.db"),
        plans_dir=str(tmp_path / "plans"),
        pnl_log=str(tmp_path / "pnl.csv"),
        gate_pass=PASS,
    )
    app.config.update(TESTING=True)
    return app


def _ungated_app(tmp_path: Path):
    app = create_app(
        live_db=str(tmp_path / "live.db"),
        webui_db=str(tmp_path / "webui.db"),
        plans_dir=str(tmp_path / "plans"),
        pnl_log=str(tmp_path / "pnl.csv"),
    )
    app.config.update(TESTING=True)
    return app


def _read_answer(client) -> int:
    with client.session_transaction() as sess:
        return int(sess["gate_ans"])


def test_unauthenticated_request_is_redirected_to_gate(tmp_path):
    app = _gated_app(tmp_path)
    client = app.test_client()
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_gate_page_renders_a_question(tmp_path):
    app = _gated_app(tmp_path)
    client = app.test_client()
    resp = client.get("/gate")
    assert resp.status_code == 200
    # GET /gate must seed a numeric answer into the session
    assert isinstance(_read_answer(client), int)


def test_correct_answer_and_passphrase_grants_access(tmp_path):
    app = _gated_app(tmp_path)
    client = app.test_client()
    client.get("/gate")
    ans = _read_answer(client)
    resp = client.post("/gate", data={"answer": str(ans), "passphrase": PASS},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" not in resp.headers["Location"]
    # now a protected page is reachable (not bounced back to /gate)
    follow = client.get("/dashboard", follow_redirects=False)
    assert follow.status_code != 302 or "/gate" not in follow.headers.get("Location", "")


def test_wrong_passphrase_is_rejected(tmp_path):
    app = _gated_app(tmp_path)
    client = app.test_client()
    client.get("/gate")
    ans = _read_answer(client)
    client.post("/gate", data={"answer": str(ans), "passphrase": "nope"})
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_wrong_answer_is_rejected(tmp_path):
    app = _gated_app(tmp_path)
    client = app.test_client()
    client.get("/gate")
    ans = _read_answer(client)
    client.post("/gate", data={"answer": str(ans + 1), "passphrase": PASS})
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_gate_disabled_when_no_passphrase_configured(tmp_path):
    app = _ungated_app(tmp_path)
    client = app.test_client()
    resp = client.get("/dashboard", follow_redirects=False)
    # no gate → may redirect to /setup, but never to /gate
    assert "/gate" not in resp.headers.get("Location", "")
