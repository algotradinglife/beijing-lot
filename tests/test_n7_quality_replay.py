import copy

import pytest

from src.n7_quality_replay import replay_quality, validate_quality_manifest, validate_quality_funded


def test_quality_replay_band_overlap_cash_and_contract():
    cutoff = {"fixture": "2020-01-01T00:00:00Z"}
    s = {"cutoffs": cutoff, "opening_options": [1, 2, 3], "opportunity_options": [],
         "options": [dict(sleeve_id=j, stake=4, coverage=p, expected_gross=5,
                          unit_copies=1, fixtures=list(range(1, 8)) if j < 2 else list(range(8, 15)))
                     for j, p in enumerate([.5, .49, .46])],
         "train": {"cutoffs": cutoff, "hits": [[1, 1, 0], [1, 1, 0], [0, 0, 1], [0, 0, 1]]}}
    assert replay_quality(s, cutoff, 8, .95, "UNION") == [1, 2]
    assert replay_quality(s, cutoff, 8, .90, "UNION") == [1, 3]
    assert replay_quality(s, cutoff, 2, .95, "UNION") == []
    t = copy.deepcopy(s)
    t["options"][2]["coverage"] = .48
    assert replay_quality(t, cutoff, 8, .95, "OVERLAP") == [1, 3]
    t["future_label"] = "arbitrary mutation"
    assert replay_quality(t, cutoff, 8, .95, "OVERLAP") == [1, 3]
    with pytest.raises(ValueError):
        replay_quality(s, {}, 8, .95, "UNION")
    with pytest.raises(ValueError):
        replay_quality(s, cutoff, 9, .95, "UNION")
    s["train"]["hits"][0][0] = 2
    with pytest.raises(ValueError):
        replay_quality(s, cutoff, 8, .95, "UNION")


def test_quality_replay_empty():
    cutoff = {"fixture": "2020-01-01T00:00:00Z"}
    s = dict(cutoffs=cutoff, options=[], opening_options=[], opportunity_options=[],
             train=dict(cutoffs=cutoff, hits=[[], []]))
    assert replay_quality(s, cutoff, 8, .95, "UNION") == []


def test_manifest_requires_all_snapshot_hashes():
    receipt = dict(cutoffs={str(i): {} for i in range(200)}, config=dict(seeds=[42501, 42502, 42503]))
    with pytest.raises(ValueError):
        validate_quality_manifest(receipt)
    names = {"predictions.csv", "funded.csv", "actions.csv", "candidates.csv"}
    names.update(f"replay-{i}-{s}.json.gz" for i in range(200) for s in receipt["config"]["seeds"])
    receipt["files"] = {name: "a" * 64 for name in names}
    assert len(validate_quality_manifest(receipt)) == 604
    receipt["files"].pop("replay-0-42501.json.gz")
    with pytest.raises(ValueError):
        validate_quality_manifest(receipt)


def test_funded_ticket_transfer_is_rejected():
    options = [dict(sleeve_id=j, depth=2, stake=4, unit_copies=1, coverage=.3, expected_gross=5) for j in range(2)]
    records = [dict(sleeve_id=j, depth=2, stake=4, copies=1, coverage=.3, expected_gross=5) for j in range(2)]
    validate_quality_funded(dict(options=options), [1, 2], records)
    records[0].update(depth=1, stake=2)
    records[1].update(depth=3, stake=6)
    with pytest.raises(ValueError, match="prefix"):
        validate_quality_funded(dict(options=options), [1, 2], records)
