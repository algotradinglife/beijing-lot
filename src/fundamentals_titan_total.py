"""Titan OU HTML through Jina: immutable capture -> offline typed quote tables.

Reader HTML is a rendered representation, not original origin entity bytes.
No import-time network/writes. HK odds are profit per unit stake, lines goals.
"""
import hashlib
import json
import math
import re
from pathlib import Path

from bs4 import BeautifulSoup
from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_titan_euro import parse_titan_euro
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes
from src.temporal_learning.provenance import implementation_closure


def total_triplet(line, over, under):
    """Parse numeric/split Asian lines and positive Hong Kong prices; raise on gaps."""
    if not re.fullmatch(r'\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?', line):
        raise ValueError('Invalid total line')
    parts = list(map(float,line.split('/')))
    if any(x < 0 or x > 30 or x*2 != int(x*2) for x in parts) or (len(parts)==2 and parts[1]-parts[0] != .5):
        raise ValueError('Invalid total line components')
    prices = list(map(float,(over,under)))
    if any(not math.isfinite(x) or x<=0 for x in prices):
        raise ValueError('Positive HK odds required')
    return dict(line=sum(parts)/len(parts),line_text=line,over_hk=prices[0],under_hk=prices[1])


def parse_titan_total_html(text):
    """Extract identity, initial/displayed-final quotes and classified changes.

    One change row per company/time/cell; preserve live/unknown rows as excluded
    evidence. Do not parse match scores or admit untimed overview prices.
    Native team IDs and match ID mandatory. Unknown structure fails visibly.
    """
    soup=BeautifulSoup(text,'html.parser')
    table=soup.select_one('table#odds'); detail=soup.select_one('table#oddsDetail')
    head=soup.select_one('.analyhead')
    if table is None or detail is None or head is None:
        raise ValueError('Missing Titan total tables/identity')
    identities={}
    for side,selector in [('home','.home'),('away','.guest')]:
        links=head.select(selector+' a[href]')
        ids=[re.search(r'/team/Summary/(\d+)\.html',a['href']) for a in links]
        ids=[m[1] for m in ids if m]
        if len(ids)!=1: raise ValueError('Missing/duplicate team identity')
        identities[side+'_team_id']=ids[0]
    error=head.select_one('a.errors'); clock=head.select_one('.time')
    pid=re.search(r'ScheduleID=(\d+)',error['href']) if error else None
    kickoff=re.search(r'\d{4}-\d\d-\d\d \d\d:\d\d',clock.get_text()) if clock else None
    if not pid or not kickoff: raise ValueError('Missing native fixture clock')
    overview=[]
    for tr in table.select('tr'):
        checkbox=tr.select_one('input[name="oddsShow"]')
        if not checkbox: continue
        tds=tr.find_all('td',recursive=False)
        company=tds[1].get_text(' ',strip=True)
        initial=[td for td in tds if td.has_attr('title')]
        final=tr.select('td[oddstype="wholeOdds"]')
        if len(initial)!=3 or len(final)!=3: raise ValueError('Unknown overview schema')
        for stage,cells in [('opening',initial),('displayed_final',final)]:
            vals=[c.get_text(strip=True) for c in cells]
            overview.append(dict(company_id=checkbox['data-id'],company=company,stage=stage,
                **total_triplet(vals[1],vals[0],vals[2])))
    empty_label='暂无公司开盘'
    known_empty_labels=(empty_label,'鏆傛棤鍏徃寮€鐩�',*(empty_label.encode('utf-8').decode(codec,errors='replace') for codec in ('gb18030','gbk')))
    explicit_empty=not overview and any(label in table.get_text() for label in known_empty_labels)
    if (not overview and not explicit_empty) or len({r['company_id'] for r in overview})*2!=len(overview):
        raise ValueError('Empty/duplicate overview companies')
    headers=[h.get_text(strip=True) for h in detail.select('tr')[0].find_all('th')]
    expected=['比分','变化时间']
    damaged=[x.encode('utf-8').decode('gb18030',errors='replace') for x in expected]
    if headers[-2:] not in (expected,damaged) or len(set(headers))!=len(headers):
        raise ValueError('Unknown detail headers')
    # Some Reader HTML already contains irreversible replacement characters.
    # Recognize only the exact known header corruption; retain every raw label.
    # Header position identifies a company within a page, never across pages.
    changes=[]
    for i,tr in enumerate(detail.select('tr')[1:]):
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=len(headers): raise ValueError('Unknown detail row width')
        local=cells[-1].get_text(strip=True); score=cells[-2].get_text(strip=True)
        for company,cell in zip(headers[:-2],cells[:-2]):
            content=cell.get_text(' ',strip=True)
            if not content: continue
            vals=content.split()
            if len(vals)!=3: raise ValueError('Unknown detail price triple')
            style=re.sub(r'\s','',cell.get('style','')).lower()
            phase=('LIVE' if score or '#eaeaff' in style else
                   'PREMATCH' if '#ffffff' in style or '#dcfbff' in style else 'UNKNOWN')
            changes.append(dict(quote_id=f'{i}/{company}',company=company,quoted_local=local,
                phase=phase,**total_triplet(vals[0],vals[1],vals[2])))
    if explicit_empty and changes:
        raise ValueError('Empty overview conflicts with change quotes')
    return dict(provider_id=pid[1],kickoff_local=kickoff[0],**identities,
        overview=overview,changes=changes,
        text_encoding_status='READER_MOJIBAKE' if headers[-2:]==damaged else 'OK')


