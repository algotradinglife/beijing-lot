import json
from pathlib import Path
import pandas as pd
import pytest
from src.strength_draw_context import strength_draw_context
from src.temporal_learning.core import Cutoff, TemporalContractError
from src.temporal_learning.frozen_blocks import frozen_block_schedule

def test_invalid_forecast_rejected_before_label_read():
    cutoff=Cutoff.decision_epoch('003','2011-01-03T00:00:00Z')
    block=frozen_block_schedule(pd.DataFrame({'issue_code':['003'],'fixture_decision_ts':['2011-01-03T00:00:00Z']}),cadence=10)[0]
    with pytest.raises(TemporalContractError,match='Invalid label-free'):
        strength_draw_context(json.dumps([{'issue':'001'}]),block,cutoff,label_path='missing',label_sha256='a'*64,
            delay_hours=24,minimum_ess=100,repository_root=Path.cwd(),source_hashes={})
