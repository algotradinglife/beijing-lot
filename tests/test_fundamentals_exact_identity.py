
import copy
import hashlib
import json
from pathlib import Path
import pytest
from src.fundamentals_exact_identity import exact_identity_match, replay_exact_identity
from src.temporal_learning import Cutoff


@pytest.mark.parametrize("field", ["issue", "slot", "provider_id", "market", "roster_ids", "source_ids", "cutoff_utc", "approved"])
def test_exact_decision_cannot_escape_fixture(field):
    f=dict(issue="100902", slot=62, native_match_id="429493", home_id="907", away_id="646")
    p=dict(provider_id="429493", home_team_id="3177", away_team_id="646")
    c=Cutoff.decision_epoch("100902","2010-09-03T18:30:00Z")
    d=dict(issue="100902",slot=62,provider_id="429493",market="euro",
        roster_ids=["907","646"],source_ids=["3177","646"],cutoff_utc=c.cutoff_ts.isoformat(),
        approved=True,adjudication_id="test")
    before=copy.deepcopy((f,p,d))
    assert exact_identity_match(f,p,d,market="euro",cutoff=c)["original_ids_preserved"]
    assert (f,p,d)==before
    d[field]=False if field=="approved" else "different"
    with pytest.raises(ValueError):
        exact_identity_match(f,p,d,market="euro",cutoff=c)


def test_replay_bound_files_and_original_cutoff(tmp_path, monkeypatch):
    import src.fundamentals_exact_identity as m
    import src.nowscore_settlement as settlement
    f=dict(issue="100902",slot=62,native_match_id="429493",home_id="907",away_id="646",
        status="完场",cutoff_text="截止时间：2010-09-04 02:30",kickoff_time="02:45")
    p=dict(provider_id="429493",home_team_id="3177",away_team_id="646",
        kickoff_utc="2010-09-03T18:45:00Z",quotes=[
            dict(quote_id="1",quoted_at="2010-09-03T18:29:00Z",odds_W=40,odds_D=12,odds_L=1),
            dict(quote_id="2",quoted_at="2010-09-03T18:30:00Z",odds_W=40,odds_D=12,odds_L=1)])
    paths=[]
    for name in ["roster","capture","peer"]:
        path=tmp_path/name;path.write_text(name);paths.append(path)
    d=dict(issue="100902",slot=62,provider_id="429493",market="euro",roster_ids=["907","646"],
        source_ids=["3177","646"],cutoff_utc="2010-09-03T18:30:00+00:00",
        approved=True,adjudication_id="test",roster_path=str(paths[0]),
        capture_path=str(paths[1]),peer_path=str(paths[2]),
        files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    config=tmp_path/"config.json";config.write_text(json.dumps([d]))
    monkeypatch.setattr(m,"read_response",lambda path: ({},b"roster"))
    monkeypatch.setattr(settlement,"parse_page",lambda *args: [f])
    monkeypatch.setattr(m,"corroborated_euro",lambda *args: dict(parsed=p))
    result=replay_exact_identity(config,repository_root=Path.cwd())
    assert result==replay_exact_identity(config,repository_root=Path.cwd())
    assert result["fixtures"][0]["prior_companies"]==1
    assert result["quotes"][0]["quote_id"]=="1"
    original_manifest = copy.deepcopy(d["files"])
    d["files"] = {}
    config.write_text(json.dumps([d]))
    with pytest.raises(ValueError, match="hash manifest"):
        replay_exact_identity(config, repository_root=Path.cwd())
    d["files"] = original_manifest
    original_path = d["capture_path"]
    d["capture_path"] = str(tmp_path / "unbound")
    config.write_text(json.dumps([d]))
    with pytest.raises(ValueError, match="hash manifest"):
        replay_exact_identity(config, repository_root=Path.cwd())
    d["capture_path"] = original_path
    config.write_text(json.dumps([d]))
    f["status"]="推迟" 
    with pytest.raises(ValueError,match="status/date"):
        replay_exact_identity(config,repository_root=Path.cwd())
    f["status"]="完场"
    paths[1].write_text("changed")
    with pytest.raises(ValueError,match="evidence changed"):
        replay_exact_identity(config,repository_root=Path.cwd())
    config.write_text(json.dumps([d,d]))
    with pytest.raises(ValueError,match="Duplicate"):
        replay_exact_identity(config,repository_root=Path.cwd())
    config.write_text("[]")
    assert replay_exact_identity(config,repository_root=Path.cwd())["fixtures"]==[]
