"""Small executable SQLite/Parquet contract for #253.

The only host-dependent input is BEIJING_LOT_DATA_ROOT.  It deliberately uses
issue-local slots, never upstream match ids as cross-source fixture identities.
"""
from __future__ import annotations
import hashlib, json, os, sqlite3
from pathlib import Path
import pandas as pd
import pyarrow as pa
from source_schema import publication

CONTRACT_VERSION = "BJ-UNIFIED-PHYSICAL-SCHEMA-001-v1"
OUTCOMES = ("3", "1", "0")
PACKAGE = "bj_unified_physical_schema_v1"

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE source_registry (source_id TEXT PRIMARY KEY, source_namespace TEXT NOT NULL CHECK(source_namespace IN ('strict_forward','historical_proxy')), causal_grade TEXT NOT NULL, time_semantics TEXT NOT NULL, capture_manifest_sha256 TEXT NOT NULL);
CREATE TABLE capture_manifest (capture_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES source_registry(source_id), source_path_relative TEXT NOT NULL, source_size_bytes INTEGER NOT NULL, source_mtime_ns INTEGER NOT NULL, slice_sha256 TEXT NOT NULL, immutable_raw_capture INTEGER NOT NULL CHECK(immutable_raw_capture IN (0,1)));
CREATE TABLE issue_slot (issue_code TEXT NOT NULL, match_idx INTEGER NOT NULL CHECK(match_idx>0), issue_slot_id TEXT NOT NULL UNIQUE, fixture_entity_id TEXT, identity_status TEXT NOT NULL CHECK(identity_status IN ('ISSUE_LOCAL_ONLY','UNIDENTIFIED')), PRIMARY KEY(issue_code,match_idx));
CREATE TABLE m3_cell (issue_code TEXT NOT NULL, match_idx INTEGER NOT NULL, outcome_code TEXT NOT NULL CHECK(outcome_code IN ('3','1','0')), source_id TEXT NOT NULL REFERENCES source_registry(source_id), source_namespace TEXT NOT NULL CHECK(source_namespace IN ('strict_forward','historical_proxy')), causal_grade TEXT NOT NULL, time_semantics TEXT NOT NULL, observed_at_utc TEXT, received_at_utc TEXT, snapshot_horizon TEXT NOT NULL, value REAL, availability_mask INTEGER NOT NULL CHECK(availability_mask IN (0,1)), missing_reason TEXT, capture_id TEXT NOT NULL REFERENCES capture_manifest(capture_id), PRIMARY KEY(issue_code,match_idx,outcome_code,source_id,snapshot_horizon), FOREIGN KEY(issue_code,match_idx) REFERENCES issue_slot(issue_code,match_idx), CHECK((availability_mask=1 AND value IS NOT NULL AND missing_reason IS NULL) OR (availability_mask=0 AND value IS NULL AND missing_reason IS NOT NULL)));
CREATE TABLE settlement (issue_code TEXT NOT NULL, match_idx INTEGER NOT NULL, result_code TEXT NOT NULL CHECK(result_code IN ('3','1','0')), winning_sp REAL, settled_at_utc TEXT NOT NULL, PRIMARY KEY(issue_code,match_idx));
"""
ARROW_SCHEMA = pa.schema([pa.field("issue_code", pa.string(), False), pa.field("match_idx", pa.int32(), False), pa.field("outcome_code", pa.string(), False), pa.field("source_id", pa.string(), False), pa.field("source_namespace", pa.string(), False), pa.field("causal_grade", pa.string(), False), pa.field("time_semantics", pa.string(), False), pa.field("observed_at_utc", pa.timestamp("ns", tz="UTC"), True), pa.field("received_at_utc", pa.timestamp("ns", tz="UTC"), True), pa.field("snapshot_horizon", pa.string(), False), pa.field("value", pa.float64(), True), pa.field("availability_mask", pa.bool_(), False), pa.field("missing_reason", pa.string(), True), pa.field("capture_id", pa.string(), False)])

def resolve_data_root(value: str | Path | None = None) -> Path:
    raw = str(value) if value is not None else os.environ.get("BEIJING_LOT_DATA_ROOT")
    if not raw: raise ValueError("BEIJING_LOT_DATA_ROOT is required; no fallback path is permitted")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir(): raise ValueError(f"BEIJING_LOT_DATA_ROOT is not a directory: {root}")
    return root

def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _slot(issue: str, idx: int) -> str: return f"bjslot:{issue}:{idx:03d}"
def _receipt(root: Path, path: Path, rows: pd.DataFrame) -> dict:
    stat=path.stat(); return {"source_path_relative": str(path.relative_to(root)), "source_size_bytes":stat.st_size,"source_mtime_ns":stat.st_mtime_ns,"slice_sha256":_sha(rows.to_csv(index=False).encode()),"immutable_raw_capture":False}
def _rows(root: Path) -> tuple[pd.DataFrame,pd.DataFrame,Path,Path]:
    live=root/'data/beidan_live.db'; hist=root/'data/derived/beidan_xlsm/beidan_xlsm.sqlite'
    if not live.is_file() or not hist.is_file(): raise FileNotFoundError("representative build requires data/beidan_live.db and data/derived/beidan_xlsm/beidan_xlsm.sqlite under BEIJING_LOT_DATA_ROOT")
    with sqlite3.connect(f"file:{live}?mode=ro",uri=True) as c:
        strict=pd.read_sql_query("SELECT m.issue issue_code,m.match_idx,s.snapshot_ts observed_at_utc,s.sp_3,s.sp_1,s.sp_0 FROM matches m JOIN snapshots s ON s.match_id=m.match_id WHERE m.issue IS NOT NULL AND m.match_idx>0 ORDER BY s.snapshot_ts LIMIT 2",c)
    with sqlite3.connect(f"file:{hist}?mode=ro",uri=True) as c:
        proxy=pd.read_sql_query("SELECT m.issue issue_code,m.match_idx,x.snapshot snapshot_horizon,x.v1_avg,x.v2_avg,x.v3_avg FROM matches m JOIN market_consensus x ON x.match_id=m.match_id WHERE x.market='euro_1x2' AND x.snapshot IN ('initial','10h','1h') AND m.issue IS NOT NULL AND m.match_idx>0 ORDER BY m.match_id,x.snapshot LIMIT 6",c)
    if strict.empty or proxy.empty: raise ValueError("representative sources yielded no M×3 rows")
    return strict,proxy,live,hist

def build_representative_slice(data_root: str | Path | None=None) -> Path:
    root=resolve_data_root(data_root); strict,proxy,live,hist=_rows(root); target=root/'normalized'/PACKAGE
    def populate(stage: Path) -> None:
        db=stage/'normalized.sqlite'; con=sqlite3.connect(db); con.executescript(DDL)
        all_cells=[]; captures=[]
        for source, frame, path, namespace, grade, semantics in [("beidan_live_poll",strict,live,"strict_forward","POLL_STARTED_AGAINST_CURRENT_SCHEDULE_REFERENCE","POLL_STARTED_AT_UTC"),("beidan_xlsm_proxy",proxy,hist,"historical_proxy","HISTORICAL_PROXY_LABEL_ONLY","SOURCE_RELATIVE_LABEL")]:
            rec=_receipt(root,path,frame); capture=f"capture:{source}:{rec['slice_sha256'][:16]}"; captures.append({"capture_id":capture,"source_id":source,**rec})
            con.execute("INSERT INTO source_registry VALUES(?,?,?,?,?)",(source,namespace,grade,semantics,rec['slice_sha256']))
            value_cols=(('sp_3','sp_1','sp_0') if namespace=='strict_forward' else ('v1_avg','v2_avg','v3_avg'))
            for _,r in frame.iterrows():
                issue=str(r.issue_code).strip(); idx=int(r.match_idx); con.execute("INSERT OR IGNORE INTO issue_slot VALUES(?,?,?,?,?)",(issue,idx,_slot(issue,idx),None,"ISSUE_LOCAL_ONLY"))
                for outcome,col in zip(OUTCOMES,value_cols):
                    value=pd.to_numeric(pd.Series([r[col]]),errors='coerce').iloc[0]; ok=bool(pd.notna(value) and float(value)>0)
                    row={"issue_code":issue,"match_idx":idx,"outcome_code":outcome,"source_id":source,"source_namespace":namespace,"causal_grade":grade,"time_semantics":semantics,"observed_at_utc":r.get('observed_at_utc') if namespace=='strict_forward' else None,"received_at_utc":None,"snapshot_horizon":"poll" if namespace=='strict_forward' else str(r.snapshot_horizon),"value":float(value) if ok else None,"availability_mask":ok,"missing_reason":None if ok else "MISSING_OR_INVALID_SOURCE_VALUE","capture_id":capture}; all_cells.append(row)
        for rec in captures: con.execute("INSERT INTO capture_manifest VALUES(?,?,?,?,?,?,?)",tuple(rec[k] for k in ('capture_id','source_id','source_path_relative','source_size_bytes','source_mtime_ns','slice_sha256','immutable_raw_capture')))
        for r in all_cells: con.execute("INSERT INTO m3_cell VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(int(r[k]) if k=='availability_mask' else r[k] for k in ('issue_code','match_idx','outcome_code','source_id','source_namespace','causal_grade','time_semantics','observed_at_utc','received_at_utc','snapshot_horizon','value','availability_mask','missing_reason','capture_id')))
        con.commit(); con.close(); frame=pd.DataFrame(all_cells); frame['observed_at_utc']=pd.to_datetime(frame['observed_at_utc'],utc=True); frame['received_at_utc']=pd.to_datetime(frame['received_at_utc'],utc=True); frame['availability_mask']=frame['availability_mask'].astype(bool); publication.atomic_write_parquet(frame,stage/'m3_cells.parquet')
        manifest={"contract_version":CONTRACT_VERSION,"row_grain":"issue_code x match_idx x outcome_code x source_id x snapshot_horizon","identity_boundary":"issue-local slot only; fixture/team/competition entity ids unavailable","namespace_pooling_forbidden":True,"settlement_separate":True,"captures":captures,"files":{p.name:_sha(p.read_bytes()) for p in (db,stage/'m3_cells.parquet')}}; publication.atomic_write_json(stage/'MANIFEST.json',manifest)
    out=publication.atomic_publish_directory(target,populate,force=True); verify_snapshot(out); return out

def verify_snapshot(package: str | Path) -> None:
    p=Path(package); manifest=json.loads((p/'MANIFEST.json').read_text());
    if manifest.get('contract_version')!=CONTRACT_VERSION or not manifest.get('namespace_pooling_forbidden'): raise AssertionError('contract manifest violation')
    if any(_sha((p/n).read_bytes())!=h for n,h in manifest['files'].items()): raise AssertionError('snapshot hash mismatch')
    con=sqlite3.connect(f"file:{p/'normalized.sqlite'}?mode=ro",uri=True); rows=pd.read_sql_query('SELECT * FROM m3_cell',con); con.close()
    if set(rows.outcome_code)!=set(OUTCOMES) or rows.groupby(['issue_code','match_idx','source_id','snapshot_horizon']).size().ne(3).any(): raise AssertionError('M×3 cell invariant failed')
    if set(rows.source_namespace)> {'strict_forward','historical_proxy'} or rows.query("source_namespace == 'strict_forward' and causal_grade != 'POLL_STARTED_AGAINST_CURRENT_SCHEDULE_REFERENCE'").shape[0]: raise AssertionError('namespace semantics violation')
    if (rows.source_namespace.eq('historical_proxy') & rows.observed_at_utc.notna()).any(): raise AssertionError('proxy claimed clock')
