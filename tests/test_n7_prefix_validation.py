import pandas as pd
import pytest
from src.n7_prefix_validation import verify_summary_grid

def test_summary_grid_rejects_missing_duplicate_and_null_configurations():
    rows=pd.DataFrame({'arm':['a','a','b'],'seed':[1,1,2]})
    summary=rows.drop_duplicates()
    assert verify_summary_grid(rows,summary)
    for bad in (summary.iloc[:0],summary.iloc[:1],pd.concat([summary,summary]),summary.assign(seed=None)):
        with pytest.raises(ValueError):
            verify_summary_grid(rows,bad)
