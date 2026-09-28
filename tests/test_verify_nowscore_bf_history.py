"""History verification must not convert reference vectors into settlements."""
import pytest

from scripts.verify_nowscore_bf_history import TYPEID_LABELS, parse_history, verify


TARGET = {"issue": "26082", "slot": 23, "expected_option": "负其他", "summary_sp_raw": "56.7144"}


def page(vectors):
    header = "".join(f"<td>{label}</td>" for label in (*TYPEID_LABELS[8], "变化时间"))
    body = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in [*v, "08-07 10:09"]) + "</tr>" for v in vectors)
    return f"<title>Sp值变化表 (26082期第23场) -- 捷报比分</title><table><tr>{header}</tr>{body}</table>".encode()


def vector(option="负其他", sp="56.71"):
    return [sp if x == option else "0" for x in TYPEID_LABELS[8]]


def test_zero_cells_are_retained_and_rounded_agreement():
    rows = parse_history(page([vector()]), "26082", 23)
    assert rows[0]["vector_raw"].count("0") == 24
    r = verify(TARGET, rows)
    assert r["classification"] == "历史页支持（SP按两位小数一致）"
    assert not r["data_changed"] and not r["official_notice_verified"]


def test_empty_history_not_evidence():
    assert verify(TARGET, parse_history(page([]), "26082", 23))["classification"] == "无历史记录"


@pytest.mark.parametrize("v,expected", [
    (["1"] * 25, "待核查：最新行为全一向量"),
    (["3"] * 25, "无最新单选结算证据"),
    (["0"] * 25, "无最新单选结算证据"),
    (vector("胜其他"), "冲突：历史选项与比分不符"),
    (vector(sp="56.72"), "冲突：历史SP与汇总SP不符"),
    (vector(sp="1"), "待核查：单选SP为1"),
])
def test_classifications(v, expected):
    assert verify(TARGET, parse_history(page([v]), "26082", 23))["classification"] == expected


def test_never_cherry_pick_an_older_matching_vector():
    rows = parse_history(page([["3"] * 25, vector()]), "26082", 23)
    assert verify(TARGET, rows)["classification"] == "无最新单选结算证据"
    rows = parse_history(page([vector(), vector(sp="57.00")]), "26082", 23)
    assert verify(TARGET, rows)["classification"] == "待核查：多个不同单选历史向量"


@pytest.mark.parametrize("raw", ["", "NaN", "Infinity", "-1", "0.5"])
def test_malformed_values_fail_closed(raw):
    with pytest.raises(ValueError):
        parse_history(page([vector(sp=raw)]), "26082", 23)


def test_wrong_identity_and_option_domain():
    with pytest.raises(ValueError, match="identity"):
        parse_history(page([]), "26082", 24)
    with pytest.raises(ValueError, match="domain"):
        parse_history(page([]).replace("负其他".encode(), "负其它".encode()), "26082", 23)
