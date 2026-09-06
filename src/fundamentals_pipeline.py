"""Immutable #408 fundamentals audit and facts-release pipeline.

The pipeline replays sealed Nowscore/Titan responses through the shared pure
parser, validates independent evidence bytes, reviews canonical event identity,
quarantines unresolved discrepancies and publishes a content-bound facts release.
It performs no learning, settlement mutation, live capture or import-time I/O.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from src.fundamentals_census import build_outputs, canonical, read_response, write_rows

RELEASE_SCHEMA = "bj408_fundamentals_audit_v1"
NORMALIZED_SCHEMA = "bj407_diagnostic_census_v1"
AUDIT_SCHEMA = "bj407_independent_audit_v1"
SCOPES = ("main", "regression")
INDEPENDENCE_REJECT_TERMS = ("UNKNOWN", "SHARED")
ADJUDICATED_SOURCE_TERMS = ("NOWSCORE", "TITAN")
INDEPENDENCE_CLASSES = frozenset({
    "ORIGINAL_ORGANIZER_CLUB_OR_VENUE_DOCUMENT",
    "ORIGINAL_PARTICIPATING_CLUB_NARRATIVE",
    "ORIGINAL_COMPETITION_DOCUMENT",
    "ORIGINAL_FEDERATION_DOCUMENT",
    "ORIGINAL_PARTICIPATING_CLUB_DOCUMENT",
    "ORIGINAL_VENUE_DOCUMENT",
    "INDEPENDENT_THIRD_PARTY_WITH_DOCUMENTED_UPSTREAM",
})
RESOLVED_DISPOSITIONS = frozenset({
    "REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED",
    "FIXTURE_IDENTITY_CORROBORATED",
    "EVENT_INSTANCE_SEMANTICS_CORROBORATED",
    "PRIOR_MATCH_CORROBORATED",
    "STANDINGS_CORROBORATED",
    "ADJACENT_SCHEDULE_CORROBORATED",
})
AGREEMENT_ACCEPT_DISPOSITIONS = frozenset({"INDEPENDENTLY_CORROBORATED_CHECKED_FACT_ONLY"})
AVAILABILITY_CLASSES = frozenset({"OBSERVED", "HISTORICAL_PROXY", "DOCUMENTED_CONSERVATIVE_SAFE_BOUNDARY"})
TARGET_KEY_FIELDS = ("scope", "issue", "slot", "provider_id", "field", "left", "right")
HISTORY_FIELD_PATTERN = re.compile(r"(?:h_data|a_data|v_data):.+")


def corroborates_discrepancy(disposition: str) -> bool:
    """Return whether a review disposition explicitly declares corroboration."""
    return disposition in RESOLVED_DISPOSITIONS


def corroborates_target(disposition: str, field: str) -> bool:
    """Return whether an allowed disposition supports this exact field class."""
    if field == "event_instance_semantics":
        return disposition in {"REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED",
                               "FIXTURE_IDENTITY_CORROBORATED", "EVENT_INSTANCE_SEMANTICS_CORROBORATED"}
    if field == "season_tables":
        return disposition == "STANDINGS_CORROBORATED"
    if field == "schedules":
        return disposition == "ADJACENT_SCHEDULE_CORROBORATED"
    if HISTORY_FIELD_PATTERN.fullmatch(field):
        return disposition in {"PRIOR_MATCH_CORROBORATED", "REGULATION_EXTRA_TIME_DISTINCTION_CORROBORATED"}
    return False


def target_key(target: dict) -> str:
    """Return the exact source-discrepancy identity, excluding its adjudicated value."""
    return canonical({name: target[name] for name in TARGET_KEY_FIELDS})


def target_set_key(targets: list[dict]) -> str:
    """Return an order-independent identity for one review's target set."""
    return canonical(sorted(target_key(target) for target in targets))


