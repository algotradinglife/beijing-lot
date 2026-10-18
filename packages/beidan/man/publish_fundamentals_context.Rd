\name{publish_fundamentals_context}
\alias{publish_fundamentals_context}
\title{Publish source-bound competition and venue context}
\usage{
publish_fundamentals_context(issue, base_version, base_manifest_sha256,
  raw_evidence_relative, raw_manifest_sha256, python, root, hot_root)
}
\arguments{
\item{issue}{Character issue ID.}
\item{base_version}{Fixed source\_issue version label.}
\item{base_manifest_sha256}{SHA256 of its manifest.}
\item{raw_evidence_relative}{Relative frozen raw archive directory.}
\item{raw_manifest_sha256}{SHA256 of the raw asset manifest.}
\item{python}{Explicit project Python executable.}
\item{root}{Explicit existing NAS root.}
\item{hot_root}{Explicit existing short-lived root.}
}
\value{List containing status, dataset and immutable version.}
\description{Parses original analysis and auxiliary responses, validates exact base
native identities and history keys through the R dataset reader, and publishes
registered typed Parquet metadata. Unknown neutral markers stay missing logical
values; source conflicts retain both observations and null effective cells.
All observations remain historical proxies and never alter base data or forecasts.}
\details{Uses the shared catalog roots, lock, atomic writers and version lifecycle.
Identical verified inputs/code are a no-op; changed or inconsistent bytes, identities
or metadata fail closed. Writes dataset, catalog and schema metadata on the NAS.}
