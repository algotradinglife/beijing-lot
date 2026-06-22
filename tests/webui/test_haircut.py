"""SP-drift haircut into live EV/sizing — opt-in (default OFF).

When enabled, each leg's SP is shifted to its expected settlement value via the
frozen GATE-1 band map before EV/Kelly sizing, so longshot bands (which drift
down hard) get a smaller / zero stake. Default OFF pending forward-test verdict.
"""
from __future__ import annotations

from src.phase5a.data_loader import LiveSnapshot
from src.webui.services import maybe_haircut_snapshots


def _snap(sp_3, sp_1, sp_0):
    return LiveSnapshot(match_id="m", issue="1", match_idx=1, league="x",
                        kickoff_ts="t", home=None, away=None, handicap_line=None,
                        sp_3=sp_3, sp_1=sp_1, sp_0=sp_0, snapshot_ts=None)


def test_disabled_is_identity():
    snaps = [_snap(10.0, 4.0, 3.0)]
    out = maybe_haircut_snapshots(snaps, enabled=False)
    assert out is snaps  # untouched


def test_enabled_shrinks_longshot_sp():
    snaps = [_snap(10.0, 4.0, 3.0)]
    out = maybe_haircut_snapshots(snaps, enabled=True)
    # >8 band drifts -0.81 -> 10 * 0.19 = 1.9
    assert round(out[0].sp_3, 3) == 1.9
    # favorite <3.5 drifts +0.33 -> 3 * 1.33 = 3.99
    assert round(out[0].sp_0, 3) == 3.99
