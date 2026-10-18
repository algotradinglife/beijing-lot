"""Thin entry for an explicitly inventoried, reviewed fundamentals audit bundle."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_audit_bundle import publish_fundamentals_audit

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--issue",required=True)
    parser.add_argument("--label",required=True)
    args=parser.parse_args()
    result=publish_fundamentals_audit(json.loads(args.inventory.read_text()),
        issue=args.issue,label=args.label,receipt=json.loads(args.receipt.read_text()),
        environ=dict(os.environ))
    print(json.dumps(result,ensure_ascii=False,indent=2))
