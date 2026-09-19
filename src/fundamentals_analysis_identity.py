"""Exact, evidence-bound analysis identity views; raw reports remain immutable."""
import copy
import hashlib
from datetime import datetime
from pathlib import Path


def analysis_identity_view(report, decisions, *, repository_root):
    """Return a diagnostic integration view and transformation ledger.

    Decisions bind a single issue/slot/provider, original roster IDs, both source
    raw hashes and actual IDs, and independently corroborating evidence files.
    Only consumed fixture identity and history block ownership are normalized.
    Historical matches retain their own home/away teams and goals. Other raw
    blocks remain source-oriented and must not be treated as normalized features.
    No network, persistence, cutoff changes, or historical-learning admission.
    """
    root = Path(repository_root).resolve()
    view = copy.deepcopy(report)
    fixtures = {f["slot"]: f for f in view["fixtures"]}
    seen = set(); ledger = []
    for decision in decisions:
        slot = decision["slot"]
        if slot in seen or slot not in fixtures:
            raise ValueError("Duplicate or unknown analysis decision")
        seen.add(slot)
        fixture = fixtures[slot]
        if any(decision[k] != fixture[k] for k in ("issue", "provider_id")):
            raise ValueError("Analysis decision fixture mismatch")
        if decision["roster_ids"] != [fixture["home_id"], fixture["away_id"]]:
            raise ValueError("Analysis decision roster mismatch")
        if decision["action"] not in {"REVERSE_ANALYSIS_ORIENTATION", "EXACT_ANALYSIS_FIXTURE_IDENTITY"}:
            raise ValueError("Unsupported analysis action")
        if not decision["evidence_files"] or not decision.get("independent_evidence_path"):
            raise ValueError("Independent evidence required")
        if decision["independent_evidence_path"] not in decision["evidence_files"]:
            raise ValueError("Independent evidence is unbound")
        for name, digest in decision["evidence_files"].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Analysis evidence hash mismatch")
        observations = [o for o in view["observations"] if o["slot"] == slot]
        if len(observations) != 2 or {o["source"] for o in observations} != {"titan", "nowscore"}:
            raise ValueError("Analysis two-source cardinality mismatch")
        for obs in observations:
            binding = decision["analysis_sources"][obs["source"]]
            actual = {k: obs.get(k) for k in ("raw_sha256", "home_id", "away_id", "kickoff_utc", "provider_id")}
            if binding != actual or [obs["home_id"], obs["away_id"]] != decision["source_ids"]:
                raise ValueError("Analysis source semantic/hash mismatch")
        expected_cutoff = report["clean"]["cutoffs"][str(slot)]
        if datetime.fromisoformat(decision["cutoff_utc"]) != datetime.fromisoformat(expected_cutoff):
            raise ValueError("Analysis cutoff mismatch")
        original = copy.deepcopy(fixture)
        if decision["action"] == "EXACT_ANALYSIS_FIXTURE_IDENTITY":
            fixture["home_id"], fixture["away_id"] = decision["source_ids"]
        else:
            if decision["source_ids"][::-1] != decision["roster_ids"]:
                raise ValueError("Analysis orientation is not an exact reverse")
            for obs in observations:
                for home, away in (("home", "away"), ("home_id", "away_id")):
                    obs[home], obs[away] = obs[away], obs[home]
            for fields in view["page_fields"]:
                if fields["slot"] != slot:
                    continue
                raw = fields.get("raw_fields") or {}
                home = raw.pop("home_history_raw", None)
                away = raw.pop("away_history_raw", None)
                if away is not None:
                    raw["home_history_raw"] = away
                if home is not None:
                    raw["away_history_raw"] = home
        ledger.append(dict(issue=fixture["issue"], slot=slot, action=decision["action"],
                           original_fixture=original, canonical_fixture=copy.deepcopy(fixture),
                           decision=copy.deepcopy(decision), historical_admission=False,
                           normalized_fields=["fixture_identity", "history_block_ownership"],
                           untouched_raw_blocks="SOURCE_ORIENTED_NOT_NORMALIZED"))
    return view, ledger


def validate_analysis_substitutions(report, decisions, *, cutoffs, repository_root):
    """Validate exact independently corroborated NS identity/date replacements.

    Returns approved slots; the caller must also enforce NS identity/date
    validity and retain the rejected Titan source values. No files are written.
    """
    root=Path(repository_root).resolve()
    fixtures={f["slot"]:f for f in report["fixtures"]}
    approved=set()
    for d in decisions:
        f=fixtures.get(d["slot"])
        if f is None or d["slot"] in approved or any(d[k]!=f[k] for k in ("issue","provider_id")):
            raise ValueError("Substitution fixture mismatch")
        if datetime.fromisoformat(d["cutoff_utc"])!=datetime.fromisoformat(cutoffs[str(d["slot"])]):
            raise ValueError("Substitution cutoff mismatch")
        if d["action"] not in {"INDEPENDENTLY_VERIFIED_NOWSCORE_DATE_SUBSTITUTION", "INDEPENDENTLY_VERIFIED_NOWSCORE_IDENTITY_SUBSTITUTION"}:
            raise ValueError("Unsupported substitution")
        if d["roster_ids"]!=[f["home_id"],f["away_id"]]:
            raise ValueError("Substitution roster mismatch")
        observations=[o for o in report["observations"] if o["slot"]==d["slot"]]
        if len(observations)!=2 or {o["source"] for o in observations}!={"titan","nowscore"}:
            raise ValueError("Substitution source cardinality mismatch")
        for o in observations:
            if d["analysis_sources"][o["source"]]!={k:o.get(k) for k in ("raw_sha256","home_id","away_id","kickoff_utc","provider_id")}:
                raise ValueError("Substitution source binding mismatch")
        if not d["independent_evidence_path"] or d["independent_evidence_path"] not in d["evidence_files"]:
            raise ValueError("Substitution independent evidence required")
        for name,digest in d["evidence_files"].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError("Substitution evidence hash mismatch")
        approved.add(d["slot"])
    return approved
