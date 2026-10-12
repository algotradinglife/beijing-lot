\name{SelectFmProbabilitySource}
\alias{SelectFmProbabilitySource}
\title{Select an evidence-bound native or joint-market score distribution}
\usage{SelectFmProbabilitySource(native, market, review, context, fixture, cutoff = native$cutoff, repository_root)}
\arguments{
\item{native}{Native base list with score-grid tibble, cutoff, model_id, source_hashes, max_source_available_utc POSIXct and intended_use.}
\item{market}{Same base contract for joint-market DC, or NULL if unavailable.}
\item{review}{Bound confidence low/uncertain/adequate, market_sufficient, market_consistent, reason, counterevidence, evidence_ids, cutoff_utc, native_hash, market_hash, author and review_version. NULL market uses ABSENT identity.}
\item{context}{Opaque admitted shared temporal_learning evidence context, binding source-selection inputs, code and dependency hashes.}
\item{fixture}{One-row tibble with fixture_id, issue_id, home and away. No ticket line.}
\item{cutoff}{Explicit issue_id and UTC POSIXct cutoff identical to both bases.}
\item{repository_root}{Explicit root with project Python environment and backend source.}}
\value{List with selected base, selected_source and machine-readable cutoff/input/code/evidence-bound receipt. The output identity is the finalized base excluding only its source_hashes selection_receipt self-reference; that field hashes the full receipt.}
\description{Low or uncertain native reliability and sufficient consistent market select the exact market grid, otherwise native. There is no lambda blending.}
\details{No fitting, scraping or writes. Shared evidence admission and replay validates chronology. Missing market declared sufficient fails closed. Empty or malformed grids, input/code changes, unavailable evidence and changed cutoff fail. Confidence refers to evidence quality, not win probability or disagreement. Historical proxies do not authorize prospective use; review is explicit caller input, not an implemented JEV score.}
