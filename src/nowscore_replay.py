"""Read-only, bounded-memory comparison of complete Nowscore SQLite outputs."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from src.nowscore_issue_inventory import canonical


def quote_identifier(name: str) -> str:
    """Quote a SQLite metadata identifier; values use SQL parameters elsewhere."""
    return '"' + name.replace('"', '""') + '"'


def database_file_hash(path: Path) -> str:
    """Stream SHA256 of a database file without loading it in memory."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require_no_pending_journal(path: Path) -> None:
    """Reject nonempty SQLite sidecars; never checkpoint or delete source data."""
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError("sealed database required: nonempty SQLite journal")


def compare_nowscore_databases(left: Path, right: Path, *, chunk_rows: int = 1000) -> dict:
    """Compare schemas and every typed row, including the original receipts.

    Requires two distinct, sealed Nowscore audit files with production disabled.
    Uses read-only connections, disk-backed sorting and bounded row chunks.
    Ignores physical page layout and indexes but compares every user table and
    duplicate row multiplicity. Raises on differences, corruption or input drift.
    Output contains file/content identities, never personal filesystem paths.
    """
    if type(chunk_rows) is not int or chunk_rows < 1:
        raise ValueError("chunk_rows must be a positive integer")
    if not left.is_file() or not right.is_file():
        raise FileNotFoundError("both replay database files must exist")
    if left.samefile(right):
        raise ValueError("independent replay requires distinct database files")
    for path in (left, right):
        require_no_pending_journal(path)
    before = [database_file_hash(path) for path in (left, right)]
    with closing(sqlite3.connect(left.resolve().as_uri() + "?mode=ro", uri=True)) as a, closing(
        sqlite3.connect(right.resolve().as_uri() + "?mode=ro", uri=True)
    ) as b:
        for con in (a, b):
            if con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
                raise ValueError("sealed database required: WAL mode is not accepted")
            con.execute("PRAGMA temp_store=FILE")
            if con.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("SQLite integrity check failed")
            if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("SQLite foreign key check failed")
            receipts = con.execute("SELECT payload_json FROM receipt").fetchall()
            if len(receipts) != 1:
                raise ValueError("sealed receipt missing or duplicated")
            receipt = json.loads(receipts[0][0])
            if receipt.get("source") != "nowscore" or receipt.get("production_enabled") is not False:
                raise ValueError("source-pure non-production receipt required")
        tables_sql = "SELECT name FROM sqlite_master WHERE type='table' AND substr(name,1,7) != 'sqlite_' ORDER BY name"
        names = [r[0] for r in a.execute(tables_sql)]
        if names != [r[0] for r in b.execute(tables_sql)]:
            raise ValueError("database table sets differ")
        required = {"capture", "observation", "option_sp", "finding", "receipt"}
        if not required.issubset(names):
            raise ValueError("audit schema incomplete")
        evidence = {}
        for name in names:
            table = quote_identifier(name)
            columns = a.execute(f"PRAGMA table_info({table})").fetchall()
            if columns != b.execute(f"PRAGMA table_info({table})").fetchall():
                raise ValueError(f"table schema differs: {name}")
            order = ",".join(quote_identifier(c[1]) + " COLLATE BINARY" for c in columns)
            query = f"SELECT * FROM {table} ORDER BY {order}"
            ac, bc = a.execute(query), b.execute(query)
            count = 0
            hasher = hashlib.sha256()
            while True:
                aa, bb = ac.fetchmany(chunk_rows), bc.fetchmany(chunk_rows)
                if len(aa) != len(bb):
                    raise ValueError(f"row count differs: {name}")
                if not aa:
                    break
                for ar, br in zip(aa, bb, strict=True):
                    if ar != br or tuple(map(type, ar)) != tuple(map(type, br)):
                        raise ValueError(f"typed row differs: {name}")
                    typed = [(type(v).__name__, v.hex() if isinstance(v, bytes) else v) for v in ar]
                    hasher.update(canonical(typed).encode() + b"\n")
                    count += 1
            evidence[name] = {"rows": count, "typed_rows_sha256": hasher.hexdigest()}
    for path in (left, right):
        require_no_pending_journal(path)
    if before != [database_file_hash(path) for path in (left, right)]:
        raise ValueError("database changed during comparison")
    return {"schema": "nowscore_logical_replay_v1", "equal": True,
            "left_file_sha256": before[0], "right_file_sha256": before[1],
            "tables": evidence, "production_enabled": False}
