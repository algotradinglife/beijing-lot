"""Read-only full-issue capture coverage. Reuses #408 raw and analysis parsers."""
from pathlib import Path
import hashlib
import platform
import json
import os
import tempfile
from importlib.metadata import version

from bs4 import BeautifulSoup

from src.fundamentals_census import AnalysisFieldError, analysis_record, read_response, decode_analysis_text, js_value
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_page_fields import observed_page_fields
from src.fundamentals_jina import analysis_parsing_view


def issue_capture_report(roster_path: str, response_paths: list[str], *, issue: str, expected_fixture_count: int = 83, expected_slots: list[int] | None = None, auxiliary_response_paths: dict[str, str] | None = None, cache_dir: str | None = None) -> dict:
    """Return full-denominator source observations and unresolved pair status.

    Explicit inputs are one saved roster receipt and zero or more selected page
    receipts; duplicates, off-inventory URLs, redirects and invalid receipts
    fail closed. Missing pages and HTTP/parser failures remain separate rows.
    No network, writes, adjudication, inferred alias or historical admission.
    SHA-256 binds every input file and the three directly used Python modules.
    Response selection is explicit: callers may not silently choose revisions.
    expected_slots optionally declares original noncontiguous positive slot IDs;
    its cardinality must equal expected_fixture_count. Default requires 1..count.
    An explicit slot set may select a subset; the caller owns and records
    exclusions. Default count still validates the entire roster.
    Gaps are recorded without renumbering or silently dropping fixtures.
    auxiliary_response_paths maps captured page URL to its explicit successful
    required-JS receipt; asset bytes remain separate and bind raw fields/cache.
    """
    roster = Path(roster_path)
    meta, raw = read_response(roster)
    if meta['status'] != 200 or meta['url'] != meta['final_url']:
        raise ValueError('roster must be an unredirected HTTP 200 response')
    if type(expected_fixture_count) is not int or expected_fixture_count < 1:
        raise ValueError("designated fixture count or slot set mismatch")
    slots = list(range(1, expected_fixture_count + 1)) if expected_slots is None else expected_slots
    if (not isinstance(slots, list) or len(slots) != expected_fixture_count or
            any(type(slot) is not int or slot < 1 for slot in slots) or
            len(set(slots)) != len(slots)):
        raise ValueError("designated fixture count or slot set mismatch")
    fixtures = issue_analysis_pages(raw, roster_url=meta['url'], issue=issue, slots=expected_slots)
    if sorted(row['slot'] for row in fixtures) != sorted(slots):
        raise ValueError('designated fixture count or slot set mismatch')
    expected = {}
    for fixture in fixtures:
        for source, key in [('nowscore', 'nowscore_url'), ('titan', 'titan_candidate_url')]:
            expected[fixture[key]] = (fixture, source)
    seen = {}
    bindings = {str(roster): hashlib.sha256(roster.read_bytes()).hexdigest()}
    for name in response_paths:
        path = Path(name)
        receipt, body = analysis_parsing_view(*read_response(path))
        url = receipt['url']
        if url not in expected or url in seen or receipt['final_url'] != url:
            raise ValueError('unexpected, duplicate or redirected page receipt')
        seen[url] = (receipt, body)
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    auxiliaries = {}
    if auxiliary_response_paths is not None and not isinstance(auxiliary_response_paths, dict):
        raise ValueError('Auxiliary receipt mapping required')
    for page_url, asset_path in (auxiliary_response_paths or {}).items():
        if page_url not in expected or page_url not in seen:
            raise ValueError('Auxiliary receipt requires captured inventory page')
        fixture, source = expected[page_url]
        if source != 'nowscore' or seen[page_url][0]['status'] != 200:
            raise ValueError('Auxiliary receipt requires successful Nowscore page')
        asset_meta, asset_body = read_response(Path(asset_path))
        asset_url = f"https://live.nowscore.com/analysisJs/data{fixture['provider_id']}.js"
        if asset_meta['status'] != 200 or asset_meta['url'] != asset_url or asset_meta['final_url'] != asset_url:
            raise ValueError('Invalid auxiliary response identity or transport')
        _validate_auxiliary_reference(seen[page_url][1], source, fixture['provider_id'])
        auxiliaries[page_url] = asset_body
        bindings[str(Path(asset_path))] = hashlib.sha256(Path(asset_path).read_bytes()).hexdigest()
    observations = []
    page_fields = []
    for url, (fixture, source) in expected.items():
        row = dict(issue=issue, slot=fixture['slot'], provider_id=fixture['provider_id'],
                   source=source, url=url, capture_state='NOT_CAPTURED', parse_state='NOT_ATTEMPTED',
                   status=None, raw_sha256=None, received_at_utc=None, error=None,
                   home=None, away=None, home_id=None, away_id=None, kickoff_utc=None,
                   evidence_class='HISTORICAL_PROXY', pairing_status='PENDING_IDENTITY_REVIEW')
        fields = dict(issue=issue, slot=fixture["slot"], source=source, raw_fields=None, normalized_fields=None, partial_fields=None, extraction_error=None)
        if url in seen:
            receipt, body = seen[url]
            if 'transport_url' in receipt:
                row.update({key: receipt[key] for key in ('transport_url', 'transport_sha256', 'parser_body_sha256', 'parser_transform')})
            row.update(status=receipt['status'], raw_sha256=receipt['sha256'],
                       received_at_utc=receipt['received_at_utc'],
                       capture_state='HTTP_OK' if receipt['status'] == 200 else 'HTTP_FAILURE')
            if receipt.get('parser_error'):
                row.update(parse_state='PARSE_FAILURE', error=receipt['parser_error'])
                fields['extraction_error'] = receipt['parser_error']
            elif receipt['status'] == 200:
                parsed = parsed_page_observation(body, source=source, provider_id=fixture['provider_id'],
                                                 url=url, auxiliary_raw=auxiliaries.get(url), cache_dir=cache_dir)
                row.update(parsed['row'])
                fields.update(parsed['fields'])
        observations.append(row)
        page_fields.append(fields)
    module_root = Path(__file__).parent
    return dict(schema='bj411_issue_capture_report_v1', issue=issue,
                runtime=dict(python=platform.python_version(), beautifulsoup4=version('beautifulsoup4'), json5=version('json5')),
                fixture_count=len(fixtures), expected_pages=len(expected),
                expected_slots=sorted(slots), slot_gaps=sorted(set(range(1, max(slots) + 1)) - set(slots)),
                fixtures=fixtures, observations=observations, page_fields=page_fields,
                input_file_hashes=bindings,
                implementation_hashes={name: hashlib.sha256((module_root/name).read_bytes()).hexdigest()
                                       for name in ('fundamentals_issue_report.py',
                                                    'fundamentals_issue_pages.py', 'fundamentals_census.py', 'fundamentals_page_fields.py', 'fundamentals_jina.py')},
                historical_learning='NONE', admission='DIAGNOSTIC_ONLY',
                identity_acceptance='NOT_PERFORMED',
                notes='Capture coverage only; successful parse does not prove same fixture or historical availability.')


