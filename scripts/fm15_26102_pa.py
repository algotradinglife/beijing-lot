"""Two-fixture bounded PA reviews; schemas/authorship are verified before selection."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root=Path(sys.argv[1]).resolve();worker=int(sys.argv[2]);caller=Path(sys.argv[3]).resolve()
assert worker in (0,1,2) and caller.is_file()
minimum_batch=int(sys.argv[4]) if len(sys.argv)>4 else 1
assert 1<=minimum_batch<=43
out=root/'results/fm15-26102-20261012'
packets=json.loads((out/'review-inputs.json').read_text())['fixtures'];assert len(packets)==86
allowed={'native_rates','top_margins','independent_market','total_constraint','asian_quotes','total_quotes','euro_quotes','missing'}
for start in range(0,len(packets),2):
    batch=start//2+1
    if (batch-1)%3!=worker or batch<minimum_batch:continue
    source=packets[start:start+2];work=out/f'pa-work-{batch:02d}';work.mkdir(exist_ok=True)
    input_path=work/'input.json';input_bytes=(json.dumps(source,ensure_ascii=False,indent=2)+'\n').encode()
    if input_path.exists():assert input_path.read_bytes()==input_bytes
    else:input_path.write_bytes(input_bytes)
    prompt=out/f'pa-prompt-{batch:02d}.txt'
    if not prompt.exists():
        brief=[{k:x[k] for k in ('fixture_id','home','away','competition','native_parameters','native_rates','top_margins','independent_market','total_constraint','asian_quotes','total_quotes','missing')} for x in source]
        prompt.write_text('''FM-1.5.0两场历史诊断审查。只读input.json，只写reviews.json；禁其他路径、联网、安装、北单及目标赛果。以下已给全部事实，不探索环境、不打印输入。原生λ已混合长期/近期同场地攻防各0.5，勿重复加成。欧赔均值和大小球推导是独立复核，非替代λ。无阵容/伤停/排名/对手强度信息不能虚构。一般分歧KEEP_NATIVE/apply并说明拒绝跟随原因；仅有独立事实支持重大中心移位但幅度未知才UNIDENTIFIED_SHIFT/retain。缺市场照实说明，保持native。比分及统一等距核心由主程序处理，不能为了下注排序裁决。所有quote_at按UTC解释。
事实：'''+json.dumps(brief,ensure_ascii=False,separators=(',',':'))+'''
逐场做很短的判断，最后一次Python读取input.json补标识并保存顶层数组reviews.json。每条恰有fixture_id/cutoff_utc/base_hash（原样复制）、decision(apply/retain)、market_action(KEEP_NATIVE/UNIDENTIFIED_SHIFT)、reason(具体攻防短句)、counterevidence(缺失/不确定性短句)、market_review(接受/拒绝哪些盘口信息短句)、evidence_ids(1-4个根名：native_rates,top_margins,independent_market,total_constraint,asian_quotes,total_quotes,euro_quotes,missing)。不写R代码或新λ，不重复工具探索，最后只报保存成功。''')
    call=out/f'pa-call-{batch:02d}'
    if not (call/'receipt.json').exists():
        assert not call.exists(),'Incomplete call: inspect without blind retries'
        result=subprocess.run([sys.executable,str(caller),'--prompt-file',str(prompt),'--cwd',str(work),'--output-dir',str(call),'--timeout','300','--model','opencode/deepseek-v4.1-flash'],capture_output=True,text=True)
        (out/f'pa-driver-{batch:02d}.log').write_text(result.stdout+result.stderr)
    receipt=json.loads((call/'receipt.json').read_text())
    assert receipt['exit_code']==0 and not receipt['timed_out'] and receipt['model']=='opencode/deepseek-v4.1-flash',f'Batch{batch}: stop and inspect provider receipt'
    assert hashlib.sha256(prompt.read_bytes()).hexdigest()==receipt['prompt_sha256']
    assert Path(receipt['cwd']).resolve()==work
    rows=json.loads((work/'reviews.json').read_text());assert len(rows)==len(source)
    for row,packet in zip(rows,source):
        assert set(row)=={'fixture_id','cutoff_utc','base_hash','decision','market_action','reason','counterevidence','market_review','evidence_ids'}
        assert all(row[k]==packet[k] for k in ('fixture_id','cutoff_utc','base_hash'))
        assert row['decision'] in ('apply','retain') and row['market_action'] in ('KEEP_NATIVE','UNIDENTIFIED_SHIFT')
        assert row['market_action']!='UNIDENTIFIED_SHIFT' or row['decision']=='retain'
        assert all(isinstance(row[k],str) and row[k].strip() for k in ('reason','counterevidence','market_review'))
        assert 1<=len(row['evidence_ids'])<=4 and set(row['evidence_ids'])<=allowed
    selection={'batch':batch,'review_path':str((work/'reviews.json').relative_to(root)),'input_path':str(input_path.relative_to(root)),'prompt_path':str(prompt.relative_to(root)),'call_path':str(call.relative_to(root)),'input_sha256':hashlib.sha256(input_bytes).hexdigest(),'review_sha256':hashlib.sha256((work/'reviews.json').read_bytes()).hexdigest()}
    destination=out/f'pa-selection-{batch:02d}.json'
    if destination.exists():
        old=json.loads(destination.read_text());assert all(old[k]==selection[k] for k in ('batch','review_path','input_path','prompt_path','call_path'))
    else:destination.write_text(json.dumps(selection,indent=2)+'\n')
    print('Accepted',batch,'fixtures',len(rows),flush=True)
