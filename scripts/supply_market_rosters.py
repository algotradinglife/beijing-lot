"""Storage-checked entry point for the independent market roster supplier."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_roster_supply import supply_rosters

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'plan-path', 'output', 'ledger-path', 'budget-id'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--request-budget', type=int, required=True)
    args = vars(parser.parse_args())
    contract = args.pop('contract')
    layout = check_layout(contract)
    root = Path(layout['data_root']).resolve()
    for name in ('plan_path', 'output', 'ledger_path'):
        if not Path(args[name]).resolve().is_relative_to(root):
            raise ValueError('supplier path outside persistent root')
    plan = json.loads(Path(args['plan_path']).read_text())
    if not Path(plan['roster_root']).resolve().is_relative_to(root/'shared/fixtures'):
        raise ValueError('roster destination outside shared fixtures')
    result = supply_rosters(**args)
    check_layout(contract)
    print(json.dumps(result), flush=True)
    sys.exit(0 if result['state'] == 'COMPLETE' else 1)
