"""Independent comparison must detect normalized-table drift, not only receipts."""
import sqlite3

import pytest

from tests.test_nowscore_settlement import multi_issue_bundle
from src.nowscore_settlement import build_database
from src.nowscore_replay import compare_nowscore_databases, quote_identifier


@pytest.fixture
def databases(tmp_path):
    root = tmp_path / "source"
    multi_issue_bundle(root, count=2)
    paths = [tmp_path / "first.sqlite", tmp_path / "second.sqlite"]
    for path in paths:
        build_database(root, path)
    return paths


def test_complete_logical_replay_and_chunk_independence(databases):
    first = compare_nowscore_databases(*databases, chunk_rows=1)
    second = compare_nowscore_databases(*databases, chunk_rows=11)
    assert first == second and first["equal"]
    assert first["tables"]["option_sp"]["rows"] == 98
    assert first["tables"]["receipt"]["rows"] == 1
    with pytest.raises(ValueError, match="distinct"):
        compare_nowscore_databases(databases[0], databases[0])


@pytest.mark.parametrize("sql", [
    "UPDATE option_sp SET raw_sp='changed' WHERE rowid=1",
    "INSERT INTO finding SELECT * FROM finding LIMIT 1",
    "UPDATE observation SET status='changed' WHERE observation_id=1",
    "ALTER TABLE capture ADD COLUMN extra TEXT",
    "CREATE TABLE extra(value TEXT)",
    "DELETE FROM receipt",
])
def test_detects_drift_even_when_data_receipt_is_unchanged(databases, sql):
    with sqlite3.connect(databases[1]) as con:
        con.execute(sql)
    with pytest.raises(ValueError):
        compare_nowscore_databases(*databases)


def test_identifier_quoting_and_blob_null_type_preservation(databases):
    name = 'odd"; DROP TABLE receipt;--'
    for path in databases:
        with sqlite3.connect(path) as con:
            con.execute(f"CREATE TABLE {quote_identifier(name)}(value)")
            con.executemany(f"INSERT INTO {quote_identifier(name)} VALUES(?)", [(None,), (0,), ("0",), (b"0",)])
    result = compare_nowscore_databases(*databases, chunk_rows=2)
    assert result["tables"][name]["rows"] == 4
    with sqlite3.connect(databases[1]) as con:
        con.execute(f"UPDATE {quote_identifier(name)} SET value=0.0 WHERE typeof(value)='integer'")
    with pytest.raises(ValueError, match="typed row"):
        compare_nowscore_databases(*databases)


def test_sqlite_prefix_does_not_hide_user_tables(databases):
    with sqlite3.connect(databases[1]) as con:
        con.execute("CREATE TABLE sqliteXcustom(value)")
    with pytest.raises(ValueError, match="table sets"):
        compare_nowscore_databases(*databases)


def test_uncheckpointed_wal_is_rejected_without_mutating_source(databases):
    from src.nowscore_replay import database_file_hash

    con = sqlite3.connect(databases[1])
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute("UPDATE option_sp SET raw_sp='pending' WHERE rowid=1")
        con.commit()
        wal = databases[1].with_name(databases[1].name + "-wal")
        before = (database_file_hash(databases[1]), wal.read_bytes())
        with pytest.raises(ValueError, match="nonempty SQLite journal"):
            compare_nowscore_databases(*databases)
        assert before == (database_file_hash(databases[1]), wal.read_bytes())
    finally:
        con.close()


def test_checkpointed_wal_mode_still_requires_explicit_sealing(databases):
    con = sqlite3.connect(databases[1])
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    with pytest.raises(ValueError, match="WAL mode"):
        compare_nowscore_databases(*databases)


def test_pending_rollback_journal_is_rejected(databases):
    journal = databases[1].with_name(databases[1].name + "-journal")
    journal.write_bytes(b"pending journal evidence")
    with pytest.raises(ValueError, match="nonempty SQLite journal"):
        compare_nowscore_databases(*databases)
    assert journal.read_bytes() == b"pending journal evidence"


def test_replay_cli_and_no_overwrite(databases, tmp_path, capsys):
    import json
    from scripts.verify_nowscore_replay import main

    output = tmp_path / "replay.json"
    args = ["--left", str(databases[0]), "--right", str(databases[1]), "--output", str(output)]
    main(args)
    assert json.loads(capsys.readouterr().out)["equal"]
    result = json.loads(output.read_text())
    assert result["implementation_sha256"] and result["generated_at"]
    assert str(tmp_path) not in output.read_text()
    with pytest.raises(FileExistsError):
        main(args)
