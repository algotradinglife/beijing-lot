\name{SelectProbabilityBase}
\alias{SelectProbabilityBase}
\title{Select a fixed probability basis for a prepared decision epoch}
\usage{
SelectProbabilityBase(epoch, base = "beidan", bd_weight = NULL,
  model_config = list(rho = -0.14, total_bounds = c(0.1, 16),
    tail_tolerance = 1e-10))
}
\arguments{
\item{epoch}{Prepared list from \code{prepare_match_inputs()}, carrying cutoff, decision_at, fixtures, match_status and prematch_sp; DC modes also require selected market inputs.}
\item{base}{Exact scalar string: \code{"beidan"}, \code{"dc"}, or \code{"mixed"}.}
\item{bd_weight}{NULL except in mixed mode, which requires a finite scalar in [0,1].}
\item{model_config}{Fixed DC configuration passed to \code{estimate_match_probabilities()}; unused for pure Beidan.}
}
\value{Projection list with cutoff, fixtures, prematch_sp, match_status, probabilities, fit, exclusions, model_config, market_policy, probability_base and probability_base_receipt. Probabilities are a tibble keyed by fixture_id/outcome, with complete W/D/L triples and unitless normalized double probabilities. Empty fixture pools return typed empty tables. Receipt binds input snapshot, output, cutoff, parameters and loaded transitive implementation.}
\description{Choose normalized inverse raw pre-match SP, existing DC projection, or the fixed mixture (1-bd_weight)*DC + bd_weight*Beidan.}
\details{Selected fixtures require complete unique positive finite SP strictly before cutoff, scheduled status and future kickoff. No clipping or implicit fallback. Mixed fixture mismatches fail; DC exclusions remain explicit. Beidan fit is empty and model_config NULL. No historical learning, tuning, labels, IO, caching or clock inference. Preparation must bind the same probability base and retain a valid raw-input replay receipt. Rebuild from raw inputs when changing cutoff or base; a DC-filtered epoch cannot be relabelled Beidan. Pure Beidan preparation skips euro/totals admission. Selected projections are independently replayed by the downstream projection-context validator.}
\seealso{\code{\link{PrematchSPProbabilities}}, \code{estimate_match_probabilities}, \code{\link{AdaptOutcomeSelections}}}
