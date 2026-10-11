"""Bounded blinded qualitative review; no settlement or SP access."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
out = root / 'results/fm15-two-issues-20261012'
packets = json.loads((out / 'review-inputs.json').read_text())['fixtures']
caller = Path('/home/drwho1985/.codex/skills/pa-analysis/scripts/call_pa.py')
selections = []
for start in range(0, len(packets), 6):
    batch = start // 6 + 1
    if len(sys.argv) > 2 and (batch - 1) % 3 != int(sys.argv[2]):
        continue
    work = out / f'review-work-{batch:02d}'
    work.mkdir(exist_ok=True)
    input_text = json.dumps({'fixtures': packets[start:start+6]}, ensure_ascii=False, indent=2)
    if (work / 'input.json').exists():
        assert (work / 'input.json').read_text() == input_text
    else:
        (work / 'input.json').write_text(input_text)
    brief = []
    for p in packets[start:start+6]:
        facts = {k:p[k] for k in ('fixture_id','home','away','competition','native_parameters','native_rates','top_margins','independent_market','asian_quotes','total_quotes','article_facts','missing')}
        brief.append(json.dumps(facts,ensure_ascii=False,separators=(',',':')))
    (work/'summary.txt').write_text('\n'.join(brief))
    prompt = out / f'review-prompt-{batch:02d}.txt'
    prompt.write_text('''FM-1.5.0历史诊断的盲审。只读本目录input.json，只写reviews.json，禁止读其他路径、联网、安装、目标赛果、北单盘口及SP。R/Python工具只用于读取输入和保存输出，不重新拟合历史。
每条native_parameters来自长期和最近8场同场地攻防的0.5混合；近期表现已在原生lambda内，不能重复加成。independent_market为旧独立市场拟合结果，仅用于复核，不能自动替换lambda。核查赛事类型、攻击/防守、文章事实、亚盘/大小球/欧赔和净胜球中心是否互相支持。缺伤停或对手强度不能虚构。有明确独立基本面事实支持移动中心但幅度不可识别，标UNIDENTIFIED_SHIFT并retain；一般市场分歧记录并保留native，不直接跟随市场。没有未识别的重大形状偏差时apply统一尾部规则：原生分布唯一众数为中心、向两侧等距最多2档，任一侧>=10%纳入整对，两侧均低则止，外围权重0.3。并列众数由主程序保留，不强行指定方向。不得为取得预计下注排序而裁决。
按输入顺序输出顶层JSON数组，每条字段必须为fixture_id,cutoff_utc,base_hash,decision(apply或retain),market_action(KEEP_NATIVE或UNIDENTIFIED_SHIFT),reason(具体数据理由<=50中文字),counterevidence(<=30字),market_review(接受哪些信息、拒绝哪些重复或无额外证据的信息<=60字),evidence_ids(从native_rates,top_margins,independent_market,asian_quotes,total_quotes,euro_quotes,missing和article_facts的evidence_id中选1-4项)。前三字段原样从input复制。所有条目都要审查，包括缺盘口者，说明缺失。最多6场，直接简短分析后一次Python写文件，最后仅报告数量。
额外允许读summary.txt，其包含原输入所有分析字段的紧凑摘录。第一步仅打印summary.txt，不打印input.json，不探索环境。直接根据摘要作简短判断，第二步Python读取input.json只用于补标识并一次写reviews.json；不要重复探索或打印数据。证据引用仅用根字段名。''')
    call = out / f'review-call-{batch:02d}'
    if (out/f'review-call-{batch:02d}-compact'/'receipt.json').exists():
        call = out/f'review-call-{batch:02d}-compact'
    if (out/f'review-call-{batch:02d}-summary'/'receipt.json').exists():
        call = out/f'review-call-{batch:02d}-summary'
    if not (call / 'receipt.json').exists():
        assert not call.exists(), 'Existing incomplete call: inspect before resuming'
        result = subprocess.run([sys.executable, str(caller), '--prompt-file', str(prompt), '--cwd', str(work), '--output-dir', str(call), '--timeout', '300', '--model', 'opencode/deepseek-v4.1-flash'], capture_output=True, text=True)
        (out / f'review-driver-{batch:02d}.log').write_text(result.stdout + result.stderr)
    receipt = json.loads((call / 'receipt.json').read_text())
    if receipt['exit_code']!=0:
        diagnostic=(call/'stdout.txt').read_text()+(call/'stderr.txt').read_text()
        assert 'ECONNRESET' in diagnostic and not any(x in diagnostic.lower() for x in ('unauthorized','insufficient balance','quota exceeded')), 'Nontransient provider failure: stop'
        retry=out/f'review-call-{batch:02d}-network-retry'
        if not (retry/'receipt.json').exists():
            assert not retry.exists() and not (work/'reviews.json').exists()
            result=subprocess.run([sys.executable,str(caller),'--prompt-file',str(prompt),'--cwd',str(work),'--output-dir',str(retry),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
            (out/f'review-network-driver-{batch:02d}.log').write_text(result.stdout+result.stderr)
        call=retry;receipt=json.loads((call/'receipt.json').read_text())
    assert receipt['exit_code'] == 0 and not receipt['timed_out'], f'Batch {batch}: inspect receipt; no automatic retry'
    if call.name.endswith('-compact') and not (work/'reviews.json').exists():
        assert 'reached a model token limit' in (call/'stdout.txt').read_text()
        summary_call=out/f'review-call-{batch:02d}-summary'
        assert not summary_call.exists()
        summary_prompt=out/f'review-summary-prompt-{batch:02d}.txt'
        summary_prompt.write_text(prompt.read_text()+'\n前轮因为多次用R探索文章结构而耗尽token；禁止探索结构。直接print(Path("summary.txt").read_text())，这是一份准确且短的原数据摘录。只用这份摘要做判断，一次Python写最终6条。不得打印input.json。')
        result=subprocess.run([sys.executable,str(caller),'--prompt-file',str(summary_prompt),'--cwd',str(work),'--output-dir',str(summary_call),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
        (out/f'review-summary-driver-{batch:02d}.log').write_text(result.stdout+result.stderr)
        call=summary_call;receipt=json.loads((call/'receipt.json').read_text())
        assert receipt['exit_code']==0 and not receipt['timed_out'] and (work/'reviews.json').exists(), 'Compact summary task failed; stop'
    if not (work / 'reviews.json').exists():
        resumed = out / f'review-call-{batch:02d}-resume'
        resume_prompt = out / f'review-resume-prompt-{batch:02d}.txt'
        resume_prompt.write_text(prompt.read_text()+'\n前轮达到输出token上限，没有产物。所有字段约束保持。禁止打印完整JSON/哈希/盘口列表；只打印每场名称、lambda、近期GF/GA、最高净胜球和盘口摘要，再直接一次Python保存简短记录。所有引用字段用原始根字段名。')
        if not resumed.exists():
            result = subprocess.run([sys.executable,str(caller),'--prompt-file',str(resume_prompt),'--cwd',str(work),'--output-dir',str(resumed),'--timeout','180','--session-id',receipt['session_id'],'--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
            (out/f'review-resume-driver-{batch:02d}.log').write_text(result.stdout+result.stderr)
        call = resumed
        receipt = json.loads((call/'receipt.json').read_text())
        if not (work/'reviews.json').exists():
            assert 'reached a model token limit' in (call/'stdout.txt').read_text(), 'Continuation failed for another reason; stop'
            compact = out/f'review-call-{batch:02d}-compact'
            assert not compact.exists(), 'Fresh compact attempt already exists; stop'
            compact_prompt = out/f'review-compact-prompt-{batch:02d}.txt'
            compact_prompt.write_text(prompt.read_text()+'''\n严格步骤：一次Python读取input.json，仅逐场打印home/away、competition、native_parameters、native_rates、top_margins、independent_market、亚盘和大小球行、文章事实；不要打印euro_quotes明细、base_hash、cutoff和完整JSON。已打印数据直接推敲，然后一次Python定义短tuple(decision,market_action,reason,counterevidence,market_review,evidence_ids)，从原输入补三个标识写reviews.json。不要探索工具环境/读取其他文件/重复打印。使用根字段证据名，避免子字段；所有理由短句。''')
            result = subprocess.run([sys.executable,str(caller),'--prompt-file',str(compact_prompt),'--cwd',str(work),'--output-dir',str(compact),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
            (out/f'review-compact-driver-{batch:02d}.log').write_text(result.stdout+result.stderr)
            call=compact;receipt=json.loads((call/'receipt.json').read_text())
        assert receipt['exit_code']==0 and not receipt['timed_out'] and (work/'reviews.json').exists(), 'Bounded continuation failed'
    rows = json.loads((work / 'reviews.json').read_text())
    source = packets[start:start+6]
    assert len(rows) == len(source)
    for row, packet in zip(rows, source):
        assert set(row) == {'fixture_id','cutoff_utc','base_hash','decision','market_action','reason','counterevidence','market_review','evidence_ids'}
        assert all(row[k] == packet[k] for k in ('fixture_id','cutoff_utc','base_hash'))
        assert row['decision'] in ('apply','retain')
        assert row['market_action'] in ('KEEP_NATIVE','UNIDENTIFIED_SHIFT')
        assert row['market_action'] != 'UNIDENTIFIED_SHIFT' or row['decision'] == 'retain'
        allowed = {'native_rates','top_margins','independent_market','asian_quotes','total_quotes','euro_quotes','missing'}
        allowed.update(a['evidence_id'] for a in packet['article_facts'])
        allowed.update('native_rates:'+r['role'] for r in packet['native_rates'])
        allowed.update('top_margins:'+str(r['margin']) for r in packet['top_margins'])
        allowed.update('top_margins:margin='+str(r['margin']) for r in packet['top_margins'])
        allowed.update('missing:'+k for k in packet['missing'])
        for kind in ('asian_quotes','total_quotes','euro_quotes'):
            allowed.update(kind+':'+str(q['company_id']) for q in (packet[kind] or []))
        for kind in ('native_rates','top_margins','independent_market','asian_quotes','total_quotes','euro_quotes'):
            allowed.update(kind+'#'+str(index) for index in range(len(packet[kind] or [])))
        allowed.update('independent_market:'+k for k in ('W','D','L'))
        if packet['independent_market']:
            allowed.add('independent_market:W/D/L')
        assert 1 <= len(row['evidence_ids']) <= 4 and set(row['evidence_ids']) <= allowed
        assert all(isinstance(row[k],str) and row[k].strip() for k in ('reason','counterevidence','market_review'))
    selections.append({'batch':batch,'call_path':str(call.relative_to(root)),'review_path':str((work/'reviews.json').relative_to(root))})
    (out/f'pa-selection-{batch:02d}.json').write_text(json.dumps(selections[-1],indent=2)+'\n')
    print('Accepted batch',batch,'fixtures',len(rows),flush=True)
