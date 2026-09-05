"""Offline acceptance contracts for the #408 facts and adjudication pipeline."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.fundamentals_census import canonical
from src import fundamentals_pipeline as pipeline

REPO = Path(__file__).resolve().parents[1]
def materialize_bundle(root: Path) -> Path:
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "materialize_fundamentals_pipeline_fixture.py"),
                             "--output-dir", str(root)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["bundle_dir"] == str(root)
    return root


def rewrite_manifest(root: Path, manifest: dict) -> None:
    (root / "bundle-manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    digest = hashlib.sha256((root / "bundle-manifest.json").read_bytes()).hexdigest()
    (root / "bundle-manifest.sha256").write_text(f"{digest}  bundle-manifest.json\n", encoding="utf-8")


@pytest.fixture
def bundle(tmp_path):
    return materialize_bundle(tmp_path / "bundle")


def test_bundle_and_normalized_contracts_detect_tampering(bundle, tmp_path):
    validated = pipeline.validate_bundle(bundle)
    assert validated["file_count"] > 10
    assert pipeline.sha256_file(bundle / "bundle-manifest.json") == validated["manifest_sha256"]
    output = tmp_path / "normalized"
    from src.fundamentals_census import build_outputs
    build_outputs(bundle / "raw_main", output, generated_at_utc="2026-09-05T12:00:00Z")
    release = pipeline.read_normalized_release(output)
    assert release["tables"]["history"][0]["score_scope"] == "SOURCE_PUBLISHED_FULL_TIME"
    (output / "history.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        pipeline.read_normalized_release(output)
    (bundle / "agreement-spotchecks.v1.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="bundle file hash mismatch"):
        pipeline.validate_bundle(bundle)


@pytest.mark.parametrize("missing_kind", ["audit", "evidence"])
def test_bundle_rejects_consumed_files_absent_from_manifest(bundle, missing_kind):
    manifest = json.loads((bundle / "bundle-manifest.json").read_text())
    if missing_kind == "audit":
        missing = "independent-cases.v1.json"
    else:
        record = json.loads((bundle / "independent-cases.v1.json").read_text())[0]
        missing = record["independent_evidence"][0]["file"]
    manifest["files"].pop(missing)
    rewrite_manifest(bundle, manifest)
    with pytest.raises(ValueError, match="consumed bundle file absent from manifest"):
        pipeline.validate_bundle(bundle)


def test_audits_bind_both_sources_and_reject_unknown_upstream(bundle, tmp_path):
    releases = {}
    for scope in pipeline.SCOPES:
        output = tmp_path / scope
        from src.fundamentals_census import build_outputs
        build_outputs(bundle / f"raw_{scope}", output, generated_at_utc="2026-09-05T12:00:00Z")
        releases[scope] = pipeline.read_normalized_release(output)
    audits = pipeline.validate_audits(bundle, releases)
    assert len(audits) == 1 and len(audits[0]["evidence"]) == 1
    assert audits[0]["scope"] == "regression"
    path = bundle / "independent-cases.v1.json"
    records = json.loads(path.read_text())
    valid_records = copy.deepcopy(records)
    empty_hash_records = copy.deepcopy(records)
    for observation in empty_hash_records[0]["observations"]:
        observation.pop("raw_sha256", None)
        observation["sha256"] = ""
    path.write_text(canonical(empty_hash_records), encoding="utf-8")
    with pytest.raises(ValueError, match="source hash not present"):
        pipeline.validate_audits(bundle, releases)
    records = copy.deepcopy(valid_records)
    records[0]["slot"] = "999"
    path.write_text(canonical(records), encoding="utf-8")
    with pytest.raises(ValueError, match="key not present"):
        pipeline.validate_audits(bundle, releases)
    records = valid_records
    records[0]["independent_evidence"][0]["statistical_upstream"] = "UNKNOWN"
    path.write_text(canonical(records), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown/shared"):
        pipeline.validate_audits(bundle, releases)
    for missing in ("", "   ", None):
        records[0]["independent_evidence"][0]["statistical_upstream"] = missing
        path.write_text(canonical(records), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown/shared"):
            pipeline.validate_audits(bundle, releases)
    for missing in ("", "   ", None):
        records[0]["independent_evidence"][0].update(
            statistical_upstream="NOT_RELIED_ON", independence=missing)
        path.write_text(canonical(records), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown/shared"):
            pipeline.validate_audits(bundle, releases)
    records[0]["independent_evidence"][0].update(
        statistical_upstream="VENDOR_X", independence="THIRD_PARTY")
    path.write_text(canonical(records), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown/shared"):
        pipeline.validate_audits(bundle, releases)
    for source_upstream in ("Nowscore", "Titan007", "now-score / titan-007"):
        records = copy.deepcopy(valid_records)
        records[0]["independent_evidence"][0].update(
            statistical_upstream=source_upstream,
            independence="INDEPENDENT_THIRD_PARTY_WITH_DOCUMENTED_UPSTREAM")
        path.write_text(canonical(records), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown/shared"):
            pipeline.validate_audits(bundle, releases)


def test_audits_reject_empty_independent_evidence_body(bundle, tmp_path):
    releases = {}
    for scope in pipeline.SCOPES:
        output = tmp_path / scope
        from src.fundamentals_census import build_outputs
        build_outputs(bundle / f"raw_{scope}", output, generated_at_utc="2026-09-05T12:00:00Z")
        releases[scope] = pipeline.read_normalized_release(output)
    audit_path = bundle / "independent-cases.v1.json"
    reviews = json.loads(audit_path.read_text())
    evidence_path = bundle / reviews[0]["independent_evidence"][0]["file"]
    receipt = json.loads(evidence_path.read_text())
    empty_hash = hashlib.sha256(b"").hexdigest()
    receipt.update(body_base64="", byte_count=0, sha256=empty_hash)
    evidence_path.write_text(canonical(receipt), encoding="utf-8")
    reviews[0]["independent_evidence"][0]["sha256"] = empty_hash
    audit_path.write_text(canonical(reviews), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence body is empty"):
        pipeline.validate_audits(bundle, releases)


def test_validated_negative_spotcheck_uses_history_id_and_rejects_null_fixture_identity(bundle, tmp_path):
    from src.fundamentals_census import build_outputs
    releases = {}
    for scope in pipeline.SCOPES:
        output = tmp_path / scope
        build_outputs(bundle / f"raw_{scope}", output, generated_at_utc="2026-09-05T12:00:00Z")
        releases[scope] = pipeline.read_normalized_release(output)
    main_history = releases["main"]["tables"]["history"]
    common_ids = {row["history_id"] for row in main_history if row["source"] == "nowscore"} & {
        row["history_id"] for row in main_history if row["source"] == "titan"}
    history_id = sorted(common_ids)[0]
    template = json.loads((bundle / "independent-cases.v1.json").read_text())[0]
    observations = []
    for source in ("nowscore", "titan"):
        history_row = next(row for row in main_history if row["source"] == source and row["history_id"] == history_id)
        response = next(row for row in releases["main"]["tables"]["responses"]
                        if row["source"] == source and row["provider_id"] == history_row["provider_id"])
        observations.append({"source": source, "analysis_provider_id": history_row["provider_id"],
                             "raw_sha256": response["sha256"],
                             "observation": {name: history_row[name] for name in
                                             ("block", "history_id", "event_date", "home_id", "away_id",
                                              "home_score", "away_score")}})
    review = {name: template[name] for name in
              ("schema", "revision", "independent_evidence", "rationale", "reviewer", "reviewed_at_utc",
               "availability_class", "settlement_mutation", "model_admission")}
    review.update(case_kind="AGREEMENT_SPOTCHECK", target_history_id=history_id,
                  disposition="TIME_SEMANTICS_UNRESOLVED", observations=observations)
    (bundle / "independent-cases.v1.json").write_text("[]\n", encoding="utf-8")
    (bundle / "agreement-spotchecks.v1.json").write_text(canonical([review]) + "\n", encoding="utf-8")
    audits = pipeline.validate_audits(bundle, releases)
    assert audits[0]["issue"] == "" and audits[0]["target_history_id"] == history_id
    tables = pipeline.derive_release_tables("r1", releases, audits)
    assert not any(f":{history_id}:" in row["fact_key"] for row in tables["facts"])
    assert any(row["field"].endswith(f":{history_id}") for row in tables["quarantine"])
    review["issue"] = None
    (bundle / "agreement-spotchecks.v1.json").write_text(canonical([review]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only target_history_id"):
        pipeline.validate_audits(bundle, releases)
    review.pop("issue")
    review["target_history_id"] = "999999999999"
    (bundle / "agreement-spotchecks.v1.json").write_text(canonical([review]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must match target_history_id"):
        pipeline.validate_audits(bundle, releases)


def synthetic_release(*, swapped=False, kickoff_changed=False, missing_history=False):
    identity_left = {"issue": "001", "slot": "1", "provider_id": "00023", "source": "nowscore",
                     "home": "甲", "away": "乙", "home_id": "0010", "away_id": "0020",
                     "kickoff_utc": "2026-09-05T12:00:00+00:00"}
    identity_right = {**identity_left, "source": "titan"}
    if swapped:
        identity_right.update(home="乙", away="甲", home_id="0020", away_id="0010")
    if kickoff_changed:
        identity_right["kickoff_utc"] = "2026-09-05T13:00:00+00:00"
    history = {"issue": "001", "slot": "1", "provider_id": "00023", "source": "nowscore",
               "block": "h_data", "history_id": "00009", "event_date": "2026-08-01",
               "home_id": "0010", "away_id": "0030", "home_score": "0", "away_score": "1",
               "halftime_home_score": "0", "halftime_away_score": "0",
               "score_scope": "SOURCE_PUBLISHED_FULL_TIME"}
    history_rows = [history]
    if not missing_history:
        history_rows.append({**history, "source": "titan"})
    findings = []
    if swapped or kickoff_changed:
        findings.append({"issue": "001", "slot": "1", "provider_id": "00023", "field": "home",
                         "left": '"甲"', "right": '"乙"', "disposition": "IDENTITY_AMBIGUOUS"})
    if missing_history:
        findings.append({"issue": "001", "slot": "1", "provider_id": "00023", "field": "h_data:00009",
                         "left": canonical([["2026-08-01", "0010", "0030", 0, 1, 0, 0]]), "right": "[]",
                         "disposition": "COVERAGE_DIFFERENCE"})
    fields = []
    for source in ("nowscore", "titan"):
        fields.extend([
            {"issue": "001", "slot": "1", "provider_id": "00023", "source": source,
             "field": "season_tables", "field_state": "POPULATED",
             "observed_value": '[{"side":"home","state":"POPULATED","team_id":"0010","values":[1,1,0,0,2,0,2,3,1]},{"side":"away","state":"POPULATED","team_id":"0020","values":[1,1,0,0,2,0,2,3,1]}]',
             "evidence_class": "OBSERVED"},
            {"issue": "001", "slot": "1", "provider_id": "00023", "source": source,
             "field": "schedules", "field_state": "POPULATED",
             "observed_value": '[{"away":"丙","competition":"联赛","event_date":"2026-09-06","home":"甲","published_lead_days":1}]',
             "evidence_class": "OBSERVED"},
        ])
    return {"receipt": {}, "tables": {"panel": [{"issue": "001", "slot": "1", "provider_id": "00023"}],
            "identity": [identity_left, identity_right], "fields": fields, "history": history_rows,
            "findings": findings, "responses": [], "denominator": []}}


def audit(disposition, *, scope="main", revision=1, targets=None):
    if targets is None:
        targets = [{"field": "event_instance_semantics", "left": "", "right": ""}]
    qualified_targets = [{"scope": scope, "issue": "001", "slot": "1", "provider_id": "00023", **target}
                         for target in targets]
    return {"review_id": str(revision) * 64, "review_kind": scope, "scope": scope,
            "issue": "001", "slot": "1",
            "provider_id": "00023", "target_history_id": "", "revision": revision, "disposition": disposition,
            "reviewer": "reviewer", "reviewed_at_utc": "2026-09-05T12:00:00Z", "rationale": "reviewed",
            "availability_class": "HISTORICAL_PROXY", "evidence": [{"url": "https://club.example", "sha256": "b" * 64}],
            "targets": qualified_targets, "record": {}}


def agreement_spotcheck(disposition, *, revision=1):
    return {"review_id": ("a" if revision == 1 else "c") * 64,
            "review_kind": "AGREEMENT_SPOTCHECK", "scope": "", "issue": "", "slot": "",
            "provider_id": "00009", "target_history_id": "00009", "revision": revision,
            "disposition": disposition, "reviewer": "reviewer",
            "reviewed_at_utc": "2026-09-05T12:00:00Z", "rationale": "spot checked",
            "availability_class": "HISTORICAL_PROXY",
            "evidence": [{"url": "https://club.example", "sha256": "b" * 64}],
            "targets": [], "record": {}}


@pytest.mark.parametrize("changed", ["swapped", "kickoff"])
def test_identity_variants_quarantine_entire_fixture(changed):
    release = synthetic_release(swapped=changed == "swapped", kickoff_changed=changed == "kickoff")
    tables = pipeline.derive_release_tables("r1", {"main": release}, [])
    assert tables["canonical_identity"][0]["identity_status"] == "QUARANTINED"
    assert tables["facts"] == []
    assert any(row["field"] == "*" for row in tables["quarantine"])


def test_missing_is_not_zero_and_coverage_is_quarantined():
    release = synthetic_release(missing_history=True)
    tables = pipeline.derive_release_tables("r1", {"main": release}, [])
    assert not any(row["fact_type"] == "prior_match" for row in tables["facts"])
    assert tables["discrepancy_queue"][0]["status"] == "QUARANTINED_MISSINGNESS"
    exact = pipeline.derive_release_tables("r2", {"main": synthetic_release()}, [])
    prior = next(row for row in exact["facts"] if row["fact_type"] == "prior_match")
    assert json.loads(prior["value_json"])["home_score"] == "0"
    assert {row["fact_type"] for row in exact["facts"]} >= {"fixture_identity", "standings_snapshot", "adjacent_schedule"}


def test_unresolved_duplicate_history_order_cannot_export_as_agreement():
    release = synthetic_release()
    first = release["tables"]["history"][0]
    second = {**first, "home_score": "2"}
    release["tables"]["history"] = [first, second,
                                    {**second, "source": "titan"},
                                    {**first, "source": "titan"},
                                    {**first, "block": "v_data"},
                                    {**first, "source": "titan", "block": "v_data"}]
    value_fields = ("event_date", "home_id", "away_id", "home_score", "away_score",
                    "halftime_home_score", "halftime_away_score", "score_scope")
    left = [[row[field] for field in value_fields] for row in (first, second)]
    right = [[row[field] for field in value_fields]
             for row in ({**second, "source": "titan"}, {**first, "source": "titan"})]
    release["tables"]["findings"] = [{"issue": "001", "slot": "1", "provider_id": "00023",
                                        "field": "h_data:00009", "left": canonical(left),
                                        "right": canonical(right), "disposition": "UNRESOLVED"}]
    tables = pipeline.derive_release_tables("r1", {"main": release}, [])
    assert not any(row["fact_type"] == "prior_match" for row in tables["facts"])
    assert any(row["field"] == "h_data:00009" and row["reason"] == "UNRESOLVED_QUARANTINED"
               for row in tables["quarantine"])
    assert any(row["field"] == "v_data:00009" and row["reason"] == "CROSS_CONTEXT_HISTORY_CONFLICT"
               for row in tables["quarantine"])


def test_cross_block_history_conflict_quarantines_every_occurrence():
    release = synthetic_release()
    first = release["tables"]["history"][0]
    release["tables"]["history"].extend([
        {**first, "block": "v_data", "home_score": "2"},
        {**first, "source": "titan", "block": "v_data", "home_score": "2"},
    ])
    release["tables"]["findings"] = []
    tables = pipeline.derive_release_tables("r1", {"main": release}, [])
    assert not any(row["fact_type"] == "prior_match" for row in tables["facts"])
    conflicts = [row for row in tables["quarantine"]
                 if row["reason"] == "CROSS_CONTEXT_HISTORY_CONFLICT"]
    assert {row["field"] for row in conflicts} == {"h_data:00009", "v_data:00009"}
    left = '[["2026-08-01","0010","0030",0,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    right = '[["2026-08-01","0010","0030",2,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    release["tables"]["findings"] = [{"issue": "001", "slot": "1", "provider_id": "00023",
                                        "field": "v_data:00009", "left": left, "right": right,
                                        "disposition": "UNRESOLVED"}]
    reviewed = audit("PRIOR_MATCH_CORROBORATED", targets=[
        {"field": "v_data:00009", "left": left, "right": right, "resolved_value": right}])
    resolved = pipeline.derive_release_tables("r2", {"main": release}, [reviewed])
    assert not any(row["fact_type"] == "prior_match" for row in resolved["facts"])


def test_concordant_cross_scope_history_resolutions_export_facts():
    main = synthetic_release()
    main["tables"]["history"][1]["home_score"] = "2"
    left = '[["2026-08-01","0010","0030",0,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    right = '[["2026-08-01","0010","0030",2,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    finding = {"issue": "001", "slot": "1", "provider_id": "00023",
               "field": "h_data:00009", "left": left, "right": right,
               "disposition": "UNRESOLVED"}
    main["tables"]["findings"] = [finding]
    regression = copy.deepcopy(main)
    target = {"field": finding["field"], "left": left, "right": right,
              "resolved_value": left}
    main_review = audit("PRIOR_MATCH_CORROBORATED", scope="main", targets=[target])
    regression_review = audit("PRIOR_MATCH_CORROBORATED", scope="regression", targets=[target])
    regression_review["review_id"] = "2" * 64
    tables = pipeline.derive_release_tables(
        "r1", {"main": main, "regression": regression}, [main_review, regression_review])
    prior = [row for row in tables["facts"] if row["fact_type"] == "prior_match"]
    assert len(prior) == 2
    assert {row["scope"] for row in prior} == {"main", "regression"}
    assert {row["verification_status"] for row in prior} == {"INDEPENDENTLY_RESOLVED"}
    assert not any(row["reason"] == "CROSS_CONTEXT_HISTORY_CONFLICT"
                   for row in tables["quarantine"])

    regression_review["targets"][0]["resolved_value"] = right
    conflicting = pipeline.derive_release_tables(
        "r2", {"main": main, "regression": regression}, [main_review, regression_review])
    assert not any(row["fact_type"] == "prior_match" for row in conflicting["facts"])
    assert sum(row["reason"] == "CROSS_CONTEXT_HISTORY_CONFLICT"
               for row in conflicting["quarantine"]) == 2


def test_reschedule_and_replay_reviews_quarantine_while_period_review_can_resolve():
    release = synthetic_release()
    for disposition in ("RESCHEDULED_EVENT_INSTANCE_QUARANTINED", "RESTART_EVENT_INSTANCE_QUARANTINED",
                        "ORIGINAL_REPLAY_IDENTITY_GUARD", "TIME_SEMANTICS_UNRESOLVED"):
        tables = pipeline.derive_release_tables("r1", {"main": release}, [audit(disposition)])
        assert tables["canonical_identity"][0]["identity_status"] == "QUARANTINED"
        assert tables["discrepancy_queue"][0]["status"] == "QUARANTINED_REVIEWED"
    resolved = pipeline.derive_release_tables("r2", {"main": release}, [audit("REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED")])
    assert resolved["canonical_identity"][0]["identity_status"] == "REVIEWED_CANONICAL"
    assert resolved["discrepancy_queue"][0]["status"] == "INDEPENDENTLY_RESOLVED"
    assert any(row["fact_type"] == "prior_match" for row in resolved["facts"])
    negative = pipeline.derive_release_tables(
        "r3", {"main": release}, [audit("NOT_CORROBORATED")])
    assert negative["canonical_identity"][0]["identity_status"] == "QUARANTINED"
    assert negative["discrepancy_queue"][0]["status"] == "QUARANTINED_REVIEWED"


def test_audits_are_scope_bound_and_only_latest_revision_controls_state():
    release = synthetic_release()
    regression_review = audit("REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED", scope="regression")
    scoped = pipeline.derive_release_tables(
        "r1", {"main": release, "regression": release}, [regression_review])
    identities = {(row["scope"], row["review_ids_json"]) for row in scoped["canonical_identity"]}
    assert ("main", "[]") in identities
    assert ("regression", canonical([regression_review["review_id"]])) in identities
    assert {row["scope"] for row in scoped["discrepancy_queue"] if row["review_id"]} == {"regression"}

    older = audit("TIME_SEMANTICS_UNRESOLVED", revision=1)
    newer = audit("REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED", revision=2)
    revised = pipeline.derive_release_tables("r2", {"main": release}, [older, newer])
    assert revised["canonical_identity"][0]["identity_status"] == "REVIEWED_CANONICAL"
    assert json.loads(revised["canonical_identity"][0]["review_ids_json"]) == [newer["review_id"]]
    assert revised["discrepancy_queue"][0]["status"] == "INDEPENDENTLY_RESOLVED"
    assert revised["discrepancy_queue"][0]["review_id"] == newer["review_id"]
    assert len(revised["adjudications"]) == 2


def test_reordered_multi_target_revision_supersedes_older_review():
    release = synthetic_release()
    history = release["tables"]["history"]
    history.extend([{**row, "history_id": "00008"} for row in list(history)])
    targets = []
    for history_id in ("00009", "00008"):
        left = canonical([["2026-08-01", "0010", "0030", 0, 1, 0, 0,
                           "SOURCE_PUBLISHED_FULL_TIME"]])
        right = canonical([["2026-08-01", "0010", "0030", 2, 1, 0, 0,
                            "SOURCE_PUBLISHED_FULL_TIME"]])
        for row in history:
            if row["history_id"] == history_id and row["source"] == "titan":
                row["home_score"] = "2"
        release["tables"]["findings"].append({
            "issue": "001", "slot": "1", "provider_id": "00023",
            "field": f"h_data:{history_id}", "left": left, "right": right,
            "disposition": "UNRESOLVED",
        })
        targets.append({"field": f"h_data:{history_id}", "left": left, "right": right})
    older = audit("TIME_SEMANTICS_UNRESOLVED", revision=1, targets=targets)
    newer_targets = [{**target, "resolved_value": target["left"]} for target in reversed(targets)]
    newer = audit("PRIOR_MATCH_CORROBORATED", revision=2, targets=newer_targets)
    tables = pipeline.derive_release_tables("r3", {"main": release}, [older, newer])
    resolved = [row for row in tables["discrepancy_queue"] if row["field"].startswith("h_data:")]
    assert len(resolved) == 2
    assert {row["status"] for row in resolved} == {"INDEPENDENTLY_RESOLVED"}
    assert {row["review_id"] for row in resolved} == {newer["review_id"]}


def test_adjudication_resolves_only_its_exact_discrepancy_target():
    release = synthetic_release()
    finding = {"issue": "001", "slot": "1", "provider_id": "00023", "field": "season_tables",
               "left": "[[1]]", "right": "[[2]]", "disposition": "UNRESOLVED"}
    release["tables"]["findings"] = [finding]
    broad = pipeline.derive_release_tables(
        "r1", {"main": release}, [audit("REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED")])
    standings = next(row for row in broad["discrepancy_queue"] if row["field"] == "season_tables")
    assert standings["status"] == "UNRESOLVED_QUARANTINED"
    assert standings["review_id"] == ""

    release["tables"]["fields"][0]["observed_value"] = finding["left"]
    release["tables"]["fields"][2]["observed_value"] = finding["right"]
    resolved_standings = '[{"side":"home","state":"POPULATED","team_id":"0010","values":[9,1,0,0,2,0,2,3,1]},{"side":"away","state":"POPULATED","team_id":"0020","values":[9,1,0,0,2,0,2,3,1]}]'
    target = {"field": finding["field"], "left": finding["left"], "right": finding["right"],
              "resolved_value": resolved_standings}
    exact = pipeline.derive_release_tables(
        "r2", {"main": release}, [audit("STANDINGS_CORROBORATED", targets=[target])])
    standings = next(row for row in exact["discrepancy_queue"] if row["field"] == "season_tables")
    assert standings["status"] == "INDEPENDENTLY_RESOLVED"
    assert standings["review_id"]
    assert json.loads(exact["adjudications"][0]["targets_json"])[0]["field"] == "season_tables"
    resolved_fact = next(row for row in exact["facts"] if row["fact_type"] == "standings_snapshot")
    assert resolved_fact["value_json"] == resolved_standings
    assert resolved_fact["verification_status"] == "INDEPENDENTLY_RESOLVED"
    assert resolved_fact["review_id"] == standings["review_id"]
    assert json.loads(resolved_fact["evidence_json"])[0]["url"] == "https://club.example"
    assert resolved_fact["availability_class"] == "HISTORICAL_PROXY"

    for row in release["tables"]["fields"]:
        if row["field"] == "season_tables":
            row["evidence_class"] = "HISTORICAL_PROXY"
    observed_review = audit("STANDINGS_CORROBORATED", targets=[target])
    observed_review["availability_class"] = "OBSERVED"
    conservative = pipeline.derive_release_tables("r2b", {"main": release}, [observed_review])
    conservative_fact = next(row for row in conservative["facts"]
                             if row["fact_type"] == "standings_snapshot")
    assert conservative_fact["availability_class"] == "HISTORICAL_PROXY"

    for row in release["tables"]["fields"]:
        if row["field"] == "season_tables":
            row["evidence_class"] = "OBSERVED"
    observed_review["availability_class"] = "DOCUMENTED_CONSERVATIVE_SAFE_BOUNDARY"
    safe_boundary = pipeline.derive_release_tables("r2c", {"main": release}, [observed_review])
    safe_boundary_fact = next(row for row in safe_boundary["facts"]
                              if row["fact_type"] == "standings_snapshot")
    assert safe_boundary_fact["availability_class"] == "DOCUMENTED_CONSERVATIVE_SAFE_BOUNDARY"

    wrong_teams = resolved_standings.replace('0010', '9999').replace('0020', '8888')
    with pytest.raises(ValueError, match="standings teams do not match"):
        pipeline.derive_release_tables(
            "r3", {"main": release}, [audit("STANDINGS_CORROBORATED", targets=[
                {**target, "resolved_value": wrong_teams}])])

    bad_target = {**target, "right": "[[3]]"}
    with pytest.raises(ValueError, match="target not present"):
        pipeline.derive_release_tables(
            "r3", {"main": release}, [audit("STANDINGS_CORROBORATED", targets=[bad_target])])


def test_resolved_discrepancy_requires_canonical_value_and_exports_history():
    release = synthetic_release()
    right = release["tables"]["history"][1]
    right["home_score"] = "2"
    left_value = '[["2026-08-01","0010","0030",0,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    right_value = '[["2026-08-01","0010","0030",2,1,0,0,"SOURCE_PUBLISHED_FULL_TIME"]]'
    release["tables"]["findings"] = [{"issue": "001", "slot": "1", "provider_id": "00023",
                                           "field": "h_data:00009", "left": left_value,
                                           "right": right_value, "disposition": "UNRESOLVED"}]
    incomplete = {"field": "h_data:00009", "left": left_value, "right": right_value}
    with pytest.raises(ValueError, match="resolved_value"):
        pipeline.derive_release_tables(
            "r1", {"main": release}, [audit("PRIOR_MATCH_CORROBORATED", targets=[incomplete])])
    noncanonical = {**incomplete, "resolved_value": '[["2026-08-01", "0010"]]'}
    with pytest.raises(ValueError, match="canonical JSON"):
        pipeline.resolved_json(noncanonical)
    invalid_score = {**incomplete,
                     "resolved_value": '[["2026-08-01","0010","0030",-1,1,0,0,"garbage"]]'}
    with pytest.raises(ValueError, match="typed fact contract"):
        pipeline.resolved_json(invalid_score)
    assert pipeline.resolved_json(
        {"field": "season_tables",
         "resolved_value": '[{"side":"home","state":"POPULATED","team_id":"10","values":[10,2,2,6,8,20,-12,8,17]},{"side":"away","state":"POPULATED","team_id":"20","values":[10,2,2,6,8,20,-12,8,17]}]'}) == \
        '[{"side":"home","state":"POPULATED","team_id":"10","values":[10,2,2,6,8,20,-12,8,17]},{"side":"away","state":"POPULATED","team_id":"20","values":[10,2,2,6,8,20,-12,8,17]}]'
    schedule_value = '[{"away":"丙","competition":"联赛","event_date":"2026-09-06","home":"甲","published_lead_days":1}]'
    assert pipeline.resolved_json({"field": "schedules", "resolved_value": schedule_value}) == schedule_value
    with pytest.raises(ValueError, match="schedule value"):
        pipeline.resolved_json({"field": "schedules", "resolved_value": '[["09-06","甲-丙"]]'})
    target = {**incomplete, "resolved_value": left_value}
    tables = pipeline.derive_release_tables(
        "r2", {"main": release}, [audit("PRIOR_MATCH_CORROBORATED", targets=[target])])
    fact = next(row for row in tables["facts"] if row["fact_key"] == "h_data:00009:1")
    assert json.loads(fact["value_json"])["home_score"] == "0"
    assert fact["verification_status"] == "INDEPENDENTLY_RESOLVED"
    assert fact["review_id"] == tables["discrepancy_queue"][0]["review_id"]
    assert pipeline.target_key({"scope": "main", "issue": "001", "slot": "1", "provider_id": "00023", **target}) == pipeline.target_key(
        {"scope": "main", "issue": "001", "slot": "1", "provider_id": "00023", **incomplete})


def test_failed_agreement_spotcheck_quarantines_every_matching_history_fact():
    release = synthetic_release()
    failed = agreement_spotcheck("TIME_SEMANTICS_UNRESOLVED")
    tables = pipeline.derive_release_tables(
        "r1", {"main": release, "regression": copy.deepcopy(release)}, [failed])
    assert not any("00009" in row["fact_key"] for row in tables["facts"])
    quarantined = [row for row in tables["quarantine"] if row["field"] == "h_data:00009"]
    assert len(quarantined) == 2
    assert all(json.loads(row["review_ids_json"]) == [failed["review_id"]] for row in quarantined)

    accepted = agreement_spotcheck("INDEPENDENTLY_CORROBORATED_CHECKED_FACT_ONLY")
    checked = pipeline.derive_release_tables("r2", {"main": release}, [accepted])
    fact = next(row for row in checked["facts"] if row["fact_key"] == "h_data:00009:1")
    assert fact["verification_status"] == "AGREED_UNVERIFIED"
    assert fact["review_id"] == accepted["review_id"]


def test_identity_discrepancy_cannot_claim_resolution_without_canonical_identity_support():
    release = synthetic_release(swapped=True)
    finding = release["tables"]["findings"][0]
    target = {"field": finding["field"], "left": finding["left"], "right": finding["right"],
              "resolved_value": finding["left"]}
    result = pipeline.derive_release_tables(
        "r1", {"main": release}, [audit("FIXTURE_IDENTITY_CORROBORATED", targets=[target])])
    assert result["canonical_identity"][0]["identity_status"] == "QUARANTINED"
    assert result["discrepancy_queue"][0]["status"] == "QUARANTINED_REVIEWED"
    assert result["facts"] == []


def test_pipeline_replay_freezes_release_and_rolls_back_failures(bundle, tmp_path, monkeypatch):
    first = tmp_path / "release-a"
    second = tmp_path / "release-b"
    kwargs = {"generated_at_utc": "2026-09-05T12:00:00Z", "release_id": "fixture-v1"}
    receipt_a = pipeline.run_pipeline(bundle, first, **kwargs)
    receipt_b = pipeline.run_pipeline(bundle, second, **kwargs)
    assert receipt_a == receipt_b
    assert receipt_a["historical_learning"] == "NONE"
    assert receipt_a["row_counts"]["facts"] > 0
    loaded = pipeline.read_release(first)
    assert loaded["receipt"] == receipt_a
    frozen_hash = hashlib.sha256((first / "receipt.json").read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        pipeline.run_pipeline(bundle, first, **kwargs)
    assert hashlib.sha256((first / "receipt.json").read_bytes()).hexdigest() == frozen_hash
    incomplete = json.loads((first / "receipt.json").read_text())
    incomplete["output_hashes"] = {}
    (first / "receipt.json").write_text(canonical(incomplete), encoding="utf-8")
    with pytest.raises(ValueError, match="missing #408 output hashes"):
        pipeline.read_release(first)
    (second / "facts.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="release hash mismatch"):
        pipeline.read_release(second)

    bad_bundle = tmp_path / "bad-bundle"
    shutil.copytree(bundle, bad_bundle)
    reviews = json.loads((bad_bundle / "independent-cases.v1.json").read_text())
    reviews[0]["observations"][0]["sha256"] = "0" * 64
    (bad_bundle / "independent-cases.v1.json").write_text(canonical(reviews), encoding="utf-8")
    files = json.loads((bad_bundle / "bundle-manifest.json").read_text())
    files["files"]["independent-cases.v1.json"] = hashlib.sha256((bad_bundle / "independent-cases.v1.json").read_bytes()).hexdigest()
    (bad_bundle / "bundle-manifest.json").write_text(canonical(files) + "\n", encoding="utf-8")
    (bad_bundle / "bundle-manifest.sha256").write_text(
        f"{hashlib.sha256((bad_bundle / 'bundle-manifest.json').read_bytes()).hexdigest()}  bundle-manifest.json\n", encoding="utf-8")
    failed = tmp_path / "failed"
    with pytest.raises(ValueError, match="source hash"):
        pipeline.run_pipeline(bad_bundle, failed, **kwargs)
    assert not failed.exists()
    assert not list(tmp_path.glob(".fundamentals-408-*"))

    mutable_bundle = tmp_path / "mutable-bundle"
    shutil.copytree(bundle, mutable_bundle)
    original_validate = pipeline.validate_bundle
    calls = 0

    def validate_then_mutate(path):
        nonlocal calls
        result = original_validate(path)
        calls += 1
        if calls == 1:
            audit_path = mutable_bundle / "independent-cases.v1.json"
            reviews = json.loads(audit_path.read_text())
            reviews[0]["disposition"] = "TIME_SEMANTICS_UNRESOLVED"
            audit_path.write_text(canonical(reviews), encoding="utf-8")
        return result

    monkeypatch.setattr(pipeline, "validate_bundle", validate_then_mutate)
    changed_input = tmp_path / "changed-input"
    with pytest.raises(ValueError, match="bundle file hash mismatch"):
        pipeline.run_pipeline(mutable_bundle, changed_input, **kwargs)
    assert not changed_input.exists()
    assert not list(tmp_path.glob(".fundamentals-408-*"))
