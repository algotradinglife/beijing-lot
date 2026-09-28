#!/usr/bin/env python3
"""Read-only settlement verification; capture history evidence, never fill options.

The reference database is opened read-only. All new outputs go into a new
evidence directory. History zero cells are retained as zeros, not invalid SPs;
this parser is intentionally distinct from the pre-match history-vector parser.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.nowscore_bjdc_sp_history import TYPEID_LABELS, history_url  # noqa: E402
from src.nowscore_settlement import canonical, digest  # noqa: E402


def parse_history(payload: bytes, issue: str, slot: int) -> list[dict]:
    soup = BeautifulSoup(payload.decode("utf-8-sig", errors="strict"), "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if not re.search(rf"Sp值变化表\s*\({re.escape(issue)}期第{slot}场\)", title):
        raise ValueError("history page identity mismatch")
    table = soup.find("table")
    if table is None:
        raise ValueError("history table absent")
    trs = table.find_all("tr")
    if not trs:
        raise ValueError("history header absent")
    header = tuple(x.get_text(strip=True) for x in trs[0].find_all("td"))
    if header != (*TYPEID_LABELS[8], "变化时间"):
        raise ValueError("history domain mismatch")
    rows = []
    for tr in trs[1:]:
        cells = [x.get_text(strip=True) for x in tr.find_all("td")]
        if len(cells) != 26:
            raise ValueError("history row width mismatch")
        values = []
        for raw in cells[:25]:
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ValueError("history nonnumeric cell") from exc
            if not value.is_finite() or value < 0 or 0 < value < 1:
                raise ValueError("history invalid SP")
            values.append(value)
        if not re.fullmatch(r"\d{2}-\d{2}\s+\d{2}:\d{2}", cells[-1]):
            raise ValueError("history timestamp malformed")
        positive = [(label, raw) for label, raw, v in zip(TYPEID_LABELS[8], cells, values, strict=False) if v > 0]
        rows.append({"source_time_raw": cells[-1], "vector_raw": cells[:25],
                     "positive_count": len(positive),
                     "single_option": positive[0][0] if len(positive) == 1 else None,
                     "single_sp_raw": positive[0][1] if len(positive) == 1 else None,
                     "all_one": all(v == 1 for v in values)})
    return rows


def verify(target: dict, rows: list[dict]) -> dict:
    # Source display order is preserved; no year inferred and no pre-match
    # availability claim. Never search backwards for a conveniently matching row.
    result = {**target, "history_rows": len(rows), "evidence_class": "HISTORICAL_PROXY",
              "official_notice_verified": False, "data_changed": False}
    if not rows:
        return {**result, "classification": "无历史记录"}
    latest = rows[0]
    result.update(latest)
    singles = {(r["single_option"], str(Decimal(r["single_sp_raw"]))) for r in rows if r["single_option"]}
    result["distinct_single_vectors"] = sorted(singles)
    if latest["all_one"]:
        return {**result, "classification": "待核查：最新行为全一向量"}
    if latest["single_option"] is None:
        return {**result, "classification": "无最新单选结算证据"}
    if latest["single_option"] != target["expected_option"]:
        return {**result, "classification": "冲突：历史选项与比分不符"}
    if Decimal(latest["single_sp_raw"]) == 1:
        return {**result, "classification": "待核查：单选SP为1"}
    if len(singles) > 1:
        return {**result, "classification": "待核查：多个不同单选历史向量"}
    expected_sp = Decimal(target["summary_sp_raw"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if Decimal(latest["single_sp_raw"]) != expected_sp:
        return {**result, "classification": "冲突：历史SP与汇总SP不符"}
    return {**result, "classification": "历史页支持（SP按两位小数一致）"}


def targets_from_db(path: Path) -> tuple[list[dict], str]:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as con:
        receipt = con.execute("SELECT payload_json FROM receipt").fetchone()[0]
        if json.loads(receipt)["source"] != "nowscore":
            raise ValueError("not a Nowscore-only database")
        rows = con.execute("""SELECT o.issue,o.slot,o.score,o.expected_option,o.payload_json
          FROM observation o JOIN finding f USING(issue,slot,play,source_sha256)
          WHERE f.code='summary_sp_without_option' AND o.play='bf'
          ORDER BY o.issue,o.slot""").fetchall()
    targets = []
    for issue, slot, score, expected, payload in rows:
        r = json.loads(payload)
        if r["status"] != "完场" or expected not in {"胜其他", "平其他", "负其他"}:
            raise ValueError("unexpected verification target")
        targets.append({"issue": issue, "slot": slot, "score": score, "expected_option": expected,
                        "summary_sp_raw": r["summary_sp_raw"], "roster_sha256": r["source_sha256"],
                        "url": history_url(issue, slot, 8)})
    if not targets or len({(r["issue"], r["slot"]) for r in targets}) != len(targets):
        raise ValueError("empty or duplicate target set")
    return targets, digest(receipt.encode())


def replay(run_root: Path) -> dict:
    manifest_bytes = (run_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["schema"] != "nowscore_bf_history_verification_v1":
        raise ValueError("wrong manifest")
    results = []
    for entry in manifest["captures"]:
        target = entry["target"]
        if entry.get("error"):
            results.append({**target, "classification": "抓取失败", "error": entry["error"]})
            continue
        sha = entry["sha256"]
        if not re.fullmatch("[0-9a-f]{64}", sha):
            raise ValueError("invalid source hash")
        b = (run_root / "raw" / (sha + ".html")).read_bytes()
        if digest(b) != sha:
            raise ValueError("source hash mismatch")
        try:
            result = verify(target, parse_history(b, target["issue"], target["slot"]))
        except ValueError as exc:
            result = {**target, "classification": "解析待核查", "error": str(exc)}
        results.append({**result, "history_sha256": sha, "received_at": entry["received_at"]})
    return {"manifest_sha256": digest(manifest_bytes), "parser_sha256": digest(Path(__file__).read_bytes()),
            "domain_module_sha256": digest((ROOT / "src/nowscore_bjdc_sp_history.py").read_bytes()),
            "target_count": len(results), "counts": dict(Counter(r["classification"] for r in results)),
            "results_sha256": digest(canonical(results).encode()), "results": results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("capture", "replay"))
    p.add_argument("--db", type=Path)
    p.add_argument("--run-root", type=Path, required=True)
    a = p.parse_args()
    if a.mode == "replay":
        original = json.loads((a.run_root / "verification.json").read_text())
        assert canonical(replay(a.run_root)) == canonical(original), "replay mismatch"
        print("Independent offline replay: exact result/receipt equality")
        return
    if a.db is None:
        p.error("capture requires --db")
    targets, receipt_sha = targets_from_db(a.db)
    a.run_root.mkdir(parents=True, exist_ok=False)
    (a.run_root / "raw").mkdir()
    captures = []
    for n, target in enumerate(targets, 1):
        entry = {"target": target}
        try:
            req = urllib.request.Request(target["url"], headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.geturl() != target["url"]:
                    raise ValueError("unexpected redirect")
                b = response.read()
            entry.update(sha256=digest(b), received_at=datetime.now(timezone.utc).isoformat())
            (a.run_root / "raw" / (entry["sha256"] + ".html")).write_bytes(b)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        captures.append(entry)
        with (a.run_root / "capture_log.jsonl").open("a", encoding="utf-8") as log:
            log.write(canonical(entry) + "\n")
        print(f'{n}/{len(targets)} {target["issue"]}/{target["slot"]} {entry.get("error", "captured")}', flush=True)
        time.sleep(2)
    manifest = {"schema": "nowscore_bf_history_verification_v1", "reference_receipt_sha256": receipt_sha,
                "captures": captures}
    (a.run_root / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    result = replay(a.run_root)
    (a.run_root / "verification.json").write_text(canonical(result) + "\n", encoding="utf-8")
    lines = ["# Nowscore 比分其他选项历史页逐场核查", "", "仅为源站内部历史佐证，不是官方结算公告。未修改原库。", "",
             "| 期号 | slot | 比分 | 应属选项 | 汇总SP | 历史选项 | 历史SP | 分类 | 来源 |",
             "|---|---:|---|---|---:|---|---:|---|---|"]
    for r in result["results"]:
        lines.append(f'| {r["issue"]} | {r["slot"]} | {r["score"]} | {r["expected_option"]} | {r["summary_sp_raw"]} | {r.get("single_option") or "—"} | {r.get("single_sp_raw") or "—"} | {r["classification"]} | [历史页]({r["url"]}) |')
    (a.run_root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(canonical(result["counts"]), flush=True)


if __name__ == "__main__":
    main()