def parsed_page_observation(body: bytes, *, source: str, provider_id: str, url: str, auxiliary_raw: bytes | None = None, cache_dir: str | None = None) -> dict:
    """Parse one immutable body offline, optionally persisting a verified JSON cache.

    No HTTP or adjudication. Cache identity binds body, URL, source, provider,
    all fundamentals modules and installed parser dependencies. Receipt times
    stay outside this content cache. Corrupt entries fail; atomic replacement
    permits concurrent readers/writers computing the same deterministic result.
    """
    if auxiliary_raw is not None:
        _validate_auxiliary_reference(body, source, provider_id)
    identity = dict(body=hashlib.sha256(body).hexdigest(), source=source,
                    auxiliary_sha256=hashlib.sha256(auxiliary_raw).hexdigest() if auxiliary_raw is not None else None,
                    provider_id=provider_id, url=url, python=platform.python_version(),
                    dependencies={name: version(name) for name in ('beautifulsoup4', 'json5', 'soupsieve')},
                    modules={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(Path(__file__).parent.glob('fundamentals*.py'))})
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    path = Path(cache_dir) / f'{key}.json' if cache_dir is not None else None
    if path is not None and path.exists():
        envelope = json.loads(path.read_text())
        payload = envelope['payload']
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if envelope.get('identity') != identity or envelope.get('sha256') != digest:
            raise ValueError('Invalid parsed page cache binding')
        return payload
    row = dict(auxiliary_sha256=identity['auxiliary_sha256'])
    fields = dict(raw_fields=None, normalized_fields=None, partial_fields=None, extraction_error=None)
    try:
        fields['raw_fields'] = observed_page_fields(body, page_url=url)
        if auxiliary_raw is not None:
            # Parse JS literals directly; never embed script bytes into HTML.
            asset_text = auxiliary_raw.decode('utf-8-sig', errors='strict')
            raw_fields = fields['raw_fields']
            raw_fields['auxiliary_script_text'] = asset_text
            raw_fields['auxiliary_sha256'] = hashlib.sha256(auxiliary_raw).hexdigest()
            raw_fields['auxiliary_javascript_errors'] = {}
            for variable, column in (('h_data', 'home_history_raw'), ('a_data', 'away_history_raw'), ('v_data', 'head_to_head_raw')):
                raw_fields[column] = None
                try:
                    raw_fields[column] = js_value(asset_text, variable)
                except ValueError as exc:
                    raw_fields['auxiliary_javascript_errors'][variable] = str(exc)
    except (ValueError, UnicodeError) as exc:
        fields['extraction_error'] = str(exc)
    try:
        parsed = analysis_record(body, source=source, provider_id=provider_id, auxiliary_raw=auxiliary_raw)
        row.update({key: parsed[key] for key in
                    ('home', 'away', 'home_id', 'away_id', 'kickoff_utc')})
        row['parse_state'] = 'PARSED'
        fields['normalized_fields'] = parsed
    except AnalysisFieldError as exc:
        partial = exc.partial_record
        row.update({key: partial[key] for key in
                    ('home', 'away', 'home_id', 'away_id', 'kickoff_utc')})
        row.update(parse_state='PARTIAL_FIELD_FAILURE', error=f'{exc.field}: {exc}')
        fields['partial_fields'] = partial
    except (ValueError, UnicodeError) as exc:
        row.update(parse_state='PARSE_FAILURE', error=str(exc))
    # Use the persisted JSON representation on cold and warm paths alike.
    # Native regex matches can contain tuples (e.g. season links).
    payload = json.loads(json.dumps(dict(row=row, fields=fields)))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = dict(identity=identity, payload=payload,
                        sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.parse-')
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(envelope, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return payload


def _validate_auxiliary_reference(body: bytes, source: str, provider_id: str) -> None:
    """Require exactly the supported native script reference before binding JS."""
    text, _ = decode_analysis_text(body)
    nodes = BeautifulSoup(text, 'html.parser').select('script[src*="/analysisJs/data"]')
    if source != 'nowscore' or len(nodes) != 1 or nodes[0]['src'] != f'/analysisJs/data{provider_id}.js':
        raise ValueError('Unexpected or unreferenced auxiliary data identity')
