#!/usr/bin/env python3
"""Apply an approved, externally corroborated half/full settlement correction ledger.

Corrects the half/full option and relocates its settlement SP for fixtures whose
half time the source recorded wrongly. Backs the database up before writing and
records the correction, its evidence manifest and the original build receipt.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settlement_half_full_update import apply_half_full_update
from src.settlement_storage import validate_settlement_storage


def main(argv=None):
    """Validate explicit storage, then apply one independently corroborated ledger."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'ledger', 'backup', 'data-root'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--mountpoint', type=Path)
    parser.add_argument('--approval-note', required=True)
    args = parser.parse_args(argv)
    validate_settlement_storage(args.data_root, [args.database, args.backup],
                                mountpoint=args.mountpoint)
    print(json.dumps(apply_half_full_update(args.database, args.ledger, args.backup,
                                            approval_note=args.approval_note),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
