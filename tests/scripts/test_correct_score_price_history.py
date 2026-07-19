from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import correct_score_price_history as history  # noqa: E402
from src.multimarket_p0 import HKT  # noqa: E402
from src.okooo_prekick_sp import parse_history_page  # noqa: E402
from scripts import live_correct_score_price_refresh_loop as refresh  # noqa: E402
from scripts import manage_correct_score_price_history as manager  # noqa: E402


SCORES = (
    "1:0", "2:0", "2:1", "3:0", "3:1", "3:2",
    "0:0", "1:1", "2:2", "3:3",
    "0:1", "0:2", "1:2", "0:3", "1:3", "2:3",
    "主胜其他", "平其他", "负其他",
)


def history_html(*, source_time: str = "2026-07-18 07:55", late: bool = False) -> bytes:
    headers = "".join(f"<th>{score}</th>" for score in SCORES)
    values = "".join(f"<td>{5 + index / 10:.1f}</td>" for index, _ in enumerate(SCORES))
    relative = "赛前00时05分" if late else "赛前02时05分"
    return (
        "<html><title>赔率变化列表</title><table><thead><tr>"
        f"<th>时间</th><th>更新</th>{headers}</tr></thead><tbody><tr>"
        f"<td>{source_time}</td><td>{relative}</td>{values}</tr>"
        "</tbody></table></html>"
    ).encode()


def nowscore_odds_html(*, blank_first_price: bool = False) -> bytes:
    labels = (
        "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "4:3",
        "0:0", "1:1", "2:2", "3:3", "4:4",
    )
    home = [str(6 + index) for index in range(15)]
    if blank_first_price:
        home[0] = ""
    return (
        '<html><table><tr><td><b>波胆</b></td>'
        + "".join(f"<td>{value}</td>" for value in labels)
        + "</tr><tr><td>主</td>"
        + "".join(f"<td>{value}</td>" for value in home)
        + "</tr><tr><td>客</td>"
        + "".join(f"<td>{8 + index}</td>" for index in range(10))
        + "</tr></table></html>"
    ).encode()


def build_snapshot(*, source_time: str = "2026-07-18 07:55", late: bool = False):
    row = parse_history_page(history_html(source_time=source_time, late=late))[0]
    return history.snapshot_from_history_row(
        row,
        issue="26076",
        match_idx=25,
        provider_match_id="1339000",
        nowscore_provider_match_id="3011000",
        kickoff_hkt=datetime(2026, 7, 18, 10, 0, tzinfo=HKT),
        fetched_at_utc="2026-07-17T23:56:00+00:00",
        source_url="https://example.test/cs/change/14/",
        raw_file="raw/025.html",
        raw_payload_sha256="a" * 64,
        capture_batch_id="batch-1",
    )


def test_normalizes_full_correct_score_vector_and_groups() -> None:
    snapshot, prices = build_snapshot()
    assert snapshot["complete"] == 1
    assert snapshot["snapshot_ts_hkt"] == "2026-07-18T07:55:00+08:00"
    assert snapshot["timestamp_grade"] == "source_explicit_hkt"
    assert snapshot["outcome_count"] == len(SCORES)
    assert {row["outcome_group"] for row in prices} == {"home", "draw", "away"}
    assert {row["outcome_code"] for row in prices} >= {"1-0", "0-0", "0-1", "home_other"}


def test_source_countdown_is_only_a_timestamp_fallback() -> None:
    payload = history_html().replace(b"2026-07-18 07:55", "无绝对时间".encode())
    row = parse_history_page(payload)[0]
    snapshot, _ = history.snapshot_from_history_row(
        row,
        issue="26076",
        match_idx=25,
        provider_match_id="1339000",
        nowscore_provider_match_id="3011000",
        kickoff_hkt=datetime(2026, 7, 18, 10, 0, tzinfo=HKT),
        fetched_at_utc="2026-07-17T23:56:00+00:00",
        source_url="https://example.test",
        raw_file="raw/025.html",
        raw_payload_sha256="a" * 64,
        capture_batch_id="batch-1",
    )
    assert snapshot["snapshot_ts_hkt"] == "2026-07-18T07:55:00+08:00"
    assert snapshot["timestamp_grade"] == "source_relative_to_kickoff_derived"


