#!/usr/bin/env python3
"""Reviewer-owned probe for high-N coverage fix review.
Checks two acceptance points:
1) simulate_config should reject malformed covered sequences (same guardrails as config_metrics).
2) analyze_high_n_coverage.py should enumerate the requested mixed n_single/n_cover2/n_cover3 frontier, not only pure cover2/pure cover3 ladders.
"""
from pathlib import Path
import re

from src.moonshot.coverage import Leg, config_metrics, simulate_config


def fair_leg(probs):
    return Leg(probs=tuple(probs), sps=tuple(1.0 / p for p in probs))

legs = [fair_leg((0.5, 0.3, 0.2)), fair_leg((0.4, 0.35, 0.25))]
bad_cases = {
    "wrong_len": [(0,)],
    "empty": [(0,), ()],
    "bad_index": [(0,), (3,)],
    "duplicate": [(0,), (1, 1)],
}
print("guardrail_probe")
for name, covered in bad_cases.items():
    for fn in (config_metrics, simulate_config):
        try:
            if fn is simulate_config:
                fn(legs, covered, n_sims=10, seed=1)  # type: ignore[arg-type]
            else:
                fn(legs, covered)  # type: ignore[arg-type]
            outcome = "ACCEPTED"
        except ValueError as e:
            outcome = "rejected_valueerror:" + str(e).split("\n")[0]
        except Exception as e:
            outcome = f"wrong_exception:{type(e).__name__}:" + str(e).split("\n")[0]
        print(f"  {fn.__name__}.{name}={outcome}")

script = Path("scripts/analyze_high_n_coverage.py").read_text()
# Lightweight static check: implementation calls simulate_strategy for one varied arg at a time.
# Full requested frontier should include a nested/enumerated pair where n_cover2 and n_cover3 are both varied/passed.
call_lines = [ln.strip() for ln in script.splitlines() if "simulate_strategy(" in ln or "kw =" in ln]
print("frontier_static_probe")
for ln in call_lines:
    print("  " + ln)
# Count visible table sections in durable doc.
doc = Path("docs/research/high_n_coverage_construction.md").read_text()
print("doc_sections")
print("  has_cover3=", "cover-3 梯度" in doc)
print("  has_cover2=", "cover-2 梯度" in doc)
print("  mentions_mixed_n_cover2_n_cover3=", bool(re.search(r"n_cover2.*n_cover3|cover-2.*cover-3.*混|混合", doc, re.S)))
