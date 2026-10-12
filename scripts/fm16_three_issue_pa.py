"""Run bounded, evidence-only DeepSeek reviews; fail on route/auth problems."""
from pathlib import Path
import json, subprocess, sys
root=Path(sys.argv[1]).resolve();out=root/'results/fm16-three-issues-20261012'
caller=Path('/home/drwho1985/.codex/skills/pa-analysis/scripts/call_pa.py')
for wd in sorted(out.glob('review-*'),key=lambda p:int(p.name.split('-')[1])):
    if not wd.is_dir():continue
    prompt=wd/'prompt.txt'
    prompt.write_text('''FM-1.6.0 historical diagnostic qualitative review. Read ONLY input.json and write ONLY reviews.json in this directory. No network, installs, extra files, target scores/labels or Beijing SP/handicap. No environment exploration. Inputs quote_at are UTC; cutoff_utc must be copied exactly. Assess native confidence first from sample, ESS, competition/cohort comparability, absent opponent strength and lineup information; never use market disagreement to define low confidence. Adequate needs affirmative reliable evidence, not just large sample. Then independently assess market sufficiency and consistency from all Euro quotes, Asian quotes, totals, prior times and joint-model residuals. Four Euro companies 281/115/82/432 is a complete basket; partial is not complete but may be sufficient with an explicit reason. No universal residual numerical gate has been approved; inspect the actual residuals and cross-channel direction/scale. Missing channels, failed reference, source identity or time conflicts -> insufficient. Price movement has NOT been provided: do not invent it. Do not fit or tune anything. Tail policy handled downstream. Output JSON array one row per input, exactly keys fixture_id,cutoff_utc,confidence(low/uncertain/adequate),market_sufficient(boolean),market_consistent(boolean),reason(specific reliability and market reasons including discrepancies),counterevidence,evidence_ids(1-4 of native_rates,confidence_limitations,article_facts,euro,asian,totals,market_ordinary,market_asian). Concrete concise statements; cannot assign all decisions blindly. Read input once, then write JSON via Python. Finish with count only.''')
    call=out/('pa-'+wd.name)
    assert not call.exists(),'Existing call requires explicit inspection'
    r=subprocess.run([sys.executable,str(caller),'--prompt-file',str(prompt),'--cwd',str(wd),'--output-dir',str(call),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
    (out/('driver-'+wd.name+'.log')).write_text(r.stdout+r.stderr)
    receipt=json.loads((call/'receipt.json').read_text())
    assert receipt['exit_code']==0 and not receipt['timed_out'],'Stop: failed call, do not repeat'
    assert (wd/'reviews.json').is_file(),'Missing business output; inspect original response'
    packets=json.loads((wd/'input.json').read_text());rows=json.loads((wd/'reviews.json').read_text())
    assert len(rows)==len(packets)
    for row,p in zip(rows,packets):
        assert set(row)=={'fixture_id','cutoff_utc','confidence','market_sufficient','market_consistent','reason','counterevidence','evidence_ids'}
        assert all(row[k]==p[k] for k in ('fixture_id','cutoff_utc'))
        assert row['confidence'] in ('low','uncertain','adequate')
        assert type(row['market_sufficient']) is bool and type(row['market_consistent']) is bool
        assert p['market_available'] or not row['market_sufficient']
        assert row['reason'].strip() and row['counterevidence'].strip()
    print('Reviewed',wd.name,len(rows),flush=True)
