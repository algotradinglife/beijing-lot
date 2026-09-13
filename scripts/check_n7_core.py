"""Replay all frozen #433 candidate features, physical layers and model risk."""
import argparse
import json
from pathlib import Path
from src.n7_joint_check import check_prefix_study
from src.n7_core_check import check_core_plan, check_core_result

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(check_prefix_study(args.study,repository_root=args.source_root,
        check_plan=check_core_plan,check_result=check_core_result,physical_plans=lambda p:p['layers']),sort_keys=True))
