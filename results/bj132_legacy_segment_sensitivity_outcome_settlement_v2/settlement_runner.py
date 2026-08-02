#!/usr/bin/env python3
"""One-shot legacy segment-sensitivity settlement for #132.

This runner is deliberately non-controlling. It settles the superseded
segment-compatible Gate-A v1 only as sensitivity evidence; the complete-issue
primary result remains NOT_RUN pending a separately accepted replacement Gate A.
"""
from __future__ import annotations

import argparse
import csv
import errno
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-DELETE-SCORE-N7-001"
VERSION = "bj132-legacy-segment-sensitivity-v2"
FREEZE_MANIFEST = "5b41fef30543647eef1dec5cfd65e4a12343c898ebd929d13393a2d6f1371937"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
FULL_K, DELETE_K, UNIT, FACTOR = 2187, 1458, Decimal("2"), Decimal("0.65")
TAX_RATE, TAX_THRESHOLD, QUANT = Decimal("0.20"), Decimal("10000"), Decimal("0.000001")
getcontext().prec = 128

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "first_kickoff_ts", "last_kickoff_ts", "variant_id", "arm",
    "portfolio_id", "selected_match_ids", "selected_n", "gm_e_sp", "disposition", "reason", "p_min_deleted_match_id",
    "p_min_deleted_code", "p_min_deleted_probability", "p_min_predicted_sp", "p_min_q", "q_min_deleted_match_id",
    "q_min_deleted_code", "q_min_deleted_probability", "q_min_predicted_sp", "q_min_q", "rankers_disagree", "formula_k",
    "stake_yuan", "matched_full_k", "matched_full_stake_yuan", "stake_reduction_fraction", "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "arm", "issue", "fold", "year", "pool_id", "match_id", "match_idx", "selection_rank",
    "e_sp", "p_min", "p3", "p1", "p0", "predicted_sp3", "predicted_sp1", "predicted_sp0", "q3", "q1", "q0",
    "p_min_deleted_match_id", "p_min_deleted_code", "q_min_deleted_match_id", "q_min_deleted_code", "allowed_codes",
)
OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "settlement_status", "outcome_gap_count", "coverage_hit", "deleted_code_occurred", "truth_sequence", "final_winning_sp_product",
    "gross_pre_tax_yuan", "issue_policy_gross_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan",
    "winning_sp_sources", "deleted_match_e_sp", "deleted_probability", "deleted_predicted_sp", "deleted_q",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "arm", "frontier_rows", "gate_a_available", "no_bet_gate_a", "unavailable_canonical_outcome",
    "settled", "stake_yuan", "gross_pre_tax_yuan", "pre_tax_net_yuan", "no_tax_roi", "tax_yuan", "after_tax_gross_yuan",
    "tax_adjusted_net_yuan", "tax_adjusted_roi", "coverage_hits", "coverage_hit_rate", "deleted_code_occurrences", "deleted_code_rate",
    "settled_issue_count", "settled_pool_count", "max_drawdown_yuan", "longest_miss_streak", "gross_top_issue_share",
    "largest_event_gross_yuan", "ex_largest_event_tax_roi",
)
COMPARISON_FIELDS = (
    "scope", "scope_value", "variant_id", "full_settled", "ranker", "ranker_settled", "full_stake_yuan", "ranker_stake_yuan",
    "stake_retention_vs_full", "gross_retention_vs_full", "full_no_tax_roi", "ranker_no_tax_roi", "no_tax_roi_delta_ranker_minus_full",
    "full_tax_adjusted_roi", "ranker_tax_adjusted_roi", "tax_adjusted_roi_delta_ranker_minus_full", "full_coverage_hit_rate",
    "ranker_coverage_hit_rate", "ranker_deleted_code_rate", "full_max_drawdown_yuan", "ranker_max_drawdown_yuan",
)
DELTA_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "first_kickoff_ts", "rankers_disagree", "arm",
    "deleted_match_id", "deleted_code", "deleted_code_occurred", "full_coverage_hit", "arm_coverage_hit", "full_stake_yuan", "arm_stake_yuan",
    "stake_saved_yuan", "full_gross_pre_tax_yuan", "arm_gross_pre_tax_yuan", "full_tax_adjusted_net_yuan", "arm_tax_adjusted_net_yuan",
    "tax_net_delta_arm_minus_full",
)
QPAIR_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "first_kickoff_ts", "p_min_deleted_match_id", "p_min_deleted_code",
    "p_min_deleted_probability", "p_min_predicted_sp", "p_min_q", "q_min_deleted_match_id", "q_min_deleted_code", "q_min_deleted_probability",
    "q_min_predicted_sp", "q_min_q", "p_min_deleted_code_occurred", "q_min_deleted_code_occurred", "p_min_tax_adjusted_net_yuan",
    "q_min_tax_adjusted_net_yuan", "q_minus_p_tax_net_yuan",
)
STRATUM_FIELDS = (
    "dimension", "stratum", "variant_id", "arm", "settled", "stake_yuan", "gross_pre_tax_yuan", "no_tax_roi", "tax_adjusted_roi",
    "expected_deleted_probability", "observed_deleted_code_rate", "deleted_code_occurrences",
)


