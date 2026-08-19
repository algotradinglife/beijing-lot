"""Read-only construction of the frozen historical issue × fixture denominator."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class InventoryPaths:
    """Hashable source locations used to build the #267 denominator."""

    base_proxy: Path
    extension_2026: Path
    history: Path
    live: Path


_COLUMNS = [
    "issue_code",
    "match_idx",
    "provider_match_id",
    "kickoff_ts",
    "league",
    "home",
    "away",
    "native_handicap_line",
]


def _connect(path: Path) -> sqlite3.Connection:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _read(path: Path, query: str, source_name: str, priority: int) -> pd.DataFrame:
    with _connect(path) as connection:
        frame = pd.read_sql_query(query, connection)
    frame["issue_code"] = frame["issue_code"].astype("string").str.strip()
    frame["match_idx"] = pd.to_numeric(frame["match_idx"], errors="coerce").astype("Int64")
    frame = frame.loc[frame.issue_code.ne("") & frame.match_idx.notna()].copy()
    duplicate = frame.duplicated(["issue_code", "match_idx"], keep=False)
    if duplicate.any():
        keys = frame.loc[duplicate, ["issue_code", "match_idx"]].drop_duplicates().head(5)
        raise ValueError(f"{source_name} has duplicate issue slots: {keys.to_dict('records')}")
    frame["source_name"] = source_name
    frame["source_priority"] = priority
    return frame[[*_COLUMNS, "source_name", "source_priority"]]


def _base_or_extension(path: Path, source_name: str, priority: int) -> pd.DataFrame:
    return _read(
        path,
        """
        SELECT CAST(issue AS TEXT) AS issue_code,
               match_idx,
               CAST(provider_match_id AS TEXT) AS provider_match_id,
               kickoff_ts,
               league,
               home,
               away,
               CAST(handicap_line_norm AS REAL) AS native_handicap_line
        FROM matches
        WHERE issue IS NOT NULL AND trim(CAST(issue AS TEXT)) <> ''
          AND match_idx IS NOT NULL
        ORDER BY CAST(issue AS TEXT), match_idx
        """,
        source_name,
        priority,
    )


def _history(path: Path) -> pd.DataFrame:
    return _read(
        path,
        """
        SELECT CAST(issue AS TEXT) AS issue_code,
               match_idx,
               NULL AS provider_match_id,
               kickoff_ts,
               league,
               home,
               away,
               CAST(handicap_line AS REAL) AS native_handicap_line
        FROM historical_matches
        WHERE issue IS NOT NULL AND trim(CAST(issue AS TEXT)) <> ''
          AND match_idx IS NOT NULL
        ORDER BY CAST(issue AS TEXT), match_idx
        """,
        "history",
        30,
    )


def _live(path: Path) -> pd.DataFrame:
    return _read(
        path,
        """
        SELECT CAST(issue AS TEXT) AS issue_code,
               match_idx,
               NULL AS provider_match_id,
               kickoff_ts,
               league,
               home,
               away,
               CAST(handicap_line AS REAL) AS native_handicap_line
        FROM matches
        WHERE issue IS NOT NULL AND trim(CAST(issue AS TEXT)) <> ''
          AND match_idx IS NOT NULL
        ORDER BY CAST(issue AS TEXT), match_idx
        """,
        "live",
        40,
    )


def build_inventory(paths: InventoryPaths) -> pd.DataFrame:
    """Return one deterministic row for every currently known issue slot.

    The base and extension stores define historical-proxy presence. History and
    live stores only extend the denominator; their outcome/settlement columns
    are never selected.
    """

    frames = [
        _base_or_extension(paths.base_proxy, "base_236", 10),
        _base_or_extension(paths.extension_2026, "extension_2026", 20),
        _history(paths.history),
        _live(paths.live),
    ]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        ["issue_code", "match_idx", "source_priority"], kind="stable"
    )
    presence = (
        combined.assign(present=True)
        .pivot_table(
            index=["issue_code", "match_idx"],
            columns="source_name",
            values="present",
            aggfunc="any",
            fill_value=False,
        )
        .reset_index()
    )
    for source in ("base_236", "extension_2026", "history", "live"):
        if source not in presence:
            presence[source] = False
    descriptive = combined.drop_duplicates(["issue_code", "match_idx"], keep="first")
    descriptive = descriptive.drop(columns=["source_name", "source_priority"])
    result = descriptive.merge(presence, on=["issue_code", "match_idx"], validate="1:1")
    result["proxy_status"] = "UNRESOLVED_SOURCE_RECOVERY"
    result.loc[result.base_236, "proxy_status"] = "ACCEPTED_236"
    result.loc[~result.base_236 & result.extension_2026, "proxy_status"] = "AVAILABLE_EXTENSION"
    result["issue_sort"] = pd.to_numeric(result.issue_code, errors="raise")
    result = result.sort_values(["issue_sort", "match_idx"], kind="stable").drop(
        columns="issue_sort"
    )
    columns = [
        "issue_code",
        "match_idx",
        "provider_match_id",
        "kickoff_ts",
        "league",
        "home",
        "away",
        "native_handicap_line",
        "base_236",
        "extension_2026",
        "history",
        "live",
        "proxy_status",
    ]
    return result[columns].reset_index(drop=True)


def inventory_sha256(frame: pd.DataFrame) -> str:
    """Hash the complete denominator with deterministic CSV serialization."""

    payload = frame.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def inventory_summary(frame: pd.DataFrame) -> dict[str, int | str]:
    issue_status = frame.groupby("issue_code", sort=False)["proxy_status"].agg(
        lambda values: "ACCEPTED_236"
        if values.eq("ACCEPTED_236").all()
        else (
            "AVAILABLE_EXTENSION"
            if values.isin({"ACCEPTED_236", "AVAILABLE_EXTENSION"}).all()
            else "UNRESOLVED_SOURCE_RECOVERY"
        )
    )
    return {
        "inventory_sha256": inventory_sha256(frame),
        "known_issue_count": int(frame.issue_code.nunique()),
        "known_fixture_count": int(len(frame)),
        "accepted_236_issue_count": int(issue_status.eq("ACCEPTED_236").sum()),
        "extension_issue_count": int(issue_status.eq("AVAILABLE_EXTENSION").sum()),
        "unresolved_issue_count": int(issue_status.eq("UNRESOLVED_SOURCE_RECOVERY").sum()),
        "accepted_236_fixture_count": int(frame.base_236.sum()),
        "extension_fixture_count": int((~frame.base_236 & frame.extension_2026).sum()),
        "unresolved_fixture_count": int(
            (~frame.base_236 & ~frame.extension_2026).sum()
        ),
    }
