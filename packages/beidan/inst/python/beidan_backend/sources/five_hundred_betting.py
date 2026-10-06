"""Pure parsers for the 500.com 北京单场 betting pages and SP XML.

Two pages are covered:

* the issue fixture page (``trade.500.com/bjdc/index.php``) -> :func:`parse_issue_rows`
* the issue list ``<select>`` -> :func:`parse_issue_options`
* the live SP XML feeds -> :func:`parse_live_sp` and :func:`parse_live_market_sp`

Every function takes already-fetched ``str``/``bytes`` and returns plain rows;
nothing here performs I/O, reads the clock, or writes a database. ``fetched_at``
is an explicit parameter so callers own the observation timestamp.
"""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Iterable

DEFAULT_LIVE_PLAYIDS = (34, 40, 41, 42, 51)
MARKET_OUTCOMES: dict[int, tuple[str, tuple[tuple[str, str, str], ...]]] = {
    34: (
        "handicap_3way",
        (("3", "胜", "c1"), ("1", "平", "c3"), ("0", "负", "c5")),
    ),
    40: (
        "total_goals",
        tuple((code, code, f"c{1 + 2 * index}") for index, code in enumerate(("0", "1", "2", "3", "4", "5", "6", "7+"))),
    ),
    41: (
        "upper_lower_odd_even",
        (
            ("upper_odd", "上+单", "c1"),
            ("upper_even", "上+双", "c3"),
            ("lower_odd", "下+单", "c5"),
            ("lower_even", "下+双", "c7"),
        ),
    ),
    42: (
        "correct_score",
        tuple(
            (code, label, f"c{index}")
            for index, (code, label) in enumerate(
                (
                    ("home_other", "胜其他"),
                    ("1:0", "1:0"),
                    ("2:0", "2:0"),
                    ("2:1", "2:1"),
                    ("3:0", "3:0"),
                    ("3:1", "3:1"),
                    ("3:2", "3:2"),
                    ("4:0", "4:0"),
                    ("4:1", "4:1"),
                    ("4:2", "4:2"),
                    ("draw_other", "平其他"),
                    ("0:0", "0:0"),
                    ("1:1", "1:1"),
                    ("2:2", "2:2"),
                    ("3:3", "3:3"),
                    ("away_other", "负其他"),
                    ("0:1", "0:1"),
                    ("0:2", "0:2"),
                    ("1:2", "1:2"),
                    ("0:3", "0:3"),
                    ("1:3", "1:3"),
                    ("2:3", "2:3"),
                    ("0:4", "0:4"),
                    ("1:4", "1:4"),
                    ("2:4", "2:4"),
                ),
                start=1,
            )
        ),
    ),
    51: (
        "half_full",
        tuple(
            (code, label, f"c{1 + 2 * index}")
            for index, (code, label) in enumerate(
                (
                    ("3-3", "胜-胜"),
                    ("3-1", "胜-平"),
                    ("3-0", "胜-负"),
                    ("1-3", "平-胜"),
                    ("1-1", "平-平"),
                    ("1-0", "平-负"),
                    ("0-3", "负-胜"),
                    ("0-1", "负-平"),
                    ("0-0", "负-负"),
                )
            )
        ),
    ),
}

