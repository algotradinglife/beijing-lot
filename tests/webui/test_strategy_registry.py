"""The backend registry is the single source of truth for strategy params.

Covers: every preset round-trips through match_strategy (no internal drift);
the /api/strategies endpoint exposes the registry to the frontend; and
/strategy/apply applies a preset by sid (no hidden-param copying).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.webui.db import WebuiDB
from src.webui.strategies import REGISTRY, match_strategy

_EXPLORER = (Path(__file__).resolve().parents[2]
             / "src" / "webui" / "templates" / "strategy_explorer.html")


def test_template_mix_rows_match_registry():
    # Every Strategy Explorer row tagged with a registry sid must show the same
    # weights + max_combos as the registry, so the label can't mislabel what
    # /strategy/apply will actually apply.
    text = _EXPLORER.read_text(encoding="utf-8")
    # Each tagged row: ...sid:'S3'... then a cfg:{max_combos:100, w:[..]..}
    rows = re.findall(r"sid:'(S\d+)'.*?max_combos:\s*(\d+),\s*w:\[([0-9.,\s]+)\]",
                      text, re.DOTALL)
    assert rows, "no sid-tagged rows found in strategy_explorer.html"
    for sid, max_combos, w_str in rows:
        s = REGISTRY[sid]
        weights = tuple(float(x) for x in w_str.split(","))
        assert int(max_combos) == s.max_combos, f"{sid} max_combos drift"
        assert weights == s.weights, f"{sid} weights drift"


def test_registry_is_self_consistent():
    # Each preset's own params must identify back to itself; otherwise the UI
    # could show one label while the engine runs another.
    for sid, s in REGISTRY.items():
        got, _ = match_strategy(
            weights=s.weights, kelly=s.kelly, lambdas=s.lambdas,
            max_combos=s.max_combos, league_q_min=s.league_q_min,
            cross_n_lambda=s.cross_n_lambda)
        assert got == sid, f"{sid} identifies as {got}"


def _init(app):
    c = app.test_client()
    # Don't follow the redirect: the dashboard touches the (empty) live DB.
    # We only need the bankroll initialized for the strategy routes.
    c.post("/setup", data={"initial_bankroll": "100000"}, follow_redirects=False)
    return c


def test_api_strategies_exposes_full_registry(app_factory):
    client = _init(app_factory())
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert set(data) == set(REGISTRY)
    s9 = data["S9"]
    assert s9["max_combos"] == 200
    assert s9["cross_n_lambda"] == 0.5
    assert s9["kelly"][2] == 0.03125  # N=4 active leg at 1/32


def test_apply_strategy_endpoint_sets_config(app_factory):
    app = app_factory()
    client = _init(app)
    resp = client.post("/strategy/apply", data={"sid": "S9"})
    assert resp.status_code == 200
    db = WebuiDB(app.config["WEBUI_DB"])
    sid, _ = match_strategy(
        weights=(float(db.get_config("mix_weight_n2")),
                 float(db.get_config("mix_weight_n3")),
                 float(db.get_config("mix_weight_n4")),
                 float(db.get_config("mix_weight_n5"))),
        kelly=(float(db.get_config("kelly_n2")), float(db.get_config("kelly_n3")),
               float(db.get_config("kelly_n4")), float(db.get_config("kelly_n5"))),
        lambdas=(float(db.get_config("lambda_n2")),
                 float(db.get_config("lambda_n3")),
                 float(db.get_config("lambda_n4")),
                 float(db.get_config("lambda_n5"))),
        max_combos=int(db.get_config("max_combos")),
        league_q_min=float(db.get_config("league_q_min") or 0),
        cross_n_lambda=float(db.get_config("cross_n_lambda") or 0))
    assert sid == "S9"


def test_apply_strategy_endpoint_rejects_unknown_sid(app_factory):
    client = _init(app_factory())
    resp = client.post("/strategy/apply", data={"sid": "S999"})
    assert resp.status_code == 400
