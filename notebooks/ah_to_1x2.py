"""
ah_to_1x2.py
============

Convert Asian Handicap (AH) market odds + Total Goals (O/U) odds into 1X2
win-draw-loss probabilities at an arbitrary INTEGER handicap line — the line
used by Beijing Single Match (北京单场) "让球胜平负".

Methodology (chosen after research, see docs/research/ah-to-1x2-methodology.md)
------------------------------------------------------------------------------
We parameterise the goal-difference D = HomeGoals - AwayGoals via the Skellam
distribution:

    HomeGoals ~ Poisson(lh)
    AwayGoals ~ Poisson(la)
    D = HomeGoals - AwayGoals  ~  Skellam(lh, la)

The Skellam has two parameters which we pin down with two independent market
constraints:

1. Total expected goals  ``lambda_total = lh + la``
       calibrated from the over/under market at total_line (typically 2.5).
       Fit lh+la so that  P(H+A > total_line) under independent Poissons
       equals the de-vigged "over" probability.

2. Supremacy             ``mu = lh - la``
       calibrated from the AH market at ah_line.  Under Skellam,
            P_home_AH(line) = P(D > line) + 0.5 * P(D == line)   (no margin)
       For half/quarter lines the bet is split per the standard Asian rules.
       We solve for mu such that the model AH-home win probability matches the
       de-vigged AH-home implied probability.

With (lh, la) determined, lh = (lambda_total + mu)/2, la = (lambda_total - mu)/2.
The 北单 integer-handicap probabilities for a target line ``h`` (e.g. -1) are:

    p3 = P(D + h > 0) = P(D > -h)
    p1 = P(D + h = 0) = P(D = -h)
    p0 = P(D + h < 0) = P(D < -h)

De-vigging
----------
We use the *power* method (Shin 1993 family — fair odds satisfy
sum(p_i^k) = 1 for some k>=1).  Power method beats proportional ("Wisdom of
Crowds" baseline) on most bookmakers per Buchdahl and Hyndman 2024 (see notes).
For two-way markets (AH, O/U) where margin is small we also offer the simple
proportional method as a fallback; in practice on Pinnacle two-way markets the
two methods agree to within rounding.

Author: built for beijing-lot project, 2026-05.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
from scipy.optimize import brentq
from scipy.stats import poisson, skellam


# ---------------------------------------------------------------------------
# De-vigging helpers
# ---------------------------------------------------------------------------

def implied_probs_proportional(odds: np.ndarray) -> np.ndarray:
    """Simple normalisation: p_i = (1/o_i) / sum(1/o_j)."""
    raw = 1.0 / np.asarray(odds, dtype=float)
    return raw / raw.sum()


def implied_probs_power(odds: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    """Power method de-vigging (Shin-style).

    Find k >= 1 such that sum( (1/o_i)^k ) = 1; return p_i = (1/o_i)^k.
    For a fair book k = 1; bookies' books have k < 1 (overround means
    we have to *raise* probabilities to a power < 1 — equivalently shrink them).

    We solve f(k) = sum( raw^k ) - 1 = 0 by bisection.  raw = 1/odds in (0,1).
    """
    raw = 1.0 / np.asarray(odds, dtype=float)
    if raw.sum() <= 1.0 + tol:
        # Already a fair / under-round book — fall back to proportional.
        return raw / raw.sum() if raw.sum() > 0 else raw

    def f(k: float) -> float:
        return float(np.sum(raw ** k) - 1.0)

    # f(1) = overround > 0; for very small k each term tends to 1 so sum tends to N >> 1.
    # As k -> infinity, raw^k -> 0 so f -> -1 < 0.  Bracket [1, 50] should always work.
    lo, hi = 1.0, 50.0
    if f(hi) > 0:
        hi = 200.0
    k = brentq(f, lo, hi, xtol=tol)
    return raw ** k


# ---------------------------------------------------------------------------
# AH win-probability under Skellam (full / half / quarter lines)
# ---------------------------------------------------------------------------

def skellam_ah_home_prob(lh: float, la: float, line: float) -> float:
    """Probability that the Asian-Handicap *home* bet wins under Skellam(lh, la).

    AH rules (line refers to the home team; negative means home is favoured):
      - line is integer x:        win if D + x > 0; push if D + x == 0; lose if < 0.
      - line is half-integer x.5: win if D + x.5 > 0  (no push possible).
      - line is quarter x.25/x.75: bet split half-half between two adjacent
        whole/half lines, each leg settled separately, then averaged.

    Push counts as half-win for expected-value purposes (stake returned).
    Returns the *expected fraction of stake recovered as winnings probability*,
    i.e. E[1_win + 0.5 * 1_push].  This is the quantity that equals 1 / fair_odds
    when there is no margin.
    """
    # Decompose quarter lines into two equal-weight legs.
    # quarter line x.25 -> legs (x.0, x.5); x.75 -> legs (x.5, x+1.0)
    frac = line - math.floor(line * 2) / 2  # 0, 0.25, 0.5, 0.75 mod 1 are mapped via *2
    # cleaner: detect quarter
    twoline = round(line * 4)
    if twoline % 2 != 0:
        # quarter line — split into two legs at the two adjacent half/whole lines
        leg_a = (twoline - 1) / 4.0
        leg_b = (twoline + 1) / 4.0
        return 0.5 * skellam_ah_home_prob(lh, la, leg_a) + 0.5 * skellam_ah_home_prob(lh, la, leg_b)

    # Now line is integer or half-integer.
    if abs(line - round(line)) < 1e-9:
        # integer
        x = int(round(line))
        # win: D > -x   push: D == -x   lose: D < -x
        # E[recovery] = P(D > -x) + 0.5 * P(D = -x)
        p_win = 1.0 - skellam.cdf(-x, lh, la)
        p_push = skellam.pmf(-x, lh, la)
        return float(p_win + 0.5 * p_push)
    else:
        # half-integer
        # win: D + line > 0  <=> D >= ceil(-line)  (no push possible since D integer)
        threshold = math.ceil(-line)  # smallest integer D for which D + line > 0
        # P(D >= threshold) = 1 - P(D <= threshold - 1) = 1 - cdf(threshold - 1)
        p_win = 1.0 - skellam.cdf(threshold - 1, lh, la)
        return float(p_win)


def total_over_prob(lh: float, la: float, total_line: float) -> float:
    """P(HomeGoals + AwayGoals > total_line) under independent Poissons.

    Because the sum of two independent Poissons is Poisson(lh+la), we use that.
    Half-integer lines give clean P(N > k); integer lines push on N == k so
    expected recovery = P(N > k) + 0.5 * P(N == k).
    Quarter lines split half-half.
    """
    twoline = round(total_line * 4)
    if twoline % 2 != 0:
        leg_a = (twoline - 1) / 4.0
        leg_b = (twoline + 1) / 4.0
        return 0.5 * total_over_prob(lh, la, leg_a) + 0.5 * total_over_prob(lh, la, leg_b)

    lam = lh + la
    if abs(total_line - round(total_line)) < 1e-9:
        k = int(round(total_line))
        p_over = 1.0 - poisson.cdf(k, lam)
        p_push = poisson.pmf(k, lam)
        return float(p_over + 0.5 * p_push)
    else:
        threshold = math.ceil(total_line)  # smallest integer N for N > total_line
        return float(1.0 - poisson.cdf(threshold - 1, lam))


# ---------------------------------------------------------------------------
# Calibration: solve for (lh, la) from market quotes
# ---------------------------------------------------------------------------

def calibrate_lambda_total(total_line: float, over_odds: float, under_odds: float,
                           devig: str = "proportional") -> float:
    """Return lambda_total = lh + la matching the de-vigged over probability."""
    if devig == "power":
        p_over, _ = implied_probs_power(np.array([over_odds, under_odds]))
    else:
        p_over, _ = implied_probs_proportional(np.array([over_odds, under_odds]))

    def f(lam: float) -> float:
        # Use lh = la = lam/2 here; for the *total* market the split doesn't matter
        # because the sum is Poisson(lam) regardless.
        return total_over_prob(lam / 2, lam / 2, total_line) - p_over

    # bracket: at lam=0.05 nearly-zero P(over 2.5); at lam=8 almost certain.
    # Allow generous bounds.
    try:
        return float(brentq(f, 0.05, 12.0, xtol=1e-7))
    except ValueError:
        # market implies extreme — clamp.
        if f(0.05) > 0:
            return 0.05
        return 12.0


def calibrate_supremacy(lambda_total: float, ah_line: float,
                        ah_home_odds: float, ah_away_odds: float,
                        devig: str = "proportional") -> float:
    """Return mu = lh - la matching the de-vigged AH home probability,
    given lh + la = lambda_total fixed."""
    if devig == "power":
        p_home, _ = implied_probs_power(np.array([ah_home_odds, ah_away_odds]))
    else:
        p_home, _ = implied_probs_proportional(np.array([ah_home_odds, ah_away_odds]))

    def f(mu: float) -> float:
        lh = (lambda_total + mu) / 2.0
        la = (lambda_total - mu) / 2.0
        if lh <= 0 or la <= 0:
            return float("nan")
        return skellam_ah_home_prob(lh, la, ah_line) - p_home

    # mu must keep both lh, la > 0 -> |mu| < lambda_total
    eps = 1e-4
    lo = -(lambda_total - eps)
    hi = lambda_total - eps
    try:
        return float(brentq(f, lo, hi, xtol=1e-7))
    except ValueError:
        # market implies more extreme supremacy than our Poisson floor allows.
        # Clamp to nearer endpoint.
        if f(lo) > 0:
            return lo
        if f(hi) < 0:
            return hi
        raise


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

@dataclass
class Calibration:
    lambda_home: float
    lambda_away: float
    lambda_total: float
    supremacy: float
    p3: float  # home-win after target_handicap
    p1: float  # draw    after target_handicap
    p0: float  # away-win after target_handicap


def ah_to_1x2(ah_line: float,
              ah_home_odds: float,
              ah_away_odds: float,
              total_line: float,
              over_odds: float,
              under_odds: float,
              target_handicap: int,
              devig: str = "proportional",
              return_calibration: bool = False
              ) -> Dict[str, float] | Calibration:
    """Convert AH + Totals odds to 1X2 probabilities at *integer* target_handicap.

    Parameters
    ----------
    ah_line : float
        Asian handicap line (home team perspective; negative = home favourite).
    ah_home_odds, ah_away_odds : float
        Decimal odds on the AH home / AH away.
    total_line : float
        Total goals over/under line, e.g. 2.5.
    over_odds, under_odds : float
        Decimal odds on over / under.
    target_handicap : int
        The integer handicap used by 北单 (e.g. -1 means home -1 / away +1).
        Must be an integer (the 让球胜平负 game uses integer lines only).
    devig : {'proportional', 'power'}
        De-vigging method for both two-way markets.  Default 'proportional'
        is exact when the two-way book has equal margin on both sides, which
        is approximately true for Pinnacle.

    Returns
    -------
    dict {'3': p_home_after_handicap, '1': p_draw, '0': p_away_after_handicap}
    (Or a Calibration dataclass if return_calibration=True.)
    """
    if not isinstance(target_handicap, (int, np.integer)):
        # accept floats that round to integers
        if abs(target_handicap - round(target_handicap)) > 1e-9:
            raise ValueError("target_handicap must be an integer (北单 uses integer lines)")
        target_handicap = int(round(target_handicap))

    lambda_total = calibrate_lambda_total(total_line, over_odds, under_odds, devig=devig)
    mu = calibrate_supremacy(lambda_total, ah_line, ah_home_odds, ah_away_odds, devig=devig)

    lh = (lambda_total + mu) / 2.0
    la = (lambda_total - mu) / 2.0

    # 北单 outcomes at integer handicap h:
    #   3: D + h > 0  i.e. D > -h
    #   1: D + h = 0  i.e. D = -h
    #   0: D + h < 0  i.e. D < -h
    h = target_handicap
    p1 = float(skellam.pmf(-h, lh, la))
    p3 = float(1.0 - skellam.cdf(-h, lh, la))  # P(D > -h)
    p0 = float(skellam.cdf(-h - 1, lh, la))    # P(D <= -h-1) = P(D < -h)

    # Numerical safety: renormalise (should already sum to 1 to ~1e-12)
    s = p3 + p1 + p0
    p3, p1, p0 = p3 / s, p1 / s, p0 / s

    if return_calibration:
        return Calibration(lh, la, lambda_total, mu, p3, p1, p0)
    return {"3": p3, "1": p1, "0": p0}


# ---------------------------------------------------------------------------
# Unit tests / sanity checks
# ---------------------------------------------------------------------------

def _approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) < tol


def run_unit_tests() -> None:
    print("Running unit tests …")

    # ---- Test 1: AH = 0 with equal odds -> mu == 0 -> p3 == p0 at target=0
    out = ah_to_1x2(ah_line=0.0, ah_home_odds=1.95, ah_away_odds=1.95,
                    total_line=2.5, over_odds=1.95, under_odds=1.95,
                    target_handicap=0, return_calibration=True)
    assert _approx(out.supremacy, 0.0, 1e-4), f"supremacy not zero: {out.supremacy}"
    assert _approx(out.p3, out.p0, 1e-4), f"p3 != p0 with symmetric input: {out.p3} vs {out.p0}"
    print(f"  [1] symmetric AH=0  -> p3={out.p3:.4f} p1={out.p1:.4f} p0={out.p0:.4f}  "
          f"lambda_total={out.lambda_total:.3f}  OK")

    # ---- Test 2: probs sum to 1 at every target for a realistic match
    res = ah_to_1x2(ah_line=-1.0, ah_home_odds=2.05, ah_away_odds=1.88,
                    total_line=2.5, over_odds=1.95, under_odds=1.95,
                    target_handicap=-1)
    s = res["3"] + res["1"] + res["0"]
    assert _approx(s, 1.0, 1e-9), f"probabilities don't sum to 1: {s}"
    print(f"  [2] sum=1 check  -> sum={s:.12f}  OK")

    # ---- Test 3: Monotonicity: stronger handicap *against* home -> lower p3
    base = dict(ah_line=-0.5, ah_home_odds=1.95, ah_away_odds=1.95,
                total_line=2.5, over_odds=1.95, under_odds=1.95)
    p3_at_minus2 = ah_to_1x2(**base, target_handicap=-2)["3"]
    p3_at_minus1 = ah_to_1x2(**base, target_handicap=-1)["3"]
    p3_at_0      = ah_to_1x2(**base, target_handicap=0)["3"]
    p3_at_plus1  = ah_to_1x2(**base, target_handicap=1)["3"]
    p3_at_plus2  = ah_to_1x2(**base, target_handicap=2)["3"]
    seq = [p3_at_minus2, p3_at_minus1, p3_at_0, p3_at_plus1, p3_at_plus2]
    assert all(seq[i] < seq[i + 1] for i in range(len(seq) - 1)), f"monotonicity broken: {seq}"
    print(f"  [3] monotonicity p3 vs handicap  -> {[round(x,3) for x in seq]}  OK")

    # ---- Test 4: AH = -1 should be roughly 50/50 in the AH market when home is moderate fav
    # If the bookmaker quotes equal odds at AH=-1, supremacy should be ~1.0 goals, so at
    # target_handicap = -1 (the same line) p3+0.5*p1 ~ 0.5.
    cal = ah_to_1x2(ah_line=-1.0, ah_home_odds=1.95, ah_away_odds=1.95,
                    total_line=2.5, over_odds=1.95, under_odds=1.95,
                    target_handicap=-1, return_calibration=True)
    ah_at_line = cal.p3 + 0.5 * cal.p1
    assert _approx(ah_at_line, 0.5, 5e-3), f"AH home prob not 0.5 at fair AH=-1 line: {ah_at_line}"
    print(f"  [4] AH=-1 fair  -> supremacy={cal.supremacy:.3f}  AH_home_prob={ah_at_line:.4f}  OK")

    # ---- Test 5: hand-computed Skellam vs scipy
    # If lh=1.5, la=1.0 -> mu=0.5, lambda_total=2.5.
    # P(D=0) for Skellam(1.5,1.0) ~ exp(-2.5)*I_0(2*sqrt(1.5)) ; we check via scipy round-trip
    lh, la = 1.5, 1.0
    p_d0 = skellam.pmf(0, lh, la)
    p_d_minus1 = skellam.pmf(-1, lh, la)
    p_d_1 = skellam.pmf(1, lh, la)
    # Sanity: with home favoured, P(D=1) > P(D=-1)
    assert p_d_1 > p_d_minus1, "Skellam asymmetry wrong"
    # And total mass between -10..10 should be ~1
    total = sum(skellam.pmf(k, lh, la) for k in range(-15, 16))
    assert _approx(total, 1.0, 1e-6), f"Skellam mass not 1: {total}"
    print(f"  [5] Skellam internal check -> P(D=0)={p_d0:.4f} P(D=1)={p_d_1:.4f} "
          f"P(D=-1)={p_d_minus1:.4f}  mass={total:.6f}  OK")

    # ---- Test 6: Power vs proportional de-vig should agree to ~few bps on a low-margin two-way book.
    res_prop = ah_to_1x2(ah_line=-0.5, ah_home_odds=1.95, ah_away_odds=1.95,
                         total_line=2.5, over_odds=1.95, under_odds=1.95,
                         target_handicap=0, devig="proportional")
    res_pow = ah_to_1x2(ah_line=-0.5, ah_home_odds=1.95, ah_away_odds=1.95,
                        total_line=2.5, over_odds=1.95, under_odds=1.95,
                        target_handicap=0, devig="power")
    diff = max(abs(res_prop[k] - res_pow[k]) for k in res_prop)
    assert diff < 5e-3, f"power vs proportional differ too much: {diff}"
    print(f"  [6] devig methods agree  -> max-diff={diff:.5f}  OK")

    print("All unit tests passed.\n")


# ---------------------------------------------------------------------------
# Calibration test against real Premier League 2024-25 data
# ---------------------------------------------------------------------------

def calibration_report(csv_path: str = "/Volumes/Data Drive/workspace/trading/beijing-lot/"
                                       "data/raw/football-data/2425_E0.csv",
                       devig: str = "proportional") -> dict:
    """For each Premier-League 2024-25 match, build the model from Pinnacle AH +
    Pinnacle O/U 2.5 odds, then predict the 1X2 probabilities at the AH line
    and compare against Pinnacle's own 1X2 odds (de-vigged).

    This validates the methodology — if the model can reconstruct the same book's
    1X2 quotes from its own AH + O/U quotes, the conversion logic is sound.

    Returns a dict with summary error metrics.
    """
    import pandas as pd  # local to keep core importable without pandas

    df = pd.read_csv(csv_path)
    # Pinnacle columns (the gold standard); fall back to Bet365 where missing.
    needed = ['PSH', 'PSD', 'PSA', 'AHh', 'PAHH', 'PAHA', 'P>2.5', 'P<2.5', 'FTR']
    df = df.dropna(subset=needed).copy()

    rows = []
    for _, r in df.iterrows():
        try:
            cal = ah_to_1x2(
                ah_line=float(r['AHh']),
                ah_home_odds=float(r['PAHH']),
                ah_away_odds=float(r['PAHA']),
                total_line=2.5,
                over_odds=float(r['P>2.5']),
                under_odds=float(r['P<2.5']),
                target_handicap=0,         # use 0 to recover plain 1X2
                devig=devig,
                return_calibration=True,
            )
        except Exception as e:
            continue

        # Pinnacle's own 1X2 de-vigged
        if devig == "power":
            book_p = implied_probs_power(np.array([r['PSH'], r['PSD'], r['PSA']]))
        else:
            book_p = implied_probs_proportional(np.array([r['PSH'], r['PSD'], r['PSA']]))

        actual = r['FTR']  # 'H','D','A'
        outcome_bit = {'H': (1, 0, 0), 'D': (0, 1, 0), 'A': (0, 0, 1)}[actual]

        rows.append(dict(
            book_h=book_p[0], book_d=book_p[1], book_a=book_p[2],
            mod_h=cal.p3,     mod_d=cal.p1,     mod_a=cal.p0,
            lambda_total=cal.lambda_total, supremacy=cal.supremacy,
            ah_line=r['AHh'],
            actual_h=outcome_bit[0], actual_d=outcome_bit[1], actual_a=outcome_bit[2],
        ))

    out = pd.DataFrame(rows)
    n = len(out)
    if n == 0:
        return {"n": 0}

    # Compare model vs book probabilities (calibration of the mapping itself)
    abs_dev_h = (out['mod_h'] - out['book_h']).abs().mean()
    abs_dev_d = (out['mod_d'] - out['book_d']).abs().mean()
    abs_dev_a = (out['mod_a'] - out['book_a']).abs().mean()
    mean_abs_dev = (abs_dev_h + abs_dev_d + abs_dev_a) / 3
    rmse = np.sqrt(((out[['mod_h', 'mod_d', 'mod_a']].values
                     - out[['book_h', 'book_d', 'book_a']].values) ** 2).mean())

    # Brier / log-loss vs *outcomes*, both for book and for model.
    def brier(p, a):
        return ((p - a) ** 2).sum(axis=1).mean()

    def logloss(p, a, eps=1e-12):
        p = np.clip(p, eps, 1 - eps)
        return -(a * np.log(p)).sum(axis=1).mean()

    P_model = out[['mod_h', 'mod_d', 'mod_a']].values
    P_book = out[['book_h', 'book_d', 'book_a']].values
    A = out[['actual_h', 'actual_d', 'actual_a']].values

    metrics = {
        "n_matches": n,
        "mean_abs_dev_vs_book": float(mean_abs_dev),
        "abs_dev_home": float(abs_dev_h),
        "abs_dev_draw": float(abs_dev_d),
        "abs_dev_away": float(abs_dev_a),
        "rmse_vs_book": float(rmse),
        "brier_model": float(brier(P_model, A)),
        "brier_book": float(brier(P_book, A)),
        "logloss_model": float(logloss(P_model, A)),
        "logloss_book": float(logloss(P_book, A)),
        "devig": devig,
    }
    return metrics


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_unit_tests()

    print("Calibration report on Premier League 2024-25 (Pinnacle AH + O/U 2.5)…")
    for method in ("proportional", "power"):
        m = calibration_report(devig=method)
        print(f"\n  De-vigging method: {method}")
        for k, v in m.items():
            if isinstance(v, float):
                print(f"    {k:>22}: {v:.5f}")
            else:
                print(f"    {k:>22}: {v}")
