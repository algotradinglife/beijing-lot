"""Issue partitions built on the authoritative shared admission/receipt context.

Separate module so adding this research client does not alter existing expert
implementation closures. No duplicated availability, weighting or cache engine.
"""
from dataclasses import dataclass, asdict
import pandas as pd
from .core import (prepare_learning_context as prepare_base_context, PartitionPolicy,
                   LearningReceipt, temporal_cache_key, TemporalContractError)


@dataclass(frozen=True)
class IssuePartitionPolicy:
    kind: str = "PRIOR_COMPLETE_ISSUES"
    tune_issues: int = 4
    calibration_issues: int = 4
    minimum_fit_issues: int = 8


def prepare_issue_learning_context(history, cutoff, *, source_hashes, repository_root,
        implementation_modules, implementation_distributions=(), availability,
        intended_use, partition_policy, weighting_policy):
    """Derive fit/tune/calibration by prior complete issue; diagnostic only.

    Base context performs admission, exact target exclusion, weights, ESS and
    provenance. Completeness counts only source rows already known by cutoff.
    A second base-context call is needed only when partial issues are removed,
    so weights/receipts still come from the single shared implementation.
    Unknown post-cutoff rows cannot retroactively remove a known prior issue.
    """
    sizes=(partition_policy.tune_issues,partition_policy.calibration_issues,
           partition_policy.minimum_fit_issues)
    if partition_policy.kind!="PRIOR_COMPLETE_ISSUES" or any(type(v) is not int or v<1 for v in sizes):
        raise TemporalContractError("Positive issue partition sizes required")
    if intended_use!="HISTORICAL_DIAGNOSTIC":
        raise TemporalContractError("Issue diagnostic partition cannot authorize prospective use")
    arguments=dict(source_hashes=source_hashes,repository_root=repository_root,
        implementation_modules=tuple(dict.fromkeys(("src.temporal_learning.issue_partitions",*implementation_modules))),
        implementation_distributions=implementation_distributions,availability=availability,
        intended_use=intended_use,partition_policy=PartitionPolicy(kind="FIXED_PRIOR_FIT",
            tune_years=0,calibration_years=0,minimum_fit_years=1),weighting_policy=weighting_policy)
    context=prepare_base_context(history,cutoff,**arguments)
    key=availability.source_issue_column
    boundary=pd.Timestamp(context.receipt.payload["availability"]["admissibility_boundary_ts"])
    known=history
    if availability.data_available_column is not None:
        known=history[pd.to_datetime(history[availability.data_available_column],utc=True).lt(boundary)]
    all_counts=known.groupby(key).size()
    prior_counts=context.eligible.groupby(key).size()
    incomplete=prior_counts.index[~prior_counts.eq(all_counts.reindex(prior_counts.index))]
    if len(incomplete):
        context=prepare_base_context(history[~history[key].isin(incomplete)],cutoff,**arguments)
    eligible=context.eligible
    ordered=(eligible.groupby(key)[availability.label_available_column].max().reset_index()
             .sort_values([availability.label_available_column,key]))
    issues=ordered[key].tolist()
    tail=partition_policy.tune_issues+partition_policy.calibration_issues
    if len(issues)<tail+partition_policy.minimum_fit_issues:
        raise TemporalContractError("insufficient complete prior issues for partitions")
    groups=dict(fit=issues[:-tail],tune=issues[-tail:-partition_policy.calibration_issues],
                calibration=issues[-partition_policy.calibration_issues:],final_refit=issues)
    context.partitions={name:eligible[eligible[key].isin(ids)].copy() for name,ids in groups.items()}
    receipt=dict(context.receipt.payload)
    receipt["partition"]={
        **{name+"_issues":sorted(ids) for name,ids in groups.items()},
        **{name+"_rows":len(frame) for name,frame in context.partitions.items()},
        **{name+"_years":sorted(map(int,frame[availability.issue_year_column].unique()))
           for name,frame in context.partitions.items()},
        "eligible_years":sorted(map(int,eligible[availability.issue_year_column].unique()))}
    receipt["partition_policy"]=asdict(partition_policy)
    receipt["cache_key"]=temporal_cache_key(cutoff,source_hashes,receipt["implementation_hashes"],
        availability.policy,intended_use,partition_policy,weighting_policy)
    receipt["excluded_partial_issues"]=sorted(incomplete.tolist())
    context.receipt=LearningReceipt(receipt)
    return context
