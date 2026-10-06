\name{ParlayCoverageAttribution}
\alias{ParlayCoverageAttribution}
\title{Attribute outcome misses to retained masks or purchased depth}
\usage{
ParlayCoverageAttribution(evaluation, match_results, as_of)
}
\arguments{
\item{evaluation}{Frozen portfolio evaluation with embedded cutoff.}
\item{match_results}{Canonical match_results tibble, one final outcome per fixture, with issue_id, fixture_id, outcome, result_available_at, source_url.}
\item{as_of}{Explicit finite UTC POSIXct scalar observation time after cutoff.}
}
\value{List of legs and groups tibbles plus a bound diagnostic receipt. Group rows include legal_space, purchased_tickets, structural_misses, unknown_legs, winner_rank, purchased_winner, winner_owned_elsewhere, depth_blocked and status: STRUCTURE_MISS, HIT, DEPTH_MISS, COVERED_ELSEWHERE or PENDING. Empty purchases return typed empty tables.}
\description{Attribute missed outcomes to retained masks or purchased depth using frozen evaluations and visible outcomes, without settlement SP.}
\details{Labels are admitted only when available by the explicit as_of time and strictly after the decision cutoff. Unknown results remain pending. Winner rank follows the frozen selection policy, including uniform triples.
Winner rank is an after-result diagnostic, not a prospective recommended depth. No learning, payout calculation, IO or modification of selection.}
