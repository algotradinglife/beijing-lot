#!/usr/bin/env python3
"""Select the N for a rolling time-segment Beidan ticket pool."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


QUALITY_GOOD = 0.78
QUALITY_NORMAL = 0.72
QUALITY_WEAK = 0.66
MIN_N = 3
MAX_N = 8


@dataclass(frozen=True)
class SegmentNRecommendation:
    eligible_matches: int
    expected_coverage_hit_rate: float
    budget_coverage: str
    half_n: int
    recommended_n: int | None
    quality_drop: int
    budget_drop: int
    capped_by_max_n: bool
    action: str
    reasons: list[str]


def normalize_rate(value: float) -> float:
    """Accept either 0.75 or 75 for the expected coverage hit rate."""
    if value < 0:
        raise ValueError("expected coverage hit rate must be non-negative")
    return value / 100.0 if value > 1.0 else value


def quality_drop_for_rate(expected_coverage_hit_rate: float) -> tuple[int, str]:
    p = normalize_rate(expected_coverage_hit_rate)
    if p >= QUALITY_GOOD:
        return 0, "coverage_hit_rate_good_use_half_n"
    if p >= QUALITY_NORMAL:
        return 1, "coverage_hit_rate_normal_drop_1"
    if p >= QUALITY_WEAK:
        return 2, "coverage_hit_rate_weak_drop_2"
    return 3, "coverage_hit_rate_poor_small_n_only"


def budget_drop_for_state(budget_coverage: str) -> tuple[int, str]:
    state = budget_coverage.strip().lower()
    if state in {"ok", "good", "sufficient"}:
        return 0, "budget_coverage_ok"
    if state in {"thin", "tight", "limited"}:
        return 1, "budget_coverage_thin_drop_1"
    if state in {"insufficient", "poor", "low"}:
        return 2, "budget_coverage_insufficient_drop_2"
    raise ValueError("budget_coverage must be ok, thin, or insufficient")


def recommend_segment_n(
    eligible_matches: int,
    expected_coverage_hit_rate: float,
    *,
    budget_coverage: str = "ok",
    min_n: int = MIN_N,
    max_n: int = MAX_N,
) -> SegmentNRecommendation:
    if eligible_matches <= 0:
        raise ValueError("eligible_matches must be positive")
    if min_n <= 0 or max_n < min_n:
        raise ValueError("require 0 < min_n <= max_n")

    p = normalize_rate(expected_coverage_hit_rate)
    raw_half = eligible_matches // 2
    half_n = min(max_n, raw_half)
    quality_drop, quality_reason = quality_drop_for_rate(p)
    budget_drop, budget_reason = budget_drop_for_state(budget_coverage)
    capped_by_max_n = raw_half > max_n
    reasons = [quality_reason, budget_reason]
    if capped_by_max_n:
        reasons.append("half_n_capped_by_max_n")

    if eligible_matches < min_n:
        return SegmentNRecommendation(
            eligible_matches=eligible_matches,
            expected_coverage_hit_rate=p,
            budget_coverage=budget_coverage,
            half_n=half_n,
            recommended_n=None,
            quality_drop=quality_drop,
            budget_drop=budget_drop,
            capped_by_max_n=capped_by_max_n,
            action="expand_or_skip",
            reasons=reasons + ["not_enough_matches_for_min_n"],
        )

    dropped = half_n - quality_drop - budget_drop
    recommended_n = max(min_n, min(max_n, eligible_matches, dropped))
    if eligible_matches <= 5:
        action = "expand_preferred_small_ticket_only"
        reasons.append("small_pool_expand_window_preferred")
    elif capped_by_max_n and eligible_matches >= 25:
        action = "split_or_cap_at_max_n"
        reasons.append("large_pool_split_preferred")
    elif p < QUALITY_WEAK:
        action = "small_n_only"
    else:
        action = "main_segment_ok"

    return SegmentNRecommendation(
        eligible_matches=eligible_matches,
        expected_coverage_hit_rate=p,
        budget_coverage=budget_coverage,
        half_n=half_n,
        recommended_n=recommended_n,
        quality_drop=quality_drop,
        budget_drop=budget_drop,
        capped_by_max_n=capped_by_max_n,
        action=action,
        reasons=reasons,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eligible-matches", type=int, required=True)
    parser.add_argument("--expected-coverage-hit-rate", type=float, required=True)
    parser.add_argument("--budget-coverage", choices=("ok", "thin", "insufficient"), default="ok")
    parser.add_argument("--min-n", type=int, default=MIN_N)
    parser.add_argument("--max-n", type=int, default=MAX_N)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recommendation = recommend_segment_n(
        args.eligible_matches,
        args.expected_coverage_hit_rate,
        budget_coverage=args.budget_coverage,
        min_n=args.min_n,
        max_n=args.max_n,
    )
    print(json.dumps(asdict(recommendation), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
