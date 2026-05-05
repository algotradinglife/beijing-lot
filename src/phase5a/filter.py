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
from src.niche_analysis.data_loader import classify_handicap, classify_league

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


_LEAGUE_Q_PATH = Path(__file__).parent / "league_quality.json"


def _load_league_q() -> dict:
    if _LEAGUE_Q_PATH.exists():
        try:
            return json.loads(_LEAGUE_Q_PATH.read_text())
        except Exception:
            return {}
    return {}


@dataclass(frozen=True)
class NicheConfig:
    return_rate: float
    rules: tuple[NicheRule, ...] = field(default_factory=tuple)
    league_q_min: float = 0.0  # if > 0, only legs from leagues with historical q ≥ this pass
    league_q_table: tuple = field(default_factory=tuple)  # (league, q) pairs

    @classmethod
    def load(cls, path: str | Path | None = None,
             league_q_min: float = 0.0) -> "NicheConfig":
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
            )
            for r in data.get("rules", [])
        )
        lq = _load_league_q()
        lq_table = tuple((k, float(v["q"])) for k, v in lq.items())
        return cls(return_rate=float(data.get("return_rate", 0.65)),
                   rules=rules,
                   league_q_min=float(league_q_min),
                   league_q_table=lq_table)

    def league_passes(self, league: str | None) -> bool:
        """Return True if `league` is allowed under the q_min filter.
        Unknown leagues default to allowed (avoid hiding new ones)."""
        if self.league_q_min <= 0:
            return True
        if not league:
            return True
        for name, q in self.league_q_table:
            if name == league:
                return q >= self.league_q_min
        return True  # unknown — be permissive


def _matches(
    rule: NicheRule, *,
    option: str, sp: float, league_tier: str, handicap_class: str,
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
        for option_code, sp in _option_iter(snap):
            for rule in config.rules:
                if _matches(rule, option=option_code, sp=sp,
                            league_tier=league_tier,
                            handicap_class=handicap_class):
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
