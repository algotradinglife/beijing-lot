"""Two original-byte/native-ID health checks before the whole-issue Nowscore batch."""
if __name__ == '__main__':
    import argparse,csv,hashlib,json
    from pathlib import Path
    from beidan_backend.unified_sources import SourceClient,document_bytes
    from beidan_backend.fundamentals import analysis_record
    from beidan_backend.market_capture.service import titan_identity
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rows=list(csv.DictReader(Path(a.input).open()));client=SourceClient();results=[]
    for kind in ('analysis','euro'):
        row=next(r for r in rows if r['kind']==kind);native=row['provider_id'].lstrip('0')
        result=dict(kind=kind,fixture_id=row['fixture_id'],provider_id=row['provider_id'],url=row['url'],price_validation=False)
        try:
            with client.cache.lock.acquire(timeout=120,poll_interval=0.001):
                cap=client.cache.extract('nowscore',row['url'],document_bytes,max_age=0,min_interval=5,retries=1,reuse_raw=True)
            result['receipt']=cap['receipt'];assert hashlib.sha256(cap['data']).hexdigest()==cap['receipt']['sha256']
            if kind=='analysis':
                h=analysis_record(cap['data'],source='nowscore',provider_id=native,identity_only=True)
                assert h['provider_id']==native
                result['identity']=dict(provider_id=native,home=h['home'],away=h['away'],kickoff_utc=h['kickoff_utc'])
            else:
                h=titan_identity(cap['data']);assert str(h['ScheduleID'])==native
                result['identity']=dict(provider_id=native,home=h['hometeam_cn'],away=h['guestteam_cn'],kickoff_utc=h['kickoff_at'].isoformat())
            result['state']='RAW_AND_NATIVE_ID_VERIFIED'
        except Exception as error:
            result.update(state='FAILED',error_type=type(error).__name__,error=str(error))
        results.append(result);write_json_atomically(value=dict(results=results),path=Path(a.output))
        print(json.dumps(result),flush=True)
        if result['state']=='FAILED':raise SystemExit(2)