def test_asof_selection_rejects_post_freeze_and_incomplete_rows() -> None:
    eligible, _ = build_snapshot(source_time="2026-07-18 07:55")
    future, _ = build_snapshot(source_time="2026-07-18 08:20")
    incomplete = {**eligible, "snapshot_id": "incomplete", "complete": 0, "snapshot_ts_hkt": "2026-07-18T08:00:00+08:00"}
    selected, reason = history.select_latest_complete(
        [eligible, future, incomplete], datetime(2026, 7, 18, 8, 10, tzinfo=HKT)
    )
    assert reason == ""
    assert selected is eligible
    missing, reason = history.select_latest_complete(
        [future], datetime(2026, 7, 18, 8, 10, tzinfo=HKT)
    )
    assert missing is None
    assert reason == "no_complete_snapshot_at_or_before_freeze"


def test_hash_bundle_policy_and_tamper_rejection(tmp_path: Path) -> None:
    assert history.POLICY["execution_enabled"] is False
    assert history.POLICY["frontend_selectable"] is False
    assert history.POLICY["roi_authorized"] is False
    final = tmp_path / "bundle"
    stage = history.make_stage(final)
    try:
        (stage / "snapshots.csv").write_text("snapshot_id\nabc\n", encoding="utf-8")
        manifest = {
            "schema_version": history.CAPTURE_SCHEMA,
            "policy": history.POLICY,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        history.publish_immutable_bundle(stage, final)
    finally:
        history.discard_stage(stage)
    assert history.verify_hashed_bundle(final, history.CAPTURE_SCHEMA)["status"] == "valid"
    with (final / "snapshots.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")
    with pytest.raises(history.CorrectScorePriceError, match="checksum mismatch"):
        history.verify_hashed_bundle(final, history.CAPTURE_SCHEMA)


def test_500_terminal_fields_do_not_exist_in_price_asset_schema() -> None:
    snapshot, prices = build_snapshot()
    forbidden = {"playid", "winning_sp", "settlement_status", "terminal_sp"}
    assert forbidden.isdisjoint(snapshot)
    assert all(forbidden.isdisjoint(row) for row in prices)


def test_nowscore_crown_forward_observation_retains_25_scores_but_rejects_missing_tails() -> None:
    odds = nowscore_odds_html()
    context = "<html><body>最后更新 2026-07-18 08:00:00</body></html>".encode()

    snapshot, prices = history.snapshot_from_nowscore_crown_current(
        odds,
        context,
        issue="26076",
        match_idx=25,
        provider_match_id="2997342",
        kickoff_hkt=datetime(2026, 7, 18, 9, 0, tzinfo=HKT),
        fetched_at_utc="2026-07-18T00:05:00+00:00",
        source_url="https://live.nowscore.com/analysis/odds/2997342.htm",
        raw_file="raw/odds.html",
        raw_payload_sha256="a" * 64,
        source_context_url="https://live.nowscore.com/analysis/2997342cn.html",
        source_context_file="raw/context.html",
        source_context_sha256="b" * 64,
        capture_batch_id="batch-nowscore",
    )

    assert snapshot["provider"] == "nowscore"
    assert snapshot["bookmaker_key"] == "crown"
    assert snapshot["outcome_count"] == 25
    assert len(prices) == 25
    assert snapshot["phase"] == "pregame"
    assert snapshot["complete"] == 0
    assert snapshot["completeness_reason"] == "missing_tail_outcomes"
    assert json.loads(snapshot["missing_exact_outcomes_json"]) == []
    assert json.loads(snapshot["missing_required_outcomes_json"]) == [
        "away_other", "draw_other", "home_other"
    ]


def test_nowscore_forward_observation_rejects_a_postkickoff_fetch() -> None:
    labels = (
        "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "4:3",
        "0:0", "1:1", "2:2", "3:3", "4:4",
    )
    odds = (
        "<table><tr><td><b>波胆</b></td>"
        + "".join(f"<td>{value}</td>" for value in labels)
        + "</tr><tr><td>主</td>" + "".join("<td>6</td>" for _ in range(15))
        + "</tr><tr><td>客</td>" + "".join("<td>8</td>" for _ in range(10))
        + "</tr></table>"
    ).encode()
    snapshot, _ = history.snapshot_from_nowscore_crown_current(
        odds,
        "<div>最后更新 2026-07-18 08:00:00</div>".encode(),
        issue="26076",
        match_idx=25,
        provider_match_id="2997342",
        kickoff_hkt=datetime(2026, 7, 18, 9, 0, tzinfo=HKT),
        fetched_at_utc="2026-07-18T01:05:00+00:00",
        source_url="https://example.test/odds",
        raw_file="raw/odds.html",
        raw_payload_sha256="a" * 64,
        source_context_url="https://example.test/context",
        source_context_file="raw/context.html",
        source_context_sha256="b" * 64,
        capture_batch_id="batch-nowscore",
    )
    assert snapshot["phase"] == "invalid_or_postkickoff"
    assert snapshot["complete"] == 0


def test_partial_capture_does_not_satisfy_forward_checkpoint(tmp_path: Path) -> None:
    issue_root = tmp_path / "26076"
    partial = issue_root / "partial"
    complete = issue_root / "complete"
    observed = issue_root / "observed"
    partial.mkdir(parents=True)
    complete.mkdir()
    observed.mkdir()
    (partial / "manifest.json").write_text(
        json.dumps({"collector_checkpoint_id": "blocked", "status": "partial"}), encoding="utf-8"
    )
    (complete / "manifest.json").write_text(
        json.dumps({"collector_checkpoint_id": "usable", "status": "complete"}), encoding="utf-8"
    )
    (observed / "manifest.json").write_text(
        json.dumps(
            {
                "collector_checkpoint_id": "observed",
                "status": "partial",
                "match_indices": [25, 26],
                "operational_observation_complete": True,
                "blocked_pages": 0,
            }
        ),
        encoding="utf-8",
    )
    assert refresh.successful_checkpoints(tmp_path, "26076") == {"usable", "observed"}
    assert refresh.checkpoint_id("26076", 2, "prefreeze").endswith("correct_score_price_v2")
    assert not hasattr(refresh, "record_source_meta")


def test_rolling_observation_checkpoints_are_bucketed_and_keep_freeze_checkpoint() -> None:
    segment = {
        "freeze_at_hkt": datetime(2026, 7, 18, 8, 25, tzinfo=HKT),
    }
    observed = refresh.correct_score_due_checkpoints(
        segment,
        now=datetime(2026, 7, 18, 8, 2, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
        observation_horizon_minutes=24 * 60,
        observation_bucket_minutes=30,
    )
    assert len(observed) == 1
    assert observed[0][0].startswith("observe_")
    assert observed[0][1] == "prefreeze_observation"

    prefreeze = refresh.correct_score_due_checkpoints(
        segment,
        now=datetime(2026, 7, 18, 8, 16, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
        observation_horizon_minutes=24 * 60,
        observation_bucket_minutes=30,
    )
    assert {trigger for _phase, trigger in prefreeze} == {"prefreeze_observation", "prefreeze"}

    frozen = refresh.correct_score_due_checkpoints(
        segment,
        now=datetime(2026, 7, 18, 8, 25, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
        observation_horizon_minutes=24 * 60,
        observation_bucket_minutes=30,
    )
    assert frozen == [("freeze", "freeze")]


def test_incomplete_schema_can_be_a_successful_forward_observation_without_becoming_complete() -> None:
    result = {
        "status": "partial",
        "match_indices": [25, 26],
        "snapshot_rows": 2,
        "price_rows": 50,
        "blocked_pages": 0,
        "complete_snapshot_rows": 0,
    }
    assert refresh.has_full_forward_observation_coverage(result) is True
    assert refresh.has_full_forward_observation_coverage({**result, "price_rows": 49}) is False
    assert result["status"] == "partial"
    assert result["complete_snapshot_rows"] == 0


def test_nowscore_match_retry_keeps_raw_attempts_and_selects_full_vector(tmp_path: Path) -> None:
    context = "<html>最后更新 2026-07-18 08:00:00</html>".encode()

    class Fetcher:
        def __init__(self) -> None:
            self.payloads = iter(
                (context, nowscore_odds_html(blank_first_price=True), context, nowscore_odds_html())
            )

        def fetch_with_primes(self, _url, _prime_urls):
            return next(self.payloads), "2026-07-18T00:05:00+00:00"

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    snapshot, prices, page = manager.collect_nowscore_forward_observation(
        fetcher=Fetcher(),
        raw_root=raw_root,
        raw_prefix="025_2997342",
        attempts=3,
        retry_delay=0,
        context_url="https://example.test/context",
        source_url="https://example.test/odds",
        issue="26076",
        match_idx=25,
        provider_match_id="2997342",
        kickoff_hkt=datetime(2026, 7, 18, 9, 0, tzinfo=HKT),
        capture_batch_id="batch-retry",
    )

    assert snapshot is not None
    assert snapshot["exact_score_complete"] == 1
    assert len(prices) == 25
    assert page["attempt_count"] == 2
    assert page["exact_score_complete_rows"] == 1
    attempts = json.loads(page["attempts_json"])
    assert [item["status"] for item in attempts] == [
        "incomplete_exact_score_vector", "ok"
    ]
    assert len(list(raw_root.glob("*.html"))) == 4


def test_capture_verifier_cross_checks_attempt_inventory_hashes(tmp_path: Path) -> None:
    final = tmp_path / "attempt-bundle"
    stage = history.make_stage(final)
    try:
        (stage / "raw").mkdir()
        (stage / "raw/context.html").write_bytes(b"context")
        manager.write_csv(
            stage / "page_inventory.csv",
            [
                {
                    "match_idx": 25,
                    "raw_file": "",
                    "attempts_json": json.dumps(
                        [
                            {
                                "context_file": "raw/context.html",
                                "context_sha256": "0" * 64,
                                "odds_file": "",
                                "odds_sha256": "",
                            }
                        ]
                    ),
                }
            ],
            manager.PAGE_FIELDS,
        )
        (stage / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": history.CAPTURE_SCHEMA,
                    "capture_batch_id": "attempt-bundle",
                    "policy": history.POLICY,
                }
            ),
            encoding="utf-8",
        )
        history.publish_immutable_bundle(stage, final)
    finally:
        history.discard_stage(stage)

    with pytest.raises(history.CorrectScorePriceError, match="attempt raw mismatch"):
        manager.verify_correct_score_bundle(final, expected_schema=history.CAPTURE_SCHEMA)


def test_replay_missing_diagnosis_prefers_full_exact_candidate() -> None:
    candidates = [
        {
            "snapshot_ts_hkt": "2026-07-18T08:00:00+08:00",
            "fetched_at_utc": "2026-07-18T00:01:00+00:00",
            "phase": "pregame",
            "exact_score_complete": "0",
            "exact_score_count": "24",
            "completeness_reason": "missing_exact_score_outcomes",
            "missing_required_outcomes_json": '["1-0"]',
        },
        {
            "snapshot_ts_hkt": "2026-07-18T07:55:00+08:00",
            "fetched_at_utc": "2026-07-18T00:02:00+00:00",
            "phase": "pregame",
            "exact_score_complete": "1",
            "exact_score_count": "25",
            "completeness_reason": "missing_tail_outcomes",
            "missing_required_outcomes_json": '["home_other"]',
        },
    ]
    reason, best = manager.diagnose_missing_snapshot(
        candidates,
        freeze_at_hkt=datetime(2026, 7, 18, 8, 25, tzinfo=HKT),
        source_statuses=["incomplete_outcome_schema"],
        fallback_reason="no_complete_snapshot",
    )
    assert reason == "missing_tail_outcomes"
    assert best is candidates[1]


def test_provider_mapping_cache_must_come_from_hash_verified_capture(tmp_path: Path) -> None:
    issue_html = (
        '<html><title>单场比分直播</title><table><tr matchid="1338614">'
        '<td class="graytx"><span>1</span></td><td><a class="ssname">罗甲</a></td>'
        '<td class="graytx">07-17 23:30</td><td></td>'
        '<td><a class="ctrl_homename">沃伦塔里</a></td><td></td>'
        '<td><a class="ctrl_awayname">博托沙尼</a></td></tr></table></html>'
    ).encode()
    final = tmp_path / "26076" / "batch"
    stage = history.make_stage(final)
    try:
        (stage / "raw").mkdir()
        (stage / "raw/issue.html").write_bytes(issue_html)
        (stage / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": history.CAPTURE_SCHEMA,
                    "capture_batch_id": "batch",
                    "policy": history.POLICY,
                }
            ),
            encoding="utf-8",
        )
        history.publish_immutable_bundle(stage, final)
    finally:
        history.discard_stage(stage)

    rows, source = manager.load_cached_issue_matches(tmp_path, "26076")

    assert rows[1].match_id == "1338614"
    assert source["path"] == str(final.resolve())
    assert len(source["sha256s_sha256"]) == 64


def test_freeze_coordinator_uses_only_verified_nowscore_crown_captures(tmp_path: Path) -> None:
    valid = tmp_path / "26076" / "valid"
    stage = history.make_stage(valid)
    try:
        (stage / "page_inventory.csv").write_text(
            "raw_file,raw_payload_sha256,source_context_file,source_context_sha256\n",
            encoding="utf-8",
        )
        (stage / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": history.CAPTURE_SCHEMA,
                    "capture_batch_id": "valid",
                    "provider": "nowscore",
                    "bookmaker_key": "crown",
                    "provider_company_id": "3",
                    "policy": history.POLICY,
                }
            ),
            encoding="utf-8",
        )
        history.publish_immutable_bundle(stage, valid)
    finally:
        history.discard_stage(stage)

    old = tmp_path / "26076" / "old-unsafe"
    old.mkdir()
    (old / "manifest.json").write_text(
        json.dumps({"schema_version": history.CAPTURE_SCHEMA, "policy": {}}), encoding="utf-8"
    )

    assert refresh.capture_bundles(tmp_path, "26076") == [valid]
