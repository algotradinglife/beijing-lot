"""Source-published cup group standings, separate from league standings.

No fetching, fitting, or import-time I/O. Missing sections stay missing; zero
played matches are real published zeroes. Observations and cell reconciliation
are retained beside effective rows; none authorize historical pregame use.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from bs4 import BeautifulSoup
from filelock import FileLock

from . import fundamentals, versioning
from .catalog import paths, registry
from .issue_schedule.contract import validate_issue_id
from .settlement_backfill import write_parquet_atomically
from .source_issue_update import arrow_table
from .unified_sources import canonical

METRICS = ('rank', 'played', 'wins', 'draws', 'losses', 'goals_for',
           'goals_against', 'goal_difference', 'points')
VALUES = dict(team_name='character', **{k: 'integer' for k in METRICS})
SCHEMAS = {
    'source_standings': dict(fixture_id='character', source='character',
        group_membership_sha256='character', team_id='character', **VALUES,
        goal_difference_basis='character', url='character', observed_at='timestamp', sha256='character'),
    'standings': dict(fixture_id='character', group_membership_sha256='character',
        team_id='character', **VALUES, state='character'),
    'coverage': dict(fixture_id='character', source='character', state='character',
        group_count='integer', team_rows='integer'),
    'reconciliation': dict(fixture_id='character', field='character', state='character',
        titan_json='character', nowscore_json='character', value_json='character', selected_source='character'),
    'provenance': dict(fixture_id='character', source='character', url='character',
        observed_at='timestamp', sha256='character'),
}
KEYS = {'source_standings': ['fixture_id','source','group_membership_sha256','team_id'],
        'standings': ['fixture_id','group_membership_sha256','team_id'],
        'coverage': ['fixture_id','source'], 'reconciliation': ['fixture_id','field'],
        'provenance': ['fixture_id','source']}


def parse_cup_standings(raw, *, fixture_id, source, identity, receipt):
    """Parse one exact analysis response into source observations and coverage.

    ``identity`` requires provider_id, home_id, away_id (text native IDs).
    ``receipt`` requires source/url/observed_at/sha256; timestamp must be aware.
    Native fixture/orientation and bytes are verified by the authoritative
    identity parser before optional tables. Returns missing coverage when no
    published cup table exists; malformed, duplicated, foreign or inconsistent
    tables raise ValueError. Nowscore omits GD; GF-GA is explicitly labelled.
    Source group identity is the SHA256 of its sorted full team membership,
    never a claimed native competition/group ID. No writes or network calls.
    """
    if not isinstance(fixture_id,str) or not fixture_id or source not in {'titan','nowscore'}:
        raise ValueError('fixture/source required')
    if not isinstance(identity,dict) or not all(isinstance(identity.get(k),str) and re.fullmatch(r'[1-9][0-9]*',identity[k]) for k in ('provider_id','home_id','away_id')):
        raise ValueError('native identities required')
    if identity['home_id']==identity['away_id']:
        raise ValueError('distinct target teams required')
    url = (f"https://zq.titan007.com/analysis/{identity['provider_id']}cn.htm" if source=='titan'
           else f"https://live.nowscore.com/analysis/{identity['provider_id']}cn.html")
    if (not isinstance(raw,bytes) or receipt.get('source')!=source or receipt.get('url')!=url
            or receipt.get('sha256')!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('raw source receipt mismatch')
    at=datetime.fromisoformat(receipt['observed_at'])
    if at.utcoffset() is None:
        raise ValueError('aware collection timestamp required')
    expected={k: identity.get(k) for k in ('provider_id','home','away','home_id','away_id','kickoff_utc')}
    record=fundamentals.analysis_record(raw,source=source,provider_id=identity['provider_id'],
        identity_only=True,expected_identity=expected)
    if any(record[k]!=identity[k] for k in ('provider_id','home_id','away_id')):
        raise ValueError('target native identity mismatch')
    soup=BeautifulSoup(raw.decode('utf-8-sig'),'html.parser')
    if source=='titan':
        containers=soup.select('#cupScore')
        if len(containers)>1:
            raise ValueError('duplicate cup section')
        tables=containers[0].find_all('table') if containers else []
        header=['排名','球队','总','胜','平','负','得','失','净','积分']
    else:
        tables=soup.select('table.cup_jifen')
        header=['排名','球队','赛','胜','平','负','得','失','积分']
    output=[]; groups=set()
    for table in tables:
        if table.find('table'):
            raise ValueError('nested cup tables are ambiguous')
        parsed=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all(['td','th'],recursive=False)
            text=[fundamentals.plain_text(str(td)) for td in cells]
            if not parsed and text==header:
                parsed.append(None)
                continue
            if not parsed or len(text)!=len(header) or text==header:
                raise ValueError('invalid cup table header/shape')
            links=cells[1].find_all('a',href=True)
            if len(links)!=1:
                raise ValueError('one native team link required')
            native=re.fullmatch(r'//(?:zq[.]titan007[.]com|info[.]nowscore[.]com)/cn/team/Summary/([1-9][0-9]*)[.]html',links[0]['href'])
            if native is None or not text[1]:
                raise ValueError('invalid cup team identity')
            numbers=[text[0],*text[2:]]
            if any(not re.fullmatch(r'-?[0-9]+',n) for n in numbers):
                raise ValueError('invalid cup integer')
            numeric=list(map(int,numbers))
            if source=='nowscore':
                numeric.insert(7,numeric[5]-numeric[6])
            values=dict(zip(METRICS,numeric))
            if (any(not -(2**31)<n<2**31 for n in numeric) or values['rank']<=0
                or any(values[k]<0 for k in METRICS if k not in {'goal_difference','points'})
                or values['played']!=sum(values[k] for k in ('wins','draws','losses'))
                or values['goal_difference']!=values['goals_for']-values['goals_against']):
                raise ValueError('inconsistent cup numeric relations')
            parsed.append(dict(team_id=native[1],team_name=text[1],**values))
        if not parsed:
            raise ValueError('cup table missing header')
        team_rows=parsed[1:]
        ids=[row['team_id'] for row in team_rows]
        if len(ids)!=len(set(ids)):
            raise ValueError('duplicate cup team')
        if ids and not {identity['home_id'],identity['away_id']}.issubset(ids):
            raise ValueError('cup table omits target teams')
        group=hashlib.sha256(canonical(sorted(ids)).encode()).hexdigest()
        if group in groups:
            raise ValueError('duplicate cup group')
        groups.add(group)
        for row in team_rows:
            output.append(dict(fixture_id=fixture_id,source=source,group_membership_sha256=group,
                **row,goal_difference_basis='PUBLISHED' if source=='titan' else 'GOALS_FOR_MINUS_AGAINST',
                **{k:receipt[k] for k in ('url','observed_at','sha256')}))
    return dict(fixture_id=fixture_id,source=source,rows=output,
        coverage=dict(fixture_id=fixture_id,source=source,
            state='ABSENT' if not tables else 'POPULATED' if output else 'PUBLISHED_EMPTY',
            group_count=None if not tables else len(groups),team_rows=None if not tables else len(output)),
        groups=None if not tables else sorted(groups),
        provenance=dict(fixture_id=fixture_id,source=source,**{k:receipt[k] for k in ('url','observed_at','sha256')}))


def reconcile_cup_standings(parsed_sources):
    """Build five factual tables from distinct validated fixture/source parses.

    All source observations remain. Differing full group memberships quarantine
    effective groups; differing cells are null in effective rows and retain
    both originals in reconciliation. No market, imputation, or fitting occurs.
    Empty input returns typed-schema-compatible empty row lists.
    """
    tables={key:[] for key in SCHEMAS}; by_fixture={}
    for parsed in parsed_sources:
        fixture,source=parsed['fixture_id'],parsed['source']
        if source not in {'titan','nowscore'} or source in by_fixture.setdefault(fixture,{}):
            raise ValueError('duplicate/invalid fixture source')
        by_fixture[fixture][source]=parsed
        tables['source_standings'].extend(parsed['rows'])
        tables['coverage'].append(parsed['coverage']);tables['provenance'].append(parsed['provenance'])
    for fixture,sources in sorted(by_fixture.items()):
        left,right=sources.get('titan'),sources.get('nowscore')
        a,b=left['groups'] if left else None,right['groups'] if right else None
        membership=_reconcile_cell(fixture,'group_membership',a,b)
        tables['reconciliation'].append(membership)
        if membership['value_json'] is None:
            continue
        groups=json.loads(membership['value_json'])
        indexed={source:{(r['group_membership_sha256'],r['team_id']):r for r in parsed['rows']} for source,parsed in sources.items()}
        keys=sorted(set().union(*(set(rows) for rows in indexed.values())))
        for group,team in keys:
            if group not in groups:
                continue
            a=indexed.get('titan',{}).get((group,team),{})
            b=indexed.get('nowscore',{}).get((group,team),{})
            row=dict(fixture_id=fixture,group_membership_sha256=group,team_id=team)
            states=[]
            for field in VALUES:
                cell=_reconcile_cell(fixture,f'group:{group}:{team}:{field}',a.get(field),b.get(field))
                tables['reconciliation'].append(cell);states.append(cell['state'])
                row[field]=None if cell['value_json'] is None else json.loads(cell['value_json'])
            row['state']='CONFLICT' if 'CONFLICT' in states else membership['state']
            tables['standings'].append(row)
    for name,keys in KEYS.items():
        seen=set()
        for row in tables[name]:
            key=tuple(row[k] for k in keys)
            if key in seen or any(k is None for k in key):
                raise ValueError('duplicate/null cup table key')
            seen.add(key)
        arrow_table(tables[name],SCHEMAS[name])
    return tables


def _reconcile_cell(fixture,field,a,b):
    """Factual cell contract: disagreement is quarantined, never averaged."""
    state=('MISSING' if a is None and b is None else 'SUPPLEMENTED' if a is None
           else 'PRIMARY_ONLY' if b is None else 'AGREEMENT' if a==b else 'CONFLICT')
    source={'PRIMARY_ONLY':'titan','AGREEMENT':'titan','SUPPLEMENTED':'nowscore'}.get(state)
    value=a if source=='titan' else b if source=='nowscore' else None
    return dict(fixture_id=fixture,field=field,state=state,
        titan_json=None if a is None else canonical(a),nowscore_json=None if b is None else canonical(b),
        value_json=None if value is None else canonical(value),selected_source=source)


def publish_cup_standings(parsed_sources, *, issue, base_version, base_manifest_sha256,
                           raw_evidence_relative, raw_manifest_sha256, base_reader, environ=None):
    """Validate and publish a registered NAS dataset with base/raw bindings.

    Explicit existing roots, immutable base manifest and frozen raw archive are
    required. Every source byte hash/time/URL must occur in the archive receipt
    whose SHA is pinned by its manifest. Reads original bytes for verification;
    ``base_reader(dataset, table, version, root)`` is the authoritative R
    read_dataset boundary, returning JSON rows; the public R publisher supplies
    it. Exact base fixture/native identities are checked before publication.
    Uses the single version lifecycle and atomic Parquet/JSON writers, catalog
    locking and rollback. Repeated identical inputs are no-ops, not new versions.
    No source/base data or frozen forecasts are overwritten. Raises on conflicts
    in registration/integrity/configuration; source field conflicts are retained.
    """
    validate_issue_id(issue)
    frozen=paths.root_path('frozen',environ=environ);paths.root_path('hot',environ=environ)
    base_manifest=versioning.version_directory(paths.dataset_path('source_issue_'+issue,environ=environ),base_version)/'manifest.json'
    if versioning.sha256_file(base_manifest)!=base_manifest_sha256:
        raise ValueError('base manifest hash mismatch')
    if Path(raw_evidence_relative).is_absolute() or '..' in Path(raw_evidence_relative).parts:
        raise ValueError('relative frozen raw evidence required')
    raw=(frozen/raw_evidence_relative).resolve()
    if not raw.is_relative_to(frozen):
        raise ValueError('raw evidence escapes frozen root')
    if versioning.sha256_file(raw/'asset-manifest.json')!=raw_manifest_sha256:
        raise ValueError('raw manifest hash mismatch')
    raw_manifest=json.loads((raw/'asset-manifest.json').read_text())
    if versioning.sha256_file(raw/'raw-receipts.json')!=raw_manifest['members']['raw-receipts.json']:
        raise ValueError('raw receipt hash mismatch')
    if (raw_manifest.get('dataset')!='source_issue_'+issue or raw_manifest.get('version')!=base_version
            or raw_manifest.get('base_manifest_sha256')!=base_manifest_sha256):
        raise ValueError('raw archive/base identity mismatch')
    receipts=json.loads((raw/'raw-receipts.json').read_text())
    index={(r['fixture_id'],r['source'],r['url'],r['sha256']):r for r in receipts}
    if len(index)!=len(receipts):
        raise ValueError('duplicate raw receipts')
    tables=reconcile_cup_standings(parsed_sources)
    base=json.loads(base_manifest.read_text())
    if not callable(base_reader):
        raise ValueError('authoritative base reader required')
    base_rows=json.loads(base_reader('source_issue_'+issue,'match',base_version,str(frozen)))
    if not isinstance(base_rows,list) or not all(isinstance(row,dict) and all(isinstance(row.get(k),str) and row[k] for k in ('fixture_id','provider_id','home_id','away_id')) for row in base_rows):
        raise ValueError('typed base fixture identities required')
    fixture_index={row['fixture_id']:row for row in base_rows}
    expected=base['tables']['match']['rows']
    if len(fixture_index)!=len(base_rows) or len(base_rows)!=expected:
        raise ValueError('base fixture identity cardinality mismatch')
    if {p['fixture_id'] for p in parsed_sources}!=set(fixture_index):
        raise ValueError('exact base fixture set required')
    if len({p['fixture_id'] for p in parsed_sources})!=expected or len(tables['coverage'])!=2*expected:
        raise ValueError('whole-base two-source coverage required')
    for p in parsed_sources:
        if not re.fullmatch(re.escape(issue)+r':[1-9][0-9]*',p['fixture_id']):
            raise ValueError('foreign fixture issue')
        r=p['provenance']; captured=index[(r['fixture_id'],r['source'],r['url'],r['sha256'])]
        if (datetime.fromisoformat(captured['capture_observed_at'])!=datetime.fromisoformat(r['observed_at'])
            or captured['path']!='raw/'+r['sha256']+'.bin'
            or versioning.sha256_file(raw/captured['path'])!=r['sha256']):
            raise ValueError('source archive binding mismatch')
        # Reparse the authoritative source when publishing; supplied row objects
        # cannot mutate the facts independently of their pinned bytes.
        checked=parse_cup_standings((raw/captured['path']).read_bytes(),fixture_id=p['fixture_id'],
            source=r['source'],identity=fixture_index[p['fixture_id']],receipt=r)
        if canonical(checked)!=canonical(p):
            raise ValueError('supplied cup facts differ from pinned source')
    implementation={name:versioning.sha256_file(Path(__file__).parent/name) for name in
        ('cup_standings.py','fundamentals.py','source_issue_update.py','fundamental_tables.py','unified_sources.py','versioning.py','settlement_backfill.py')}
    source=dict(issue=issue,base_dataset='source_issue_'+issue,base_version=base_version,
        base_manifest_sha256=base_manifest_sha256,base_fixture_identity_sha256=hashlib.sha256(canonical(base_rows).encode()).hexdigest(),raw_evidence_relative=raw_evidence_relative,
        raw_manifest_sha256=raw_manifest_sha256,historical_admission=False,
        availability_class='HISTORICAL_PROXY',implementation_sha256=implementation)
    identity=hashlib.sha256(canonical(dict(tables=tables,source=source)).encode()).hexdigest()
    name='source_cup_standings_'+issue
    destination=paths.dataset_path(name,require_exists=False,environ=environ)
    with FileLock(paths.catalog_root(environ=environ)/'source-issue-publication.lock',timeout=30):
        catalog=registry.load_catalog(environ=environ);previous=versioning.read_current(destination)
        if previous and previous.get('identity_sha256')==identity:
            entry=catalog['datasets'].get(name)
            if not entry or entry['version']!=previous['label_version']:
                raise versioning.VersionError('cup catalog/current mismatch')
            _verify_publication(destination,previous)
            return dict(status='unchanged',dataset=name,version=previous['label_version'])
        label=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        def write(directory):
            entries={}
            for key,rows in tables.items():
                written=write_parquet_atomically(arrow_table(rows,SCHEMAS[key]),directory/'tables'/(key+'.parquet'))
                entries[key]=dict(kind='whole',rows=written['rows'],files=[dict(name=key+'.parquet',rows=written['rows'],sha256=written['sha256'])])
            versioning.write_json_atomically(dict(version=label,tables=entries,source=source),directory/'manifest.json')
            versioning.write_json_atomically(source,directory/'receipt.json')
            return dict(identity_sha256=identity,manifest_sha256=versioning.sha256_file(directory/'manifest.json'),receipt_sha256=versioning.sha256_file(directory/'receipt.json'))
        try:
            published=versioning.publish_version(destination,label,write)
            schema_id='beidan_cup_standings_v1'
            versioning.write_json_atomically(dict(schema_id=schema_id,tables=SCHEMAS,keys=KEYS,
                nullable='effective conflict cells null; absent coverage counts null',
                meaning='source-published cup group tables; group identity hashes full source membership; historical proxy only'),paths.schema_path(schema_id,require_exists=False,environ=environ))
            catalog['datasets'][name]=dict(kind='dataset',format='parquet',location='frozen:datasets/'+name,
                schema_id=schema_id,version=label,owner='collector:cup-standings',retention='retained',tables=len(SCHEMAS),manifest=f'datasets/{name}/versions/{label}/manifest.json')
            versioning.write_json_atomically(catalog,registry.catalog_path(environ=environ))
        except Exception:
            final=versioning.version_directory(destination,label)
            if final.exists():os.replace(final,destination/('.failed-'+label))
            if previous is None:(destination/'current.json').unlink(missing_ok=True)
            else:versioning.write_json_atomically(previous,destination/'current.json')
            raise
    return dict(status=published['status'],dataset=name,version=label)


def _verify_publication(base,current):
    """Verify this contract's immutable no-op target, including metadata hashes."""
    directory=versioning.version_directory(base,current['label_version'])
    if versioning.content_digest(directory)!=current['content_digest']:
        raise versioning.VersionError('cup published content digest mismatch')
    for name,key in [('manifest.json','manifest_sha256'),('receipt.json','receipt_sha256')]:
        if versioning.sha256_file(directory/name)!=current[key]:
            raise versioning.VersionError('cup published metadata mismatch')
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['version']!=current['label_version'] or set(manifest['tables'])!=set(SCHEMAS):
        raise versioning.VersionError('cup manifest table identity mismatch')
    for name,entry in manifest['tables'].items():
        if len(entry['files'])!=1 or entry['files'][0]['name']!=name+'.parquet':
            raise versioning.VersionError('cup manifest file identity mismatch')
        if versioning.sha256_file(directory/'tables'/entry['files'][0]['name'])!=entry['files'][0]['sha256']:
            raise versioning.VersionError('cup published file mismatch')
