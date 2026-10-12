\name{BuildFmTailJudgement}
\alias{BuildFmTailJudgement}
\title{Build FM-1.6.0 single or dual center margin targets}
\usage{BuildFmTailJudgement(base, review, evidence_id, cutoff = base$cutoff, policy)}
\arguments{
\item{base}{List with normalized score grid tibble and explicit cutoff.}
\item{review}{Bound apply/retain decision, center_mode single/dual/auto, optional adjacent centers, grid hash, UTC cutoff, reason and counterevidence.}
\item{evidence_id}{Admitted nonempty evidence identity.}
\item{cutoff}{Explicit issue_id and UTC POSIXct cutoff matching the base; omitted cutoff uses the explicitly passed base cutoff.}
\item{policy}{Explicit max_radius (0--2), threshold (0--1), coefficient (positive at most one), tie_tolerance, dual_gap (NULL or probability difference). Auto requires dual_gap; FM16 uses 2/0.1/0.3/1e-12/0.01.}}
\value{List with full integer-partition judgement, centers, radius, core margins, shells, masses, normalizer, policy and identity binding.}
\description{Freezes a unique modal margin or unambiguous adjacent top-two interval before pairwise expansion. No fitting, scraping or writes.}
\details{Auto uses dual centers when adjacent top-two difference is at most dual_gap including equality. Ambiguous modes retain the grid. Each shell checks the two interval endpoints; either side reaching threshold admits both, at most two layers. Core weight one, exterior coefficient, normalized across complete support. Missing support is zero; empty, malformed or unbound inputs fail. No ticket line or desired outcome may govern targets. Use the shared evidence adjustment interface to apply them.}
