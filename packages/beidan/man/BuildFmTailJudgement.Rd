\name{BuildFmTailJudgement}
\alias{BuildFmTailJudgement}
\title{Build FM-1.7.0 probability-ranked net-margin core targets}
\usage{BuildFmTailJudgement(base, review, evidence_id, cutoff = base$cutoff, policy)}
\arguments{
\item{base}{List with normalized score-grid tibble and explicit cutoff.}
\item{review}{Bound decision apply/retain, grid base_hash, ISO-Z cutoff_utc, reason and counterevidence. Obsolete centers and center_mode are rejected.}
\item{evidence_id}{Nonempty identity admitted by the shared adjustment context.}
\item{cutoff}{Explicit issue/time cutoff identical to base and review; omitted cutoff uses the explicitly passed base cutoff.}
\item{policy}{Ordered explicit list coverage (0,1), coefficient (0,1], tie_tolerance (0,1e-8]. FM17 uses 0.9/0.3/1e-12.}}
\value{List judgement, branch, effective_coefficient, ranked_margins tibble, boundary_rank, core_margins, core_mass, final_core_mass, normalizer, policy and implementation binding. Judgement bins give a complete integer partition including zero-mass exterior ranges.}
\description{Pure target construction, with no fitting, fetching, labels, writes or ticket handicap.}
\details{Aggregate normalized score rows by home minus away goals. Sort probability descending, include the first rank strictly crossing coverage, and all bins tied with its probability. Numerical tolerance is capped below half the remaining distance to one. The core may be disconnected or asymmetric and has no radius cap. Core weight one, exterior coefficient; explicit retain decision uses weight one everywhere. Normalize complete support; missing integer margins have zero mass. Use adjust_score_margin_distribution with shared evidence context to preserve within-margin conditional score proportions. Empty, malformed, unnormalized or detached cutoff/hash inputs fail closed. Old center policies are unsupported; frozen previous versions require their own pinned implementation.}
