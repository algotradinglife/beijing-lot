"""Thin independent replay entry point."""
import argparse
import json
from pathlib import Path
from src.n7_joint_check import check_joint_study

if __name__ == "__main__":
    cli = argparse.ArgumentParser(); cli.add_argument("--study", required=True)
    args = cli.parse_args()
    print(json.dumps(check_joint_study(args.study, repository_root=Path.cwd()), sort_keys=True))
