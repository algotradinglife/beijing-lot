# #176 issue-level equity and risk-adjusted diagnostics

## Decision

This retrospective diagnostic adds path risk; it does not promote a betting policy. BEST_FULL/FULL remains the #134 controlling selection baseline. The positive MODEL and Q sleeves remain source-context diagnostics and must not be relabelled as a BEST_FULL stack.

## Primary pre-tax metrics (1x common research bankroll)

| Support | Arm | ROI | Sharpe | Sortino | Calmar | Max DD | Max DD % | P&L Calmar | HHI | Ex-largest year ROI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NATIVE_SELECTOR | BEST_FULL_FULL | -9.47% | -0.539 | -1.006 | -0.167 | ¥78,519 | 33.99% | -0.137 | 0.0120 | -11.67% |
| NATIVE_SELECTOR | MODEL_SOURCE_MODEL_CAP1_M512 | +8.14% | +0.356 | +0.702 | +0.263 | ¥10,716 | 4.39% | +0.244 | 0.0127 | -0.21% |
| NATIVE_SELECTOR | Q_SOURCE_Q_TOP_MASS_M192 | +20.37% | +0.319 | +2.365 | +0.214 | ¥87,643 | 23.51% | +0.145 | 0.0833 | -14.99% |
| THREE_WAY_COMMON | BEST_FULL_FULL | -9.09% | -0.496 | -0.958 | -0.189 | ¥66,618 | 28.90% | -0.160 | 0.0142 | -12.36% |
| THREE_WAY_COMMON | MODEL_SOURCE_MODEL_CAP1_M512 | +14.09% | +0.552 | +1.158 | +0.544 | ¥7,348 | 3.12% | +0.528 | 0.0169 | +5.46% |
| THREE_WAY_COMMON | Q_SOURCE_Q_TOP_MASS_M192 | -37.66% | -0.628 | -1.962 | -0.167 | ¥127,817 | 50.74% | -0.122 | 0.1707 | -80.69% |

## Conventions

- Common 1x research bankroll: ¥220,000; 0.5x/1x/2x sensitivity uses the same frozen P&L and no reinvestment.
- Calendar Sharpe uses path-dependent issue equity returns, sample standard deviation, zero risk-free rate and observed calendar issue frequency/year.
- Sortino downside target is zero per issue; downside deviation includes zero-flow calendar rows.
- CAGR and Calmar use elapsed kickoff time and fixed starting equity. P&L Calmar is annualized net divided by absolute maximum yuan drawdown.
- Miss streak counts consecutive active issues with zero payout; no-bet and unavailable zero-flow rows neither create nor end a betting miss streak.
- HHI and ex-largest issue/year use payout contributions. Native and THREE_WAY_COMMON supports are separate denominators.

## Source integrity

All 6 required arm/support bridges reconcile to accepted #167/#170 stake, gross, ROI and policy counts within the frozen serialization tolerances.

Pre-tax is primary; tax-adjusted results are secondary. This package grants no purchase, execution, betting, production or promotion authority.
