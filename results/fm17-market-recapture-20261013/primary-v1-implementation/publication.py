"""Immutable diagnostic market snapshots on the single catalog/version lifecycle."""
import hashlib
import json
import os
from pathlib import Path
from filelock import FileLock
import pyarrow as pa
from beidan_backend.catalog import paths, registry
from beidan_backend import versioning
from beidan_backend.settlement_backfill import write_parquet_atomically


KEYS = {'history': ['fixture_id', 'market', 'sequence'],
        'latest': ['fixture_id', 'market', 'company_id'],
        'coverage': ['fixture_id', 'market'], 'provenance':['fixture_id','market']}


def publish_market_snapshot(tables: dict, receipt: dict, label: str, *, environ: dict) -> dict:
    """Publish explicit Arrow tables and immutable source/cutoff receipt.

    Tables are history/latest/coverage/provenance; each is keyed as KEYS, and coverage has
    all three markets per fixture. Every table includes string fixture/market,
    UTC timestamp quote_at (history/latest) or cutoff_utc (coverage). History
    has boolean prior; latest has boolean qualified/fresh/supported and decimal
    prices. This is diagnostic data, never a prospective availability claim.
    roots come only from explicit environ through catalog.paths. Writes use
    read-back/rename helpers and shared versioning; catalog's existing source
    publication lock serializes registrations. Same label requires both data
    and binding identity unchanged. Failure after version publication restores
    prior pointer and preserves rejected output outside the version namespace.
    Returns the registered dataset/version/root and source binding identity.
    """
    if set(tables) != set(KEYS) or not isinstance(receipt,dict) or receipt.get('historical_admitted') is not False:
        raise ValueError('Diagnostic tables and false historical admission required')
    required_receipt = {'scope_sha256','input_hashes','implementation_hashes','cutoffs'}
    if not required_receipt <= set(receipt) or not receipt['input_hashes'] or not receipt['implementation_hashes']:
        raise ValueError('Explicit source, code and cutoff bindings required')
    for hashes in [receipt['input_hashes'],receipt['implementation_hashes'],{'scope':receipt['scope_sha256']}]:
        if not all(isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in hashes.values()):
            raise ValueError('SHA256 bindings required')
    frames={}
    for name,table in tables.items():
        if not isinstance(table,pa.Table) or not set(KEYS[name])<=set(table.column_names):
            raise ValueError('Arrow table and explicit keys required')
        for col in ['fixture_id','market']:
            if not (pa.types.is_string(table.schema.field(col).type) or pa.types.is_large_string(table.schema.field(col).type)):
                raise ValueError('String identity columns required')
        clock='cutoff_utc' if name in {'coverage','provenance'} else 'quote_at'
        if clock not in table.column_names or not pa.types.is_timestamp(table.schema.field(clock).type) or table.schema.field(clock).type.tz!='UTC':
            raise ValueError('Typed UTC clock required')
        frame=table.to_pandas()
        if frame[KEYS[name]+[clock]].isna().any().any() or frame.duplicated(KEYS[name]).any():
            raise ValueError('Unique non-null table keys and clocks required')
        if not frame.market.isin(['euro','asian','totals']).all():raise ValueError('Unknown market')
        frames[name]=frame
    coverage=frames['coverage']
    if coverage.empty or not coverage.groupby('fixture_id').size().eq(3).all():
        raise ValueError('Complete three-market coverage ledger required')
    if set(receipt['cutoffs']) != set(coverage.fixture_id):raise ValueError('Exact cutoff fixture scope required')
    for row in coverage.itertuples():
        if row.cutoff_utc.isoformat()!=receipt['cutoffs'][row.fixture_id]:raise ValueError('Cutoff receipt differs')
    if set(zip(frames['provenance'].fixture_id,frames['provenance'].market))!=set(zip(coverage.fixture_id,coverage.market)):
        raise ValueError('Exact provenance ledger scope required')
    provenance=frames['provenance']
    needed={'source_url','collected_at','response_sha256','request_error','availability','parser_sha256','packet_sha256'}
    if not needed<=set(provenance):raise ValueError('Full source provenance required')
    if not pa.types.is_timestamp(tables['provenance'].schema.field('collected_at').type) or tables['provenance'].schema.field('collected_at').type.tz!='UTC' or provenance.collected_at.isna().any():
        raise ValueError('Typed original collection clock required')
    for row in provenance.itertuples():
        if row.cutoff_utc.isoformat()!=receipt['cutoffs'][row.fixture_id] or row.availability!='HISTORICAL_QUOTE_PROXY':raise ValueError('Provenance cutoff/class differs')
        if not isinstance(row.source_url,str) or not row.source_url.startswith('https://'):raise ValueError('Source URL required')
        if not isinstance(row.request_error,str):raise ValueError('Explicit request status required')
        hashes=[row.parser_sha256,row.packet_sha256]
        if not row.request_error:hashes.append(row.response_sha256)
        if not all(isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in hashes):raise ValueError('Source response/parser hashes required')
    for name in ['history','latest']:
        f=frames[name]
        if not set(f.fixture_id)<=set(coverage.fixture_id):raise ValueError('Foreign quote fixture')
        if name=='history':
            if not pa.types.is_boolean(tables[name].schema.field('prior').type) or f.prior.isna().any():raise ValueError('Typed prior status required')
        else:
            for col in ['qualified','fresh','supported']:
                if not pa.types.is_boolean(tables[name].schema.field(col).type) or f[col].isna().any():raise ValueError('Typed eligibility status required')
        admitted=f if name=='latest' else f[f.prior]
        import pandas as pd
        boundaries=admitted.fixture_id.map(receipt['cutoffs']).map(pd.Timestamp)
        if not (admitted.quote_at < boundaries).all():raise ValueError('Prior quote exceeds bound cutoff')
    frozen=paths.root_path('frozen',environ=environ);paths.root_path('hot',environ=environ)
    name='fm17_replayed_markets';base=paths.dataset_path(name,require_exists=False,environ=environ)
    binding=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    lock=paths.catalog_root(environ=environ)/'source-issue-publication.lock'
    with FileLock(lock,timeout=30):
        catalog=registry.load_catalog(environ=environ);previous=versioning.read_current(base)
        destination=versioning.version_directory(base,label)
        if destination.exists():
            old=json.loads((destination/'receipt.json').read_bytes())
            if old!=receipt:raise versioning.VersionError('Published receipt binding differs')
        def write(directory):
            entries={}
            for key,table in tables.items():
                path=directory/'tables'/(key+'.parquet')
                written=write_parquet_atomically(table,path)
                entries[key]=dict(kind='whole',rows=written['rows'],files=[dict(name=path.name,rows=written['rows'],sha256=written['sha256'])])
            versioning.write_json_atomically(dict(version=label,tables=entries,source=receipt),directory/'manifest.json')
            versioning.write_json_atomically(receipt,directory/'receipt.json')
            return dict(binding_sha256=binding,manifest_sha256=versioning.sha256_file(directory/'manifest.json'))
        published=False
        try:
            result=versioning.publish_version(base,label,write)
            published=result['status']=='published'
            catalog['datasets'][name]=dict(kind='dataset',format='parquet',location='frozen:datasets/'+name,
                schema_id='fm17_replayed_markets_v1',version=result['current']['label_version'],owner='collector:fm17-market-replay',retention='retained',tables=4)
            versioning.write_json_atomically(dict(schema_id='fm17_replayed_markets_v1',keys=KEYS,
                tables={k:{f.name:str(f.type) for f in t.schema} for k,t in tables.items()},
                nullable='Unused market price columns are null; quote keys/clocks/flags not null; missing market newest age null.',historical_admitted=False),paths.schema_path('fm17_replayed_markets_v1',require_exists=False,environ=environ))
            versioning.write_json_atomically(catalog,registry.catalog_path(environ=environ))
        except Exception:
            if published:
                os.replace(destination,base/('.failed-'+label))
                if previous is None:(base/'current.json').unlink(missing_ok=True)
                else:versioning.write_json_atomically(previous,base/'current.json')
            raise
    return dict(dataset=name,version=label,root=str(frozen),status=result['status'],binding_sha256=binding,historical_admitted=False)
