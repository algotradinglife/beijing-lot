from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settlement_halftime_evidence import (  # noqa: E402
    EXTRACTORS,
    HALF_FULL_EXTRACTORS,
    corroborate,
    corroborate_half_full,
    half_full_option,
)

# The module's own registries, so an extractor that is added without a preserved page fails the
# coverage example below rather than going unnoticed.
_REAL_EXTRACTORS = dict(EXTRACTORS)
_REAL_EXTRACTORS.update(HALF_FULL_EXTRACTORS)


FIXTURE = {"home": "甲队", "away": "乙队", "date": "2021-08-06", "slot": 90,
           "ft_home": 2, "ft_away": 3, "away_en": "Cork City"}

OKOOO_LIVECENTER = ('<table><tr><td>90</td><td>爱甲</td><td>08-07 02:45</td><td>完</td>'
                    '<td>[2] 甲队 (-1)</td><td>2 - 3</td><td class="dzname">[9] 乙队'
                    '<td><span class="font_red">2-2</span></td></td>'
                    '<td class="weather_icon"></td><td class="blockbox">4.22 3.40 2.12</td>'
                    '<td class="ctrl_result">0</td></tr></table>').encode("gbk")

OKOOO_HALF_FULL = ('<table><tr><td>90 爱甲</td><td>02:40</td><td>甲队 乙队</td><td>16.07</td>'
                   '<td>投注区</td><td>全</td><td></td><td>2-3</td><td>1-0</td>'
                   '<td>析</td></tr></table>').encode("gbk")

GSA = b"""<html><body><div>Full Time 2 - 3 Cork City FC</div>
<div>1st Half 2 - 2 Killian Brouder ( 2 - 2 ) 41'</div></body></html>"""

SCORE24 = b"""<html><body><table>
<tr><td>06.08.21</td><td>Galway</td><td>Cork City</td><td class="score"><b>L 2:3 (2:2)</b></td></tr>
<tr><td>12.05.17</td><td>Galway</td><td>Cork City</td><td class="score"><b>D 1:1 (0:0)</b></td></tr>
</table></body></html>"""

SPORTSMOLE_INLINE = b"""<html><body><div>Brugge Aug 6, 2021 7.45pm 1 1 HT : 1 0 FT Cercle Brugge</div>
<div>22 Cercle Brugge Jan 28, 2021 5.45pm 1 2 HT : 1 1 FT Brugge</div></body></html>"""

SPORTSMOLE_BRACKETED = b"""<html><body><div>Stadio Rigamonti Ceppi Lecco 1 - 1 Cittadella
Crociata (44') Parigini (16') FT (HT: 1-1) Negro (26')</div></body></html>"""

FOOTBALLCRITIC = b"""<html><body><div>Date: Aug 6, 2021 18:45 Half Time Score: 1-0
Full Time Score: 1-1 Referees: D. Van Esch</div></body></html>"""

TRANSFERMARKT = b"""<html><body><div>31. Matchday | Mon, 01/04/24 | 3:00 PM 1:1 ( 1: 1) Rigamonti-Ceppi</div>
<div>Lecco - Cittadella 1:1 ( 1: 1)</div><div>form 11 1:1 2:0 1:0</div></body></html>"""


def test_globalsportsarchive_reads_the_half_time_heading() -> None:
    claim = EXTRACTORS["globalsportsarchive"](GSA, FIXTURE)
    assert claim == {"home": 2, "away": 2, "ft_home": 2, "ft_away": 3}


def test_24score_reads_only_the_row_for_the_fixture_date() -> None:
    claim = EXTRACTORS["24score"](SCORE24, FIXTURE)
    assert claim == {"home": 2, "away": 2, "ft_home": 2, "ft_away": 3}


def test_sportsmole_reads_the_inline_form_from_the_fixture_window() -> None:
    fixture = {"home": "布鲁日", "away": "色格拉", "date": "2021-08-06",
               "ft_home": 1, "ft_away": 1, "away_en": "Cercle Brugge"}
    claim = EXTRACTORS["sportsmole"](SPORTSMOLE_INLINE, fixture)
    assert claim == {"home": 1, "away": 0, "ft_home": 1, "ft_away": 1}


def test_sportsmole_reads_the_bracketed_form_beside_the_scoreline() -> None:
    fixture = {"home": "莱科", "away": "奇塔代拉", "date": "2024-04-01",
               "ft_home": 1, "ft_away": 1, "away_en": "Cittadella"}
    claim = EXTRACTORS["sportsmole"](SPORTSMOLE_BRACKETED, fixture)
    assert claim == {"home": 1, "away": 1, "ft_home": 1, "ft_away": 1}


