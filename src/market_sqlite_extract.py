"""Extract source records for storage, before any cutoff/quality selection.

JSON5 and BeautifulSoup decode source data; existing Titan parsers provide the
normalized view. Uninterpreted cells remain structured evidence, not page bytes.
"""
import re
import json

import json5
from bs4 import BeautifulSoup

from src.fundamentals_census import decode_analysis_text
from src.fundamentals_titan_euro import parse_titan_euro
from src.fundamentals_titan_total import parse_titan_total_html


def extract_market_source(payload, *, market):
    """Return all observed data rows, normalized view and parser anomalies.

    Source ordinals and literal fields are retained even for missing, low or
    invalid odds. No time inference/filtering, model fitting, HTTP or writes.
    Errors in the normalized parser are recorded, not treated as empty markets.
    This does not claim to preserve arbitrary page text or script code.
    """
    if market not in ('euro', 'total'):
        raise ValueError('unsupported market')
    # Reader transport is UTF-8 even when the embedded HTML declares GBK.
    text, encoding = (decode_analysis_text(payload) if market=='euro'
                      else (payload.decode('utf-8-sig',errors='strict'),'utf-8'))
    result = {'market':market,'encoding':encoding,'records':[], 'anomalies':[], 'normalized':None,'source_identity':{}}
    if market == 'euro':
        result['source_identity']={name:re.findall(
            r'(?:^|[;\n])\s*(?:var\s+)?'+name+r'\s*=\s*([^;]+);',text)
            for name in ('ScheduleID','hometeamID','guestteamID','MatchTime')}
        for array in ('game', 'gameDetail'):
            matches = re.findall(r'\b'+array+r'\s*=\s*Array\((.*?)\)\s*;',text,re.S)
            if not matches and array == 'gameDetail':
                continue
            if len(matches) != 1:
                result['anomalies'].append({'code':'ARRAY_SCHEMA','array':array,'matches':len(matches)})
                continue
            try:
                try:
                    rows = json.loads('['+matches[0]+']')
                except json.JSONDecodeError:
                    rows = json5.loads('['+matches[0]+']', allow_duplicate_keys=False)
            except ValueError as exc:
                result['anomalies'].append({'code':'ARRAY_PARSE_ERROR','array':array,'error':str(exc)})
                continue
            for order,row in enumerate(rows):
                if not isinstance(row,str):
                    result['anomalies'].append({'code':'NON_STRING_ROW','array':array,'ordinal':order,'value':row})
                    continue
                if array == 'game':
                    result['records'].append({'section':array,'source_ordinal':order,'fields':row.split('|')})
                elif '^' not in row:
                    result['anomalies'].append({'code':'HISTORY_ID_MISSING','ordinal':order,'fields':row.split('|')})
                else:
                    record_id,history = row.split('^',1)
                    for ordinal,entry in enumerate(history.split(';')):
                        if entry:
                            result['records'].append({'section':array,'source_ordinal':order,
                                'record_id':record_id,'quote_ordinal':ordinal,'fields':entry.split('|')})
    else:
        soup=BeautifulSoup(text,'html.parser')
        result['source_identity']={'headers':[
            {'text':head.get_text(' ',strip=True),
             'elements':[{'tag':e.name,'attributes':dict(e.attrs),'text':e.get_text(' ',strip=True)}
                         for e in head.find_all(['a','span'])]}
            for head in soup.select('.analyhead')]}
        # Keep every source table cell, including hidden/live/unknown columns.
        # The normalized view below selects neither what survives storage nor
        # which observations are admitted to a historical model.
        for table_id in ('odds','oddsDetail'):
            tables=soup.find_all(id=table_id)
            if len(tables)!=1:
                result['anomalies'].append({'code':'TABLE_SCHEMA','table':table_id,'matches':len(tables)})
                continue
            for ordinal,tr in enumerate(tables[0].find_all('tr')):
                cells=tr.find_all(['th','td'],recursive=False)
                result['records'].append({'section':table_id,'source_ordinal':ordinal,
                    'cells':[{'text':c.get_text(' ',strip=True),'attributes':dict(c.attrs),
                              'elements':[{'tag':e.name,'attributes':dict(e.attrs),'text':e.get_text(' ',strip=True)}
                                          for e in c.find_all(['input','a','span'])]} for c in cells]})
    try:
        result['normalized'] = parse_titan_euro(text) if market=='euro' else parse_titan_total_html(text)
    except (ValueError,KeyError,IndexError,TypeError,AttributeError) as exc:
        result['anomalies'].append({'code':'NORMALIZED_PARSE_ERROR','error':type(exc).__name__+': '+str(exc)})
    if not result['records']:
        result['anomalies'].append({'code':'NO_SOURCE_RECORDS'})
    return result
