"""Replay and package #433 after the complete frozen study has been settled."""
import argparse
import json
from pathlib import Path
from src.n7_core_archive import package_core_report

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','destination','frozen-source-root','checker-root','baseline-archive'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--baseline-body-sha256',required=True)
    parser.add_argument('--baseline-arm',required=True)
    args=vars(parser.parse_args())
    print(json.dumps(package_core_report(**args),sort_keys=True))
