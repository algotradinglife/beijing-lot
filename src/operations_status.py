"""Canonical Operations Status v2 aggregation.

This module owns status aggregation and alert derivation for the existing
Operations API.  Adapters in ``src.decision_api.app`` collect runtime, database,
freeze, artifact, adhoc, and settlement facts.  The frontend must display the
resulting alerts and must not independently reimplement these rules.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "operations_status_v2"
STABLE_STATUSES = frozenset(
    {
        "ok",
        "running",
        "due",
        "partial",
        "stale",
        "failed",
        "missing",
        "blocked",
        "not_applicable",
    }
)
ALERT_SEVERITIES = frozenset({"blocker", "warning"})
ALERT_STATES = frozenset({"open", "recovering"})

_STATUS_RANK = {
    "failed": 90,
    "blocked": 85,
    "missing": 80,
    "stale": 60,
    "partial": 50,
    "due": 30,
    "running": 20,
    "ok": 10,
    "not_applicable": 0,
}


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _timestamp_sort_key(value: str) -> tuple[int, datetime | str]:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return 0, parsed.astimezone(timezone.utc)
    except ValueError:
        return 1, text


def stable_alert_id(code: str, domain: str, affected: Mapping[str, Any]) -> str:
    identity = {
        "code": str(code),
        "domain": str(domain),
        "segments": sorted(str(value) for value in affected.get("segments", [])),
        "matches": sorted(str(value) for value in affected.get("matches", [])),
        "markets": sorted(str(value) for value in affected.get("markets", [])),
        "sources": sorted(str(value) for value in affected.get("sources", [])),
    }
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return f"ops-{digest[:20]}"


def aggregate_status(statuses: Iterable[str], *, empty: str = "not_applicable") -> str:
    values = [status if status in STABLE_STATUSES else "failed" for status in statuses]
    if not values:
        return empty
    return max(values, key=lambda status: _STATUS_RANK[status])


def _time(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if str(item)]


def _alert(
    *,
    code: str,
    domain: str,
    severity: str,
    title: str,
    detail: str,
    impact: str,
    next_action: str,
    observed_at: str,
    affected: Mapping[str, Any] | None = None,
    first_seen_at: str = "",
    last_seen_at: str = "",
    last_success_at: str = "",
    next_due_at: str = "",
    auto_recovery_expected: bool,
    retry_count: int | None = None,
    links: list[dict[str, str]] | None = None,
    blocks: Mapping[str, bool] | None = None,
    recovering: bool = False,
) -> dict[str, Any]:
    scope = dict(affected or {})
    normalized_scope = {
        "segments": _list(scope.get("segments")),
        "matches": _list(scope.get("matches")),
        "markets": _list(scope.get("markets")),
        "sources": _list(scope.get("sources")),
    }
    affected_count = int(
        scope.get("count")
        or max((len(values) for values in normalized_scope.values()), default=0)
        or 1
    )
    normalized_blocks = {
        "data_display": False,
        "research_freeze": False,
        "adhoc_generation": False,
        "settlement": False,
        **{str(key): bool(value) for key, value in (blocks or {}).items()},
    }
    severity_value = severity if severity in ALERT_SEVERITIES else "blocker"
    return {
        "alert_id": stable_alert_id(code, domain, normalized_scope),
        "code": code,
        "domain": domain,
        "severity": severity_value,
        "status": "recovering" if recovering else "open",
        "title": title,
        "detail": detail,
        "impact": impact,
        "next_action": next_action,
        "observed_at": observed_at,
        "first_seen_at": _time(first_seen_at, observed_at),
        "last_seen_at": _time(last_seen_at, observed_at),
        "last_success_at": str(last_success_at or ""),
        "next_due_at": str(next_due_at or ""),
        "affected_count": affected_count,
        "affected": normalized_scope,
        "auto_recovery_expected": bool(auto_recovery_expected),
        "retry_count": retry_count,
        "links": links or [],
        "blocks": normalized_blocks,
    }


def _runtime_alerts(runtime: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for component in runtime.get("components", []):
        if not isinstance(component, Mapping):
            continue
        status = str(component.get("status") or "missing")
        if status not in {"failed", "blocked", "missing", "stale", "partial"}:
            continue
        label = str(component.get("label") or component.get("component_id") or "运行组件")
        component_id = str(component.get("component_id") or "unknown")
        severity = "blocker" if status in {"failed", "blocked", "missing"} else "warning"
        code = "workflow_failed" if component_id == "refresh_workflow" and status == "failed" else f"runtime_{component_id}_{status}"
        alerts.append(
            _alert(
                code=code,
                domain="runtime",
                severity=severity,
                title=f"{label}状态异常",
                detail=str(component.get("detail") or f"当前状态为 {status}。"),
                impact=str(component.get("impact") or "系统状态检查可能不完整。"),
                next_action=str(component.get("next_action") or "检查运行探针并恢复对应服务。"),
                observed_at=observed_at,
                first_seen_at=str(component.get("first_seen_at") or ""),
                last_seen_at=str(component.get("checked_at") or ""),
                last_success_at=str(component.get("last_success_at") or ""),
                next_due_at=str(component.get("next_due_at") or ""),
                auto_recovery_expected=bool(component.get("auto_recovery_expected")),
                retry_count=component.get("retry_count"),
                affected={"sources": [component_id], "count": 1},
                links=list(component.get("links") or []),
                blocks={"data_display": severity == "blocker"},
                recovering=status == "partial" and bool(component.get("auto_recovery_expected")),
            )
        )
    return alerts


def _collection_alerts(collection: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if collection.get("plan_status") != "ok":
        alerts.append(
            _alert(
                code="collection_plan_invalid",
                domain="collection",
                severity="blocker",
                title="采集计划不可用",
                detail=str(collection.get("plan_error") or "采集计划缺失或格式无效。"),
                impact="无法按采集器 SLA 判断数据是否及时和完整。",
                next_action="修复 config/data_collection_plan.json 并重新检查运行状态。",
                observed_at=observed_at,
                auto_recovery_expected=False,
                affected={"sources": ["data_collection_plan"], "count": 1},
                links=[{"kind": "config", "label": "采集计划", "ref": "config:data_collection_plan_v1"}],
                blocks={"data_display": True, "research_freeze": True, "adhoc_generation": True},
            )
        )
    for collector in collection.get("collectors", []):
        if not isinstance(collector, Mapping) or not collector.get("enabled", True):
            continue
        status = str(collector.get("status") or "missing")
        if status not in {"failed", "blocked", "missing", "stale", "partial"}:
            continue
        critical = collector.get("importance") == "critical"
        severity = "blocker" if critical and status in {"failed", "blocked", "missing"} else "warning"
        collector_id = str(collector.get("collector_id") or "unknown")
        label = str(collector.get("label") or collector_id)
        missing_matches = _list(collector.get("missing_match_ids"))
        markets = _list(collector.get("markets"))
        alerts.append(
            _alert(
                code=f"collector_{collector_id}_{status}",
                domain="collection",
                severity=severity,
                title=f"{label}：{status}",
                detail=str(
                    collector.get("error")
                    or collector.get("status_detail")
                    or "最近采集状态未达到计划要求。"
                ),
                impact=str(
                    collector.get("impact")
                    or (
                        "关键数据展示及其下游能力可能不完整。"
                        if critical
                        else "相关市场或研究输入可能不完整。"
                    )
                ),
                next_action=str(collector.get("maintenance_action") or "检查采集进程、日志和覆盖率。"),
                observed_at=observed_at,
                first_seen_at=str(
                    collector.get("first_unhealthy_at")
                    or collector.get("last_error_at")
                    or collector.get("last_attempt_at")
                    or ""
                ),
                last_seen_at=str(collector.get("last_attempt_at") or ""),
                last_success_at=str(collector.get("last_success_at") or ""),
                next_due_at=str(collector.get("next_due_at") or ""),
                auto_recovery_expected=bool(collector.get("auto_recovery_expected")),
                retry_count=collector.get("retry_count"),
                affected={
                    "sources": [collector_id],
                    "matches": missing_matches,
                    "markets": markets,
                    "count": int(collector.get("missing_count") or 1),
                },
                links=list(collector.get("links") or []),
                blocks={
                    "data_display": severity == "blocker",
                    "research_freeze": critical,
                    "adhoc_generation": critical,
                },
                recovering=bool(collector.get("auto_recovery_expected")) and status == "partial",
            )
        )
    return alerts


def _artifact_alerts(artifacts: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    active = artifacts.get("active_decision")
    if isinstance(active, Mapping):
        status = str(active.get("status") or "missing")
        if status in {"failed", "blocked", "missing", "stale", "partial"}:
            missing_matches = _list(active.get("missing_match_ids"))
            alerts.append(
                _alert(
                    code=f"active_decision_{status}",
                    domain="artifacts",
                    severity="blocker" if status in {"failed", "blocked", "missing"} else "warning",
                    title="正式决策产物不完整",
                    detail=str(active.get("detail") or "active 决策未覆盖当前期全部比赛。"),
                    impact="受影响比赛无法展示完整的正式决策产物。",
                    next_action=str(active.get("next_action") or "检查正式决策输入并生成或修复缺失产物。"),
                    observed_at=observed_at,
                    last_seen_at=str(active.get("generated_at") or ""),
                    last_success_at=str(active.get("last_success_at") or ""),
                    auto_recovery_expected=False,
                    affected={"matches": missing_matches, "count": int(active.get("missing_count") or 1)},
                    links=list(active.get("links") or []),
                    blocks={"data_display": True, "research_freeze": True, "adhoc_generation": True},
                )
            )
    draft_count = int(artifacts.get("draft_count") or 0)
    if draft_count:
        alerts.append(
            _alert(
                code="draft_replacement_pending",
                domain="artifacts",
                severity="warning",
                title=f"{draft_count} 条决策草稿待确认",
                detail="草稿不会自动覆盖 active 决策。",
                impact="active 展示保持不变；草稿需人工确认后才会生效。",
                next_action="逐条检查草稿差异并确认或保留现有 active 决策。",
                observed_at=observed_at,
                auto_recovery_expected=False,
                affected={
                    "matches": _list(artifacts.get("draft_match_ids")),
                    "count": draft_count,
                },
                links=[{"kind": "page", "label": "决策草稿", "ref": "operations:#artifacts"}],
            )
        )
    return alerts


def _freeze_alerts(scheduled_freeze: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for segment in scheduled_freeze.get("segments", []):
        if not isinstance(segment, Mapping):
            continue
        timeline_status = str(segment.get("timeline_status") or "unavailable")
        if timeline_status not in {"missed", "unavailable", "verification_failed"}:
            continue
        identity = str(segment.get("segment_identity") or segment.get("segment_idx") or "unknown")
        severity = "blocker" if timeline_status in {"missed", "verification_failed"} else "warning"
        alerts.append(
            _alert(
                code=f"scheduled_freeze_{timeline_status}",
                domain="scheduled_freeze",
                severity=severity,
                title=f"{identity} 定时冻结{timeline_status}",
                detail=str(segment.get("detail") or "该 segment 未形成可验证的定时冻结状态。"),
                impact=str(segment.get("impact") or "该 segment 的定时研究冻结或 exact-N 产物不可用。"),
                next_action=str(
                    segment.get("next_action")
                    or (
                        "检查冻结包与校验摘要；校验失败时需要人工处理。"
                        if timeline_status == "verification_failed"
                        else "检查冻结调度与不可变 ledger；错过窗口不得事后伪造冻结。"
                    )
                ),
                observed_at=observed_at,
                first_seen_at=str(segment.get("freeze_at") or ""),
                last_seen_at=str(segment.get("observed_at") or ""),
                last_success_at=str(segment.get("published_at") or ""),
                next_due_at=str(segment.get("next_due_at") or ""),
                auto_recovery_expected=bool(segment.get("auto_recovery_expected")),
                retry_count=segment.get("retry_count"),
                affected={"segments": [identity], "count": 1},
                links=list(segment.get("links") or []),
                blocks={"research_freeze": True},
            )
        )
    return alerts


def _adhoc_alerts(adhoc: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    isolation_status = str(adhoc.get("isolation_status") or "")
    if isolation_status == "failed":
        alerts.append(
            _alert(
                code="adhoc_isolation_invalid",
                domain="adhoc_service",
                severity="blocker",
                title="即时生成研究隔离标记无效",
                detail=str(adhoc.get("detail") or "最近请求违反 adhoc 与定时研究证据隔离契约。"),
                impact="该请求不能被视为独立 adhoc 产物，且不得进入定时研究证据。",
                next_action=str(adhoc.get("next_action") or "检查请求 ledger 并隔离受影响产物。"),
                observed_at=observed_at,
                last_seen_at=str(adhoc.get("last_request_at") or ""),
                last_success_at=str(adhoc.get("last_success_at") or ""),
                auto_recovery_expected=False,
                affected={"sources": ["adhoc_request_ledger"], "count": 1},
                links=list(adhoc.get("links") or []),
                blocks={"research_freeze": True, "adhoc_generation": True},
            )
        )
    service_status = str(
        adhoc.get("service_status")
        or (adhoc.get("status") if not isolation_status else "ok")
        or "missing"
    )
    if service_status in {"failed", "blocked", "missing", "stale", "partial"}:
        alerts.append(
            _alert(
                code=f"adhoc_service_{service_status}",
                domain="adhoc_service",
                severity="blocker" if service_status in {"failed", "blocked"} else "warning",
                title="即时生成服务不可用",
                detail=str(adhoc.get("service_detail") or adhoc.get("detail") or "即时生成能力最近状态异常。"),
                impact="用户即时生成请求可能无法完成；不影响定时研究冻结证据。",
                next_action=str(adhoc.get("service_next_action") or "检查即时生成 API 和服务探针。"),
                observed_at=observed_at,
                last_seen_at=str(adhoc.get("service_checked_at") or ""),
                last_success_at=str(adhoc.get("last_success_at") or ""),
                auto_recovery_expected=False,
                affected={"sources": ["adhoc_service"], "count": 1},
                links=list(adhoc.get("links") or []),
                blocks={"adhoc_generation": True},
            )
        )
    return alerts


def _settlement_alerts(settlement: Mapping[str, Any], observed_at: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    missing_sp = _list(settlement.get("missing_winning_sp_match_ids"))
    if missing_sp:
        alerts.append(
            _alert(
                code="winning_sp_missing",
                domain="settlement_review",
                severity="warning",
                title=f"{len(missing_sp)} 场已完赛但 winning SP 缺失",
                detail="赛果已出现，但方案模拟结算所需的 winning SP 尚未齐全。",
                impact="受影响场次暂不能完成方案模拟结算。",
                next_action="等待下一轮结算采集；若持续缺失，检查 500 场次/结算 SP 采集。",
                observed_at=observed_at,
                last_success_at=str(settlement.get("last_settlement_success_at") or ""),
                next_due_at=str(settlement.get("next_due_at") or ""),
                auto_recovery_expected=True,
                affected={"matches": missing_sp, "count": len(missing_sp)},
                links=[{"kind": "page", "label": "缺失结算场次", "ref": "operations:#settlement"}],
                blocks={"settlement": True},
                recovering=True,
            )
        )
    unreviewed = _list(settlement.get("unreviewed_match_ids"))
    if unreviewed:
        alerts.append(
            _alert(
                code="postmatch_review_missing",
                domain="settlement_review",
                severity="warning",
                title=f"{len(unreviewed)} 场已结算未复盘",
                detail="这些场次尚无当前 review version 的复盘记录。",
                impact="复盘覆盖率不完整；不代表用户真实收益或线下购买结果。",
                next_action="先运行复盘 dry-run，确认结果后再按原权限执行写入。",
                observed_at=observed_at,
                last_success_at=str(settlement.get("latest_review_at") or ""),
                auto_recovery_expected=False,
                affected={"matches": unreviewed, "count": len(unreviewed)},
                links=[{"kind": "page", "label": "未复盘场次", "ref": "operations:#settlement"}],
                blocks={"settlement": True},
            )
        )
    task = settlement.get("task")
    if isinstance(task, Mapping) and str(task.get("status")) == "failed":
        alerts.append(
            _alert(
                code="postmatch_review_failed",
                domain="settlement_review",
                severity="blocker",
                title="最近复盘任务失败",
                detail=str(task.get("error") or "复盘任务返回 failed。"),
                impact="本次复盘未完成；已有复盘记录不受影响。",
                next_action="检查任务诊断 ID，修复后先重新运行 dry-run。",
                observed_at=observed_at,
                first_seen_at=str(task.get("started_at") or ""),
                last_seen_at=str(task.get("finished_at") or ""),
                last_success_at=str(settlement.get("latest_review_at") or ""),
                auto_recovery_expected=False,
                affected={"sources": ["postmatch_review"], "count": 1},
                links=list(task.get("links") or []),
                blocks={"settlement": True},
            )
        )
    return alerts


def _sort_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        alerts,
        key=lambda alert: (
            0 if alert["severity"] == "blocker" else 1,
            str(alert.get("last_seen_at") or alert.get("observed_at") or ""),
            str(alert["alert_id"]),
        ),
    )


def _apply_alert_lifecycle(
    alerts: list[dict[str, Any]],
    *,
    observed_at: str,
    prior_alert_lifecycle: Mapping[str, Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Reconcile active alerts with their persisted observation lifecycle."""

    prior = prior_alert_lifecycle or {}
    for alert in alerts:
        previous = prior.get(str(alert["alert_id"]))
        if isinstance(previous, Mapping):
            alert["first_seen_at"] = _time(
                previous.get("first_seen_at"),
                _time(alert.get("first_seen_at"), observed_at),
            )
        else:
            alert["first_seen_at"] = _time(alert.get("first_seen_at"), observed_at)
        # last_seen_at describes the latest canonical observation, not the
        # source event timestamp carried by last_success_at/next_due_at.
        alert["last_seen_at"] = observed_at
    return alerts


