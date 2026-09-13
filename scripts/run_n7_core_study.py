"""Thin offline #433 freeze/evaluate entry; all inputs and runtimes explicit."""
import argparse
from pathlib import Path

from src.n7_joint_study import freeze_prefix_study, evaluate_prefix_study
from src.n7_core_settlement import settle_core_layers
from src.n7_core_study import CORE_R_SOURCES, describe_core_plan

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['freeze', 'evaluate'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository-root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--rscript', type=Path, required=True)
    args = parser.parse_args()
    if args.phase == 'freeze':
        freeze_prefix_study(args.source, args.output, args.config, repository_root=args.repository_root,
                            python=args.python, rscript=args.rscript,
                            entry_point='scripts/run_n7_core_issue.R', r_sources=CORE_R_SOURCES)
    else:
        evaluate_prefix_study(args.source, args.output, repository_root=args.repository_root,
                              describe_plan=describe_core_plan, settle_plan=settle_core_layers,
                              reference_arms=[], reference_seeds=[])
