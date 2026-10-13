"""Pure independently parsed issue identity inventory; no learning or I/O."""
import re
from urllib.parse import urlsplit, parse_qs
from bs4 import BeautifulSoup
from .issue_schedule.decode import decode_response
from .issue_schedule.sources import parse_nowscore_rows


def parse_exclusion_roster(raw, *, source_url, observed_at, content_type):
    """Read the provider's actual selector universe and native roster identities.

    Returns selected issue, all declared issue IDs and issue/slot/native-ID rows.
    Existing source parser validates row identities. No numerical issue ranges
    are invented: unlisted codes do not imply officially nonexistent issues.
    No labels are returned or used, and there is no fitting, fetching or write.
    """
    url=urlsplit(source_url);query=parse_qs(url.query)
    if (url.scheme!='https' or url.hostname!='cp.nowscore.com' or url.path!='/buy/DanChang.aspx'
            or query.get('TypeID')!=['5'] or query.get('all')!=['1']):
        raise ValueError('Explicit full SPF provider URL required')
    text=decode_response(raw,content_type)
    soup=BeautifulSoup(text,'html.parser')
    select=soup.select_one('#dropIssueNum')
    if select is None:raise ValueError('Provider issue selector required')
    options=select.select('option')
    issues=[o.get('value') for o in options]
    selected=[o.get('value') for o in options if o.has_attr('selected')]
    if (len(selected)!=1 or len(issues)!=len(set(issues))
            or not all(isinstance(i,str) and re.fullmatch(r'\d{5,6}',i) for i in issues)):
        raise ValueError('Unique actual selected issue and declared issue IDs required')
    if 'issueNum' in query and query['issueNum']!=selected:
        raise ValueError('Requested and selected source issue differ')
    rows=parse_nowscore_rows(text,issue_id=selected[0],observed_at=observed_at,source_url=source_url)
    roster=[dict(issue_id=selected[0],slot=r.slot,provider_id=r.provider_match_id) for r in rows]
    if not roster or len({r['provider_id'] for r in roster})!=len(roster):
        raise ValueError('Complete unique nonempty source roster required')
    return dict(selected_issue=selected[0],declared_issues=issues,roster=roster)