def build_operations_v2(
    *,
    issue: str,
    generated_at: str,
    runtime: Mapping[str, Any],
    collection: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    scheduled_freeze: Mapping[str, Any],
    adhoc_service: Mapping[str, Any],
    settlement_review: Mapping[str, Any],
    prior_alert_lifecycle: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the canonical v2 domains, summary, and sole alert list."""

    domains = {
        "runtime": dict(runtime),
        "collection": dict(collection),
        "artifacts": dict(artifacts),
        "scheduled_freeze": dict(scheduled_freeze),
        "adhoc_service": dict(adhoc_service),
        "settlement_review": dict(settlement_review),
    }
    alerts = _sort_alerts(
        _apply_alert_lifecycle(
            [
                *_runtime_alerts(runtime, generated_at),
                *_collection_alerts(collection, generated_at),
                *_artifact_alerts(artifacts, generated_at),
                *_freeze_alerts(scheduled_freeze, generated_at),
                *_adhoc_alerts(adhoc_service, generated_at),
                *_settlement_alerts(settlement_review, generated_at),
            ],
            observed_at=generated_at,
            prior_alert_lifecycle=prior_alert_lifecycle,
        )
    )
    blockers = sum(alert["severity"] == "blocker" for alert in alerts)
    warnings = sum(alert["severity"] == "warning" for alert in alerts)
    next_actions = [
        (str(alert.get("next_due_at") or ""), str(alert.get("title") or ""))
        for alert in alerts
        if alert.get("next_due_at")
    ]
    scheduled_freeze_due_at = str(scheduled_freeze.get("next_due_at") or "")
    if scheduled_freeze_due_at:
        next_actions.append((scheduled_freeze_due_at, "下一个 segment 定时冻结"))
    next_action_at, next_action_title = min(
        next_actions,
        key=lambda item: _timestamp_sort_key(item[0]),
        default=("", ""),
    )
    overall_status = "failed" if blockers else "partial" if warnings else "ok"
    return {
        "schema_version": SCHEMA_VERSION,
        "issue": str(issue),
        "generated_at": generated_at,
        "summary": {
            "status": overall_status,
            "blocker_count": blockers,
            "warning_count": warnings,
            "next_action_at": next_action_at,
            "next_action_title": next_action_title,
            "message": (
                "发现系统阻断项；这只描述系统与数据能力状态。"
                if blockers
                else "发现需关注事项；这不代表策略、执行或收益准备度。"
                if warnings
                else "当前未发现系统阻断；这不代表策略、执行或收益已经就绪。"
            ),
        },
        "domains": domains,
        "alerts": alerts,
    }


def legacy_warnings(alerts: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Project canonical alerts into the pre-v2 warning shape."""

    return [
        {
            "code": str(alert.get("code") or ""),
            "severity": "bad" if alert.get("severity") == "blocker" else "warn",
            "label": str(alert.get("title") or ""),
            "detail": str(alert.get("detail") or ""),
        }
        for alert in alerts
    ]
