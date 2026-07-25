"""Immutable request-time betting packages for ``BJ-ADHOC-BET-001``.

This module deliberately has no dependency on scheduled-freeze manifests,
ledgers, or package layouts.  It accepts a request-time source snapshot built
by the API, classifies every match fail-closed, reuses only the released
exact-N portfolio primitives, and publishes one append-only adhoc package.

The source snapshot is intentionally a plain JSON-compatible object.  That
makes the temporal/eligibility contract testable without a live database and
prevents a generated package from reaching back into mutable runtime state.
"""

from __future__ import annotations

import csv
import fcntl
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from scripts import estimate_segment_betting_plan as portfolio
from scripts import replay_rolling_segment_n_tickets as rolling


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HKT = ZoneInfo("Asia/Hong_Kong")

CAPABILITY_ID = "BJ-ADHOC-BET-001"
PACKAGE_SCHEMA_VERSION = "adhoc_betting_package_v1"
LEDGER_SCHEMA_VERSION = "adhoc_betting_ledger_v1"
CONTENT_ID_SCHEMA = "adhoc_betting_content_id_v1"
REQUEST_ID_SCHEMA = "adhoc_betting_request_id_v1"

ALLOWED_N_VALUES = frozenset({3, 4, 5, 6, 7})
ALLOWED_BUDGETS = frozenset({512, 768, 1024})
OPEN_SALE_STATES = frozenset({"OPEN", "ON_SALE", "OPEN_PREGAME"})
TERMINAL_MATCH_STATES = frozenset(
    {"STARTED", "LIVE", "FINISHED", "SETTLED", "CANCELLED", "POSTPONED"}
)
OUTCOME_LABELS = {"3": "胜", "1": "平", "0": "负"}

DEFAULT_ADHOC_ROOT = PROJECT_ROOT / "results" / "adhoc_betting_plans"
DEFAULT_FONT_FILE = (
    PROJECT_ROOT
    / "evidence"
    / "bj_adhoc_bet_001"
    / "assets"
    / "fonts"
    / "NotoSansCJKsc-Regular.otf"
)
DEFAULT_SAFETY_MARGIN_SECONDS = 120
DEFAULT_MAX_SOURCE_AGE_SECONDS = 900
DEFAULT_SAMPLE_ATTEMPTS = 4000

REQUIRED_PACKAGE_FILES = frozenset(
    {
        "adhoc_request_manifest.json",
        "eligible_denominator.json",
        "decision_input.json",
        "exact_n_plan.json",
        "adhoc_betting_view.html",
        "adhoc_betting_slip.pdf",
        "ticket_legs.csv",
        "SHA256SUMS",
    }
)


class AdhocBettingError(ValueError):
    """A request cannot safely produce or expose an adhoc plan."""


class AdhocPlanNotFound(AdhocBettingError):
    """The requested adhoc identity is absent from the dedicated ledger."""


class AdhocIdempotencyConflict(AdhocBettingError):
    """A client replayed an idempotency key with different request fields."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(canonical(payload) + b"\n")


def _json_load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdhocBettingError(f"invalid JSON package artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise AdhocBettingError(f"JSON package artifact must be an object: {path.name}")
    return payload


def _unsigned(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "sha256"}


def _verify_payload_hash(payload: dict[str, Any], *, label: str) -> None:
    claimed = str(payload.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", claimed) or claimed != digest(_unsigned(payload)):
        raise AdhocBettingError(f"{label} semantic SHA-256 mismatch")


def _with_hash(payload: dict[str, Any]) -> dict[str, Any]:
    unsigned = _unsigned(payload)
    return {**unsigned, "sha256": digest(unsigned)}


def _parse_hkt(value: object, *, label: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AdhocBettingError(f"{label} is missing")
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text[:-1] + "+00:00")
        elif "T" in text:
            parsed = datetime.fromisoformat(text)
        else:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError(text)
    except ValueError as exc:
        raise AdhocBettingError(f"{label} is not an ISO/HKT clock") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def _iso_hkt(value: datetime) -> str:
    return value.astimezone(HKT).isoformat(timespec="seconds")


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "open", "allowed"}:
        return True
    if text in {"0", "false", "no", "n", "closed", "denied"}:
        return False
    return None


def _as_number(value: object, *, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise AdhocBettingError(f"{label} is not numeric") from exc
    if not math.isfinite(numeric):
        raise AdhocBettingError(f"{label} is not finite")
    return numeric


def _codes(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[+,/|]", str(value or ""))
    return tuple(str(code).strip() for code in raw if str(code).strip() in OUTCOME_LABELS)


def _selection_label(codes: list[str] | tuple[str, ...]) -> str:
    return "+".join(OUTCOME_LABELS.get(code, code) for code in codes)


def _csv_bytes(rows: list[dict[str, object]], fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _package_identity(manifest: dict[str, Any]) -> str:
    unsigned = _unsigned(manifest)
    unsigned.pop("package_id", None)
    return digest(
        {
            "content_id_schema": CONTENT_ID_SCHEMA,
            "manifest_payload_without_package_id": unsigned,
        }
    )


def _request_id(
    *,
    issue: str,
    requested_n: int,
    requested_budget_yuan: int,
    requested_at_hkt: str,
    idempotency_key: str,
    source_snapshot_sha256: str,
) -> str:
    return digest(
        {
            "schema": REQUEST_ID_SCHEMA,
            "issue": issue,
            "requested_n": requested_n,
            "requested_budget_yuan": requested_budget_yuan,
            "requested_at_hkt": requested_at_hkt,
            "idempotency_key": idempotency_key,
            "source_snapshot_sha256": source_snapshot_sha256,
        }
    )


@contextmanager
def _exclusive_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".adhoc-publish.lock"
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _source_snapshot_hash(source_snapshot: dict[str, Any]) -> str:
    unsigned = dict(source_snapshot)
    claimed = str(unsigned.pop("source_snapshot_sha256", "") or "")
    actual = digest(unsigned)
    if claimed and claimed != actual:
        raise AdhocBettingError("source snapshot SHA-256 mismatch")
    return actual


def _normalize_match(
    raw: dict[str, Any],
    *,
    requested_at: datetime,
    max_source_age: timedelta,
    safety_margin: timedelta,
) -> dict[str, Any]:
    """Freeze one denominator row plus all exclusion reasons.

    Deliberately do not throw for a malformed match: it must remain visible in
    the complete denominator with a structured exclusion reason.
    """

    reasons: list[str] = []
    try:
        match_idx = int(raw.get("match_idx"))
    except (TypeError, ValueError):
        match_idx = -1
        reasons.append("INVALID_MATCH_INDEX")

    source_status = str(raw.get("decision_input_status") or "READY").upper()
    source_reasons = raw.get("decision_input_reasons")
    if source_status not in {"READY", "AVAILABLE", "VALID"}:
        reasons.append(f"DECISION_INPUT_{source_status}")
    if isinstance(source_reasons, list):
        reasons.extend(str(reason) for reason in source_reasons if str(reason))

    kickoff: datetime | None = None
    cutoff: datetime | None = None
    observed: datetime | None = None
    try:
        kickoff = _parse_hkt(raw.get("kickoff_at_hkt"), label="kickoff_at_hkt")
    except AdhocBettingError:
        reasons.append("MISSING_KICKOFF")
    try:
        cutoff = _parse_hkt(raw.get("sale_cutoff_hkt"), label="sale_cutoff_hkt")
    except AdhocBettingError:
        reasons.append("MISSING_SALE_CUTOFF")
    try:
        observed = _parse_hkt(
            raw.get("source_observed_at_hkt"), label="source_observed_at_hkt"
        )
    except AdhocBettingError:
        reasons.append("MISSING_SOURCE_OBSERVED_AT")

    sale_status = str(raw.get("sale_status") or "UNKNOWN").upper()
    if sale_status not in OPEN_SALE_STATES:
        reasons.append(
            "UNKNOWN_SALE_STATE"
            if sale_status in {"", "UNKNOWN", "UNVERIFIED", "MISSING"}
            else "SALE_CLOSED"
        )
    pass_allowed = _as_bool(raw.get("pass_allowed"))
    if pass_allowed is not True:
        reasons.append("PASS_NOT_ALLOWED" if pass_allowed is False else "UNKNOWN_PASS_ALLOWED")

    match_status = str(raw.get("match_status") or "").upper()
    if match_status in TERMINAL_MATCH_STATES:
        reasons.append(f"MATCH_{match_status}")
    elif match_status != "SCHEDULED":
        reasons.append("UNKNOWN_MATCH_STATUS")
    if raw.get("result_code") or raw.get("score"):
        reasons.append("MATCH_ALREADY_SETTLED")
    if kickoff is not None and requested_at >= kickoff:
        reasons.append("STARTED_OR_KICKED_OFF")
    if cutoff is not None and requested_at + safety_margin >= cutoff:
        reasons.append("SALE_CUTOFF_MARGIN_REACHED")
    if observed is not None:
        age = requested_at - observed
        if age < timedelta(seconds=-5):
            reasons.append("SOURCE_CLOCK_AFTER_REQUEST")
        elif age > max_source_age:
            reasons.append("STALE_INPUT")

    codes = _codes(raw.get("selection_codes"))
    if not codes:
        reasons.append("MISSING_DECISION_CODES")
    probabilities: dict[str, float] = {}
    sp: dict[str, float] = {}
    raw_probabilities = raw.get("probabilities")
    raw_sp = raw.get("sp")
    for code in ("3", "1", "0"):
        try:
            probabilities[code] = _as_number(
                raw_probabilities.get(code) if isinstance(raw_probabilities, dict) else None,
                label=f"p_{code}",
            )
            sp[code] = _as_number(
                raw_sp.get(code) if isinstance(raw_sp, dict) else None,
                label=f"sp_{code}",
            )
        except AdhocBettingError:
            reasons.append("MISSING_DECISION_OR_SP_VECTOR")
            break
    if any(probabilities.get(code, 0.0) <= 0 or sp.get(code, 0.0) <= 0 for code in codes):
        reasons.append("INVALID_SELECTED_DECISION_OR_SP")

    raw_provenance = raw.get("source_provenance")
    source_provenance: dict[str, Any] = {}
    if raw_provenance is not None:
        if not isinstance(raw_provenance, dict):
            reasons.append("INVALID_SOURCE_PROVENANCE")
        else:
            try:
                # Store a JSON-only copy: package verification must never rely
                # on mutable Python objects held by an API request handler.
                source_provenance = json.loads(canonical(raw_provenance).decode("utf-8"))
            except (TypeError, ValueError):
                reasons.append("INVALID_SOURCE_PROVENANCE")

    # Stable ordering and de-duplication make denominator bytes reproducible.
    reasons = sorted(set(reasons))
    return {
        "match_idx": match_idx,
        "match_id": str(raw.get("match_id") or ""),
        "league": str(raw.get("league") or ""),
        "home": str(raw.get("home") or ""),
        "away": str(raw.get("away") or ""),
        "handicap_line": raw.get("handicap_line"),
        "kickoff_at_hkt": _iso_hkt(kickoff) if kickoff else "",
        "sale_cutoff_hkt": _iso_hkt(cutoff) if cutoff else "",
        "sale_status": sale_status,
        "pass_allowed": pass_allowed,
        "match_status": match_status,
        "source_observed_at_hkt": _iso_hkt(observed) if observed else "",
        "source_provenance": source_provenance,
        "decision_input_status": source_status,
        "selection_codes": list(codes),
        "probabilities": probabilities,
        "sp": sp,
        "included": not reasons,
        "exclusion_reasons": reasons,
    }


def _public_denominator_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return shop-safe denominator rows without probabilities, SP, or scores."""

    return [
        {
            "match_idx": int(row["match_idx"]),
            "match_id": str(row.get("match_id") or ""),
            "league": str(row.get("league") or ""),
            "home": str(row.get("home") or ""),
            "away": str(row.get("away") or ""),
            "handicap_line": row.get("handicap_line"),
            "kickoff_at_hkt": str(row.get("kickoff_at_hkt") or ""),
            "eligible": bool(row.get("included")),
            "exclusion_reasons": list(row.get("exclusion_reasons") or []),
        }
        for row in sorted(rows, key=lambda item: int(item["match_idx"]))
    ]


