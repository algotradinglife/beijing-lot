"""Replay every sealed capital allocation and its source-bound shared worlds."""
import argparse
import json
from pathlib import Path
from src.n7_joint_check import check_prefix_study
from src.n7_capital_check import check_capital_plan, check_capital_result

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--study',required=True)
    args=parser.parse_args()
    print(json.dumps(check_prefix_study(args.study,repository_root=Path.cwd(),check_plan=check_capital_plan,
        check_result=check_capital_result),sort_keys=True))
