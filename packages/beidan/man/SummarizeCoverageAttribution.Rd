\name{SummarizeCoverageAttribution}
\alias{SummarizeCoverageAttribution}
\title{Aggregate structure/depth misses from frozen purchased masks and physical tickets.}
\usage{
SummarizeCoverageAttribution(backtest)
}
\arguments{
\item{backtest}{Receipt-bound output of SummarizeProbabilityBacktest.}
}
\value{List of round_causes (round/strategy/issue/status), fixture_causes (round/strategy/issue/fixture), repeated_fixtures (strategy/issue/fixture), and diagnostic receipt. Counts are overlapping group exposures, not independent samples. Empty inputs preserve typed schemas; no-bet rounds have explicit NO_BET rows.}
\description{Aggregate structure/depth misses from frozen purchased masks and physical tickets.}
\details{Structural_miss_groups counts actual results outside a fixture mask. Multiple offenders can belong to the same failed group, so summing fixture counts double counts groups. Participating_depth_miss_groups counts membership, not individual causation. COVERED_ELSEWHERE remains separate. Repeated fixtures report round support and structural miss occurrences. Missing outcomes stay unknown. No labels are used for fitting or ticket selection; no IO or mutation.}
