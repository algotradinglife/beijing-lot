\name{AdaptOutcomeSelections}
\alias{AdaptOutcomeSelections}
\title{Reallocate fixture categories for an adaptive structure}
\usage{AdaptOutcomeSelections(ranked_selections, n_legs, pattern = NULL, max_role1 = 1L, requested_groups = 1L, max_reuse = NULL)}
\arguments{
\item{ranked_selections}{Receipt-bound original ranked tibble with embedded cutoff.}
\item{n_legs}{Positive whole required leg count.}
\item{pattern}{Optional role vector 1:3 of length n_legs; NULL uses parlay_suggest_pattern.}
\item{max_role1}{Maximum singles in suggested pattern, default one.}
\item{requested_groups}{Positive whole target group count for supply planning.}
\item{max_reuse}{Optional positive whole per-fixture reuse cap, counting all roles.}}
\value{List with ranked tibble, cutoff-bound allocation and sorted integer pattern. Ledger records original and allocated role and primary coverage probabilities. Insufficient fixtures are explicit; no fixtures are fabricated.}
\description{Reassign surplus categories to deficit categories using a fixed greedy policy. Prefer the nearest donor role, then maximize primary coverage gain, then fixture identity. With a reuse cap, require ceiling(role count times feasible target groups divided by max reuse) fixtures per category; the target is capped by total available fixture appearances and reduced until rounded category minima fit available fixtures. Unchanged fixtures preserve original choices. Changed fixtures use allocated TopN, with optional DC union protection when present. Original probability mass and filtering are preserved.}
\details{No learning, global optimization, labels, IO or normalization. Replays source, cutoff and implementation bindings. Rejects already allocated inputs.}
