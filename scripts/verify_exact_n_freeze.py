#!/usr/bin/env python3
"""Semantic verifier for a BJ-BET-FREEZE-001 matrix directory."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("directory",type=Path); a=p.parse_args(); root=a.directory
    files=sorted(root.glob("exact_n_*_budget_*.json"))
    if len(files)!=15: raise SystemExit("expected 15 N×budget cells")
    common=None
    for path in files:
        x=json.loads(path.read_text()); key=(x["segment_match_indices"],x["decision_input_sha256"],x["scheduled_freeze_at"])
        common=common or key
        if key!=common or x["requested_n"]!=x["artifact_n"]!=x["recommended_n"]: raise SystemExit("semantic identity/N mismatch")
        if x["actual_budget_yuan"]>x["requested_budget_yuan"]: raise SystemExit("budget exceeded")
        if any(t["actual_n"]!=x["requested_n"] for t in x["tickets"]): raise SystemExit("N=4→3 or other leg fallback")
    sums={line.split("  ")[1]:line.split("  ")[0] for line in (root/"SHA256SUMS").read_text().splitlines()}
    for path in files:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sums.get(path.name): raise SystemExit("SHA256SUMS mismatch")
    print(json.dumps({"status":"PASS","cells":15,"shared_freeze_at":common[2]}))
if __name__=="__main__": main()
