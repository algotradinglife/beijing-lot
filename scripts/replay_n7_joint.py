"""Thin entry point: freeze every R plan, then evaluate the frozen study."""
import argparse
import json
from pathlib import Path
from src.n7_joint_study import freeze_prefix_study, evaluate_prefix_study, describe_joint_plan, JOINT_R_SOURCES

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--source", required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--config", default="config/n7_joint_424.json")
    cli.add_argument("--python", required=True)
    cli.add_argument("--rscript", required=True)
    args = cli.parse_args()
    freeze_prefix_study(args.source, args.output, args.config, repository_root=Path.cwd(),
                       python=args.python, rscript=args.rscript,
                       entry_point="scripts/run_n7_joint_issue.R", r_sources=JOINT_R_SOURCES)
    print("ALL R PLANS FROZEN; opening settlement", flush=True)
    evaluate_prefix_study(args.source, args.output, repository_root=Path.cwd(),
        describe_plan=describe_joint_plan,
        reference_arms=("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512"),
        reference_seeds=json.loads(Path(args.config).read_text())["seeds"])
