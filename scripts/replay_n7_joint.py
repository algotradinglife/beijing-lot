"""Thin entry point: freeze every R plan, then evaluate the frozen study."""
import argparse
from pathlib import Path
from src.n7_joint_study import freeze_joint_study, evaluate_joint_study

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--source", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--config", default="config/n7_joint_424.json")
    cli.add_argument("--python", required=True)
    cli.add_argument("--rscript", required=True)
    args = cli.parse_args()
    freeze_joint_study(args.source, args.output, args.config, repository_root=Path.cwd(),
                       python=args.python, rscript=args.rscript)
    print("ALL R PLANS FROZEN; opening settlement", flush=True)
    evaluate_joint_study(args.source, args.output, repository_root=Path.cwd())
