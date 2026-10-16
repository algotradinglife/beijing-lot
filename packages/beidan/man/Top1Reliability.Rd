\name{Top1Reliability}
\alias{Top1Reliability}
\title{Describe confidence reliability of frozen three-outcome forecasts}
\usage{Top1Reliability(probabilities, labels, breaks)}
\arguments{
\item{probabilities}{Tibble with fixture_id, model, outcome (W/D/L), probability. Complete normalized triples on a common universe.}
\item{labels}{Tibble with unique fixture_id and actual_outcome (W/D/L).}
\item{breaks}{Explicit increasing numeric edges covering [1/3,1].}}
\value{List of fixtures, bins and summary tibbles. Probabilities and rates are 0--1. Empty bins have zero counts and missing means.}
\description{Pure post-hoc description using the authoritative paired diagnostic scorer and W/D/L tie ordering. Does not fit a transformation, select thresholds or make decisions.}
\details{Bins are left-closed and the final bin includes 1. Invalid, missing, empty or incomplete probability inputs fail. Degenerate correlations are missing. No inference or confidence intervals are produced. No side effects.}
