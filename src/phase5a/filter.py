"""Niche qualification: turn (match, option) pairs into combo Candidates.

The niche definitions live in a JSON file (default
``src/phase5a/niches_default.json``) so that the surviving-niches table
can be updated without touching code. Each rule may constrain any subset
of: option, sp_lo, sp_hi, league_tier, handicap_class. A rule "matches"
a (match, option) when ALL specified constraints are met. The first
matching rule supplies ``p_hat_train`` (used as the prior probability)
and the candidate is emitted.

Re-uses the league/handicap classifiers from ``niche_analysis.data_loader``
to stay consistent with Phase 4 buckets.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from src.combo_optimizer import Candidate
from src.niche_analysis.data_loader import (
    classify_comp_type, classify_handicap, classify_league,
)

from .data_loader import LiveSnapshot

DEFAULT_NICHES_PATH = Path(__file__).parent / "niches_default.json"


@dataclass(frozen=True)
class NicheRule:
    name: str
    p_hat_train: float
    option: Optional[str] = None
    sp_lo: Optional[float] = None
    sp_hi: Optional[float] = None
    league_tier: Optional[str] = None
    handicap_class: Optional[str] = None
    # comp_type ∈ {"cup", "league", "intl"} — added 2026-05-09 after the
    # cup-subset analysis showed +0.07 q boost for option=0/sp 3.5-4.5/h1
    # in cup matches and +0.04 boost for option=3/sp 3.5-4.5/h_unknown
    # cup. More-specific comp_type rules go BEFORE the general ones in
    # JSON so the first-match-wins loop picks them up.
    comp_type: Optional[str] = None


_LEAGUE_Q_PATH = Path(__file__).parent / "league_quality.json"


def _load_league_q() -> dict:
    if _LEAGUE_Q_PATH.exists():
        try:
            return json.loads(_LEAGUE_Q_PATH.read_text())
        except Exception:
            return {}
    return {}


@dataclass(frozen=True)
class DriftBlockRule:
    """Block a (match, option) leg if ALL specified conditions match.

    Fields mirror NicheRule dimensions but serve as a reject-list: any leg
    that satisfies every non-None field is dropped before entering the pool.
    None means "any value" — always specify at least one constraint.

    hcp_class values: "h0" (平受), "h1" (±1 goal), "h2plus" (±2+), "h_unknown".
    option values: "3" (主胜), "1" (平局), "0" (客胜).
    leagues: frozenset of league names; None = apply to all leagues.
    """
    option: Optional[str] = None
    hcp_class: Optional[str] = None
    sp_lo: Optional[float] = None   # sp >= sp_lo
    sp_hi: Optional[float] = None   # sp < sp_hi
    leagues: Optional[frozenset] = None  # None → all leagues


def _drift_blocked(
    rules: tuple,
    *,
    option: str,
    hcp_class: str,
    sp: float,
    league: Optional[str],
) -> bool:
    """Return True if the leg matches any DriftBlockRule (i.e., should be rejected)."""
    for r in rules:
        if r.option is not None and r.option != option:
            continue
        if r.hcp_class is not None and r.hcp_class != hcp_class:
            continue
        if r.sp_lo is not None and sp < r.sp_lo:
            continue
        if r.sp_hi is not None and sp >= r.sp_hi:
            continue
        if r.leagues is not None and league not in r.leagues:
            continue
        return True
    return False


@dataclass(frozen=True)
class NicheConfig:
    return_rate: float
    rules: tuple[NicheRule, ...] = field(default_factory=tuple)
    league_q_min: float = 0.0  # if > 0, only legs from leagues with historical q ≥ this pass
    league_q_table: tuple = field(default_factory=tuple)  # (league, q) pairs
    # SP-drift blacklist: leagues with empirically high big-drop rates (>33% from 2026-05 analysis).
    # Default is the 档一 set; override via DB config key "league_blacklist" (comma-separated).
    league_blacklist: frozenset = field(default_factory=frozenset)
    # Fine-grained SP-drift block rules: condition-based filter more precise than league-level.
    # Populated from "drift_block_rules" key in the niches JSON file.
    drift_block_rules: tuple = field(default_factory=tuple)

    @classmethod
    def load(cls, path: str | Path | None = None,
             league_q_min: float = 0.0,
             league_blacklist: frozenset | set | None = None) -> "NicheConfig":
        p = Path(path) if path else DEFAULT_NICHES_PATH
        data = json.loads(p.read_text())
        rules = tuple(
            NicheRule(
                name=r["name"],
                p_hat_train=float(r["p_hat_train"]),
                option=r.get("option"),
                sp_lo=r.get("sp_lo"),
                sp_hi=r.get("sp_hi"),
                league_tier=r.get("league_tier"),
                handicap_class=r.get("handicap_class"),
                comp_type=r.get("comp_type"),
            )
            for r in data.get("rules", [])
        )
        drift_rules = tuple(
            DriftBlockRule(
                option=d.get("option"),
                hcp_class=d.get("hcp_class"),
                sp_lo=d.get("sp_lo"),
                sp_hi=d.get("sp_hi"),
                leagues=frozenset(d["leagues"]) if d.get("leagues") else None,
            )
            for d in data.get("drift_block_rules", [])
        )
        lq = _load_league_q()
        lq_table = tuple((k, float(v["q"])) for k, v in lq.items())
        bl = frozenset(league_blacklist) if league_blacklist is not None else frozenset()
        return cls(return_rate=float(data.get("return_rate", 0.65)),
                   rules=rules,
                   league_q_min=float(league_q_min),
                   league_q_table=lq_table,
                   league_blacklist=bl,
                   drift_block_rules=drift_rules)

    def league_passes(self, league: str | None) -> bool:
        """Return True if `league` is allowed (not blacklisted, and passes q_min).
        Unknown leagues default to allowed (avoid hiding new ones)."""
        if not league:
            return True
        if league in self.league_blacklist:
            return False
        if self.league_q_min <= 0:
            return True
        for name, q in self.league_q_table:
            if name == league:
                return q >= self.league_q_min
        return True  # unknown — be permissive


def _matches(
    rule: NicheRule, *,
    option: str, sp: float, league_tier: str, handicap_class: str,
    comp_type: str = "league",
) -> bool:
    if rule.option is not None and rule.option != option:
        return False
    if rule.sp_lo is not None and sp < rule.sp_lo:
        return False
    if rule.sp_hi is not None and sp >= rule.sp_hi:
        return False
    if rule.league_tier is not None and rule.league_tier != league_tier:
        return False
    if rule.handicap_class is not None and rule.handicap_class != handicap_class:
        return False
    if rule.comp_type is not None and rule.comp_type != comp_type:
        return False
    return True


def _option_iter(snap: LiveSnapshot):
    for code, sp in (("3", snap.sp_3), ("1", snap.sp_1), ("0", snap.sp_0)):
        if sp is None or sp <= 1.0:
            continue
        yield code, float(sp)


@dataclass(frozen=True)
class QualifiedCandidate:
    """combo_optimizer.Candidate plus context for human-readable plan rows."""

    candidate: Candidate
    rule_name: str
    snap: LiveSnapshot
    option_code: str  # "3" / "1" / "0"


def qualify_candidates(
    snapshots: Iterable[LiveSnapshot],
    config: NicheConfig,
) -> List[QualifiedCandidate]:
    """Emit one Candidate per (match, option) pair that matches some rule.

    If a single match has multiple options that qualify (e.g. both home
    and away pass distinct rules), all are emitted. The combo_optimizer
    selector dedupes by match_id (keeping the highest-edge leg), so this
    is safe and lets the higher-EV side win.
    """
    out: List[QualifiedCandidate] = []
    for snap in snapshots:
        if not config.league_passes(snap.league):
            continue
        league_tier = classify_league(snap.league)
        handicap_class = classify_handicap(snap.handicap_line)
        comp_type = classify_comp_type(snap.league)
        for option_code, sp in _option_iter(snap):
            if config.drift_block_rules and _drift_blocked(
                config.drift_block_rules,
                option=option_code,
                hcp_class=handicap_class,
                sp=sp,
                league=snap.league,
            ):
                continue
            for rule in config.rules:
                if _matches(rule, option=option_code, sp=sp,
                            league_tier=league_tier,
                            handicap_class=handicap_class,
                            comp_type=comp_type):
                    cand = Candidate(
                        match_id=snap.match_id,
                        selection=int(option_code),
                        p_hat=rule.p_hat_train,
                        sp=sp,
                    )
                    out.append(QualifiedCandidate(
                        candidate=cand, rule_name=rule.name,
                        snap=snap, option_code=option_code,
                    ))
                    break  # first matching rule wins
    return out
