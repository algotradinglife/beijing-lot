"""Minimal same-cycle input binding for adhoc betting generation.

This module intentionally stops at input correctness.  It does not schedule
refreshes, publish PDFs, maintain a ledger, or change any strategy decision.
The caller supplies the three raw-source parses collected in one bounded
refresh and receives normalized playid-34 rows plus a content-addressed
receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
HKT = timezone(timedelta(hours=8))
OUTCOME_CODES = ("3", "1", "0")
SCHEMA_VERSION = "adhoc_same_cycle_eligibility_v1"
CAPTURE_CLASSIFICATION = "adhoc_same_cycle_bound"
DEFAULT_MAX_CLOCK_SKEW = timedelta(minutes=5)


class AdhocInputFreshnessError(ValueError):
    """Raised when source inputs cannot form a trustworthy refresh batch."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AdhocInputFreshnessError("UTC collection clock is missing")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdhocInputFreshnessError(
            f"invalid UTC collection clock: {text!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise AdhocInputFreshnessError(
            f"collection clock must include a timezone offset: {text!r}"
        )
    return parsed.astimezone(UTC)


def explicit_utc(value: str | datetime) -> str:
    parsed = value if isinstance(value, datetime) else parse_utc(value)
    if parsed.tzinfo is None:
        raise AdhocInputFreshnessError("collection clock must be timezone-aware")
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def parse_hkt(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AdhocInputFreshnessError("HKT source clock is missing")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdhocInputFreshnessError(f"invalid HKT source clock: {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def explicit_hkt(value: str | datetime) -> str:
    parsed = value if isinstance(value, datetime) else parse_hkt(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT).isoformat(timespec="seconds")


def resolve_kickoff_hkt(
    *,
    sale_cutoff: str,
    schedule_date: str,
    kickoff_time: str,
    max_after_cutoff: timedelta = timedelta(hours=12),
) -> datetime | None:
    """Resolve kickoff while treating the official sale cutoff as the date gate.

    A provider ``schedule_date`` is only accepted when the resulting kickoff is
    on or after the official cutoff and within the bounded post-cutoff window.
    When it conflicts across midnight, the clock component is reconciled around
    the cutoff date instead of being returned directly.
    """

    cutoff: datetime | None
    try:
        cutoff = parse_hkt(sale_cutoff)
    except AdhocInputFreshnessError:
        cutoff = None

    text = str(kickoff_time or "").strip()
    direct: datetime | None = None
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=HKT)
            direct = parsed.astimezone(HKT)

    scheduled: datetime | None = None
    if schedule_date and text:
        try:
            parsed = datetime.fromisoformat(f"{schedule_date}T{text}")
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=HKT)
            scheduled = parsed.astimezone(HKT)

    if cutoff is None:
        return direct or scheduled

    for candidate in (direct, scheduled):
        if candidate is not None and cutoff <= candidate <= cutoff + max_after_cutoff:
            return candidate

    clock_text = text
    if "T" in clock_text:
        clock_text = clock_text.rsplit("T", 1)[-1]
    if " " in clock_text:
        clock_text = clock_text.rsplit(" ", 1)[-1]
    try:
        clock = datetime.strptime(clock_text, "%H:%M:%S").time()
    except ValueError:
        try:
            clock = datetime.strptime(clock_text, "%H:%M").time()
        except ValueError:
            return None
    candidates = [
        (cutoff + timedelta(days=offset)).replace(
            hour=clock.hour,
            minute=clock.minute,
            second=clock.second,
            microsecond=0,
        )
        for offset in (-1, 0, 1)
    ]
    return min(
        (
            candidate
            for candidate in candidates
            if cutoff <= candidate <= cutoff + max_after_cutoff
        ),
        default=None,
    )


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "open", "allowed"}:
        return True
    if text in {"0", "false", "no", "closed", "denied"}:
        return False
    return None


