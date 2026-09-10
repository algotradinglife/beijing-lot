"""Cutoff-bound overall/venue form for a fixed descriptive draw expert."""
from pathlib import Path
import hashlib
import json

from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import pilot_tables
from src.fundamentals_home_away import home_away_windows
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.diagnostic_window import diagnostic_date_window
from src.temporal_learning.provenance import implementation_closure


def draw_form_summary(selection, *, team_id, target_net, cutoff):
    """Describe an existing shared window; goals/points per match and fractions.

    No new window, fitting, cache or I/O. Empty selected window stays unavailable.
    Team-relative net is used (away team's target net is sign-reversed).
    Explicit cutoff/receipt/row hash binding rejects altered or cross-cutoff rows.
    """
    receipt=selection['receipt']; rows=selection['rows']
    if not isinstance(cutoff,Cutoff) or receipt['cutoff_identity']!=cutoff.identity:
        raise ValueError('Form cutoff binding mismatch')
    if (receipt.get('identity') != stable_json_hash({k:v for k,v in receipt.items() if k!='identity'})
        or receipt.get('cutoff_ts') != cutoff.cutoff_ts.isoformat()
        or receipt.get('target_issue') != cutoff.target_issue):
        raise ValueError('Form receipt integrity/cutoff mismatch')
    if stable_json_hash(rows)!=receipt['selected_sha256']:
        raise ValueError('Form selection changed')
    if not isinstance(team_id,str) or not team_id or type(target_net) is not int:
        raise ValueError('Team/target margin required')
    fields=('wins','draws','losses','goals_for_pg','goals_against_pg','net_pg',
            'points_pg','exact_margin_rate','total_pg')
    if not rows:return dict(n=0,**dict.fromkeys(fields))
    gf=[]; ga=[]
    for row in rows:
        if (row['home_id']==team_id)+(row['away_id']==team_id)!=1:
            raise ValueError('Unique team orientation required')
        h,a=row['home_goals'],row['away_goals']
        if any(type(v) is not int or v<0 for v in (h,a)):
            raise ValueError('Integer historical scores required')
        scored,conceded=(h,a) if row['home_id']==team_id else (a,h)
        gf.append(scored);ga.append(conceded)
    net=[a-b for a,b in zip(gf,ga)];n=len(rows)
    wins=sum(x>0 for x in net);draws=sum(x==0 for x in net)
    return dict(n=n,wins=wins,draws=draws,losses=n-wins-draws,
        goals_for_pg=sum(gf)/n,goals_against_pg=sum(ga)/n,net_pg=sum(net)/n,
        points_pg=(3*wins+draws)/n,exact_margin_rate=sum(x==target_net for x in net)/n,
        total_pg=(sum(gf)+sum(ga))/n)


def draw_context_inputs(inventories, targets, *, repository_root, cache_dir, window, minimum):
    """Build only declared fixture contexts; reuse Titan-primary integration.

    Targets: issue/slot/provider_id/handicap. Inventories supply explicit cutoffs.
    Overall and venue views use shared diagnostic_date_window / home_away_windows.
    Weather uses an explicit owner assumption of prematch availability; its
    observed availability remains UNKNOWN. No fabricated forecast timestamps.
    Returns sealed flat rows, four form receipts/fixture, raw/code hashes.
    Read-only except the existing declared parse cache; no target result reading.
    """
    closure=implementation_closure(Path(repository_root),('src.fundamentals_draw_context',))['files']
    keys=[(t['issue'],t['slot'],t['provider_id']) for t in targets]
    if not keys or len(set(keys))!=len(keys):raise ValueError('Unique declared targets required')
    rows=[]; receipts=[]; hashes={}; found=set(); cuts={}
    for inv in inventories:
        chosen=[t for t in targets if t['issue']==inv['issue']]
        if not chosen:continue
        report=issue_capture_report(inv['roster_path'],inv['response_paths'],issue=inv['issue'],
            expected_fixture_count=inv['fixture_count'],expected_slots=[int(s) for s in inv['cutoffs']],cache_dir=cache_dir)
        pilot=pilot_tables(report,cutoffs=inv['cutoffs'],adjudications=inv.get('adjudications'))
        venue=home_away_windows(pilot,report['fixtures'],cutoffs=inv['cutoffs'],
            window=window,minimum=minimum,repository_root=repository_root)
        hashes.update(pilot['input_file_hashes']);excluded={f['provider_id'] for f in report['fixtures']}
        for t in chosen:
            f=next((f for f in report['fixtures'] if f['slot']==t['slot']),None)
            if f is None or f['provider_id']!=t['provider_id']:raise ValueError('Context native identity mismatch')
            if type(t['handicap']) not in (int,float) or int(t['handicap'])!=t['handicap']:
                raise ValueError('Integer handicap required')
            cutoff=Cutoff.decision_epoch(inv['issue'],inv['cutoffs'][str(t['slot'])])
            cuts.setdefault(inv['issue'],{})[str(t['slot'])]=inv['cutoffs'][str(t['slot'])]
            v=next(v for v in venue if v['slot']==t['slot'])
            base=next(f for f in pilot['integrated_fixtures'] if f['slot']==t['slot'])
            row=dict(t,home_team_id=f['home_id'],away_team_id=f['away_id'],
                cutoff_utc=cutoff.cutoff_ts.isoformat(),status=v['status'],
                venue_mode=v['history_mode'],competition=base['competition_name'],
                competition_category=base['competition_category'],
                weather=base['weather_normalized'],weather_source=base['weather_normalized_source'],
                temperature_min_c=base['temperature_min_c'],temperature_max_c=base['temperature_max_c'],
                weather_availability='UNKNOWN',weather_assumption='ASSUMED_PREMATCH_BY_OWNER',
                weather_used=base['weather_normalized'] is not None or base['temperature_min_c'] is not None or base['temperature_max_c'] is not None)
            ledger=dict(issue=t['issue'],slot=t['slot'],provider_id=t['provider_id'],views={})
            for side in ('home','away'):
                tid=f[side+'_id'];net=int(-t['handicap'] if side=='home' else t['handicap'])
                candidates=[r for r in pilot['integrated_history'] if r['slot']==t['slot'] and tid in (r['home_id'],r['away_id'])]
                overall=diagnostic_date_window(candidates,cutoff=cutoff,window=window,
                    minimum=v['adjudication'].get('minimum',minimum),timezone='Asia/Shanghai',excluded_ids=excluded,
                    source_hashes=pilot['input_file_hashes'],implementation_hashes=closure)
                role=dict(rows=v[side+'_window'],receipt=v[side+'_receipt'])
                for name,selection in [('overall',overall),('venue',role)]:
                    summary=draw_form_summary(selection,team_id=tid,target_net=net,cutoff=cutoff)
                    row.update({side+'_'+name+'_'+k:value for k,value in summary.items()})
                    ledger['views'][side+'_'+name]=selection
                    if summary['n']==0:row['status']='INSUFFICIENT_FORM_HISTORY'
            rows.append(row);receipts.append(ledger);found.add((t['issue'],t['slot'],t['provider_id']))
    if found!=set(keys):raise ValueError('Unmatched declared contexts')
    artifact=dict(rows=rows,receipts=receipts,cutoffs=cuts,input_file_hashes=hashes,
        implementation_hashes=closure,window=window,minimum=minimum,historical_admission=False)
    encoded=json.dumps(artifact,ensure_ascii=True,separators=(',',':'),allow_nan=False)
    return dict(artifact,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())
