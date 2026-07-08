import { readFileSync } from 'node:fs';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { mockDashboardData } from '../src/data/mockData';
import { ApiDashboardAdapter } from '../src/data/apiAdapter';
import type { DashboardData } from '../src/data/types';

beforeEach(() => {
  vi.stubEnv('VITE_DATA_MODE', 'mock');
});

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function relativeIsoDate(offsetDays: number) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function parseCsvLine(line: string) {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      fields.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  fields.push(current);
  return fields;
}

function parseCsvRows(text: string) {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = parseCsvLine(headerLine);
  return lines.map((line) => {
    const values = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? '']));
  });
}

describe('北单实盘决策台 v1', () => {
  it('renders navigable pages with focused issue dashboard fields', async () => {
    const yesterday = relativeIsoDate(-1);
    const today = relativeIsoDate(0);
    const tomorrow = relativeIsoDate(1);
    const dashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        issueDate: today,
        matches: mockDashboardData.issue.matches.map((match, index) => ({
          ...match,
          kickoffDate: index === 2 ? yesterday : index >= 3 ? tomorrow : today,
        })),
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(dashboardData);
    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });
     expect(screen.getByText('UI betting-scope-v0400-0140')).toBeInTheDocument();
    for (const page of ['期次看板', '赛后复盘', '下注设计', '运行状态', '实时信号', '策略实验']) {
      expect(screen.getByRole('button', { name: page })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: '投注构建' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '主策略' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '影子策略' })).not.toBeInTheDocument();
    const navButtons = screen.getAllByRole('button').map((button) => button.textContent);
    expect(navButtons.slice(0, 2)).toEqual(['期次看板', '赛后复盘']);
    expect(screen.queryByRole('button', { name: '比赛详情' })).not.toBeInTheDocument();

    expect(screen.getByText('第 26052 期')).toBeInTheDocument();
    expect(screen.getByLabelText('选择期号')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(yesterday) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(today) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(tomorrow) })).toBeInTheDocument();
    expect(screen.getByText('bjdc_26052_001')).toBeInTheDocument();
    const firstMatchRow = screen.getByText('bjdc_26052_001').closest('tr');
    expect(firstMatchRow).not.toBeNull();
    expect(within(firstMatchRow!).getByText(/^押$/)).toBeInTheDocument();
    expect(within(firstMatchRow!).getByText(/^保$/)).toBeInTheDocument();
    expect(within(firstMatchRow!).queryByText(/^停$/)).not.toBeInTheDocument();
    expect(within(firstMatchRow!).getByText('未中')).toBeInTheDocument();
    expect(within(firstMatchRow!).queryByText('押中')).not.toBeInTheDocument();
    expect(screen.getByText('bjdc_26052_009')).toBeInTheDocument();
    expect(screen.queryByText('bjdc_26052_006')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: new RegExp(yesterday) }));
    expect(screen.getByText('bjdc_26052_006')).toBeInTheDocument();
    expect(screen.getAllByText(/中/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('未中').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('columnheader', { name: '预测' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('columnheader', { name: '时间' }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('columnheader', { name: '半场' })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '关注' })).not.toBeInTheDocument();
    const issueHeaders = screen.getAllByRole('columnheader').map((header) => header.textContent?.replace(/\s+/g, '') ?? '');
    const resultIndex = issueHeaders.indexOf('赛果');
    const predictionIndex = issueHeaders.indexOf('预测');
    const settlementIndex = issueHeaders.indexOf('结算SP');
    expect(resultIndex).toBeGreaterThan(-1);
    expect(predictionIndex).toBeGreaterThan(-1);
    expect(settlementIndex).toBeGreaterThan(-1);
    expect(resultIndex).toBeLessThan(predictionIndex);
    expect(settlementIndex).toBeGreaterThan(resultIndex);
    expect(within(firstMatchRow!).getByText(/\(半\)/)).toBeInTheDocument();
    expect(within(firstMatchRow!).getByText(/\(全\)/)).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'q' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('columnheader', { name: '概率' }).length).toBeGreaterThan(0);
    expect(screen.getByText('46%')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '层级' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('columnheader', { name: '结算SP' }).length).toBeGreaterThan(0);
    expect(screen.getByText('胜 2.1')).toBeInTheDocument();
    expect(screen.queryByText('高SP')).not.toBeInTheDocument();
    expect(screen.queryByText('待复盘')).not.toBeInTheDocument();
    expect(screen.queryByText(/概率=让球校准概率 · q=概率×当前SP/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^SP$/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/数据OK/)).not.toBeInTheDocument();
    expect(screen.queryByText(/line-gap 缺/)).not.toBeInTheDocument();
    expect(screen.queryByText(/500_live_sp_latest/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^watch$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Issue Quality \/ LLM Assist/)).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM 辅助解释层/)).not.toBeInTheDocument();
    expect(screen.getAllByText('押/保').length).toBeGreaterThan(0);
    expect(screen.queryByText('押+保+停')).not.toBeInTheDocument();

    const versionSelect = screen.getByLabelText('选择决策版本') as HTMLSelectElement;
    expect(versionSelect.value).toBe('active_v3.3.3');
    expect([...versionSelect.options].map((option) => option.value)).not.toContain('active_v3');
    expect([...versionSelect.options].map((option) => option.value)).not.toContain('shadow_v4.2.0000_execution_strict_fullcap2');
    await userEvent.selectOptions(versionSelect, 'active_v3.3.3');
    expect(versionSelect.value).toBe('active_v3.3.3');
    const firstMatchShadowRow = screen.getByText('bjdc_26052_001').closest('tr');
    expect(firstMatchShadowRow).not.toBeNull();
    expect(within(firstMatchShadowRow!).getByText(/^押$/)).toBeInTheDocument();
    expect(within(firstMatchShadowRow!).getByText(/^保$/)).toBeInTheDocument();
    expect(within(firstMatchShadowRow!).queryByText(/^停$/)).not.toBeInTheDocument();
    expect(within(firstMatchShadowRow!).getByText('未中')).toBeInTheDocument();
    expect(within(firstMatchShadowRow!).queryByText('押中')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('bjdc_26052_001'));
    expect(screen.getAllByText(/^押$/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^保$/).length).toBeGreaterThan(0);
    expect(screen.queryByText('押+保+停')).not.toBeInTheDocument();
    expect(screen.getAllByText(/决策拆解/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/盘口与关注要点/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/情报摘要/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/结构化决策链/).length).toBeGreaterThan(0);
    expect((screen.getByLabelText('选择详情决策版本') as HTMLSelectElement).value).toBe('active_v3.3.3');
    expect(screen.getAllByText(/让球后概率/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/q \/ EV/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/脚本汇总/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/mock_shadow_switch/)).not.toBeInTheDocument();
    expect(screen.queryByText(/模型EV建议/)).not.toBeInTheDocument();
    expect(screen.queryByText(/三结果对比/)).not.toBeInTheDocument();
    expect(screen.queryByText(/数据分析/)).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM 输出 \/ 人工确认/)).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM 决策边界/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Active \/ Draft 对比/)).not.toBeInTheDocument();
    expect(screen.queryByText(/待确认覆盖/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/赛后复盘/).length).toBeGreaterThan(0);

	    await userEvent.click(screen.getByRole('button', { name: '下注设计' }));
	    expect(screen.getByText('下注方案')).toBeInTheDocument();
	    expect(screen.getByText('已生成')).toBeInTheDocument();
		    const bettingVersionSelect = screen.getByLabelText('选择下注决策链版本') as HTMLSelectElement;
		    expect([...bettingVersionSelect.options].map((option) => option.value)).toContain('shadow_v4.2.0000_execution_late_proxy_fullcap2');
		    const bettingScopeSelect = screen.getByLabelText('选择下注范围') as HTMLSelectElement;
		    expect(bettingScopeSelect.value).toBe('by_segment');
		    expect([...bettingScopeSelect.options].map((option) => option.textContent)).toEqual(['分段下注', '整期下注']);
		    expect(screen.getByLabelText('下注预算')).toBeInTheDocument();
		    expect(screen.getByLabelText('选择投入方式')).toBeInTheDocument();
		    expect(screen.queryByLabelText('计划')).not.toBeInTheDocument();
	    expect(screen.queryByText('决策时间')).not.toBeInTheDocument();
	    expect(screen.getAllByText('预算放大').length).toBeGreaterThan(0);
	    expect(screen.getByText('分段计划')).toBeInTheDocument();
		    expect(screen.getByText('票组明细')).toBeInTheDocument();
		    expect(screen.getByText('计划更新')).toBeInTheDocument();
		    expect(screen.getByText('2026-06-30 21:58')).toBeInTheDocument();
		    expect(screen.getByText('方向来源')).toBeInTheDocument();
		    expect(screen.getByText('期次看板同版本')).toBeInTheDocument();
		    expect(screen.getByText(/#1 负\+平/)).toBeInTheDocument();
	    expect(screen.queryByText('死段')).not.toBeInTheDocument();
	    expect(screen.queryByText('有效')).not.toBeInTheDocument();
	    expect(screen.queryByRole('columnheader', { name: '场次/N' })).not.toBeInTheDocument();
	    expect(screen.getAllByRole('columnheader', { name: '场次' }).length).toBeGreaterThan(0);
	    expect(screen.getAllByRole('columnheader', { name: 'N' }).length).toBeGreaterThan(0);
	    expect(screen.getByText('从 2026-06-30 18:00')).toBeInTheDocument();
	    expect(screen.getByText('到 2026-07-01 06:00')).toBeInTheDocument();
	    expect(screen.getByText('从 2026-07-01 18:00')).toBeInTheDocument();
	    expect(screen.getByText('到 2026-07-02 06:00')).toBeInTheDocument();
	    expect(screen.queryByText(/^动态段$/)).not.toBeInTheDocument();
	    expect(screen.queryByText(/^收益$/)).not.toBeInTheDocument();
	    expect(screen.queryByText(/^ROI$/)).not.toBeInTheDocument();
	    expect(screen.queryByText(/只覆盖下一开赛时段/)).not.toBeInTheDocument();
	    expect(screen.queryByText(/覆盖本期剩余比赛/)).not.toBeInTheDocument();
	    expect(screen.queryByText('计划成本')).not.toBeInTheDocument();
	    expect(screen.queryByText('实结收益')).not.toBeInTheDocument();
	    expect(screen.queryByText('实结 ROI')).not.toBeInTheDocument();
	    expect(screen.queryByText('结算状态')).not.toBeInTheDocument();
	    expect(screen.queryByText('历史表现参考')).not.toBeInTheDocument();
	    expect(screen.queryByText(/用于观察方案稳定性/)).not.toBeInTheDocument();
	    expect(screen.queryByText('方案稳定性')).not.toBeInTheDocument();
	    expect(screen.queryByText('分段表现区间')).not.toBeInTheDocument();
	    expect(screen.queryByRole('columnheader', { name: '收益区间' })).not.toBeInTheDocument();
	    expect(screen.queryByRole('columnheader', { name: '结果校验' })).not.toBeInTheDocument();
    expect(screen.queryByText('赛后回放方案')).not.toBeInTheDocument();
    expect(screen.queryByText('回放样本')).not.toBeInTheDocument();
    expect(screen.queryByText('回放结果')).not.toBeInTheDocument();
    expect(screen.queryByText(/回放/)).not.toBeInTheDocument();
    expect(screen.queryByText('波动参考')).not.toBeInTheDocument();
    expect(screen.queryByText('样本数')).not.toBeInTheDocument();
    expect(screen.queryByText('成本 低/均/高')).not.toBeInTheDocument();
    expect(screen.queryByText('收益 低/均/高')).not.toBeInTheDocument();
    expect(screen.queryByText('ROI 低/均/高')).not.toBeInTheDocument();
    expect(screen.queryByText('只读产物')).not.toBeInTheDocument();
    expect(screen.queryByText('参数契约')).not.toBeInTheDocument();
    expect(screen.queryByText('采样CSV')).not.toBeInTheDocument();
    expect(screen.queryByText('segment_betting_plan_segments.csv')).not.toBeInTheDocument();
    expect(screen.queryByText(/segment_betting_strategy_user_explainer_2026-07-07/)).not.toBeInTheDocument();
    expect(screen.queryByText(/默认高亮/)).not.toBeInTheDocument();
    expect(screen.queryByText('单次审计')).not.toBeInTheDocument();
    expect(screen.queryByText('不可用')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '运行状态' }));
    expect(screen.getByText(/实盘健康检查 \/ Issue 26071/)).toBeInTheDocument();
    expect(screen.getByText('待处理事项')).toBeInTheDocument();
    expect(screen.getByText('数据源健康')).toBeInTheDocument();
    expect(screen.getByText('决策快照')).toBeInTheDocument();
    expect(screen.getByText('复盘进度')).toBeInTheDocument();
    expect(screen.getByText('操作区')).toBeInTheDocument();
    expect(screen.getByText('待确认决策草稿')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '复盘 dry-run' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '执行复盘写入' })).toBeInTheDocument();
    expect(screen.queryByText('实盘日流程')).not.toBeInTheDocument();
    expect(screen.queryByText('访问与服务')).not.toBeInTheDocument();
    expect(screen.queryByText('版本锁定')).not.toBeInTheDocument();
    expect(screen.queryByText('数据源新鲜度')).not.toBeInTheDocument();
    expect(screen.queryByText('wf_26071_mock')).not.toBeInTheDocument();
    expect(screen.queryByText(/Host smoke/)).not.toBeInTheDocument();
    expect(screen.queryByText(/triggerEndpoint/)).not.toBeInTheDocument();
    expect(screen.queryByText(/draft_replacement_pending/)).not.toBeInTheDocument();
    expect(screen.queryByText(/draft replacement/)).not.toBeInTheDocument();
    expect(screen.queryByText(/would_insert/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dry_run/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/预计写入/).length).toBeGreaterThan(0);
    expect(screen.queryByText('http://127.0.0.1:4173/')).not.toBeInTheDocument();
    expect(screen.queryByText('http://127.0.0.1:8790/healthz')).not.toBeInTheDocument();
    expect(screen.queryByText(/pid 1001/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pid 1002/)).not.toBeInTheDocument();
    expect(screen.queryByText('trade-server.tail0aa0e9.ts.net')).not.toBeInTheDocument();
    expect(screen.queryByText('f2ad3ef6')).not.toBeInTheDocument();
    expect(screen.getByText('26071_014')).toBeInTheDocument();
    expect(screen.getByText(/1 条决策草稿/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '实时信号' }));
    expect(screen.getAllByText(/source_failed/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/stale/).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: '赛后复盘' }));
    expect(screen.getAllByText(/赛后复盘/).length).toBeGreaterThan(0);
    const settlementIssueSelect = screen.getByLabelText('选择复盘期号') as HTMLSelectElement;
    expect(settlementIssueSelect.value).toBe('26051');
    expect([...settlementIssueSelect.options].map((option) => option.value)).toEqual(['26051']);
    const settlementVersionSelect = screen.getByLabelText('选择复盘决策链版本') as HTMLSelectElement;
    expect([...settlementVersionSelect.options].map((option) => option.value)).toEqual(['active_v3.3.3', 'shadow_v4.2.0000_execution_late_proxy_fullcap2']);
    expect(settlementVersionSelect.value).toBe('active_v3.3.3');
    await userEvent.selectOptions(settlementVersionSelect, 'shadow_v4.2.0000_execution_late_proxy_fullcap2');
    expect(settlementVersionSelect.value).toBe('shadow_v4.2.0000_execution_late_proxy_fullcap2');
    expect(screen.getByText('错因标签')).toBeInTheDocument();
    expect(screen.queryByText('本期摘要')).not.toBeInTheDocument();
    expect(screen.queryByText('v3_decision_variant_active_v3_3_3_tags')).not.toBeInTheDocument();
    expect(screen.getAllByText('v4.2.0004 备选观察').length).toBeGreaterThan(0);
    expect(screen.queryByText(/主押 1 中，保护救回 0 场/)).not.toBeInTheDocument();
    expect(screen.getByText('复盘焦点')).toBeInTheDocument();
    expect(screen.getAllByText('未覆盖').length).toBeGreaterThan(0);
    expect(screen.getAllByText('保护救回').length).toBeGreaterThan(0);
    expect(screen.getByText('标签对应比赛')).toBeInTheDocument();
    expect(screen.getAllByText('漏平').length).toBeGreaterThan(0);
    expect(screen.getAllByText('未覆盖赛果').length).toBeGreaterThan(0);
    expect(screen.queryByText('missed_draw')).not.toBeInTheDocument();
    expect(screen.queryByText('uncovered_result')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /全部/ }));
    expect(screen.getByText('本期不是方向全错，而是覆盖结构问题')).toBeInTheDocument();
    expect(screen.getByText('保护腿有实际价值')).toBeInTheDocument();
    expect(screen.getByText('最大漏点是平局保护不足')).toBeInTheDocument();
    expect(screen.getByText(/押胜率，q 方向做保/)).toBeInTheDocument();
    expect(screen.queryByText('N串1结算')).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '组合空间' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '策略实验' }));
    expect(screen.getAllByText(/baseline_384_hybrid/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/selector_v2_frozen/).length).toBeGreaterThan(0);
    expect(screen.getByText(/年度表现/)).toBeInTheDocument();
  });

  it('keeps betting plan decision version selectable before plan artifacts are generated', async () => {
    const lateProxyId = 'shadow_v4.2.0000_execution_late_proxy_fullcap2';
    const decisionOptions = [
      { variantId: 'active_v3.3.3', kind: 'shadow', label: '正式版 v3.3.3', version: 'llm_chain_bet_protect_stop_v3.3.3_shadow', source: 'structured_shadow_csv', isDefault: true },
      { variantId: lateProxyId, kind: 'shadow', label: 'v4.2 late proxy', version: 'llm_chain_structured_v4.2.0000_layered_merge_execution_policy', versionId: '4.2.0004', source: 'structured_shadow_csv', isDefault: false },
    ];
    const dashboardData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        decisionVariantOptions: decisionOptions,
        strategyVersionContext: {
          schemaVersion: 'strategy_version_context_v1',
          requestedVariantId: '',
          selectedVariantId: 'active_v3.3.3',
          selectionStatus: 'ok',
          availableVariantIds: decisionOptions.map((option) => option.variantId),
          options: decisionOptions,
          contractWarnings: [],
        },
      },
      segmentBettingPlan: {
        ...mockDashboardData.segmentBettingPlan,
        availabilityStatus: 'missing',
        unavailableReason: 'segment_betting_plan_artifact_missing',
        availablePlans: [],
        selectedPlan: undefined,
        selectedPlanId: '',
        summary: {},
        segments: [],
        bundles: [],
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(dashboardData);

    render(<App />);
    await screen.findByRole('button', { name: '下注设计' });
    await userEvent.click(screen.getByRole('button', { name: '下注设计' }));

    expect(screen.getByText('待生成')).toBeInTheDocument();
    expect(screen.getByText('暂无下注计划')).toBeInTheDocument();
    expect(screen.queryByText('不可用')).not.toBeInTheDocument();
	    const versionSelect = screen.getByLabelText('选择下注决策链版本') as HTMLSelectElement;
	    expect(versionSelect.disabled).toBe(false);
	    expect([...versionSelect.options].map((option) => option.value)).toEqual(['active_v3.3.3', lateProxyId]);
	    await userEvent.selectOptions(versionSelect, lateProxyId);
	    expect(versionSelect.value).toBe(lateProxyId);
	    expect(screen.queryByLabelText('计划')).not.toBeInTheDocument();
	    expect((screen.getByLabelText('下注预算') as HTMLInputElement).value).toBe('1000');
	    expect((screen.getByLabelText('选择投入方式') as HTMLSelectElement).value).toBe('scale_to_budget');
	  });

  it('renders v4.2 execution variants from executable picks and keeps audit recommendations separate', async () => {
    const today = relativeIsoDate(0);
    const lateProxy0004Id = 'shadow_v4.2.0000_execution_late_proxy_fullcap2';
    const strict0004Id = 'shadow_v4.2.0000_execution_strict_fullcap2';
    const lateProxyId = 'shadow_v4.2.0005_execution_late_proxy_fullcap2';
    const strictId = 'shadow_v4.2.0005_execution_strict_fullcap2';
    const decisionVariantOptions = [
      { variantId: 'active_v3', kind: 'active', label: 'v3', version: 'llm_chain_bet_protect_stop_v3', source: 'active_snapshot', isDefault: false },
      { variantId: strict0004Id, kind: 'shadow', label: 'v4.2 strict', version: 'llm_chain_structured_v4.2.0000_layered_merge_execution_policy', versionId: '4.2.0004', source: 'structured_shadow_csv', artifactKey: 'v4_2_0004_strict', isDefault: false },
      { variantId: lateProxy0004Id, kind: 'shadow', label: 'v4.2 late proxy', version: 'llm_chain_structured_v4.2.0000_layered_merge_execution_policy', versionId: '4.2.0004', source: 'structured_shadow_csv', artifactKey: 'v4_2_0004_late_proxy', isDefault: false },
      { variantId: strictId, kind: 'shadow', label: 'v4.2 strict', version: 'llm_chain_structured_v4.2.0000_layered_merge_execution_policy', versionId: '4.2.0005', source: 'structured_shadow_csv', artifactKey: 'v4_2_0005_strict', isDefault: false },
      { variantId: lateProxyId, kind: 'shadow', label: 'v4.2 late proxy', version: 'llm_chain_structured_v4.2.0000_layered_merge_execution_policy', versionId: '4.2.0005', source: 'structured_shadow_csv', artifactKey: 'v4_2_0005_late_proxy', isDefault: true },
    ];
    const strategyVersionContext = {
      schemaVersion: 'strategy_version_context_v1',
      requestedVariantId: lateProxyId,
      selectedVariantId: lateProxyId,
      selectionStatus: 'ok',
      availableVariantIds: ['active_v3', strict0004Id, lateProxy0004Id, strictId, lateProxyId],
      options: decisionVariantOptions,
      contractWarnings: [],
    };
    const strictVariant = {
      ...decisionVariantOptions[3],
      recommendation: '等待晚盘',
      primaryPick: undefined,
      protectPicks: [],
      selectionCodes: [],
      selectionType: 'no-buy' as const,
      stopFlag: true,
      qScore: 3.74,
      probability: 0.45,
      executionPolicyVersion: 'v4.2.0005_execution_policy_2026-07-07_extreme_source_q_guard',
      executionPolicyName: 'strict_fullcap2',
      executionAction: 'skip_wait_late_refresh',
      executionReasons: ['requires_late_refresh_before_bet'],
      executionSourceAction: 'wait_late_refresh',
      executionRecommendedCodes: '1+0',
      executionDoubleCodes: '1+0',
      executionFullScore: 0,
      executionFullCandidate: false,
      executionFullKept: false,
      executionSegmentIdx: 2,
      executionUnlockState: 'waiting_late_refresh',
    };
    const lateProxyVariant = {
      ...decisionVariantOptions[4],
      recommendation: 'full downgraded to double',
      primaryPick: '1',
      protectPicks: ['3'],
      selectionCodes: ['1', '3'],
      selectionType: 'double' as const,
      stopFlag: false,
      qScore: 1.11,
      probability: 0.46,
      executionPolicyVersion: 'v4.2.0005_execution_policy_2026-07-07_extreme_source_q_guard',
      executionPolicyName: 'late_proxy_fullcap2',
      executionAction: 'downgrade_full_to_double_layer_conflict',
      executionReasons: ['full_required_but_value_below_threshold'],
      executionSourceAction: 'full_cover_or_skip',
      executionRecommendedCodes: '3+1+0',
      executionDoubleCodes: '1+3',
      executionFullScore: 0.85,
      executionFullCandidate: false,
      executionFullKept: false,
      executionSegmentIdx: 1,
      executionUnlockState: 'unlocked_after_late_refresh',
    };
    const match = {
      ...mockDashboardData.issue.matches[0],
      kickoffDate: today,
      status: 'open' as const,
      score: undefined,
      halftimeScore: undefined,
      scoreStatus: 'scheduled',
      scoreStatusText: '未开',
      resultCode: undefined,
      resultLabel: undefined,
      predictionHit: null,
      settlementSp: undefined,
      selectedDecisionVariantId: lateProxyId,
      selectedDecisionVariant: lateProxyVariant,
      decisionVariants: [strictVariant, lateProxyVariant],
    };
    const dashboardData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        issueDate: today,
        decisionVariantOptions,
        strategyVersionContext,
        matches: [match],
      },
      matchDetail: {
        ...mockDashboardData.matchDetail,
        status: 'open',
        score: undefined,
        halftimeScore: undefined,
        scoreStatus: 'scheduled',
        scoreStatusText: '未开',
        resultLabel: undefined,
        predictionHit: null,
        settlementSp: undefined,
        decisionVariantOptions,
        strategyVersionContext,
        decisionVariants: [strictVariant, lateProxyVariant],
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(dashboardData);

    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });
    const versionSelect = screen.getByLabelText('选择决策版本') as HTMLSelectElement;
    expect([...versionSelect.options].map((option) => option.value)).toContain(lateProxyId);
    expect([...versionSelect.options].map((option) => option.textContent)).toEqual(expect.arrayContaining([
      'v4.2.0004 备选观察',
      'v4.2.0005 备选观察',
    ]));
    expect([...versionSelect.options].map((option) => option.value)).not.toContain('active_v3');
    expect([...versionSelect.options].map((option) => option.value)).not.toContain(strict0004Id);
    expect([...versionSelect.options].map((option) => option.value)).not.toContain(strictId);
    expect(versionSelect.value).toBe(lateProxyId);
    expect(screen.queryByText(/备选观察版/)).not.toBeInTheDocument();
    expect(screen.queryByText(/shadow_v4\.2\.0000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/shadow_v4\.2\.0005/)).not.toBeInTheDocument();
    const row = screen.getByText('bjdc_26052_001').closest('tr');
    expect(row).not.toBeNull();
    const betCell = row!.querySelector('.bet-cell') as HTMLElement;
    expect(within(betCell).getByText('押')).toBeInTheDocument();
    expect(within(betCell).getByText('平')).toBeInTheDocument();
    expect(within(betCell).getByText('保')).toBeInTheDocument();
    expect(within(betCell).getByText('胜')).toBeInTheDocument();
    expect(within(betCell).getByText('冲突降双 · 晚盘解锁')).toBeInTheDocument();
    expect(within(betCell).getByText('审 胜+平+负 → 执 平+胜')).toBeInTheDocument();

    await userEvent.selectOptions(versionSelect, lateProxyId);
    await userEvent.click(screen.getByText('bjdc_26052_001'));
    expect((screen.getByLabelText('选择详情决策版本') as HTMLSelectElement).selectedOptions[0]?.textContent).toBe('v4.2.0005 备选观察');
    expect(screen.getAllByText('v4.2.0005 备选观察').length).toBeGreaterThan(0);
    expect(screen.getByText('执行层')).toBeInTheDocument();
    expect(screen.getByText('可出票')).toBeInTheDocument();
    expect(screen.getByText('晚盘解锁')).toBeInTheDocument();
    expect(screen.getByText('可执行')).toBeInTheDocument();
    expect(screen.getAllByText('平+胜').length).toBeGreaterThan(0);
    expect(screen.getByText('审计建议')).toBeInTheDocument();
    expect(screen.getByText('胜+平+负')).toBeInTheDocument();
    expect(screen.getByText('审计建议与可执行下注不同，出票按“可执行”列。')).toBeInTheDocument();
    expect(screen.getByText('0.85')).toBeInTheDocument();
  });

  it('parses the v4.2 execution artifact fixture fields used by the dashboard contract', () => {
    const csv = readFileSync('../../docs/strategy/examples/v4_2_0000_execution_artifact_example.csv', 'utf8');
    const rows = parseCsvRows(csv);
    expect(rows.length).toBeGreaterThanOrEqual(6);
    const lateProxyRow = rows.find((row) => row.match_id === '26072_005');
    expect(lateProxyRow).toMatchObject({
      shadow_arm: 'shadow_v4.2.0000_execution_late_proxy_fullcap2',
      shadow_selection_codes: '1+3',
      execution_recommended_codes: '3+1+0',
      execution_action: 'downgrade_full_to_double_layer_conflict',
      execution_full_score: '0.8500',
      execution_unlock_state: 'not_applicable',
    });
    const strictWaitRow = rows.find((row) => row.match_id === '26072_020');
    expect(strictWaitRow).toMatchObject({
      shadow_arm: 'shadow_v4.2.0000_execution_strict_fullcap2',
      shadow_selection_codes: '',
      shadow_stop_flag: '1',
      selection_type: 'no-buy',
      execution_action: 'skip_wait_late_refresh',
      execution_recommended_codes: '1+0',
      execution_unlock_state: 'waiting_late_refresh',
    });
  });

  it('does not score halftime matches as missed even when upstream status says finished', async () => {
    const today = relativeIsoDate(0);
    const halftimeData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        issueDate: today,
        matches: [{
          ...mockDashboardData.issue.matches[0],
          kickoffDate: today,
          status: 'open',
          score: '4-1',
          halftimeScore: '4-1',
          scoreStatus: 'finished',
          scoreStatusText: '中场',
          resultCode: '3',
          resultLabel: '胜',
          predictionHit: false,
          settlementSp: undefined,
        }],
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(halftimeData);
    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });
    const row = screen.getByText('bjdc_26052_001').closest('tr');
    expect(row).not.toBeNull();
    expect(within(row!).getByText('进行中')).toBeInTheDocument();
    expect(row!.textContent).toContain('(半) 4-1');
    expect(row!.textContent).toContain('(全) -');
    expect(within(row!).queryByText('未中')).not.toBeInTheDocument();
    expect(within(row!).queryByText('押中')).not.toBeInTheDocument();
  });

  it('shows first-half live score on the half row and keeps full-time blank', async () => {
    const today = relativeIsoDate(0);
    const liveData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        issueDate: today,
        matches: [{
          ...mockDashboardData.issue.matches[0],
          kickoffDate: today,
          status: 'open',
          score: '0-1',
          halftimeScore: '',
          scoreStatus: 'live',
          scoreStatusText: '上',
          resultCode: '',
          resultLabel: '',
          predictionHit: null,
          settlementSp: undefined,
        }],
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(liveData);
    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });
    const row = screen.getByText('bjdc_26052_001').closest('tr');
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain('(半) 0-1');
    expect(row!.textContent).toContain('(全) -');
    expect(within(row!).getByText('进行中')).toBeInTheDocument();
  });

  it('shows second-half live score on the full row without extra wording', async () => {
    const today = relativeIsoDate(0);
    const liveData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        issueDate: today,
        matches: [{
          ...mockDashboardData.issue.matches[0],
          kickoffDate: today,
          status: 'open',
          score: '1-2',
          halftimeScore: '0-1',
          scoreStatus: 'live',
          scoreStatusText: '下',
          resultCode: '',
          resultLabel: '',
          predictionHit: null,
          settlementSp: undefined,
        }],
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(liveData);
    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });
    const row = screen.getByText('bjdc_26052_001').closest('tr');
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain('(半) 0-1');
    expect(row!.textContent).toContain('(全) 1-2');
    expect(row!.textContent).not.toContain('(全) 进行中');
    expect(within(row!).getByText('进行中')).toBeInTheDocument();
  });

  it('hides retired active snapshot draft controls from the public decision version picker', async () => {
    const dashboardData: DashboardData = {
      ...mockDashboardData,
      issue: {
        ...mockDashboardData.issue,
        matches: mockDashboardData.issue.matches.map((match, index) => index === 0 ? {
          ...match,
          draftDecisionSnapshotId: 'draft_26052_001',
        } : match),
      },
      matchDetail: {
        ...mockDashboardData.matchDetail,
        decisionSnapshot: {
          snapshotId: 'active_26052_001',
          status: 'active',
          generatedAt: '2026-07-03 10:00',
          checkedAt: '2026-07-03 10:05',
          inputHash: 'active-input',
          recommendation: '押胜，保平',
          primaryPick: '3',
          protectPicks: ['1'],
          stopFlag: false,
          selectionCodes: ['3', '1'],
          confidence: 0.66,
          confidenceLabel: '中',
          qScore: 1.38,
          probability: 0.46,
          promptVersion: 'prompt-v1',
          modelVersion: 'gpt-fixed-chain-v1',
          probModelVersion: 'prob-v1',
          qModelVersion: 'q-v1',
          decisionChainVersion: 'chain-v1',
          decisionConfigHash: 'abcdef123456',
          reviewTagVersion: 'review-v1',
        },
        draftDecisionSnapshot: {
          snapshotId: 'draft_26052_001',
          status: 'draft_replacement',
          generatedAt: '2026-07-03 10:30',
          checkedAt: '2026-07-03 10:35',
          inputHash: 'draft-input',
          recommendation: '押负，保胜',
          primaryPick: '0',
          protectPicks: ['3'],
          stopFlag: false,
          selectionCodes: ['0', '3'],
          confidence: 0.62,
          confidenceLabel: '中',
          qScore: 1.44,
          probability: 0.41,
          promptVersion: 'prompt-v1',
          modelVersion: 'gpt-fixed-chain-v2',
          probModelVersion: 'prob-v1',
          qModelVersion: 'q-v1',
          decisionChainVersion: 'chain-v2',
          decisionConfigHash: 'fedcba987654',
          reviewTagVersion: 'review-v1',
        },
      },
    };
    vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData').mockResolvedValue(dashboardData);
    vi.spyOn(ApiDashboardAdapter.prototype, 'confirmDecisionSnapshot').mockResolvedValue({
      action: 'confirmed_override',
      confirmedAt: '2026-07-03 10:40',
      previousActive: dashboardData.matchDetail.decisionSnapshot,
      active: { ...dashboardData.matchDetail.draftDecisionSnapshot!, status: 'active', confirmedAt: '2026-07-03 10:40' },
    });
    render(<App />);
    await screen.findByRole('button', { name: '期次看板' });

    await userEvent.click(screen.getByRole('button', { name: /2026-06-30/ }));
    expect(screen.getByText('待确认新建议')).toBeInTheDocument();
    expect(screen.queryByText(/Active \/ Draft 对比/)).not.toBeInTheDocument();
    expect([...((screen.getByLabelText('选择决策版本') as HTMLSelectElement).options)].map((option) => option.value)).not.toContain('active_v3');

    await userEvent.click(screen.getByText('bjdc_26052_001'));
    expect(screen.queryByText(/Active \/ Draft 对比/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '确认覆盖' })).not.toBeInTheDocument();
  });

  it('keeps the last successful dashboard visible when a real refresh fails', async () => {
    const getDashboardSpy = vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData')
      .mockResolvedValueOnce(mockDashboardData)
      .mockRejectedValueOnce(new Error('API 503'));

    render(<App />);
    await screen.findByText('第 26052 期');

    await userEvent.selectOptions(screen.getByLabelText('选择期号'), '26051');

    expect(await screen.findByRole('alert')).toHaveTextContent('数据刷新失败');
    expect(screen.getByText(/API 503/)).toBeInTheDocument();
    expect(screen.getByText(/继续显示上一次成功数据/)).toBeInTheDocument();
    expect(screen.getByText('第 26052 期')).toBeInTheDocument();
    expect((screen.getByLabelText('选择期号') as HTMLSelectElement).value).toBe('26051');
    expect(getDashboardSpy).toHaveBeenCalledTimes(2);
  });

  it('ignores slower stale dashboard requests after a newer selection resolves', async () => {
    let resolveSlowIssue!: (value: DashboardData) => void;
    const slowIssueData: DashboardData = {
      ...mockDashboardData,
      issue: { ...mockDashboardData.issue, issueId: '26051' },
    };
    const latestIssueData: DashboardData = {
      ...mockDashboardData,
      issue: { ...mockDashboardData.issue, issueId: '26052' },
    };
    const getDashboardSpy = vi.spyOn(ApiDashboardAdapter.prototype, 'getDashboardData')
      .mockResolvedValueOnce(mockDashboardData)
      .mockImplementationOnce(() => new Promise<DashboardData>((resolve) => {
        resolveSlowIssue = resolve;
      }))
      .mockResolvedValueOnce(latestIssueData);

    render(<App />);
    await screen.findByText('第 26052 期');
    const issueSelect = screen.getByLabelText('选择期号') as HTMLSelectElement;

    await userEvent.selectOptions(issueSelect, '26051');
    await waitFor(() => expect(getDashboardSpy).toHaveBeenCalledTimes(2));
    await userEvent.selectOptions(issueSelect, '26052');
    await waitFor(() => expect(getDashboardSpy).toHaveBeenCalledTimes(3));
    expect(screen.getByText('第 26052 期')).toBeInTheDocument();

    resolveSlowIssue(slowIssueData);
    await waitFor(() => expect(screen.queryByText('第 26051 期')).not.toBeInTheDocument());
  });

  it('mock data covers ok, missing, failed, stale, and settled review states', () => {
    const statuses = new Set(mockDashboardData.issue.matches.map((m) => m.scrapeStatus));
    expect(statuses).toEqual(new Set(['ok', 'partial', 'missing', 'failed', 'stale']));
    expect(mockDashboardData.settlement.reviewStatus).toBe('review_draft');
    expect(mockDashboardData.settlement.ticketResults[0].missedProtection).toBeGreaterThan(0);
    expect(mockDashboardData.selectorShadow.ruleName).toContain('weakcount');
    expect(mockDashboardData.selectorShadow.recentDecisions[0].outcome).toBe('helped');
    expect(mockDashboardData.mainStrategy.candidates.map((arm) => arm.armId)).toContain('b384_dd32_smooth100');
    expect(mockDashboardData.mainStrategy.evPool.available).toBe(true);
    expect(mockDashboardData.availableIssues.map((issue) => issue.issueId)).toContain('26051');
    expect(mockDashboardData.operations.runtime.publicDiagnostics).toBe(false);
    expect(mockDashboardData.operations.snapshots.draftReplacementCount).toBe(1);
    expect(mockDashboardData.operations.workflow.steps).toHaveLength(3);
    expect(mockDashboardData.operations.review.task.status).toBe('dry_run');
  });

  it('uses an adapter layer that can switch from mock to fetch API', async () => {
    const adapter = new ApiDashboardAdapter({ mode: 'mock' });
    await expect(adapter.getIssueDashboard('26052')).resolves.toMatchObject({ issueId: '26052' });
  });

  it('fetches only the issue list and issue dashboard for the initial shell', async () => {
    const payloads: Record<string, unknown> = {
      '/api/issues?limit=120&include_replay=0': { issues: [{ issue: '26052', label: '26052 当前期', status: 'current', source: 'sqlite', is_current: true, last_seen_at: '2026-07-04' }] },
      '/api/issues/26052/dashboard?view=summary': {
        issue: '26052',
        issue_date: '2026-07-04',
        status: 'open',
        capture_status: 'ok',
        stats: { n_matches: 0, qualified_legs: 0, qualified_matches: 0, q_avg: 0, pool_quality_flag: 'green' },
        matches: [],
        source: { kind: 'sqlite', provider: '500.com', tables: ['matches'] },
      },
      '/api/issues/26052/decision-artifacts/status': {
        issue: '26052',
        variant_id: 'active_v3.3.3',
        status: 'missing',
        expected_count: 0,
        row_count: 0,
        missing_match_idxs: [],
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input).replace('http://api.test', '');
      return { ok: true, json: async () => payloads[url] } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });
    await expect(adapter.getDashboardShell('26052')).resolves.toMatchObject({ issue: { issueId: '26052' } });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://api.test/api/issues?limit=120&include_replay=0');
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://api.test/api/issues/26052/dashboard?view=summary');
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://api.test/api/issues/26052/decision-artifacts/status');
  });

  it('fetch mode calls canonical API paths and transforms minimal snake_case payloads', async () => {
    const payloads: Record<string, unknown> = {
      '/api/issues/26052/dashboard': {
	        issue: '26052',
	        status: 'open',
	        capture_status: 'partial',
	        stats: { n_matches: 14, qualified_legs: 17, qualified_matches: 10, q_avg: 1.2, pool_quality_flag: 'green' },
	        decision_variant_options: [
	          { variant_id: 'active_v3', label: 'v3', version: 'chain-v1', source: 'active_snapshot', is_default: false },
	          { variant_id: 'shadow_v3.3.1', label: 'shadow v3.3.1', version: 'chain-v3.3.1-shadow', source: 'structured_shadow_csv', source_path: 'shadow.csv', is_default: true },
	        ],
	        matches: [{
	          match_id: 'bjdc_26052_001', league: '日乙', kickoff_ts: '2026-06-30 19:00', home: '札幌', away: '横滨FC', handicap_line: -1,
	          score: '2-1', halftime_score: '1-0', live_score_status: 'finished', live_score_status_text: '完场',
	          sp_3: 2.1, sp_1: 3.55, sp_0: 3.2, eu_home: 1.86, eu_draw: 3.4, eu_away: 4.1, ah_line: -0.75, ah_home: 1.91, ah_away: 1.97,
	          line_gap: 0.25, sp_drift_3: -0.08, sp_drift_1: -0.03, sp_drift_0: 0.11, q_max: 1.2,
	          selection: '3', selection_codes: ['3'], selection_type: 'single',
	          model_selection: '3', model_selection_codes: ['3'], model_selection_type: 'single',
	          llm_selection: '1', llm_selection_codes: ['1', '0'], llm_selection_type: 'double', llm_q_score: 1.08, llm_probability: 0.31, llm_confidence_label: '中', llm_source: 'gpt_fixed_decision_chain_v1',
	          decision_variants: [
	            { variant_id: 'active_v3', label: 'v3', version: 'chain-v1', source: 'active_snapshot', is_default: false, recommendation: '押平，保负', primary_pick: '1', protect_picks: ['0'], selection_codes: ['1', '0'], selection_type: 'double', stop_flag: false, q_score: 1.08, probability: 0.31, coverage_hit: true },
	            { variant_id: 'shadow_v3.3.1', label: 'shadow v3.3.1', version: 'chain-v3.3.1-shadow', source: 'structured_shadow_csv', is_default: true, recommendation: '押胜', primary_pick: '3', protect_picks: [], selection_codes: ['3'], selection_type: 'single', stop_flag: false, q_score: 1.2, probability: 0.46, coverage_hit: false },
	          ],
	        }],
	      },
	      '/api/matches/bjdc_26052_001': {
	        match: { match_id: 'bjdc_26052_001', issue: '26052', league: '日乙', kickoff_ts: '2026-06-30T19:00:00+08:00', home: '札幌', away: '横滨FC', handicap_line: -1, status: 'open', score: '2-1', halftime_score: '1-0', live_score_status: 'finished', live_score_status_text: '完场', sp_3: 2.1, sp_1: 3.55, sp_0: 3.2, sp_snapshot_ts: '2026-06-30T18:20:00+08:00', sp_drift_band: '胜-4.2% 平-1.5% 负+9.1%', eu_home: 1.86, eu_draw: 3.4, eu_away: 4.1, ah_line: -0.75, ah_home: 1.91, ah_away: 1.97, line_gap: 0.25, odds_consensus: { n_companies: 42, open_avg: { home: 1.92, draw: 3.36, away: 4.05 }, current_avg: { home: 1.84, draw: 3.31, away: 4.42 }, drift: { home: -0.042, draw: -0.015, away: 0.091 }, providers: [{ company: 'Bet 365', open: { home: 1.91, draw: 3.4, away: 4.1 }, current: { home: 1.83, draw: 3.3, away: 4.5 } }] }, market_highlights: ['欧赔均值 主胜-4.2% 平-1.5% 客胜+9.1%'] },
	        decision_variant_options: [{ variant_id: 'active_v3', label: 'v3', version: 'chain-v1', source: 'active_snapshot', is_default: false }, { variant_id: 'shadow_v3.3.1', label: 'shadow v3.3.1', version: 'chain-v3.3.1-shadow', source: 'structured_shadow_csv', source_path: 'shadow.csv', is_default: true }],
	        decision_variants: [{ variant_id: 'active_v3', label: 'v3', version: 'chain-v1', source: 'active_snapshot', is_default: false, recommendation: '押平，保负', primary_pick: '1', protect_picks: ['0'], selection_codes: ['1', '0'], selection_type: 'double', stop_flag: false }, { variant_id: 'shadow_v3.3.1', label: 'shadow v3.3.1', version: 'chain-v3.3.1-shadow', source: 'structured_shadow_csv', is_default: true, recommendation: '押胜', primary_pick: '3', protect_picks: [], selection_codes: ['3'], selection_type: 'single', stop_flag: false }],
        analysis_500: { status: 'ok', fetched_at: '2026-06-30 15:40:00', title: '札幌VS横滨FC-数据分析-500彩票网', description: '500 detail', urls: { data: 'https://odds.500.com/fenxi/shuju-1.shtml' }, home_recent: { team: '札幌', summary: '近10场 5胜3平2负', rows: [] }, away_recent: { team: '横滨FC', summary: '近10场 4胜2平4负', rows: [] }, h2h: { summary: '交锋缺', rows: [] }, league_table: '积分摘要', source: 'odds.500.com/fenxi/shuju', highlights: ['主队主场胜率 50%'], market_summary: '欧赔均值 主胜-4.2% 平-1.5% 客胜+9.1%', odds_consensus: { n_companies: 42, open_avg: { home: 1.92, draw: 3.36, away: 4.05 }, current_avg: { home: 1.84, draw: 3.31, away: 4.42 }, drift: { home: -0.042, draw: -0.015, away: 0.091 }, providers: [] } },
        intelligence: { status: 'ok', fetched_at: '2026-06-30 15:41:00', headline: '26日乙第21轮', points: ['赛事阶段：联赛 第21轮', '资料观点：主队主场效率较高。'], tags: ['league_round', '500资料观点'], stage: { competition_label: '26日乙第21轮', stage_name: '联赛', stage_type: 'league_round', round: '21', home_standing: '4', away_standing: '12' }, sources: [{ source: '500_pc_shuju_macau', tier: 'editorial', status: 'ok', title: '26日乙第21轮', url: 'https://odds.500.com/fenxi/shuju-1.shtml' }], source_count: 1 },
        decision_snapshot: { snapshot_id: 'active_26052_001', status: 'active', generated_at: '2026-06-30T14:20:00+08:00', checked_at: '2026-06-30T14:21:00+08:00', input_hash: 'activehash', recommendation: '押平，保负', primary_pick: '1', protect_picks: ['0'], stop_flag: false, selection_codes: ['1', '0'], confidence: 0.64, confidence_label: '中', q_score: 1.2, probability: 0.29, prompt_version: 'prompt-v1', model_version: 'gpt-fixed-chain-v1', prob_model_version: 'prob-v1', q_model_version: 'q-v1', decision_chain_version: 'chain-v1', decision_config_hash: 'abcdef123456', review_tag_version: 'review-v1' },
        draft_decision_snapshot: { snapshot_id: 'draft_26052_001', status: 'draft_replacement', generated_at: '2026-06-30T14:40:00+08:00', checked_at: '2026-06-30T14:41:00+08:00', input_hash: 'drafthash', recommendation: '押负，保平', primary_pick: '0', protect_picks: ['1'], stop_flag: false, selection_codes: ['0', '1'], confidence: 0.62, confidence_label: '中', q_score: 1.1, probability: 0.25, prompt_version: 'prompt-v1', model_version: 'gpt-fixed-chain-v2', prob_model_version: 'prob-v1', q_model_version: 'q-v1', decision_chain_version: 'chain-v2', decision_config_hash: 'fedcba987654', review_tag_version: 'review-v1' },
        prediction: { q_score: 1.2, confidence_weight: 0.81, model_p_3: 0.46, model_p_1: 0.29, model_p_0: 0.25, market_p_3: 0.39, market_p_1: 0.31, market_p_0: 0.3, strategy_arms: [{ arm_id: 'current', selection: '1', selection_type: 'all', active: true }, { arm_id: 'allocator', selection: 'pass', selection_type: 'single', active: false }], llm_judgment: '1', llm_explanation: 'spec payload', llm_confidence: 0.65, llm_source: 'test', generated_ts: '2026-06-30T14:25:00+08:00' },
      },
      '/api/matches/bjdc_26052_001/decision-snapshot/confirm': {
        action: 'confirmed_override',
        confirmed_at: '2026-06-30T14:42:00+08:00',
        previous_active: { snapshot_id: 'active_26052_001', status: 'superseded', generated_at: '2026-06-30T14:20:00+08:00', checked_at: '2026-06-30T14:21:00+08:00', input_hash: 'activehash', recommendation: '押平，保负', primary_pick: '1', protect_picks: ['0'], stop_flag: false, selection_codes: ['1', '0'], prompt_version: 'prompt-v1', model_version: 'gpt-fixed-chain-v1', decision_chain_version: 'chain-v1', decision_config_hash: 'abcdef123456', superseded_at: '2026-06-30T14:42:00+08:00' },
        active: { snapshot_id: 'draft_26052_001', status: 'active', generated_at: '2026-06-30T14:40:00+08:00', checked_at: '2026-06-30T14:42:00+08:00', confirmed_at: '2026-06-30T14:42:00+08:00', input_hash: 'drafthash', recommendation: '押负，保平', primary_pick: '0', protect_picks: ['1'], stop_flag: false, selection_codes: ['0', '1'], prompt_version: 'prompt-v1', model_version: 'gpt-fixed-chain-v2', decision_chain_version: 'chain-v2', decision_config_hash: 'fedcba987654', supersedes_snapshot_id: 'active_26052_001' },
      },
      '/api/issues/26052/tickets?status=candidate': {
        issue: '26052', plan_id: '26052', tickets: [{ candidate_id: 'cand_1', n_legs: 1, coverage: 'double', coverage_detail: { n_full: 1, n_double: 1 }, stake_yuan: 20, expected_return_yuan: 25, pred_ev_per_stake: 1.25, expected_payout: 45, risk_warnings: ['ticket risk'], legs: [{ match_id: 'bjdc_26052_001', selection: '1', league: '日乙', home: '札幌', away: '横滨FC', handicap: -1, sp: 3.55, q_score: 1.2, cover_type: 'any' }] }], total: 1,
      },
      '/api/issues/26052/signals': {
        issue: '26052', generated_ts: '2026-06-30T14:30:00+08:00', freshness: 'live', signals: [{ match_id: 'bjdc_26052_001', qualified_options: [{ selection: '1', q_score: 1.2, sp_drift_band: 'warm', arms_recommending: ['current'] }] }],
      },
      '/api/issues/26052/settlement': {
        issue: '26052', settled_ts: '2026-06-30T10:15:00+08:00', n_tickets: 1, n_hits: 0, n_legs_total: 1, n_legs_hit: 0, n_legs_missed_by_1: 1, total_stake: 20, total_payout: 45, pnl: 25, roi: 1.25, quality_review: 'ok', per_match_settlements: [{ match_id: 'bjdc_26052_001', result_code: '0', winning_sp: 3.55, selected_by_arms: ['current'], arm_hits: { current: false }, sp_drift: -0.05 }],
        postmatch_review_issue_summary: { issue: '26052', review_version: 'v3_decision_variant_active_v3_3_3_tags', decision_variant_id: 'active_v3.3.3', reviewed_at: '2026-06-30 10:15:00', n_reviews: 9, stake: 32, gross_return: 42.64, profit: 10.64, roi: 0.3325, primary_hits: 5, protect_hits: 3, coverage_hits: 8, stopped_correct: 0, stopped_wrong: 0, tag_counts: { missed_draw: 2, uncovered_result: 1, uncovered_high_prob_alt: 1 } },
        postmatch_reviews: [{ issue: '26052', match_idx: 8, match_id: '26052_008', league: '女欧', home: '比利时', away: '塞内加尔', kickoff_ts: '2026-06-30T23:30:00+08:00', score: '1:1', halftime_score: '0:0', result_code: '1', result_label: '平', winning_sp: 2.95, llm_selection_codes: ['3'], llm_judgment: '押胜', outcome_label: '未中', primary_hit: false, protect_hit: false, coverage_hit: false, stopped: false, stake: 2, gross_return: 0, profit: -2, roi: -1, tags: ['missed_draw', 'uncovered_result', 'uncovered_high_prob_alt'], review_summary: '未命中：胜未覆盖实际平。', action_suggestion: '复查平局保护阈值。', reviewed_at: '2026-06-30 10:15:00' }],
      },
      '/api/strategies/lab': {
        strategies: [
          { strategy_id: 's1', strategy_name: 'Strategy 1', arms: [{ arm_id: 'current', arm_name: 'Current', active: true, roi: 1.16, profit: 209, hit_rate: 0.09, max_dd: -0.16, equity_curve: [100, 101], description: 'Reference' }], annual_performance: [{ year: 2024, n_issues: 10, tickets: 20, stake: 100, profit: 50, roi: 0.5, hit_rate: 0.1, max_dd: -0.1 }] },
          { strategy_id: 's2', strategy_name: 'Strategy 2', arms: [{ arm_id: 'challenger', arm_name: 'Challenger', active: false, roi: 0.5, profit: 80, hit_rate: 0.11, max_dd: -0.08, equity_curve: [100, 102], description: 'Candidate' }], annual_performance: [{ year: 2024, n_issues: 11, tickets: 21, stake: 110, profit: 55, roi: 0.5, hit_rate: 0.11, max_dd: -0.08 }] },
        ],
      },
      '/api/issues/26052/selector-shadow': {
        issue: '26052',
        rule_name: 'rule_x',
        mode: 'live-shadow',
        generated_at: '2026-06-30T14:40:00+08:00',
        current_decision: { chosen_arm: 'selector', baseline_arm: 'base', defensive_arm: 'def', state_signal: true, quality_signal: false, reason: 'loss_streak>=6', pre_loss_streak: 6, pre_drawdown_units: 9000, weak_count: 2, weak_score: 0.12, quality_history_issues: 120, budget_units: 384 },
        feature_flags: [{ feature: 'core_avg_q', value: 1.9, threshold: 1.8, weak: false, severity: 0 }],
        arms: [{ arm_id: 'selector', label: 'Selector', role: 'selector', profit_per_256: 100, roi: 0.2, max_drawdown_units: -50, max_loss_streak: 4, issue_win_rate: 0.2, full_loss_rate: 0.4, recent_profit_per_256: 20, delta_profit_per_256_vs_base: 10, delta_max_drawdown_units_vs_base: 5, delta_loss_streak_vs_base: -1 }],
        switch_attribution: [{ group: 'all', count: 1, delta_vs_base_units: 10, helped: 1, hurt: 0, flat: 0 }],
        rolling_stability: [{ window: 40, profit_positive_rate: 1, max_drawdown_positive_rate: 1, both_positive_rate: 1, avg_profit_delta: 10, avg_maxdrawdown_delta: 5, avg_loss_streak_delta: -1 }],
        recent_decisions: [{ issue: '26051', year: 2026, chosen_arm: 'selector', reason: 'test', delta_vs_base_units: 10, base_profit_units: -2, selector_profit_units: 8, weak_count: 2, pre_loss_streak: 6, pre_drawdown_units: 9000, outcome: 'helped' }],
        guardrail: 'shadow only',
      },
      '/api/issues/26052/main-strategy': {
        issue: '26052',
        generated_ts: '2026-06-30T14:45:00+08:00',
        mode: 'historical_replay',
        strategy_family: 'N=7 fixed-384 main strategy',
        candidates: [{ arm_id: 'b384_dd32_smooth100', label: 'A 稳健/回撤控制', role: 'stable', recommended_for: 'control DD', issue_budget: 384, extra_budget: 128, stake_units: 1000, profit_units: 200, profit_per_256: 100, roi: 0.2, issue_win_rate: 0.18, non_full_loss_rate: 0.71, full_loss_rate: 0.29, max_drawdown_units: -100, max_drawdown_per_256: -80, max_loss_streak: 3, max_dead_streak: 1, recent_profit_per_256: 50, recent_roi: 0.4, allocation: 'same_ticket4_full_risk=96', rationale: 'smooth', risk_tags: ['line_gap_diagnostic_only'] }],
        annual_performance: [{ arm_id: 'b384_dd32_smooth100', year: 2025, n_issues: 15, stake_units: 5760, profit_units: 100, roi: 0.1, issue_win_rate: 0.2, non_full_loss_rate: 0.7, max_drawdown_units: -300 }],
        ev_pool: { available: true, status: 'historical_replay', source: 'selected_tickets.csv', ticket_count: 1, tickets: [{ ticket_id: 't1', ticket_idx: 1, source_strategy: 'ev', n_legs: 7, stake_units: 8, pred_ev_per_stake: 12, pred_hit_prob: 0.01, hit: false, payout_units: 0, profit_units: -8, topology: 'neg0_7', avg_q_score: 2.1, avg_confidence_weight: 1.3, line_gap_support_net: 1, avg_abs_line_gap: 0.4, diagnostic_tags: ['historical_replay'], legs: [{ leg_id: 'L1', match_id: 'm1', label: 'A vs B', handicap: -1, beidan_handicap: -1, asian_1h_line: -0.5, line_gap: -0.5, selection_code: '0', selection_label: '负', result_code: '3', result_label: '胜', hit: false, winning_sp: 2.2, q_score: 2.1, confidence_weight: 1.3, selected_model_p: 0.3, selected_market_p: 0.2, pred_sp_multiplier: 0.8, diagnostic_tags: ['line_gap:oppose'] }] }] },
        live_proxy: null,
        risk_state: { latest_backtest_issue: '26051', risk_level: 'watch', recommended_arm: 'b384_dd32_smooth100', reason: 'watch', cooldown: { state: 'off', policy: 'fixed', pre_loss_streak: 2, pre_drawdown_units: -99 }, budget: { mode: 'fixed', selected_units: 384, base_units: 256, extra_units: 128, notes: 'fixed' }, guardrails: ['no mock fallback'] },
        diagnostics: { line_gap_policy: 'diagnostic_only_not_hard_gate', sp_drift_policy: 'diagnostic_only', paper_arms: [{ arm_id: 'paper_drift_top8_256', issues: 10, profit_per_256: 20, roi: 0.2, issue_win_rate: 0.03, non_full_loss_rate: 0.03, max_drawdown_units: -1000, max_loss_streak: 20, production_status: 'paper_convex_sleeve_only' }] },
        review: { source: 'sleeve_mix_issue_profit.csv', issues: [{ issue: '26051', issue_order: 1, calendar_year: 2026, issue_close_ts: '2026-05-02', arms: [{ arm_id: 'b384_dd32_smooth100', stake_units: 384, profit_units: -10, roi: -0.1, tickets: 1, hits: 0, parts: 'current:256', state: 'static', allocation: 'same_ticket4_full_risk=96' }] }] },
        source: { main_strategy_dir: 'main', ticket_pool_dir: 'pool', model_db: 'model.sqlite', live_db: 'live.sqlite', no_future_leakage: 'historical only' },
      },
      '/api/issues/26052/segment-betting-plan': {
        schema_version: 'segment_betting_plan_v1',
        issue: '26052',
        mode: 'settled_replay_shadow_planning',
        requested_decision_variant_id: '',
        requested_planning_scope: 'by_segment',
        requested_decision_time: '',
        selected_plan_id: '26052_v3.3.3_b1000_seed20260707',
        availability_status: 'available',
        notice: 'settled replay only',
        source: { artifact_key: 'segment_betting_plan_dir', artifact_dir: 'results/segment_betting_plan' },
        strategy_family: 'segment_betting_plan',
        betting_strategy_version: 'segment_betting_v0.4.0000',
        artifact_schema_version: 'segment_betting_artifact_v1',
        planning_scope: 'by_segment',
        artifact_planning_scope: 'next_segment',
        decision_time: '',
        available_segments: 2,
        sp_drift_risk: { accepted: false, level: 'low', reason: 'next segment only' },
        selection_binding: { match_selection_source: 'issue_board_same_decision_variant', frontend_display_source: 'issue_board', refresh_policy: 'match directions follow issue board artifact refresh' },
        available_plans: [{ plan_id: '26052_v3.3.3_b1000_seed20260707', label: 'v3.3.3', decision_variant_id: 'active_v3.3.3', strategy_family: 'segment_betting_plan', betting_strategy_version: 'segment_betting_v0.4.0000', artifact_schema_version: 'segment_betting_artifact_v1', planning_scope: 'by_segment', artifact_planning_scope: 'next_segment', decision_time: '', stake_mode: 'scale_to_budget', available_segments: 2, sp_drift_risk_accepted: false, sp_drift_risk_level: 'low', arm: 'shadow', segment_budget_yuan: 1000, sample_seed: 20260707, selected_bundles: 1, base_cost_yuan: 32, stake_multiplier_units: 2, selected_cost_yuan: 64, profit_yuan: 128, roi: 2 }],
        selected_plan: { plan_id: '26052_v3.3.3_b1000_seed20260707', label: 'v3.3.3', decision_variant_id: 'active_v3.3.3', strategy_family: 'segment_betting_plan', betting_strategy_version: 'segment_betting_v0.4.0000', artifact_schema_version: 'segment_betting_artifact_v1', planning_scope: 'by_segment', artifact_planning_scope: 'next_segment', decision_time: '', stake_mode: 'scale_to_budget', available_segments: 2, sp_drift_risk_accepted: false, sp_drift_risk_level: 'low', arm: 'shadow', segment_budget_yuan: 1000, sample_seed: 20260707, selected_bundles: 1, base_cost_yuan: 32, stake_multiplier_units: 2, selected_cost_yuan: 64, profit_yuan: 128, roi: 2 },
        settings: { planning_scope: 'by_segment', decision_time: '', stake_mode: 'scale_to_budget', window_hours: 12, segment_budget_yuan: 1000, sample_seed: 20260707, min_n: 3, max_n: 8, max_bundle_spend_pct: 0.4, positive_ev_only: true, betting_strategy_version: 'segment_betting_v0.4.0000' },
        summary: { segments: 1, selected_segments: 1, dead_segments: 0, selected_bundles: 1, base_cost_yuan: 32, stake_multiplier_units: 2, selected_cost_yuan: 64, payout_yuan: 192, profit_yuan: 128, roi: 2 },
        segments: [{ segment_idx: 1, arm: 'shadow', planning_scope: 'by_segment', artifact_planning_scope: 'next_segment', hours_from_decision_start: 2, hours_from_decision_end: 14, sp_drift_risk_accepted: false, sp_drift_risk_level: 'low', sp_drift_risk_reason: 'next segment only', stake_mode: 'scale_to_budget', segment_start: '2026-06-30 18:00', segment_end: '2026-07-01 06:00', window_hours: 12, eligible_matches: 8, expected_coverage_hit_rate: 0.7, actual_coverage_hits: 7, actual_coverage_hit_rate: 0.875, recommended_n: 5, selected_bundles: 1, candidate_bundles: 12, base_cost_yuan: 32, stake_multiplier_units: 2, selected_cost_yuan: 64, segment_budget_yuan: 1000, profit_yuan: 128, roi: 2, dead_segment: false, reasons: ['budget_coverage_ok'], match_indices: [1, 2, 3, 4, 5, 6, 7, 8] }],
        bundles: [{ segment_idx: 1, bundle_idx: 7, arm: 'shadow', n_value: 5, match_indices: [1, 2, 3, 4, 5], leg_codes: ['3+1', '0', '3', '1+0', '3+0'], widths: [2, 1, 1, 2, 2], stake_multiplier: 2, cost_yuan: 16, scaled_cost_yuan: 32, expected_profit_yuan: 64, scaled_expected_profit_yuan: 128, expected_roi: 4, hit_prob: 0.12, realized_hit: true, payout_yuan: 80, scaled_payout_yuan: 160, profit_yuan: 64, scaled_profit_yuan: 128 }],
      },
      '/api/issues/26052/operations': {
        issue: '26052',
        generated_at: '2026-07-03 00:50:00',
        issue_status: { current_issue: '26052', match_count: 14, finished_count: 9, settled_sp_count: 9, open_count: 5, capture_status: 'ok', latest_snapshot_at: '2026-07-02T16:44:28Z', latest_snapshot_age_minutes: 8 },
        runtime: {
          api_health: 'ok',
          api_url: '',
          api_health_url: '',
          api_port: '',
          frontend_health: 'ok',
          frontend_local_url: '',
          frontend_remote_url: '',
          frontend_port: '',
          checked_at: '2026-07-03T00:50:02+08:00',
          public_diagnostics: false,
          access_mode: 'local_only',
          external_access_configured: false,
          api_process_status: 'running',
          frontend_process_status: 'running',
          health: {
            api: { ok: true, status: 200, latency_ms: 1.2 },
            frontend_local: { ok: true, status: 200, latency_ms: 2.3 },
            operations: { ok: true, status: 200, latency_ms: 10.1, issue: '26052', workflow_status: 'dry_run', review_task_status: 'dry_run' },
            host_smoke_count: 1,
            host_smoke_ok_count: 1,
          },
        },
        sources: [{ source_name: 'issue_html', status: 'ok', last_attempt_at: '2026-07-02 16:44:27', last_success_at: '2026-07-02 16:44:27', age_minutes: 8, ok_count: 10, fail_count: 0, total_attempts: 10, rows_parsed: 140 }],
        snapshots: { active_count: 14, draft_replacement_count: 1, superseded_count: 0, pending_drafts: [{ match_idx: 8, match_id: '26052_008', generated_at: '2026-07-02 22:47:13', checked_at: '2026-07-02 22:47:13' }] },
        review: { review_version: 'v3_decision_variant_active_v3_3_3_tags', settled_match_count: 9, reviewed_match_count: 8, unreviewed_settled_count: 1, latest_review_at: '2026-07-03 00:45:00', unreviewed_matches: [{ match_idx: 4, match_id: '26052_004', label: '水原 vs 浦项', result_label: '平', winning_sp: 3.05 }], task: { run_id: 'pmr_26052_test', issue: '26052', mode: 'postmatch_review_v1', status: 'dry_run', dry_run: true, requested_by: 'test', started_at: '2026-07-03 00:49:00', finished_at: '2026-07-03 00:49:01', elapsed_sec: 0.9, trigger_endpoint: 'POST /api/issues/26052/postmatch-review?dry_run=1', command: ['python3'], result: { would_insert: 1, inserted: 0, coverage_hits: 8, profit: 10.64 } } },
        workflow: { run_id: 'wf_26052_test', issue: '26052', mode: 'live_day_refresh_v1', status: 'dry_run', dry_run: true, requested_by: 'test', started_at: '2026-07-03 00:50:00', finished_at: '2026-07-03 00:50:01', elapsed_sec: 1.2, trigger_endpoint: 'POST /api/issues/26052/live-workflow?dry_run=1', steps: [{ step_idx: 1, step_key: 'monitor_500_nowscore', label: '刷新 500/捷报/赛果/SP', status: 'planned', command: ['python3'], elapsed_sec: 0.1 }] },
        versions: { schema_version: 'decision_versions_v1', prob_model_version: 'prob-v1', q_model_version: 'q-v1', decision_chain_version: 'chain-v1', decision_prompt_version: 'prompt-v1', decision_model_version: 'model-v1', review_tag_version: 'review-v1', review_version: 'v3_decision_variant_active_v3_3_3_tags', decision_config_hash: 'abcdef123456', config_path: 'config/decision_versions.json' },
        warnings: [{ code: 'draft_replacement_pending', severity: 'warn', label: '1 条 draft 待确认', detail: 'manual confirm required' }],
        source: { sqlite_db: 'redacted', tables: ['matches', 'fetch_log'] },
      },
      '/api/issues/26052/postmatch-review?dry_run=1': {
        run_id: 'pmr_26052_dry',
        issue: '26052',
        mode: 'postmatch_review_v1',
        status: 'dry_run',
        dry_run: true,
        requested_by: 'test',
        started_at: '2026-07-03 01:00:00',
        finished_at: '2026-07-03 01:00:01',
        elapsed_sec: 0.7,
        trigger_endpoint: 'POST /api/issues/26052/postmatch-review?dry_run=1',
        command: ['python3', 'scripts/review_settled_matches.py', '--dry-run'],
        result: { would_insert: 1, inserted: 0, coverage_hits: 8, profit: 10.64 },
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input).replace('http://api.test', '');
      return { ok: true, json: async () => payloads[url] } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    window.localStorage.setItem('BEIDAN_OPERATOR_TOKEN', 'test-token');

    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });

    await expect(adapter.getIssueDashboard('26052')).resolves.toMatchObject({ issueId: '26052', matchCount: 14, qualifiedCandidateCount: 10, dataCompleteRate: 0.5, decisionVariantOptions: [{ variantId: 'active_v3' }, { variantId: 'shadow_v3.3.1' }], matches: [{ matchId: 'bjdc_26052_001', kickoffTime: '19:00', qScore: 1.08, recommendedOutcome: '平+负', primaryBetOutcome: '平', protectionOutcomes: ['负'], modelRecommendedOutcome: '胜', recommendationSource: 'LLM', score: '2-1', halftimeScore: '1-0', scoreStatus: 'finished', decisionVariants: [{ variantId: 'active_v3' }, { variantId: 'shadow_v3.3.1', primaryPick: '3', selectionType: 'single' }] }] });
    await expect(adapter.getMatchDetail('26052', 'bjdc_26052_001')).resolves.toMatchObject({ issueId: '26052', matchId: 'bjdc_26052_001', qScore: 1.2, confidence: 0.81, halftimeScore: '1-0', selectedOutcomes: ['平'], recommendedCoverage: 'full', decisionVariantOptions: [{ variantId: 'active_v3' }, { variantId: 'shadow_v3.3.1' }], decisionVariants: [{ variantId: 'active_v3' }, { variantId: 'shadow_v3.3.1', primaryPick: '3' }], oddsConsensus: { nCompanies: 42, currentAvg: { away: 4.42 } }, marketHighlights: ['欧赔均值 主胜-4.2% 平-1.5% 客胜+9.1%'], decisionSnapshot: { primaryPick: '1', protectPicks: ['0'], decisionChainVersion: 'chain-v1' }, draftDecisionSnapshot: { primaryPick: '0', protectPicks: ['1'], decisionChainVersion: 'chain-v2' }, analysis500: { status: 'ok', homeRecent: { summary: '近10场 5胜3平2负' }, marketSummary: '欧赔均值 主胜-4.2% 平-1.5% 客胜+9.1%' }, intelligence: { status: 'ok', headline: '26日乙第21轮', points: ['赛事阶段：联赛 第21轮', '资料观点：主队主场效率较高。'], stage: { stageType: 'league_round' }, sourceCount: 1 } });
    await expect(adapter.getTicketDraft('26052')).resolves.toMatchObject({ issueId: '26052', ticketId: 'cand_1', ticketName: '26052', totalBudget: 20, totalCombinations: 6, legs: [{ matchId: 'bjdc_26052_001', coverageType: 'full', riskTags: ['ticket risk'] }] });
    await expect(adapter.getLiveSignals('26052')).resolves.toMatchObject({ issueId: '26052', alerts: [{ matchId: 'bjdc_26052_001', alertType: 'model_changed' }] });
    await expect(adapter.getSettlementReview('26052')).resolves.toMatchObject({ issueId: '26052', totalStake: 32, netReturn: 10.64, grossReturn: 42.64, postmatchSummary: { reviewCount: 9, primaryHits: 5, protectHits: 3, coverageHits: 8, tagCounts: { missed_draw: 2, uncovered_result: 1 } }, postmatchReviews: [{ matchId: '26052_008', matchIdx: 8, selectedOutcomes: ['胜'], resultLabel: '平', outcomeLabel: '未中', tags: ['missed_draw', 'uncovered_result', 'uncovered_high_prob_alt'] }], ticketResults: [{ ticketId: 'summary', hitLegs: 8, missedByLegs: 1, missedProtection: 1 }], legReviews: [{ matchId: 'bjdc_26052_001', hit: false, actualResult: '负', selectedOutcomes: [], tags: ['arm:current'] }] });
    await expect(adapter.getStrategyLab()).resolves.toMatchObject({ arms: [{ armId: 'current', maxDrawdown: -0.16 }, { armId: 'challenger', maxDrawdown: -0.08 }], annualPerformance: [{ armId: 's1', year: 2024, totalStake: 100 }, { armId: 's2', year: 2024, totalStake: 110 }] });
    await expect(adapter.getSelectorShadow('26052')).resolves.toMatchObject({ issueId: '26052', ruleName: 'rule_x', currentDecision: { chosenArm: 'selector' }, recentDecisions: [{ outcome: 'helped' }] });
    await expect(adapter.getMainStrategy('26052')).resolves.toMatchObject({ issueId: '26052', candidates: [{ armId: 'b384_dd32_smooth100' }], evPool: { tickets: [{ ticketId: 't1', legs: [{ selectionLabel: '负', hit: false }] }] }, riskState: { recommendedArm: 'b384_dd32_smooth100' } });
    await expect(adapter.getSegmentBettingPlan('26052')).resolves.toMatchObject({ issueId: '26052', bettingStrategyVersion: 'segment_betting_v0.4.0000', planningScope: 'by_segment', artifactPlanningScope: 'next_segment', spDriftRisk: { accepted: false, level: 'low' }, selectedPlanId: '26052_v3.3.3_b1000_seed20260707', selectedPlan: { stakeMode: 'scale_to_budget', baseCostYuan: 32, stakeMultiplierUnits: 2, artifactPlanningScope: 'next_segment' }, settings: { stakeMode: 'scale_to_budget', maxBundleSpendPct: 0.4 }, selectionBinding: { frontendDisplaySource: 'issue_board' }, summary: { baseCostYuan: 32, stakeMultiplierUnits: 2, selectedCostYuan: 64, profitYuan: 128 }, segments: [{ recommendedN: 5, planningScope: 'by_segment', spDriftRiskAccepted: false, stakeMode: 'scale_to_budget', baseCostYuan: 32, stakeMultiplierUnits: 2 }], bundles: [{ realizedHit: true, legCodes: ['3+1', '0', '3', '1+0', '3+0'], stakeMultiplier: 2, scaledCostYuan: 32, scaledProfitYuan: 128 }] });
    await expect(adapter.getOperationsStatus('26052')).resolves.toMatchObject({ issueId: '26052', runtime: { apiPort: '', frontendPort: '', publicDiagnostics: false, accessMode: 'local_only', health: { hostSmokeCount: 1, hostSmokeOkCount: 1, operations: { workflowStatus: 'dry_run', reviewTaskStatus: 'dry_run' } } }, snapshots: { draftReplacementCount: 1, pendingDrafts: [{ matchId: '26052_008' }] }, review: { unreviewedSettledCount: 1, task: { runId: 'pmr_26052_test', status: 'dry_run', result: { wouldInsert: 1, profit: 10.64 } } }, workflow: { runId: 'wf_26052_test', status: 'dry_run', dryRun: true, steps: [{ stepKey: 'monitor_500_nowscore' }] }, versions: { decisionConfigHash: 'abcdef123456' } });
    await expect(adapter.confirmDecisionSnapshot('bjdc_26052_001')).resolves.toMatchObject({ action: 'confirmed_override', confirmedAt: '2026-06-30 14:42', active: { snapshotId: 'draft_26052_001', status: 'active', confirmedAt: '2026-06-30 14:42', supersedesSnapshotId: 'active_26052_001' }, previousActive: { snapshotId: 'active_26052_001', supersededAt: '2026-06-30 14:42' } });
    await expect(adapter.runPostmatchReview('26052', true)).resolves.toMatchObject({ runId: 'pmr_26052_dry', status: 'dry_run', result: { wouldInsert: 1, profit: 10.64 } });

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://api.test/api/issues/26052/dashboard');
    expect(fetchMock).toHaveBeenNthCalledWith(2, 'http://api.test/api/matches/bjdc_26052_001');
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://api.test/api/issues/26052/tickets?status=candidate');
    expect(fetchMock).toHaveBeenNthCalledWith(4, 'http://api.test/api/issues/26052/signals');
    expect(fetchMock).toHaveBeenNthCalledWith(5, 'http://api.test/api/issues/26052/settlement');
    expect(fetchMock).toHaveBeenNthCalledWith(6, 'http://api.test/api/strategies/lab');
    expect(fetchMock).toHaveBeenNthCalledWith(7, 'http://api.test/api/issues/26052/selector-shadow');
    expect(fetchMock).toHaveBeenNthCalledWith(8, 'http://api.test/api/issues/26052/main-strategy');
    expect(fetchMock).toHaveBeenNthCalledWith(9, 'http://api.test/api/issues/26052/segment-betting-plan');
    expect(fetchMock).toHaveBeenNthCalledWith(10, 'http://api.test/api/issues/26052/operations');
    expect(fetchMock).toHaveBeenNthCalledWith(11, 'http://api.test/api/matches/bjdc_26052_001/decision-snapshot/confirm', { method: 'POST', headers: { 'X-Beidan-Operator-Token': 'test-token' } });
    expect(fetchMock).toHaveBeenNthCalledWith(12, 'http://api.test/api/issues/26052/postmatch-review?dry_run=1', { method: 'POST', headers: { 'X-Beidan-Operator-Token': 'test-token' } });
  });

	  it('passes segment betting scope controls to the API', async () => {
	    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
	      const url = String(input).replace('http://api.test', '');
	      expect(url).toBe('/api/issues/26052/segment-betting-plan?decision_variant=active_v3.3.3&planning_scope=entire_issue&segment_budget_yuan=1000&stake_mode=scale_to_budget');
	      return {
	        ok: true,
	        json: async () => ({
	          issue: '26052',
	          requested_decision_variant_id: 'active_v3.3.3',
	          requested_planning_scope: 'entire_issue',
	          requested_segment_budget_yuan: 1000,
	          requested_stake_mode: 'scale_to_budget',
	          selected_plan_id: 'planA',
	          availability_status: 'available',
	          planning_scope: 'entire_issue',
	          sp_drift_risk: { accepted: true, level: 'elevated', reason: 'remaining issue selected' },
	          source: {},
          available_plans: [],
          settings: {},
          summary: {},
          segments: [],
          bundles: [],
        }),
      } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

	    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });
	    await expect(adapter.getSegmentBettingPlan('26052', 'active_v3.3.3', undefined, {
	      planningScope: 'entire_issue',
	      segmentBudgetYuan: 1000,
	      stakeMode: 'scale_to_budget',
	    })).resolves.toMatchObject({
	      issueId: '26052',
	      requestedPlanningScope: 'entire_issue',
	      requestedSegmentBudgetYuan: 1000,
	      requestedStakeMode: 'scale_to_budget',
	      planningScope: 'entire_issue',
	      spDriftRisk: { accepted: true, level: 'elevated' },
	    });
  });

  it('dashboard aggregate passes the selected decision variant to versioned API endpoints', async () => {
    const payloads: Record<string, unknown> = {
      '/api/issues?limit=120': {
        issues: [{ issue: '26052', label: '26052', status: 'current', is_current: true, has_settlement: false, is_fully_settled: false, match_count: 1 }],
      },
      '/api/issues/26052/dashboard?decision_variant=active_v3.3.3': {
        issue: '26052',
        status: 'open',
        stats: { n_matches: 1 },
        matches: [{ match_id: 'bjdc_26052_001', issue: '26052', selected_decision_variant_id: 'active_v3.3.3' }],
        strategy_version_context: {
          schema_version: 'strategy_version_context_v1',
          requested_variant_id: 'active_v3.3.3',
          selected_variant_id: 'active_v3.3.3',
          selection_status: 'ok',
          available_variant_ids: ['active_v3', 'active_v3.3.3'],
          options: [
            { variant_id: 'active_v3', kind: 'active', label: 'v3', version: 'llm_chain_bet_protect_stop_v3', source: 'active_snapshot', is_default: false },
            { variant_id: 'active_v3.3.3', kind: 'shadow', label: '正式版 v3.3.3', version: 'llm_chain_bet_protect_stop_v3.3.3_shadow', source: 'structured_shadow_csv', artifact_key: 'shadow_v3_3_3', is_default: true },
          ],
        },
      },
      '/api/matches/bjdc_26052_001?decision_variant=active_v3.3.3': {
        match: { match_id: 'bjdc_26052_001', issue: '26052', selected_decision_variant_id: 'active_v3.3.3' },
        prediction: {},
        strategy_version_context: {
          schema_version: 'strategy_version_context_v1',
          requested_variant_id: 'active_v3.3.3',
          selected_variant_id: 'active_v3.3.3',
          selection_status: 'ok',
          available_variant_ids: ['active_v3', 'active_v3.3.3'],
          options: [{ variant_id: 'active_v3.3.3', kind: 'shadow', label: '正式版 v3.3.3', version: 'llm_chain_bet_protect_stop_v3.3.3_shadow', source: 'structured_shadow_csv' }],
        },
      },
      '/api/issues/26052/tickets?status=candidate': { issue: '26052', tickets: [] },
      '/api/issues/26052/signals': { issue: '26052', signals: [] },
      '/api/issues/26052/settlement?decision_variant=active_v3.3.3': { issue: '26052', settled_ts: '', postmatch_reviews: [] },
      '/api/strategies/lab': { strategies: [] },
      '/api/issues/26052/selector-shadow': { issue: '26052', rule_name: 'rule_x', current_decision: {}, arms: [], switch_attribution: [], rolling_stability: [], recent_decisions: [] },
      '/api/issues/26052/main-strategy?decision_variant=active_v3.3.3': {
        issue: '26052',
        candidates: [],
        annual_performance: [],
        ev_pool: { tickets: [] },
        risk_state: { cooldown: {}, budget: {} },
        diagnostics: {},
        review: { issues: [] },
        source: {},
        strategy_version_context: {
          schema_version: 'strategy_version_context_v1',
          requested_variant_id: 'active_v3.3.3',
          selected_variant_id: 'active_v3.3.3',
          selection_status: 'ok',
          available_variant_ids: ['active_v3', 'active_v3.3.3'],
          options: [{ variant_id: 'active_v3.3.3', kind: 'shadow', label: '正式版 v3.3.3', version: 'llm_chain_bet_protect_stop_v3.3.3_shadow', source: 'structured_shadow_csv' }],
        },
      },
      '/api/issues/26052/segment-betting-plan?decision_variant=active_v3.3.3': {
        schema_version: 'segment_betting_plan_v1',
        issue: '26052',
        mode: 'settled_replay_shadow_planning',
        requested_decision_variant_id: 'active_v3.3.3',
        selected_plan_id: '26052_v3.3.3_b1000_seed20260707',
        availability_status: 'available',
        notice: 'settled replay only',
        source: { artifact_key: 'segment_betting_plan_dir', artifact_dir: 'results/segment_betting_plan' },
        available_plans: [{ plan_id: '26052_v3.3.3_b1000_seed20260707', label: 'v3.3.3', decision_variant_id: 'active_v3.3.3', arm: 'shadow', segment_budget_yuan: 1000, sample_seed: 20260707 }],
        selected_plan: { plan_id: '26052_v3.3.3_b1000_seed20260707', label: 'v3.3.3', decision_variant_id: 'active_v3.3.3', arm: 'shadow', segment_budget_yuan: 1000, sample_seed: 20260707 },
        settings: { segment_budget_yuan: 1000, sample_seed: 20260707 },
        summary: { selected_bundles: 0, selected_cost_yuan: 0, profit_yuan: 0, roi: 0 },
        segments: [],
        bundles: [],
      },
      '/api/issues/26052/operations': { issue: '26052', issue_status: {}, runtime: {}, sources: [], snapshots: {}, review: {}, versions: {}, warnings: [], source: {} },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input).replace('http://api.test', '');
      if (!(url in payloads)) throw new Error(`unexpected URL ${url}`);
      return { ok: true, json: async () => payloads[url] } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });
    await expect(adapter.getDashboardData('26052', undefined, 'active_v3.3.3')).resolves.toMatchObject({
      issue: { strategyVersionContext: { selectedVariantId: 'active_v3.3.3' } },
      matchDetail: { strategyVersionContext: { selectedVariantId: 'active_v3.3.3' } },
      mainStrategy: { strategyVersionContext: { selectedVariantId: 'active_v3.3.3' } },
      segmentBettingPlan: { requestedDecisionVariantId: 'active_v3.3.3' },
    });

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/issues/26052/dashboard?decision_variant=active_v3.3.3');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/matches/bjdc_26052_001?decision_variant=active_v3.3.3');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/issues/26052/settlement?decision_variant=active_v3.3.3');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/issues/26052/main-strategy?decision_variant=active_v3.3.3');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/issues/26052/segment-betting-plan?decision_variant=active_v3.3.3');
    expect(fetchMock).not.toHaveBeenCalledWith('http://api.test/api/issues/26052/dashboard');
  });

  it('dashboard aggregate tolerates canonical settlement 404 for open issues', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input).replace('http://api.test', '');
      if (url === '/api/issues/26052/settlement') return { ok: false, status: 404, json: async () => ({}) } as Response;
      const payloads: Record<string, unknown> = {
        '/api/issues/26052/dashboard': { issue: '26052', status: 'open', stats: { n_matches: 0 }, matches: [] },
        '/api/matches/bjdc_26052_001': { match: { match_id: 'bjdc_26052_001', issue: '26052' }, prediction: {} },
        '/api/issues/26052/tickets?status=candidate': { issue: '26052', tickets: [] },
        '/api/issues/26052/signals': { issue: '26052', signals: [] },
        '/api/issues/26052/selector-shadow': { issue: '26052', rule_name: 'rule_x', current_decision: {}, arms: [], switch_attribution: [], rolling_stability: [], recent_decisions: [] },
        '/api/issues/26052/main-strategy': { issue: '26052', candidates: [], annual_performance: [], ev_pool: { tickets: [] }, risk_state: { cooldown: {}, budget: {} }, diagnostics: {}, review: { issues: [] }, source: {} },
        '/api/issues/26052/segment-betting-plan': { issue: '26052', availability_status: 'missing', source: {}, available_plans: [], settings: {}, summary: {}, segments: [], bundles: [] },
        '/api/issues/26052/operations': { issue: '26052', issue_status: {}, runtime: {}, sources: [], snapshots: {}, review: {}, versions: {}, warnings: [], source: {} },
        '/api/strategies/lab': { strategies: [] },
      };
      return { ok: true, json: async () => payloads[url] } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });
    await expect(adapter.getDashboardData('26052', 'bjdc_26052_001')).resolves.toMatchObject({
      issue: { issueId: '26052', settlementStatus: 'open' },
      settlement: { issueId: '26052', ticketCount: 0, errorTags: ['not_settled'] },
    });
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/issues/26052/settlement');
  });

  it('dashboard aggregate derives default match from fetched issue dashboard in fetch mode', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input).replace('http://api.test', '');
      const payloads: Record<string, unknown> = {
        '/api/issues/26099/dashboard': { issue: '26099', status: 'open', stats: { n_matches: 1 }, matches: [{ match_id: 'bjdc_26099_007' }] },
        '/api/matches/bjdc_26099_007': { match: { match_id: 'bjdc_26099_007', issue: '26099' }, prediction: {} },
        '/api/issues/26099/tickets?status=candidate': { issue: '26099', tickets: [] },
        '/api/issues/26099/signals': { issue: '26099', signals: [] },
        '/api/issues/26099/settlement': { issue: '26099', settled_ts: '2026-06-30T10:15:00+08:00' },
        '/api/issues/26099/selector-shadow': { issue: '26099', rule_name: 'rule_x', current_decision: {}, arms: [], switch_attribution: [], rolling_stability: [], recent_decisions: [] },
        '/api/issues/26099/main-strategy': { issue: '26099', candidates: [], annual_performance: [], ev_pool: { tickets: [] }, risk_state: { cooldown: {}, budget: {} }, diagnostics: {}, review: { issues: [] }, source: {} },
        '/api/issues/26099/segment-betting-plan': { issue: '26099', availability_status: 'missing', source: {}, available_plans: [], settings: {}, summary: {}, segments: [], bundles: [] },
        '/api/issues/26099/operations': { issue: '26099', issue_status: {}, runtime: {}, sources: [], snapshots: {}, review: {}, versions: {}, warnings: [], source: {} },
        '/api/strategies/lab': { strategies: [] },
      };
      return { ok: true, json: async () => payloads[url] } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    const adapter = new ApiDashboardAdapter({ mode: 'fetch', baseUrl: 'http://api.test' });
    await expect(adapter.getDashboardData('26099')).resolves.toMatchObject({ matchDetail: { matchId: 'bjdc_26099_007', issueId: '26099' } });
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/matches/bjdc_26099_007');
  });
});
