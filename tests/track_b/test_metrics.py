"""TDD for src/track_b/metrics.py."""
import math

from src.track_b.metrics import (
    multiclass_log_loss, multiclass_brier, accuracy, divergence_lift,
)


def test_log_loss_perfect_and_uniform():
    # perfect prediction -> ~0
    assert multiclass_log_loss([(1.0, 0.0, 0.0)], ["3"]) < 1e-10
    # uniform 1/3 -> log 3
    ll = multiclass_log_loss([(1 / 3, 1 / 3, 1 / 3)], ["1"])
    assert abs(ll - math.log(3)) < 1e-9


def test_log_loss_lower_is_better():
    P_good = [(0.7, 0.2, 0.1), (0.1, 0.1, 0.8)]
    P_bad = [(0.3, 0.4, 0.3), (0.4, 0.3, 0.3)]
    y = ["3", "0"]
    assert multiclass_log_loss(P_good, y) < multiclass_log_loss(P_bad, y)


def test_brier():
    # perfect -> 0
    assert multiclass_brier([(1.0, 0.0, 0.0)], ["3"]) < 1e-12
    # (0.5,0.25,0.25) vs class 3: (0.5)^2... = 0.25+0.0625+0.0625 = 0.375
    assert abs(multiclass_brier([(0.5, 0.25, 0.25)], ["3"]) - 0.375) < 1e-9


def test_accuracy():
    P = [(0.7, 0.2, 0.1), (0.1, 0.2, 0.7)]
    assert accuracy(P, ["3", "0"]) == 1.0
    assert accuracy(P, ["1", "1"]) == 0.0


def test_divergence_lift_detects_signal():
    # model that nudges p_home up exactly when home is MORE likely than close says
    p_close = [(0.4, 0.3, 0.3)] * 200
    p_hat, labels = [], []
    for i in range(200):
        up = i < 100
        p_hat.append((0.5 if up else 0.3, 0.25, 0.25 if up else 0.45))
        # positive-divergence group realizes home 60%, negative group 20%
        labels.append("3" if (up and i % 10 < 6) or (not up and i % 10 < 2) else "0")
    tab = divergence_lift(p_hat, p_close, labels, outcome_idx=0, edges=[-1.0, 0.0, 1.0])
    pos = [b for b in tab if b["lo"] == 0.0][0]
    neg = [b for b in tab if b["lo"] == -1.0][0]
    assert pos["realized"] > pos["mean_p_close"]   # model adds info on the up side
    assert neg["realized"] < neg["mean_p_close"]
