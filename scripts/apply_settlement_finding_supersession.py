#!/usr/bin/env python3
"""Apply an approved supersession of findings that a later correction resolved.

Re-codes the named findings so consumers are no longer told about a contradiction the
sealed database no longer contains. Backs the database up before writing and records the
original code, the original detail and the reason in the database itself.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settlement_finding_supersession import supersede_findings
from src.settlement_storage import validate_settlement_storage


def main(argv=None):
    """Validate explicit storage, then supersede one approved finding class."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'ledger', 'backup', 'data-root'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--mountpoint', type=Path)
    parser.add_argument('--approval-note', required=True)
    args = parser.parse_args(argv)
    validate_settlement_storage(args.data_root, [args.database, args.backup],
                                mountpoint=args.mountpoint)
    print(json.dumps(supersede_findings(args.database, args.ledger, args.backup,
                                        approval_note=args.approval_note),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
