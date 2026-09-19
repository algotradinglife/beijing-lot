"""Check persistent storage and deliver cleaning lifecycle messages to Codex queue."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_cleaning_notify import notify_cleaning_events, notify_cleaning_poll

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--poll-state',choices=['STARTED','BUSY'])
    args=parser.parse_args()
    if args.poll_state:
        print(json.dumps(notify_cleaning_poll(args.config,args.poll_state),ensure_ascii=False))
        sys.exit(0)
    root=check_layout(args.contract)['data_root']
    print(json.dumps(notify_cleaning_events(root,args.config),ensure_ascii=False))
