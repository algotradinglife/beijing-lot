"""Factual competition/venue context, bound to immutable base and raw versions.

No fitting, fetching or import-time writes. Historical observations remain proxies.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup
from filelock import FileLock
import pyarrow as pa

from . import fundamentals, versioning
from .catalog import paths, registry
from .fundamental_tables import HISTORY_SCOPES
from .issue_schedule.contract import validate_issue_id
from .settlement_backfill import write_parquet_atomically
from .source_issue_update import arrow_table
from .unified_sources import canonical

FIXTURE_VALUES = dict(competition_id='character', competition='character',
                      source_route='character', neutral='logical')
HISTORY_VALUES = dict(competition_id='character', competition='character', explicit_neutral='logical')
SCHEMAS = {
    'source_fixture': dict(fixture_id='character', source='character', provider_id='character',
        home_id='character', away_id='character', **FIXTURE_VALUES, competition_url='character',home_header='character',
        url='character', observed_at='timestamp', sha256='character'),
    'fixture': dict(fixture_id='character', provider_id='character', home_id='character',
        away_id='character', **FIXTURE_VALUES, state='character'),
    'source_history': dict(fixture_id='character', source='character', scope='character',
        match_id='character', event_date='date', home_id='character', away_id='character',
        **HISTORY_VALUES, analysis_sha256='character', data_url='character',
        data_sha256='character', data_observed_at='timestamp'),
    'history': dict(fixture_id='character', scope='character', match_id='character',
        **HISTORY_VALUES, base_selected_source='character', state='character'),
    'reconciliation': dict(fixture_id='character', field='character', state='character',
        titan_json='character', nowscore_json='character', value_json='character', selected_source='character'),
    'provenance': dict(fixture_id='character', source='character', resource='character',
        url='character', observed_at='timestamp', sha256='character'),
}
KEYS = {'source_fixture':['fixture_id','source'], 'fixture':['fixture_id'],
    'source_history':['fixture_id','source','scope','match_id'],
    'history':['fixture_id','scope','match_id'], 'reconciliation':['fixture_id','field'],
    'provenance':['fixture_id','source','url']}


def _receipt(raw, receipt, source, url):
    """Validate original bytes, source URL and aware collection time; no mutation."""
    if (not isinstance(raw,bytes) or not isinstance(receipt,dict)
            or receipt.get('source')!=source or receipt.get('url')!=url
            or receipt.get('sha256')!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('context source receipt mismatch')
    if not isinstance(receipt.get('observed_at'),str) or datetime.fromisoformat(receipt['observed_at']).utcoffset() is None:
        raise ValueError('context collection time must be aware')


def parse_source_context(raw, *, fixture_id, source, identity, receipt,
                         auxiliary_raw=None, auxiliary_receipt=None):
    """Parse one verified fixture plus published historical metadata.

    Native fixture/provider/team IDs, full analysis and auxiliary response receipts
    are checked. Missing labels/markers stay null; explicit home is False, neutral
    True; historical unmarked venues stay unknown. Returns source rows/provenance,
    never writes. Scope/IDs come from the authoritative factual history parser.
    """
    if source not in {'titan','nowscore'} or not isinstance(fixture_id,str) or not fixture_id:
        raise ValueError('context fixture/source required')
    if not isinstance(identity,dict) or not all(isinstance(identity.get(k),str) and re.fullmatch(r'[1-9][0-9]*',identity[k])
               for k in ('provider_id','home_id','away_id')):
        raise ValueError('context native identities required')
    provider=identity['provider_id']
    if identity['home_id']==identity['away_id']:raise ValueError('distinct context target teams required')
    url=(f'https://zq.titan007.com/analysis/{provider}cn.htm' if source=='titan'
         else f'https://live.nowscore.com/analysis/{provider}cn.html')
    _receipt(raw,receipt,source,url)
    expected={k:identity.get(k) for k in ('provider_id','home','away','home_id','away_id','kickoff_utc')}
    if auxiliary_raw is not None or auxiliary_receipt is not None:
        if auxiliary_raw is None or auxiliary_receipt is None:
            raise ValueError('context auxiliary bytes/receipt pair required')
        _receipt(auxiliary_raw,auxiliary_receipt,source,
                 f'https://live.nowscore.com/analysisJs/data{provider}.js')
    record=fundamentals.analysis_record(raw,source=source,provider_id=provider,
        auxiliary_raw=auxiliary_raw,expected_identity=expected)
    if any(record[k]!=identity[k] for k in ('provider_id','home_id','away_id')):
        raise ValueError('context native identity mismatch')
    soup=BeautifulSoup(raw.decode('utf-8-sig'),'html.parser')
    links=soup.select('a.LName[href]' if source=='titan' else 'a.sclassName[href]')
    if len(links)>1:
        raise ValueError('ambiguous source competition links')
    competition=fundamentals.plain_text(str(links[0])) or None if links else None
    competition_url=links[0]['href'] if links else None
    competition_id=None
    if competition_url:
        address=urlsplit(competition_url)
        hosts=({'info.titan007.com','zq.titan007.com'} if source=='titan'
               else {'info.nowscore.com','live.nowscore.com'})
        if address.scheme not in ('','http','https') or (address.hostname and address.hostname not in hosts):
            raise ValueError('foreign source competition URL')
        if source=='titan':
            match=re.search(r'/(?:cupmatch_|league_)?([0-9]+)[.]html?$',address.path)
            competition_id=match[1] if match else None
        else:
            values=parse_qs(urlsplit(competition_url).query).get('id',[])
            if len(values)!=1 or not re.fullmatch('[0-9]+',values[0]):
                raise ValueError('invalid source competition URL identity')
            competition_id=values[0]
    route=('CUP_ROUTE' if competition_url and '/cup_match/' in competition_url else
           'LEAGUE_ROUTE' if competition_url and '/league_match/' in competition_url else None)
    href=(f'//zq.titan007.com/cn/team/Summary/{identity["home_id"]}.html' if source=='titan'
          else f'//info.nowscore.com/cn/team/Summary.aspx?teamid={identity["home_id"]}')
    header=soup.find('a',href=href)
    text=header.get_text(' ',strip=True) if header else None
    neutral=True if text and re.search(r'[（(]中[）)]',text) else (
        False if text and re.search(r'[（(]主[）)]',text) else None)
    fixture=dict(fixture_id=fixture_id,source=source,provider_id=provider,
        home_id=identity['home_id'],away_id=identity['away_id'],competition_id=competition_id,competition=competition,
        competition_url=competition_url,source_route=route,neutral=neutral,home_header=text,
        url=url,observed_at=receipt['observed_at'],sha256=receipt['sha256'])
    provenance=[dict(fixture_id=fixture_id,source=source,resource='analysis',
                     **{k:receipt[k] for k in ('url','observed_at','sha256')})]
    data_receipt=receipt
    if record['blocks_from_auxiliary']:
        if auxiliary_receipt is None:
            raise ValueError('context auxiliary receipt required')
        data_receipt=auxiliary_receipt
        provenance.append(dict(fixture_id=fixture_id,source=source,resource='auxiliary',
                               **{k:data_receipt[k] for k in ('url','observed_at','sha256')}))
    history=[]
    for item in record['history']:
        row=record['blocks'][item['block']][item['ordinal']]
        native=row[1]
        if native is not None and not ((type(native) is int and native>=0)
                or (isinstance(native,str) and re.fullmatch(r'[0-9]+',native))):
            raise ValueError('invalid historical competition ID')
        if row[2] is not None and not isinstance(row[2],str):
            raise ValueError('historical competition label must be text')
        history.append(dict(fixture_id=fixture_id,source=source,scope=HISTORY_SCOPES[item['block']],
            match_id=item['history_id'],event_date=item['event_date'],home_id=item['home_id'],
            away_id=item['away_id'],competition_id=None if native is None else str(native),
            competition=fundamentals.plain_text(str(row[2])) or None if row[2] is not None else None,
            explicit_neutral=True if re.search(r'[（(]中[）)]',str(row[5])) else None,
            analysis_sha256=receipt['sha256'],data_url=data_receipt['url'],
            data_sha256=data_receipt['sha256'],data_observed_at=data_receipt['observed_at']))
    return dict(fixture=fixture,history=history,provenance=provenance)


def _cell(fixture,field,a,b,preferred):
    """Retain both observations; conflicts are null, agreement prefers base source."""
    if preferred not in ('titan','nowscore'):raise ValueError('context preferred source required')
    state=('MISSING' if a is None and b is None else 'SUPPLEMENTED' if a is None else
           'PRIMARY_ONLY' if b is None else 'AGREEMENT' if a==b else 'CONFLICT')
    chosen=(preferred if state=='AGREEMENT' else
            {'SUPPLEMENTED':'nowscore','PRIMARY_ONLY':'titan'}.get(state))
    value=a if chosen=='titan' else b if chosen=='nowscore' else None
    return dict(fixture_id=fixture,field=field,state=state,
        titan_json=None if a is None else canonical(a),nowscore_json=None if b is None else canonical(b),
        value_json=None if value is None else canonical(value),selected_source=chosen)


def reconcile_context(parsed, base_fixtures, base_history):
    """Project exact base fixtures/history, retaining source cells and conflicts.

    Base rows must be JSON records read by R read_dataset(), with native fixture
    identities and historical party/date/selected-source keys. Every base history
    must have its selected source; observed historical identity mismatches fail
    closed. Metadata reconciliation does not alter base scores or source selection.
    """
    output={name:[] for name in SCHEMAS};fixtures={};history={}
    for p in parsed:
        f=p['fixture'];key=(f['fixture_id'],f['source'])
        if key in fixtures:raise ValueError('duplicate context fixture source')
        fixtures[key]=f;output['source_fixture'].append(f);output['provenance'].extend(p['provenance'])
        for row in p['history']:
            key=(row['fixture_id'],row['source'],row['scope'],row['match_id'])
            if key in history:raise ValueError('duplicate context source history')
            history[key]=row;output['source_history'].append(row)
    expected={(f['fixture_id'],s) for f in base_fixtures for s in ('titan','nowscore')}
    if set(fixtures)!=expected or len(expected)!=2*len(base_fixtures):
        raise ValueError('exact base two-source fixture set required')
    for f in base_fixtures:
        fid=f['fixture_id'];values={};states=[]
        for s in ('titan','nowscore'):
            if any(fixtures[(fid,s)][k]!=f[k] for k in ('provider_id','home_id','away_id')):
                raise ValueError('base context native identity mismatch')
        for name in FIXTURE_VALUES:
            cell=_cell(fid,name,fixtures[(fid,'titan')][name],fixtures[(fid,'nowscore')][name],'titan')
            if (name=='competition' and cell['state']=='CONFLICT'
                    and fixtures[(fid,'titan')]['competition_id'] is not None
                    and int(fixtures[(fid,'titan')]['competition_id'])>0
                    and fixtures[(fid,'titan')]['competition_id']==fixtures[(fid,'nowscore')]['competition_id']):
                cell.update(state='LABEL_VARIANT',value_json=cell['titan_json'],selected_source='titan')
            output['reconciliation'].append(cell);states.append(cell['state'])
            values[name]=None if cell['value_json'] is None else json.loads(cell['value_json'])
        output['fixture'].append(dict(fixture_id=fid,**{k:f[k] for k in ('provider_id','home_id','away_id')},
            **values,state='CONFLICT' if 'CONFLICT' in states else 'RESOLVED'))
    seen=set()
    for h in base_history:
        key=(h['fixture_id'],h['scope'],h['match_id'])
        if key in seen:raise ValueError('duplicate base history key')
        seen.add(key);chosen=h['selected_source']
        if chosen not in ('titan','nowscore') or (key[0],chosen,key[1],key[2]) not in history:
            raise ValueError('base selected history source missing')
        candidates={s:history.get((key[0],s,key[1],key[2])) for s in ('titan','nowscore')}
        for row in candidates.values():
            if row and any(row[k]!=h[k] for k in ('event_date','home_id','away_id')):
                raise ValueError('historical native party/date conflict')
        values={};states=[]
        for name in HISTORY_VALUES:
            a=candidates['titan'];b=candidates['nowscore']
            cell=_cell(key[0],f'history:{key[1]}:{key[2]}:{name}',None if a is None else a[name],
                       None if b is None else b[name],chosen)
            if (name=='competition' and cell['state']=='CONFLICT' and a and b
                    and a['competition_id'] is not None and int(a['competition_id'])>0
                    and a['competition_id']==b['competition_id']):
                cell.update(state='LABEL_VARIANT',value_json=cell[chosen+'_json'],selected_source=chosen)
            output['reconciliation'].append(cell);states.append(cell['state'])
            values[name]=None if cell['value_json'] is None else json.loads(cell['value_json'])
        output['history'].append(dict(fixture_id=key[0],scope=key[1],match_id=key[2],**values,
            base_selected_source=chosen,state='CONFLICT' if 'CONFLICT' in states else 'RESOLVED'))
    return output


def context_arrow_table(rows, schema):
    """Reuse existing scalar/date bridge; Arrow bool columns preserve True/False/null."""
    if any(set(row)!=set(schema) for row in rows):raise ValueError('context table columns mismatch')
    scalars={k:v for k,v in schema.items() if v!='logical'}
    table=arrow_table([{k:row[k] for k in scalars} for row in rows],scalars)
    for name,kind in schema.items():
        if kind=='logical':
            values=[row[name] for row in rows]
            if any(value is not None and type(value) is not bool for value in values):
                raise ValueError('explicit logical scalar required')
            table=table.append_column(name,pa.array(values,type=pa.bool_()))
    return table.select(list(schema))


def publish_fundamentals_context(*, issue, base_version, base_manifest_sha256,
        raw_evidence_relative, raw_manifest_sha256, base_reader, environ):
    """Parse pinned original bytes and publish six registered contextual tables.

    base_reader(dataset,table,version,root) is the authoritative R read_dataset
    boundary returning JSON identity/history records; the public R wrapper supplies
    it. Exact base cardinalities, original bytes/times and native fixture/history
    identities are verified. Existing identical input/code is verified then reused;
    catalog failures restore the prior pointer. Never changes base or forecasts.
    All paths/versions/hashes are explicit; all data remain historical proxies.
    """
    validate_issue_id(issue)
    frozen=paths.root_path('frozen',environ=environ);paths.root_path('hot',environ=environ)
    base_path=versioning.version_directory(paths.dataset_path('source_issue_'+issue,environ=environ),base_version)/'manifest.json'
    if versioning.sha256_file(base_path)!=base_manifest_sha256:
        raise ValueError('context base manifest hash mismatch')
    if Path(raw_evidence_relative).is_absolute() or '..' in Path(raw_evidence_relative).parts:
        raise ValueError('context relative raw archive required')
    raw=(frozen/raw_evidence_relative).resolve()
    if not raw.is_relative_to(frozen) or versioning.sha256_file(raw/'asset-manifest.json')!=raw_manifest_sha256:
        raise ValueError('context raw manifest mismatch')
    raw_manifest=json.loads((raw/'asset-manifest.json').read_text())
    if (raw_manifest.get('dataset')!='source_issue_'+issue or raw_manifest.get('version')!=base_version
            or raw_manifest.get('base_manifest_sha256')!=base_manifest_sha256
            or versioning.sha256_file(raw/'raw-receipts.json')!=raw_manifest['members']['raw-receipts.json']):
        raise ValueError('context raw/base receipt mismatch')
    if not callable(base_reader):raise ValueError('context authoritative R base reader required')
    base=json.loads(base_path.read_text());base_rows={}
    for table,columns in [('match',('fixture_id','provider_id','home_id','away_id')),
            ('history',('fixture_id','scope','match_id','event_date','home_id','away_id','selected_source'))]:
        rows=json.loads(base_reader('source_issue_'+issue,table,base_version,str(frozen)))
        if (not isinstance(rows,list) or len(rows)!=base['tables'][table]['rows']
                or any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k] for k in columns) for row in rows)):
            raise ValueError('context typed base rows/cardinality required')
        base_rows[table]=rows
    fixture_ids=[f['fixture_id'] for f in base_rows['match']]
    if len(set(fixture_ids))!=len(fixture_ids) or any(not re.fullmatch(re.escape(issue)+r':[1-9][0-9]*',fid) for fid in fixture_ids):
        raise ValueError('context exact issue fixture identities required')
    receipts=json.loads((raw/'raw-receipts.json').read_text());index={}
    for r in receipts:
        key=(r['fixture_id'],r['source'],r['url'])
        if (not isinstance(r.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',r['sha256'])
                or key in index or r['path']!='raw/'+r['sha256']+'.bin'):
            raise ValueError('context unique canonical raw receipts required')
        if versioning.sha256_file(raw/r['path'])!=r['sha256']:
            raise ValueError('context original source bytes mismatch')
        at=datetime.fromisoformat(r['capture_observed_at'])
        if at.utcoffset() is None:raise ValueError('context capture timestamp must be aware')
        index[key]=r
    implementation={name:versioning.sha256_file(Path(__file__).parent/name) for name in
        ('fundamentals_context.py','fundamentals.py','fundamental_tables.py','source_issue_update.py',
         'unified_sources.py','versioning.py','settlement_backfill.py','catalog/paths.py','catalog/registry.py')}
    source=dict(issue=issue,base_dataset='source_issue_'+issue,base_version=base_version,
        base_manifest_sha256=base_manifest_sha256,raw_evidence_relative=raw_evidence_relative,
        raw_manifest_sha256=raw_manifest_sha256,base_rows_sha256=hashlib.sha256(canonical(base_rows).encode()).hexdigest(),
        availability_class='HISTORICAL_PROXY',historical_admission=False,implementation_sha256=implementation)
    identity=hashlib.sha256(canonical(source).encode()).hexdigest()
    name='source_fundamentals_context_'+issue
    destination=paths.dataset_path(name,require_exists=False,environ=environ)
    schema_id='beidan_fundamentals_context_v1'
    schema=dict(schema_id=schema_id,tables=SCHEMAS,keys=KEYS,
        nullable='unknown markers and conflicted cells null; identifiers remain character',
        meaning='factual source context; native-ID label variants retained; historical proxies only')
    with FileLock(paths.catalog_root(environ=environ)/'source-issue-publication.lock',timeout=30):
        cached=_cached_context(destination,registry.load_catalog(environ=environ),identity,name,schema,environ)
        if cached:return cached
    parsed=[]
    for f in base_rows['match']:
        for s in ('titan','nowscore'):
            url=(f'https://zq.titan007.com/analysis/{f["provider_id"]}cn.htm' if s=='titan'
                 else f'https://live.nowscore.com/analysis/{f["provider_id"]}cn.html')
            captured=index[(f['fixture_id'],s,url)]
            receipt={k:captured[k] for k in ('source','url','sha256')}
            receipt['observed_at']=captured['capture_observed_at']
            aux=index.get((f['fixture_id'],s,f'https://live.nowscore.com/analysisJs/data{f["provider_id"]}.js'))
            ar=None
            if aux:
                ar={k:aux[k] for k in ('source','url','sha256')};ar['observed_at']=aux['capture_observed_at']
            parsed.append(parse_source_context((raw/captured['path']).read_bytes(),
                fixture_id=f['fixture_id'],source=s,identity=f,receipt=receipt,
                auxiliary_raw=(raw/aux['path']).read_bytes() if aux else None,auxiliary_receipt=ar))
    tables=reconcile_context(parsed,base_rows['match'],base_rows['history'])
    for table,rows in tables.items():
        keys=KEYS[table];seen=set()
        for row in rows:
            key=tuple(row[k] for k in keys)
            if any(v is None for v in key) or key in seen:raise ValueError('context table key violation')
            seen.add(key)
    with FileLock(paths.catalog_root(environ=environ)/'source-issue-publication.lock',timeout=30):
        catalog=registry.load_catalog(environ=environ)
        cached=_cached_context(destination,catalog,identity,name,schema,environ)
        if cached:return cached
        previous=versioning.read_current(destination)
        label=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        def write(directory):
            entries={}
            for table,rows in tables.items():
                info=write_parquet_atomically(context_arrow_table(rows,SCHEMAS[table]),directory/'tables'/(table+'.parquet'))
                entries[table]=dict(kind='whole',rows=info['rows'],files=[dict(name=table+'.parquet',rows=info['rows'],sha256=info['sha256'])])
            versioning.write_json_atomically(dict(version=label,tables=entries,source=source),directory/'manifest.json')
            versioning.write_json_atomically(source,directory/'receipt.json')
            return dict(identity_sha256=identity,manifest_sha256=versioning.sha256_file(directory/'manifest.json'),
                        receipt_sha256=versioning.sha256_file(directory/'receipt.json'))
        try:
            result=versioning.publish_version(destination,label,write)
            versioning.write_json_atomically(schema,
                paths.schema_path(schema_id,require_exists=False,environ=environ))
            catalog['datasets'][name]=dict(kind='dataset',format='parquet',location='frozen:datasets/'+name,
                schema_id=schema_id,version=label,owner='collector:fundamentals-context',retention='retained',
                tables=len(SCHEMAS),manifest=f'datasets/{name}/versions/{label}/manifest.json')
            versioning.write_json_atomically(catalog,registry.catalog_path(environ=environ))
        except Exception:
            final=versioning.version_directory(destination,label)
            if final.exists():os.replace(final,destination/('.failed-'+label))
            if previous is None:(destination/'current.json').unlink(missing_ok=True)
            else:versioning.write_json_atomically(previous,destination/'current.json')
            raise
    return dict(status=result['status'],dataset=name,version=label)


def _cached_context(destination,catalog,identity,name,schema,environ):
    """Verify a matching immutable target and catalog/schema binding; no writes."""
    previous=versioning.read_current(destination)
    if previous is None or previous.get('identity_sha256')!=identity:return None
    entry=catalog['datasets'].get(name,{})
    expected=dict(kind='dataset',format='parquet',location='frozen:datasets/'+name,
                  schema_id=schema['schema_id'],version=previous['label_version'],tables=len(SCHEMAS))
    if any(entry.get(k)!=v for k,v in expected.items()):
        raise versioning.VersionError('context catalog/current mismatch')
    schema_path=paths.schema_path(schema['schema_id'],require_exists=False,environ=environ)
    if not schema_path.is_file() or json.loads(schema_path.read_text())!=schema:
        raise versioning.VersionError('context published schema mismatch')
    _verify_context_version(destination,previous)
    return dict(status='unchanged',dataset=name,version=previous['label_version'])


def _verify_context_version(base,current):
    """Verify the immutable no-op target's metadata and every declared table file."""
    directory=versioning.version_directory(base,current['label_version'])
    if versioning.content_digest(directory)!=current['content_digest']:
        raise versioning.VersionError('context data digest mismatch')
    for name,key in [('manifest.json','manifest_sha256'),('receipt.json','receipt_sha256')]:
        if versioning.sha256_file(directory/name)!=current[key]:
            raise versioning.VersionError('context metadata hash mismatch')
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['version']!=current['label_version'] or set(manifest['tables'])!=set(SCHEMAS):
        raise versioning.VersionError('context manifest table set mismatch')
    for table,entry in manifest['tables'].items():
        if len(entry['files'])!=1 or entry['files'][0]['name']!=table+'.parquet':
            raise versioning.VersionError('context table file identity mismatch')
        if versioning.sha256_file(directory/'tables'/entry['files'][0]['name'])!=entry['files'][0]['sha256']:
            raise versioning.VersionError('context table hash mismatch')
