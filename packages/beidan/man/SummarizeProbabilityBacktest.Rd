\name{SummarizeProbabilityBacktest}
\alias{SummarizeProbabilityBacktest}
\title{Summarise visible results and money for immutable alternative decisions.}
\usage{
SummarizeProbabilityBacktest(experiment, observations)
}
\arguments{
\item{experiment}{Frozen output of BuildProbabilityBacktest; each case has its embedded cutoff and raw-source decision receipt.}
\item{observations}{Named lists matching round IDs exactly. Each has canonical match_results, actual settlements and explicit finite UTC as_of after cutoff; typed empty tables are valid.}
}
\value{Receipt-bound round_summary, strategy_summary, match_summary, fixture_results, ticket_returns, group_attributions and leg_attributions tibbles. Money is CNY, probabilities and hit rates unitless fractions; zero denominators yield NA. Case keys are round_id/strategy_id.}
\description{Summarise visible results and money for immutable alternative decisions.}
\details{Every raw-source decision is replayed before evaluation. Projected, filtered and purchased fixture scopes retain their own resolved/pending/neutral denominators. Actual final money stays NA until all ticket amounts are known. Partial known payout is separate. Confirmed losses pay zero even if prices are unpublished; winning tickets with unknown prices remain pending. Frozen-SP outcome valuation uses the authoritative settlement engine separately from actual money and model EV, applying the frozen ticket-level factor once. Neutral ALL is not a W/D/L prediction hit; special results do not imply refunds. Duplicate/conflicting labels, missing chronology and tampered receipts fail closed. No IO, fitting or decision changes. Empty experiments preserve typed schemas.}