def test_footballcritic_reads_both_labelled_scores() -> None:
    fixture = {"home": "布鲁日", "away": "色格拉", "date": "2021-08-06",
               "ft_home": 1, "ft_away": 1, "away_en": "Cercle Brugge"}
    claim = EXTRACTORS["footballcritic"](FOOTBALLCRITIC, fixture)
    assert claim == {"home": 1, "away": 0, "ft_home": 1, "ft_away": 1}


def test_transfermarkt_reads_the_parenthesised_half_time() -> None:
    fixture = {"home": "莱科", "away": "奇塔代拉", "date": "2024-04-01",
               "ft_home": 1, "ft_away": 1, "away_en": "Cittadella"}
    claim = EXTRACTORS["transfermarkt"](TRANSFERMARKT, fixture)
    assert claim == {"home": 1, "away": 1, "ft_home": 1, "ft_away": 1}


@pytest.mark.parametrize("source", sorted(EXTRACTORS))
def test_every_extractor_fails_closed_on_an_unrelated_page(source: str) -> None:
    with pytest.raises(ValueError):
        EXTRACTORS[source](b"<html><body>nothing here</body></html>", FIXTURE)


@pytest.mark.parametrize("source", sorted(EXTRACTORS))
def test_every_extractor_rejects_a_page_whose_full_time_is_not_the_fixture(source: str) -> None:
    other = dict(FIXTURE, ft_home=9, ft_away=9)
    with pytest.raises(ValueError):
        EXTRACTORS[source]({"globalsportsarchive": GSA, "24score": SCORE24}.get(source, b"<html></html>"), other)


def test_corroborate_accepts_two_agreeing_sources() -> None:
    assert corroborate({"a": {"home": 2, "away": 2}, "b": {"home": 2, "away": 2}}) == (2, 2)


def test_corroborate_refuses_a_single_source() -> None:
    with pytest.raises(ValueError, match="need >= 2 independent sources"):
        corroborate({"a": {"home": 2, "away": 2}})


def test_corroborate_refuses_disagreement_rather_than_voting() -> None:
    with pytest.raises(ValueError, match="disagree on half time"):
        corroborate({"a": {"home": 2, "away": 2}, "b": {"home": 2, "away": 1}})


def test_okooo_livecenter_reads_the_half_time_from_the_red_cell() -> None:
    assert EXTRACTORS["okooo"](OKOOO_LIVECENTER, FIXTURE) == {
        "home": 2, "away": 2, "ft_home": 2, "ft_away": 3}


def test_okooo_livecenter_rejects_a_page_without_the_slot() -> None:
    with pytest.raises(ValueError, match="exactly one row for slot 91"):
        EXTRACTORS["okooo"](OKOOO_LIVECENTER, dict(FIXTURE, slot=91))


def test_okooo_half_full_reads_the_settlement_code_and_its_sp() -> None:
    assert HALF_FULL_EXTRACTORS["okooo_half_full"](OKOOO_HALF_FULL, FIXTURE) == {
        "option": "平-负", "sp": 16.07, "ft_home": 2, "ft_away": 3}


def test_okooo_half_full_rejects_a_page_whose_full_time_is_not_the_fixture() -> None:
    with pytest.raises(ValueError, match="not the expected fixture"):
        HALF_FULL_EXTRACTORS["okooo_half_full"](OKOOO_HALF_FULL,
                                                dict(FIXTURE, ft_home=1, ft_away=1))


@pytest.mark.parametrize("source", sorted(HALF_FULL_EXTRACTORS))
def test_every_half_full_extractor_fails_closed_on_an_unrelated_page(source: str) -> None:
    with pytest.raises(ValueError):
        HALF_FULL_EXTRACTORS[source](b"<html><body>nothing here</body></html>", FIXTURE)


def test_half_full_option_matches_the_build_derivation() -> None:
    assert half_full_option((2, 2), (2, 3)) == "平-负"
    assert half_full_option((1, 0), (1, 1)) == "胜-平"
    assert half_full_option((1, 1), (1, 1)) == "平-平"
    assert half_full_option((0, 1), (3, 1)) == "负-胜"


def test_corroborate_half_full_accepts_the_option_the_corrected_half_time_implies() -> None:
    settled = corroborate_half_full((2, 2), (2, 3),
                                    {"okooo_half_full": {"option": "平-负", "sp": 16.07}})
    assert settled == {"option": "平-负", "sp": 16.07}


def test_corroborate_half_full_refuses_the_option_the_source_inherited_from_its_error() -> None:
    with pytest.raises(ValueError, match="disagrees with the corrected half time"):
        corroborate_half_full((2, 2), (2, 3),
                              {"okooo_half_full": {"option": "胜-负", "sp": 16.07}})


