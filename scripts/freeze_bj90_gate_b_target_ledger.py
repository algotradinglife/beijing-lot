#!/usr/bin/env python3
"""One authorized official-SP target read for #90 Gate B."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "scripts").is_dir(): return candidate
    raise RuntimeError("repository root unavailable")


ROOT=root(); FREEZE=ROOT/"results/bj90_gate_a_preoutcome_v3"; OUT=ROOT/"results/bj90_gate_b_target_ledger_v1"
SOURCE=ROOT.parent.parent/"data/derived/beidan_xlsm/beidan_xlsm.sqlite"


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def read(path: Path) -> list[dict]:
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=sorted({k for r in rows for k in r}));w.writeheader();w.writerows(rows)


def main() -> int:
    if OUT.exists(): raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage=Path(tempfile.mkdtemp(prefix="bj90-target-ledger-",dir=OUT.parent))
    try:
        manifest=json.loads((FREEZE/"SHA256SUMS.json").read_text())
        actual={p.name:sha(p) for p in FREEZE.iterdir() if p.is_file() and p.name!="SHA256SUMS.json"}
        if actual != manifest: raise RuntimeError("Gate-A v3 manifest mismatch")
        card=json.loads((FREEZE/"experiment_card.json").read_text())
        if sha(SOURCE)!=card["source"]["sha256"]: raise RuntimeError("source bytes changed")
        rows=read(FREEZE/"frozen_preoutcome_rows.csv"); ids=[int(r["match_id"]) for r in rows]
        target={}; conn=sqlite3.connect(f"file:{SOURCE}?mode=ro",uri=True)
        for i in range(0,len(ids),900):
            part=ids[i:i+900]; marks=",".join("?" for _ in part)
            # Gate B's sole target access; result and winning-SP columns are never selected.
            for mid,s3,s1,s0 in conn.execute(f"SELECT match_id,official_sp_3,official_sp_1,official_sp_0 FROM match_features WHERE match_id IN ({marks})",part): target[int(mid)]=(s3,s1,s0)
        conn.close(); ledger=[]
        for r in rows:
            mid=int(r["match_id"]); values=target.get(mid)
            if values is None: reason="MISSING_ROW"; values=("","","")
            elif any(v is None or float(v)<=0 for v in values): reason="NONPOSITIVE"; values=("","","")
            else: reason="AVAILABLE_POSITIVE"
            ledger.append({"match_id":mid,"issue":r["issue"],"match_idx":r["match_idx"],"year":r["year"],"fold":r["fold"],"target_reason":reason,"sp_3":values[0],"sp_1":values[1],"sp_0":values[2]})
        if any(r["target_reason"]!="AVAILABLE_POSITIVE" for r in ledger): raise RuntimeError("target ledger incomplete")
        write(stage/"official_sp_target_ledger.csv",ledger)
        meta={"issue":90,"stage":"GATE_B_AUTHORIZED_OFFICIAL_SP_TARGET_LEDGER","created_at_utc":datetime.now(timezone.utc).isoformat(),"gate_a_manifest_sha256":sha(FREEZE/"SHA256SUMS.json"),"source_sha256":card["source"]["sha256"],"target_read_whitelist":["match_features.match_id","match_features.official_sp_3","match_features.official_sp_1","match_features.official_sp_0"],"prohibited":["score","result_label","result_code","winning_sp","ROI","portfolio","N","K","stake"]}
        (stage/"ledger_card.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n");shutil.copyfile(__file__,stage/"ledger_runner.py")
        m={p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file()};(stage/"SHA256SUMS.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
        os.replace(stage,OUT);print(json.dumps({"output":str(OUT),"n":len(ledger),"manifest_sha256":sha(OUT/"SHA256SUMS.json")},sort_keys=True));return 0
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise


if __name__=="__main__":sys.exit(main())