def _positive(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _unique_rows_by_index(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
    source: str,
) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get(key) is None:
            continue
        try:
            index = int(row[key])
        except (TypeError, ValueError) as exc:
            raise AdhocInputFreshnessError(
                f"{source} contains an invalid match index"
            ) from exc
        if index in indexed:
            raise AdhocInputFreshnessError(
                f"{source} contains duplicate match index {index}"
            )
        indexed[index] = dict(row)
    return indexed


def build_same_cycle_batch(
    *,
    issue: str,
    issue_rows: Sequence[Mapping[str, Any]],
    nowscore_rows: Sequence[Mapping[str, Any]],
    market_rows: Sequence[Mapping[str, Any]],
    source_clocks_utc: Mapping[str, str],
    source_sha256: Mapping[str, str],
    parlay_modes: Iterable[str],
    max_clock_skew: timedelta = DEFAULT_MAX_CLOCK_SKEW,
) -> dict[str, Any]:
    """Bind match, SP, sale and parlay evidence from one bounded refresh."""

    required_sources = {"issue_html", "nowscore_html", "live_sp_xml"}
    if set(source_clocks_utc) != required_sources:
        raise AdhocInputFreshnessError(
            "source clocks must contain issue_html, nowscore_html and live_sp_xml"
        )
    if set(source_sha256) != required_sources:
        raise AdhocInputFreshnessError(
            "source hashes must contain issue_html, nowscore_html and live_sp_xml"
        )
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        for digest in source_sha256.values()
    ):
        raise AdhocInputFreshnessError("source hashes must be lowercase SHA-256")

    clocks = {name: parse_utc(value) for name, value in source_clocks_utc.items()}
    oldest = min(clocks.values())
    newest = max(clocks.values())
    if newest - oldest > max_clock_skew:
        raise AdhocInputFreshnessError(
            "same-cycle source clock skew exceeds "
            f"{int(max_clock_skew.total_seconds())} seconds"
        )

    issue_by_idx = _unique_rows_by_index(
        issue_rows,
        key="match_idx",
        source="official issue page",
    )
    nowscore_by_idx = _unique_rows_by_index(
        nowscore_rows,
        key="match_idx",
        source="Nowscore issue page",
    )
    market_by_idx: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in market_rows:
        if row.get("row_idx") is not None:
            market_by_idx[int(row["row_idx"])].append(dict(row))

    modes = tuple(
        sorted({str(mode).strip() for mode in parlay_modes if str(mode).strip()})
    )
    parlay_proven = "自由过关" in modes
    batch_identity = {
        "schema_version": SCHEMA_VERSION,
        "issue": str(issue),
        "source_clocks_utc": {
            name: explicit_utc(clock) for name, clock in sorted(clocks.items())
        },
        "source_sha256": dict(sorted(source_sha256.items())),
        "parlay_modes": list(modes),
    }
    batch_id = sha256_bytes(canonical_json(batch_identity))
    evidence = {
        **batch_identity,
        "batch_id": batch_id,
        "clock_skew_seconds": int((newest - oldest).total_seconds()),
    }
    evidence_json = canonical_json(evidence).decode("utf-8")

    bound_rows: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    eligible_indices: list[int] = []
    for match_idx, issue_row in sorted(issue_by_idx.items()):
        reasons: list[str] = []
        nowscore = nowscore_by_idx.get(match_idx)
        vector = market_by_idx.get(match_idx, [])
        by_code = {
            str(row.get("outcome_code") or ""): row
            for row in vector
            if str(row.get("outcome_code") or "") in OUTCOME_CODES
        }
        if nowscore is None:
            reasons.append("NOWSCORE_MATCH_MISSING")
        relevant_vector_rows = [
            row for row in vector if str(row.get("outcome_code") or "") in OUTCOME_CODES
        ]
        if (
            len(relevant_vector_rows) != len(OUTCOME_CODES)
            or set(by_code) != set(OUTCOME_CODES)
            or any(
                not _positive(by_code.get(code, {}).get("sp")) for code in OUTCOME_CODES
            )
        ):
            reasons.append("LIVE_SP_VECTOR_INCOMPLETE")
        if any(
            not _positive(issue_row.get(field))
            for field in ("sp_home", "sp_draw", "sp_away")
        ):
            reasons.append("OFFICIAL_SELECTION_VECTOR_INCOMPLETE")

        disabled = str(issue_row.get("disabled") or "").strip().lower()
        issue_sale = True if disabled == "no" else False if disabled else None
        nowscore_sale = _as_bool(nowscore.get("can_sale")) if nowscore else None
        if issue_sale is False or nowscore_sale is False:
            sale_status = "closed"
            reasons.append("SALE_CLOSED")
        elif issue_sale is True and nowscore_sale is True:
            sale_status = "open"
        else:
            sale_status = "unknown"
            reasons.append("SALE_STATUS_UNVERIFIED")
        if not parlay_proven:
            reasons.append("PARLAY_EVIDENCE_MISSING")

        cutoff_text = str(issue_row.get("end_time") or "")
        try:
            cutoff = explicit_hkt(cutoff_text)
        except AdhocInputFreshnessError:
            cutoff = ""
            reasons.append("SALE_CUTOFF_UNVERIFIED")

        reasons = sorted(set(reasons))
        rejection_counts.update(reasons)
        if not reasons:
            eligible_indices.append(match_idx)
        for code in OUTCOME_CODES:
            raw = by_code.get(code)
            if raw is None:
                continue
            bound_rows.append(
                {
                    **raw,
                    "issue": str(issue),
                    "playid": 34,
                    "market_key": "handicap_3way",
                    "fetched_at": explicit_utc(clocks["live_sp_xml"]),
                    "fetched_at_utc": explicit_utc(clocks["live_sp_xml"]),
                    "source_updatetime": str(raw.get("source_updatetime") or ""),
                    "source_updated_at_hkt": explicit_hkt(
                        str(raw.get("source_updatetime") or "")
                    ),
                    "match_id": f"{issue}_{match_idx:03d}",
                    "batch_id": batch_id,
                    "source_url": str(raw.get("source_url") or ""),
                    "sale_status": sale_status,
                    "sale_cutoff_hkt": cutoff or None,
                    "parlay_allowed": "allowed" if parlay_proven else "unknown",
                    "parlay_modes_json": json.dumps(
                        list(modes), ensure_ascii=False, separators=(",", ":")
                    ),
                    "stake_limit_json": "{}",
                    "capture_classification": CAPTURE_CLASSIFICATION,
                    "eligibility_evidence_json": evidence_json,
                    "eligibility_reasons_json": json.dumps(
                        reasons, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )

    receipt = {
        **evidence,
        "match_count": len(issue_by_idx),
        "nowscore_match_count": len(nowscore_by_idx),
        "live_sp_match_count": len(market_by_idx),
        "eligible_match_count": len(eligible_indices),
        "eligible_match_indices": eligible_indices,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "status": "PASS" if eligible_indices else "FAILED_CLOSED",
    }
    receipt["sha256"] = sha256_bytes(canonical_json(receipt))
    return {
        "batch_id": batch_id,
        "rows": bound_rows,
        "receipt": receipt,
    }


def verify_same_cycle_evidence(
    *,
    batch_id: str,
    capture_classification: str,
    evidence_json: str,
    expected_issue: str | None = None,
) -> dict[str, Any]:
    """Verify the content-addressed evidence stored with a market vector."""

    if capture_classification != CAPTURE_CLASSIFICATION:
        raise AdhocInputFreshnessError("market snapshot is not same-cycle bound")
    try:
        evidence = json.loads(evidence_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AdhocInputFreshnessError("same-cycle evidence is malformed") from exc
    if not isinstance(evidence, dict):
        raise AdhocInputFreshnessError("same-cycle evidence must be an object")
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise AdhocInputFreshnessError("same-cycle evidence schema is unsupported")
    if expected_issue is not None and str(evidence.get("issue") or "") != str(
        expected_issue
    ):
        raise AdhocInputFreshnessError("same-cycle evidence issue mismatch")
    embedded = str(evidence.get("batch_id") or "")
    identity = {
        key: value
        for key, value in evidence.items()
        if key not in {"batch_id", "clock_skew_seconds"}
    }
    expected = sha256_bytes(canonical_json(identity))
    if not batch_id or embedded != batch_id or expected != batch_id:
        raise AdhocInputFreshnessError("same-cycle batch identity mismatch")
    clocks = evidence.get("source_clocks_utc")
    hashes = evidence.get("source_sha256")
    if not isinstance(clocks, dict) or not isinstance(hashes, dict):
        raise AdhocInputFreshnessError("same-cycle evidence sources are missing")
    required_sources = {"issue_html", "nowscore_html", "live_sp_xml"}
    if set(clocks) != required_sources or set(hashes) != required_sources:
        raise AdhocInputFreshnessError("same-cycle evidence source set is incomplete")
    for value in clocks.values():
        parse_utc(str(value))
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        for digest in hashes.values()
    ):
        raise AdhocInputFreshnessError("same-cycle evidence source hash is invalid")
    modes = evidence.get("parlay_modes")
    if not isinstance(modes, list) or "自由过关" not in modes:
        raise AdhocInputFreshnessError("same-cycle evidence lacks free-parlay proof")
    return evidence
