from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settlement_halftime_evidence import EXTRACTORS, corroborate  # noqa: E402


FIXTURE = {"home": "甲队", "away": "乙队", "date": "2021-08-06",
           "ft_home": 2, "ft_away": 3, "away_en": "Cork City"}

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
