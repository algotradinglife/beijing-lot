"""Fail-closed audit-only human views for immutable exact-N freezes."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import html
import io
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.verify_exact_n_freeze import verify_directory as verify_exact_n_freeze
from src.segment_recovery import verify_manifest as verify_recovery_manifest

CAPABILITY_ID = "BJ-FREEZE-REVIEW-001"
RENDERER_VERSION = "1.0.0"
SCHEMA_VERSION = "freeze_review_bundle_v1"
CONTENT_ID_SCHEMA = "freeze_review_content_id_v1"
SOURCE_INTEGRITY_PASS = "SOURCE_INTEGRITY_PASS"
USAGE_BOUNDARY = "RESEARCH_AUDIT_ONLY_NOT_FOR_PURCHASE"
PORTABLE_CLEAN_CHECKOUT = "PORTABLE_CLEAN_CHECKOUT"
EXTERNAL_ASSETS_REQUIRED = "EXTERNAL_ASSETS_REQUIRED"
N_VALUES = (3, 4, 5, 6, 7)
BUDGETS = (512, 768, 1024)
HKT = ZoneInfo("Asia/Hong_Kong")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CODE_LABELS = {
    "3": "让球胜",
    "1": "让球平",
    "0": "让球负",
}
REQUIRED_METADATA = ("league", "home", "away", "handicap_line")


class FreezeReviewError(ValueError):
    """The source or derived human view violates its immutable contract."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    claimed = str(unsigned.pop("sha256", ""))
    actual = digest(unsigned)
    if claimed != actual:
        raise FreezeReviewError("payload sha256 mismatch")
    return claimed


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeReviewError(f"cannot read JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise FreezeReviewError(f"JSON object required: {path.name}")
    return value


def _money(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FreezeReviewError("invalid monetary value") from exc
    if not result.is_finite():
        raise FreezeReviewError("non-finite monetary value")
    return result


def _money_text(value: object) -> str:
    amount = _money(value)
    if amount == amount.to_integral():
        return str(int(amount))
    return format(amount.quantize(Decimal("0.01")), "f")


def _normalized_hkt(value: object, *, label: str = "clock") -> tuple[str, str]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise FreezeReviewError(f"invalid {label} clock") from exc
    if parsed.tzinfo is None:
        raise FreezeReviewError(f"{label} clock lacks timezone")
    normalized = parsed.astimezone(HKT)
    if normalized.utcoffset() != HKT.utcoffset(normalized):
        raise FreezeReviewError(f"{label} clock is not normalizable to HKT")
    return (
        normalized.isoformat(timespec="seconds"),
        normalized.strftime("%m-%d %H:%M HKT"),
    )


def _clock_record(kickoff: object) -> dict[str, str]:
    kickoff_iso, kickoff_display = _normalized_hkt(kickoff, label="kickoff")
    return {
        "kickoff_at_hkt": kickoff_iso,
        "kickoff_display": kickoff_display,
    }


def _selection_label(raw_code: object) -> str:
    raw = str(raw_code)
    parts = raw.split("+")
    if (
        not parts
        or any(part not in CODE_LABELS for part in parts)
        or len(set(parts)) != len(parts)
    ):
        raise FreezeReviewError(f"unsupported or duplicate leg code: {raw}")
    return "+".join(CODE_LABELS[part] for part in parts)


def _read_structured_rows(path: Path, issue: str) -> dict[int, dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            fields = set(reader.fieldnames or ())
    except (OSError, csv.Error) as exc:
        raise FreezeReviewError("cannot read frozen structured input") from exc
    required = {"issue", "match_idx", *REQUIRED_METADATA}
    if not required.issubset(fields):
        raise FreezeReviewError("frozen structured input metadata columns missing")
    result: dict[int, dict[str, str]] = {}
    for row in rows:
        if str(row.get("issue") or "") != issue:
            raise FreezeReviewError("structured input issue mismatch")
        try:
            match_idx = int(str(row.get("match_idx") or ""))
        except ValueError as exc:
            raise FreezeReviewError("structured input match index malformed") from exc
        if match_idx in result:
            raise FreezeReviewError("duplicate structured input match metadata")
        result[match_idx] = {key: str(value or "") for key, value in row.items()}
    return result


def _recovery_kickoffs(
    source: Path,
    manifest: dict[str, Any],
    artifact_entries: dict[str, dict[str, Any]],
) -> dict[int, dict[str, str]]:
    recovery_path = source / "recovery_manifest.json"
    recovery = _load_json(recovery_path)
    semantic_hash = verify_recovery_manifest(recovery)
    recovery_hash = str(manifest.get("recovery_manifest_sha256") or "")
    segment_hash = str(manifest.get("segment_manifest_sha256") or "")
    entry = artifact_entries.get("recovery_manifest.json")
    if (
        not recovery_hash
        or semantic_hash != recovery_hash
        or semantic_hash != segment_hash
        or not entry
        or str(entry.get("semantic_sha256") or "") != semantic_hash
        or str(entry.get("sha256") or "") != file_hash(recovery_path)
    ):
        raise FreezeReviewError("recovery manifest hash linkage mismatch")
    if str(recovery.get("child_identity") or "") != str(
        manifest.get("segment_identity") or ""
    ) or int(recovery.get("parent_segment_idx", -1)) != int(
        manifest.get("parent_segment_idx", -2)
    ):
        raise FreezeReviewError("recovery identity mismatch")
    included = recovery.get("included")
    if not isinstance(included, list):
        raise FreezeReviewError("recovery membership missing")
    result: dict[int, dict[str, str]] = {}
    for item in included:
        if not isinstance(item, dict):
            raise FreezeReviewError("recovery membership malformed")
        try:
            match_idx = int(item["match_idx"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FreezeReviewError("recovery match index malformed") from exc
        if match_idx in result:
            raise FreezeReviewError("duplicate recovery kickoff")
        result[match_idx] = _clock_record(item.get("kickoff_at_hkt"))
    expected = [int(value) for value in manifest.get("segment_match_indices", [])]
    if list(result) != expected or set(result) != set(expected):
        raise FreezeReviewError("recovery kickoff membership mismatch")
    return result


def _standard_kickoffs(
    rows: dict[int, dict[str, str]], members: list[int]
) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for match_idx in members:
        row = rows.get(match_idx)
        if row is None or "kickoff_at_hkt" not in row:
            raise FreezeReviewError(
                "non-recovery package lacks frozen structured-input kickoff"
            )
        result[match_idx] = _clock_record(row["kickoff_at_hkt"])
    return result


def _plan_concentration(
    tickets: list[dict[str, Any]], actual_cost: Decimal
) -> dict[str, Any]:
    costs = [_money(ticket["cost_yuan"]) for ticket in tickets]
    appearances = Counter(
        int(match_idx) for ticket in tickets for match_idx in ticket["match_indices"]
    )
    max_cost = max(costs, default=Decimal("0"))
    max_appearance = max(appearances.values(), default=0)
    return {
        "max_ticket_cost_yuan": float(max_cost),
        "max_ticket_cost_share": (
            float(max_cost / actual_cost) if actual_cost else 0.0
        ),
        "max_match_ticket_appearances": max_appearance,
        "max_match_ticket_share": (max_appearance / len(tickets) if tickets else 0.0),
    }


def load_source_model(source_package: Path) -> dict[str, Any]:
    """Verify and normalize a source package without reading outside it."""
    source = source_package.expanduser().resolve()
    if not source.is_dir():
        raise FreezeReviewError("source package directory missing")
    exact_receipt = verify_exact_n_freeze(source)
    if exact_receipt.get("status") != "PASS":
        raise FreezeReviewError("source exact-N verifier did not pass")
    manifest = _load_json(source / "manifest.json")
    manifest_payload_sha = _payload_hash(manifest)
    artifact_entries = {
        str(item.get("file")): item
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    issue = str(manifest.get("issue") or "")
    members = [int(value) for value in manifest.get("segment_match_indices", [])]
    structured_rows = _read_structured_rows(source / "structured_input.csv", issue)
    is_recovery = bool(manifest.get("recovery_manifest_sha256"))
    kickoffs = (
        _recovery_kickoffs(source, manifest, artifact_entries)
        if is_recovery
        else _standard_kickoffs(structured_rows, members)
    )
    score = _load_json(source / "correct_score_audit.json")
    if score.get("status") != "UNAVAILABLE_CORRECT_SCORE_PLAN":
        raise FreezeReviewError("correct-score plan must remain separately unavailable")

    plans: list[dict[str, Any]] = []
    for n in N_VALUES:
        for budget in BUDGETS:
            filename = f"exact_n_{n}_budget_{budget}.json"
            payload = _load_json(source / filename)
            payload_sha = _payload_hash(payload)
            if (
                int(payload.get("requested_n", -1)) != n
                or int(payload.get("artifact_n", -1)) != n
                or int(payload.get("recommended_n", -1)) != n
                or int(payload.get("requested_budget_yuan", -1)) != budget
            ):
                raise FreezeReviewError("plan N/budget identity mismatch")
            if str(payload.get("status")) != "FROZEN_EXACT_N_BUDGET":
                plans.append(
                    {
                        "n": n,
                        "budget": budget,
                        "status": str(payload.get("status") or "UNAVAILABLE"),
                        "source_file": filename,
                        "source_plan_sha256": payload_sha,
                        "tickets": [],
                        "actual_cost": Decimal("0"),
                        "unused_budget": Decimal(str(budget)),
                        "concentration": _plan_concentration([], Decimal("0")),
                    }
                )
                continue
            tickets = payload.get("tickets")
            if not isinstance(tickets, list) or not tickets:
                raise FreezeReviewError("frozen plan has no tickets")
            actual_cost = _money(payload.get("actual_cost_yuan"))
            if actual_cost > Decimal(budget):
                raise FreezeReviewError("plan budget exceeded")
            rendered_tickets: list[dict[str, Any]] = []
            running_cost = Decimal("0")
            for ticket_number, ticket in enumerate(tickets, start=1):
                if not isinstance(ticket, dict):
                    raise FreezeReviewError("ticket is not an object")
                indices = [int(value) for value in ticket.get("match_indices", [])]
                raw_codes = [str(value) for value in ticket.get("leg_codes", [])]
                if (
                    len(indices) != n
                    or len(raw_codes) != n
                    or int(ticket.get("actual_n", -1)) != n
                ):
                    raise FreezeReviewError("ticket exact-N mismatch")
                multiplier = int(ticket.get("stake_multiplier", -1))
                base_cost = _money(ticket.get("base_cost_yuan"))
                ticket_cost = _money(ticket.get("cost_yuan"))
                if multiplier <= 0 or base_cost * multiplier != ticket_cost:
                    raise FreezeReviewError("ticket multiplier/cost mismatch")
                running_cost += ticket_cost
                legs: list[dict[str, Any]] = []
                for leg_order, (match_idx, raw_code) in enumerate(
                    zip(indices, raw_codes, strict=True), start=1
                ):
                    metadata = structured_rows.get(match_idx)
                    if metadata is None or any(
                        not str(metadata.get(key) or "").strip()
                        for key in REQUIRED_METADATA
                    ):
                        raise FreezeReviewError("frozen match metadata missing")
                    kickoff = kickoffs.get(match_idx)
                    if kickoff is None:
                        raise FreezeReviewError("frozen match kickoff missing")
                    legs.append(
                        {
                            "leg_order": leg_order,
                            "match_idx": match_idx,
                            "raw_code": raw_code,
                            "selection_label": _selection_label(raw_code),
                            "kickoff_at_hkt": kickoff["kickoff_at_hkt"],
                            "kickoff_display": kickoff["kickoff_display"],
                            "league": metadata["league"].strip(),
                            "home": metadata["home"].strip(),
                            "away": metadata["away"].strip(),
                            "handicap_line": metadata["handicap_line"].strip(),
                        }
                    )
                rendered_tickets.append(
                    {
                        "ticket_number": ticket_number,
                        "actual_n": n,
                        "stake_multiplier": multiplier,
                        "base_cost_yuan": float(base_cost),
                        "cost_yuan": float(ticket_cost),
                        "match_indices": indices,
                        "leg_codes": raw_codes,
                        "legs": legs,
                    }
                )
            if running_cost != actual_cost:
                raise FreezeReviewError("ticket sum differs from actual cost")
            unused = _money(payload.get("unused_budget_yuan"))
            if unused != Decimal(budget) - actual_cost:
                raise FreezeReviewError("unused budget mismatch")
            plan = {
                "n": n,
                "budget": budget,
                "status": "FROZEN_EXACT_N_BUDGET",
                "source_file": filename,
                "source_plan_sha256": payload_sha,
                "actual_cost": actual_cost,
                "unused_budget": unused,
                "tickets": rendered_tickets,
                "concentration": _plan_concentration(rendered_tickets, actual_cost),
            }
            plan["binding_sha256"] = digest(
                {
                    "issue": issue,
                    "segment_identity": manifest.get("segment_identity"),
                    "event_key": manifest.get("event_key"),
                    "source_manifest_sha256": file_hash(source / "manifest.json"),
                    "source_plan_sha256": payload_sha,
                    "n": n,
                    "budget": budget,
                    "actual_cost_yuan": float(actual_cost),
                    "tickets": rendered_tickets,
                }
            )
            plans.append(plan)
    return {
        "source": source,
        "exact_verification": exact_receipt,
        "manifest": manifest,
        "manifest_payload_sha256": manifest_payload_sha,
        "manifest_file_sha256": file_hash(source / "manifest.json"),
        "sha256s_sha256": file_hash(source / "SHA256SUMS"),
        "structured_input_sha256": file_hash(source / "structured_input.csv"),
        "correct_score_status": score["status"],
        "plans": plans,
    }


def _normalize_generated_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise FreezeReviewError("review generation clock must be timezone-aware")
    return datetime.fromisoformat(value.astimezone(HKT).isoformat(timespec="seconds"))


def bind_review_context(
    model: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    """Bind an audit-only view clock without changing any frozen ticket."""
    created = _normalize_generated_at(generated_at)
    created_text = created.isoformat(timespec="seconds")
    model["generated_at_hkt"] = created_text
    model["source_integrity_status"] = SOURCE_INTEGRITY_PASS
    model["usage_boundary"] = USAGE_BOUNDARY
    for plan in model["plans"]:
        if plan["status"] != "FROZEN_EXACT_N_BUDGET":
            continue
        plan["view_binding_sha256"] = digest(
            {
                "source_plan_binding_sha256": plan["binding_sha256"],
                "generated_at_hkt": created_text,
                "source_integrity_status": SOURCE_INTEGRITY_PASS,
                "usage_boundary": USAGE_BOUNDARY,
            }
        )
    return model


def _segment_label(manifest: dict[str, Any]) -> str:
    identity = str(manifest.get("segment_identity") or "")
    match = re.fullmatch(r"segment_(\d+)_recovery_(\d+)", identity)
    if match:
        return f"Segment #{match.group(1)} Recovery #{match.group(2)}"
    return f"Segment #{int(manifest.get('segment_idx', -1))}"


def _display_hkt(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise FreezeReviewError("invalid display clock") from exc
    if parsed.tzinfo is None:
        raise FreezeReviewError("display clock lacks timezone")
    return parsed.astimezone(HKT).strftime("%Y-%m-%d %H:%M:%S HKT")


def _render_html(model: dict[str, Any], plan: dict[str, Any]) -> str:
    manifest = model["manifest"]
    source_binding = str(plan["binding_sha256"])
    view_binding = str(plan["view_binding_sha256"])
    ticket_blocks: list[str] = []
    for ticket in plan["tickets"]:
        number = int(ticket["ticket_number"])
        leg_blocks = []
        for leg in ticket["legs"]:
            leg_blocks.append(
                f"""
        <li class="leg">
          <div class="leg-main"><span class="match">#{int(leg["match_idx"])}</span>
            <span class="choice">{html.escape(str(leg["selection_label"]))}
              <span class="raw">({html.escape(str(leg["raw_code"]))})</span>
            </span>
          </div>
          <div class="leg-meta">{html.escape(str(leg["kickoff_display"]))} ·
            {html.escape(str(leg["league"]))}</div>
          <div class="teams">{html.escape(str(leg["home"]))} vs
            {html.escape(str(leg["away"]))}
            <span class="handicap">让球：{html.escape(str(leg["handicap_line"]))}</span>
          </div>
        </li>"""
            )
        marker = f"N{plan['n']}-B{plan['budget']}-T{number:03d}"
        ticket_blocks.append(
            f"""
      <section class="ticket">
        <span class="audit-token">{marker}-BEGIN</span>
        <div class="ticket-head">
          <strong>冻结记录票组 #{number:02d}</strong>
          <span>{int(plan["n"])}串1 · 倍率 {int(ticket["stake_multiplier"])} ·
            冻结记录成本 {_money_text(ticket["cost_yuan"])}元（仅研究审计）</span>
        </div>
        <ol>{"".join(leg_blocks)}</ol>
        <span class="audit-token">{marker}-END</span>
      </section>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="freeze-review-source-binding" content="{source_binding}">
  <meta name="freeze-review-view-binding" content="{view_binding}">
  <meta name="usage-boundary" content="{USAGE_BOUNDARY}">
  <title>{html.escape(str(manifest["issue"]))}期 N={plan["n"]} 研究冻结审计视图</title>
  <style>
    :root {{ color-scheme: light; font-family: "FreezeReviewCJK", "Noto Sans CJK SC",
      "Microsoft YaHei", sans-serif; color: #172033; background: #f3f5f8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 16px; line-height: 1.45; }}
    main {{ width: 100%; max-width: 760px; min-width: 0; margin: 0 auto; }}
    header, .ticket, footer {{ background: white; border: 1px solid #ccd3df;
      border-radius: 10px; padding: 14px; margin: 0 0 12px;
      min-width: 0; max-width: 100%; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; overflow-wrap: anywhere; }}
    .summary {{ display: grid; grid-template-columns: repeat(2,minmax(0,1fr));
      gap: 6px 16px; font-size: 14px; }}
    .summary > * {{ min-width: 0; overflow-wrap: anywhere; }}
    .warning {{ margin-top: 10px; padding: 8px; color: #7a2d00;
      background: #fff3e8; border-radius: 6px; font-weight: 700;
      overflow-wrap: anywhere; }}
    .watermark {{ margin: 0 0 12px; padding: 12px; border: 4px solid #a61b1b;
      color: #a61b1b; background: #fff0f0; text-align: center;
      font-size: 22px; font-weight: 900; letter-spacing: .04em; }}
    .ticket {{ break-inside: avoid; page-break-inside: avoid; }}
    .ticket-head {{ display: flex; justify-content: space-between; gap: 8px;
      border-bottom: 2px solid #243b67; padding-bottom: 7px; }}
    ol {{ list-style: none; padding: 0; margin: 8px 0 0; }}
    .leg {{ padding: 8px 0; border-bottom: 1px dashed #b8c0cc; }}
    .leg:last-child {{ border-bottom: 0; }}
    .leg-main {{ display: flex; gap: 10px; align-items: baseline; }}
    .match {{ min-width: 48px; font-size: 19px; font-weight: 800; color: #102e63; }}
    .choice {{ font-size: 18px; font-weight: 800; overflow-wrap: anywhere; }}
    .raw {{ font-size: 14px; font-weight: 600; color: #4b5567; }}
    .leg-meta, .teams {{ color: #465166; font-size: 13px; overflow-wrap: anywhere; }}
    .handicap {{ margin-left: 8px; font-weight: 800; color: #7a2d00; }}
    footer {{ font-size: 12px; overflow-wrap: anywhere; }}
    .verified {{ color: #116329; font-weight: 800; }}
    .audit-token {{ font-size: 1pt; color: #fff; line-height: 1pt; }}
    @media (max-width: 520px) {{
      body {{ padding: 8px; }}
      h1 .title-divider {{ display: none; }}
      h1 .segment-title {{ display: block; }}
      .summary {{ grid-template-columns: minmax(0,1fr); }}
      .ticket-head, .leg-main {{ align-items: flex-start; flex-direction: column; }}
      .match {{ min-width: 0; }}
      .handicap {{ display: block; margin-left: 0; }}
    }}
    @page {{ size: A4; margin: 12mm; }}
    @media print {{
      body {{ background: #fff; padding: 0; font-size: 10pt; }}
      main {{ max-width: none; }}
      header, .ticket, footer {{ border-radius: 0; }}
      .ticket {{ break-inside: avoid-page; page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
<main>
  <div class="watermark">研究冻结审计视图 / NOT FOR PURCHASE</div>
  <header>
    <h1><span>{html.escape(str(manifest["issue"]))}期研究冻结审计视图</span><span class="title-divider">｜</span><span class="segment-title">{html.escape(_segment_label(manifest))}</span></h1>
    <div class="summary">
      <div><strong>N={plan["n"]}</strong>（每票严格 {plan["n"]} 腿）</div>
      <div>冻结记录预算 {plan["budget"]}元（研究字段）</div>
      <div>冻结记录总成本 {_money_text(plan["actual_cost"])}元（研究字段）</div>
      <div>冻结记录票组数 {len(plan["tickets"])}</div>
      <div>决策时间 {_display_hkt(manifest["effective_decision_at"])}</div>
      <div>审计视图生成时间 {_display_hkt(model["generated_at_hkt"])}</div>
      <div>计划 {str(plan["source_plan_sha256"])[:12]}...</div>
      <div>冻结事件 {str(manifest["event_key"])[:12]}...</div>
      <div>来源完整性：{SOURCE_INTEGRITY_PASS}</div>
      <div>用途边界：{USAGE_BOUNDARY}</div>
    </div>
    <div class="warning">本页完整保留预注册定时冻结的原始票组，仅供 Strategist
      研究分析与人工证据复核。不得用于购买、到店录入、执行、实时筛选、删票、重算或重新分配预算。
      让球选项不是普通胜平负；比分冻结计划不可用。</div>
  </header>
{"".join(ticket_blocks)}
  <footer>
    <div>冻结记录票组数 {len(plan["tickets"])}｜逐票记录成本求和
      {_money_text(plan["actual_cost"])}元｜冻结记录总成本
      {_money_text(plan["actual_cost"])}元（均为研究审计字段）</div>
    <div class="verified">来源完整性：{SOURCE_INTEGRITY_PASS}
      （package、计划、metadata、kickoff、票序与冻结金额已绑定）</div>
    <div class="warning">研究冻结审计视图 / NOT FOR PURCHASE｜{USAGE_BOUNDARY}</div>
    <div>Freeze Review Binding SHA-256: {view_binding}</div>
    <div>Source Freeze Plan Binding SHA-256: {source_binding}</div>
    <div>Source plan SHA-256: {html.escape(str(plan["source_plan_sha256"]))}</div>
    <div>Renderer: {CAPABILITY_ID}/{RENDERER_VERSION}</div>
  </footer>
</main>
</body>
</html>
"""


def _ticket_leg_rows(model: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for plan in model["plans"]:
        if plan["status"] != "FROZEN_EXACT_N_BUDGET":
            continue
        for ticket in plan["tickets"]:
            for leg in ticket["legs"]:
                rows.append(
                    {
                        "requested_n": plan["n"],
                        "requested_budget_yuan": plan["budget"],
                        "review_generated_at_hkt": model["generated_at_hkt"],
                        "source_integrity_status": model["source_integrity_status"],
                        "usage_boundary": model["usage_boundary"],
                        "ticket_number": ticket["ticket_number"],
                        "leg_order": leg["leg_order"],
                        "match_idx": leg["match_idx"],
                        "selection_code": leg["raw_code"],
                        "selection_label_zh": leg["selection_label"],
                        "stake_multiplier": ticket["stake_multiplier"],
                        "ticket_base_cost_yuan": _money_text(ticket["base_cost_yuan"]),
                        "ticket_cost_yuan": _money_text(ticket["cost_yuan"]),
                        "kickoff_at_hkt": leg["kickoff_at_hkt"],
                        "league": leg["league"],
                        "home": leg["home"],
                        "away": leg["away"],
                        "handicap_line": leg["handicap_line"],
                        "plan_binding_sha256": plan["binding_sha256"],
                    }
                )
    return rows


def _csv_bytes(rows: list[dict[str, object]], fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


PLAN_MATRIX_FIELDS = [
    "requested_n",
    "requested_budget_yuan",
    "status",
    "source_integrity_status",
    "usage_boundary",
    "review_generated_at_hkt",
    "ticket_count",
    "actual_cost_yuan",
    "unused_budget_yuan",
    "max_ticket_cost_yuan",
    "max_ticket_cost_share",
    "max_match_ticket_appearances",
    "max_match_ticket_share",
    "source_plan_sha256",
    "plan_binding_sha256",
    "html_status",
    "pdf_status",
    "correct_score_status",
]
TICKET_LEG_FIELDS = [
    "requested_n",
    "requested_budget_yuan",
    "review_generated_at_hkt",
    "source_integrity_status",
    "usage_boundary",
    "ticket_number",
    "leg_order",
    "match_idx",
    "selection_code",
    "selection_label_zh",
    "stake_multiplier",
    "ticket_base_cost_yuan",
    "ticket_cost_yuan",
    "kickoff_at_hkt",
    "league",
    "home",
    "away",
    "handicap_line",
    "plan_binding_sha256",
]


def _font_coverage(font_file: Path, text: str) -> None:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise FreezeReviewError("fonttools unavailable") from exc
    try:
        font = TTFont(font_file, fontNumber=0)
        cmap = font.getBestCmap() or {}
    except Exception as exc:
        raise FreezeReviewError("cannot inspect PDF font") from exc
    required = {
        ord(character)
        for character in text
        if not character.isspace() and ord(character) >= 32
    }
    missing = sorted(required - set(cmap))
    if missing:
        preview = "".join(chr(value) for value in missing[:12])
        raise FreezeReviewError(f"PDF font lacks required glyphs: {preview!r}")


def _canonicalize_pdf_identifier(target: Path, identifier: str) -> None:
    """Replace pydyf's random revision ID without changing PDF byte offsets."""
    if not re.fullmatch(r"[0-9a-f]{64}", identifier):
        raise FreezeReviewError("PDF identifier must be a SHA-256 digest")
    payload = target.read_bytes()
    pattern = re.compile(
        rb"/ID \[\((" + identifier.encode("ascii") + rb")\) \(([0-9a-f]{32})\)\]"
    )
    revision = digest({"pdf_identifier": identifier, "revision": 1})[:32].encode(
        "ascii"
    )
    normalized, replacements = pattern.subn(
        rb"/ID [(\1) (" + revision + rb")]",
        payload,
    )
    if replacements != 1 or len(normalized) != len(payload):
        raise FreezeReviewError("PDF identifier normalization failed")
    target.write_bytes(normalized)


def _write_pdf(html_text: str, target: Path, font_file: Path, identifier: str) -> str:
    try:
        import weasyprint
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as exc:
        raise FreezeReviewError("PDF_UNAVAILABLE: WeasyPrint missing") from exc
    font_config = FontConfiguration()
    font_css = CSS(
        string=(
            '@font-face { font-family: "FreezeReviewCJK"; '
            f'src: url("{font_file.resolve().as_uri()}"); }}'
        ),
        font_config=font_config,
    )
    try:
        previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        try:
            HTML(string=html_text, base_url=str(target.parent)).write_pdf(
                target,
                stylesheets=[font_css],
                font_config=font_config,
                pdf_identifier=identifier,
                presentational_hints=True,
                full_fonts=False,
                hinting=False,
                optimize_images=False,
            )
        finally:
            if previous_epoch is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    except Exception as exc:
        raise FreezeReviewError("PDF_UNAVAILABLE: rendering failed") from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise FreezeReviewError("PDF_UNAVAILABLE: empty PDF")
    _canonicalize_pdf_identifier(target, identifier)
    return str(weasyprint.__version__)


def _asset_reference(
    *,
    asset: Path,
    explicit_reference: str | None,
    asset_kind: str,
    content_sha256: str,
) -> tuple[str, bool]:
    resolved = asset.expanduser().resolve()
    if explicit_reference is not None:
        candidate = Path(explicit_reference)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.as_posix() != explicit_reference
            or (REPOSITORY_ROOT / candidate).resolve() != resolved
        ):
            raise FreezeReviewError(f"invalid portable {asset_kind} reference")
        return explicit_reference, True
    try:
        relative = resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return f"external://{asset_kind}/sha256/{content_sha256}", False
    return relative, True


def _portable_font_contract(
    font_file: Path,
    font_reference: str,
    font_sha256: str,
) -> dict[str, str]:
    license_path = font_file.parent / "OFL.txt"
    provenance_path = font_file.with_suffix(".provenance.json")
    if not license_path.is_file() or not provenance_path.is_file():
        raise FreezeReviewError("portable font license/provenance missing")
    provenance = _load_json(provenance_path)
    if (
        provenance.get("font_sha256") != font_sha256
        or provenance.get("license_sha256") != file_hash(license_path)
        or provenance.get("font_reference") != font_reference
    ):
        raise FreezeReviewError("portable font provenance mismatch")
    return {
        "font_license_reference": license_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "font_license_sha256": file_hash(license_path),
        "font_provenance_reference": provenance_path.relative_to(
            REPOSITORY_ROOT
        ).as_posix(),
        "font_provenance_sha256": file_hash(provenance_path),
    }


def _output_identity(manifest_payload: dict[str, Any]) -> str:
    unsigned = dict(manifest_payload)
    unsigned.pop("sha256", None)
    unsigned.pop("output_id", None)
    return digest(
        {
            "content_id_schema": CONTENT_ID_SCHEMA,
            "manifest_payload_without_output_id": unsigned,
        }
    )


def _manifest_payload(
    *,
    model: dict[str, Any],
    generated_at: str,
    source_reference: str,
    font_reference: str,
    reproducibility_status: str,
    font_contract: dict[str, str],
    font_sha256: str,
    pdf_engine: str,
    plan_entries: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    source_manifest = model["manifest"]
    return {
        "schema_version": SCHEMA_VERSION,
        "capability_id": CAPABILITY_ID,
        "renderer_version": RENDERER_VERSION,
        "renderer_source_sha256": file_hash(Path(__file__).resolve()),
        "content_id_schema": CONTENT_ID_SCHEMA,
        "immutable": True,
        "append_only": True,
        "generated_at": generated_at,
        "source_integrity_status": SOURCE_INTEGRITY_PASS,
        "usage_boundary": USAGE_BOUNDARY,
        "issue": str(source_manifest["issue"]),
        "segment_identity": str(source_manifest["segment_identity"]),
        "segment_idx": int(source_manifest["segment_idx"]),
        "parent_segment_idx": source_manifest.get("parent_segment_idx"),
        "event_key": str(source_manifest["event_key"]),
        "effective_decision_at": str(source_manifest["effective_decision_at"]),
        "correct_score_status": model["correct_score_status"],
        "correct_score_review_generated": False,
        "source_package_reference": source_reference,
        "source_manifest_file_sha256": model["manifest_file_sha256"],
        "source_manifest_payload_sha256": model["manifest_payload_sha256"],
        "source_sha256s_sha256": model["sha256s_sha256"],
        "source_structured_input_sha256": model["structured_input_sha256"],
        "source_exact_verification": model["exact_verification"],
        "reproducibility_status": reproducibility_status,
        "pdf_engine": pdf_engine,
        "pdf_font_reference": font_reference,
        "pdf_font_sha256": font_sha256,
        **font_contract,
        "plans": plan_entries,
        "artifacts": artifacts,
        "reproduce": {
            "status": reproducibility_status,
            "argv": (
                [
                    "python3",
                    "scripts/render_exact_n_freeze_reviews.py",
                    "--source-package",
                    source_reference,
                    "--source-reference",
                    source_reference,
                    "--output-root",
                    "evidence/bj_freeze_review_001",
                    "--font-file",
                    font_reference,
                    "--font-reference",
                    font_reference,
                    "--generated-at",
                    generated_at,
                ]
                if reproducibility_status == PORTABLE_CLEAN_CHECKOUT
                else None
            ),
            "required_external_assets": (
                []
                if reproducibility_status == PORTABLE_CLEAN_CHECKOUT
                else [
                    {
                        "asset": "source_package",
                        "reference": source_reference,
                        "sha256s_sha256": model["sha256s_sha256"],
                    },
                    {
                        "asset": "pdf_font",
                        "reference": font_reference,
                        "sha256": font_sha256,
                    },
                ]
            ),
        },
    }


def render_bundle(
    *,
    source_package: Path,
    output_root: Path,
    font_file: Path,
    generated_at: datetime | None = None,
    source_reference: str | None = None,
    font_reference: str | None = None,
) -> dict[str, Any]:
    """Render one append-only bundle after complete source verification."""
    model = load_source_model(source_package)
    created = _normalize_generated_at(generated_at or datetime.now(HKT))
    created_text = created.isoformat(timespec="seconds")
    bind_review_context(model, created)
    font = font_file.expanduser().resolve()
    if not font.is_file():
        raise FreezeReviewError("PDF_UNAVAILABLE: font file missing")
    font_sha256 = file_hash(font)
    source_ref, portable_source = _asset_reference(
        asset=model["source"],
        explicit_reference=source_reference,
        asset_kind="source-package",
        content_sha256=model["sha256s_sha256"],
    )
    font_ref, portable_font = _asset_reference(
        asset=font,
        explicit_reference=font_reference,
        asset_kind="pdf-font",
        content_sha256=font_sha256,
    )
    portability = (
        PORTABLE_CLEAN_CHECKOUT
        if portable_source and portable_font
        else EXTERNAL_ASSETS_REQUIRED
    )
    font_contract = (
        _portable_font_contract(font, font_ref, font_sha256)
        if portability == PORTABLE_CLEAN_CHECKOUT
        else {}
    )
    html_documents = {
        (int(plan["n"]), int(plan["budget"])): _render_html(model, plan)
        for plan in model["plans"]
        if plan["status"] == "FROZEN_EXACT_N_BUDGET"
    }
    _font_coverage(font, "\n".join(html_documents.values()))
    try:
        import weasyprint
    except ImportError as exc:
        raise FreezeReviewError("PDF_UNAVAILABLE: WeasyPrint missing") from exc
    pdf_engine = f"WeasyPrint/{weasyprint.__version__}"
    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".publish.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        stage = Path(tempfile.mkdtemp(prefix=".freeze-review-stage.", dir=root))
        try:
            plan_entries: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            matrix_rows: list[dict[str, object]] = []
            for plan in model["plans"]:
                n = int(plan["n"])
                budget = int(plan["budget"])
                entry = {
                    "requested_n": n,
                    "requested_budget_yuan": budget,
                    "status": plan["status"],
                    "source_file": plan["source_file"],
                    "source_plan_sha256": plan["source_plan_sha256"],
                    "source_integrity_status": model["source_integrity_status"],
                    "usage_boundary": model["usage_boundary"],
                    "review_generated_at_hkt": model["generated_at_hkt"],
                    "ticket_count": len(plan["tickets"]),
                    "actual_cost_yuan": float(plan["actual_cost"]),
                    "unused_budget_yuan": float(plan["unused_budget"]),
                    "concentration": plan["concentration"],
                    "html_status": "NOT_RENDERED",
                    "pdf_status": "NOT_RENDERED",
                }
                if plan["status"] == "FROZEN_EXACT_N_BUDGET":
                    html_name = f"freeze_review_N{n}_B{budget}.html"
                    pdf_name = f"freeze_review_N{n}_B{budget}.pdf"
                    html_path = stage / html_name
                    pdf_path = stage / pdf_name
                    html_text = html_documents[(n, budget)]
                    html_path.write_text(html_text, encoding="utf-8", newline="\n")
                    engine_version = _write_pdf(
                        html_text,
                        pdf_path,
                        font,
                        str(plan["view_binding_sha256"]),
                    )
                    if engine_version != str(weasyprint.__version__):
                        raise FreezeReviewError("PDF engine version drift")
                    entry.update(
                        {
                            "plan_binding_sha256": plan["binding_sha256"],
                            "view_binding_sha256": plan["view_binding_sha256"],
                            "html_file": html_name,
                            "html_sha256": file_hash(html_path),
                            "html_status": "GENERATED",
                            "pdf_file": pdf_name,
                            "pdf_sha256": file_hash(pdf_path),
                            "pdf_status": "GENERATED",
                        }
                    )
                    artifacts.extend(
                        [
                            {
                                "file": html_name,
                                "sha256": entry["html_sha256"],
                                "artifact_type": "canonical_freeze_review",
                                "plan_binding_sha256": plan["binding_sha256"],
                                "view_binding_sha256": plan["view_binding_sha256"],
                            },
                            {
                                "file": pdf_name,
                                "sha256": entry["pdf_sha256"],
                                "artifact_type": "a4_freeze_review_derivative",
                                "source_html_sha256": entry["html_sha256"],
                                "plan_binding_sha256": plan["binding_sha256"],
                                "view_binding_sha256": plan["view_binding_sha256"],
                            },
                        ]
                    )
                plan_entries.append(entry)
                concentration = plan["concentration"]
                matrix_rows.append(
                    {
                        "requested_n": n,
                        "requested_budget_yuan": budget,
                        "status": plan["status"],
                        "source_integrity_status": model["source_integrity_status"],
                        "usage_boundary": model["usage_boundary"],
                        "review_generated_at_hkt": model["generated_at_hkt"],
                        "ticket_count": len(plan["tickets"]),
                        "actual_cost_yuan": _money_text(plan["actual_cost"]),
                        "unused_budget_yuan": _money_text(plan["unused_budget"]),
                        "max_ticket_cost_yuan": _money_text(
                            concentration["max_ticket_cost_yuan"]
                        ),
                        "max_ticket_cost_share": (
                            f"{concentration['max_ticket_cost_share']:.9f}"
                        ),
                        "max_match_ticket_appearances": concentration[
                            "max_match_ticket_appearances"
                        ],
                        "max_match_ticket_share": (
                            f"{concentration['max_match_ticket_share']:.9f}"
                        ),
                        "source_plan_sha256": plan["source_plan_sha256"],
                        "plan_binding_sha256": plan.get("binding_sha256", ""),
                        "html_status": entry["html_status"],
                        "pdf_status": entry["pdf_status"],
                        "correct_score_status": model["correct_score_status"],
                    }
                )
            matrix_path = stage / "plan_matrix.csv"
            legs_path = stage / "ticket_legs.csv"
            matrix_path.write_bytes(_csv_bytes(matrix_rows, PLAN_MATRIX_FIELDS))
            legs_path.write_bytes(
                _csv_bytes(_ticket_leg_rows(model), TICKET_LEG_FIELDS)
            )
            artifacts.extend(
                [
                    {
                        "file": matrix_path.name,
                        "sha256": file_hash(matrix_path),
                        "artifact_type": "plan_matrix",
                    },
                    {
                        "file": legs_path.name,
                        "sha256": file_hash(legs_path),
                        "artifact_type": "ticket_legs",
                    },
                ]
            )
            manifest_payload = _manifest_payload(
                model=model,
                generated_at=created_text,
                source_reference=source_ref,
                font_reference=font_ref,
                reproducibility_status=portability,
                font_contract=font_contract,
                font_sha256=font_sha256,
                pdf_engine=pdf_engine,
                plan_entries=plan_entries,
                artifacts=artifacts,
            )
            output_id = _output_identity(manifest_payload)
            manifest_payload["output_id"] = output_id
            manifest_payload["sha256"] = digest(manifest_payload)
            manifest_path = stage / "freeze_review_manifest.json"
            manifest_path.write_bytes(canonical(manifest_payload) + b"\n")
            sums_path = stage / "SHA256SUMS"
            sums_path.write_text(
                "".join(
                    f"{file_hash(path)}  {path.name}\n"
                    for path in sorted(stage.iterdir())
                    if path.is_file() and path.name != "SHA256SUMS"
                ),
                encoding="utf-8",
            )
            receipt = verify_bundle(
                stage,
                model["source"],
                font,
                _allow_staging_name=True,
            )
            destination = root / output_id
            if destination.exists():
                existing = verify_bundle(destination, model["source"], font)
                if (stage / "SHA256SUMS").read_bytes() != (
                    destination / "SHA256SUMS"
                ).read_bytes():
                    raise FreezeReviewError("content identity collision")
                shutil.rmtree(stage)
                return {
                    **existing,
                    "idempotent": True,
                    "path": str(destination),
                }
            os.rename(stage, destination)
            return {
                **receipt,
                "idempotent": False,
                "path": str(destination),
            }
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise


def _read_output_sums(root: Path) -> dict[str, str]:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise FreezeReviewError("derived SHA256SUMS missing")
    entries: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        try:
            claimed, name = line.split("  ", 1)
        except ValueError as exc:
            raise FreezeReviewError("derived SHA256SUMS malformed") from exc
        if (
            not re.fullmatch(r"[0-9a-f]{64}", claimed)
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or name in entries
        ):
            raise FreezeReviewError("derived SHA256SUMS entry invalid")
        entries[name] = claimed
    actual = {
        path.name
        for path in root.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(entries) != actual:
        raise FreezeReviewError("derived SHA256SUMS file set mismatch")
    for name, claimed in entries.items():
        if file_hash(root / name) != claimed:
            raise FreezeReviewError(f"derived hash mismatch: {name}")
    return entries


def _pdf_text_by_page(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise FreezeReviewError("pypdf unavailable") from exc
    try:
        reader = PdfReader(path)
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise FreezeReviewError("cannot verify rendered PDF") from exc


def _normalized_visible_html(html_text: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise FreezeReviewError("BeautifulSoup unavailable") from exc
    soup = BeautifulSoup(html_text, "html.parser")
    if soup.body is None:
        raise FreezeReviewError("HTML body missing")
    return re.sub(r"\s+", "", soup.body.get_text(" "))


def verify_bundle(
    bundle: Path,
    source_package: Path | None = None,
    font_file: Path | None = None,
    *,
    _allow_staging_name: bool = False,
) -> dict[str, Any]:
    """Verify hashes, source linkage, CSVs, HTML bindings and PDF page integrity."""
    root = bundle.expanduser().resolve()
    if not root.is_dir():
        raise FreezeReviewError("freeze-review bundle missing")
    sums = _read_output_sums(root)
    manifest = _load_json(root / "freeze_review_manifest.json")
    manifest_payload_sha = _payload_hash(manifest)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("capability_id") != CAPABILITY_ID
        or manifest.get("renderer_version") != RENDERER_VERSION
        or manifest.get("content_id_schema") != CONTENT_ID_SCHEMA
        or manifest.get("renderer_source_sha256") != file_hash(Path(__file__).resolve())
        or manifest.get("immutable") is not True
        or manifest.get("append_only") is not True
        or manifest.get("correct_score_review_generated") is not False
        or manifest.get("source_integrity_status") != SOURCE_INTEGRITY_PASS
        or manifest.get("usage_boundary") != USAGE_BOUNDARY
    ):
        raise FreezeReviewError("derived manifest contract mismatch")
    portability = str(manifest.get("reproducibility_status") or "")
    source_ref = str(manifest.get("source_package_reference") or "")
    font_ref = str(manifest.get("pdf_font_reference") or "")
    if portability == PORTABLE_CLEAN_CHECKOUT:
        for reference in (source_ref, font_ref):
            candidate = Path(reference)
            if (
                candidate.is_absolute()
                or ".." in candidate.parts
                or candidate.as_posix() != reference
            ):
                raise FreezeReviewError("portable asset reference invalid")
        canonical_source = (REPOSITORY_ROOT / source_ref).resolve()
        canonical_font = (REPOSITORY_ROOT / font_ref).resolve()
        if source_package is not None and source_package.expanduser().resolve() != (
            canonical_source
        ):
            raise FreezeReviewError("portable source override differs from reference")
        if font_file is not None and font_file.expanduser().resolve() != canonical_font:
            raise FreezeReviewError("portable font override differs from reference")
        source = canonical_source
        font = canonical_font
    elif portability == EXTERNAL_ASSETS_REQUIRED:
        if source_package is None or font_file is None:
            raise FreezeReviewError("external verification assets are required")
        source = source_package.expanduser().resolve()
        font = font_file.expanduser().resolve()
    else:
        raise FreezeReviewError("unknown reproducibility status")
    model = load_source_model(source)
    bind_review_context(
        model,
        datetime.fromisoformat(str(manifest.get("generated_at") or "")),
    )
    if not font.is_file() or file_hash(font) != str(
        manifest.get("pdf_font_sha256") or ""
    ):
        raise FreezeReviewError("PDF font hash mismatch")
    if portability == PORTABLE_CLEAN_CHECKOUT:
        font_contract = _portable_font_contract(
            font,
            font_ref,
            file_hash(font),
        )
        if any(manifest.get(key) != value for key, value in font_contract.items()):
            raise FreezeReviewError("portable font contract linkage mismatch")
        expected_reproduce = {
            "status": PORTABLE_CLEAN_CHECKOUT,
            "argv": [
                "python3",
                "scripts/render_exact_n_freeze_reviews.py",
                "--source-package",
                source_ref,
                "--source-reference",
                source_ref,
                "--output-root",
                "evidence/bj_freeze_review_001",
                "--font-file",
                font_ref,
                "--font-reference",
                font_ref,
                "--generated-at",
                str(manifest["generated_at"]),
            ],
            "required_external_assets": [],
        }
        if manifest.get("reproduce") != expected_reproduce:
            raise FreezeReviewError("portable reproduce command mismatch")
    else:
        expected_source_ref = (
            f"external://source-package/sha256/{model['sha256s_sha256']}"
        )
        expected_font_ref = f"external://pdf-font/sha256/{file_hash(font)}"
        if source_ref != expected_source_ref or font_ref != expected_font_ref:
            raise FreezeReviewError("external asset contract hash mismatch")
    if (
        manifest.get("source_manifest_file_sha256") != model["manifest_file_sha256"]
        or manifest.get("source_manifest_payload_sha256")
        != model["manifest_payload_sha256"]
        or manifest.get("source_sha256s_sha256") != model["sha256s_sha256"]
        or manifest.get("source_structured_input_sha256")
        != model["structured_input_sha256"]
        or manifest.get("source_exact_verification") != model["exact_verification"]
        or manifest.get("correct_score_status") != model["correct_score_status"]
        or manifest.get("event_key") != model["manifest"].get("event_key")
    ):
        raise FreezeReviewError("derived bundle source linkage mismatch")
    expected_output_id = _output_identity(manifest)
    valid_name = root.name == expected_output_id or (
        _allow_staging_name and root.name.startswith(".freeze-review-stage.")
    )
    if manifest.get("output_id") != expected_output_id or not valid_name:
        raise FreezeReviewError("derived output identity mismatch")
    plan_entries = manifest.get("plans")
    if not isinstance(plan_entries, list) or len(plan_entries) != 15:
        raise FreezeReviewError("derived plan matrix must contain 15 alternatives")
    entries_by_grid = {
        (int(item["requested_n"]), int(item["requested_budget_yuan"])): item
        for item in plan_entries
        if isinstance(item, dict)
    }
    if set(entries_by_grid) != {(n, budget) for n in N_VALUES for budget in BUDGETS}:
        raise FreezeReviewError("derived plan grid mismatch")
    artifact_entries = {
        str(item.get("file")): item
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    expected_matrix: list[dict[str, object]] = []
    for plan in model["plans"]:
        key = (int(plan["n"]), int(plan["budget"]))
        entry = entries_by_grid[key]
        if (
            entry.get("status") != plan["status"]
            or entry.get("source_plan_sha256") != plan["source_plan_sha256"]
            or entry.get("source_integrity_status") != model["source_integrity_status"]
            or entry.get("usage_boundary") != USAGE_BOUNDARY
            or entry.get("review_generated_at_hkt") != model["generated_at_hkt"]
            or int(entry.get("ticket_count", -1)) != len(plan["tickets"])
            or _money(entry.get("actual_cost_yuan")) != plan["actual_cost"]
            or _money(entry.get("unused_budget_yuan")) != plan["unused_budget"]
        ):
            raise FreezeReviewError("derived plan summary mismatch")
        if plan["status"] == "FROZEN_EXACT_N_BUDGET":
            if (
                entry.get("plan_binding_sha256") != plan["binding_sha256"]
                or entry.get("view_binding_sha256") != plan["view_binding_sha256"]
            ):
                raise FreezeReviewError("plan binding mismatch")
            html_name = f"freeze_review_N{key[0]}_B{key[1]}.html"
            pdf_name = f"freeze_review_N{key[0]}_B{key[1]}.pdf"
            if (
                entry.get("html_file") != html_name
                or entry.get("pdf_file") != pdf_name
                or entry.get("html_status") != "GENERATED"
                or entry.get("pdf_status") != "GENERATED"
                or entry.get("html_sha256") != file_hash(root / html_name)
                or entry.get("pdf_sha256") != file_hash(root / pdf_name)
            ):
                raise FreezeReviewError("plan output hash/status mismatch")
            html_text = (root / html_name).read_text(encoding="utf-8")
            source_binding = str(plan["binding_sha256"])
            view_binding = str(plan["view_binding_sha256"])
            if (
                html_text != _render_html(model, plan)
                or (
                    f'name="freeze-review-source-binding" content="{source_binding}"'
                    not in html_text
                )
                or (
                    f'name="freeze-review-view-binding" content="{view_binding}"'
                    not in html_text
                )
                or f"Freeze Review Binding SHA-256: {view_binding}" not in html_text
                or "研究冻结审计视图 / NOT FOR PURCHASE" not in html_text
                or USAGE_BOUNDARY not in html_text
                or "下注单" in html_text
                or "现场勾选" in html_text
                or "可执行金额" in html_text
                or "校验状态：PASS" in html_text
                or "仅按已验证 exact-N 冻结录入" in html_text
                or "overflow-x" in html_text
                or "break-inside: avoid" not in html_text
                or "page-break-inside: avoid" not in html_text
            ):
                raise FreezeReviewError("HTML binding/layout contract mismatch")
            pages = _pdf_text_by_page(root / pdf_name)
            joined = "\n".join(pages)
            if view_binding not in joined or re.sub(
                r"\s+", "", joined
            ) != _normalized_visible_html(html_text):
                raise FreezeReviewError("PDF/HTML semantic content mismatch")
            _font_coverage(font, html_text)
            for ticket in plan["tickets"]:
                marker = f"N{key[0]}-B{key[1]}-T{int(ticket['ticket_number']):03d}"
                begin_pages = [
                    index
                    for index, text in enumerate(pages)
                    if f"{marker}-BEGIN" in text
                ]
                end_pages = [
                    index for index, text in enumerate(pages) if f"{marker}-END" in text
                ]
                if (
                    len(begin_pages) != 1
                    or len(end_pages) != 1
                    or begin_pages[0] != end_pages[0]
                ):
                    raise FreezeReviewError(
                        "PDF ticket is missing or split across pages"
                    )
            for name in (html_name, pdf_name):
                artifact = artifact_entries.get(name)
                if (
                    not artifact
                    or artifact.get("sha256") != sums.get(name)
                    or artifact.get("plan_binding_sha256") != plan["binding_sha256"]
                    or artifact.get("view_binding_sha256")
                    != plan["view_binding_sha256"]
                ):
                    raise FreezeReviewError("derived artifact manifest mismatch")
        elif (
            entry.get("html_status") != "NOT_RENDERED"
            or entry.get("pdf_status") != "NOT_RENDERED"
            or entry.get("html_file") is not None
            or entry.get("pdf_file") is not None
        ):
            raise FreezeReviewError("unavailable plan was rendered")
        concentration = plan["concentration"]
        expected_matrix.append(
            {
                "requested_n": key[0],
                "requested_budget_yuan": key[1],
                "status": plan["status"],
                "source_integrity_status": model["source_integrity_status"],
                "usage_boundary": model["usage_boundary"],
                "review_generated_at_hkt": model["generated_at_hkt"],
                "ticket_count": len(plan["tickets"]),
                "actual_cost_yuan": _money_text(plan["actual_cost"]),
                "unused_budget_yuan": _money_text(plan["unused_budget"]),
                "max_ticket_cost_yuan": _money_text(
                    concentration["max_ticket_cost_yuan"]
                ),
                "max_ticket_cost_share": (
                    f"{concentration['max_ticket_cost_share']:.9f}"
                ),
                "max_match_ticket_appearances": concentration[
                    "max_match_ticket_appearances"
                ],
                "max_match_ticket_share": (
                    f"{concentration['max_match_ticket_share']:.9f}"
                ),
                "source_plan_sha256": plan["source_plan_sha256"],
                "plan_binding_sha256": plan.get("binding_sha256", ""),
                "html_status": entry["html_status"],
                "pdf_status": entry["pdf_status"],
                "correct_score_status": model["correct_score_status"],
            }
        )
    if (root / "plan_matrix.csv").read_bytes() != _csv_bytes(
        expected_matrix, PLAN_MATRIX_FIELDS
    ):
        raise FreezeReviewError("plan_matrix.csv semantic mismatch")
    if (root / "ticket_legs.csv").read_bytes() != _csv_bytes(
        _ticket_leg_rows(model), TICKET_LEG_FIELDS
    ):
        raise FreezeReviewError("ticket_legs.csv semantic mismatch")
    for name in ("plan_matrix.csv", "ticket_legs.csv"):
        artifact = artifact_entries.get(name)
        if not artifact or artifact.get("sha256") != sums.get(name):
            raise FreezeReviewError("CSV artifact manifest mismatch")
    expected_files = {
        "freeze_review_manifest.json",
        "plan_matrix.csv",
        "ticket_legs.csv",
        *(
            f"freeze_review_N{int(plan['n'])}_B{int(plan['budget'])}.{suffix}"
            for plan in model["plans"]
            if plan["status"] == "FROZEN_EXACT_N_BUDGET"
            for suffix in ("html", "pdf")
        ),
    }
    if set(sums) != expected_files:
        raise FreezeReviewError("derived bundle complete file set mismatch")
    return {
        "status": "PASS",
        "capability_id": CAPABILITY_ID,
        "output_id": expected_output_id,
        "source_integrity_status": SOURCE_INTEGRITY_PASS,
        "usage_boundary": USAGE_BOUNDARY,
        "generated_at": model["generated_at_hkt"],
        "reproducibility_status": portability,
        "plans": 15,
        "html_files": sum(
            plan["status"] == "FROZEN_EXACT_N_BUDGET" for plan in model["plans"]
        ),
        "pdf_files": sum(
            plan["status"] == "FROZEN_EXACT_N_BUDGET" for plan in model["plans"]
        ),
        "ticket_leg_rows": len(_ticket_leg_rows(model)),
        "source_event_key": model["manifest"]["event_key"],
        "source_manifest_sha256": model["manifest_file_sha256"],
        "freeze_review_manifest_payload_sha256": manifest_payload_sha,
        "freeze_review_manifest_file_sha256": file_hash(
            root / "freeze_review_manifest.json"
        ),
        "package_sha256s_sha256": file_hash(root / "SHA256SUMS"),
    }
