"""Load + dedupe + de-vig + feature-engineer 北单 history into per-option rows.

Produces a long-format DataFrame: one row per (match, option) where
option in {3, 1, 0}.  Each row carries:
  - implied_prob_prop / implied_prob_pow: de-vigged prob from avg_eu odds
  - did_win: 1/0
  - features: league_tier, handicap_class, prob_bucket, option_type,
    option_strength_relative, issue (期号), winning_sp (only valid if did_win=1)
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Paths

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(REPO_ROOT, "data", "beidan_history.db")
USER_CSV_PATH = os.path.join(REPO_ROOT, "data", "raw", "beidan_history_user.csv")


# ---------------------------------------------------------------------------
# League-tier mapping

TOP5 = {"英超", "西甲", "意甲", "德甲", "法甲"}
LOWER_EU = {
    "英冠", "英甲", "英乙", "英锦", "英足总", "英联杯",
    "西乙", "意乙", "德乙", "德丙", "法乙",
    "荷甲", "荷乙", "葡超", "葡甲", "比甲", "比乙",
    "苏超", "苏冠", "苏甲", "苏乙", "瑞典超", "瑞典甲", "瑞超", "瑞甲",
    "挪超", "挪甲", "丹超", "丹甲", "芬超", "芬甲",
    "奥甲", "奥乙", "瑞士超", "瑞士甲", "瑞士杯",
    "希腊超", "土超", "土甲", "波兰甲", "捷克甲", "俄超", "俄甲",
    "罗甲", "塞超", "克甲", "匈甲", "斯洛超", "斯伐超",
    "冰超", "爱超", "爱甲", "威超", "北爱超",
    "欧冠", "欧联", "欧协", "欧国联", "欧预", "欧青预", "欧青赛",
}
SOUTH_AM = {
    "巴甲", "巴乙", "阿超", "阿乙", "智甲", "智乙", "哥伦甲",
    "秘鲁甲", "厄瓜甲", "玻利甲", "乌拉甲", "巴拉甲", "委内甲",
    "南美杯", "南美解放者杯", "解放者", "南美俱乐部杯",
}
ASIAN = {
    "日职", "日职乙", "日联赛杯", "日联", "日皇杯", "亚冠", "亚预",
    "韩K联", "韩职", "韩K2", "韩K3",
    "中超", "中甲", "中乙", "足协杯", "中足协",
    "澳超", "澳总杯",
    "印尼超", "印度超", "越南超", "泰超", "马来超", "新加坡",
    "沙特超", "卡塔超", "阿联超", "伊朗超", "约旦超",
}


def classify_league(league: Optional[str]) -> str:
    if league is None or (isinstance(league, float) and np.isnan(league)):
        return "Other"
    s = str(league).strip()
    if s in TOP5:
        return "Top5EU"
    if s in LOWER_EU:
        return "LowerEU"
    if s in SOUTH_AM:
        return "SouthAm"
    if s in ASIAN:
        return "Asian"
    return "Other"


# Competition-type buckets — orthogonal to league_tier. "杯" matches cup
# competitions (Champions League, FA Cup etc.); intl-keywords match
# inter-national qualifications and friendlies which behave differently
# (rotated squads, lower predictability). See `scripts/niche_split_analysis.py`.
_INTL_KEYWORDS = ("友谊", "预选", "锦标")


def classify_comp_type(league) -> str:
    """Return one of {'cup', 'league', 'intl'} for a 北单 league name."""
    if league is None:
        return "league"
    try:
        if isinstance(league, float) and not np.isfinite(league):
            return "league"
    except TypeError:
        pass
    s = str(league)
    if "杯" in s:
        return "cup"
    for kw in _INTL_KEYWORDS:
        if kw in s:
            return "intl"
    return "league"


def classify_handicap(h) -> str:
    """Bucket handicap into {h=0, |h|=1, |h|>=2}."""
    if h is None:
        return "h_unknown"
    try:
        v = float(h)
    except (TypeError, ValueError):
        return "h_unknown"
    if np.isnan(v):
        return "h_unknown"
    a = abs(v)
    if a < 0.5:
        return "h0"
    if a < 1.5:
        return "h1"
    return "h2plus"


# ---------------------------------------------------------------------------
# De-vig helpers

def devig_proportional(o_home: float, o_draw: float, o_away: float):
    """Proportional de-vig: p_i = (1/o_i) / sum(1/o)."""
    inv = np.array([1.0 / o_home, 1.0 / o_draw, 1.0 / o_away])
    s = inv.sum()
    if s <= 0 or not np.isfinite(s):
        return np.array([np.nan, np.nan, np.nan])
    return inv / s


def devig_power(o_home: float, o_draw: float, o_away: float, tol: float = 1e-8):
    """Power de-vig: find k such that sum((1/o_i)^k) = 1.

    More accurate than proportional for biased books, especially for
    favorites (compresses extreme implied probs less).
    """
    inv = np.array([1.0 / o_home, 1.0 / o_draw, 1.0 / o_away], dtype=float)
    if not np.all(np.isfinite(inv)) or np.any(inv <= 0):
        return np.array([np.nan, np.nan, np.nan])
    # Bisection on k in (0, 5]
    lo, hi = 0.01, 5.0
    for _ in range(60):
        k = 0.5 * (lo + hi)
        s = float(np.sum(inv ** k))
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = k  # need larger k to shrink
        else:
            hi = k
    return inv ** k


# ---------------------------------------------------------------------------
# Data loading

def _load_db() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            """
            SELECT issue, match_idx, league, handicap_line AS handicap,
                   result_code AS result_norm, winning_sp,
                   avg_eu_home, avg_eu_draw, avg_eu_away
            FROM historical_matches
            WHERE avg_eu_home IS NOT NULL
              AND avg_eu_draw IS NOT NULL
              AND avg_eu_away IS NOT NULL
              AND result_code IS NOT NULL
            """,
            con,
        )
    finally:
        con.close()
    df["source"] = "db"
    return df


def _load_user_csv() -> pd.DataFrame:
    if not os.path.exists(USER_CSV_PATH):
        return pd.DataFrame()
    df = pd.read_csv(USER_CSV_PATH)
    df = df.rename(
        columns={
            "expect": "issue",
            "match_no": "match_idx",
            "result": "result_norm",
            "sp": "winning_sp",
            "avg_odds_home": "avg_eu_home",
            "avg_odds_draw": "avg_eu_draw",
            "avg_odds_away": "avg_eu_away",
        }
    )
    keep = [
        "issue", "match_idx", "league", "handicap", "result_norm", "winning_sp",
        "avg_eu_home", "avg_eu_draw", "avg_eu_away",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["issue"] = df["issue"].astype(str)
    df["match_idx"] = pd.to_numeric(df["match_idx"], errors="coerce")
    df["result_norm"] = df["result_norm"].astype(str)
    df["source"] = "user"
    return df


def load_matches(devig: str = "proportional") -> pd.DataFrame:
    """Load matches from DB and user CSV, dedupe on (issue, match_idx).

    Returns a wide DataFrame (one row per match) with columns:
      issue, match_idx, league, handicap, result_norm, winning_sp,
      avg_eu_home/draw/away, p_home, p_draw, p_away, league_tier,
      handicap_class, source
    """
    db = _load_db()
    user = _load_user_csv()
    if db.empty and user.empty:
        return pd.DataFrame()
    df = pd.concat([db, user], ignore_index=True)
    # Normalize issue to string
    df["issue"] = df["issue"].astype(str).str.strip()
    df["result_norm"] = df["result_norm"].astype(str).str.strip()
    # Dedupe — DB takes precedence
    df = df.drop_duplicates(subset=["issue", "match_idx"], keep="first").reset_index(drop=True)
    # Coerce numeric
    for col in ["avg_eu_home", "avg_eu_draw", "avg_eu_away", "winning_sp", "handicap"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["avg_eu_home", "avg_eu_draw", "avg_eu_away"]).reset_index(drop=True)
    # Restrict to reasonable odds
    for col in ["avg_eu_home", "avg_eu_draw", "avg_eu_away"]:
        df = df[df[col] > 1.0]
    df = df.reset_index(drop=True)

    # De-vig
    devig_fn = devig_power if devig == "power" else devig_proportional
    probs = np.vstack([
        devig_fn(h, d, a)
        for h, d, a in zip(df["avg_eu_home"], df["avg_eu_draw"], df["avg_eu_away"])
    ])
    df["p_home"] = probs[:, 0]
    df["p_draw"] = probs[:, 1]
    df["p_away"] = probs[:, 2]

    df = df.dropna(subset=["p_home", "p_draw", "p_away"]).reset_index(drop=True)
    df["league_tier"] = df["league"].map(classify_league)
    df["handicap_class"] = df["handicap"].map(classify_handicap)
    return df


def to_long(df: pd.DataFrame) -> pd.DataFrame:
    """Explode each match into 3 rows (one per option ∈ {3, 1, 0})."""
    if df.empty:
        return df
    rows = []
    for _, r in df.iterrows():
        opts = [
            ("3", r["p_home"], r["avg_eu_home"]),
            ("1", r["p_draw"], r["avg_eu_draw"]),
            ("0", r["p_away"], r["avg_eu_away"]),
        ]
        # Determine relative strength: favorite=lowest implied (highest prob)
        ps = [p for _, p, _ in opts]
        order = np.argsort(ps)  # ascending probs
        # order[2] = highest p = favorite
        strength = {order[2]: "fav", order[1]: "mid", order[0]: "long"}
        for i, (opt, p, eu) in enumerate(opts):
            rows.append({
                "issue": r["issue"],
                "match_idx": r["match_idx"],
                "league_tier": r["league_tier"],
                "handicap_class": r["handicap_class"],
                "option_type": opt,
                "implied_prob": p,
                "eu_odds": eu,
                "did_win": int(r["result_norm"] == opt),
                "winning_sp": r["winning_sp"] if r["result_norm"] == opt else np.nan,
                "option_strength": strength[i],
            })
    long = pd.DataFrame(rows)
    long["prob_bucket"] = pd.cut(
        long["implied_prob"],
        bins=[0.0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.70, 0.85, 1.0],
        labels=["<.15", ".15-.25", ".25-.35", ".35-.45",
                ".45-.55", ".55-.70", ".70-.85", ">.85"],
        include_lowest=True,
    ).astype(str)
    return long


def train_test_split_by_issue(long_df: pd.DataFrame, train_frac: float = 100 / 150):
    """Split observations by issue: earlier issues => train, later => test."""
    issues = sorted(long_df["issue"].unique())
    cut = int(round(len(issues) * train_frac))
    train_issues = set(issues[:cut])
    test_issues = set(issues[cut:])
    train = long_df[long_df["issue"].isin(train_issues)].reset_index(drop=True)
    test = long_df[long_df["issue"].isin(test_issues)].reset_index(drop=True)
    return train, test
