\name{BuildProbabilityPlan}
\alias{BuildProbabilityPlan}
\title{Build a receipt-bound plan using one declared probability basis throughout}
\usage{
BuildProbabilityPlan(inputs, cutoff, settings, group_budget_cny,
 base = "beidan", bd_weight = NULL, market_policy = NULL,
 model_config = list(rho = -.14, total_bounds = c(.1, 16), tail_tolerance = 1e-10),
 single_threshold = .45, top1_sp_threshold = 2, pattern = NULL, window_hours = c(4, 28),
 max_candidates = NULL, objective = "coverage", min_group_ev_cny = NULL,
 reuse_policy = list(max_reuse = NULL), overlap_policy = list(max_overlap = NULL))
}
\arguments{
\item{inputs}{Raw match input list from \code{read_match_inputs()}. Beidan requires fixtures, prematch_sp and match_status; euro/totals are unused and optional.}
\item{cutoff}{Explicit issue decision context with character issue_id and UTC POSIXct cutoff_utc. Mismatched issue/source chronology fails closed.}
\item{settings}{Explicit validated \code{parlay_settings()} list, including n_legs, issue_budget_cny, unit_cny, payout_factor and SP valuation policy. Not mutated.}
\item{group_budget_cny}{Nonnegative finite plain scalar CNY cap per group; whole-ticket depth is limited by this cap divided by settings$unit_cny.}
\item{base}{Exact beidan (default), dc, or mixed source used in every stage.}
\item{bd_weight}{Explicit plain scalar in [0,1] required only for mixed.}
\item{market_policy}{Euro/totals policies required for DC/mixed; ignored for BD.}
\item{model_config}{Fixed DC settings; ignored for Beidan.}
\item{single_threshold}{Plain probability threshold in [1/3,1], default .45.}
\item{top1_sp_threshold}{Finite minimum Top1 decimal SP, at least 1; equality is retained. Independent of the SP valuation policy.}
\item{pattern}{NULL for the adaptive target, or explicit integer roles 1:3 with length settings$n_legs. Both modes use cross-category allocation.}
\item{window_hours}{Elapsed-hour fixture decision window, default c(4,28).}
\item{max_candidates}{Optional finite candidate cap; NULL keeps the full deterministic construction trajectory, not exhaustive global enumeration.}
\item{objective}{Exact coverage or ev criterion; default coverage.}
\item{min_group_ev_cny}{Optional minimum group marginal EV in CNY.}
\item{reuse_policy}{Explicit group fixture-reuse policy.}
\item{overlap_policy}{Explicit group overlap policy.}
}
\value{List containing cutoff, probability_base, prepared epoch, projected probabilities, filtered/ranked selections, adapted roles, group pool, canonical plan, selection tibble, BET/NO_BET status, and deterministic receipt binding raw inputs, parameters, code, cutoff and output. Empty admitted pools produce typed empty tables and NO_BET.}
\description{Build a plan from raw inputs with one probability basis throughout admission, projection, filtering, classification, cross-category allocation, construction and funding.}
\details{Beidan uses normalized inverse raw SP and does not require euro or totals. DC/mixed require their declared policies and complete aligned inputs. NULL pattern selects the adaptive target; explicit patterns also use cross-category allocation. No labels, historical tuning, IO, clock inference or session mutation. All monetary units are CNY; probabilities are normalized unitless doubles. Rebuild from raw sources when changing basis or cutoff.}
