"""Tests for the lightweight math + passphrase access gate.

The gate is active only when a passphrase is configured (via the
``gate_pass`` create_app arg or ``BEIDAN_GATE_PASS`` env). When active,
every page except the gate itself (and static assets) requires the
visitor to answer a simple arithmetic question AND supply the fixed
passphrase before the session is granted.

The arithmetic question is stateless: its operands ride in hidden form
fields, so a second hit to /gate (e.g. the browser fetching /favicon.ico)
cannot invalidate the answer the user is currently filling in.
"""
import re
from pathlib import Path

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


def _operands(body: str):
    a = int(re.search(r'name="a"\s+value="(\d+)"', body).group(1))
    b = int(re.search(r'name="b"\s+value="(\d+)"', body).group(1))
    return a, b


def test_unauthenticated_request_is_redirected_to_gate(tmp_path):
    client = _gated_app(tmp_path).test_client()
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_gate_page_renders_a_question(tmp_path):
    client = _gated_app(tmp_path).test_client()
    body = client.get("/gate").get_data(as_text=True)
    a, b = _operands(body)
    assert f"{a} + {b}" in body


def test_correct_answer_and_passphrase_grants_access(tmp_path):
    client = _gated_app(tmp_path).test_client()
    a, b = _operands(client.get("/gate").get_data(as_text=True))
    resp = client.post("/gate",
                       data={"a": a, "b": b, "answer": str(a + b), "passphrase": PASS},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" not in resp.headers["Location"]
    follow = client.get("/dashboard", follow_redirects=False)
    assert "/gate" not in follow.headers.get("Location", "")


def test_answer_survives_a_second_gate_load(tmp_path):
    """Regression: a favicon/refresh hitting /gate again must not invalidate
    the answer shown on the page the user is filling in."""
    client = _gated_app(tmp_path).test_client()
    a, b = _operands(client.get("/gate").get_data(as_text=True))
    client.get("/gate")  # second load (e.g. /favicon.ico → redirected to /gate)
    resp = client.post("/gate",
                       data={"a": a, "b": b, "answer": str(a + b), "passphrase": PASS},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" not in resp.headers["Location"]


def test_wrong_passphrase_is_rejected(tmp_path):
    client = _gated_app(tmp_path).test_client()
    a, b = _operands(client.get("/gate").get_data(as_text=True))
    client.post("/gate", data={"a": a, "b": b, "answer": str(a + b), "passphrase": "nope"})
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_wrong_answer_is_rejected(tmp_path):
    client = _gated_app(tmp_path).test_client()
    a, b = _operands(client.get("/gate").get_data(as_text=True))
    client.post("/gate", data={"a": a, "b": b, "answer": str(a + b + 1), "passphrase": PASS})
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/gate" in resp.headers["Location"]


def test_gate_disabled_when_no_passphrase_configured(tmp_path):
    client = _ungated_app(tmp_path).test_client()
    resp = client.get("/dashboard", follow_redirects=False)
    assert "/gate" not in resp.headers.get("Location", "")
