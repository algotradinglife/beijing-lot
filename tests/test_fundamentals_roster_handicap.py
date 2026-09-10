import gzip
import pytest
from pathlib import Path
from src.fundamentals_roster_handicap import roster_handicaps
from src import fundamentals_roster_handicap as module


@pytest.fixture
def receipt(tmp_path):
    path = tmp_path / "roster.json"
    path.write_bytes(gzip.decompress(Path("tests/fixtures/fundamentals_pilot/roster.json.gz").read_bytes()))
    return path


def test_real_saved_roster(receipt):
    rows = roster_handicaps(receipt, issue="100101", slots=[1, 3, 5])
    assert [r["home_handicap"] for r in rows] == [0, -2, 1]
    assert [r["provider_id"] for r in rows] == ["358101", "356276", "356278"]
    assert all(not r["historical_admission"] for r in rows)
    with pytest.raises(ValueError):
        roster_handicaps(receipt, issue="100102", slots=[1])
    with pytest.raises(ValueError):
        roster_handicaps(receipt, issue="100101", slots=[999])


@pytest.mark.parametrize("slots", [[], [1, 1], [True], [0], [1.5]])
def test_invalid_slots(receipt, slots):
    with pytest.raises(ValueError):
        roster_handicaps(receipt, issue="100101", slots=slots)


def test_invalid_handicap_and_transport(receipt, monkeypatch):
    meta, body = module.read_response(receipt)
    monkeypatch.setattr(module, "read_response", lambda _: (meta, body.replace(b'polygoal="0"', b'polygoal="0.5"', 1)))
    with pytest.raises(ValueError, match="integer lottery"):
        roster_handicaps(receipt, issue="100101", slots=[1])
    monkeypatch.setattr(module, "read_response", lambda _: ({**meta, "status": 500}, body))
    with pytest.raises(ValueError, match="successful"):
        roster_handicaps(receipt, issue="100101", slots=[1])
