"""TDD for src/moonshot/coverage.py — high-N coverage construction primitives.

Outcome index 0/1/2 maps to result code '3'/'1'/'0' (home-hcp-win/draw/away).
The key identity under test: EV/budget = RR · ∏[(Σ_{o∈C} p_o·sp_o)/|C|], so for a
FAIR market (p_o·sp_o = 1) EV/budget = RR regardless of how much you cover —
covering changes P(hit) and payoff shape, NOT EV.
"""
import math

from src.moonshot.coverage import (
    RR, devig3, Leg, parlay_ev_single, config_metrics, simulate_config,
    simulate_strategy,
)


def fair_leg(probs):
    """A leg priced fairly: sp_o = 1/p_o so p_o·sp_o = 1 for every outcome."""
    return Leg(probs=tuple(probs), sps=tuple(1.0 / p for p in probs))


def test_devig3_normalizes():
    p = devig3(2.0, 4.0, 4.0)
    assert abs(p[0] - 0.5) < 1e-12 and abs(p[1] - 0.25) < 1e-12 and abs(p[2] - 0.25) < 1e-12
    assert abs(sum(p) - 1.0) < 1e-12


def test_parlay_ev_single_fair_is_rake():
    legs = [fair_leg((0.5, 0.25, 0.25)), fair_leg((0.4, 0.3, 0.3))]
    # selecting any outcome on a fair leg gives p*sp = 1, so EV = RR
    assert abs(parlay_ev_single(legs, [0, 0]) - RR) < 1e-12
    assert abs(parlay_ev_single(legs, [2, 1]) - RR) < 1e-12


def test_config_metrics_single_select():
    legs = [fair_leg((0.5, 0.25, 0.25)), fair_leg((0.4, 0.3, 0.3))]
    m = config_metrics(legs, [(0,), (0,)])      # single-select outcome 0 on both
    assert m["tickets"] == 1
    assert abs(m["hit_prob"] - 0.5 * 0.4) < 1e-12
    assert abs(m["ev_per_budget"] - RR) < 1e-12  # fair -> rake


def test_config_metrics_cover_all_is_guaranteed_but_still_rake():
    legs = [fair_leg((0.5, 0.25, 0.25)), fair_leg((0.4, 0.3, 0.3))]
    m = config_metrics(legs, [(0, 1, 2), (0, 1, 2)])  # cover everything
    assert m["tickets"] == 9                  # 3 x 3
    assert abs(m["hit_prob"] - 1.0) < 1e-12    # one ticket always wins
    assert abs(m["ev_per_budget"] - RR) < 1e-12  # still -35%: rake on losing covers


def test_coverage_raises_hitprob_not_ev():
    legs = [fair_leg((0.6, 0.2, 0.2)) for _ in range(4)]
    single = config_metrics(legs, [(0,)] * 4)
    cover2 = config_metrics(legs, [(0, 1)] * 4)   # cover top-2 each
    assert cover2["hit_prob"] > single["hit_prob"]
    assert cover2["tickets"] > single["tickets"]
    assert abs(cover2["ev_per_budget"] - single["ev_per_budget"]) < 1e-9  # EV unchanged


def test_simulate_matches_analytic_ev_and_deterministic():
    legs = [fair_leg((0.5, 0.3, 0.2)) for _ in range(3)]
    cov = [(0, 1)] * 3
    a = simulate_config(legs, cov, budget=100.0, n_sims=40000, seed=11)
    b = simulate_config(legs, cov, budget=100.0, n_sims=40000, seed=11)
    assert a == b                                   # deterministic
    analytic = config_metrics(legs, cov)
    # MC mean return/budget should converge to analytic EV/budget
    assert abs(a["mean_roi"] + 1.0 - analytic["ev_per_budget"]) < 0.05
    assert abs(a["hit_rate"] - analytic["hit_prob"]) < 0.03


