"""Fixed-design assembly of prediction-only residual comparisons."""
import pandas as pd


def assemble_residual_predictions(reference, additions, *, issue_order, affected_issues):
    """Return two reference arms plus three residual variants, one row per key.

    Copies unaffected control decisions and their budget/accounting exactly;
    replaces affected rows with frozen additions. After freeze the same mechanical
    assembly can carry settlement columns; it never branches on outcome values.
    No fitting, IO or changes to existing control rows. Missing/duplicate
    keys or a different variant grid raise ValueError. IDs remain strings.
    """
    keys=['issue','arm','seed']
    if (reference.duplicated(keys).any() or additions.duplicated(keys).any() or
        set(reference.issue)!=set(issue_order) or
        set(additions.issue)!=set(affected_issues)):
        raise ValueError('Residual issue/key mismatch')
    controls=reference[reference.variant.isin(['FILTER_ONLY','REFILL'])].copy()
    base=reference[reference.variant=='FILTER_ONLY'].copy()
    frames=[controls]
    for variant in ['STANDALONE','INCREMENTAL','EFFICIENCY_GATE']:
        unchanged=base[~base.issue.isin(affected_issues)].copy()
        unchanged['variant']=variant
        unchanged['arm']=unchanged.arm.str.replace('_SP130_',f'_{variant}_',regex=False)
        unchanged['original_stake']=unchanged.stake;unchanged['added_stake']=0
        unchanged['initial_eval_union']=unchanged.eval_union;unchanged['added_eval_union']=0
        changed=additions[additions.variant==variant]
        expected=base[base.issue.isin(affected_issues)].copy()
        expected['arm']=expected.arm.str.replace('_SP130_',f'_{variant}_',regex=False)
        if set(map(tuple,changed[keys].to_numpy()))!=set(map(tuple,expected[keys].to_numpy())):
            raise ValueError('Residual variant grid mismatch')
        frames.extend([unchanged,changed])
    result=pd.concat(frames,ignore_index=True)
    if len(result)!=5*len(base) or result.duplicated(keys).any():
        raise ValueError('Five-arm scope mismatch')
    return result