def test_corroborate_half_full_refuses_a_missing_sp_rather_than_guessing() -> None:
    with pytest.raises(ValueError, match="settlement SP"):
        corroborate_half_full((2, 2), (2, 3),
                              {"okooo_half_full": {"option": "平-负", "sp": None}})


def test_corroborate_half_full_refuses_disagreeing_sps() -> None:
    with pytest.raises(ValueError, match="settlement SP"):
        corroborate_half_full((2, 2), (2, 3),
                              {"a": {"option": "平-负", "sp": 16.07},
                               "b": {"option": "平-负", "sp": 15.0}})


def test_corroborate_half_full_refuses_without_any_source() -> None:
    with pytest.raises(ValueError, match="at least one half/full settlement source"):
        corroborate_half_full((2, 2), (2, 3), {})


# --- Real pages the sources actually served ------------------------------------------------
#
# Every extractor above is otherwise only exercised against markup this file builds, which is
# how the Okooo parser stayed green while it destroyed the team names: a page that is only ever
# seen as the author's idea of it proves nothing about the source. These cases drive each
# extractor with the bytes preserved during the #479 corroboration, and the identity that comes
# with them is the record of the change those pages authorized.

_FIXTURES = Path(__file__).parent / "fixtures" / "halftime_evidence"
_CASE_DATA = json.loads((_FIXTURES / "cases.json").read_text(encoding="utf-8"))
_CASES = _CASE_DATA["cases"]
def _page(case: dict) -> bytes:
    path = (_FIXTURES / case["page"]).resolve()
    assert path.exists(), f"missing preserved page {case['page']}"
    return gzip.open(path, "rb").read()


def test_real_page_evidence_covers_every_extractor() -> None:
    """An extractor added without preserved page bytes should fail here, not pass unnoticed."""
    covered = {case["source_id"] for case in _CASES}
    assert covered == set(_REAL_EXTRACTORS), sorted(set(_REAL_EXTRACTORS) - covered)


@pytest.mark.parametrize("case", _CASES, ids=lambda c: f"{c['source_id']}-{c['issue']}-{c['slot']}")
def test_extractor_reads_the_half_time_from_the_preserved_page(case: dict) -> None:
    payload = _page(case)
    if case.get("page_sha256"):
        assert hashlib.sha256(payload).hexdigest() == case["page_sha256"]
    got = _REAL_EXTRACTORS[case["source_id"]](payload, case["fixture"])
    if case["source_id"] in HALF_FULL_EXTRACTORS:
        # the half-full board answers with the settlement option and its price, not a score
        assert got["option"] == case["expected_option"]
        assert got["sp"] == pytest.approx(case["sp"])
        assert (got["ft_home"], got["ft_away"]) == (case["fixture"]["ft_home"], case["fixture"]["ft_away"])
    else:
        assert (got["home"], got["away"]) == tuple(int(p) for p in case["expected_half"].split("-"))
        assert (got["ft_home"], got["ft_away"]) == (case["fixture"]["ft_home"], case["fixture"]["ft_away"])


def _page_text(payload: bytes) -> str:
    """Decode a preserved page with the charset it declares, not with a guess.

    Okooo serves GB2312: decoding its pages as UTF-8 loses the Chinese names that identify the
    fixture, which is the same substitution that made the Okooo parser produce unreadable teams.
    """
    declared = re.search(rb'charset=["\']?([\w-]+)', payload[:4096])
    for encoding in ([declared.group(1).decode("ascii")] if declared else []) + ["utf-8", "gb18030"]:
        try:
            return payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise AssertionError("no encoding decodes this page")


@pytest.mark.parametrize("case", _CASES, ids=lambda c: f"{c['source_id']}-{c['issue']}-{c['slot']}")
def test_the_preserved_page_is_that_fixture(case: dict) -> None:
    """A page that is not this fixture's must not be read as evidence for it."""
    token = case["identity_token"]
    assert token, f"{case['page']} records no identity token"
    assert token in _page_text(_page(case)), (
        f"{case['page']} does not mention {token}, so it is not this fixture's page")


@pytest.mark.parametrize("case", _CASES, ids=lambda c: f"{c['source_id']}-{c['issue']}-{c['slot']}")
def test_the_preserved_page_still_fails_closed_on_another_fixture(case: dict) -> None:
    """The real page passed through the gate must reject a different fixture's score."""
    payload = _page(case)
    other = dict(case["fixture"], ft_home=case["fixture"]["ft_home"] + 1)
    with pytest.raises(ValueError):
        _REAL_EXTRACTORS[case["source_id"]](payload, other)
