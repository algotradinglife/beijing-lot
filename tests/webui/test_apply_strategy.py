"""apply_strategy writes a registry preset into config as the single source of
truth, so the running plan params round-trip back to the same preset id."""
from __future__ import annotations

import pytest

from src.webui.db import WebuiDB
from src.webui.strategies import apply_strategy, match_strategy


def _running_strategy(db: WebuiDB):
    g = db.get_config
    return match_strategy(
        weights=(float(g("mix_weight_n2")), float(g("mix_weight_n3")),
                 float(g("mix_weight_n4")), float(g("mix_weight_n5"))),
        kelly=(float(g("kelly_n2")), float(g("kelly_n3")),
               float(g("kelly_n4")), float(g("kelly_n5"))),
        lambdas=(float(g("lambda_n2")), float(g("lambda_n3")),
                 float(g("lambda_n4")), float(g("lambda_n5"))),
        max_combos=int(g("max_combos")),
        league_q_min=float(g("league_q_min") or 0),
        cross_n_lambda=float(g("cross_n_lambda") or 0),
    )


def test_apply_strategy_s9_round_trips_to_s9(tmp_path):
    db = WebuiDB(tmp_path / "webui.db")
    apply_strategy(db, "S9")
    sid, _name = _running_strategy(db)
    assert sid == "S9"
    assert int(db.get_config("mix_enabled")) == 1
    # S9 is a low-Kelly preset: active N's at 1/32, not 1/4.
    assert float(db.get_config("kelly_n4")) == pytest.approx(0.03125)


def test_apply_strategy_overwrites_prior_custom(tmp_path):
    db = WebuiDB(tmp_path / "webui.db")
    # Seed a genuinely non-preset (custom) high-Kelly config (max=137).
    for k, v in {
        "mix_enabled": 1, "mix_weight_n2": 0.2, "mix_weight_n3": 0.2,
        "mix_weight_n4": 0.6, "mix_weight_n5": 0.0, "kelly_n2": 0.25,
        "kelly_n3": 0.25, "kelly_n4": 0.25, "kelly_n5": 0.125,
        "lambda_n2": 0, "lambda_n3": 1.0, "lambda_n4": 0.5, "lambda_n5": 0,
        "max_combos": 137, "cross_n_lambda": 0.0,
    }.items():
        db.set_config(k, v)
    assert _running_strategy(db)[0] == "custom"  # sanity: starts as custom
    apply_strategy(db, "S9")
    assert _running_strategy(db)[0] == "S9"


def test_apply_strategy_unknown_sid_raises(tmp_path):
    db = WebuiDB(tmp_path / "webui.db")
    with pytest.raises(KeyError):
        apply_strategy(db, "S999")
