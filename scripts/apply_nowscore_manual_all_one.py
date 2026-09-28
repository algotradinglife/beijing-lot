#!/usr/bin/env python3
"""Thin entry point for explicitly approved Nowscore all-one decisions."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.nowscore_manual_all_one import apply_decisions  # noqa: E402
from src.nowscore_settlement import canonical  # noqa: E402


def main(argv=None):
    """Parse explicit paths, issue:slot targets and zoned review time; no defaults."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-db',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',action='append',required=True)
    p.add_argument('--reviewed-at',required=True)
    p.add_argument('--zero-target',action='append',default=[],help='Explicitly reviewed original-zero exception, issue:slot')
    a = p.parse_args(argv)
    targets = []
    for value in a.target:
        try:
            issue, slot = value.split(':')
            targets.append((issue,int(slot)))
        except ValueError:
            p.error('targets must have issue:slot format')
    try:
        zero_targets = tuple((v.split(':')[0], int(v.split(':')[1])) for v in a.zero_target if len(v.split(':'))==2)
        if len(zero_targets) != len(a.zero_target):
            raise ValueError('invalid zero target')
    except ValueError:
        p.error('zero targets must have issue:slot format')
    result = apply_decisions(a.source_db,a.output,targets,a.reviewed_at,zero_targets)
    print(canonical({k:v for k,v in result.items() if k!='ledger'}))


if __name__ == '__main__':
    main()