def resolved_json(target: dict) -> str:
    """Return and validate one canonical JSON value selected by independent evidence."""
    value = target.get("resolved_value")
    if not isinstance(value, str) or not value:
        raise ValueError("corroborated discrepancy requires resolved_value")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("resolved_value must be canonical JSON") from exc
    if canonical(parsed) != value:
        raise ValueError("resolved_value must be canonical JSON")
    field = target.get("field", "")
    if field == "season_tables":
        if (not isinstance(parsed, list) or len(parsed) != 2 or
                [row.get("side") if isinstance(row, dict) else None for row in parsed] != ["home", "away"] or
                any(not re.fullmatch(r"\d+", str(row.get("team_id", ""))) or row.get("state") != "POPULATED" or
                    not isinstance(row.get("values"), list) or len(row["values"]) != 9 or
                    any(value is not None and
                        (type(value) is not int or (index not in {6, 7} and value < 0))
                        for index, value in enumerate(row["values"]))
                    for row in parsed)):
            raise ValueError("resolved standings value has invalid shape")
    if field == "schedules":
        if (not isinstance(parsed, list) or
                any(not isinstance(row, dict) or set(row) != {
                        "event_date", "competition", "home", "away", "published_lead_days"} or
                    any(not isinstance(row[name], str) or not row[name].strip()
                        for name in ("competition", "home", "away")) or
                    type(row["published_lead_days"]) is not int or row["published_lead_days"] < 0
                    for row in parsed)):
            raise ValueError("resolved schedule value has invalid shape")
        for row in parsed:
            try:
                datetime.strptime(row["event_date"], "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                raise ValueError("resolved schedule value has invalid event date") from exc
    if HISTORY_FIELD_PATTERN.fullmatch(field):
        if (not isinstance(parsed, list) or len(parsed) != 1 or
                any(not isinstance(row, list) or len(row) != 8 for row in parsed)):
            raise ValueError("resolved history value has invalid shape")
        for row in parsed:
            try:
                datetime.strptime(row[0], "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                raise ValueError("resolved history value has invalid event date") from exc
            if (any(not isinstance(value, str) or not value.isdigit() or int(value) <= 0 for value in row[1:3]) or
                    row[1] == row[2] or
                    any(type(value) is not int or value < 0 for value in row[3:5]) or
                    any(value is not None and (type(value) is not int or value < 0) for value in row[5:7]) or
                    row[7] != "SOURCE_PUBLISHED_FULL_TIME"):
                raise ValueError("resolved history value violates typed fact contract")
            if ((row[5] is not None and row[5] > row[3]) or
                    (row[6] is not None and row[6] > row[4])):
                raise ValueError("resolved halftime score exceeds full-time score")
    return value


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of one regular file."""
    if not path.is_file():
        raise ValueError(f"missing regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle(bundle_dir: str | Path) -> dict:
    """Validate the sealed #407 bundle manifest and every declared file."""
    root = Path(bundle_dir).resolve()
    manifest_path = root / "bundle-manifest.json"
    checksum_path = root / "bundle-manifest.sha256"
    checksum_parts = checksum_path.read_text(encoding="utf-8").strip().split()
    if checksum_parts != [sha256_file(manifest_path), "bundle-manifest.json"]:
        raise ValueError("bundle manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "bj407_census_bundle_v1" or manifest.get("historical_learning") != "NONE":
        raise ValueError("unsupported bundle contract")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("empty bundle manifest")
    for relative, expected in files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise ValueError("unsafe bundle manifest entry")
        if sha256_file(path) != expected:
            raise ValueError(f"bundle file hash mismatch: {relative}")
    consumed = {"independent-cases.v1.json", "agreement-spotchecks.v1.json"}
    for raw_dir in (root / "raw_main", root / "raw_regression"):
        consumed.update(str(path.relative_to(root)) for path in raw_dir.rglob("*") if path.is_file())
    for audit_file in ("independent-cases.v1.json", "agreement-spotchecks.v1.json"):
        if audit_file not in files:
            raise ValueError(f"consumed bundle file absent from manifest: {audit_file}")
        records = json.loads((root / audit_file).read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"invalid audit collection: {audit_file}")
        for record in records:
            evidence_items = record.get("independent_evidence", [])
            if isinstance(evidence_items, dict):
                evidence_items = [evidence_items]
            if isinstance(evidence_items, list):
                consumed.update(str(item.get("file", "")) for item in evidence_items if isinstance(item, dict))
    missing = sorted(relative for relative in consumed if not relative or relative not in files)
    if missing:
        raise ValueError(f"consumed bundle file absent from manifest: {missing[0]}")
    return {"root": str(root), "manifest_sha256": sha256_file(manifest_path), "file_count": len(files)}


def read_normalized_release(input_dir: str | Path) -> dict:
    """Read one normalized replay after validating its receipt and CSV hashes."""
    root = Path(input_dir)
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("schema") != NORMALIZED_SCHEMA or receipt.get("historical_learning") != "NONE":
        raise ValueError("unsupported normalized release")
    names = ("panel", "denominator", "responses", "identity", "fields", "history", "findings")
    expected_files = {f"{name}.csv" for name in names}
    hashes = receipt.get("output_hashes")
    if not isinstance(hashes, dict) or not expected_files.issubset(hashes):
        raise ValueError("missing normalized output hashes")
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if (not path.is_relative_to(root.resolve()) or
                not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or sha256_file(path) != expected):
            raise ValueError(f"normalized output hash mismatch: {relative}")
    tables = {}
    for name in names:
        with (root / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
            tables[name] = list(csv.DictReader(stream))
    return {"receipt": receipt, "tables": tables}


def validate_audits(bundle_dir: str | Path, releases: dict[str, dict]) -> list[dict]:
    """Validate versioned reviews, source observations and independent raw bytes.

    Unknown or shared upstream evidence cannot resolve or corroborate a fact.
    Search snippets and metadata-only receipts fail because original bytes and a
    successful exact URL are required. Returned rows retain all review versions.
    """
    root = Path(bundle_dir).resolve()
    source_rows = []
    history_rows = []
    panel_keys = set()
    for scope, release in releases.items():
        panel_keys.update((scope, row["issue"], row["slot"], row["provider_id"])
                          for row in release["tables"]["panel"])
        for row in release["tables"]["responses"]:
            source_rows.append({**row, "scope": scope})
        for row in release["tables"]["history"]:
            history_rows.append({**row, "scope": scope})
    results = []
    for filename, default_kind in (("independent-cases.v1.json", "DISCREPANCY_REVIEW"),
                                   ("agreement-spotchecks.v1.json", "AGREEMENT_SPOTCHECK")):
        records = json.loads((root / filename).read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"invalid audit collection: {filename}")
        for record in records:
            if record.get("schema") != AUDIT_SCHEMA or type(record.get("revision")) is not int or record["revision"] < 1:
                raise ValueError("invalid audit schema or revision")
            if not all(isinstance(record.get(name), str) and record[name].strip()
                       for name in ("reviewer", "rationale", "disposition", "reviewed_at_utc")):
                raise ValueError("incomplete audit review")
            reviewed = datetime.fromisoformat(record["reviewed_at_utc"].replace("Z", "+00:00"))
            if reviewed.utcoffset() is None or record.get("model_admission") is not False or record.get("settlement_mutation") is not False:
                raise ValueError("audit chronology/admission contract failure")
            if record.get("availability_class") not in AVAILABILITY_CLASSES:
                raise ValueError("invalid audit availability class")
            case_kind = record.get("case_kind", default_kind)
            if case_kind not in {*SCOPES, "AGREEMENT_SPOTCHECK"}:
                raise ValueError("unsupported audit case kind")
            scope = case_kind if case_kind in SCOPES else ""
            if case_kind == "AGREEMENT_SPOTCHECK":
                target_history_id = record.get("target_history_id")
                if (not isinstance(target_history_id, str) or not re.fullmatch(r"\d+", target_history_id) or
                        any(name in record for name in ("issue", "slot", "provider_id"))):
                    raise ValueError("agreement spot-check requires only target_history_id")
            elif any(name not in record or not str(record[name]).strip() for name in ("issue", "slot", "provider_id")):
                raise ValueError("fixture audit requires issue, slot and provider_id")
            elif (scope, str(record["issue"]), str(record["slot"]), str(record["provider_id"])) not in panel_keys:
                raise ValueError("fixture audit key not present in normalized panel")
            observations = record.get("observations")
            if not isinstance(observations, list) or len(observations) != 2 or {row.get("source") for row in observations} != {"nowscore", "titan"}:
                raise ValueError("audit must preserve both source observations")
            for observation in observations:
                if case_kind == "AGREEMENT_SPOTCHECK":
                    observed_history = observation.get("observation")
                    if (not isinstance(observed_history, dict) or
                            str(observed_history.get("history_id", "")) != target_history_id):
                        raise ValueError("agreement spot-check observation must match target_history_id")
                provider_id = str(observation.get("analysis_provider_id", record.get("provider_id", "")))
                response_matches = [row for row in source_rows if row["provider_id"] == provider_id
                                    and row["source"] == observation["source"]
                                    and (not scope or (row["scope"] == scope
                                                       and row["issue"] == str(record["issue"])
                                                       and row["slot"] == str(record["slot"])))]
                accepted_hashes = {value for row in response_matches
                                   for value in (row.get("sha256"), row.get("auxiliary_sha256"))
                                   if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)}
                observed_hash = observation.get("raw_sha256", observation.get("sha256"))
                if (not isinstance(observed_hash, str) or
                        not re.fullmatch(r"[0-9a-f]{64}", observed_hash) or observed_hash not in accepted_hashes):
                    raise ValueError("audit source hash not present in normalized release")
                if "identity" in observation:
                    identity_matches = []
                    for release_scope, release in releases.items():
                        identity_matches.extend(row for row in release["tables"]["identity"]
                                                if row["provider_id"] == provider_id and row["source"] == observation["source"]
                                                and (not scope or scope == release_scope))
                    expected_identity = observation["identity"]
                    fields = ("home", "away", "home_id", "away_id", "kickoff_utc")
                    if not any(all(row[field] == str(expected_identity[field]) for field in fields) for row in identity_matches):
                        raise ValueError("audit identity observation mismatch")
                if "observation" in observation:
                    expected = observation["observation"]
                    fields = ("block", "history_id", "event_date", "home_id", "away_id", "home_score", "away_score")
                    if not any(row["source"] == observation["source"] and row["provider_id"] == provider_id
                               and (not scope or row["scope"] == scope)
                               and all(row[field] == str(expected[field]) for field in fields) for row in history_rows):
                        raise ValueError("audit historical observation mismatch")
            evidence_items = record.get("independent_evidence")
            if isinstance(evidence_items, dict):
                evidence_items = [evidence_items]
            if not isinstance(evidence_items, list) or not evidence_items:
                raise ValueError("independent evidence required")
            evidence_rows = []
            for evidence in evidence_items:
                raw_independence = evidence.get("independence", evidence.get("publisher_scope"))
                raw_upstream = evidence.get("statistical_upstream")
                if (not isinstance(raw_independence, str) or not raw_independence.strip() or
                        not isinstance(raw_upstream, str) or not raw_upstream.strip()):
                    raise ValueError("unknown/shared evidence cannot adjudicate")
                independence = raw_independence.strip().upper()
                upstream = raw_upstream.strip().upper()
                normalized_upstream = re.sub(r"[^A-Z0-9]", "", upstream)
                if (independence not in INDEPENDENCE_CLASSES or
                        any(term in independence or term in upstream for term in INDEPENDENCE_REJECT_TERMS) or
                        any(term in normalized_upstream for term in ADJUDICATED_SOURCE_TERMS)):
                    raise ValueError("unknown/shared evidence cannot adjudicate")
                evidence_path = (root / str(evidence.get("file", ""))).resolve()
                if not evidence_path.is_relative_to(root):
                    raise ValueError("unsafe independent evidence path")
                metadata, evidence_bytes = read_response(evidence_path)
                if metadata["status"] != 200 or metadata["url"] != evidence.get("url") or metadata["final_url"] != evidence.get("final_url", evidence.get("url")):
                    raise ValueError("independent evidence transport mismatch")
                if not evidence_bytes:
                    raise ValueError("independent evidence body is empty")
                if metadata["sha256"] != evidence.get("sha256"):
                    raise ValueError("independent evidence hash mismatch")
                evidence_rows.append({"url": metadata["final_url"], "sha256": metadata["sha256"],
                                      "received_at_utc": metadata["received_at_utc"],
                                      "independence": independence, "statistical_upstream": upstream})
            raw_targets = record.get("targets")
            if raw_targets is None:
                raw_targets = ([{"field": "event_instance_semantics", "left": "", "right": ""}]
                               if record.get("issue") is not None else [])
            if not isinstance(raw_targets, list):
                raise ValueError("audit targets must be a list")
            targets = []
            for target in raw_targets:
                if (not isinstance(target, dict) or
                        not isinstance(target.get("field"), str) or not target["field"] or
                        not all(isinstance(target.get(name), str) for name in ("left", "right"))):
                    raise ValueError("incomplete audit discrepancy target")
                normalized_target = {"scope": scope, "issue": str(record.get("issue", "")),
                                     "slot": str(record.get("slot", "")),
                                     "provider_id": str(record.get("provider_id", record.get("target_history_id", ""))),
                                     "field": target["field"], "left": target["left"], "right": target["right"]}
                if "resolved_value" in target:
                    normalized_target["resolved_value"] = target["resolved_value"]
                if corroborates_discrepancy(record["disposition"]) and not corroborates_target(record["disposition"], target["field"]):
                    raise ValueError("audit disposition does not support target field")
                if corroborates_target(record["disposition"], target["field"]) and target["field"] != "event_instance_semantics":
                    resolved_json(normalized_target)
                elif "resolved_value" in normalized_target:
                    raise ValueError("resolved_value requires a corroborating discrepancy disposition")
                targets.append(normalized_target)
            review_id = hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()
            results.append({"review_id": review_id, "review_kind": case_kind, "scope": scope,
                            "issue": str(record.get("issue", "")), "slot": str(record.get("slot", "")),
                            "provider_id": str(record.get("provider_id", record.get("target_history_id", ""))),
                            "target_history_id": str(record.get("target_history_id", "")),
                            "revision": record["revision"], "disposition": record["disposition"],
                            "reviewer": record["reviewer"], "reviewed_at_utc": record["reviewed_at_utc"],
                            "rationale": record["rationale"], "availability_class": record.get("availability_class", ""),
                            "evidence": evidence_rows, "targets": targets, "record": record})
    revision_keys = [(row["review_kind"], row["scope"], row["issue"], row["slot"], row["provider_id"],
                      target_set_key(row["targets"]), row["revision"])
                     for row in results]
    if len(revision_keys) != len(set(revision_keys)):
        raise ValueError("duplicate audit revision")
    return results


def derive_release_tables(release_id: str, releases: dict[str, dict], audits: list[dict]) -> dict[str, list[dict]]:
    """Derive canonical identities, queue, adjudications, facts and quarantine.

    Dual-source agreement is explicitly unverified. Genuine differences are
    resolved only by validated independent evidence; all others remain excluded.
    Identity uncertainty quarantines the entire fixture and every dependent fact.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id):
        raise ValueError("invalid release ID")
    history_value_fields = ("event_date", "home_id", "away_id", "home_score", "away_score",
                            "halftime_home_score", "halftime_away_score", "score_scope")
    history_signatures = defaultdict(lambda: defaultdict(set))
    for scope, release in releases.items():
        for row in release["tables"]["history"]:
            context = (scope, row["issue"], row["slot"], row["provider_id"], row["block"])
            history_signatures[row["history_id"]][context].add(tuple(
                row.get(field, "") for field in history_value_fields))
    cross_context_history_conflicts = {
        history_id for history_id, contexts in history_signatures.items()
        if len(contexts) > 1 and len(set().union(*contexts.values())) > 1
    }
    cross_context_findings = defaultdict(list)
    for history_id in cross_context_history_conflicts:
        contexts = history_signatures[history_id]
        for context, signatures in contexts.items():
            scope, issue, slot, provider_id, block = context
            other_contexts = []
            for other_context, other_signatures in sorted(contexts.items()):
                if other_context == context:
                    continue
                other_contexts.append({
                    "scope": other_context[0], "issue": other_context[1], "slot": other_context[2],
                    "provider_id": other_context[3], "block": other_context[4],
                    "values": [list(value) for value in sorted(other_signatures)],
                })
            cross_context_findings[(scope, issue, slot, provider_id)].append({
                "issue": issue, "slot": slot, "provider_id": provider_id,
                "field": f"{block}:{history_id}",
                "left": canonical([list(value) for value in sorted(signatures)]),
                "right": canonical(other_contexts), "disposition": "UNRESOLVED",
            })
    disputed_history_ids = cross_context_history_conflicts | {
        finding["field"].split(":", 1)[1]
        for release in releases.values()
        for finding in release["tables"]["findings"]
        if HISTORY_FIELD_PATTERN.fullmatch(finding["field"])
    }
    audits_by_fixture = defaultdict(list)
    spotcheck_chains = defaultdict(list)
    for audit in audits:
        if audit["issue"]:
            audits_by_fixture[(audit.get("scope", ""), audit["issue"], audit["slot"], audit["provider_id"])].append(audit)
        elif audit["review_kind"] == "AGREEMENT_SPOTCHECK" and audit["target_history_id"]:
            spotcheck_chains[audit["target_history_id"]].append(audit)
    cross_context_resolutions = defaultdict(lambda: defaultdict(list))
    for fixture_context, fixture_audits in audits_by_fixture.items():
        revision_chains = defaultdict(list)
        for audit in fixture_audits:
            revision_chains[target_set_key(audit.get("targets", []))].append(audit)
        for audit in (max(chain, key=lambda row: row["revision"])
                      for chain in revision_chains.values()):
            for target in audit.get("targets", []):
                if (HISTORY_FIELD_PATTERN.fullmatch(target["field"]) and
                        corroborates_target(audit["disposition"], target["field"])):
                    block, history_id = target["field"].split(":", 1)
                    context = (*fixture_context, block)
                    cross_context_resolutions[history_id][context].append(resolved_json(target))
    reconciled_history_ids = {
        history_id for history_id in cross_context_history_conflicts
        if set(cross_context_resolutions[history_id]) == set(history_signatures[history_id])
        and all(len(values) == 1 for values in cross_context_resolutions[history_id].values())
        and len({values[0] for values in cross_context_resolutions[history_id].values()}) == 1
    }
    latest_spotchecks = {history_id: max(chain, key=lambda row: row["revision"])
                         for history_id, chain in spotcheck_chains.items()}
    identity_states = {}
    for scope, release in releases.items():
        identity_groups = defaultdict(list)
        finding_groups = defaultdict(list)
        for row in release["tables"]["identity"]:
            identity_groups[(row["issue"], row["slot"], row["provider_id"])].append(row)
        for row in release["tables"]["findings"]:
            finding_groups[(row["issue"], row["slot"], row["provider_id"])].append(row)
        for context, synthetic_findings in cross_context_findings.items():
            if context[0] != scope:
                continue
            fixture = context[1:]
            existing_fields = {row["field"] for row in finding_groups[fixture]}
            finding_groups[fixture].extend(
                row for row in synthetic_findings if row["field"] not in existing_fields)
        for panel in release["tables"]["panel"]:
            fixture = (panel["issue"], panel["slot"], panel["provider_id"])
            source_map = {row["source"]: row for row in identity_groups[fixture]}
            identity_fields = ("home", "away", "home_id", "away_id", "kickoff_utc")
            exact = set(source_map) == {"nowscore", "titan"} and all(
                source_map["nowscore"][field] == source_map["titan"][field] for field in identity_fields)
            revision_chains = defaultdict(list)
            for audit in audits_by_fixture[(scope, *fixture)]:
                revision_chains[target_set_key(audit.get("targets", []))].append(audit)
            latest_audits = sorted(
                (max(chain, key=lambda row: row["revision"]) for chain in revision_chains.values()),
                key=lambda row: (row["reviewed_at_utc"], row["review_id"]),
            )
            identity_field_names = {"home", "away", "home_id", "away_id", "kickoff_utc",
                                    "event_instance_semantics"}
            identity_audits = [audit for audit in latest_audits
                               if not audit.get("targets") or
                               all(target["field"] in identity_field_names or
                                   target["field"].startswith("roster_") or
                                   target["field"].startswith("panel_roster_")
                                   for target in audit["targets"])]
            identity_findings = [row for row in finding_groups[fixture]
                                 if row["disposition"] == "IDENTITY_AMBIGUOUS" or
                                 row["field"].startswith("roster_") or
                                 row["field"].startswith("panel_roster_")]
            semantic_quarantine = any(
                not all(corroborates_target(audit["disposition"], target["field"])
                        for target in audit["targets"])
                for audit in identity_audits)
            quarantined = not exact or bool(identity_findings) or semantic_quarantine
            identity_states[(scope, *fixture)] = {
                "source_map": source_map, "identity_fields": identity_fields, "exact": exact,
                "latest_audits": latest_audits, "identity_audits": identity_audits,
                "findings": finding_groups[fixture], "quarantined": quarantined,
            }
    quarantined_fixture_ids = {
        context[3] for context, state in identity_states.items() if state["quarantined"]
    }
    disputed_history_ids |= quarantined_fixture_ids
    identities = []
    queue = []
    adjudications = []
    facts = []
    quarantine = []
    for audit in audits:
        adjudications.append({"release_id": release_id, "review_id": audit["review_id"],
                              "review_kind": audit["review_kind"], "scope": audit.get("scope", ""), "issue": audit["issue"],
                              "slot": audit["slot"], "provider_id": audit["provider_id"],
                              "revision": audit["revision"], "disposition": audit["disposition"],
                              "reviewer": audit["reviewer"], "reviewed_at_utc": audit["reviewed_at_utc"],
                              "rationale": audit["rationale"], "availability_class": audit["availability_class"],
                              "targets_json": canonical(audit.get("targets", [])),
                              "evidence_json": canonical(audit["evidence"])})
    for scope, release in releases.items():
        tables = release["tables"]
        field_groups = defaultdict(list)
        history_groups = defaultdict(lambda: defaultdict(list))
        for row in tables["fields"]:
            field_groups[(row["issue"], row["slot"], row["provider_id"], row["field"])].append(row)
        for row in tables["history"]:
            fixture = (row["issue"], row["slot"], row["provider_id"])
            history_groups[fixture][(row["block"], row["history_id"])].append(row)
        for panel in tables["panel"]:
            fixture = (panel["issue"], panel["slot"], panel["provider_id"])
            state = identity_states[(scope, *fixture)]
            source_map, identity_fields, exact = state["source_map"], state["identity_fields"], state["exact"]
            latest_audits, identity_audits = state["latest_audits"], state["identity_audits"]
            fixture_findings, quarantined = state["findings"], state["quarantined"]
            identity_value = {field: source_map["nowscore"][field] for field in identity_fields} if exact else {}
            identities.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                               "provider_id": fixture[2], "identity_status": "QUARANTINED" if quarantined else "REVIEWED_CANONICAL",
                               "verification_status": "INDEPENDENTLY_REVIEWED" if identity_audits else "AGREED_UNVERIFIED",
                               "canonical_identity_json": canonical(identity_value),
                               "review_ids_json": canonical([row["review_id"] for row in identity_audits]),
                               "rationale": "; ".join(row["rationale"] for row in identity_audits) if identity_audits
                                            else "Exact Nowscore/Titan candidate identity reviewed under #408; no independent truth claim."})
            if quarantined:
                quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                   "provider_id": fixture[2], "field": "*", "reason": "IDENTITY_OR_EVENT_INSTANCE_UNRESOLVED",
                                   "review_ids_json": canonical([row["review_id"] for row in identity_audits])})
            else:
                facts.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                              "provider_id": fixture[2], "fact_type": "fixture_identity", "fact_key": fixture[2],
                              "value_json": canonical(identity_value), "verification_status": "AGREED_UNVERIFIED",
                              "source_count": 2, "availability_class": "HISTORICAL_PROXY",
                              "review_id": "", "evidence_json": "[]"})
            matched_targets = set()
            resolved_findings = {}
            for finding in fixture_findings:
                category = "COVERAGE_DIFFERENCE" if finding["disposition"] == "COVERAGE_DIFFERENCE" else "GENUINE_DISCREPANCY"
                discrepancy_target = {"scope": scope, "issue": fixture[0], "slot": fixture[1],
                                      "provider_id": fixture[2], "field": finding["field"],
                                      "left": finding["left"], "right": finding["right"]}
                discrepancy_key = target_key(discrepancy_target)
                matching_audits = [audit for audit in latest_audits
                                   if discrepancy_key in {target_key(target) for target in audit.get("targets", [])}]
                if len(matching_audits) > 1:
                    raise ValueError("multiple active audits target one discrepancy")
                latest = matching_audits[0] if matching_audits else None
                if latest:
                    matched_targets.add(discrepancy_key)
                if category == "COVERAGE_DIFFERENCE":
                    status = "QUARANTINED_MISSINGNESS"
                elif (latest and not (HISTORY_FIELD_PATTERN.fullmatch(finding["field"]) and
                                      finding["field"].split(":", 1)[1] in cross_context_history_conflicts and
                                      finding["field"].split(":", 1)[1] not in reconciled_history_ids)):
                    status = ("INDEPENDENTLY_RESOLVED" if corroborates_target(latest["disposition"], finding["field"])
                              else "QUARANTINED_REVIEWED")
                else:
                    status = "UNRESOLVED_QUARANTINED"
                discrepancy_id = hashlib.sha256(canonical({"scope": scope, **finding}).encode("utf-8")).hexdigest()
                queue.append({"release_id": release_id, "discrepancy_id": discrepancy_id, "scope": scope,
                              "issue": fixture[0], "slot": fixture[1], "provider_id": fixture[2],
                              "field": finding["field"], "left_value": finding["left"], "right_value": finding["right"],
                              "category": category, "status": status,
                              "review_id": latest["review_id"] if latest else ""})
                if status == "INDEPENDENTLY_RESOLVED":
                    target = next(target for target in latest["targets"] if target_key(target) == discrepancy_key)
                    resolved_json(target)
                    resolved_findings[finding["field"]] = (target, latest)
                if status != "INDEPENDENTLY_RESOLVED":
                    quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                       "provider_id": fixture[2], "field": finding["field"], "reason": status,
                                       "review_ids_json": canonical([latest["review_id"]] if latest else [])})
            for audit in latest_audits:
                if audit.get("targets"):
                    event_targets = [target for target in audit["targets"]
                                     if target["field"] == "event_instance_semantics"]
                    if event_targets:
                        if len(audit["targets"]) != 1 or event_targets[0]["left"] or event_targets[0]["right"]:
                            raise ValueError("invalid event-instance audit target")
                        target = event_targets[0]
                        matched_targets.add(target_key(target))
                        status = ("INDEPENDENTLY_RESOLVED"
                                  if corroborates_target(audit["disposition"], target["field"])
                                  else "QUARANTINED_REVIEWED")
                        synthetic = {**target, "disposition": audit["disposition"]}
                        queue.append({"release_id": release_id,
                                      "discrepancy_id": hashlib.sha256(canonical(synthetic).encode("utf-8")).hexdigest(),
                                      "scope": target["scope"], "issue": target["issue"], "slot": target["slot"],
                                      "provider_id": target["provider_id"], "field": target["field"],
                                      "left_value": target["left"], "right_value": target["right"],
                                      "category": "GENUINE_DISCREPANCY", "status": status,
                                      "review_id": audit["review_id"]})
                    missing_targets = [target for target in audit["targets"]
                                       if target_key(target) not in matched_targets]
                    if missing_targets:
                        raise ValueError("audit discrepancy target not present in normalized findings")
                else:
                    raise ValueError("fixture audit requires an explicit target")
            if quarantined:
                continue
            for (block, history_id), rows in history_groups[fixture].items():
                by_source = defaultdict(list)
                history_field = f"{block}:{history_id}"
                for row in rows:
                    by_source[row["source"]].append({field: row.get(field, "") for field in history_value_fields})
                spotcheck = latest_spotchecks.get(history_id)
                if history_id in quarantined_fixture_ids:
                    quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                       "provider_id": fixture[2], "field": history_field,
                                       "reason": "RELATED_QUARANTINED_FIXTURE_IDENTITY",
                                       "review_ids_json": "[]"})
                    continue
                if (history_id in cross_context_history_conflicts and
                        history_id not in reconciled_history_ids):
                    quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                       "provider_id": fixture[2], "field": history_field,
                                       "reason": "CROSS_CONTEXT_HISTORY_CONFLICT",
                                       "review_ids_json": "[]"})
                    continue
                if spotcheck and spotcheck["disposition"] not in AGREEMENT_ACCEPT_DISPOSITIONS:
                    quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                       "provider_id": fixture[2], "field": f"{block}:{history_id}",
                                       "reason": "AGREEMENT_SPOTCHECK_" + spotcheck["disposition"],
                                       "review_ids_json": canonical([spotcheck["review_id"]])})
                    continue
                resolved = resolved_findings.get(history_field)
                unresolved = any(finding["field"] == history_field for finding in fixture_findings)
                related_dispute = history_id in disputed_history_ids
                if related_dispute and not unresolved and not resolved:
                    quarantine.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                       "provider_id": fixture[2], "field": history_field,
                                       "reason": "RELATED_HISTORY_ID_DISCREPANCY",
                                       "review_ids_json": "[]"})
                if resolved:
                    target, review = resolved
                    selected = json.loads(resolved_json(target))
                    if not isinstance(selected, list) or any(not isinstance(row, list) or len(row) != len(history_value_fields)
                                                             for row in selected):
                        raise ValueError("resolved history value has invalid shape")
                    verification_status = "INDEPENDENTLY_RESOLVED"
                    review_id = review["review_id"]
                    evidence_json = canonical(review["evidence"])
                    source_count = 2
                elif (not related_dispute and set(by_source) == {"nowscore", "titan"} and
                      by_source["nowscore"] == by_source["titan"]):
                    selected = []
                    for row in by_source["nowscore"]:
                        try:
                            selected.append([
                                row["event_date"], row["home_id"], row["away_id"],
                                int(row["home_score"]), int(row["away_score"]),
                                None if row["halftime_home_score"] == "" else int(row["halftime_home_score"]),
                                None if row["halftime_away_score"] == "" else int(row["halftime_away_score"]),
                                row["score_scope"],
                            ])
                        except (TypeError, ValueError) as exc:
                            raise ValueError("normalized history value violates typed fact contract") from exc
                    selected = json.loads(resolved_json({
                        "field": history_field, "resolved_value": canonical(selected)}))
                    verification_status = "AGREED_UNVERIFIED"
                    review_id = spotcheck["review_id"] if spotcheck else ""
                    evidence_json = canonical(spotcheck["evidence"]) if spotcheck else "[]"
                    source_count = 2
                else:
                    selected = []
                for occurrence, row in enumerate(selected, start=1):
                    value = dict(zip(history_value_fields, row))
                    facts.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                  "provider_id": fixture[2], "fact_type": "prior_match",
                                  "fact_key": f"{block}:{history_id}:{occurrence}", "value_json": canonical(value),
                                  "verification_status": verification_status, "source_count": source_count,
                                  "availability_class": "HISTORICAL_PROXY", "review_id": review_id,
                                  "evidence_json": evidence_json})
            for field in ("season_tables", "schedules"):
                rows = field_groups.get((*fixture, field), [])
                by_source = {row["source"]: row for row in rows}
                if set(by_source) == {"nowscore", "titan"} and all(row["field_state"] == "POPULATED" for row in rows):
                    resolved = resolved_findings.get(field)
                    source_values = ({source: resolved_json({"field": field, "resolved_value": row["observed_value"]})
                                      for source, row in by_source.items()} if not resolved else {})
                    if resolved or source_values["nowscore"] == source_values["titan"]:
                        target, review = resolved if resolved else ({}, None)
                        value_json = resolved_json(target) if review else source_values["nowscore"]
                        if field == "season_tables":
                            standings = json.loads(value_json)
                            expected_teams = {"home": identity_value["home_id"], "away": identity_value["away_id"]}
                            if {row["side"]: row["team_id"] for row in standings} != expected_teams:
                                raise ValueError("standings teams do not match canonical fixture identity")
                        availability_evidence = [row["evidence_class"] for row in rows]
                        if review:
                            availability_evidence.append(review["availability_class"])
                        availability = (
                            "HISTORICAL_PROXY" if "HISTORICAL_PROXY" in availability_evidence else
                            "DOCUMENTED_CONSERVATIVE_SAFE_BOUNDARY"
                            if "DOCUMENTED_CONSERVATIVE_SAFE_BOUNDARY" in availability_evidence else
                            "OBSERVED"
                        )
                        facts.append({"release_id": release_id, "scope": scope, "issue": fixture[0], "slot": fixture[1],
                                      "provider_id": fixture[2], "fact_type": "standings_snapshot" if field == "season_tables" else "adjacent_schedule",
                                      "fact_key": field, "value_json": value_json,
                                      "verification_status": "INDEPENDENTLY_RESOLVED" if review else "AGREED_UNVERIFIED",
                                      "source_count": 2,
                                      "availability_class": availability, "review_id": review["review_id"] if review else "",
                                      "evidence_json": canonical(review["evidence"]) if review else "[]"})
    for row in queue:
        if row["category"] == "GENUINE_DISCREPANCY" and row["status"] == "INDEPENDENTLY_RESOLVED":
            matching = [audit for audit in audits if audit["review_id"] == row["review_id"]]
            if len(matching) != 1 or not matching[0]["evidence"]:
                raise ValueError("resolved discrepancy lacks independent evidence")
    return {"canonical_identity": identities, "discrepancy_queue": queue,
            "adjudications": adjudications, "facts": facts, "quarantine": quarantine}


def run_pipeline(bundle_dir: str | Path, output_dir: str | Path, *, generated_at_utc: str, release_id: str) -> dict:
    """Replay, audit and atomically publish one immutable #408 facts release."""
    generated = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    if generated.utcoffset() is None:
        raise ValueError("generation time requires timezone")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    bundle = validate_bundle(bundle_dir)
    bundle_root = Path(bundle["root"])
    implementation_paths = (Path(__file__), Path(__file__).with_name("fundamentals_census.py"))
    implementation_hashes = {path.name: sha256_file(path) for path in implementation_paths}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".fundamentals-408-") as temp:
        stage = Path(temp) / "release"
        stage.mkdir()
        releases = {}
        for scope in SCOPES:
            normalized_dir = stage / "normalized" / scope
            build_outputs(bundle_root / f"raw_{scope}", normalized_dir, generated_at_utc=generated_at_utc)
            releases[scope] = read_normalized_release(normalized_dir)
        audits = validate_audits(bundle_root, releases)
        tables = derive_release_tables(release_id, releases, audits)
        columns = {
            "canonical_identity": ["release_id", "scope", "issue", "slot", "provider_id", "identity_status",
                                   "verification_status", "canonical_identity_json", "review_ids_json", "rationale"],
            "discrepancy_queue": ["release_id", "discrepancy_id", "scope", "issue", "slot", "provider_id", "field",
                                  "left_value", "right_value", "category", "status", "review_id"],
            "adjudications": ["release_id", "review_id", "review_kind", "scope", "issue", "slot", "provider_id", "revision",
                              "disposition", "reviewer", "reviewed_at_utc", "rationale", "availability_class",
                              "targets_json", "evidence_json"],
            "facts": ["release_id", "scope", "issue", "slot", "provider_id", "fact_type", "fact_key", "value_json",
                      "verification_status", "source_count", "availability_class", "review_id", "evidence_json"],
            "quarantine": ["release_id", "scope", "issue", "slot", "provider_id", "field", "reason", "review_ids_json"],
        }
        for name, rows in tables.items():
            write_rows(stage / f"{name}.csv", rows, columns[name])
        if validate_bundle(bundle_root) != bundle:
            raise ValueError("source bundle identity changed during release")
        if implementation_hashes != {path.name: sha256_file(path) for path in implementation_paths}:
            raise ValueError("implementation changed during release")
        generated_files = sorted(path for path in stage.rglob("*") if path.is_file())
        output_hashes = {str(path.relative_to(stage)): sha256_file(path) for path in generated_files}
        receipt = {"schema": RELEASE_SCHEMA, "release_id": release_id, "generated_at_utc": generated_at_utc,
                   "historical_learning": "NONE", "source_bundle_manifest_sha256": bundle["manifest_sha256"],
                   "source_bundle_file_count": bundle["file_count"], "implementation_hashes": implementation_hashes,
                   "output_hashes": output_hashes,
                   "row_counts": {name: len(rows) for name, rows in tables.items()},
                   "admission": "FACTS_EXPORT_ONLY; AGREED_UNVERIFIED is not independent truth; quarantined data excluded; no settlement mutation"}
        (stage / "receipt.json").write_text(canonical(receipt) + "\n", encoding="utf-8")
        os.rename(stage, output)
    return receipt


def read_release(output_dir: str | Path) -> dict:
    """Verify and return the machine-readable receipt plus #408 CSV records."""
    root = Path(output_dir)
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("schema") != RELEASE_SCHEMA or receipt.get("historical_learning") != "NONE":
        raise ValueError("unsupported #408 release")
    expected_tables = {f"{name}.csv" for name in
                       ("canonical_identity", "discrepancy_queue", "adjudications", "facts", "quarantine")}
    output_hashes = receipt.get("output_hashes")
    if not isinstance(output_hashes, dict) or not expected_tables.issubset(output_hashes):
        raise ValueError("missing #408 output hashes")
    for relative, expected in output_hashes.items():
        path = (root / relative).resolve()
        if (not path.is_relative_to(root.resolve()) or
                not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or sha256_file(path) != expected):
            raise ValueError(f"#408 release hash mismatch: {relative}")
    tables = {}
    for name in ("canonical_identity", "discrepancy_queue", "adjudications", "facts", "quarantine"):
        with (root / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
            tables[name] = list(csv.DictReader(stream))
    return {"receipt": receipt, "tables": tables}
