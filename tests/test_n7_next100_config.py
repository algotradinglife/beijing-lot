"""The new control selects exactly the already agreed #425 arm."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_control_is_an_exact_subset_of_frozen_original_parameters():
    parent_path = ROOT / 'config/n7_capital_425.json'
    parent = json.loads(parent_path.read_text())
    child = json.loads((ROOT / 'config/n7_next100_control_435.json').read_text())
    assert child['inherited_configuration']['sha256'] == hashlib.sha256(parent_path.read_bytes()).hexdigest()
    assert child['budgets'] == [1024]
    assert child['arms'] == ['NONUNIFORM_ANY_ROI_NONE_B1024']
    assert child['preferences'] == [p for p in parent['preferences'] if p['name'] == 'ANY_ROI_NONE']
    assert child['coverage_targets'] == child['equal_depths'] == child['reference_arms'] == child['reference_seeds'] == []
    restricted = {'budgets', 'arms', 'preferences', 'coverage_targets', 'equal_depths',
                  'reference_arms', 'reference_seeds', 'workers', 'inherited_configuration'}
    assert {k:v for k,v in child.items() if k not in restricted} == {
        k:v for k,v in parent.items() if k not in restricted}
    assert child['unit_cny'] == 2 and child['payout_factor'] == .65
