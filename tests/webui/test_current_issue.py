"""A generated plan must never mix legs from different 北单 issues.

`select_current_issue` picks the single issue a plan should be built from: the
issue with the most open matches (the slate we actually have), tie-broken
toward the larger/newer issue string so leftover stragglers from a previous
issue never win.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.webui.services import select_current_issue


@dataclass
class _Snap:
    issue: str


def test_single_issue_returned():
    snaps = [_Snap("26065"), _Snap("26065")]
    assert select_current_issue(snaps) == "26065"


def test_modal_issue_wins_over_straggler():
    # 3 matches from 26065, 1 leftover from the previous issue 26064.
    snaps = [_Snap("26065"), _Snap("26064"), _Snap("26065"), _Snap("26065")]
    assert select_current_issue(snaps) == "26065"


def test_tie_breaks_toward_newer_issue():
    snaps = [_Snap("26064"), _Snap("26065")]
    assert select_current_issue(snaps) == "26065"


def test_empty_returns_none():
    assert select_current_issue([]) is None


def test_ignores_blank_issue():
    snaps = [_Snap(""), _Snap("26065"), _Snap(None)]
    assert select_current_issue(snaps) == "26065"
