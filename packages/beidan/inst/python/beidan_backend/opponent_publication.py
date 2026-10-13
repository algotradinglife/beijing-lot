"""One immutable NAS dataset for the bounded opponent-lambda diagnostic."""
import hashlib
import json
import os
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow as pa
from filelock import FileLock
from .catalog import paths, registry
from . import versioning
from .settlement_backfill import write_parquet_atomically
from .temporal_learning import Cutoff
from .temporal_learning.serialized_opponent_fit import validate_serialized_opponent_fit
from .temporal_learning.provenance import verify_implementation_closure

KEYS={'audit':['fixture_id'],'probabilities':['fixture_id','model','outcome'],
      'metrics':['cohort','issue_id','comparison','model'],
      'lambdas':['fixture_id'],'margins':['fixture_id','model','stage','margin'],
      'coefficients':['fixture_id','term'],'observations':['fixture_id','row_key'],
      'support':['fixture_id','team_id','venue'],'snapshots':['snapshot_id']}


def publish_opponent_research(tables, receipt, label, *, environ, repository_root):
    """Publish typed diagnostic tables and complete fitting/cutoff evidence.

    Tables are explicit Arrow objects keyed as KEYS. Audit lists every attempted
    native fixture with a UTC cutoff; lambdas/probabilities/observations etc.
    contain only successfully estimated fixtures. Receipt binds input/code
    hashes, independent replay, fitting receipts and full shared weight ledgers.
    Historical proxies cannot authorize prospective use. Uses existing atomic
    writers, catalog roots, shared publication lock and publish_version().
    Same label cannot change content/bindings. On a failure the prior catalog
    and current pointer are restored; rejected versions remain inventoried.
    No fetching, fitting or selection. Empty/malformed inputs fail closed.
    """
    root=Path(repository_root)
    if (set(tables)!=set(KEYS) or not isinstance(receipt,dict)
            or receipt.get('intended_use')!='POSTHOC_HISTORICAL_DIAGNOSTIC'
            or receipt.get('formal_FM_unchanged')is not True):
        raise ValueError('Complete diagnostic tables and unchanged formal FM required')
    for key in ['input_hashes','implementation_hashes']:
        if not receipt.get(key) or not all(isinstance(v,str) and len(v)==64 and
            all(c in '0123456789abcdef' for c in v) for v in receipt[key].values()):
            raise ValueError('Complete SHA256 input and code identities required')
    if (receipt.get('independent_replay',{}).get('status')!='FULL_IDENTICAL_REPLAY'
            or receipt['independent_replay'].get('sha256')!=receipt['input_hashes'].get('forecasts')):
        raise ValueError('Independent exact forecast replay required')
    if not receipt.get('publication_implementation'):raise ValueError('Transitive publication implementation required')
    verify_implementation_closure(root,receipt['publication_implementation'])
    frames={}
    for name,table in tables.items():
        if not isinstance(table,pa.Table) or not set(KEYS[name])<=set(table.column_names):
            raise ValueError('Arrow tables and complete keys required')
        frame=table.to_pandas()
        if frame.empty or frame[KEYS[name]].isna().any().any() or frame.duplicated(KEYS[name]).any():
            raise ValueError('Nonempty unique non-null table keys required: '+name)
        for column in set(KEYS[name])&{'fixture_id','model','outcome','issue_id','team_id','row_key'}:
            if not (pa.types.is_string(table.schema.field(column).type) or pa.types.is_large_string(table.schema.field(column).type)):
                raise ValueError('Character identity types required')
        frames[name]=frame
    audit=frames['audit'];estimated=set(audit.fixture_id[audit.state.eq('ESTIMATED')])
    snapshots=frames['snapshots']
    if not {'snapshot_id','payload','sha256'}<=set(snapshots):raise ValueError('Complete replay snapshot payloads required')
    for row in snapshots.itertuples():
        if not isinstance(row.payload,str) or hashlib.sha256(row.payload.encode('utf-8')).hexdigest()!=row.sha256:
            raise ValueError('Replay snapshot payload digest differs')
    if (not estimated or set(frames['lambdas'].fixture_id)!=estimated
            or set(receipt.get('fits',{}))!=estimated or set(receipt.get('cutoffs',{}))!=set(audit.fixture_id)):
        raise ValueError('Exact audit, estimate, fitting receipt and cutoff scopes required')
    if (not pa.types.is_timestamp(tables['audit'].schema.field('cutoff_utc').type)
            or tables['audit'].schema.field('cutoff_utc').type.tz!='UTC' or audit.cutoff_utc.isna().any()):
        raise ValueError('Typed UTC fixture cutoffs required')
    for row in audit.itertuples():
        cutoff=Cutoff.decision_epoch(row.fixture_id.split(':')[0],receipt['cutoffs'][row.fixture_id])
        if row.cutoff_utc!=cutoff.cutoff_ts:raise ValueError('Audit cutoff differs from receipt')
        if row.fixture_id not in estimated:continue
        validate_serialized_opponent_fit(receipt['fits'][row.fixture_id],cutoff,root)
    for name in ['probabilities','margins','coefficients','observations','support']:
        if not set(frames[name].fixture_id)<=estimated:raise ValueError('Unestimated or foreign fixture in model tables')
    for name in ['probabilities','margins']:
        f=frames[name]
        if (not f.probability.between(0,1).all() or f.probability.isna().any()):raise ValueError('Finite probability masses required')
        group=['fixture_id','model']+(['stage'] if name=='margins' else [])
        if not f.groupby(group).probability.sum().sub(1).abs().lt(1e-8).all():raise ValueError('Normalized probability triples/grids required')
        if name=='probabilities' and (not f.outcome.isin(['W','D','L']).all() or not f.groupby(group).size().eq(3).all()):
            raise ValueError('Complete W/D/L probability triples required')
    for column in ['lambda_home','lambda_away']:
        if not frames['lambdas'][column].gt(0).all() or not np.isfinite(frames['lambdas'][column]).all():raise ValueError('Positive finite goal means required')
    base=paths.dataset_path('fm17_opponent_research',require_exists=False,environ=environ)
    paths.root_path('hot',environ=environ)
    binding=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    destination=versioning.version_directory(base,label)
    with FileLock(paths.catalog_root(environ=environ)/'source-issue-publication.lock',timeout=30):
        catalog=registry.load_catalog(environ=environ);old_catalog=json.loads(json.dumps(catalog))
        previous=versioning.read_current(base)
        if destination.exists() and json.loads((destination/'receipt.json').read_bytes())!=receipt:
            raise versioning.VersionError('Published fitting receipt identity differs')
        def write(directory):
            entries={}
            for name,table in tables.items():
                path=directory/'tables'/(name+'.parquet');result=write_parquet_atomically(table,path)
                entries[name]=dict(kind='whole',rows=result['rows'],files=[dict(name=path.name,rows=result['rows'],sha256=result['sha256'])])
            versioning.write_json_atomically(dict(version=label,tables=entries,source=receipt),directory/'manifest.json')
            versioning.write_json_atomically(receipt,directory/'receipt.json')
            return dict(binding_sha256=binding)
        published=False
        try:
            result=versioning.publish_version(base,label,write);published=result['status']=='published'
            schema_id='fm17_opponent_research_v1'
            versioning.write_json_atomically(dict(schema_id=schema_id,keys=KEYS,
                tables={k:{f.name:str(f.type) for f in t.schema} for k,t in tables.items()},
                nullable='Audit lambda/metadata columns null for unestimated fixtures; all model probability keys and values nonnull.',
                intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC'),paths.schema_path(schema_id,require_exists=False,environ=environ))
            catalog['datasets']['fm17_opponent_research']=dict(kind='dataset',format='parquet',
                location='frozen:datasets/fm17_opponent_research',schema_id=schema_id,
                version=result['current']['label_version'],owner='research:fm17-opponent-lambda',retention='retained',tables=len(tables))
            versioning.write_json_atomically(catalog,registry.catalog_path(environ=environ))
        except BaseException:
            if published:
                if registry.load_catalog(environ=environ)!=old_catalog:
                    versioning.write_json_atomically(old_catalog,registry.catalog_path(environ=environ))
                if previous is None:(base/'current.json').unlink(missing_ok=True)
                else:versioning.write_json_atomically(previous,base/'current.json')
                os.replace(destination,base/('.failed-'+label))
            raise
    return dict(dataset='fm17_opponent_research',version=result['current']['label_version'],
                status=result['status'],binding_sha256=binding)
