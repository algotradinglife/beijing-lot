\name{PrematchSPProbabilities}
\alias{PrematchSPProbabilities}
\title{Normalize inverse observed pre-match SP}
\usage{PrematchSPProbabilities(prematch_sp, cutoff)}
\arguments{
\item{prematch_sp}{Nonempty tibble keyed by fixture_id/outcome, complete W/D/L triples, positive finite sp_raw, POSIXct quote_at strictly before cutoff and nonempty source_url.}
\item{cutoff}{Explicit issue decision cutoff with UTC cutoff_utc and character issue_id.}
}
\value{Probability tibble keyed by fixture_id/outcome with unitless normalized doubles. Row order and identifiers are retained.}
\description{Convert complete observed pre-match SP into normalized inverse-SP market proxy probabilities, without clipping.}
\details{No IO, labels, fitting or clock. Empty, incomplete, duplicate, malformed or post-cutoff evidence errors. This market proxy is not a calibrated probability or a locked payout price.}
