import copy
import hashlib
import json

import pytest

from src.n7_exchange_replay import replay_group_exchange, verify_exchange_provenance


def test_greedy_failure_mandatory_and_cutoff():
    cuts = {"a": "epoch"}
    x = dict(cutoffs=cuts, opening_options=[1, 2, 3], opportunity_options=[],
             options=[dict(sleeve_id=j, stake=6 if j == 0 else 4,
                           expected_gross=10 if j == 0 else 8, unit_copies=1) for j in range(3)],
             train=dict(cutoffs=cuts, hits=[[1, 1, 0], [1, 1, 0], [1, 0, 1],
                                          [1, 1, 0], [1, 0, 1], [0, 0, 1]]))
    assert replay_group_exchange(x, cuts, [1], 8, 1) == [1]
    assert replay_group_exchange(x, cuts, [1], 8, 2) == [2, 3]
    assert replay_group_exchange(x, cuts, [2, 3], 8, 2) == [2, 3]
    altered = copy.deepcopy(x)
    altered["future_labels"] = [9, 9, 9]
    assert replay_group_exchange(altered, cuts, [1], 8, 2) == [2, 3]
    x["opportunity_options"] = [1]
    assert replay_group_exchange(x, cuts, [1], 8, 2) == [1]
    with pytest.raises(ValueError):
        replay_group_exchange(x, cuts, [2], 8, 2)
    with pytest.raises(ValueError):
        replay_group_exchange(x, {}, [1], 8, 2)


def test_empty_and_ties():
    cuts = {"a": "epoch"}
    x = dict(cutoffs=cuts, options=[], opening_options=[], opportunity_options=[],
             train=dict(cutoffs=cuts, hits=[[], []]))
    assert replay_group_exchange(x, cuts, [], 8, 2) == []
    x.update(options=[dict(sleeve_id=j, stake=4, expected_gross=10, unit_copies=1) for j in range(3)],
             opening_options=[1, 2, 3], train=dict(cutoffs=cuts, hits=[[1, 1, 1], [0, 1, 1]]))
    assert replay_group_exchange(x, cuts, [1], 4, 1) == [2]
    assert replay_group_exchange(x, cuts, [3], 4, 1) == [3]


def test_provenance_checks_code_clocks_and_delegates_source_mutation(tmp_path, monkeypatch):
    names = ["r/n7_capital_portfolio.R", "r/n7_core_opportunity.R", "r/n7_frozen_scenarios.R",
             "r/n7_group_exchange.R", "scripts/run_n7_group_exchanges.R", "src/n7_quality_replay.py"]
    hashes = {}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    cuts = {"issue": {"a": "epoch"}}
    frozen = dict(implementation=hashes, cutoffs=cuts, input_binding=json.dumps(dict(cutoffs=cuts)))
    prior = dict(frozen, config=dict(catalog="catalog", rank_dir="ranks"))
    calls = []
    monkeypatch.setattr("src.n7_exchange_replay.verify_union_binding", lambda *args: calls.append(args) or True)
    assert verify_exchange_provenance(frozen, prior, tmp_path)
    assert len(calls) == 1
    altered = copy.deepcopy(frozen)
    altered["cutoffs"]["issue"]["a"] = "later"
    with pytest.raises(ValueError, match="cutoff"):
        verify_exchange_provenance(altered, prior, tmp_path)
    (tmp_path / names[0]).write_text("mutated")
    with pytest.raises(ValueError, match="implementation changed"):
        verify_exchange_provenance(frozen, prior, tmp_path)
    (tmp_path / names[0]).write_text("original")
    monkeypatch.setattr("src.n7_exchange_replay.verify_union_binding", lambda *args: False)
    with pytest.raises(ValueError, match="source verification"):
        verify_exchange_provenance(frozen, prior, tmp_path)
