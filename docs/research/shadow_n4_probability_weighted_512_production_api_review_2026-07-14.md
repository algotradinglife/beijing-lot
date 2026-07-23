# shadow_n4_probability_weighted_512_v1 Production API Review

Status: `continue_paper_non_selectable`.

## Purpose

Expose a single research candidate to production operations as read-only status
metadata. This review does not promote a strategy, produce tickets, modify the
active decision chain, or change a release registry.

The source research report is
`docs/strategy/strategy_parallel_n4_512_paper_recommendation_2026-07-14.md`
in the strategy worktree. Its combined 26072--26074 diagnostic ROI is
`+27.82%`, but the evidence is only three issues and ten sampling-sensitivity
seeds, not ten independent operating observations.

## Candidate Contract

| Field | Fixed value |
| --- | --- |
| Strategy ID | `shadow_n4_probability_weighted_512_v1` |
| Decision source | `shadow_v3.3.3` selected codes |
| Scope | whole issue only |
| N | 4 |
| Budget | 256 units / 512 yuan |
| Ordering | probability weighted |
| Candidate construction | 3,000 attempts |
| Research seed policy | `20260707`--`20260716`, sensitivity only |
| Operational state | `continue_paper_non_selectable` |

## Initial Production Surface

`GET /api/strategy-candidates` returns status metadata only. It does not
accept issue, budget, seed, or ticket-generation parameters and never returns
ticket, bundle, leg, stake, payout, or execution-plan data.

```json
{
  "api_scope": "strategy_status_metadata_only",
  "candidates": [{
    "strategy_id": "shadow_n4_probability_weighted_512_v1",
    "status": "continue_paper_non_selectable",
    "execution_enabled": false,
    "frontend_selectable": false,
    "scope": "whole_issue",
    "n_value": 4,
    "budget_yuan": 512,
    "budget_units": 256,
    "base_decision_chain": "shadow_v3.3.3",
    "ordering": "probability_weighted",
    "candidate_attempts": 3000,
    "evidence": {
      "settled_issues": ["26072", "26073", "26074"],
      "combined_weighted_roi": 0.278206,
      "combined_full_loss_rate": 0.0
    }
  }]
}
```

The endpoint is deliberately separate from `/api/strategies/lab`, the decision
variant registry, and every ticket or segment-plan endpoint. The dashboard is
not changed to fetch or display this candidate, so there is no frontend
selection path.

## Non-Goals And Guards

- Do not add the candidate to `config/strategy_release.json`.
- Do not add a decision variant, active strategy arm, artifact generator, or
  ticket endpoint for it.
- Do not add a dashboard strategy selector or ticket action.
- Keep both `execution_enabled` and `frontend_selectable` false in the only
  exposed record.
- Treat the reported ROI as research evidence, not a production performance
  claim.

## Execution Review Prerequisites

Any later execution review must first complete all of the following, in order:

1. Freeze one operational randomization policy or a deterministic seed.
2. Run the unchanged candidate on newly issued, hash-locked forward snapshots.
3. Review forward performance, concentration, fill, and full-loss behavior.
4. Complete a formal release review that explicitly approves a release manifest
   change and a separate executable-ticket API design.

Until all four gates pass, this endpoint remains informational only.
