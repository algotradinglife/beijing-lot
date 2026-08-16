"""Issue #232 — terminal disposition truth table (R2 fresh, EV C2).

R1's builder decided READY from a single branch (recovered SP issue count
nonzero AND Q_BJ_x_SP fit_issues nonzero) — it never required the
independent-source interface (Q_BJ x EU x SP OR Q_BJ x POWER x SP) nor
issue-level support in every chronological role (fit/tune/calibration).
R2 moves the decision into a pure truth-table function with mutation tests:
READY requires EVERY necessary condition; any failure -> UNRECOVERABLE.

Frozen gate (contract "Modelability gate"):
  READY iff:
    1. positive causal Q_BJ x SP support (complete triplets exist), AND
    2. positive causal Q_BJ x EU x SP OR Q_BJ x POWER x SP support, AND
    3. complete three-outcome match triplets exist, AND
    4. issue-level support in every chronological role required by #209
       (fit <= 2021, tune 2022, calibration 2023).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import contract


@dataclass(frozen=True)
class ModelabilitySupport:
    """Boolean support summary consumed by the disposition truth table.

    qbj_sp_complete_matches: complete Q_BJ x SP matches (triplets with a
        causally available Q_BJ anchor on all three outcomes).
    qbj_eu_sp_complete_matches: complete Q_BJ x EU x SP matches.
    qbj_power_sp_complete_matches: complete Q_BJ x POWER x SP matches.
    cohort_issue_support: {cohort: issue_count} for Q_BJ x SP complete
        matches (or any interface — same issue space).
    """

    qbj_sp_complete_matches: int
    qbj_eu_sp_complete_matches: int
    qbj_power_sp_complete_matches: int
    cohort_issue_support: dict[str, int]

    def qbj_sp_positive(self) -> bool:
        return self.qbj_sp_complete_matches > 0

    def independent_source_positive(self) -> bool:
        return (
            self.qbj_eu_sp_complete_matches > 0
            or self.qbj_power_sp_complete_matches > 0
        )

    def all_roles_supported(self) -> bool:
        return all(
            self.cohort_issue_support.get(cohort, 0) > 0
            for cohort in contract.REQUIRED_COHORTS_FOR_READY
        )


def terminal_disposition(support: ModelabilitySupport) -> str:
    """Pure truth table — every necessary condition must hold for READY.

    The truth table (mutation-tested in tests):
        Q_BJxSP  INDEP   ROLES   ->  disposition
        F        *       *       ->  UNRECOVERABLE
        T        F       *       ->  UNRECOVERABLE
        T        T       F       ->  UNRECOVERABLE
        T        T       T       ->  READY
    """
    if not support.qbj_sp_positive():
        return contract.TERMINAL_UNRECOVERABLE
    if not support.independent_source_positive():
        return contract.TERMINAL_UNRECOVERABLE
    if not support.all_roles_supported():
        return contract.TERMINAL_UNRECOVERABLE
    return contract.TERMINAL_READY_FOR_209