def _validate_request(
    *,
    issue: object,
    requested_n: object,
    requested_budget_yuan: object,
    idempotency_key: object,
) -> tuple[str, int, int, str]:
    issue_text = str(issue or "").strip()
    if not issue_text:
        raise AdhocBettingError("issue is required")
    try:
        n_value = int(requested_n)
        budget = int(requested_budget_yuan)
    except (TypeError, ValueError) as exc:
        raise AdhocBettingError("requested N and budget must be integers") from exc
    if n_value not in ALLOWED_N_VALUES:
        raise AdhocBettingError("requested_n must be one of 3/4/5/6/7")
    if budget not in ALLOWED_BUDGETS:
        raise AdhocBettingError("requested_budget_yuan must be one of 512/768/1024")
    key = str(idempotency_key or "").strip()
    if len(key) < 8 or len(key) > 200:
        raise AdhocBettingError("idempotency_key must contain 8-200 characters")
    return issue_text, n_value, budget, key


def _make_portfolio(
    *,
    eligible: list[dict[str, Any]],
    issue: str,
    n_value: int,
    budget_yuan: int,
    seed: int,
    sample_attempts: int,
) -> tuple[list[dict[str, Any]], float, float, str]:
    """Use the released deterministic exact-N core without an N/budget fallback."""

    legs: list[rolling.LegRow] = []
    for row in eligible:
        kickoff = _parse_hkt(row["kickoff_at_hkt"], label="kickoff_at_hkt")
        codes = tuple(str(code) for code in row["selection_codes"])
        legs.append(
            rolling.LegRow(
                issue=issue,
                match_idx=int(row["match_idx"]),
                match_id=str(row["match_id"] or f"{issue}_{int(row['match_idx']):03d}"),
                kickoff=kickoff,
                league=str(row["league"]),
                home=str(row["home"]),
                away=str(row["away"]),
                active_codes=(),
                shadow_codes=codes,
                probabilities={code: float(row["probabilities"][code]) for code in ("3", "1", "0")},
                sp={code: float(row["sp"][code]) for code in ("3", "1", "0")},
                actual_code=None,
                winning_sp=None,
            )
        )
    metrics = [metric for leg in legs if (metric := portfolio.leg_metrics(leg, "shadow")) is not None]
    if len(metrics) < n_value:
        return [], 0.0, 0.0, "eligible_match_count_below_requested_n"

    budget_units = budget_yuan / 2.0
    candidates = portfolio.generate_candidates(
        metrics=metrics,
        segment_idx=0,
        arm="shadow",
        n_value=n_value,
        budget_units=budget_units,
        sample_attempts=max(1, int(sample_attempts)),
        seed=seed,
    )
    selected = portfolio.select_bundles(
        [candidate for candidate in candidates if len(candidate.match_indices) == n_value],
        budget_units=budget_units,
        max_overlap=max(0, n_value - 2),
        positive_ev_only=True,
        max_bundle_cost_units=budget_units * 0.4,
    )
    staked, spent_units, reason = portfolio.apply_stake_mode(
        selected,
        budget_units=budget_units,
        stake_mode="scale_to_budget",
        max_bundle_cost_units=budget_units * 0.4,
    )
    tickets: list[dict[str, Any]] = []
    for ticket_number, item in enumerate(staked, start=1):
        candidate = item.candidate
        if len(candidate.match_indices) != n_value:
            raise AdhocBettingError("exact-N portfolio core returned a non-exact ticket")
        tickets.append(
            {
                "ticket_no": ticket_number,
                "match_indices": list(candidate.match_indices),
                "leg_codes": list(candidate.leg_codes),
                "actual_n": len(candidate.match_indices),
                "stake_multiplier": int(item.stake_multiplier),
                "base_cost_yuan": round(candidate.cost_units * 2.0, 2),
                "cost_yuan": round(candidate.cost_units * item.stake_multiplier * 2.0, 2),
            }
        )
    actual_cost = round(spent_units * 2.0, 2)
    base_cost = round(sum(float(ticket["base_cost_yuan"]) for ticket in tickets), 2)
    if actual_cost > budget_yuan + 1e-9:
        raise AdhocBettingError("exact-N portfolio core exceeded the requested budget")
    return tickets, base_cost, actual_cost, reason


