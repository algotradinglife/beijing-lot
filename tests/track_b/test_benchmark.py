"""TDD for src/track_b/benchmark.py."""
import math

from src.track_b.benchmark import calibration_table, max_calibration_gap, brier


def test_calibration_perfect():
    # 100 pairs at p=0.5 with exactly half hits -> calibrated
    pairs = [(0.5, i % 2 == 0) for i in range(100)]
    tab = calibration_table(pairs, [0.0, 0.4, 0.6, 1.0])
    mid = [b for b in tab if b["lo"] == 0.4][0]
    assert mid["n"] == 100
    assert abs(mid["mean_p"] - 0.5) < 1e-9
    assert abs(mid["hit_rate"] - 0.5) < 1e-9
    assert max_calibration_gap(tab) < 1e-9


def test_calibration_detects_miscalibration():
    # predicts 0.8 but only 30% happen -> big gap
    pairs = [(0.8, i < 30) for i in range(100)]
    tab = calibration_table(pairs, [0.0, 0.7, 1.0])
    assert max_calibration_gap(tab) > 0.4


def test_calibration_empty_bucket_is_nan():
    tab = calibration_table([(0.1, True)], [0.0, 0.5, 1.0])
    hi = [b for b in tab if b["lo"] == 0.5][0]
    assert hi["n"] == 0 and math.isnan(hi["hit_rate"])


def test_brier():
    assert abs(brier([(1.0, True), (0.0, False)])) < 1e-12
    assert abs(brier([(0.5, True), (0.5, False)]) - 0.25) < 1e-12