EXPECT_SELECT_RE = re.compile(r'<select[^>]+id="expect_select"[^>]*>(?P<body>.*?)</select>', re.S | re.I)
OPTION_RE = re.compile(r'<option\s+value="(?P<issue>\d+)"(?P<attrs>[^>]*)>(?P<label>.*?)</option>', re.S | re.I)
ROW_RE = re.compile(
    r'<tr\s+class="(?P<class>[^"]*\bvs_lines\b[^"]*)"(?P<attrs>[^>]*)>'
    r'(?P<body>.*?)</tr>',
    re.S | re.I,
)
VALUE_ATTR_RE = re.compile(r'value="(?P<value>\{[^}]*\})"', re.I)
FID_ATTR_RE = re.compile(r'fid="(?P<fid>-?\d+)"', re.I)
VALUE_PAIR_RE = re.compile(r"(\w+):(?:'([^']*)'|([^,}]+))")
SCORE_RE = re.compile(r'class="[^"]*\bred\b[^"]*\beng\b[^"]*"[^>]*>\s*([^<]+?)\s*</a>', re.S | re.I)
PJOZ_RE = re.compile(r'<span\s+class="[^"]*\bpjoz\b[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.S | re.I)
ASIAN_RE = re.compile(r'<span\s+class="asianhand"[^>]*>\s*([^<]*?)\s*</span>', re.S | re.I)
LABEL_BLOCK_RE = re.compile(
    r'value="(?P<label>胜|平|负)"(?P<block>.*?</label>)',
    re.S | re.I,
)
SP_VALUE_RE = re.compile(r'<span\s+class="[^"]*\bsp_value\b[^"]*"[^>]*>\s*([0-9.]+)\s*</span>', re.S | re.I)

RESULT_CODE_BY_LABEL = {"胜": "3", "平": "1", "负": "0"}
SCORE_PARTS_RE = re.compile(r"^\s*(\d+)\s*[:：]\s*(\d+)\s*$")


def clean_text(raw: str | None) -> str:
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def as_float(raw: object) -> float | None:
    if raw is None:
        return None
    text = clean_text(str(raw))
    if not text or text == "--":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def as_int(raw: object) -> int | None:
    if raw is None:
        return None
    text = clean_text(str(raw))
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def decode_html(data: bytes) -> str:
    return data.decode("gb18030", errors="ignore")


def issue_year(issue: str) -> int | None:
    if len(issue) < 2 or not issue[:2].isdigit():
        return None
    return 2000 + int(issue[:2])


def parse_issue_options(text: str) -> list[dict[str, object]]:
    m = EXPECT_SELECT_RE.search(text)
    if not m:
        return []
    out: list[dict[str, object]] = []
    for idx, opt in enumerate(OPTION_RE.finditer(m.group("body"))):
        issue = opt.group("issue")
        if len(issue) < 5:
            continue
        attrs = opt.group("attrs")
        label = clean_text(re.sub(r"<.*?>", "", opt.group("label")))
        out.append(
            {
                "issue": issue,
                "ordinal": idx,
                "label": label,
                "is_selected": 1 if "selected" in attrs.lower() else 0,
                "is_current": 1 if "当前期" in label else 0,
                "year": issue_year(issue),
            }
        )
    return out


def parse_value_object(raw: str) -> dict[str, str]:
    raw = html.unescape(raw)
    out: dict[str, str] = {}
    for key, quoted, bare in VALUE_PAIR_RE.findall(raw):
        out[key] = clean_text(quoted if quoted != "" else bare)
    return out


def parse_label_sp(body: str) -> dict[str, float | None]:
    out = {"胜": None, "平": None, "负": None}
    for m in LABEL_BLOCK_RE.finditer(body):
        sp_m = SP_VALUE_RE.search(m.group("block"))
        out[m.group("label")] = as_float(sp_m.group(1)) if sp_m else None
    return out


def infer_result_label(score: str, handicap_line: float | None) -> str | None:
    if handicap_line is None:
        return None
    m = SCORE_PARTS_RE.match(score)
    if not m:
        return None
    home_goals = int(m.group(1))
    away_goals = int(m.group(2))
    adjusted_home = home_goals + handicap_line
    if adjusted_home > away_goals:
        return "胜"
    if adjusted_home < away_goals:
        return "负"
    return "平"


def parse_issue_rows(issue: str, text: str, *, fetched_at: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for m in ROW_RE.finditer(text):
        value_match = VALUE_ATTR_RE.search(m.group("attrs"))
        fid_match = FID_ATTR_RE.search(m.group("attrs"))
        if value_match is None or fid_match is None:
            continue
        fid = as_int(fid_match.group("fid"))
        # Old 6-digit pages retain canceled placeholders (fid=-1); never let
        # a row regex spill into the next valid row to compensate for them.
        if fid is None or fid <= 0:
            continue
        raw_value = html.unescape(value_match.group("value"))
        info = parse_value_object(raw_value)
        body = m.group("body")
        pjoz = [as_float(x) for x in PJOZ_RE.findall(body)]
        pjoz = (pjoz + [None, None, None])[:3]
        asian = ASIAN_RE.search(body)
        score_m = SCORE_RE.search(body)
        score = clean_text(score_m.group(1)) if score_m else ""
        label_sp = parse_label_sp(body)
        visible_sp = [label_sp["胜"], label_sp["平"], label_sp["负"]]
        winning_labels = [label for label, sp in label_sp.items() if sp is not None]
        handicap_line = as_float(info.get("rangqiuNum"))
        inferred_label = infer_result_label(score, handicap_line)
        result_label = winning_labels[0] if score and len(winning_labels) == 1 else inferred_label
        winning_sp = label_sp[result_label] if result_label else None
        raw_row = m.group(0)
        rows.append(
            {
                "issue": issue,
                "match_idx": as_int(info.get("index")),
                "fid": fid,
                "league": info.get("leagueName", ""),
                "home": info.get("homeTeam", ""),
                "away": info.get("guestTeam", ""),
                "end_time": info.get("endTime", ""),
                "schedule_date": info.get("scheduleDate", ""),
                "handicap_line": handicap_line,
                "disabled": info.get("disabled", ""),
                "home_rank": as_int(info.get("homeTeamRank")),
                "away_rank": as_int(info.get("guestTeamRank")),
                "bg_color": info.get("bgColor", ""),
                "score": score,
                "result_label": result_label,
                "result_code": RESULT_CODE_BY_LABEL.get(result_label or ""),
                "winning_sp": winning_sp,
                "sp_home": visible_sp[0],
                "sp_draw": visible_sp[1],
                "sp_away": visible_sp[2],
                "avg_odds_home": pjoz[0],
                "avg_odds_draw": pjoz[1],
                "avg_odds_away": pjoz[2],
                "asian_handicap": clean_text(asian.group(1)) if asian else "",
                "raw_value": raw_value,
                "raw_row_hash": hashlib.sha1(raw_row.encode("utf-8", errors="ignore")).hexdigest(),
                "fetched_at": fetched_at,
            }
        )
    return rows


def parse_live_sp(issue: str, playid: int, data: bytes, fetched_at: str) -> tuple[str | None, list[dict[str, object]]]:
    root = ET.fromstring(decode_html(data))
    source_updatetime = root.attrib.get("updatetime")
    rows: list[dict[str, object]] = []
    for child in list(root):
        name = child.tag
        if not name.startswith("w"):
            continue
        try:
            row_idx = int(name[1:])
        except ValueError:
            continue
        raw_node = ET.tostring(child, encoding="unicode")
        rows.append(
            {
                "issue": issue,
                "playid": playid,
                "fetched_at": fetched_at,
                "source_updatetime": source_updatetime,
                "row_idx": row_idx,
                "home": child.attrib.get("h", ""),
                "away": child.attrib.get("a", ""),
                "league": child.attrib.get("gn", ""),
                "handicap_line": as_float(child.attrib.get("r")),
                "sp_home": as_float(child.attrib.get("c1")),
                "sp_draw": as_float(child.attrib.get("c3")),
                "sp_away": as_float(child.attrib.get("c5")),
                "raw_node": raw_node,
            }
        )
    return source_updatetime, rows


def parse_live_market_sp(
    issue: str,
    playid: int,
    data: bytes,
    fetched_at: str,
) -> tuple[str | None, list[dict[str, object]]]:
    market = MARKET_OUTCOMES.get(playid)
    if market is None:
        raise ValueError(f"unsupported normalized BJDC playid: {playid}")
    market_key, outcomes = market
    root = ET.fromstring(decode_html(data))
    source_updatetime = root.attrib.get("updatetime")
    rows: list[dict[str, object]] = []
    for child in list(root):
        if not child.tag.startswith("w"):
            continue
        try:
            row_idx = int(child.tag[1:])
        except ValueError:
            continue
        raw_node = ET.tostring(child, encoding="unicode")
        for outcome_code, outcome_label, attribute in outcomes:
            rows.append(
                {
                    "issue": issue,
                    "playid": playid,
                    "market_key": market_key,
                    "fetched_at": fetched_at,
                    "source_updatetime": source_updatetime,
                    "row_idx": row_idx,
                    "home": child.attrib.get("h", ""),
                    "away": child.attrib.get("a", ""),
                    "league": child.attrib.get("gn", ""),
                    "outcome_code": outcome_code,
                    "outcome_label": outcome_label,
                    "sp": as_float(child.attrib.get(attribute)),
                    "source_attribute": attribute,
                    "raw_node": raw_node,
                }
            )
    return source_updatetime, rows


def parse_playids(values: Iterable[object] | None) -> tuple[int, ...]:
    if not values:
        return DEFAULT_LIVE_PLAYIDS
    playids: list[int] = []
    for raw in values:
        for part in str(raw).replace("，", ",").split(","):
            if not part.strip():
                continue
            playid = int(part.strip())
            if playid not in MARKET_OUTCOMES:
                raise ValueError(f"unsupported BJDC playid: {playid}")
            if playid not in playids:
                playids.append(playid)
    return tuple(playids)
