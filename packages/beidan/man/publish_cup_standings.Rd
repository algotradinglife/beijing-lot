\name{publish_cup_standings}
\alias{publish_cup_standings}
\title{Publish verified cup group standings}
\usage{
publish_cup_standings(parsed_sources, issue, base_version,
  base_manifest_sha256, raw_evidence_relative, raw_manifest_sha256,
  python, root, hot_root)
}
\arguments{
\item{parsed_sources}{Parsed source observations for both sources of every base fixture.}
\item{issue}{Character issue ID.}
\item{base_version}{Immutable source issue version.}
\item{base_manifest_sha256}{SHA256 of the base manifest.}
\item{raw_evidence_relative}{Relative frozen raw archive path under root.}
\item{raw_manifest_sha256}{SHA256 of the raw asset manifest.}
\item{python}{Explicit project Python executable.}
\item{root}{Explicit existing NAS Parquet root.}
\item{hot_root}{Explicit existing working root.}
}
\value{A list containing status, dataset and version.}
\description{Publishes source-published cup group tables separately from league standings, with fixed base identities read through \code{read_dataset}. Preserves original observations, conflicts and historical-proxy status.}
\details{Writes immutable versions and atomic catalog/schema metadata through the authoritative backend. Identical inputs are a no-op; catalog failures restore the previous pointer. Does not modify base data or frozen predictions.}
