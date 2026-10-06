\name{BuildProbabilityBacktest}
\alias{BuildProbabilityBacktest}
\title{Freeze all raw-source fixed alternatives without labels before evaluating observations.}
\usage{
BuildProbabilityBacktest(rounds, strategies, settings, group_budget_cny,
 max_candidates = NULL)
}
\arguments{
\item{rounds}{Named raw round lists: inputs, explicit cutoff, window_hours and market_policy. IDs distinguish decisions within an issue; an empty list is allowed.}
\item{strategies}{Nonempty named fixed lists: base, optional bd_weight, single_threshold, pattern, model_config. Defaults follow BuildProbabilityPlan.}
\item{settings}{Explicit common validated parlay settings, including units and CNY budget.}
\item{group_budget_cny}{Finite nonnegative CNY cap per group.}
\item{max_candidates}{Optional common candidate cap; NULL retains the full deterministic trajectory.}
}
\value{Receipt-bound cases with round_id, strategy_id, explicit arguments and BuildProbabilityPlan decisions. Receipt binds raw inputs, parameters, cutoff ledger and transitive code.}
\description{Freeze all raw-source fixed alternatives without labels before evaluating observations.}
\details{No IO, clock inference, fitting, tuning, strategy routing or session mutation. Persist the immutable experiment before opening labels. Alternative strategies are separate hypothetical accounts. Empty rounds retain a valid empty experiment.}