def titan_total_inputs(euro, capture_paths, *, cutoffs, repository_root, timezone, maximum_days):
    """Bind OU to verified Euro/Titan identity and fixture-specific cutoffs.

    Input euro is a freshly sealed titan_euro_inputs artifact. cutoffs is the
    explicit issue -> slot -> timestamp map; timezone must be Asia/Shanghai and
    the same rendered kickoff must equal the independent UTC Euro kickoff.
    Failed captures/identities/parser/clock conflicts remain status rows. Return
    all overview/change rows and latest strictly prior PREMATCH company quotes.
    A native match may occur in several issues: its one capture is replayed
    independently for each issue/slot cutoff. Duplicate issue/slot keys fail.
    No writes, no opening-price fallback; exact response envelopes/code bound.
    """
    if timezone!='Asia/Shanghai': raise ValueError('Unsupported source display timezone')
    if hashlib.sha256(euro['canonical_json'].encode()).hexdigest()!=euro['seal']:
        raise ValueError('Invalid Euro seal')
    canonical=json.loads(euro['canonical_json'])
    if any(canonical[k]!=euro[k] for k in canonical): raise ValueError('Euro artifact mutated')
    closure=implementation_closure(Path(repository_root),('src.fundamentals_titan_total',))['files']
    keys=[(r['issue'],r['slot']) for r in euro['rows']]
    if len(set(keys))!=len(keys): raise ValueError('Duplicate Euro fixture')
    indexed={}
    for r in euro['rows']:
        indexed.setdefault(r['provider_id'],[]).append(r)
    rows=[]; overview=[]; changes=[]; selected=[]; receipts=[]; hashes={}; seen=set()
    for path in capture_paths:
        path=str(path); meta,raw=read_response(Path(path))
        match=re.fullmatch(r'https://r\.jina\.ai/https://vip\.titan007\.com/OverDown_n\.aspx\?id=(\d+)&l=0',meta['url'])
        if not match or meta.get('final_url',meta['url'])!=meta['url']: raise ValueError('Unexpected Reader URL')
        pid=match[1]
        if pid in seen or pid not in indexed: raise ValueError('Duplicate/unmatched OU fixture')
        seen.add(pid)
        for e in indexed[pid]:
            cutoff=cutoffs[e['issue']][str(e['slot'])]
            if cutoff!=e['cutoff_utc']: raise ValueError('OU cutoff mismatch')
            capture_hash=hashlib.sha256(Path(path).read_bytes()).hexdigest(); hashes[path]=capture_hash
            base=dict(issue=e['issue'],slot=e['slot'],provider_id=pid)
            row=dict(base,status='HTTP_FAILURE',capture_path=path,capture_sha256=capture_hash,
                raw_sha256=meta.get('sha256'),received_at_utc=meta['received_at_utc'],
                source_url=meta['url'].removeprefix('https://r.jina.ai/'),cutoff_utc=cutoff,
                overview_companies=0,change_rows=0,selected_companies=0,excluded_live=0,excluded_unknown=0,
                excluded_same_or_later=0,detail=None)
            rows.append(row)
            if meta.get('status')!=200: continue
            try: p=parse_titan_total_html(raw.decode('utf-8'))
            except (ValueError,KeyError) as exc:
                row.update(status='PARSER_FAILURE',detail=str(exc)); continue
            row.update(overview_companies=len(p['overview'])//2,change_rows=len(p['changes']),
                text_encoding_status=p['text_encoding_status'])
            overview.extend(dict(base,**r) for r in p['overview'])
            changes.extend(dict(base,**r) for r in p['changes'])
            if e['status']!='OK_DIAGNOSTIC': row['status']='EURO_IDENTITY_OR_QUOTE_GATE'; continue
            if hashlib.sha256(Path(e['capture_path']).read_bytes()).hexdigest()!=e['capture_sha256']:
                raise ValueError('Euro capture changed')
            _,eraw=read_response(Path(e['capture_path'])); ep=parse_titan_euro(decode_analysis_text(eraw)[0])
            from zoneinfo import ZoneInfo
            from datetime import datetime
            kickoff=datetime.strptime(p['kickoff_local'],'%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(timezone))
            if any(p[k]!=ep[k] for k in ('provider_id','home_team_id','away_team_id')) or utc(kickoff)!=utc(ep['kickoff_utc']):
                row['status']='IDENTITY_OR_DISPLAY_CLOCK_MISMATCH'; continue
            row['excluded_live']=sum(r['phase']=='LIVE' for r in p['changes'])
            row['excluded_unknown']=sum(r['phase']=='UNKNOWN' for r in p['changes'])
            try:
                window=diagnostic_monthday_quotes([r for r in p['changes'] if r['phase']=='PREMATCH'],
                    anchor_utc=ep['kickoff_utc'],timezone=timezone,maximum_days=maximum_days,
                    cutoff=Cutoff.decision_epoch(e['issue'],cutoff),
                    source_hashes={path:capture_hash,e['capture_path']:e['capture_sha256']},implementation_hashes=closure)
            except ValueError as exc:
                row.update(status='CLOCK_OR_QUOTE_CONFLICT',detail=str(exc)); continue
            selected.extend(dict(base,**r) for r in window['rows'])
            receipts.append(dict(base,**window))
            row.update(status='OK_DIAGNOSTIC' if window['rows'] else 'NO_PRIOR_PREMATCH_QUOTES',
                selected_companies=len(window['rows']),excluded_same_or_later=window['window']['receipt']['excluded_same_or_later'])
    if seen!=set(indexed): raise ValueError('Missing declared OU captures')
    artifact=dict(rows=rows,overview=overview,changes=changes,selected=selected,receipts=receipts,
        capture_hashes=hashes,implementation_hashes=closure,euro_seal=euro['seal'],cutoffs=cutoffs,
        timezone=timezone,maximum_days=maximum_days,historical_admission=False)
    encoded=json.dumps(artifact,ensure_ascii=True,separators=(',',':'),allow_nan=False)
    return dict(artifact,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())