def _render_html(
    *,
    manifest: dict[str, Any],
    plan: dict[str, Any],
    match_by_idx: dict[int, dict[str, Any]],
) -> str:
    title = "北单即时方案"
    rows: list[str] = []
    for ticket in plan["tickets"]:
        legs: list[str] = []
        for match_idx, code_text in zip(ticket["match_indices"], ticket["leg_codes"]):
            match = match_by_idx[int(match_idx)]
            codes = [code for code in str(code_text).split("+") if code]
            legs.append(
                "<li>"
                f"<strong>#{int(match_idx)} {_selection_label(codes)}</strong>"
                f"<span>{html.escape(str(match['home']))} vs {html.escape(str(match['away']))}</span>"
                f"<small>{html.escape(str(match['league']))} · {html.escape(str(match['kickoff_at_hkt']))} · 让球 {html.escape(str(match['handicap_line'] if match['handicap_line'] is not None else '-'))}</small>"
                "</li>"
            )
        rows.append(
            "<section class=\"ticket\">"
            f"<header><b>第 {int(ticket['ticket_no'])} 票 · {int(ticket['actual_n'])} 串 1</b>"
            f"<span>¥{float(ticket['cost_yuan']):.2f} · 倍数 {int(ticket['stake_multiplier'])}</span></header>"
            f"<ol>{''.join(legs)}</ol>"
            "</section>"
        )
    body = "".join(rows) or "<p class=\"unavailable\">当前没有可生成的 exact-N 即时方案；请查看排除原因并在输入更新后重新生成。</p>"
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{title} {html.escape(str(manifest['request_id'][:12]))}</title>
<style>
@page {{ size:A4; margin:12mm; }}
* {{ box-sizing:border-box; }}
body {{ font-family:AdhocBettingCJK,"Noto Sans CJK SC",sans-serif; color:#122033; font-size:12px; line-height:1.5; }}
h1 {{ margin:0 0 5px; font-size:22px; }} .notice {{ color:#9a3412; font-weight:700; }}
.meta {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px 16px; padding:10px; border:1px solid #b8c6d9; border-radius:7px; background:#f8fbff; }}
.meta b {{ color:#0f3c78; }} .ticket {{ break-inside:avoid; page-break-inside:avoid; border:1px solid #b8c6d9; border-radius:7px; margin:10px 0; padding:9px 11px; }}
.ticket header {{ display:flex; justify-content:space-between; gap:8px; border-bottom:1px solid #d8e1ed; padding-bottom:5px; }}
ol {{ margin:8px 0 0; padding-left:20px; }} li {{ margin:5px 0; }} li strong, li span, li small {{ display:block; }} li strong {{ font-size:14px; color:#102a56; }} li small {{ color:#53657b; }}
.footer {{ margin-top:12px; color:#596b82; font-size:10px; }} .unavailable {{ border:1px solid #f0b49b; padding:12px; background:#fff7f4; }}
</style></head><body>
<h1>{title}</h1>
<p class=\"notice\">仅在有效期内可用于人工核对；过期后必须重新生成，不会自动替换、删票或重算。</p>
<div class=\"meta\"><div>请求号 <b>{html.escape(str(manifest['request_id']))}</b></div><div>状态 <b>{html.escape(str(manifest['status']))}</b></div>
<div>生成/请求时间 <b>{html.escape(str(manifest['requested_at_hkt']))}</b></div><div>输入 as-of <b>{html.escape(str(manifest['input_asof_hkt']))}</b></div>
<div>有效至 <b>{html.escape(str(manifest['valid_until_hkt'] or '无可用窗口'))}</b></div><div>exact N / 预算 <b>N={int(manifest['requested_n'])} / ¥{int(manifest['requested_budget_yuan'])}</b></div>
<div>票数 / 基础成本 <b>{len(plan['tickets'])} / ¥{float(plan['base_cost_yuan']):.2f}</b></div><div>实际成本 / 未用预算 <b>¥{float(plan['actual_cost_yuan']):.2f} / ¥{float(plan['unused_budget_yuan']):.2f}</b></div>
<div>预算利用率 <b>{float(plan['budget_utilization']) * 100:.2f}%</b></div></div>
{body}
<p class=\"footer\">{CAPABILITY_ID} · research_evidence_eligible=false · scheduled_freeze_event_id=null · 正确比分执行未开放。</p>
</body></html>"""


def _canonicalize_pdf_identifier(target: Path, identifier: str) -> None:
    payload = target.read_bytes()
    pattern = re.compile(
        rb"/ID \[\((" + identifier.encode("ascii") + rb")\) \(([0-9a-f]{32})\)\]"
    )
    revision = digest({"pdf_identifier": identifier, "revision": 1})[:32].encode("ascii")
    normalized, replacements = pattern.subn(
        rb"/ID [(\1) (" + revision + rb")]",
        payload,
    )
    if replacements != 1 or len(normalized) != len(payload):
        raise AdhocBettingError("PDF identifier normalization failed")
    target.write_bytes(normalized)


def _assert_font_coverage(font_file: Path, text: str) -> None:
    """Fail closed instead of publishing a PDF with missing CJK glyphs."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise AdhocBettingError("PDF_UNAVAILABLE: fonttools is not installed") from exc
    try:
        cmap = TTFont(font_file, fontNumber=0).getBestCmap() or {}
    except Exception as exc:
        raise AdhocBettingError("PDF_UNAVAILABLE: unable to inspect portable font") from exc
    required = {ord(character) for character in text if not character.isspace() and ord(character) >= 32}
    missing = sorted(required - set(cmap))
    if missing:
        preview = "".join(chr(value) for value in missing[:12])
        raise AdhocBettingError(
            f"PDF_UNAVAILABLE: portable font lacks required glyphs {preview!r}"
        )


def _write_pdf(html_text: str, target: Path, font_file: Path, identifier: str) -> str:
    try:
        import weasyprint
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise AdhocBettingError("PDF_UNAVAILABLE: WeasyPrint is not installed") from exc
    if not font_file.is_file():
        raise AdhocBettingError("PDF_UNAVAILABLE: portable CJK font is missing")
    _assert_font_coverage(font_file, html_text)
    config = FontConfiguration()
    font_css = CSS(
        string=(
            '@font-face { font-family: "AdhocBettingCJK"; '
            f'src: url("{font_file.resolve().as_uri()}"); }}'
        ),
        font_config=config,
    )
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        HTML(string=html_text, base_url=str(target.parent)).write_pdf(
            target,
            stylesheets=[font_css],
            font_config=config,
            pdf_identifier=identifier,
            presentational_hints=True,
            full_fonts=False,
            hinting=False,
            optimize_images=False,
        )
    except Exception as exc:
        raise AdhocBettingError("PDF_UNAVAILABLE: render failed") from exc
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    if not target.is_file() or target.stat().st_size == 0:
        raise AdhocBettingError("PDF_UNAVAILABLE: render produced an empty PDF")
    _canonicalize_pdf_identifier(target, identifier)
    return f"WeasyPrint/{weasyprint.__version__}"


def _ticket_leg_rows(
    *,
    request_id: str,
    tickets: list[dict[str, Any]],
    match_by_idx: dict[int, dict[str, Any]],
    valid_until_hkt: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ticket in tickets:
        for match_idx, leg_codes in zip(ticket["match_indices"], ticket["leg_codes"]):
            match = match_by_idx[int(match_idx)]
            codes = [code for code in str(leg_codes).split("+") if code]
            rows.append(
                {
                    "request_id": request_id,
                    "ticket_no": int(ticket["ticket_no"]),
                    "match_idx": int(match_idx),
                    "match_id": str(match["match_id"]),
                    "selection_code": "+".join(codes),
                    "selection_label": _selection_label(codes),
                    "kickoff_at_hkt": str(match["kickoff_at_hkt"]),
                    "league": str(match["league"]),
                    "home": str(match["home"]),
                    "away": str(match["away"]),
                    "handicap_line": match["handicap_line"] if match["handicap_line"] is not None else "",
                    "stake_multiplier": int(ticket["stake_multiplier"]),
                    "ticket_cost_yuan": f"{float(ticket['cost_yuan']):.2f}",
                    "valid_until_hkt": valid_until_hkt,
                }
            )
    return rows


def _ledger_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS adhoc_betting_request_ledger (
            request_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL,
            issue TEXT NOT NULL,
            requested_n INTEGER NOT NULL,
            requested_budget_yuan INTEGER NOT NULL,
            requested_at_hkt TEXT NOT NULL,
            input_asof_hkt TEXT NOT NULL,
            source_snapshot_sha256 TEXT NOT NULL,
            package_id TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            package_path TEXT NOT NULL,
            immutable_status TEXT NOT NULL,
            valid_until_hkt TEXT,
            sale_status_verified INTEGER NOT NULL,
            research_evidence_eligible INTEGER NOT NULL CHECK(research_evidence_eligible=0),
            scheduled_freeze_event_id TEXT CHECK(scheduled_freeze_event_id IS NULL),
            state TEXT NOT NULL,
            created_at_hkt TEXT NOT NULL,
            UNIQUE(issue, idempotency_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_adhoc_betting_ledger_issue ON adhoc_betting_request_ledger(issue, requested_at_hkt)"
    )


def _package_dir(root: Path, issue: str, package_id: str) -> Path:
    safe_issue = re.sub(r"[^A-Za-z0-9._-]", "_", issue)
    return root / "packages" / safe_issue / package_id


def _load_package(root: Path, row: sqlite3.Row | dict[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    package_id = str(row["package_id"])
    issue = str(row["issue"])
    path = _package_dir(root, issue, package_id)
    verification = verify_package(path)
    if verification["status"] != "PASS":  # defensive; verifier raises on failure.
        raise AdhocBettingError("adhoc package verification did not pass")
    manifest = _json_load(path / "adhoc_request_manifest.json")
    ledger_bindings = {
        "request_id": str(manifest.get("request_id") or ""),
        "issue": str(manifest.get("issue") or ""),
        "requested_n": int(manifest.get("requested_n") or 0),
        "requested_budget_yuan": int(manifest.get("requested_budget_yuan") or 0),
        "source_snapshot_sha256": str(manifest.get("source_snapshot_sha256") or ""),
        "package_id": str(manifest.get("package_id") or ""),
        "manifest_sha256": str(manifest.get("sha256") or ""),
        "immutable_status": str(manifest.get("status") or ""),
        "valid_until_hkt": str(manifest.get("valid_until_hkt") or ""),
        "sale_status_verified": 1 if bool(manifest.get("sale_status_verified")) else 0,
        "research_evidence_eligible": 0,
        "scheduled_freeze_event_id": None,
    }
    for field, expected in ledger_bindings.items():
        if row[field] != expected:
            raise AdhocBettingError(f"adhoc ledger/package binding mismatch: {field}")
    recorded_path = Path(str(row["package_path"])).resolve()
    if recorded_path != path.resolve():
        raise AdhocBettingError("adhoc ledger/package binding mismatch: package_path")
    return (
        path,
        manifest,
        _json_load(path / "exact_n_plan.json"),
        _json_load(path / "eligible_denominator.json"),
    )


class AdhocBettingStore:
    """Dedicated append-only store for user-triggered plans.

    The ledger lives in a separate SQLite table and all package paths are
    under ``results/adhoc_betting_plans``.  Neither name overlaps a scheduled
    segment/freeze namespace.
    """

    def __init__(
        self,
        *,
        db_path: str | os.PathLike[str],
        root: str | os.PathLike[str] = DEFAULT_ADHOC_ROOT,
        font_file: str | os.PathLike[str] = DEFAULT_FONT_FILE,
        safety_margin_seconds: int = DEFAULT_SAFETY_MARGIN_SECONDS,
        max_source_age_seconds: int = DEFAULT_MAX_SOURCE_AGE_SECONDS,
        sample_attempts: int = DEFAULT_SAMPLE_ATTEMPTS,
    ) -> None:
        self.db_path = Path(db_path)
        self.root = Path(root)
        self.font_file = Path(font_file)
        self.safety_margin = timedelta(seconds=max(0, int(safety_margin_seconds)))
        self.max_source_age = timedelta(seconds=max(1, int(max_source_age_seconds)))
        self.sample_attempts = max(1, int(sample_attempts))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        _ledger_schema(conn)
        return conn

    def _existing_for_key(
        self,
        conn: sqlite3.Connection,
        *,
        issue: str,
        idempotency_key: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM adhoc_betting_request_ledger WHERE issue=? AND idempotency_key=?",
            (issue, idempotency_key),
        ).fetchone()

    def eligibility_preview(
        self,
        *,
        source_snapshot: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Classify the live denominator without creating an immutable plan.

        The preview is informational only.  Generation repeats this work and
        binds a fresh source snapshot, so a preview can never be mistaken for
        a ticket package or a reservation.
        """

        clock = (now or datetime.now(timezone.utc)).astimezone(HKT)
        raw_matches = source_snapshot.get("matches")
        if not isinstance(raw_matches, list) or not raw_matches:
            raise AdhocBettingError("source snapshot lacks a complete match denominator")
        normalized = [
            _normalize_match(
                dict(row) if isinstance(row, dict) else {},
                requested_at=clock,
                max_source_age=self.max_source_age,
                safety_margin=self.safety_margin,
            )
            for row in raw_matches
        ]
        indices = [int(row["match_idx"]) for row in normalized]
        if len(indices) != len(set(indices)) or any(index <= 0 for index in indices):
            raise AdhocBettingError("source snapshot denominator has invalid or duplicate match indices")
        excluded = [row for row in normalized if not row["included"]]
        counts: Counter[str] = Counter()
        for row in excluded:
            counts.update(str(reason) for reason in row["exclusion_reasons"])
        return {
            "schema_version": "adhoc_betting_eligibility_preview_v1",
            "capability_id": CAPABILITY_ID,
            "issue": str(source_snapshot.get("issue") or ""),
            "observed_at_hkt": _iso_hkt(clock),
            "input_asof_hkt": str(source_snapshot.get("input_asof_hkt") or ""),
            "status": "ELIGIBILITY_PREVIEW",
            "eligible_match_count": sum(1 for row in normalized if row["included"]),
            "excluded_match_count": len(excluded),
            "exclusion_counts": dict(sorted(counts.items())),
            "matches": _public_denominator_rows(normalized),
            "safety_margin_seconds": int(self.safety_margin.total_seconds()),
            "preview_only": True,
            "research_evidence_eligible": False,
            "scheduled_freeze_event_id": None,
        }

    def create_or_get(
        self,
        *,
        issue: object,
        requested_n: object,
        requested_budget_yuan: object,
        idempotency_key: object,
        source_snapshot: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        issue_text, n_value, budget, key = _validate_request(
            issue=issue,
            requested_n=requested_n,
            requested_budget_yuan=requested_budget_yuan,
            idempotency_key=idempotency_key,
        )
        requested_at = (now or datetime.now(timezone.utc)).astimezone(HKT)
        requested_at_text = _iso_hkt(requested_at)
        if str(source_snapshot.get("issue") or "") != issue_text:
            raise AdhocBettingError("source snapshot issue does not match the request")

        with _exclusive_lock(self.root):
            with self._connect() as conn:
                existing = self._existing_for_key(conn, issue=issue_text, idempotency_key=key)
                if existing is not None:
                    if (
                        int(existing["requested_n"]) != n_value
                        or int(existing["requested_budget_yuan"]) != budget
                    ):
                        raise AdhocIdempotencyConflict(
                            "idempotency_key was already bound to different exact-N or budget"
                        )
                    _path, manifest, plan, denominator = _load_package(self.root, existing)
                    return self._public_result(
                        manifest=manifest,
                        plan=plan,
                        denominator=denominator,
                        now=requested_at,
                        idempotent=True,
                    )

            source_hash = _source_snapshot_hash(source_snapshot)
            request_id = _request_id(
                issue=issue_text,
                requested_n=n_value,
                requested_budget_yuan=budget,
                requested_at_hkt=requested_at_text,
                idempotency_key=key,
                source_snapshot_sha256=source_hash,
            )
            stage_parent = self.root / ".staging"
            stage_parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".adhoc-stage-", dir=stage_parent))
            try:
                manifest, plan, denominator, package_id = self._write_stage(
                    stage=stage,
                    issue=issue_text,
                    requested_n=n_value,
                    requested_budget_yuan=budget,
                    idempotency_key=key,
                    requested_at=requested_at,
                    request_id=request_id,
                    source_snapshot=source_snapshot,
                    source_snapshot_sha256=source_hash,
                )
                staged_verification = verify_package(stage, allow_staging=True)
                destination = _package_dir(self.root, issue_text, package_id)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    visible_verification = verify_package(destination)
                    if visible_verification != staged_verification:
                        raise AdhocBettingError("content-addressed package identity collision")
                    shutil.rmtree(stage)
                else:
                    os.rename(stage, destination)
                    visible_verification = verify_package(destination)
                    if visible_verification != staged_verification:
                        raise AdhocBettingError("visible package verification differs from staging receipt")

                with self._connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    existing = self._existing_for_key(conn, issue=issue_text, idempotency_key=key)
                    if existing is not None:
                        conn.rollback()
                        _path, old_manifest, old_plan, old_denominator = _load_package(self.root, existing)
                        return self._public_result(
                            manifest=old_manifest,
                            plan=old_plan,
                            denominator=old_denominator,
                            now=requested_at,
                            idempotent=True,
                        )
                    conn.execute(
                        """
                        INSERT INTO adhoc_betting_request_ledger(
                            request_id,idempotency_key,issue,requested_n,requested_budget_yuan,
                            requested_at_hkt,input_asof_hkt,source_snapshot_sha256,package_id,
                            manifest_sha256,package_path,immutable_status,valid_until_hkt,
                            sale_status_verified,research_evidence_eligible,
                            scheduled_freeze_event_id,state,created_at_hkt
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            request_id,
                            key,
                            issue_text,
                            n_value,
                            budget,
                            requested_at_text,
                            str(manifest["input_asof_hkt"]),
                            source_hash,
                            package_id,
                            str(manifest["sha256"]),
                            str(destination),
                            str(manifest["status"]),
                            str(manifest["valid_until_hkt"] or ""),
                            1 if manifest["sale_status_verified"] else 0,
                            0,
                            None,
                            "PUBLISHED",
                            requested_at_text,
                        ),
                    )
                    conn.commit()
                return self._public_result(
                    manifest=manifest,
                    plan=plan,
                    denominator=denominator,
                    now=requested_at,
                    idempotent=False,
                )
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    def _write_stage(
        self,
        *,
        stage: Path,
        issue: str,
        requested_n: int,
        requested_budget_yuan: int,
        idempotency_key: str,
        requested_at: datetime,
        request_id: str,
        source_snapshot: dict[str, Any],
        source_snapshot_sha256: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
        input_asof = _parse_hkt(source_snapshot.get("input_asof_hkt"), label="input_asof_hkt")
        if input_asof > requested_at:
            raise AdhocBettingError("decision input as-of clock is after the server request clock")
        raw_matches = source_snapshot.get("matches")
        if not isinstance(raw_matches, list) or not raw_matches:
            raise AdhocBettingError("source snapshot lacks a complete match denominator")
        normalized = [
            _normalize_match(
                dict(row) if isinstance(row, dict) else {},
                requested_at=requested_at,
                max_source_age=self.max_source_age,
                safety_margin=self.safety_margin,
            )
            for row in raw_matches
        ]
        indices = [int(row["match_idx"]) for row in normalized]
        if len(indices) != len(set(indices)) or any(index <= 0 for index in indices):
            raise AdhocBettingError("source snapshot denominator has invalid or duplicate match indices")
        normalized.sort(key=lambda row: int(row["match_idx"]))
        eligible = [row for row in normalized if row["included"]]
        excluded = [row for row in normalized if not row["included"]]
        eligibility = {
            "schema_version": "adhoc_eligible_denominator_v1",
            "capability_id": CAPABILITY_ID,
            "issue": issue,
            "request_id": request_id,
            "requested_at_hkt": _iso_hkt(requested_at),
            "safety_margin_seconds": int(self.safety_margin.total_seconds()),
            "max_source_age_seconds": int(self.max_source_age.total_seconds()),
            "considered_match_count": len(normalized),
            "eligible_match_count": len(eligible),
            "excluded_match_count": len(excluded),
            "included": eligible,
            "excluded": excluded,
        }
        eligibility = _with_hash(eligibility)
        _json_dump(stage / "eligible_denominator.json", eligibility)

        decision_input = _with_hash(
            {
                "schema_version": "adhoc_decision_input_v1",
                "capability_id": CAPABILITY_ID,
                "issue": issue,
                "request_id": request_id,
                "input_asof_hkt": _iso_hkt(input_asof),
                "source_snapshot_sha256": source_snapshot_sha256,
                "decision_variant_id": str(source_snapshot.get("decision_variant_id") or "active_v3.3.3"),
                "source_metadata": source_snapshot.get("source_metadata")
                if isinstance(source_snapshot.get("source_metadata"), dict)
                else {},
                "matches": normalized,
            }
        )
        _json_dump(stage / "decision_input.json", decision_input)

        seed = portfolio.stable_seed(
            CAPABILITY_ID,
            request_id,
            source_snapshot_sha256,
            requested_n,
            requested_budget_yuan,
        )
        tickets, base_cost, actual_cost, portfolio_reason = _make_portfolio(
            eligible=eligible,
            issue=issue,
            n_value=requested_n,
            budget_yuan=requested_budget_yuan,
            seed=seed,
            sample_attempts=self.sample_attempts,
        )
        sale_status_verified = bool(tickets) and all(
            row["sale_status"] in OPEN_SALE_STATES and row["pass_allowed"] is True
            for row in eligible
        )
        selected_rows = {
            int(match_idx)
            for ticket in tickets
            for match_idx in ticket["match_indices"]
        }
        selected = [row for row in eligible if int(row["match_idx"]) in selected_rows]
        valid_until = (
            min(
                _parse_hkt(row["sale_cutoff_hkt"], label="sale_cutoff_hkt")
                - self.safety_margin
                for row in selected
            )
            if selected
            else None
        )
        status = "READY_FOR_REVIEW" if tickets and sale_status_verified else "UNAVAILABLE_ADHOC_PLAN"
        unavailable_reasons: list[str] = []
        if not tickets:
            unavailable_reasons.append(portfolio_reason)
        if not sale_status_verified and tickets:
            unavailable_reasons.append("sale_status_not_verified")
        plan = _with_hash(
            {
                "schema_version": "adhoc_exact_n_plan_v1",
                "capability_id": CAPABILITY_ID,
                "request_id": request_id,
                "issue": issue,
                "requested_n": requested_n,
                "artifact_n": requested_n,
                "requested_budget_yuan": requested_budget_yuan,
                "base_cost_yuan": base_cost,
                "actual_cost_yuan": actual_cost,
                "unused_budget_yuan": round(requested_budget_yuan - actual_cost, 2),
                "budget_utilization": round(actual_cost / requested_budget_yuan, 8),
                "status": status,
                "reason": portfolio_reason,
                "unavailable_reasons": unavailable_reasons,
                "deterministic_seed": seed,
                "tickets": tickets,
                "correct_score_status": "UNAVAILABLE_ADHOC_CORRECT_SCORE",
            }
        )
        _json_dump(stage / "exact_n_plan.json", plan)

        match_by_idx = {int(row["match_idx"]): row for row in normalized}
        provisional_manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "capability_id": CAPABILITY_ID,
            "content_id_schema": CONTENT_ID_SCHEMA,
            "immutable": True,
            "append_only": True,
            "request_id": request_id,
            "idempotency_key_sha256": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
            "issue": issue,
            "requested_at_hkt": _iso_hkt(requested_at),
            "input_asof_hkt": _iso_hkt(input_asof),
            "requested_n": requested_n,
            "requested_budget_yuan": requested_budget_yuan,
            "base_cost_yuan": base_cost,
            "actual_cost_yuan": actual_cost,
            "unused_budget_yuan": round(requested_budget_yuan - actual_cost, 2),
            "budget_utilization": round(actual_cost / requested_budget_yuan, 8),
            "valid_until_hkt": _iso_hkt(valid_until) if valid_until else "",
            "sale_status_verified": sale_status_verified,
            "status": status,
            "structural_verification_status": "STRUCTURAL_INTEGRITY_PENDING",
            "research_evidence_eligible": False,
            "scheduled_freeze_event_id": None,
            "decision_input_sha256": str(decision_input["sha256"]),
            "eligible_denominator_sha256": str(eligibility["sha256"]),
            "exact_n_plan_sha256": str(plan["sha256"]),
            "source_snapshot_sha256": source_snapshot_sha256,
            "decision_variant_id": str(decision_input["decision_variant_id"]),
            "correct_score_status": "UNAVAILABLE_ADHOC_CORRECT_SCORE",
            "artifacts": [],
        }
        html_text = _render_html(manifest=provisional_manifest, plan=plan, match_by_idx=match_by_idx)
        html_path = stage / "adhoc_betting_view.html"
        html_path.write_text(html_text, encoding="utf-8", newline="\n")
        pdf_path = stage / "adhoc_betting_slip.pdf"
        pdf_engine = _write_pdf(html_text, pdf_path, self.font_file, request_id[:32])
        leg_path = stage / "ticket_legs.csv"
        leg_path.write_bytes(
            _csv_bytes(
                _ticket_leg_rows(
                    request_id=request_id,
                    tickets=tickets,
                    match_by_idx=match_by_idx,
                    valid_until_hkt=str(provisional_manifest["valid_until_hkt"]),
                ),
                [
                    "request_id",
                    "ticket_no",
                    "match_idx",
                    "match_id",
                    "selection_code",
                    "selection_label",
                    "kickoff_at_hkt",
                    "league",
                    "home",
                    "away",
                    "handicap_line",
                    "stake_multiplier",
                    "ticket_cost_yuan",
                    "valid_until_hkt",
                ],
            )
        )
        artifacts = [
            {"file": "eligible_denominator.json", "sha256": file_hash(stage / "eligible_denominator.json"), "artifact_type": "complete_eligibility_denominator"},
            {"file": "decision_input.json", "sha256": file_hash(stage / "decision_input.json"), "artifact_type": "request_time_decision_input"},
            {"file": "exact_n_plan.json", "sha256": file_hash(stage / "exact_n_plan.json"), "artifact_type": "exact_n_portfolio"},
            {"file": "adhoc_betting_view.html", "sha256": file_hash(html_path), "artifact_type": "operational_html_view"},
            {"file": "adhoc_betting_slip.pdf", "sha256": file_hash(pdf_path), "artifact_type": "a4_operational_pdf", "source_html_sha256": file_hash(html_path)},
            {"file": "ticket_legs.csv", "sha256": file_hash(leg_path), "artifact_type": "ticket_legs"},
        ]
        manifest = {
            **provisional_manifest,
            "structural_verification_status": "STRUCTURAL_INTEGRITY_PASS",
            "pdf_engine": pdf_engine,
            "pdf_font_reference": self._font_reference(),
            "pdf_font_sha256": file_hash(self.font_file),
            "artifacts": artifacts,
        }
        package_id = _package_identity(manifest)
        manifest["package_id"] = package_id
        manifest = _with_hash(manifest)
        _json_dump(stage / "adhoc_request_manifest.json", manifest)
        (stage / "SHA256SUMS").write_text(
            "".join(
                f"{file_hash(path)}  {path.name}\n"
                for path in sorted(stage.iterdir())
                if path.is_file() and path.name != "SHA256SUMS"
            ),
            encoding="utf-8",
        )
        return manifest, plan, eligibility, package_id

    def _font_reference(self) -> str:
        try:
            return self.font_file.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return f"external://adhoc-font/sha256/{file_hash(self.font_file)}"

    def get(self, request_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        clock = (now or datetime.now(timezone.utc)).astimezone(HKT)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM adhoc_betting_request_ledger WHERE request_id=? AND state='PUBLISHED'",
                (str(request_id),),
            ).fetchone()
        if row is None:
            raise AdhocPlanNotFound("adhoc request was not found")
        _path, manifest, plan, denominator = _load_package(self.root, row)
        return self._public_result(
            manifest=manifest,
            plan=plan,
            denominator=denominator,
            now=clock,
            idempotent=True,
        )

    def artifact_path(
        self,
        request_id: str,
        *,
        fmt: str,
        now: datetime | None = None,
        clock_provider: Callable[[], datetime] | None = None,
        audit_only: bool = False,
    ) -> tuple[Path, dict[str, Any]]:
        """Return one verified artifact, checking operational expiry at response time.

        Runtime callers provide ``clock_provider`` so a request that crosses
        ``valid_until_hkt`` while its immutable package is being verified
        cannot still receive an operational download.  ``now`` remains for
        deterministic callers/tests, where its deliberately frozen value is
        used for both checks.
        """
        if now is not None and clock_provider is not None:
            raise AdhocBettingError("supply either now or clock_provider, not both")
        if clock_provider is None:
            frozen_clock = (now or datetime.now(timezone.utc)).astimezone(HKT)

            def clock_provider() -> datetime:
                return frozen_clock

        def trusted_clock() -> datetime:
            candidate = clock_provider()
            if not isinstance(candidate, datetime):
                raise AdhocBettingError("trusted adhoc clock must return a datetime")
            return candidate.astimezone(HKT)

        payload = self.get(request_id, now=trusted_clock())
        current = str(payload["current_status"])
        if not audit_only and current != "DOWNLOADABLE_CURRENT":
            raise AdhocBettingError(
                f"operational download disabled: {current}; generate a new adhoc request"
            )
        names = {
            "pdf": "adhoc_betting_slip.pdf",
            "html": "adhoc_betting_view.html",
            "csv": "ticket_legs.csv",
        }
        name = names.get(str(fmt).lower())
        if not name:
            raise AdhocBettingError("download format must be pdf, html, or csv")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM adhoc_betting_request_ledger WHERE request_id=? AND state='PUBLISHED'",
                (str(request_id),),
            ).fetchone()
        if row is None:
            raise AdhocPlanNotFound("adhoc request was not found")
        root, manifest, plan, denominator = _load_package(self.root, row)
        target = root / name
        if not target.is_file():
            raise AdhocBettingError("verified adhoc package is missing the requested artifact")

        # This is intentionally after the complete package/ledger/SHA256SUMS
        # verification above and immediately before the caller constructs its
        # file response.  A request that crosses the immutable validity bound
        # during verification must fail closed rather than carry a stale
        # OPERATIONAL_CURRENT result into ``send_file``.
        final_payload = self._public_result(
            manifest=manifest,
            plan=plan,
            denominator=denominator,
            now=trusted_clock(),
            idempotent=True,
        )
        current = str(final_payload["current_status"])
        if not audit_only and current != "DOWNLOADABLE_CURRENT":
            raise AdhocBettingError(
                f"operational download disabled: {current}; generate a new adhoc request"
            )
        return target, {**final_payload, "audit_only_download": bool(audit_only)}

    @staticmethod
    def _current_status(manifest: dict[str, Any], now: datetime) -> str:
        immutable_status = str(manifest.get("status") or "FAILED_CLOSED")
        if immutable_status == "UNAVAILABLE_ADHOC_PLAN":
            return "UNAVAILABLE_ADHOC_PLAN"
        if immutable_status != "READY_FOR_REVIEW":
            return "FAILED_CLOSED"
        if not bool(manifest.get("sale_status_verified")):
            return "UNVERIFIED_SALE_STATE"
        valid_until = str(manifest.get("valid_until_hkt") or "")
        if not valid_until:
            return "UNVERIFIED_SALE_STATE"
        if now >= _parse_hkt(valid_until, label="valid_until_hkt"):
            return "EXPIRED_NOT_PURCHASABLE"
        return "DOWNLOADABLE_CURRENT"

    def _public_result(
        self,
        *,
        manifest: dict[str, Any],
        plan: dict[str, Any],
        denominator: dict[str, Any],
        now: datetime,
        idempotent: bool,
    ) -> dict[str, Any]:
        current_status = self._current_status(manifest, now)
        included = denominator.get("included") if isinstance(denominator.get("included"), list) else []
        match_by_idx = {
            int(row["match_idx"]): row
            for row in included
            if isinstance(row, dict) and str(row.get("match_idx") or "").isdigit()
        }
        tickets: list[dict[str, Any]] = []
        for ticket in plan.get("tickets", []):
            if not isinstance(ticket, dict):
                continue
            legs: list[dict[str, Any]] = []
            for match_idx, code_text in zip(ticket.get("match_indices", []), ticket.get("leg_codes", [])):
                match = match_by_idx.get(int(match_idx), {})
                codes = [code for code in str(code_text).split("+") if code]
                legs.append(
                    {
                        "match_idx": int(match_idx),
                        "match_id": str(match.get("match_id") or ""),
                        "selection_code": "+".join(codes),
                        "selection_label": _selection_label(codes),
                        "kickoff_at_hkt": str(match.get("kickoff_at_hkt") or ""),
                        "league": str(match.get("league") or ""),
                        "home": str(match.get("home") or ""),
                        "away": str(match.get("away") or ""),
                        "handicap_line": match.get("handicap_line"),
                    }
                )
            tickets.append(
                {
                    "ticket_no": int(ticket.get("ticket_no") or 0),
                    "actual_n": int(ticket.get("actual_n") or 0),
                    "stake_multiplier": int(ticket.get("stake_multiplier") or 0),
                    "base_cost_yuan": float(ticket.get("base_cost_yuan") or 0),
                    "cost_yuan": float(ticket.get("cost_yuan") or 0),
                    "legs": legs,
                }
            )
        exclusion_counts: Counter[str] = Counter()
        for row in denominator.get("excluded", []):
            if isinstance(row, dict):
                for reason in row.get("exclusion_reasons", []):
                    exclusion_counts[str(reason)] += 1
        return {
            "schema_version": "adhoc_betting_api_v1",
            "capability_id": CAPABILITY_ID,
            "request_id": str(manifest["request_id"]),
            "issue": str(manifest["issue"]),
            "requested_at_hkt": str(manifest["requested_at_hkt"]),
            "input_asof_hkt": str(manifest["input_asof_hkt"]),
            "requested_n": int(manifest["requested_n"]),
            "requested_budget_yuan": int(manifest["requested_budget_yuan"]),
            "base_cost_yuan": float(manifest["base_cost_yuan"]),
            "actual_cost_yuan": float(manifest["actual_cost_yuan"]),
            "unused_budget_yuan": float(manifest["unused_budget_yuan"]),
            "budget_utilization": float(manifest["budget_utilization"]),
            "valid_until_hkt": str(manifest.get("valid_until_hkt") or ""),
            "status": str(manifest["status"]),
            "current_status": current_status,
            "structural_verification_status": str(manifest["structural_verification_status"]),
            "sale_status_verified": bool(manifest["sale_status_verified"]),
            "operational_downloads_enabled": current_status == "DOWNLOADABLE_CURRENT",
            "audit_downloads_available": True,
            "ticket_count": len(tickets),
            "eligible_match_count": int(denominator.get("eligible_match_count") or 0),
            "excluded_match_count": int(denominator.get("excluded_match_count") or 0),
            "exclusion_counts": dict(sorted(exclusion_counts.items())),
            "denominator": _public_denominator_rows(
                [
                    row
                    for row in [*denominator.get("included", []), *denominator.get("excluded", [])]
                    if isinstance(row, dict)
                ]
            ),
            "tickets": tickets,
            "plan_reason": str(plan.get("reason") or ""),
            "unavailable_reasons": list(plan.get("unavailable_reasons") or []),
            "input_sha256": str(manifest["decision_input_sha256"]),
            "manifest_sha256": str(manifest["sha256"]),
            "package_id": str(manifest["package_id"]),
            "research_evidence_eligible": False,
            "scheduled_freeze_event_id": None,
            "correct_score_status": "UNAVAILABLE_ADHOC_CORRECT_SCORE",
            "idempotent": idempotent,
        }


def verify_package(root: str | os.PathLike[str], *, allow_staging: bool = False) -> dict[str, Any]:
    """Verify the full package before API exposure or download.

    This intentionally validates semantic linkage as well as file hashes so a
    rehashed, self-consistent-looking package cannot claim a different N,
    budget, scheduled identity, or mutable output directory.
    """

    path = Path(root)
    if not path.is_dir():
        raise AdhocBettingError("adhoc package directory is missing")
    if any(item.is_symlink() or not item.is_file() for item in path.iterdir()):
        raise AdhocBettingError("adhoc package contains a non-regular artifact")
    names = {item.name for item in path.iterdir() if item.is_file()}
    if not REQUIRED_PACKAGE_FILES.issubset(names):
        raise AdhocBettingError("adhoc package required file set is incomplete")
    sums_path = path / "SHA256SUMS"
    sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        try:
            claimed, name = line.split("  ", 1)
        except ValueError as exc:
            raise AdhocBettingError("adhoc SHA256SUMS is malformed") from exc
        target = Path(name)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", claimed)
            or target.is_absolute()
            or ".." in target.parts
            or name in sums
        ):
            raise AdhocBettingError("adhoc SHA256SUMS has an invalid entry")
        sums[name] = claimed
    actual_files = {item.name for item in path.iterdir() if item.is_file() and item.name != "SHA256SUMS"}
    if set(sums) != actual_files:
        raise AdhocBettingError("adhoc SHA256SUMS file set mismatch")
    for name, claimed in sums.items():
        if file_hash(path / name) != claimed:
            raise AdhocBettingError(f"adhoc package file hash mismatch: {name}")

    manifest = _json_load(path / "adhoc_request_manifest.json")
    denominator = _json_load(path / "eligible_denominator.json")
    decision_input = _json_load(path / "decision_input.json")
    plan = _json_load(path / "exact_n_plan.json")
    for payload, label in (
        (manifest, "adhoc manifest"),
        (denominator, "eligible denominator"),
        (decision_input, "decision input"),
        (plan, "exact-N plan"),
    ):
        _verify_payload_hash(payload, label=label)
    if (
        manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION
        or manifest.get("capability_id") != CAPABILITY_ID
        or manifest.get("content_id_schema") != CONTENT_ID_SCHEMA
        or manifest.get("immutable") is not True
        or manifest.get("append_only") is not True
        or manifest.get("research_evidence_eligible") is not False
        or manifest.get("scheduled_freeze_event_id") is not None
    ):
        raise AdhocBettingError("adhoc/scheduled separation contract failed")
    package_id = str(manifest.get("package_id") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", package_id) or package_id != _package_identity(manifest):
        raise AdhocBettingError("adhoc package content identity mismatch")
    if not allow_staging and path.name != package_id:
        raise AdhocBettingError("adhoc package directory is not content-addressed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise AdhocBettingError("adhoc manifest artifacts are missing")
    artifact_hashes = {
        str(item.get("file")): str(item.get("sha256"))
        for item in artifacts
        if isinstance(item, dict)
    }
    expected_artifacts = REQUIRED_PACKAGE_FILES - {"SHA256SUMS", "adhoc_request_manifest.json"}
    if set(artifact_hashes) != expected_artifacts:
        raise AdhocBettingError("adhoc manifest artifact set mismatch")
    for name, claimed in artifact_hashes.items():
        if claimed != file_hash(path / name):
            raise AdhocBettingError(f"adhoc manifest artifact hash mismatch: {name}")
    if (
        str(manifest.get("decision_input_sha256")) != str(decision_input.get("sha256"))
        or str(manifest.get("eligible_denominator_sha256")) != str(denominator.get("sha256"))
        or str(manifest.get("exact_n_plan_sha256")) != str(plan.get("sha256"))
    ):
        raise AdhocBettingError("adhoc manifest semantic artifact linkage mismatch")
    source_snapshot_sha256 = str(manifest.get("source_snapshot_sha256") or "")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", source_snapshot_sha256)
        or source_snapshot_sha256 != str(decision_input.get("source_snapshot_sha256") or "")
    ):
        raise AdhocBettingError("adhoc request-time source binding mismatch")
    common = ("request_id", "issue", "requested_n", "requested_budget_yuan")
    if any(manifest.get(key) != plan.get(key) for key in common):
        raise AdhocBettingError("adhoc exact-N plan identity mismatch")
    if any(manifest.get(key) != denominator.get(key) for key in ("request_id", "issue")):
        raise AdhocBettingError("adhoc denominator identity mismatch")
    if any(manifest.get(key) != decision_input.get(key) for key in ("request_id", "issue", "input_asof_hkt")):
        raise AdhocBettingError("adhoc decision input identity mismatch")
    if str(decision_input.get("decision_variant_id") or "") != "active_v3.3.3":
        raise AdhocBettingError("adhoc decision input is not the formal active_v3.3.3 variant")
    requested_at = _parse_hkt(manifest.get("requested_at_hkt"), label="requested_at_hkt")
    input_asof = _parse_hkt(manifest.get("input_asof_hkt"), label="input_asof_hkt")
    if input_asof > requested_at:
        raise AdhocBettingError("adhoc decision input as-of clock is after request clock")
    try:
        n_value = int(manifest.get("requested_n") or 0)
        budget = float(manifest.get("requested_budget_yuan") or 0)
    except (TypeError, ValueError) as exc:
        raise AdhocBettingError("adhoc request N/budget contract is invalid") from exc
    if n_value not in ALLOWED_N_VALUES or budget not in ALLOWED_BUDGETS:
        raise AdhocBettingError("adhoc request N/budget contract is invalid")
    tickets = plan.get("tickets")
    if not isinstance(tickets, list):
        raise AdhocBettingError("adhoc tickets are malformed")

    def indexed_rows(rows: object, *, label: str) -> dict[int, dict[str, Any]]:
        if not isinstance(rows, list):
            raise AdhocBettingError(f"adhoc {label} rows are malformed")
        indexed: dict[int, dict[str, Any]] = {}
        for item in rows:
            if not isinstance(item, dict):
                raise AdhocBettingError(f"adhoc {label} row is malformed")
            try:
                idx = int(item.get("match_idx"))
            except (TypeError, ValueError) as exc:
                raise AdhocBettingError(f"adhoc {label} row has invalid match index") from exc
            if idx <= 0 or idx in indexed:
                raise AdhocBettingError(f"adhoc {label} rows have duplicate match indices")
            indexed[idx] = item
        return indexed

    included_rows = indexed_rows(denominator.get("included"), label="included denominator")
    excluded_rows = indexed_rows(denominator.get("excluded"), label="excluded denominator")
    if set(included_rows) & set(excluded_rows):
        raise AdhocBettingError("adhoc denominator included/excluded membership overlaps")
    decision_rows = indexed_rows(decision_input.get("matches"), label="decision input")
    denominator_rows = {**included_rows, **excluded_rows}
    if set(decision_rows) != set(denominator_rows) or any(
        decision_rows[idx] != denominator_rows[idx] for idx in decision_rows
    ):
        raise AdhocBettingError("adhoc denominator is not bound to decision input bytes")
    source_metadata = decision_input.get("source_metadata")
    if not isinstance(source_metadata, dict):
        raise AdhocBettingError("adhoc decision input source metadata is missing")
    try:
        source_request_clock = _parse_hkt(
            source_metadata.get("request_clock_hkt"), label="source_metadata.request_clock_hkt"
        )
    except AdhocBettingError as exc:
        raise AdhocBettingError("adhoc source request clock is missing") from exc
    if source_request_clock != requested_at:
        raise AdhocBettingError("adhoc source request clock is not bound to manifest request time")
    formal_input = source_metadata.get("formal_decision_input")
    formal_generated_at: datetime | None = None
    if isinstance(formal_input, dict):
        try:
            formal_generated_at = _parse_hkt(
                formal_input.get("generated_at_hkt"), label="formal_decision_input.generated_at_hkt"
            )
        except AdhocBettingError:
            formal_generated_at = None
    if formal_generated_at is not None and formal_generated_at > requested_at:
        raise AdhocBettingError("adhoc formal decision input clock is after request time")
    if manifest.get("status") == "READY_FOR_REVIEW" and formal_generated_at is None:
        raise AdhocBettingError("adhoc formal decision input clock is missing")
    if manifest.get("status") == "READY_FOR_REVIEW":
        if (
            not isinstance(formal_input, dict)
            or str(formal_input.get("status") or "") != "VERIFIED_FORMAL_INPUT"
            or str(formal_input.get("decision_variant_id") or "") != "active_v3.3.3"
        ):
            raise AdhocBettingError("adhoc formal decision input contract is invalid")
        for field in ("structured_csv_sha256", "structured_receipt_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(formal_input.get(field) or "")):
                raise AdhocBettingError("adhoc formal decision input hash is missing")
    observed_clocks: list[datetime] = []
    required_provenance_clocks = (
        "match_html_fetched_at_hkt",
        "nowscore_fetched_at_hkt",
        "live_sp_source_updated_at_hkt",
        "live_sp_fetched_at_hkt",
        "market_source_observed_at_hkt",
        "market_fetched_at_hkt",
        "market_latest_observed_at_hkt",
    )
    for idx, row in decision_rows.items():
        observed_text = str(row.get("source_observed_at_hkt") or "")
        if observed_text:
            observed = _parse_hkt(observed_text, label="source_observed_at_hkt")
            if observed > requested_at:
                raise AdhocBettingError("adhoc input observation is after request time")
            observed_clocks.append(observed)
        if idx not in included_rows:
            continue
        provenance = row.get("source_provenance")
        if not isinstance(provenance, dict):
            raise AdhocBettingError("adhoc included row lacks source provenance")
        if formal_generated_at is None:
            raise AdhocBettingError("adhoc included row lacks formal decision clock")
        clocks: list[datetime] = [formal_generated_at]
        for field in required_provenance_clocks:
            try:
                clock = _parse_hkt(provenance.get(field), label=f"source_provenance.{field}")
            except AdhocBettingError as exc:
                raise AdhocBettingError("adhoc included row lacks complete source/fetch clocks") from exc
            if clock > requested_at:
                raise AdhocBettingError("adhoc included row source/fetch clock is after request time")
            clocks.append(clock)
        try:
            row_formal_clock = _parse_hkt(
                provenance.get("formal_decision_generated_at_hkt"),
                label="source_provenance.formal_decision_generated_at_hkt",
            )
        except AdhocBettingError as exc:
            raise AdhocBettingError("adhoc included row lacks formal decision clock") from exc
        if row_formal_clock != formal_generated_at:
            raise AdhocBettingError("adhoc formal decision clock differs across package bindings")
        clocks.append(row_formal_clock)
        for field in ("market_outcome_source_clocks_hkt", "market_outcome_fetched_clocks_hkt"):
            vector = provenance.get(field)
            if not isinstance(vector, dict) or set(vector) != set(OUTCOME_LABELS):
                raise AdhocBettingError("adhoc included row lacks complete per-outcome market clocks")
            for code in OUTCOME_LABELS:
                try:
                    clock = _parse_hkt(vector.get(code), label=f"source_provenance.{field}.{code}")
                except AdhocBettingError as exc:
                    raise AdhocBettingError("adhoc included row has invalid per-outcome market clock") from exc
                if clock > requested_at:
                    raise AdhocBettingError("adhoc per-outcome market clock is after request time")
                clocks.append(clock)
        if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get("live_sp_snapshot_sha256") or "")):
            raise AdhocBettingError("adhoc included row lacks live-SP snapshot hash")
        if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get("market_snapshot_sha256") or "")):
            raise AdhocBettingError("adhoc included row lacks market snapshot hash")
        if observed_text and _parse_hkt(observed_text, label="source_observed_at_hkt") != min(clocks):
            raise AdhocBettingError("adhoc row observation clock is not the oldest bound source clock")
        if set(row.get("sp") or {}) != set(OUTCOME_LABELS) or any(
            _as_number((row.get("sp") or {}).get(code), label=f"sp_{code}") <= 0
            for code in OUTCOME_LABELS
        ):
            raise AdhocBettingError("adhoc included row lacks complete live price vector")
    if observed_clocks and input_asof != min(observed_clocks):
        raise AdhocBettingError("adhoc input as-of clock is not bound to the frozen denominator")
    if manifest.get("status") == "READY_FOR_REVIEW" and not observed_clocks:
        raise AdhocBettingError("ready adhoc plan lacks bound input observations")
    try:
        max_source_age_seconds = int(denominator.get("max_source_age_seconds", -1))
        safety_margin_seconds = int(denominator.get("safety_margin_seconds", -1))
    except (TypeError, ValueError) as exc:
        raise AdhocBettingError("adhoc denominator timing policy is invalid") from exc
    if max_source_age_seconds < 1 or safety_margin_seconds < 0:
        raise AdhocBettingError("adhoc denominator timing policy is invalid")
    max_source_age = timedelta(seconds=max_source_age_seconds)
    safety_margin_delta = timedelta(seconds=safety_margin_seconds)

    total = 0.0
    selected_rows: dict[int, dict[str, Any]] = {}
    for ticket in tickets:
        if not isinstance(ticket, dict):
            raise AdhocBettingError("adhoc ticket is malformed")
        indices = ticket.get("match_indices")
        codes = ticket.get("leg_codes")
        try:
            exact_n_contract = (
                isinstance(indices, list)
                and isinstance(codes, list)
                and len(indices) == n_value
                and len(codes) == n_value
                and len({int(value) for value in indices}) == n_value
                and int(ticket.get("actual_n") or 0) == n_value
                and int(ticket.get("stake_multiplier") or 0) >= 1
            )
        except (TypeError, ValueError):
            exact_n_contract = False
        if not exact_n_contract:
            raise AdhocBettingError("adhoc exact-N ticket contract failed")
        cost = _as_number(ticket.get("cost_yuan"), label="ticket cost")
        ticket_base_cost = _as_number(ticket.get("base_cost_yuan"), label="ticket base cost")
        multiplier = int(ticket.get("stake_multiplier") or 0)
        if cost <= 0 or ticket_base_cost <= 0 or round(ticket_base_cost * multiplier, 2) != round(cost, 2):
            raise AdhocBettingError("adhoc ticket cost is invalid")
        for raw_idx, raw_codes in zip(indices, codes):
            idx = int(raw_idx)
            row = included_rows.get(idx)
            if row is None:
                raise AdhocBettingError("adhoc ticket selects an excluded or absent match")
            ticket_codes = [code for code in str(raw_codes).split("+") if code]
            allowed_codes = {str(code) for code in row.get("selection_codes") or []}
            if not ticket_codes or not set(ticket_codes).issubset(allowed_codes):
                raise AdhocBettingError("adhoc ticket selection is not bound to formal decision input")
            rechecked = _normalize_match(
                row,
                requested_at=requested_at,
                max_source_age=max_source_age,
                safety_margin=safety_margin_delta,
            )
            if not rechecked["included"] or rechecked != row:
                raise AdhocBettingError("adhoc ticket no longer satisfies its frozen eligibility contract")
            selected_rows[idx] = row
        total += cost
    actual_cost = _as_number(manifest.get("actual_cost_yuan"), label="actual_cost_yuan")
    base_cost = _as_number(manifest.get("base_cost_yuan"), label="base_cost_yuan")
    if round(total, 2) != round(actual_cost, 2) or actual_cost > budget + 1e-9:
        raise AdhocBettingError("adhoc actual cost does not reconcile to tickets/budget")
    if (
        round(sum(_as_number(ticket.get("base_cost_yuan"), label="ticket base cost") for ticket in tickets), 2)
        != round(base_cost, 2)
        or round(_as_number(plan.get("base_cost_yuan"), label="plan base_cost_yuan"), 2)
        != round(base_cost, 2)
        or round(_as_number(plan.get("actual_cost_yuan"), label="plan actual_cost_yuan"), 2)
        != round(actual_cost, 2)
        or round(_as_number(plan.get("unused_budget_yuan"), label="plan unused_budget_yuan"), 2)
        != round(_as_number(manifest.get("unused_budget_yuan"), label="unused_budget_yuan"), 2)
        or round(actual_cost + _as_number(manifest.get("unused_budget_yuan"), label="unused_budget_yuan"), 2)
        != round(budget, 2)
        or round(_as_number(plan.get("budget_utilization"), label="plan budget_utilization"), 8)
        != round(actual_cost / budget, 8)
        or round(_as_number(manifest.get("budget_utilization"), label="budget_utilization"), 8)
        != round(actual_cost / budget, 8)
    ):
        raise AdhocBettingError("adhoc plan and manifest costs do not reconcile")
    if str(plan.get("status") or "") != str(manifest.get("status") or ""):
        raise AdhocBettingError("adhoc plan/manifest status mismatch")
    if (
        str(plan.get("correct_score_status") or "") != "UNAVAILABLE_ADHOC_CORRECT_SCORE"
        or str(manifest.get("correct_score_status") or "") != "UNAVAILABLE_ADHOC_CORRECT_SCORE"
    ):
        raise AdhocBettingError("adhoc correct-score execution boundary failed")
    if manifest.get("status") == "READY_FOR_REVIEW":
        if not tickets or manifest.get("sale_status_verified") is not True:
            raise AdhocBettingError("ready adhoc plan lacks verified tickets")
        valid_until = _parse_hkt(manifest.get("valid_until_hkt"), label="valid_until_hkt")
        if valid_until <= requested_at:
            raise AdhocBettingError("adhoc validity window is not future-facing")
        safety_margin = int(denominator.get("safety_margin_seconds", -1))
        if safety_margin < 0:
            raise AdhocBettingError("adhoc safety margin is invalid")
        try:
            expected_valid_until = min(
                _parse_hkt(row.get("sale_cutoff_hkt"), label="sale_cutoff_hkt")
                - timedelta(seconds=safety_margin)
                for row in selected_rows.values()
            )
        except ValueError as exc:
            raise AdhocBettingError("adhoc selected tickets lack sale cutoffs") from exc
        if valid_until != expected_valid_until:
            raise AdhocBettingError("adhoc validity window is not bound to selected sale cutoffs")
    elif manifest.get("status") != "UNAVAILABLE_ADHOC_PLAN":
        raise AdhocBettingError("adhoc immutable status is unsupported")
    if len(denominator.get("included") or []) != int(
        denominator.get("eligible_match_count", -1)
    ):
        raise AdhocBettingError("adhoc denominator included count mismatch")
    if len(denominator.get("excluded") or []) != int(
        denominator.get("excluded_match_count", -1)
    ):
        raise AdhocBettingError("adhoc denominator excluded count mismatch")
    if (
        int(denominator.get("considered_match_count", -1))
        != int(denominator.get("eligible_match_count", 0))
        + int(denominator.get("excluded_match_count", 0))
    ):
        raise AdhocBettingError("adhoc denominator count does not reconcile")
    return {
        "status": "PASS",
        "request_id": str(manifest["request_id"]),
        "package_id": package_id,
        "manifest_sha256": str(manifest["sha256"]),
        "ticket_count": len(tickets),
        "actual_cost_yuan": actual_cost,
    }
