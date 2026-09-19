import copy
import hashlib
import pytest
from src.fundamentals_analysis_identity import analysis_identity_view


def test_exact_analysis_view_preserves_raw_history_and_rejects_unbound_changes(tmp_path):
    evidence = tmp_path / "independent.json"
    evidence.write_text("verified fixture")
    fixture = dict(issue="100609", slot=2, provider_id="355292", home_id="649", away_id="803")
    obs = [dict(issue="100609", slot=2, provider_id="355292", source=s, home="South Africa", away="France", home_id="803", away_id="649", kickoff_utc="2010-06-22T14:00:00+00:00", raw_sha256=s) for s in ("titan", "nowscore")]
    fields = [dict(issue="100609", slot=2, source=s, raw_fields=dict(home_history_raw=[["historical home", 3, 0]], away_history_raw=[["historical away", 0, 2]], head_to_head_raw=[["H2H", 1, 1]], standings={"home":"original source home"})) for s in ("titan", "nowscore")]
    report = dict(fixtures=[fixture], observations=obs, page_fields=fields, clean=dict(cutoffs={"2":"2010-06-22T13:30:00+00:00"}))
    original = copy.deepcopy(report)
    decision = dict(issue="100609", slot=2, provider_id="355292", roster_ids=["649","803"], source_ids=["803","649"], action="REVERSE_ANALYSIS_ORIENTATION", cutoff_utc="2010-06-22T13:30:00+00:00", independent_evidence_path="independent.json", evidence_files={"independent.json":hashlib.sha256(evidence.read_bytes()).hexdigest()}, analysis_sources={o["source"]:{k:o[k] for k in ("raw_sha256","home_id","away_id","kickoff_utc","provider_id")} for o in obs})
    view, ledger = analysis_identity_view(report,[decision],repository_root=tmp_path)
    assert report == original
    assert view["observations"][0]["home_id"] == "649"
    assert view["page_fields"][0]["raw_fields"]["home_history_raw"] == [["historical away",0,2]]
    assert view["page_fields"][0]["raw_fields"]["head_to_head_raw"] == [["H2H",1,1]]
    assert view["page_fields"][0]["raw_fields"]["standings"] == fields[0]["raw_fields"]["standings"]
    assert ledger[0]["historical_admission"] is False
    alias=copy.deepcopy(decision); alias["action"]="EXACT_ANALYSIS_FIXTURE_IDENTITY"
    view,_=analysis_identity_view(report,[alias],repository_root=tmp_path)
    assert view["fixtures"][0]["home_id"]=="803"
    assert view["page_fields"]==fields
    assert analysis_identity_view(report,[],repository_root=tmp_path)==(report,[])
    for key,value in (("slot",3),("provider_id","different"),("roster_ids",["1","2"]),("source_ids",["1","2"]),("action","GLOBAL_ALIAS"),("cutoff_utc","2010-06-22T14:30:00+00:00"),("independent_evidence_path","absent"),("evidence_files",{})):
        bad=copy.deepcopy(decision);bad[key]=value
        with pytest.raises(ValueError): analysis_identity_view(report,[bad],repository_root=tmp_path)
    bad=copy.deepcopy(decision);bad["analysis_sources"]["titan"]["raw_sha256"]="wrong"
    with pytest.raises(ValueError): analysis_identity_view(report,[bad],repository_root=tmp_path)
    with pytest.raises(ValueError): analysis_identity_view(report,[decision,decision],repository_root=tmp_path)
    evidence.write_text("mutated")
    with pytest.raises(ValueError): analysis_identity_view(report,[decision],repository_root=tmp_path)