def test_config_metrics_rejects_bad_covered():
    legs = [fair_leg((0.5, 0.3, 0.2)), fair_leg((0.5, 0.3, 0.2))]
    import pytest
    with pytest.raises(ValueError):       # wrong length (zip would silently truncate)
        config_metrics(legs, [(0,)])
    with pytest.raises(ValueError):       # empty covered set
        config_metrics(legs, [(0,), ()])
    with pytest.raises(ValueError):       # bad outcome index
        config_metrics(legs, [(0,), (3,)])
    with pytest.raises(ValueError):       # duplicate outcome
        config_metrics(legs, [(0,), (1, 1)])


def test_simulate_config_validates_covered():
    # same contract as config_metrics — no silent zip-truncation / ZeroDivision
    import pytest
    legs = [fair_leg((0.5, 0.3, 0.2)), fair_leg((0.5, 0.3, 0.2))]
    with pytest.raises(ValueError):
        simulate_config(legs, [(0,)], n_sims=10)            # wrong length
    with pytest.raises(ValueError):
        simulate_config(legs, [(0,), ()], n_sims=10)        # empty set
    with pytest.raises(ValueError):
        simulate_config(legs, [(0,), (3,)], n_sims=10)      # bad index
    with pytest.raises(ValueError):
        simulate_config(legs, [(0,), (1, 1)], n_sims=10)    # duplicate


def test_cover2_between_single_and_cover3():
    # cover-2 (drop least likely) sits between single and cover-3 on P(hit)/tickets
    legs = [fair_leg((0.6, 0.25, 0.15)) for _ in range(4)]
    single = config_metrics(legs, [(0,)] * 4)
    cover2 = config_metrics(legs, [(0, 1)] * 4)       # top-2 each
    cover3 = config_metrics(legs, [(0, 1, 2)] * 4)
    assert single["hit_prob"] < cover2["hit_prob"] < cover3["hit_prob"]
    assert single["tickets"] < cover2["tickets"] < cover3["tickets"]
    assert cover2["tickets"] == 2 ** 4
    # EV stays at the fair floor regardless
    assert abs(cover2["ev_per_budget"] - RR) < 1e-9


def test_simulate_strategy_deterministic_and_fair_floor():
    # fair pool -> EV/budget = RR for every coverage level (no edge, no drift)
    pool = [fair_leg((0.55, 0.25, 0.20)), fair_leg((0.6, 0.22, 0.18)),
            fair_leg((0.5, 0.3, 0.2)), fair_leg((0.45, 0.30, 0.25)),
            fair_leg((0.65, 0.20, 0.15)), fair_leg((0.4, 0.33, 0.27)),
            fair_leg((0.7, 0.18, 0.12)), fair_leg((0.5, 0.28, 0.22))]
    a = simulate_strategy(pool, n_legs=7, n_cover3=0, n_sims=30000, seed=5)
    b = simulate_strategy(pool, n_legs=7, n_cover3=0, n_sims=30000, seed=5)
    assert a == b                                          # deterministic
    assert abs(a["mean_roi"] + 1.0 - RR) < 0.06            # fair -> -35% floor
    # covering more raises hit rate but keeps the EV floor
    cov = simulate_strategy(pool, n_legs=7, n_cover3=4, n_sims=30000, seed=5)
    assert cov["hit_rate"] > a["hit_rate"]
    assert cov["tickets"] == 81 and a["tickets"] == 1
    assert abs(cov["mean_roi"] + 1.0 - RR) < 0.06
    # cover-2 ladder: tickets = 2^n_cover2, hit between single and cover-3
    c2 = simulate_strategy(pool, n_legs=7, n_cover2=4, n_sims=30000, seed=5)
    assert c2["tickets"] == 16
    assert a["hit_rate"] < c2["hit_rate"] < cov["hit_rate"]
    assert abs(c2["mean_roi"] + 1.0 - RR) < 0.06


def test_simulate_strategy_rejects_overcover():
    import pytest
    pool = [fair_leg((0.5, 0.3, 0.2)) for _ in range(6)]
    with pytest.raises(ValueError):
        simulate_strategy(pool, n_legs=5, n_cover2=3, n_cover3=3, n_sims=10)