def repo(anchor: Path) -> Path:
    for item in (anchor.resolve().parent, *anchor.resolve().parents):
        if (item / ".git").exists(): return item
    raise RuntimeError("repository root unavailable")


ROOT = repo(Path(__file__))
FREEZE = ROOT / "results" / "bj132_gate_a_preoutcome_v1"
OUTCOMES = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj132_legacy_segment_sensitivity_outcome_settlement_v2"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""): digest.update(block)
    return digest.hexdigest()


def dec(value: object, label: str) -> Decimal:
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error: raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite(): raise RuntimeError(f"non-finite {label}")
    return result


def money(value: Decimal) -> str: return format(value.quantize(QUANT), "f")
def ratio(value: Decimal | None) -> str: return "" if value is None else format(value, ".12f")


def manifest(bundle: Path, expected: str) -> dict[str, str]:
    path = bundle / "SHA256SUMS.json"
    if sha(path) != expected: raise RuntimeError(f"unaccepted manifest: {bundle}")
    declared = json.loads(path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in bundle.iterdir() if item.is_file() and item.name != path.name}
    if declared != actual: raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def validate_inputs() -> dict[str, str]:
    freeze = manifest(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("denominator", {}).get("frontier_rows") != 294576 or card.get("denominator", {}).get("role_rows") != 1894515:
        raise RuntimeError("Gate-A contract/cardinality drift")
    outcome = manifest(OUTCOMES, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD: raise RuntimeError("canonical outcome payload drift")
    return {"gate_a_manifest_sha256": FREEZE_MANIFEST, "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
            "outcome_manifest_sha256": OUTCOME_MANIFEST, "outcome_payload_sha256": OUTCOME_PAYLOAD}


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOMES / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS: raise RuntimeError("outcome schema drift")
        result = {row["match_id"]: row for row in reader}
    for row in result.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0:
            raise RuntimeError("untrusted outcome")
    return result


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb"); zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline=""); writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n"); writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles; text.flush(); text.detach(); zipped.close(); raw.close()


def role_groups():
    with gzip.open(FREEZE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ROLE_FIELDS: raise RuntimeError("role schema drift")
        current: tuple[str, str, str] | None = None; group: list[dict[str, str]] = []
        for row in reader:
            key = row["variant_id"], row["portfolio_id"], row["arm"]
            if current is not None and current != key:
                yield current, group; group = []
            current = key; group.append(row)
        if current is not None: yield current, group


def settle(frontier: dict[str, str], roles: list[dict[str, str]] | None, outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    if frontier["arm"] == "NO_BET_CONTROL":
        if roles is not None or frontier["disposition"] != "NO_BET": raise RuntimeError("no-bet drift")
        return {"status":"NO_BET_GATE_A","gap":0,"hit":"","deleted":"","truth":"","product":Decimal(0),"gross":Decimal(0),"sources":"","e_sp":"","p":"","sp":"","q":""}
    if roles is None or len(roles) != 7 or [int(row["selection_rank"]) for row in roles] != list(range(1,8)):
        raise RuntimeError("seven-role geometry drift")
    if (frontier["variant_id"],frontier["portfolio_id"],frontier["arm"]) != (roles[0]["variant_id"],roles[0]["portfolio_id"],roles[0]["arm"]): raise RuntimeError("role/frontier drift")
    if ";".join(row["match_id"] for row in roles) != frontier["selected_match_ids"]: raise RuntimeError("frozen matches drift")
    expected = FULL_K if frontier["arm"] == "MATCHED_FULL_N7" else DELETE_K
    if frontier["arm"] not in {"MATCHED_FULL_N7","P_MIN_DELETE_N7","Q_MIN_DELETE_N7"} or int(frontier["formula_k"]) != expected or dec(frontier["stake_yuan"],"stake") != UNIT * expected:
        raise RuntimeError("ticket/stake drift")
    missing = [row["match_id"] for row in roles if row["match_id"] not in outcomes]
    if missing: return {"status":"UNAVAILABLE_CANONICAL_OUTCOME","gap":len(missing),"hit":"","deleted":"","truth":"","product":Decimal(0),"gross":Decimal(0),"sources":"","e_sp":"","p":"","sp":"","q":""}
    if frontier["arm"] == "P_MIN_DELETE_N7":
        mid, code, p, sp, q = frontier["p_min_deleted_match_id"], frontier["p_min_deleted_code"], frontier["p_min_deleted_probability"], frontier["p_min_predicted_sp"], frontier["p_min_q"]
    elif frontier["arm"] == "Q_MIN_DELETE_N7":
        mid, code, p, sp, q = frontier["q_min_deleted_match_id"], frontier["q_min_deleted_code"], frontier["q_min_deleted_probability"], frontier["q_min_predicted_sp"], frontier["q_min_q"]
    else: mid = code = p = sp = q = ""
    truth: list[str] = []; product = Decimal(1); sources: set[str] = set(); hit = True; deleted_e = ""
    for role in roles:
        outcome = outcomes[role["match_id"]]; truth.append(outcome["result_code"]); product *= dec(outcome["winning_sp"],"winning SP"); sources.add(outcome["winning_sp_source"])
        hit = hit and outcome["result_code"] in role["allowed_codes"]
        if role["match_id"] == mid: deleted_e = role["e_sp"]
    deleted = "YES" if mid and outcomes[mid]["result_code"] == code else ("NO" if mid else "")
    return {"status":"SETTLED","gap":0,"hit":"YES" if hit else "NO","deleted":deleted,"truth":"".join(truth),"product":product,"gross":UNIT*FACTOR*product if hit else Decimal(0),"sources":";".join(sorted(sources)),"e_sp":deleted_e,"p":p,"sp":sp,"q":q}


def bucket(row: dict[str, str]) -> tuple[str,str,str]: return row["issue"],row["variant_id"],row["arm"]


@dataclass
class Metric:
    variant: str; arm: str; scope: str; value: str
    track_path: bool = False
    rows: int = 0; available: int = 0; no_bet: int = 0; unavailable: int = 0; settled: int = 0; hits: int = 0; deleted: int = 0
    stake: Decimal = Decimal(0); gross: Decimal = Decimal(0); tax: Decimal = Decimal(0); net: Decimal = Decimal(0)
    issue_gross: dict[str,Decimal] = field(default_factory=lambda: defaultdict(Decimal)); issue_net: dict[str,Decimal] = field(default_factory=lambda: defaultdict(Decimal)); issues: set[str] = field(default_factory=set); pools: set[str] = field(default_factory=set)
    events: list[tuple[str,str,str,Decimal,bool,Decimal,Decimal]] = field(default_factory=list)
    def add(self,row:dict[str,str]) -> None:
        self.rows += 1
        if row["disposition"] == "AVAILABLE": self.available += 1
        if row["settlement_status"] == "NO_BET_GATE_A": self.no_bet += 1; return
        if row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME": self.unavailable += 1; return
        if row["settlement_status"] != "SETTLED": raise RuntimeError("unknown status")
        self.settled += 1; self.hits += row["coverage_hit"] == "YES"; self.deleted += row["deleted_code_occurred"] == "YES"
        stake,gross,tax,net=(dec(row[key],key) for key in ("stake_yuan","gross_pre_tax_yuan","tax_yuan","tax_adjusted_net_yuan"))
        self.stake += stake; self.gross += gross; self.tax += tax; self.net += net; self.issues.add(row["issue"]); self.pools.add(row["pool_id"]); self.issue_gross[row["issue"]]+=gross; self.issue_net[row["issue"]]+=net
        if self.track_path:
            self.events.append((row["first_kickoff_ts"],row["pool_id"],row["portfolio_id"],net,row["coverage_hit"]=="YES",gross,stake))
    def output(self) -> dict[str,object]:
        cumulative=peak=draw=Decimal(0); streak=longest=0
        for _,_,_,net,hit,_,_ in sorted(self.events):
            cumulative+=net; peak=max(peak,cumulative); draw=max(draw,peak-cumulative); streak=0 if hit else streak+1; longest=max(longest,streak)
        largest=max(self.events,key=lambda row:row[5],default=None); ex_net=self.net-(largest[3] if largest else Decimal(0)); ex_stake=self.stake-(largest[6] if largest else Decimal(0)); gross_total=sum(self.issue_gross.values(),Decimal(0)); top=max(self.issue_gross.values(),default=Decimal(0)); pre=self.gross-self.stake
        return {"scope":self.scope,"scope_value":self.value,"variant_id":self.variant,"arm":self.arm,"frontier_rows":self.rows,"gate_a_available":self.available,"no_bet_gate_a":self.no_bet,"unavailable_canonical_outcome":self.unavailable,"settled":self.settled,"stake_yuan":money(self.stake),"gross_pre_tax_yuan":money(self.gross),"pre_tax_net_yuan":money(pre),"no_tax_roi":ratio(pre/self.stake if self.stake else None),"tax_yuan":money(self.tax),"after_tax_gross_yuan":money(self.gross-self.tax),"tax_adjusted_net_yuan":money(self.net),"tax_adjusted_roi":ratio(self.net/self.stake if self.stake else None),"coverage_hits":self.hits,"coverage_hit_rate":ratio(Decimal(self.hits)/self.settled if self.settled else None),"deleted_code_occurrences":self.deleted,"deleted_code_rate":ratio(Decimal(self.deleted)/self.settled if self.settled else None),"settled_issue_count":len(self.issues),"settled_pool_count":len(self.pools),"max_drawdown_yuan":money(draw),"longest_miss_streak":longest,"gross_top_issue_share":ratio(top/gross_total if gross_total else None),"largest_event_gross_yuan":money(largest[5] if largest else Decimal(0)),"ex_largest_event_tax_roi":ratio(ex_net/ex_stake if ex_stake else None)}


def all_summaries(path: Path) -> tuple[list[dict[str,object]],list[dict[str,object]]]:
    allm:dict[tuple[str,str],Metric]={}; parts:dict[tuple[str,str,str,str],Metric]={}; years:set[str]=set()
    with gzip.open(path,"rt",newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key=row["variant_id"],row["arm"]; years.add(row["year"]); allm.setdefault(key,Metric(*key,"ALL","ALL",True)).add(row)
            for scope,value in (("YEAR",row["year"]),("FOLD",row["fold"])): parts.setdefault((scope,value,*key),Metric(*key,scope,value)).add(row)
    robust=[metric.output() for _,metric in sorted(parts.items())]
    for omitted in sorted(years):
        local:dict[tuple[str,str],Metric]={}
        with gzip.open(path,"rt",newline="",encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["year"] != omitted:
                    key=row["variant_id"],row["arm"]; local.setdefault(key,Metric(*key,"LEAVE_ONE_YEAR_OUT",omitted)).add(row)
        robust.extend(metric.output() for _,metric in sorted(local.items()))
    return [metric.output() for _,metric in sorted(allm.items())],robust


def write_csv(path:Path,fields:tuple[str,...],rows:list[dict[str,object]])->None:
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n");writer.writeheader();writer.writerows(rows)


def comparisons(rows:list[dict[str,object]])->list[dict[str,object]]:
    index={(row["scope"],row["scope_value"],row["variant_id"],row["arm"]):row for row in rows}; output=[]
    for (scope,value,variant,arm),full in sorted(index.items()):
        if arm != "MATCHED_FULL_N7": continue
        for ranker in ("P_MIN_DELETE_N7","Q_MIN_DELETE_N7"):
            other=index[(scope,value,variant,ranker)]; d=lambda r,k:dec(r[k],k)
            output.append({"scope":scope,"scope_value":value,"variant_id":variant,"full_settled":full["settled"],"ranker":ranker,"ranker_settled":other["settled"],"full_stake_yuan":full["stake_yuan"],"ranker_stake_yuan":other["stake_yuan"],"stake_retention_vs_full":ratio(d(other,"stake_yuan")/d(full,"stake_yuan") if d(full,"stake_yuan") else None),"gross_retention_vs_full":ratio(d(other,"gross_pre_tax_yuan")/d(full,"gross_pre_tax_yuan") if d(full,"gross_pre_tax_yuan") else None),"full_no_tax_roi":full["no_tax_roi"],"ranker_no_tax_roi":other["no_tax_roi"],"no_tax_roi_delta_ranker_minus_full":ratio(d(other,"no_tax_roi")-d(full,"no_tax_roi")) if full["no_tax_roi"] else "","full_tax_adjusted_roi":full["tax_adjusted_roi"],"ranker_tax_adjusted_roi":other["tax_adjusted_roi"],"tax_adjusted_roi_delta_ranker_minus_full":ratio(d(other,"tax_adjusted_roi")-d(full,"tax_adjusted_roi")) if full["tax_adjusted_roi"] else "","full_coverage_hit_rate":full["coverage_hit_rate"],"ranker_coverage_hit_rate":other["coverage_hit_rate"],"ranker_deleted_code_rate":other["deleted_code_rate"],"full_max_drawdown_yuan":full["max_drawdown_yuan"],"ranker_max_drawdown_yuan":other["max_drawdown_yuan"]})
    return output


def stratum(value:str,dimension:str)->str:
    x=float(value)
    if dimension=="DELETED_PROBABILITY": return "LE_010" if x<=.10 else "LE_020" if x<=.20 else "LE_030" if x<=.30 else "GT_030"
    if dimension=="PREDICTED_SP": return "LT_300" if x<3 else "300_400" if x<4 else "GE_400"
    if dimension=="E_SP": return "LT_280" if x<2.8 else "280_300" if x<3 else "GE_300"
    return "LT_300" if x<3 else "300_305" if x<3.05 else "GE_305"


def write_pair_and_strata(stage:Path,settlement:Path)->None:
    delta_h=gzip_writer(stage/"matched_full_deltas.csv.gz",DELTA_FIELDS); pair_h=gzip_writer(stage/"q_minus_p_disagreement_deltas.csv.gz",QPAIR_FIELDS); dw,pw=delta_h[-1],pair_h[-1]
    pending: list[dict[str,str]] = []; current: tuple[str,str] | None = None; stats:dict[tuple[str,str,str,str],list[Decimal|int]]=defaultdict(lambda:[0,Decimal(0),Decimal(0),Decimal(0),Decimal(0),0])
    def add_stat(row:dict[str,str],dim:str,key:str)->None:
        if row["arm"] == "MATCHED_FULL_N7" or row["settlement_status"] != "SETTLED": return
        item=stats[(dim,key,row["variant_id"],row["arm"])]; item[0]+=1; item[1]+=dec(row["stake_yuan"],"stake"); item[2]+=dec(row["gross_pre_tax_yuan"],"gross"); item[3]+=dec(row["tax_adjusted_net_yuan"],"net"); item[4]+=dec(row["deleted_probability"],"p"); item[5]+=row["deleted_code_occurred"]=="YES"
    def flush(group: list[dict[str,str]]) -> None:
        if not group: return
        if len(group)!=3: raise RuntimeError("matched-arm grouping drift")
        by={row["arm"]:row for row in group}; full=by["MATCHED_FULL_N7"]
        if set(by)!={"MATCHED_FULL_N7","P_MIN_DELETE_N7","Q_MIN_DELETE_N7"}: raise RuntimeError("matched arm labels drift")
        for arm in ("P_MIN_DELETE_N7","Q_MIN_DELETE_N7"):
            row=by[arm]; dw.writerow({"variant_id":row["variant_id"],"portfolio_id":row["portfolio_id"],"issue":row["issue"],"fold":row["fold"],"year":row["year"],"pool_id":row["pool_id"],"first_kickoff_ts":row["first_kickoff_ts"],"rankers_disagree":row["rankers_disagree"],"arm":arm,"deleted_match_id":row["p_min_deleted_match_id"] if arm=="P_MIN_DELETE_N7" else row["q_min_deleted_match_id"],"deleted_code":row["p_min_deleted_code"] if arm=="P_MIN_DELETE_N7" else row["q_min_deleted_code"],"deleted_code_occurred":row["deleted_code_occurred"],"full_coverage_hit":full["coverage_hit"],"arm_coverage_hit":row["coverage_hit"],"full_stake_yuan":full["stake_yuan"],"arm_stake_yuan":row["stake_yuan"],"stake_saved_yuan":money(dec(full["stake_yuan"],"s")-dec(row["stake_yuan"],"s")),"full_gross_pre_tax_yuan":full["gross_pre_tax_yuan"],"arm_gross_pre_tax_yuan":row["gross_pre_tax_yuan"],"full_tax_adjusted_net_yuan":full["tax_adjusted_net_yuan"],"arm_tax_adjusted_net_yuan":row["tax_adjusted_net_yuan"],"tax_net_delta_arm_minus_full":money(dec(row["tax_adjusted_net_yuan"],"n")-dec(full["tax_adjusted_net_yuan"],"n"))})
        if full["rankers_disagree"]=="1":
            p,q=by["P_MIN_DELETE_N7"],by["Q_MIN_DELETE_N7"];pw.writerow({"variant_id":p["variant_id"],"portfolio_id":p["portfolio_id"],"issue":p["issue"],"fold":p["fold"],"year":p["year"],"pool_id":p["pool_id"],"first_kickoff_ts":p["first_kickoff_ts"],"p_min_deleted_match_id":p["p_min_deleted_match_id"],"p_min_deleted_code":p["p_min_deleted_code"],"p_min_deleted_probability":p["p_min_deleted_probability"],"p_min_predicted_sp":p["p_min_predicted_sp"],"p_min_q":p["p_min_q"],"q_min_deleted_match_id":q["q_min_deleted_match_id"],"q_min_deleted_code":q["q_min_deleted_code"],"q_min_deleted_probability":q["q_min_deleted_probability"],"q_min_predicted_sp":q["q_min_predicted_sp"],"q_min_q":q["q_min_q"],"p_min_deleted_code_occurred":p["deleted_code_occurred"],"q_min_deleted_code_occurred":q["deleted_code_occurred"],"p_min_tax_adjusted_net_yuan":p["tax_adjusted_net_yuan"],"q_min_tax_adjusted_net_yuan":q["tax_adjusted_net_yuan"],"q_minus_p_tax_net_yuan":money(dec(q["tax_adjusted_net_yuan"],"q")-dec(p["tax_adjusted_net_yuan"],"p"))})
    with gzip.open(settlement,"rt",newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["settlement_status"]=="SETTLED":
                if row["arm"]!="MATCHED_FULL_N7":
                    deleted_code = row["p_min_deleted_code"] if row["arm"] == "P_MIN_DELETE_N7" else row["q_min_deleted_code"]
                    add_stat(row,"OUTCOME_TYPE",deleted_code); add_stat(row,"E_SP",stratum(row["deleted_match_e_sp"],"E_SP")); add_stat(row,"GM_E_SP",stratum(row["gm_e_sp"],"GM_E_SP")); add_stat(row,"DELETED_PROBABILITY",stratum(row["deleted_probability"],"DELETED_PROBABILITY")); add_stat(row,"PREDICTED_SP",stratum(row["deleted_predicted_sp"],"PREDICTED_SP"))
                key=(row["variant_id"],row["portfolio_id"])
                if current is not None and key != current:
                    flush(pending); pending=[]
                current=key; pending.append(row)
    flush(pending)
    close_gzip(delta_h);close_gzip(pair_h)
    out=[]
    for (dimension,key,variant,arm),item in sorted(stats.items()):
        n,stake,gross,net,prob,observed=item;out.append({"dimension":dimension,"stratum":key,"variant_id":variant,"arm":arm,"settled":n,"stake_yuan":money(stake),"gross_pre_tax_yuan":money(gross),"no_tax_roi":ratio((gross-stake)/stake if stake else None),"tax_adjusted_roi":ratio(net/stake if stake else None),"expected_deleted_probability":ratio(prob/Decimal(n) if n else None),"observed_deleted_code_rate":ratio(Decimal(observed)/Decimal(n) if n else None),"deleted_code_occurrences":observed})
    write_csv(stage/"deletion_strata.csv",STRATUM_FIELDS,out)


def build(output:Path)->dict[str,object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=".bj132_gateb_",dir=ROOT/"results"))
    try:
        provenance=validate_inputs();outcomes=load_outcomes();pre=stage/"_pre_tax.csv";buckets:dict[tuple[str,str,str],Decimal]=defaultdict(Decimal); roles=role_groups();next_group=next(roles,None);total=no_bet=identities=role_rows=0
        with gzip.open(FREEZE/"matched_delete_score_frontier.csv.gz","rt",newline="",encoding="utf-8") as source,pre.open("w",newline="",encoding="utf-8") as target:
            reader=csv.DictReader(source)
            if tuple(reader.fieldnames or ())!=FRONTIER_FIELDS:raise RuntimeError("frontier schema drift")
            writer=csv.DictWriter(target,fieldnames=FRONTIER_FIELDS+("settlement_status","outcome_gap_count","coverage_hit","deleted_code_occurred","truth_sequence","final_winning_sp_product","gross_pre_tax_yuan","winning_sp_sources","deleted_match_e_sp","deleted_probability","deleted_predicted_sp","deleted_q"),lineterminator="\n");writer.writeheader()
            for frontier in reader:
                role_set=None
                if frontier["arm"]!="NO_BET_CONTROL":
                    if next_group is None or next_group[0]!=(frontier["variant_id"],frontier["portfolio_id"],frontier["arm"]):raise RuntimeError("role stream drift")
                    role_set=next_group[1];next_group=next(roles,None);role_rows+=len(role_set)
                    if frontier["arm"]=="MATCHED_FULL_N7":identities+=1
                else:no_bet+=1
                result=settle(frontier,role_set,outcomes);writer.writerow({**frontier,"settlement_status":result["status"],"outcome_gap_count":result["gap"],"coverage_hit":result["hit"],"deleted_code_occurred":result["deleted"],"truth_sequence":result["truth"],"final_winning_sp_product":money(result["product"]),"gross_pre_tax_yuan":money(result["gross"]),"winning_sp_sources":result["sources"],"deleted_match_e_sp":result["e_sp"],"deleted_probability":result["p"],"deleted_predicted_sp":result["sp"],"deleted_q":result["q"]})
                if result["status"]=="SETTLED":buckets[bucket(frontier)]+=result["gross"]
                total+=1
        if next_group is not None or (total,no_bet,identities,role_rows)!=(294576,23931,90215,1894515):raise RuntimeError("frozen denominator drift")
        handles=gzip_writer(stage/"portfolio_settlement.csv.gz",SETTLEMENT_FIELDS);writer=handles[-1]
        with pre.open(newline="",encoding="utf-8") as source:
            for row in csv.DictReader(source):
                gross=dec(row["gross_pre_tax_yuan"],"gross");tax=gross*TAX_RATE if buckets[bucket(row)]>=TAX_THRESHOLD else Decimal(0);stake=dec(row["stake_yuan"],"stake") if row["settlement_status"]=="SETTLED" else Decimal(0)
                writer.writerow({**row,"stake_yuan":money(stake),"issue_policy_gross_yuan":money(buckets[bucket(row)]),"tax_yuan":money(tax),"after_tax_gross_yuan":money(gross-tax),"pre_tax_net_yuan":money(gross-stake),"tax_adjusted_net_yuan":money(gross-tax-stake)})
        close_gzip(handles);pre.unlink();all_rows,robust=all_summaries(stage/"portfolio_settlement.csv.gz");write_csv(stage/"arm_summary.csv",SUMMARY_FIELDS,all_rows);write_csv(stage/"robustness_summary.csv",SUMMARY_FIELDS,robust);write_csv(stage/"ranker_comparison.csv",COMPARISON_FIELDS,comparisons(all_rows+robust));write_pair_and_strata(stage,stage/"portfolio_settlement.csv.gz")
        positives=[row for row in all_rows if row["arm"]!="MATCHED_FULL_N7" and row["tax_adjusted_roi"] and dec(row["tax_adjusted_roi"],"roi")>0]
        decision={"decision":"POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives else "NO_PROMOTION","classification":"LEGACY_SEGMENT_SENSITIVITY_NON_CONTROLLING","applies_to":"superseded segment-compatible Gate-A v1 only","primary_issue_level_result":"NOT_RUN","positive_all_rows":len(positives),"promotion_authorized":False,"strict_independent_ev_required":bool(positives),"rule":"This NO_PROMOTION decision applies only to the legacy segment sensitivity. The primary complete-issue result is NOT_RUN pending acceptance and settlement of replacement Gate A."}
        (stage/"decision.json").write_text(json.dumps(decision,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        card={"issue":132,"contract":CONTRACT,"runner_version":VERSION,"stage":"LEGACY_SEGMENT_SENSITIVITY_OUTCOME_SETTLEMENT","classification":"LEGACY_SEGMENT_SENSITIVITY_NON_CONTROLLING","applies_to":"superseded segment-compatible Gate-A v1 only","primary_issue_level_result":"NOT_RUN","provenance":provenance,"denominator":{"frontier_rows":294576,"no_bet_rows":23931,"portfolio_identities":90215,"role_rows":1894515,"variants":9},"settlement":"A ¥2 sequence pays ¥2×0.65×product(final winning SP) exactly once iff frozen allowed codes cover all truth; final SP is uncapped.","tax":"Within issue+variant+arm paper policy, apply 20% to winning gross iff aggregate gross is at least ¥10,000.","boundary":"No matching, selection, q/p ranking, code deletion, threshold, or capital amount is regenerated after outcome source validation. This package is non-controlling legacy sensitivity evidence, not the #132 primary outcome settlement."}
        (stage/"settlement_card.json").write_text(json.dumps(card,indent=2,sort_keys=True)+"\n",encoding="utf-8");shutil.copyfile(__file__,stage/"settlement_runner.py");(stage/"README.md").write_text("# #132 legacy segment sensitivity\n\nNon-controlling settlement of the superseded segment-compatible Gate-A v1. `NO_PROMOTION` in this package applies only to this legacy comparator; the primary complete-issue result is `NOT_RUN`. Compare portable content identity after replay.\n",encoding="utf-8")
        def uncompressed(path:Path)->tuple[str,int]:
            digest,size=hashlib.sha256(),0
            with gzip.open(path,"rb") as handle:
                for block in iter(lambda:handle.read(1<<20),b""):digest.update(block);size+=len(block)
            return digest.hexdigest(),size
        gz=("portfolio_settlement.csv.gz","matched_full_deltas.csv.gz","q_minus_p_disagreement_deltas.csv.gz");content={"contract_version":"bj132-gateb-portable-content-v1","gzip_payloads":{name:{"canonical_decompressed_sha256":uncompressed(stage/name)[0],"canonical_decompressed_bytes":uncompressed(stage/name)[1]} for name in gz},"non_compressed_controls":{item.name:sha(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gz}};(stage/"CONTENT_IDENTITY.json").write_text(json.dumps(content,indent=2,sort_keys=True)+"\n",encoding="utf-8");sums={item.name:sha(item) for item in sorted(stage.iterdir()) if item.is_file()};(stage/"SHA256SUMS.json").write_text(json.dumps(sums,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        try:
            os.replace(stage,output)
        except OSError as error:
            if error.errno != errno.EXDEV: raise
            shutil.move(str(stage),str(output))
        return {"manifest_sha256":sha(output/"SHA256SUMS.json"),"content_identity_sha256":sha(output/"CONTENT_IDENTITY.json"),"decision":decision,"summary_rows":len(all_rows)}
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=OUTPUT);print(json.dumps(build(parser.parse_args().output.resolve()),sort_keys=True))


if __name__=="__main__":main()
