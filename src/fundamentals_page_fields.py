"""Lossless page-field observations, separate from strict facts acceptance."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.fundamentals_census import decode_analysis_text, js_value


def observed_page_fields(raw: bytes, *, page_url: str) -> dict:
    """Extract all saved HTML table cells, inline scripts and data literals.

    Returns scalar observations and nested raw blocks, never accepted facts.
    Invalid data literals retain named errors and original inline script text.
    Table coordinates/attributes preserve every direct cell including nested
    tables; no row is dropped for factual contradictions. No scripts execute,
    no linked pages are fetched, and missing fields remain None versus [].
    Essential script URLs are listed with no implied asset-capture success.
    """
    text, encoding = decode_analysis_text(raw)
    soup = BeautifulSoup(text, 'html.parser')
    scripts = [node.get_text() for node in soup.find_all('script') if not node.get('src')]
    data_text = '\n'.join(scripts)
    variables, errors = {}, {}
    for name in sorted(set(re.findall(r'\bvar\s+([A-Za-z_$][\w$]*)\s*=', data_text))):
        try:
            variables[name] = js_value(data_text, name)
        except ValueError as exc:
            errors[name] = str(exc)
    tables = []
    groups = {name: [] for name in ("standings_raw", "injuries_raw", "previous_lineup_raw", "schedules_raw")}
    for ordinal, table in enumerate(soup.find_all('table')):
        rows = []
        for tr in table.find_all('tr'):
            if tr.find_parent('table') is not table:
                continue
            rows.append([dict(text=cell.get_text(' ', strip=True),
                              html=cell.decode_contents(),
                              rowspan=cell.get('rowspan', '1'), colspan=cell.get('colspan', '1'))
                         for cell in tr.find_all(['td', 'th'], recursive=False)])
        tables.append(dict(ordinal=ordinal, id=table.get('id'), rows=rows))
        if not table.find('table'):
            labels = table.get_text(' ', strip=True)
            if '全场' in labels and '排名' in labels and '胜' in labels:
                groups['standings_raw'].append(tables[-1])
            if '缺阵原因' in labels:
                groups['injuries_raw'].append(tables[-1])
            if ('首发' in labels and '后备' in labels) or ('球员' in labels and '评分' in labels):
                groups['previous_lineup_raw'].append(tables[-1])
            if '对阵' in labels and ('日期' in labels or '时间' in labels):
                groups['schedules_raw'].append(tables[-1])
    visible = soup.get_text(' ', strip=True)
    header = visible[:1800]
    venue = re.search(r'场地[：:]\s*(.*?)\s*天气[：:]', header)
    weather = re.search(r'天气[：:]\s*([^\d℃]*?)\s*([+-]?\d+(?:\s*[~～]\s*[+-]?\d+)?)\s*℃', header)
    competition = sorted({re.sub(r'\s*资料(?:库)?$', '', a.get_text(' ', strip=True))
                          for a in soup.select('a[href]')
                          if re.fullmatch(r'.+?\s*资料(?:库)?', a.get_text(' ', strip=True))})
    return dict(page_title=soup.title.get_text(' ', strip=True) if soup.title else None,
                encoding=encoding, home_observed=variables.get('hometeam'),
                away_observed=variables.get('guestteam'), competition_observed=competition,
                home_history_raw=variables.get('h_data'), away_history_raw=variables.get('a_data'),
                head_to_head_raw=variables.get('v_data'),
                venue_observed=venue[1].strip() or None if venue else None,
                weather_observed=weather[1].strip() or None if weather else None,
                temperature_c_observed=weather[2] if weather else None,
                page_tables=tables, **groups, javascript_literals=variables, javascript_errors=errors,
                inline_scripts=scripts, page_text=visible,
                page_links=[dict(text=a.get_text(' ', strip=True), url=urljoin(page_url, a['href']))
                            for a in soup.select('a[href]')],
                input_fields=[dict(node.attrs) for node in soup.select('input, select, textarea')],
                script_urls=[urljoin(page_url, node['src'].strip()) for node in soup.select('script[src]')],
                observation_status='RAW_ONLY_NOT_VALIDATED')
