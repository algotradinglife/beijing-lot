\name{AlphaTop3Draw}
\alias{AlphaTop3Draw}
\title{Experimental top-three margin draw allocation}
\usage{AlphaTop3Draw(base, handicap, fixture, cutoff, context, repository_root)}
\arguments{
\item{base}{Frozen selected BEFORE-tail source artifact: normalized score-grid tibble, explicit cutoff and source chronology/hashes. Diagnostic only.}
\item{handicap}{Signed integer home handicap; draw margin is its negative.}
\item{fixture}{One-row tibble fixture_id, issue_id, home, away.}
\item{cutoff}{Explicit UTC decision cutoff, identical to base.}
\item{context}{Shared temporal_learning evidence context binding alpha_input and alpha_code. See source documentation for exact hashes.}
\item{repository_root}{Explicit root containing the project Python environment.}}
\value{Reweighted grid, final and before margin tibbles, W/D/L probabilities, handicap binding and a cutoff-bound diagnostic receipt.}
\description{FM-1.8.0-alpha.1 candidate: draw atom in the top two gets its share of the top three atoms, including boundary ties. Remaining mass uses the complete original W:L ratio. No tail compression.}
\details{Conditional score ratios inside each outcome remain unchanged. No trigger retains the original grid. The result is specific to the supplied handicap and is not a new DC fit. No prospective admission, fetching or persistence. Missing/invalid inputs and mismatched chronology, context, input or code hashes fail closed.}
