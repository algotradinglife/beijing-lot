"""Create the portable #425 QMD input after independent full-study checks."""
import argparse
import json
from pathlib import Path
from src.n7_capital_archive import package_capital_report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('study','destination','example-issue'):parser.add_argument(f'--{key}',required=True)
    args=parser.parse_args()
    print(json.dumps(package_capital_report(args.study,args.destination,repository_root=Path.cwd(),
        example_issue=args.example_issue),sort_keys=True))
