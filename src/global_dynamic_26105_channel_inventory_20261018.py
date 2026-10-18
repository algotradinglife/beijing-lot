"""Cache-only company8 Asian/total queue from365 authoritative native headers."""
if __name__ == '__main__':
    import argparse,csv,hashlib,json
    from datetime import datetime,timedelta
    from pathlib import Path
    from beidan_backend.unified_sources import SourceClient,IDENTITY,validate_identity,identity_matches
    from beidan_backend.fundamentals import analysis_record
    from beidan_backend.market_capture.history import over_under_history_url
    from beidan_backend.extraction_cache import CacheMissError
    from beidan_backend.catalog.paths import location
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    roster_path=Path(a.roster);roster=json.loads(roster_path.read_bytes());rows=roster['data']
    if len(rows)!=365 or len({r['slot'] for r in rows})!=365 or any(r['issue_id']!='26105' for r in rows):raise ValueError('Exact365 fixture roster required')
    work=location(a.output,require_exists=False)
    if work.exists():raise ValueError('Immutable output exists')
    work.mkdir(parents=True);client=SourceClient();headers=[];channels=[];fixture_rows=[]
    for row in rows:
        native=row['native_id'].lstrip('0');fixture=f"26105:{row['slot']}";packet=dict(fixture_id=fixture,provider_id=row['native_id'])
        try:
            cap=client.request('titan',f'https://zq.titan007.com/analysis/{native}cn.htm',max_age=0,cache_only=True,reuse_raw=True)
            packet['analysis_receipt']=cap['receipt'];assert cap['receipt']['network_attempts']==0
        except CacheMissError as error:
            packet.update(state='CACHE_MISS',error=str(error));headers.append(packet);continue
        try:
            head=analysis_record(cap['data'],source='titan',provider_id=native,identity_only=True)
            identity={k:head[k] for k in IDENTITY};validate_identity(identity)
            if row.get('home_id') is not None and row.get('away_id') is not None:
                expected=dict(provider_id=native,home_id=row['home_id'].lstrip('0'),away_id=row['away_id'].lstrip('0'))
                if not identity_matches(head,expected):raise ValueError('Roster oriented native IDs differ')
            elif (head['home'],head['away'])!=(row['home'],row['away']):raise ValueError('Missing roster IDs and exact names differ')
            kickoff=datetime.fromisoformat(head['kickoff_utc'])
            packet.update(state='HEADER_VALIDATED',identity=identity)
        except (ValueError,KeyError) as error:
            packet.update(state='HEADER_REJECTED',error_type=type(error).__name__,error=str(error));headers.append(packet);continue
        headers.append(packet)
        fixture_rows.append(dict(fixture_id=fixture,provider_id=native,home_id=head['home_id'],away_id=head['away_id'],home=head['home'],away=head['away'],slot=row['slot'],handicap=row['handicap'],kickoff_at=kickoff.isoformat(),cutoff_utc=(kickoff-timedelta(hours=24)).isoformat()))
        total=over_under_history_url(native,8,kickoff)
        for kind,url in [('asian',total.replace('oddskind=1','oddskind=0')),('total',total)]:
            item=dict(fixture_id=fixture,provider_id=native,kind=kind,url=url,state='RAW_CACHED',receipt=None)
            try:
                raw=client.request('titan',url,max_age=0,cache_only=True,reuse_raw=True)
                item['receipt']=raw['receipt'];assert raw['receipt']['network_attempts']==0
            except CacheMissError:item['state']='CACHE_MISS'
            channels.append(item)
    manifest=dict(issue_id='26105',scope=365,network_attempts=0,prices_validated=False,
        source_roster=dict(path=str(roster_path),sha256=hashlib.sha256(roster_path.read_bytes()).hexdigest()),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),company_id=8,headers=headers,channels=channels,fixtures=fixture_rows)
    write_json_atomically(value=manifest,path=work/'inventory.json')
    print(json.dumps(dict(scope=365,validated_headers=len(fixture_rows),rejected_headers=sum(x['state']!='HEADER_VALIDATED' for x in headers),channels=len(channels),raw_cached=sum(x['state']=='RAW_CACHED' for x in channels),raw_missing=sum(x['state']=='CACHE_MISS' for x in channels),network_attempts=0)),flush=True)
