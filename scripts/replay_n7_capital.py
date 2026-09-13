"""Freeze all #425 plans before opening settlement; no import-time execution."""
import argparse
import json
from pathlib import Path
from src.n7_joint_study import freeze_prefix_study, evaluate_prefix_study
from src.n7_capital_study import describe_capital_plan

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("source", "output", "config", "python", "rscript"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    freeze_prefix_study(args.source, args.output, args.config, repository_root=Path.cwd(),
        python=args.python, rscript=args.rscript, entry_point=config["entry_point"],
        r_sources=config["r_sources"])
    print("ALL CAPITAL PLANS FROZEN; opening settlement", flush=True)
    evaluate_prefix_study(args.source, args.output, repository_root=Path.cwd(),
        describe_plan=describe_capital_plan, reference_arms=config["reference_arms"],
        reference_seeds=config["reference_seeds"])
