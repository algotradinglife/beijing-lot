#!/usr/bin/env python3
"""Fail-closed cross-layer verifier for the natural-day operational contract."""
from __future__ import annotations
import argparse, hashlib, json, sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--db", type=Path, required=True); p.add_argument("--report", type=Path, required=True)
    a = p.parse_args(); raw = a.manifest.read_bytes(); manifest = json.loads(raw)
    claimed = manifest.pop("manifest_sha256"); actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if claimed != actual: raise SystemExit("manifest hash mismatch")
    conn = sqlite3.connect(a.db)
    rows = conn.execute("SELECT segment_idx,freeze_at,match_indices_json FROM segment_decision_windows WHERE issue=? ORDER BY segment_idx", (manifest["issue"],)).fetchall(); conn.close()
    hkt = ZoneInfo("Asia/Hong_Kong")
    def normalized(value: str) -> str:
        parsed = datetime.fromisoformat(value)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=hkt)).astimezone(hkt).isoformat(timespec="seconds")
    expected = [(int(x["segment_idx"]), normalized(x["freeze_at"]), list(x["match_indices"])) for x in manifest["segments"]]
    observed = [(int(i), normalized(str(f)), list(json.loads(m))) for i, f, m in rows]
    if expected != observed: raise SystemExit("cross-layer mismatch: SQLite differs from natural-day manifest")
    report = {"status":"PASS", "issue":manifest["issue"], "manifest_sha256":claimed, "segments":[{"segment_idx":i,"freeze_at":f,"match_count":len(m)} for i,f,m in observed]}
    a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, sort_keys=True, indent=2)+"\n")
    print(json.dumps(report, sort_keys=True))
if __name__ == "__main__": main()
