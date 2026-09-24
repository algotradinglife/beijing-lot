"""Thin #422 entry point: immutable archived retrospective experiment."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.conditional_score.archive import read_score_archive
from src.conditional_score.runner import run_experiment
from beidan_backend.temporal_learning.core import Cutoff,WeightingPolicy
from beidan_backend.temporal_learning.issue_partitions import IssuePartitionPolicy as PartitionPolicy

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    archive=read_score_archive(a.source_root,clock_horizon=Cutoff.last_issue("100607","2011-01-01T00:00:00Z"),label_delay_hours=72)
    receipt=run_experiment(archive,a.output,repository_root=Path(__file__).resolve().parents[1],
        penalties=(.1,1.,10.),partition_policy=PartitionPolicy(kind="PRIOR_COMPLETE_ISSUES"),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=100),
        budget_cny=1024,unit_cny=2,payout_factor=.65,allocation_seed=422,max_uses=2,initial_bankroll_cny=100000)
    print(receipt["fixtures"],receipt["issues"])
