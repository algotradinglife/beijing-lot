import pandas as pd
import pytest
from src.n7_residual_comparison import assemble_residual_predictions


def test_five_arm_assembly_keeps_unaffected_rows_and_rejects_missing_variants():
    rows=[]
    for issue in ['001','002']:
        for variant,prefix in [('FILTER_ONLY','SP130'),('REFILL','REFILL')]:
            rows.append(dict(issue=issue,arm=f'T250_{prefix}_RULE_B512',variant=variant,
                seed=1,stake=128,cash=384,budget_cny=512,eval_union=.2))
    reference=pd.DataFrame(rows);new=[]
    for variant in ['STANDALONE','INCREMENTAL','EFFICIENCY_GATE']:
        new.append(dict(rows[0],variant=variant,arm=f'T250_{variant}_RULE_B512',stake=256,cash=256))
    additions=pd.DataFrame(new)
    result=assemble_residual_predictions(reference,additions,issue_order=['001','002'],affected_issues=['001'])
    assert len(result)==10
    assert result[result.issue=='002'].stake.eq(128).all()
    assert result[(result.issue=='001')&result.variant.eq('STANDALONE')].stake.iloc[0]==256
    with pytest.raises(ValueError,match='variant grid'):
        assemble_residual_predictions(reference,additions.iloc[:2],issue_order=['001','002'],affected_issues=['001'])
