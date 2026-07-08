import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, BarChart3, CheckCircle2, Clock, Database, Gauge, LineChart, Server, ShieldAlert, WalletCards } from 'lucide-react';
import { ApiDashboardAdapter } from './data/apiAdapter';
import { ACTIVE_DECISION_VARIANT_ID, DEFAULT_DECISION_VARIANT_ID, decisionVersionLabel, displayableDecisionVariants, isActiveDecisionVariant, isShadowDecisionVariant } from './decisionVariants';
import type { DashboardData, DecisionArtifactStatusData, DecisionVariantData, DecisionVariantOption, IssueDashboardData, IssueMatchRow, IssueOption } from './data/types';

type Page = 'Issue Dashboard' | 'Match Detail' | 'Operations' | 'Betting Plan' | 'Live Signals' | 'Settlement Review' | 'Strategy Lab';
const pages: Page[] = ['Issue Dashboard', 'Settlement Review', 'Betting Plan', 'Operations', 'Live Signals', 'Strategy Lab'];
const UI_BUILD_LABEL = 'UI betting-scope-v0400-0140';
const PAGE_LABELS: Record<Page, string> = {
  'Issue Dashboard': '期次看板',
  'Settlement Review': '赛后复盘',
  'Betting Plan': '下注设计',
  Operations: '运行状态',
  'Live Signals': '实时信号',
  'Strategy Lab': '策略实验',
  'Match Detail': '比赛详情',
};
const DEFAULT_BETTING_PLAN_SCOPE = 'by_segment';
const BETTING_PLAN_SCOPE_OPTIONS = [
  { value: 'by_segment', label: '分段下注' },
  { value: 'entire_issue', label: '整期下注' },
] as const;
type BettingPlanScope = typeof BETTING_PLAN_SCOPE_OPTIONS[number]['value'];
type ConfirmDraftState = { matchId: string; status: 'submitting' | 'succeeded' | 'failed'; message: string };
type ReviewTaskState = { issueId: string; status: 'submitting' | 'succeeded' | 'failed'; message: string };
type ArtifactGenerateState = { issueId: string; variantId: string; status: 'submitting' | 'succeeded' | 'failed'; message: string };
type DashboardShellData = {
  availableIssues: IssueOption[];
  issue: IssueDashboardData;
} & Partial<Omit<DashboardData, 'availableIssues' | 'issue'>>;
type DeferredPageState = { page: Page; status: 'loading' | 'refreshing'; message: string };

const statusLabel: Record<string, string> = { ok: '', partial: '部分数据', missing: '缺数据', failed: '抓取失败', stale: '过期' };
const coverageLabel: Record<string, string> = { single: '单选', double: '双选', full: '全包', 'no-buy': '不买' };

function pct(value?: number) {
  return value === undefined ? '缺失' : `${Math.round(value * 100)}%`;
}

function pct1(value?: number) {
  return value === undefined ? '缺失' : `${(value * 100).toFixed(1)}%`;
}

function signedPct(value?: number) {
  if (value === undefined) return '缺';
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function signedPp(value?: number) {
  if (value === undefined) return '缺';
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}pp`;
}

function money(value: number) {
  return `${value < 0 ? '-' : ''}¥${Math.abs(value).toLocaleString('zh-CN')}`;
}

function moneyFixed(value: number | undefined, digits = 2) {
  if (value === undefined || !Number.isFinite(value)) return '缺失';
  const sign = value < 0 ? '-' : '';
  return `${sign}¥${Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

function units(value: number, digits = 0) {
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}${Math.abs(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

function localIsoDate(date = new Date()) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function isCurrentOrFutureDate(value: string, today = localIsoDate()) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= today;
}

const Q_FOCUS_THRESHOLD = 1.5;
const CONFIDENCE_FOCUS_THRESHOLD = 0.45;
type PickCode = '3' | '1' | '0';
const REVIEW_TAG_LABELS: Record<string, string> = {
  had_pre_match_risks: '赛前风险',
  intel_misread: '情报误读',
  line_gap_warning_ignored: '让球偏移未处理',
  low_sp_double_negative_ev: '双选低赔负EV',
  missed_draw: '漏平',
  missed_protection: '错过保护',
  not_settled: '未结算',
  primary_hit: '主押命中',
  protection_saved: '保护救票',
  quality_only_switches: '质量信号切换',
  q_trap: 'q陷阱',
  recent_ex_best_negative: '近期最优反向',
  sp_drift_error: 'SP漂移误判',
  stop_unknown: '停牌未知',
  stop_wrong: '停牌错误',
  under_coverage: '覆盖不足',
  uncovered_high_prob_alt: '高概率替代未覆盖',
  uncovered_result: '未覆盖赛果',
  weak_recent_2024_2025: '近年弱势区间',
  wrong_favorite: '热门方向错误',
};

function dashboardApiBaseUrl(configured?: string) {
  const value = configured?.trim();
  if (!value) return '';
  if (typeof window === 'undefined') return value;
  const pageHost = window.location.hostname;
  const isRemotePage = pageHost !== '127.0.0.1' && pageHost !== 'localhost';
  if (!isRemotePage) return value;
  try {
    const url = new URL(value);
    if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') {
      return `${url.protocol}//${pageHost}:${url.port || '8790'}`;
    }
  } catch {
    return value;
  }
  return value;
}

function focusValueClass(value: number | undefined, threshold: number) {
  return value !== undefined && value >= threshold ? 'focus-value' : undefined;
}

function isSettlementReviewIssue(issue: DashboardData['availableIssues'][number]) {
  return Boolean(issue.hasSettlement && issue.isFullySettled && (issue.matchCount ?? 0) > 0);
}

function reviewTagLabel(tag: string) {
  if (REVIEW_TAG_LABELS[tag]) return REVIEW_TAG_LABELS[tag];
  if (tag.startsWith('arm:')) return '策略臂标签';
  return '其他错因';
}

type SettlementReviewRow = DashboardData['settlement']['postmatchReviews'][number];

function matchRef(row: SettlementReviewRow) {
  const teams = row.home && row.away ? `${row.home} vs ${row.away}` : row.home || row.matchId;
  return `#${row.matchIdx} ${teams}`;
}

function matchRefs(rows: SettlementReviewRow[], limit = 4) {
  const shown = rows.slice(0, limit).map(matchRef);
  const more = rows.length > limit ? `等${rows.length}场` : '';
  return [...shown, more].filter(Boolean).join('、') || '无';
}

function profitSum(rows: SettlementReviewRow[]) {
  return rows.reduce((total, row) => total + row.profit, 0);
}

function settlementTakeaways(data: DashboardData['settlement']) {
  const rows = data.postmatchReviews;
  if (!rows.length) return [{ tone: 'neutral' as const, title: '暂无可复盘比赛', body: '等待赛果后生成整期结论。' }];
  const summary = data.postmatchSummary;
  const reviewCount = summary?.reviewCount ?? rows.length;
  const coverageHits = summary?.coverageHits ?? rows.filter((row) => row.coverageHit).length;
  const primaryHits = summary?.primaryHits ?? rows.filter((row) => row.primaryHit).length;
  const protectRows = rows.filter((row) => row.protectHit);
  const missRows = rows.filter((row) => !row.coverageHit && !row.stopped);
  const missedDrawRows = missRows.filter((row) => row.resultLabel === '平' || row.tags.includes('missed_draw'));
  const qTrapRows = rows.filter((row) => row.tags.includes('q_trap'));
  const lowSpRows = rows.filter((row) => row.tags.includes('low_sp_double_negative_ev'));
  const topProfitRows = [...rows].filter((row) => row.profit > 0).sort((a, b) => b.profit - a.profit).slice(0, 4);
  const takeaways = [
    {
      tone: data.netReturn >= 0 ? 'good' as const : 'bad' as const,
      title: '本期不是方向全错，而是覆盖结构问题',
      body: `投入 ${money(data.totalStake)}，回报 ${money(data.grossReturn)}，净收益 ${money(data.netReturn)}，ROI ${pct(data.roi)}。主押命中 ${primaryHits}/${reviewCount}，押+保覆盖 ${coverageHits}/${reviewCount}，完全未覆盖 ${missRows.length}/${reviewCount}。`,
    },
    {
      tone: 'good' as const,
      title: '保护腿有实际价值',
      body: `保护救回 ${protectRows.length} 场，净贡献 ${money(profitSum(protectRows))}：${matchRefs(protectRows)}。这说明“押胜率，q 方向做保”的思路在本期是有效的。`,
    },
    {
      tone: missedDrawRows.length ? 'bad' as const : 'good' as const,
      title: '最大漏点是平局保护不足',
      body: missedDrawRows.length
        ? `${missRows.length} 场未覆盖里有 ${missedDrawRows.length} 场实际为平：${matchRefs(missedDrawRows)}。下一步应把“热门方向 + 让球偏移/情报反证/实力接近”作为保平触发，而不是只看最大 q。`
        : '本期未出现明显漏平，平局保护没有暴露为主要问题。',
    },
    {
      tone: lowSpRows.length ? 'warn' as const : 'neutral' as const,
      title: '低SP双选不要当成收益来源',
      body: lowSpRows.length
        ? `${matchRefs(lowSpRows)} 命中仍合计 ${money(profitSum(lowSpRows))}；这类票只能作为高N防死腿成本，不能因为“猜中”就加深资金。`
        : '本期没有明显“命中但负EV”的低SP双选。',
    },
    {
      tone: qTrapRows.length ? 'warn' as const : 'neutral' as const,
      title: 'q 高不等于主押方向可靠',
      body: qTrapRows.length
        ? `q陷阱集中在 ${matchRefs(qTrapRows)}。处理上应先用胜率/情报/让球一致性决定主押，再让高 q 的反向结果进入保护层。`
        : '本期没有明显 q 陷阱标签。',
    },
    {
      tone: 'good' as const,
      title: '利润来自高SP命中与高SP保护',
      body: `主要正贡献：${topProfitRows.map((row) => `${matchRef(row)} ${money(row.profit)}`).join('、') || '无'}。下一轮重点保留这种“有胜率支撑且SP不低”的腿。`,
    },
  ];
  return takeaways;
}

function settlementFocusRows(data: DashboardData['settlement']) {
  const rows = data.postmatchReviews;
  const focus: Array<{ key: string; label: string; tone: 'good' | 'warn' | 'bad' | 'neutral'; row: SettlementReviewRow; reason: string }> = [];
  const pushRows = (label: string, tone: 'good' | 'warn' | 'bad' | 'neutral', selectedRows: SettlementReviewRow[], reason: (row: SettlementReviewRow) => string) => {
    for (const row of selectedRows) {
      const key = `${label}-${row.matchId}`;
      if (focus.some((item) => item.key === key)) continue;
      focus.push({ key, label, tone, row, reason: reason(row) });
    }
  };
  pushRows(
    '未覆盖',
    'bad',
    rows.filter((row) => !row.coverageHit && !row.stopped).sort((a, b) => a.profit - b.profit).slice(0, 5),
    (row) => row.summary || `${row.llmJudgment || row.selectedOutcomes.join('+') || '未下注'} 未覆盖实际 ${row.resultLabel || '-'}。`,
  );
  pushRows(
    '保护救回',
    'good',
    rows.filter((row) => row.protectHit).sort((a, b) => b.profit - a.profit).slice(0, 4),
    (row) => row.summary || `保护命中 ${row.resultLabel || '-'}，说明该腿反向风险值得覆盖。`,
  );
  pushRows(
    '正贡献',
    'good',
    rows.filter((row) => row.profit > 0 && !row.protectHit).sort((a, b) => b.profit - a.profit).slice(0, 4),
    (row) => row.summary || `主押命中并贡献 ${money(row.profit)}。`,
  );
  pushRows(
    '停牌校验',
    'warn',
    rows.filter((row) => row.stopped).slice(0, 3),
    (row) => row.summary || `停牌场次实际为 ${row.resultLabel || '-'}，用于校验停牌阈值。`,
  );
  return focus.slice(0, 10);
}

function Card({ title, children, icon, className = '' }: { title: string; children: React.ReactNode; icon?: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`.trim()}><h2>{icon}{title}</h2>{children}</section>;
}

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'good' | 'warn' | 'bad' | 'neutral' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function statusTone(status?: string): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'ok' || status === 'active' || status === 'served_by_api') return 'good';
  if (status === 'failed' || status === 'missing' || status === 'bad' || status === 'missing_build' || status === 'api_missing') return 'bad';
  if (status === 'partial' || status === 'stale' || status === 'warn' || status === 'draft_replacement') return 'warn';
  return 'neutral';
}

function opsStatusLabel(status?: string) {
  if (!status) return '未运行';
  if (status === 'ok') return '正常';
  if (status === 'active') return '生效';
  if (status === 'dry_run') return '试运行完成';
  if (status === 'running') return '运行中';
  if (status === 'planned') return '计划中';
  if (status === 'partial') return '部分数据';
  if (status === 'stale') return '过期';
  if (status === 'failed') return '失败';
  if (status === 'missing') return '缺失';
  return status;
}

function minutesLabel(value?: number) {
  if (value === undefined) return '缺';
  if (value < 1) return '<1m';
  if (value < 60) return `${Math.round(value)}m`;
  return `${(value / 60).toFixed(1)}h`;
}

function secondsLabel(value?: number) {
  if (value === undefined) return '-';
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${(value / 60).toFixed(1)}m`;
}

function healthProbeLabel(probe?: { ok: boolean; status: number; url?: string; latencyMs?: number; error?: string }) {
  if (!probe) return '未检查';
  if (!probe.ok) return probe.status ? `异常 · HTTP ${probe.status}` : '异常';
  return `正常 · ${probe.latencyMs ?? '-'}ms`;
}

function processLabel(status?: string) {
  if (!status) return '未记录';
  if (status === 'running') return '运行中';
  if (status === 'missing') return '未运行';
  if (status === 'served_by_api') return '由 API 托管';
  if (status === 'missing_build') return '缺少构建';
  if (status === 'api_missing') return 'API 未运行';
  return status;
}

function accessModeLabel(mode?: string, configured?: boolean) {
  if (mode === 'local_only') return '仅本机监听';
  if (mode === 'runtime_status_missing') return '未生成运行快照';
  if (mode === 'direct_bind_non_loopback') return '存在非本机监听';
  if (mode === 'tailnet_metadata_recorded') return '记录了 Tailnet 访问元数据';
  if (mode === 'public_funnel_configured') return '记录了 Funnel 访问元数据';
  return configured ? '已记录外部访问元数据' : '未记录外部访问';
}

function DeferredPage({ title, loading, error }: { title: string; loading?: DeferredPageState; error?: string }) {
  return <div className="grid page-grid">
    <Card title={title}>
      <div className="empty-state">
        <b>{error ? '加载失败' : loading ? '正在加载' : '尚未加载'}</b>
        <span>{error || loading?.message || '进入页面后按需读取真实数据。'}</span>
      </div>
    </Card>
  </div>;
}

function spChangeLabel(value?: string) {
  const text = value?.trim();
  if (!text || text === '缺' || text === 'api' || text === 'open') return '样本不足';
  if (text.includes('complete_sp') || text.includes('missing_complete_sp')) return '样本不足';
  return text;
}

function probabilityEdgeLabel(edge: IssueMatchRow['modelProb']) {
  return `胜 ${signedPp(edge.win)} · 平 ${signedPp(edge.draw)} · 负 ${signedPp(edge.loss)}`;
}

function isMatchCompleted(match: { status?: string; scoreStatus?: string; scoreStatusText?: string }): boolean {
  const statusText = match.scoreStatusText || '';
  if (statusText.includes('中场') || statusText.includes('半场') || ['上', '中', '下', '加', '点'].includes(statusText)) {
    return false;
  }
  return match.status === 'settled' || match.scoreStatus === 'finished' || statusText.includes('完场');
}

function predictionTone(match: IssueMatchRow): 'good' | 'warn' | 'bad' | 'neutral' {
  const completed = isMatchCompleted(match);
  if (!completed) return 'neutral';
  if (match.postmatchReviewOutcome) return reviewTone(match.postmatchReviewOutcome);
  if (match.predictionHit === true) return 'good';
  if (match.predictionHit === false) return 'bad';
  return 'warn';
}

function predictionLabel(match: IssueMatchRow): string {
  const completed = isMatchCompleted(match);
  if (!completed) return match.scoreStatus === 'live' || match.scoreStatusText?.includes('中场') ? '进行中' : '待验证';
  if (match.postmatchReviewOutcome) return match.postmatchReviewOutcome;
  if (match.predictionHit === true) return '命中';
  if (match.predictionHit === false) return '未中';
  return '待验证';
}

function reviewTone(label?: string): 'good' | 'warn' | 'bad' | 'neutral' {
  if (!label) return 'neutral';
  if (label.includes('未中') || label.includes('停错')) return 'bad';
  if (label.includes('押中') || label.includes('保中') || label.includes('覆盖中') || label.includes('停正确')) return 'good';
  return 'warn';
}

function matchScoreLabel(match: IssueMatchRow): string {
  if (match.score) return match.score;
  if (match.scoreStatus === 'live') return '进行中';
  if (match.scoreStatus === 'finished') return '完场';
  return '未完赛';
}

function scoreCellParts(match: IssueMatchRow): { half: string; full: string } {
  const statusText = match.scoreStatusText || '';
  const score = match.score || '';
  if (isMatchCompleted(match)) {
    return { half: match.halftimeScore || '-', full: matchScoreLabel(match) };
  }
  if (match.scoreStatus === 'live' || ['上', '中', '下', '加', '点'].includes(statusText) || statusText.includes('中场') || statusText.includes('半场') || statusText.includes("'")) {
    if (statusText === '上' || statusText.includes("'")) {
      return { half: score || '进行中', full: '-' };
    }
    if (statusText === '中' || statusText.includes('中场') || statusText.includes('半场')) {
      return { half: match.halftimeScore || score || '进行中', full: '-' };
    }
    return { half: match.halftimeScore || '-', full: score || '-' };
  }
  return { half: match.halftimeScore || '-', full: '-' };
}

function matchStatusLabel(match: IssueMatchRow): string {
  if (match.scoreStatusText) return match.scoreStatusText;
  if (match.status === 'settled') return '已结算';
  if (match.scoreStatus === 'scheduled') return '未开';
  if (match.scoreStatus === 'closed') return '已截止';
  return match.resultLabel || '-';
}

function splitOutcomeLabel(label: string): string[] {
  if (label === '全包') return ['胜', '平', '负'];
  if (!label || label === '不买' || label === '待预测' || label === '观察') return [];
  return label.split('+').map((value) => value.trim()).filter(Boolean);
}

function betParts(match: IssueMatchRow): { primary: string; protection: string[]; stopped: boolean } {
  const fallbackOutcomes = splitOutcomeLabel(match.recommendedOutcome);
  const primary = match.primaryBetOutcome || fallbackOutcomes[0] || match.recommendedOutcome || '待预测';
  const protection = match.protectionOutcomes?.length ? match.protectionOutcomes : fallbackOutcomes.slice(1);
  if (match.stopFlag || match.recommendedCoverage === 'no-buy' || primary === '不买' || primary === '待预测' || primary === '观察' || primary === '停') {
    return { primary: '-', protection: [], stopped: true };
  }
  return { primary, protection, stopped: Boolean(match.stopFlag) };
}

function actualOutcomeLabel(match: IssueMatchRow): string | undefined {
  if (!isMatchCompleted(match)) return undefined;
  if (match.resultCode === '3') return '胜';
  if (match.resultCode === '1') return '平';
  if (match.resultCode === '0') return '负';
  if (['胜', '平', '负'].includes(match.resultLabel || '')) {
    return match.resultLabel;
  }
  return undefined;
}

function betOutcomeClass(match: IssueMatchRow, outcome: string): string {
  return `bet-outcome ${actualOutcomeLabel(match) === outcome ? 'hit' : ''}`.trim();
}

function settlementSpLabel(match: IssueMatchRow): string {
  const outcome = actualOutcomeLabel(match);
  if (!outcome || match.settlementSp === undefined || match.settlementSp === null) return '-';
  return `${outcome} ${match.settlementSp}`;
}

function probabilityTriplet(match: IssueMatchRow) {
  return [
    { key: 'win', value: match.modelProb.win },
    { key: 'draw', value: match.modelProb.draw },
    { key: 'loss', value: match.modelProb.loss },
  ];
}

function probabilityTripletText(value?: number) {
  return value === undefined ? '缺' : `${Math.round(value * 100)}%`;
}

function artifactStatusTone(status?: string): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'available') return 'good';
  if (status === 'missing' || status === 'incomplete') return 'warn';
  if (status === 'unsupported') return 'bad';
  return 'neutral';
}

function artifactStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    available: '已生成',
    missing: '缺少',
    incomplete: '不完整',
    unsupported: '不支持',
  };
  return labels[String(status || '')] || (status || '未知');
}

function artifactMissingText(status?: DecisionArtifactStatusData) {
  const missing = status?.completeness?.missingMatchIdx ?? [];
  if (!missing.length) return '';
  const shown = missing.slice(0, 12).map((idx) => `#${idx}`).join('、');
  return missing.length > 12 ? `${shown} 等 ${missing.length} 场` : shown;
}

function isFormalArtifactBlocking(status: DecisionArtifactStatusData | undefined, selectedVariantId: string) {
  if (!status) return false;
  const selected = selectedVariantId || status.variantId;
  return selected === ACTIVE_DECISION_VARIANT_ID && status.status !== 'available';
}

function pickLabel(value?: string) {
  if (value === '3') return '胜';
  if (value === '1') return '平';
  if (value === '0') return '负';
  return value || '-';
}

function pickListLabel(values?: string[]) {
  const mapped = (values ?? []).map(pickLabel).filter((value) => value && value !== '-');
  return mapped.length ? mapped.join('+') : '-';
}

function decisionVariantForMatch(match: IssueMatchRow, selectedVariantId: string) {
  const variants = match.decisionVariants ?? [];
  const selectedVariant = match.selectedDecisionVariant;
  return variants.find((variant) => variant.variantId === selectedVariantId)
    ?? (selectedVariant?.variantId === selectedVariantId ? selectedVariant : undefined)
    ?? variants.find((variant) => variant.isDefault)
    ?? selectedVariant
    ?? variants[0];
}

function labelsFromCodes(values?: string[]) {
  return (values ?? []).map(pickLabel).filter((value) => value && value !== '-');
}

function isPickCode(value?: string): value is PickCode {
  return value === '3' || value === '1' || value === '0';
}

function normalisedPickCodes(values?: string[]): PickCode[] {
  return (values ?? [])
    .map((value) => value.trim())
    .filter(isPickCode);
}

function codesFromJoined(value?: string) {
  return normalisedPickCodes(value?.split(/[+/,，\s]+/));
}

function isExecutionSkip(variant?: DecisionVariantData) {
  return Boolean(variant?.executionAction?.startsWith('skip_'));
}

function isExecutionStopped(variant?: DecisionVariantData) {
  if (!variant) return false;
  return Boolean(
    variant.stopFlag
      || variant.selectionType === 'no-buy'
      || isExecutionSkip(variant)
      || normalisedPickCodes(variant.selectionCodes).length === 0,
  );
}

function executableSelectionCodes(variant?: DecisionVariantData) {
  if (!variant || isExecutionStopped(variant)) return [];
  return normalisedPickCodes(variant.selectionCodes);
}

function executablePrimaryCode(variant?: DecisionVariantData) {
  const codes = executableSelectionCodes(variant);
  if (!codes.length) return undefined;
  const primary = variant?.primaryPick?.trim();
  return isPickCode(primary) && codes.includes(primary) ? primary : codes[0];
}

function executableProtectCodes(variant?: DecisionVariantData) {
  const codes = executableSelectionCodes(variant);
  const primary = executablePrimaryCode(variant);
  const explicitProtect = normalisedPickCodes(variant?.protectPicks).filter((code) => code !== primary && codes.includes(code));
  if (explicitProtect.length) return explicitProtect;
  return codes.filter((code) => code !== primary);
}

function executionRecommendedCodes(variant?: DecisionVariantData) {
  return codesFromJoined(variant?.executionRecommendedCodes);
}

function executionAuditDiffers(variant?: DecisionVariantData) {
  if (!variant) return false;
  const recommended = executionRecommendedCodes(variant);
  if (!recommended.length) return false;
  const executable = executableSelectionCodes(variant);
  return recommended.join('+') !== executable.join('+');
}

function executionActionLabel(action?: string) {
  const labels: Record<string, string> = {
    execute_single: '单选执行',
    execute_double: '双选执行',
    execute_full_cover: '全包执行',
    downgrade_full_to_double: '降全为双',
    downgrade_full_to_double_layer_conflict: '冲突降双',
    downgrade_full_to_double_over_cap: '超额降双',
    skip_wait_late_refresh: '等待晚盘',
    skip_stop: '停',
    skip_full_over_cap: '全包超额停',
    skip_no_recommendation: '无建议停',
    skip_missing_decision: '缺决策停',
    skip_missing_execution_sp: '缺执行SP',
  };
  return action ? labels[action] || action : '未记录';
}

function codeNumberTripletLabel(values?: Record<string, number>) {
  if (!values) return '-';
  const win = values['3'];
  const draw = values['1'];
  const loss = values['0'];
  const fmt = (value?: number) => value !== undefined && Number.isFinite(value) ? value.toFixed(2) : '缺';
  return `${fmt(win)} / ${fmt(draw)} / ${fmt(loss)}`;
}

function hasCodeNumbers(values?: Record<string, number>) {
  return Boolean(values && ['3', '1', '0'].some((code) => values[code] !== undefined && Number.isFinite(values[code])));
}

function executionUnlockLabel(state?: string) {
  const labels: Record<string, string> = {
    waiting_late_refresh: '等待晚盘',
    unlocked_after_late_refresh: '晚盘解锁',
    blocked_after_late_refresh: '晚盘仍停',
    not_applicable: '常规',
  };
  return state ? labels[state] || state : '常规';
}

function executionUnlockTone(state?: string): 'good' | 'warn' | 'bad' | 'neutral' {
  if (state === 'unlocked_after_late_refresh') return 'good';
  if (state === 'waiting_late_refresh' || state === 'blocked_after_late_refresh') return 'bad';
  return 'neutral';
}

function executionBoolLabel(value?: boolean | null) {
  if (value === true) return '是';
  if (value === false) return '否';
  return '-';
}

function executionCodesLabel(codes: string[]) {
  const labels = labelsFromCodes(codes);
  return labels.length ? labels.join('+') : '停';
}

function hasDecisionHitValue(value?: boolean | null) {
  return value === true || value === false;
}

function computedVariantHits(match: { resultCode?: string; status?: string; scoreStatus?: string; scoreStatusText?: string }, variant: ReturnType<typeof decisionVariantForMatch>) {
  if (!variant || !isMatchCompleted(match) || !match.resultCode) {
    return { primaryHit: undefined, coverageHit: undefined, predictionHit: undefined };
  }
  const selectedCodes = executableSelectionCodes(variant);
  if (!selectedCodes.length || !isPickCode(match.resultCode)) {
    return { primaryHit: undefined, coverageHit: undefined, predictionHit: undefined };
  }
  const primaryCode = executablePrimaryCode(variant) || selectedCodes[0];
  const coverageHit = selectedCodes.includes(match.resultCode);
  return {
    primaryHit: primaryCode ? primaryCode === match.resultCode : undefined,
    coverageHit,
    predictionHit: coverageHit,
  };
}

function variantOutcomeLabel(match: IssueMatchRow, variant: ReturnType<typeof decisionVariantForMatch>, selectedLabels: string[], protectLabels: string[]): string | undefined {
  if (!variant) return undefined;
  const completed = isMatchCompleted(match);
  if (!completed) return undefined;
  if (isExecutionStopped(variant) || selectedLabels.length === 0) return '停';
  const computedHits = computedVariantHits(match, variant);
  const primaryHit = variant.primaryHit ?? computedHits.primaryHit;
  const coverageHit = variant.coverageHit ?? variant.predictionHit ?? computedHits.coverageHit;
  const hasCoverageHit = hasDecisionHitValue(coverageHit);
  const hasPredictionHit = hasDecisionHitValue(variant.predictionHit ?? computedHits.predictionHit);
  const hasPrimaryHit = hasDecisionHitValue(primaryHit);
  if (!hasCoverageHit && !hasPredictionHit && !hasPrimaryHit) return undefined;
  if (primaryHit === true) return '押中';
  if (coverageHit === true) {
    const actual = actualOutcomeLabel(match);
    return actual && protectLabels.includes(actual) ? '保中' : '命中';
  }
  if (coverageHit === false) return '未中';
  if (primaryHit === false) return '主押未中';
  return undefined;
}

function applyDecisionVariant(match: IssueMatchRow, selectedVariantId: string): IssueMatchRow {
  const variant = decisionVariantForMatch(match, selectedVariantId);
  if (!variant) return match;
  const stopped = isExecutionStopped(variant);
  const executableCodes = executableSelectionCodes(variant);
  const selectedLabels = labelsFromCodes(executableCodes);
  const protectLabels = labelsFromCodes(executableProtectCodes(variant));
  const primaryCode = executablePrimaryCode(variant);
  const primaryLabel = primaryCode ? pickLabel(primaryCode) : undefined;
  const isActiveVariant = isActiveDecisionVariant(variant);
  const computedHits = computedVariantHits(match, variant);
  const predictionHit = variant.coverageHit ?? variant.predictionHit ?? computedHits.predictionHit ?? (isActiveVariant ? match.predictionHit : undefined);
  const postmatchReviewOutcome = variantOutcomeLabel(match, variant, selectedLabels, protectLabels) ?? (isActiveVariant ? match.postmatchReviewOutcome : undefined);
  return {
    ...match,
    qScore: variant.qScore ?? match.qScore,
    confidence: variant.probability ?? match.confidence,
    recommendedOutcome: stopped ? '不买' : selectedLabels.length ? selectedLabels.join('+') : variant.recommendation || match.recommendedOutcome,
    primaryBetOutcome: stopped ? undefined : primaryLabel,
    protectionOutcomes: protectLabels,
    recommendedCoverage: stopped ? 'no-buy' : variant.selectionType,
    stopFlag: stopped,
    recommendationSource: decisionVersionLabel(variant) || match.recommendationSource,
    recommendationConfidenceLabel: variant.confidenceLabel || match.recommendationConfidenceLabel,
    predictionHit,
    postmatchReviewOutcome,
  };
}

function shortHash(value?: string) {
  return value ? value.slice(0, 8) : '-';
}

function issueRiskTags(match: IssueMatchRow): Array<{ label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> {
  const tags = match.postmatchReviewTags ?? [];
  const out: Array<{ label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = [];
  const add = (label: string, tone: 'good' | 'warn' | 'bad' | 'neutral') => {
    if (!out.some((item) => item.label === label)) out.push({ label, tone });
  };
  if (match.draftDecisionSnapshotId) add('待确认', 'warn');
  if (match.lineGap !== undefined && Math.abs(match.lineGap) >= 0.5) add('让球偏移', 'warn');
  if (tags.includes('missed_draw') || tags.includes('line_gap_warning_ignored') || (match.lineGap !== undefined && Math.abs(match.lineGap) >= 0.5)) add('平局边界', 'warn');
  if ([match.sp.win, match.sp.draw, match.sp.loss].some((value) => value !== undefined && value >= 3.5)) add('高SP', 'neutral');
  if (tags.includes('protection_saved') || match.postmatchReviewOutcome === '保中') add('保护救票', 'good');
  if (tags.includes('uncovered_result') || tags.includes('uncovered_high_prob_alt') || match.postmatchReviewOutcome === '未中') add('未覆盖', 'bad');
  if (isMatchCompleted(match) && !match.postmatchReviewOutcome) add('待复盘', 'warn');
  return out.slice(0, 4);
}

function IssueDashboard({
  data,
  availableIssues,
  selectedIssue,
  selectedDecisionVariant,
  onIssueChange,
  onDecisionVariantChange,
  onOpenMatch,
}: {
  data: DashboardData['issue'];
  availableIssues: DashboardData['availableIssues'];
  selectedIssue: string;
  selectedDecisionVariant: string;
  onIssueChange: (issueId: string) => void;
  onDecisionVariantChange: (variantId: string) => void;
  onOpenMatch: (matchId: string) => void;
}) {
  const rawDecisionOptions = data.strategyVersionContext?.options?.length ? data.strategyVersionContext.options : data.decisionVariantOptions ?? [];
  const decisionOptions = displayableDecisionVariants(rawDecisionOptions);
  const selectedDecisionOption = decisionOptions.find((option) => option.variantId === selectedDecisionVariant)
    ?? decisionOptions.find((option) => option.isDefault)
    ?? decisionOptions[0];
  const displayedMatches = useMemo(
    () => data.matches.map((match) => applyDecisionVariant(match, selectedDecisionVariant)),
    [data.matches, selectedDecisionVariant],
  );
  const grouped = useMemo(() => {
    const byDate = new Map<string, IssueMatchRow[]>();
    for (const match of displayedMatches) {
      const date = match.kickoffDate || data.issueDate || '未分组';
      byDate.set(date, [...(byDate.get(date) ?? []), match]);
    }
    return [...byDate.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, matches]) => ({
        date,
        matches: matches.sort((a, b) => `${a.kickoffTime}-${a.matchId}`.localeCompare(`${b.kickoffTime}-${b.matchId}`)),
      }));
  }, [data.issueDate, displayedMatches]);
  const settledMatches = displayedMatches.filter((match) => match.status === 'settled');
  const evaluatedMatches = settledMatches.filter((match) => match.predictionHit !== undefined && match.predictionHit !== null);
  const hitCount = evaluatedMatches.filter((match) => match.predictionHit).length;
  const defaultExpandedDates = useMemo(() => grouped.filter((group) => isCurrentOrFutureDate(group.date)).map((group) => group.date), [grouped]);
  const defaultExpandedDateKey = defaultExpandedDates.join('|');
  const [expandedDates, setExpandedDates] = useState<Set<string>>(() => new Set(defaultExpandedDates));
  useEffect(() => {
    setExpandedDates(new Set(defaultExpandedDates));
  }, [data.issueId, defaultExpandedDateKey]);
  const toggleDate = (date: string) => {
    setExpandedDates((previous) => {
      const next = new Set(previous);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };
  return <div className="grid page-grid">
    <Card title={`第 ${data.issueId} 期`} icon={<BarChart3 />}>
      <div className="issue-toolbar">
	        <label>
	          <span>期号</span>
	          <select value={selectedIssue} onChange={(event) => onIssueChange(event.target.value)} aria-label="选择期号">
	            {availableIssues.map((issue) => <option key={issue.issueId} value={issue.issueId}>{issue.label}</option>)}
	          </select>
	        </label>
        {decisionOptions.length > 0 && <label>
          <span>决策版本</span>
          <select value={selectedDecisionVariant || selectedDecisionOption?.variantId || ''} onChange={(event) => onDecisionVariantChange(event.target.value)} aria-label="选择决策版本" disabled={decisionOptions.length <= 1}>
            {decisionOptions.map((option) => <option key={option.variantId} value={option.variantId}>{decisionVersionLabel(option)}</option>)}
          </select>
        </label>}
	        <div className="issue-source"><Badge tone={data.settlementStatus === 'settled' ? 'good' : 'warn'}>{data.settlementStatus}</Badge><span>{data.lastScrapedAt || data.issueDate}</span></div>
      </div>
      <div className="hero-stats">
        <div><span>截止</span><b>{data.salesDeadline}</b></div>
        <div><span>数据完整</span><b>{pct(data.dataCompleteRate)}</b></div>
        <div><span>候选</span><b>{data.qualifiedCandidateCount}/{data.matchCount}</b></div>
        <div><span>预测命中</span><b>{evaluatedMatches.length ? `${hitCount}/${evaluatedMatches.length}` : '待统计'}</b></div>
      </div>
		    </Card>

    <Card title="比赛列表">
      <div className="issue-board">
        {grouped.map((group) => {
          const isExpanded = expandedDates.has(group.date);
          const settledInGroup = group.matches.filter(isMatchCompleted).length;
          return <section key={group.date} className={isExpanded ? 'match-day' : 'match-day collapsed'}>
          <button type="button" className="match-day-toggle" onClick={() => toggleDate(group.date)} aria-expanded={isExpanded}>
            <b>{group.date}</b>
            <span>{group.matches.length} 场 · {settledInGroup} 已完赛</span>
            <small>{isExpanded ? '收起' : '展开'}</small>
          </button>
          {isExpanded && <div className="table-wrap"><table className="issue-matches-table"><colgroup><col className="issue-col-id" /><col className="issue-col-time" /><col className="issue-col-match" /><col className="issue-col-handicap" /><col className="issue-col-sp" /><col className="issue-col-probability" /><col className="issue-col-pick" /><col className="issue-col-result" /><col className="issue-col-status" /><col className="issue-col-settlement-sp" /></colgroup><thead><tr><th>#</th><th>时间</th><th>比赛</th><th>让球</th><th>SP</th><th>概率</th><th>注<br/><small>押/保</small></th><th>赛果</th><th>预测</th><th>结算SP</th></tr></thead><tbody>
            {group.matches.map((m: IssueMatchRow) => {
              const bet = betParts(m);
              const variant = decisionVariantForMatch(m, selectedDecisionVariant);
              const auditCodes = executionRecommendedCodes(variant);
              const executableCodes = executableSelectionCodes(variant);
              const hasExecutionMeta = Boolean(variant?.executionAction || variant?.executionUnlockState);
              const hasExecutionDiff = executionAuditDiffers(variant);
              const probabilities = probabilityTriplet(m);
              const maxProbability = Math.max(...probabilities.map((item) => item.value ?? -1));
              const scoreParts = scoreCellParts(m);
              return <tr key={m.matchId} onClick={() => onOpenMatch(m.matchId)} className="clickable">
              <td>{m.matchId}</td>
              <td>{m.kickoffTime || '-'}</td>
              <td><b>{m.league}</b><br/>{m.home} vs {m.away}</td>
              <td>{m.handicap}</td>
              <td>{m.sp.win ?? '缺'} / {m.sp.draw ?? '缺'} / {m.sp.loss ?? '缺'}</td>
              <td className="triplet-cell">{probabilities.map((item, index) => <span key={item.key} className={item.value !== undefined && item.value === maxProbability && item.value >= CONFIDENCE_FOCUS_THRESHOLD ? 'focus-value' : undefined}>{index > 0 ? ' / ' : ''}{probabilityTripletText(item.value)}</span>)}</td>
              <td className="recommendation-cell bet-cell">
                <span className={`bet-row ${bet.primary === '-' ? 'muted' : ''}`.trim()}><span className="bet-label">押</span><span className={bet.primary === '-' ? 'bet-outcome muted' : betOutcomeClass(m, bet.primary)}>{bet.primary}</span></span>
                <span className={`bet-row protect ${bet.protection.length ? '' : 'muted'}`.trim()}><span className="bet-label">保</span>
                  {bet.protection.length ? <span className="bet-outcome-list">{bet.protection.map((outcome, index) => <span key={outcome} className="bet-outcome-item">{index > 0 ? <span className="bet-separator">+</span> : null}<span className={betOutcomeClass(m, outcome)}>{outcome}</span></span>)}</span> : <span className="bet-outcome muted">-</span>}
                </span>
                {bet.stopped ? <span className="bet-row stop active"><span className="bet-label">停</span><span className="bet-outcome stop-active">停</span></span> : null}
                {hasExecutionMeta ? <small className={`execution-chip ${executionUnlockTone(variant?.executionUnlockState)}`.trim()}>{executionActionLabel(variant?.executionAction)} · {executionUnlockLabel(variant?.executionUnlockState)}</small> : null}
                {hasExecutionDiff ? <small className="execution-audit-diff">审 {executionCodesLabel(auditCodes)} → 执 {executionCodesLabel(executableCodes)}</small> : null}
                {m.draftDecisionSnapshotId ? <small className="decision-snapshot-note warn">待确认新建议</small> : null}
              </td>
              <td className="score-cell"><span>(半) {scoreParts.half}</span><span>(全) {scoreParts.full}</span><small>{matchStatusLabel(m)}</small></td>
              <td><Badge tone={predictionTone(m)}>{predictionLabel(m)}</Badge>{m.scrapeStatus !== 'ok' ? <small className="data-warning">{statusLabel[m.scrapeStatus]}</small> : null}</td>
              <td><span className={m.settlementSp !== undefined && m.settlementSp !== null ? 'settlement-sp' : undefined}>{settlementSpLabel(m)}</span></td>
            </tr>;
            })}
          </tbody></table></div>}
        </section>;
        })}
      </div>
    </Card>
  </div>;
}

function MatchDetail({
  data,
  selectedDecisionVariant,
  onDecisionVariantChange,
  confirmDraftState,
  onConfirmDraft,
}: {
  data: DashboardData['matchDetail'];
  selectedDecisionVariant: string;
  onDecisionVariantChange: (variantId: string) => void;
  confirmDraftState?: ConfirmDraftState;
  onConfirmDraft: (matchId: string) => Promise<void>;
}) {
  const rawDecisionOptions = data.strategyVersionContext?.options?.length ? data.strategyVersionContext.options : data.decisionVariantOptions ?? [];
  const decisionOptions = displayableDecisionVariants(rawDecisionOptions);
  const selectedVariant = (data.decisionVariants ?? []).find((variant) => variant.variantId === selectedDecisionVariant)
    ?? (data.decisionVariants ?? []).find((variant) => variant.isDefault)
    ?? (data.decisionVariants ?? [])[0];
  const selectedDecisionOption = selectedVariant
    ?? decisionOptions.find((option) => option.variantId === selectedDecisionVariant)
    ?? decisionOptions.find((option) => option.isDefault)
    ?? decisionOptions[0];
  const selectedVariantStopped = isExecutionStopped(selectedVariant);
  const selectedVariantExecutableCodes = executableSelectionCodes(selectedVariant);
  const selectedVariantAuditCodes = executionRecommendedCodes(selectedVariant);
  const selectedVariantLabels = selectedVariant ? labelsFromCodes(selectedVariantExecutableCodes) : [];
  const selectedVariantProtectLabels = selectedVariant ? labelsFromCodes(executableProtectCodes(selectedVariant)) : [];
  const selectedVariantAuditLabels = labelsFromCodes(selectedVariantAuditCodes);
  const selectedVariantExecutionDiffers = executionAuditDiffers(selectedVariant);
  const selectedVariantPrimaryCode = executablePrimaryCode(selectedVariant);
  const llmReady = Boolean(selectedVariant) || (data.llm.source !== 'none' && data.llm.source !== 'api' && data.llm.direction !== '待决策');
  const modelPick = data.selectedOutcomes.length ? data.selectedOutcomes.join('+') : '不买';
  const llmDecision = selectedVariant ? (selectedVariantStopped ? '停' : selectedVariantLabels.join('+') || selectedVariant.recommendation) : llmReady ? data.llm.direction : '待决策';
  const latestOdds = data.oddsTimeline[data.oddsTimeline.length - 1];
  const modelRole = data.recommendedCoverage === 'no-buy' ? '不买' : data.qScore >= 2 ? '核心' : data.qScore >= 1.2 ? '保护' : '观察';
  const analysis500 = data.analysis500;
  const intelligence = data.intelligence;
  const intelligencePoints = (intelligence?.points ?? []).filter((point) => !/^赛事(阶段)?：/.test(point));
	  const intelligenceTags = (intelligence?.tags ?? []).filter((tag) => !['knockout', 'league_round', 'group'].includes(tag));
	  const llmChain = data.llmDecisionChain ?? [];
	  const activeDecisionVersionSelected = !selectedVariant || isActiveDecisionVariant(selectedVariant);
	  const shadowDecisionVersionSelected = isShadowDecisionVariant(selectedVariant);
	  const visibleLlmSupport = activeDecisionVersionSelected ? data.llm.support : [];
	  const visibleLlmRisks = activeDecisionVersionSelected ? data.llm.risks : selectedVariant?.notes ?? [];
	  const visibleLlmChain = activeDecisionVersionSelected ? llmChain : [];
	  const shadowDecisionCategories = shadowDecisionVersionSelected ? selectedVariant?.decisionCategories ?? [] : [];
	  const shadowDecisionChain = shadowDecisionVersionSelected ? selectedVariant?.decisionChain ?? [] : [];
	  const decisionSnapshot = data.decisionSnapshot;
	  const draftDecisionSnapshot = data.draftDecisionSnapshot;
	  const postmatchReview = data.postmatchReview;
	  const matchCompleted = isMatchCompleted(data);
	  const selectedVariantHits = computedVariantHits(data, selectedVariant);
	  const selectedDecisionHit = matchCompleted && !selectedVariantStopped ? selectedVariant?.coverageHit ?? selectedVariant?.predictionHit ?? selectedVariantHits.predictionHit ?? data.predictionHit : undefined;
  const lineGapValue = data.lineGap;
  const lineGapLabel = lineGapValue === undefined ? '缺' : `${lineGapValue > 0 ? '+' : ''}${lineGapValue}`;
  const lineGapValueClass = lineGapValue !== undefined && Math.abs(lineGapValue) >= 0.75 ? 'bad-value' : lineGapValue !== undefined && Math.abs(lineGapValue) >= 0.5 ? 'warn-value' : undefined;
  const spChange = spChangeLabel(latestOdds?.drift);
  const consensus = data.oddsConsensus ?? analysis500?.oddsConsensus;
  const consensusDriftLabel = consensus
    ? `主胜 ${signedPct(consensus.drift.home)} · 平 ${signedPct(consensus.drift.draw)} · 客胜 ${signedPct(consensus.drift.away)}`
    : '';
  const outcomeRows = [
    { label: '胜', probability: data.probability.win, market: data.impliedProbability.win, sp: data.sp.win },
    { label: '平', probability: data.probability.draw, market: data.impliedProbability.draw, sp: data.sp.draw },
    { label: '负', probability: data.probability.loss, market: data.impliedProbability.loss, sp: data.sp.loss },
  ].map((row) => ({
    ...row,
    q: row.probability !== undefined && row.sp !== undefined ? row.probability * row.sp : undefined,
    modelSelected: data.selectedOutcomes.includes(row.label),
  }));
  const topProbabilityOutcome = [...outcomeRows].sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))[0];
  const topQOutcome = [...outcomeRows].sort((a, b) => (b.q ?? -1) - (a.q ?? -1))[0];
  const llmProtectionFromData = data.llmProtectionOutcomes ?? [];
  const llmStopped = selectedVariant ? selectedVariantStopped : Boolean(data.llmStopped) || data.recommendedCoverage === 'no-buy' || llmDecision.includes('停');
  const primaryOutcome = selectedVariant
    ? (selectedVariantStopped ? '-' : selectedVariantPrimaryCode ? pickLabel(selectedVariantPrimaryCode) : selectedVariantLabels[0] || modelPick)
    : data.llmPrimaryOutcome || (['胜', '平', '负'].includes(llmDecision) ? llmDecision : modelPick);
  const protectionOutcomes = selectedVariant
    ? selectedVariantStopped ? [] : selectedVariantProtectLabels
    : llmProtectionFromData.length
        ? llmProtectionFromData
        : topQOutcome?.label && topQOutcome.label !== primaryOutcome
          ? [topQOutcome.label]
          : [];
  const drawRow = outcomeRows.find((row) => row.label === '平');
  const highSpLowProb = outcomeRows.filter((row) => (row.sp ?? 0) >= 3.5 && (row.probability ?? 1) <= 0.35);
	  const strongCounterEvidence = visibleLlmRisks[0] || (lineGapValue !== undefined && Math.abs(lineGapValue) >= 0.5 ? '让球偏移需要复核' : '无明显强反证');
  const focusCards = [
    {
      label: '让球偏移',
      value: lineGapLabel,
      detail: data.asia.line !== undefined ? `亚盘 ${data.asia.line}` : '亚盘缺',
      tone: lineGapValue !== undefined && Math.abs(lineGapValue) >= 0.5 ? 'warn' : 'good',
    },
    {
      label: '平局边界',
      value: `${pct(drawRow?.probability)} / q ${drawRow?.q?.toFixed(2) ?? '缺'}`,
      detail: (drawRow?.probability ?? 0) >= 0.3 || (drawRow?.q ?? 0) >= 1.2 ? '平局需要纳入保护视野' : '平局压力一般',
      tone: (drawRow?.probability ?? 0) >= 0.3 || (drawRow?.q ?? 0) >= 1.2 ? 'warn' : 'neutral',
    },
    ...(activeDecisionVersionSelected ? [{
	      label: '强反证',
	      value: strongCounterEvidence,
	      detail: visibleLlmRisks.length ? '来自当前决策版本' : '未发现明确反面信号',
	      tone: visibleLlmRisks.length ? 'warn' : 'good',
    }] : []),
    {
      label: '高SP/低胜率',
      value: highSpLowProb.length ? highSpLowProb.map((row) => `${row.label} ${row.sp}`).join(' / ') : '无',
      detail: highSpLowProb.length ? '高赔结果只作为保护或尾部机会' : '没有突出的高赔低胜率陷阱',
      tone: highSpLowProb.length ? 'warn' : 'good',
    },
  ] as const;
  const analysisRows = analysis500 && analysis500.status === 'ok' ? [
    { label: '主队近况', team: analysis500.homeRecent.team || data.home, summary: analysis500.homeRecent.summary },
    { label: '客队近况', team: analysis500.awayRecent.team || data.away, summary: analysis500.awayRecent.summary },
    { label: '交锋', team: `${data.home} vs ${data.away}`, summary: analysis500.h2h.summary },
  ].filter((item) => item.summary && item.summary.trim()) : [];
  const decisionIntelPoints = [
    ...intelligencePoints,
    ...analysisRows.map((item) => `${item.label}：${item.summary}`),
    ...data.marketHighlights,
  ].filter(Boolean).slice(0, 5);
  const probabilityLine = `胜 ${pct(data.probability.win)} · 平 ${pct(data.probability.draw)} · 负 ${pct(data.probability.loss)}`;
  const evLine = topQOutcome ? `${topQOutcome.label} q ${topQOutcome.q?.toFixed(2) ?? '缺'}，模型EV ${modelPick}` : `模型EV ${modelPick}`;
  const protectionReason = protectionOutcomes.length
    ? selectedVariantExecutionDiffers
      ? `审计建议 ${selectedVariantAuditLabels.join('+')}，执行层按 ${selectedVariantLabels.join('+')} 出票`
      : `q/EV 倾向与主押存在差异，保护 ${protectionOutcomes.join('+')}`
    : '未触发额外保护';
	  const stopReason = llmStopped
	    ? selectedVariant?.executionReasons?.[0] || (selectedVariant?.executionAction ? executionActionLabel(selectedVariant.executionAction) : visibleLlmRisks[0]) || '最大 q 偏低或综合反证过多，停牌'
	    : data.qScore < 1.1
      ? '接近停牌线，降低优先级'
      : '未触发停牌';
  const activeSnapshot = decisionSnapshot;
  const draftSnapshot = draftDecisionSnapshot;
  const currentConfirmState = confirmDraftState?.matchId === data.matchId ? confirmDraftState : undefined;
  const confirmingDraft = currentConfirmState?.status === 'submitting';
  const snapshotDiffs = activeSnapshot && draftSnapshot ? {
    primary: (activeSnapshot.primaryPick || '') !== (draftSnapshot.primaryPick || ''),
    protect: pickListLabel(activeSnapshot.protectPicks) !== pickListLabel(draftSnapshot.protectPicks),
    stop: Boolean(activeSnapshot.stopFlag) !== Boolean(draftSnapshot.stopFlag),
    version: (activeSnapshot.decisionChainVersion || activeSnapshot.modelVersion || '') !== (draftSnapshot.decisionChainVersion || draftSnapshot.modelVersion || '')
      || (activeSnapshot.decisionConfigHash || '') !== (draftSnapshot.decisionConfigHash || ''),
  } : undefined;
  const snapshotDiffBadges = snapshotDiffs ? [
    snapshotDiffs.primary ? '主押变化' : '',
    snapshotDiffs.protect ? '保护变化' : '',
    snapshotDiffs.stop ? '停/买变化' : '',
    snapshotDiffs.version ? '版本变化' : '',
  ].filter(Boolean) : [];
  const renderSnapshotColumn = (snapshot: NonNullable<typeof activeSnapshot>, role: 'active' | 'draft') => {
    const isDraft = role === 'draft';
    const base = activeSnapshot;
    const primaryChanged = isDraft && base ? (base.primaryPick || '') !== (snapshot.primaryPick || '') : false;
    const protectChanged = isDraft && base ? pickListLabel(base.protectPicks) !== pickListLabel(snapshot.protectPicks) : false;
    const stopChanged = isDraft && base ? Boolean(base.stopFlag) !== Boolean(snapshot.stopFlag) : false;
    const versionChanged = isDraft && base
      ? (base.decisionChainVersion || base.modelVersion || '') !== (snapshot.decisionChainVersion || snapshot.modelVersion || '')
        || (base.decisionConfigHash || '') !== (snapshot.decisionConfigHash || '')
      : false;
    return <div className={`snapshot-column ${role}`}>
      <div className="snapshot-column-head">
        <span>{role === 'active' ? 'Active' : 'Draft'}</span>
        <Badge tone={role === 'active' ? 'good' : 'warn'}>{snapshot.status || role}</Badge>
      </div>
      <div className="snapshot-field"><span>方向</span><b>{snapshot.recommendation || '-'}</b></div>
      <div className={primaryChanged ? 'snapshot-field changed' : 'snapshot-field'}><span>押</span><b>{pickLabel(snapshot.primaryPick)}</b></div>
      <div className={protectChanged ? 'snapshot-field changed' : 'snapshot-field'}><span>保</span><b>{pickListLabel(snapshot.protectPicks)}</b></div>
      <div className={stopChanged ? 'snapshot-field changed' : 'snapshot-field'}><span>停/买</span><b>{snapshot.stopFlag ? '停' : '买'}</b></div>
      <div className="snapshot-field"><span>置信</span><b>{snapshot.confidenceLabel || pct(snapshot.confidence)}</b></div>
      <div className="snapshot-field"><span>q</span><b>{snapshot.qScore?.toFixed(2) ?? '-'}</b></div>
      <div className={versionChanged ? 'snapshot-field changed' : 'snapshot-field'}><span>版本</span><b>{snapshot.decisionChainVersion || snapshot.modelVersion || '-'}</b></div>
      <div className={versionChanged ? 'snapshot-field changed' : 'snapshot-field'}><span>配置</span><b>{shortHash(snapshot.decisionConfigHash)}</b></div>
      <div className="snapshot-field"><span>生成</span><b>{snapshot.generatedAt || '-'}</b></div>
      <div className="snapshot-field"><span>检查</span><b>{snapshot.checkedAt || '-'}</b></div>
    </div>;
  };
  return <div className="grid page-grid match-detail-page">
    <section className="match-decision-hero">
      <div className="match-summary-block">
        <div className="eyebrow">Issue {data.issueId} · {data.league}</div>
        <h2><CheckCircle2 />{data.home} vs {data.away}</h2>
	        <div className="match-meta-line">
	          <span>让球 {data.handicap}</span>
	          <span>开赛 {data.kickoffTime}</span>
	          <span>{data.scoreStatusText || data.resultStatus}</span>
	          {data.score ? <span>比分 {data.score}</span> : null}
	          {data.halftimeScore ? <span>半场 {data.halftimeScore}</span> : null}
	        </div>
        {decisionOptions.length > 0 && <label className="decision-version-control match-detail-version">
          <span>决策版本</span>
          <select value={selectedDecisionVariant || selectedDecisionOption?.variantId || ''} onChange={(event) => onDecisionVariantChange(event.target.value)} aria-label="选择详情决策版本" disabled={decisionOptions.length <= 1}>
            {decisionOptions.map((option) => <option key={option.variantId} value={option.variantId}>{decisionVersionLabel(option)}</option>)}
          </select>
        </label>}
	        <div className={llmStopped ? 'decision-bet-panel has-stop' : 'decision-bet-panel'}>
	          <div className="decision-bet-row primary"><span>押</span><b>{primaryOutcome}</b></div>
          <div className={protectionOutcomes.length ? 'decision-bet-row protect' : 'decision-bet-row muted'}><span>保</span><b>{protectionOutcomes.length ? protectionOutcomes.join('+') : '-'}</b></div>
          {llmStopped ? <div className="decision-bet-row stop active"><span>停</span><b>停</b></div> : null}
        </div>
        <div className="snapshot-meta">
          <span>概率 {data.qInputProbabilitySnapshotAt || data.probabilityCalibratedAt || '缺'}</span>
          <span>SP {data.qInputSpSnapshotAt || latestOdds?.at || '缺'}</span>
          <span>q {data.qCalculatedAt || '缺'}</span>
        </div>
      </div>
      <div className="outcome-card-grid">
        {outcomeRows.map((row) => {
          const classes = ['outcome-card'];
          if (row.label === primaryOutcome) classes.push('primary');
          if (protectionOutcomes.includes(row.label)) classes.push('protect');
          if (row.label === topQOutcome?.label) classes.push('ev');
          return <div key={row.label} className={classes.join(' ')}>
            <div className="outcome-card-head"><b>{row.label}</b>{row.label === primaryOutcome ? <Badge tone="good">押</Badge> : protectionOutcomes.includes(row.label) ? <Badge tone="warn">保</Badge> : null}</div>
            <div className="outcome-metrics">
              <span>概率</span><strong className={focusValueClass(row.probability, CONFIDENCE_FOCUS_THRESHOLD)}>{pct(row.probability)}</strong>
              <span>SP</span><strong>{row.sp ?? '缺'}</strong>
              <span>q</span><strong className={row.q !== undefined && row.q >= Q_FOCUS_THRESHOLD ? 'focus-value' : undefined}>{row.q?.toFixed(2) ?? '缺'}</strong>
            </div>
            <small>市场概率 {pct(row.market)}</small>
          </div>;
        })}
      </div>
    </section>

    <Card title="决策拆解" className="decision-brief-card">
      <div className="decision-reason-grid">
        <div><span>让球后胜率</span><b>{topProbabilityOutcome?.label ?? '缺'}</b><p>{probabilityLine}</p></div>
        <div><span>q / EV</span><b>{data.qScore.toFixed(2)} · {modelRole}</b><p>{evLine}</p></div>
        <div><span>保护原因</span><b>{protectionOutcomes.length ? protectionOutcomes.join('+') : '无'}</b><p>{protectionReason}</p></div>
        <div><span>停牌原因</span><b>{llmStopped ? '停' : '未停'}</b><p>{stopReason}</p></div>
      </div>
		    </Card>

    {selectedVariant?.executionAction && <Card title="执行层" className="execution-policy-panel">
      <div className="execution-policy-head">
        <Badge tone={isExecutionStopped(selectedVariant) ? 'bad' : 'good'}>{isExecutionStopped(selectedVariant) ? '不可出票' : '可出票'}</Badge>
        <Badge tone={executionUnlockTone(selectedVariant.executionUnlockState)}>{executionUnlockLabel(selectedVariant.executionUnlockState)}</Badge>
        <span>{executionActionLabel(selectedVariant.executionAction)}</span>
      </div>
      <div className="execution-policy-grid">
        <div><span>可执行</span><b>{executionCodesLabel(selectedVariantExecutableCodes)}</b></div>
        <div><span>审计建议</span><b>{selectedVariantAuditLabels.length ? selectedVariantAuditLabels.join('+') : '-'}</b></div>
        <div><span>全包评分</span><b>{selectedVariant.executionFullScore?.toFixed(2) ?? '-'}</b></div>
        <div><span>全包状态</span><b>{executionBoolLabel(selectedVariant.executionFullCandidate)} / {executionBoolLabel(selectedVariant.executionFullKept)}</b></div>
        <div><span>分段</span><b>{selectedVariant.executionSegmentIdx ?? '-'}</b></div>
        <div><span>策略</span><b>{selectedVariant.executionPolicyName || selectedVariant.executionPolicyVersion || '-'}</b></div>
        {hasCodeNumbers(selectedVariant.executionSp) ? <div><span>执行SP</span><b>{codeNumberTripletLabel(selectedVariant.executionSp)}</b></div> : null}
        {selectedVariant.executionSpSnapshotTs ? <div><span>SP快照</span><b>{selectedVariant.executionSpSnapshotTs}</b></div> : null}
        {selectedVariant.executionSpRepriced || selectedVariant.executionSpMissing ? <div><span>SP变动</span><b>{selectedVariant.executionSpMissing ? '缺执行SP' : `重定价 x${selectedVariant.executionSpRepriceRatioMax?.toFixed(2) ?? '-'}`}</b></div> : null}
      </div>
      {selectedVariantExecutionDiffers ? <div className="execution-policy-diff">审计建议与可执行下注不同，出票按“可执行”列。</div> : null}
      {selectedVariant.executionReasons?.length ? <div className="compact-list execution-reasons">
        {selectedVariant.executionReasons.slice(0, 3).map((reason) => <p key={reason}>{reason}</p>)}
      </div> : null}
    </Card>}

	    {activeDecisionVersionSelected && activeSnapshot && draftSnapshot && <Card title="Active / Draft 对比" className="decision-snapshot-compare-card">
      <div className="decision-version-banner">
        <b>发现 draft_replacement，待确认覆盖</b>
        <span>Draft 不会自动覆盖 Active，需要用户手动确认。</span>
      </div>
      <div className="snapshot-diff-tags">
        {snapshotDiffBadges.length ? snapshotDiffBadges.map((item) => <Badge key={item} tone="warn">{item}</Badge>) : <Badge tone="neutral">无核心差异</Badge>}
      </div>
      <div className="snapshot-compare-grid">
        {renderSnapshotColumn(activeSnapshot, 'active')}
        {renderSnapshotColumn(draftSnapshot, 'draft')}
      </div>
      <div className="snapshot-action-row">
        <button type="button" disabled={confirmingDraft} onClick={() => onConfirmDraft(data.matchId)}>
          {confirmingDraft ? '确认中...' : '确认覆盖'}
        </button>
        <small className={currentConfirmState?.status === 'failed' ? 'bad-value' : currentConfirmState?.status === 'succeeded' ? 'good-text' : undefined}>
          {currentConfirmState?.message || `确认后 Draft 会提升为 Active，旧 Active 会进入 superseded；previous_active=${activeSnapshot.snapshotId}`}
        </small>
      </div>
    </Card>}

    <Card title="盘口与关注要点" className="market-panel">
      <div className="market-meta">更新 {latestOdds?.at || data.probabilityCalibratedAt || '缺'}</div>
      <div className="focus-card-grid">
        {focusCards.map((item) => <div key={item.label} className={`focus-card ${item.tone}`}>
          <span>{item.label}</span>
          <b className={item.label === '让球偏移' ? lineGapValueClass : undefined}>{item.value}</b>
          <p>{item.detail}</p>
        </div>)}
      </div>
      <div className="market-note compact"><span>概率差</span><b>{probabilityEdgeLabel(data.edge)}</b></div>
      {spChange !== '样本不足' && <div className="market-note compact"><span>SP变化</span><b>{spChange}</b></div>}
      {consensusDriftLabel && <div className="market-note compact"><span>欧赔变化</span><b>{consensusDriftLabel}</b></div>}
    </Card>

    <Card title="情报摘要">
      {(intelligence && intelligence.status === 'ok' && (decisionIntelPoints.length > 0 || intelligenceTags.length > 0)) || analysisRows.length ? <>
        <div className="intel-head">
          <b>{intelligence?.headline || `${data.league} ${data.home} vs ${data.away}`}</b>
          <span>{intelligence?.fetchedAt || analysis500?.fetchedAt || '未标记时间'}</span>
        </div>
        {decisionIntelPoints.length > 0 && <div className="intel-points compact-list">
          {decisionIntelPoints.map((point) => <p key={point}>{point}</p>)}
        </div>}
        {intelligenceTags.length > 0 && <div className="focus-points">
          {intelligenceTags.map((tag) => <Badge key={tag} tone={tag.includes('淘汰') || tag.includes('小组') ? 'warn' : 'neutral'}>{tag}</Badge>)}
        </div>}
      </> : <div className="empty-state"><b>情报未采集</b><span>{intelligence?.error || analysis500?.error || '等待独立情报脚本生成摘要。'}</span></div>}
    </Card>

    <Card title={shadowDecisionVersionSelected ? "结构化决策链" : "LLM 决策理由"}>
	      <div className="decision-input-grid">
	        <div><span>综合决策</span><b>{llmDecision}</b></div>
	        <div><span>主押</span><b>{primaryOutcome}</b></div>
	        <div><span>保护</span><b>{protectionOutcomes.length ? protectionOutcomes.join('+') : '-'}</b></div>
	        <div><span>置信</span><b>{selectedVariant?.confidenceLabel || (selectedVariant?.probability !== undefined ? pct(selectedVariant.probability) : llmReady ? data.llm.confidenceLabel : '待接入')}</b></div>
	        <div><span>决策时间</span><b>{decisionSnapshot?.generatedAt || data.llm.generatedAt || '缺'}</b></div>
	        <div><span>检查时间</span><b>{decisionSnapshot?.checkedAt || '-'}</b></div>
	        <div><span>版本</span><b>{selectedDecisionOption ? decisionVersionLabel(selectedDecisionOption) : decisionSnapshot?.decisionChainVersion || data.llm.source}</b></div>
	        <div><span>说明</span><b>{decisionSnapshot?.decisionConfigHash ? shortHash(decisionSnapshot.decisionConfigHash) : '-'}</b></div>
	      </div>
	      {shadowDecisionVersionSelected && shadowDecisionCategories.length > 0 && <div className="decision-category-grid">
	        {shadowDecisionCategories.map((item) => <div key={item.key || item.label} className="decision-category-card">
	          <span>{item.label}</span>
	          <b>{item.result || '-'}</b>
	          {item.score ? <strong>{item.score}</strong> : null}
	          {item.verdict ? <p>{item.verdict}</p> : null}
	          {(item.evidence ?? []).slice(0, 3).map((evidence) => <small key={evidence}>{evidence}</small>)}
	        </div>)}
	      </div>}
	      {shadowDecisionVersionSelected && shadowDecisionChain.length > 0 && <details className="llm-chain">
	        <summary>脚本汇总链路</summary>
	        <ol>{shadowDecisionChain.map((item) => <li key={item}>{item}</li>)}</ol>
	      </details>}
	      {activeDecisionVersionSelected && llmReady && (visibleLlmSupport.length > 0 || visibleLlmRisks.length > 0) && <div className="llm-evidence-grid">
	        {visibleLlmSupport.length > 0 && <div>
	          <span>支持依据</span>
	          {visibleLlmSupport.slice(0, 4).map((item) => <p key={item}>{item}</p>)}
	        </div>}
	        {visibleLlmRisks.length > 0 && <div>
	          <span>风险/反证</span>
	          {visibleLlmRisks.slice(0, 4).map((item) => <p key={item}>{item}</p>)}
	        </div>}
	      </div>}
	      {activeDecisionVersionSelected && llmReady && visibleLlmChain.length > 0 && <details className="llm-chain">
	        <summary>固定决策链</summary>
	        <ol>{visibleLlmChain.map((item) => <li key={item}>{item}</li>)}</ol>
	      </details>}
    </Card>

    <Card title="赛后复盘">
      {postmatchReview ? <>
        <div className="decision-input-grid">
          <div><span>结果</span><b><Badge tone={reviewTone(postmatchReview.outcomeLabel)}>{postmatchReview.outcomeLabel}</Badge></b></div>
          <div><span>投入</span><b>{money(postmatchReview.stake)}</b></div>
          <div><span>回报</span><b>{money(postmatchReview.grossReturn)}</b></div>
          <div><span>净收益</span><b className={postmatchReview.profit >= 0 ? 'profit-good' : 'profit-bad'}>{money(postmatchReview.profit)}</b></div>
        </div>
        <div className="decision-input-grid review-score-grid">
          <div><span>比分</span><b>{data.status === 'settled' ? data.score || '-' : '未完赛'}</b></div>
          <div><span>北单赛果</span><b>{data.resultLabel || '-'}</b></div>
          <div><span>结算SP</span><b>{data.settlementSp ?? '未结算'}</b></div>
          <div><span>复盘时间</span><b>{postmatchReview.reviewedAt || '-'}</b></div>
        </div>
        {postmatchReview.summary && <p className="postmatch-summary">{postmatchReview.summary}</p>}
        {postmatchReview.tags.length > 0 && <div className="review-tags">
          {postmatchReview.tags.map((tag) => <Badge key={tag} tone={tag.includes('hit') || tag.includes('saved') ? 'good' : tag.includes('trap') || tag.includes('wrong') || tag.includes('missed') || tag.includes('uncovered') ? 'bad' : 'warn'}>{reviewTagLabel(tag)}</Badge>)}
        </div>}
        {postmatchReview.actionSuggestion && <div className="review-action"><span>下次动作</span><b>{postmatchReview.actionSuggestion}</b></div>}
      </> : <>
	        <div className="decision-input-grid">
	          <div><span>比分</span><b>{data.status === 'settled' ? data.score || '-' : '未完赛'}</b></div>
	          <div><span>北单赛果</span><b>{data.resultLabel || '-'}</b></div>
	          <div><span>押保命中</span><b>{selectedDecisionHit === true ? '命中' : selectedDecisionHit === false ? '未中' : '待验证'}</b></div>
	          <div><span>结算SP</span><b>{data.settlementSp ?? '未结算'}</b></div>
	        </div>
        <p>等待赛后复盘脚本写入标签归因。</p>
      </>}
    </Card>

  </div>;
}

function legCodeLabel(value: string) {
  return pickListLabel(value.split('+'));
}

function bettingPlanScopeLabel(value?: string) {
  return BETTING_PLAN_SCOPE_OPTIONS.find((option) => option.value === value)?.label ?? value ?? '分段下注';
}

function matchIndexFromRow(match: IssueMatchRow, fallbackIndex: number) {
  if (typeof match.matchIdx === 'number' && Number.isFinite(match.matchIdx)) return match.matchIdx;
  const matchIdIndex = match.matchId.match(/_(\d{1,3})$/);
  if (matchIdIndex) return Number(matchIdIndex[1]);
  return fallbackIndex + 1;
}

function issueBoardLegLabel(matchIdx: number, match?: IssueMatchRow) {
  if (!match) return `#${matchIdx} 缺看板选择`;
  const selection = match.stopFlag || match.recommendedCoverage === 'no-buy'
    ? '不买'
    : match.recommendedOutcome || '待定';
  return `#${matchIdx} ${selection}`;
}

function multiplierLabel(value?: number, digits = 0) {
  if (value === undefined || !Number.isFinite(value)) return '-';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function driftRiskLabel(value?: string) {
  if (value === 'low') return '低';
  if (value === 'medium') return '中';
  if (value === 'high') return '高';
  return value || '未知';
}

function bettingPlanStatusLabel(value?: string) {
  if (value === 'available') return '已生成';
  if (value === 'degraded') return '待确认';
  if (value === 'missing') return '待生成';
  return value || '待生成';
}

function bettingPlanStatusTone(value?: string): 'good' | 'warn' | 'bad' | 'neutral' {
  if (value === 'available') return 'good';
  if (value === 'degraded' || value === 'missing') return 'warn';
  return 'neutral';
}

function BettingPlan({
  data,
  availableIssues,
  decisionVariantOptions,
	  issueMatches,
	  selectedIssue,
	  selectedDecisionVariant,
	  onIssueChange,
	  onDecisionVariantChange,
	  selectedPlanningScope,
	  onPlanningScopeChange,
	  selectedSegmentBudgetYuan,
	  onSegmentBudgetChange,
	  selectedStakeMode,
	  onStakeModeChange,
	}: {
	  data: DashboardData['segmentBettingPlan'];
	  availableIssues: DashboardData['availableIssues'];
	  decisionVariantOptions: DecisionVariantOption[];
	  issueMatches: IssueMatchRow[];
	  selectedIssue: string;
	  selectedDecisionVariant: string;
	  onIssueChange: (issueId: string) => void;
	  onDecisionVariantChange: (variantId: string) => void;
	  selectedPlanningScope: BettingPlanScope;
	  onPlanningScopeChange: (value: BettingPlanScope) => void;
	  selectedSegmentBudgetYuan: string;
	  onSegmentBudgetChange: (value: string) => void;
	  selectedStakeMode: string;
	  onStakeModeChange: (value: string) => void;
	}) {
	  const plans = data.availablePlans;
	  const fallbackVariantOptions: DecisionVariantOption[] = Array.from(new Map(plans.map((plan) => [plan.decisionVariantId, plan])).values())
	    .filter((plan) => plan.decisionVariantId)
	    .map((plan) => ({ variantId: plan.decisionVariantId, label: plan.label, version: '', source: '' }));
	  const variantOptions = decisionVariantOptions.length ? decisionVariantOptions : fallbackVariantOptions;
	  const selectedVariantValue = variantOptions.some((option) => option.variantId === selectedDecisionVariant)
	    ? selectedDecisionVariant
	    : variantOptions.find((option) => option.isDefault)?.variantId || variantOptions[0]?.variantId || '';
	  const topBundles = data.bundles.slice(0, 12);
	  const planUpdatedAt = data.artifactStatus.updatedAt || data.selectedPlan?.updatedAt || '';
	  const displayedMatchByIdx = useMemo(() => {
	    const entries = issueMatches.map((match, index) => {
	      const displayed = applyDecisionVariant(match, selectedVariantValue);
	      return [matchIndexFromRow(displayed, index), displayed] as const;
	    });
	    return new Map(entries);
	  }, [issueMatches, selectedVariantValue]);
	  const sourceLabel = data.selectionBinding?.frontendDisplaySource === 'issue_board' ? '期次看板同版本' : '期次看板';
	  return <div className="grid page-grid">
	    <Card title={`下注设计 / Issue ${data.issueId || selectedIssue}`} icon={<WalletCards />}>
      <div className="status-row">
        <span>下注方案</span>
        <Badge tone={bettingPlanStatusTone(data.availabilityStatus)}>{bettingPlanStatusLabel(data.availabilityStatus)}</Badge>
	      </div>
	      <div className="control-row">
	        <label>期号<select value={selectedIssue} onChange={(event) => onIssueChange(event.target.value)}>
	          {availableIssues.map((issue) => <option key={issue.issueId} value={issue.issueId}>{issue.label.replace('历史回放', '历史参考')}</option>)}
	        </select></label>
	        <label>决策链版本<select aria-label="选择下注决策链版本" value={selectedVariantValue} disabled={!variantOptions.length} onChange={(event) => onDecisionVariantChange(event.target.value)}>
	          {variantOptions.length ? variantOptions.map((option) => <option key={option.variantId} value={option.variantId}>{decisionVersionLabel(option)}</option>) : <option value="">暂无版本</option>}
	        </select></label>
	        <label>下注范围<select aria-label="选择下注范围" value={selectedPlanningScope} onChange={(event) => onPlanningScopeChange(event.target.value as BettingPlanScope)}>
	          {BETTING_PLAN_SCOPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
	        </select></label>
	        <label>预算<input aria-label="下注预算" type="number" min="2" step="2" value={selectedSegmentBudgetYuan} onChange={(event) => onSegmentBudgetChange(event.target.value)} /></label>
	        <label>投入方式<select aria-label="选择投入方式" value={selectedStakeMode} onChange={(event) => onStakeModeChange(event.target.value)}>
	          <option value="scale_to_budget">预算放大</option>
	          <option value="unit_once">基础投入</option>
	        </select></label>
	      </div>
	      {data.availabilityStatus !== 'available' ? <div className="empty-state"><b>暂无下注计划</b><span>{data.unavailableReason === 'segment_betting_plan_artifact_missing' ? '当前期下注计划还未生成，请稍后刷新。' : data.unavailableReason || '当前期下注计划还未生成。'}</span></div> : null}
		    </Card>
		    <Card title={selectedPlanningScope === 'entire_issue' ? '整期计划' : '分段计划'}>
	      {data.segments.length ? <div className="table-wrap"><table><thead><tr><th>段</th><th>时间窗</th><th>场次</th><th>N</th><th>票组</th><th>预算/成本</th><th>风险</th></tr></thead><tbody>{data.segments.map((segment) => <tr key={segment.segmentIdx ?? segment.segmentStart}>
	        <td>#{segment.segmentIdx}</td>
	        <td><div className="time-window-cell"><span>从 {segment.segmentStart}</span><span>到 {segment.segmentEnd}</span></div></td>
	        <td>{segment.eligibleMatches ?? '-'} 场<br/><small>#{segment.matchIndices.join(',')}</small></td>
	        <td>{segment.recommendedN ?? '-'}</td>
	        <td>{segment.selectedBundles ?? 0}<br/><small>候选 {segment.candidateBundles ?? '-'}</small></td>
	        <td>{moneyFixed(segment.selectedCostYuan)}<br/><small>基础 {moneyFixed(segment.baseCostYuan, 0)} · 倍数 {multiplierLabel(segment.stakeMultiplierUnits)}</small></td>
	        <td><Badge tone={segment.spDriftRiskAccepted ? 'warn' : 'good'}>SP变化{driftRiskLabel(segment.spDriftRiskLevel || data.spDriftRisk.level)}</Badge></td>
	      </tr>)}</tbody></table></div> : <div className="empty-state"><b>暂无分段计划</b></div>}
			    </Card>
		    <Card title="票组明细">
	      {planUpdatedAt ? <div className="status-row"><span>计划更新</span><Badge tone="neutral">{planUpdatedAt}</Badge></div> : null}
	      <div className="status-row"><span>方向来源</span><Badge tone="neutral">{sourceLabel}</Badge><span>{bettingPlanScopeLabel(data.requestedPlanningScope || selectedPlanningScope)}</span></div>
	      {topBundles.length ? <div className="table-wrap"><table><thead><tr><th>段/票组</th><th>N</th><th>场次</th><th>腿覆盖</th><th>成本</th></tr></thead><tbody>{topBundles.map((bundle) => <tr key={`${bundle.segmentIdx}-${bundle.bundleIdx}`}>
	        <td>#{bundle.segmentIdx} / {bundle.bundleIdx}</td>
	        <td>{bundle.nValue ?? '-'}<br/><small>{bundle.widths.join('×')}</small></td>
	        <td>{bundle.matchIndices.map((idx) => `#${idx}`).join(',')}</td>
	        <td>{bundle.matchIndices.map((idx) => issueBoardLegLabel(idx, displayedMatchByIdx.get(idx))).join(' | ')}</td>
	        <td>{moneyFixed(bundle.scaledCostYuan ?? bundle.costYuan)}<br/><small>基础 {moneyFixed(bundle.costYuan, 0)} · 倍数 {bundle.stakeMultiplier ?? 1}</small></td>
	      </tr>)}</tbody></table></div> : <div className="empty-state"><b>暂无票组明细</b></div>}
	    </Card>
  </div>;
}

function MainStrategy({ data }: { data: DashboardData['mainStrategy'] }) {
  const topTickets = data.evPool.tickets.slice(0, 8);
  const firstTicket = topTickets[0];
  const recentYears = data.annualPerformance.filter((row) => row.year >= 2023);
  const riskTone = data.riskState.riskLevel === 'normal' ? 'good' : data.riskState.riskLevel === 'watch' ? 'warn' : 'bad';
  const poolTone = data.evPool.available ? 'good' : 'warn';
  const recommendedArm = data.candidates.find((arm) => arm.armId === data.riskState.recommendedArm) ?? data.candidates[0];
  const totalReviewProfit = data.review.issues.reduce((sum, issue) => sum + issue.arms.reduce((armSum, arm) => armSum + arm.profitUnits, 0), 0);
  return <div className="grid page-grid">
    <section className="decision-hero">
      <div className="decision-hero-copy">
        <div className="eyebrow">Issue {data.issueId} · {data.strategyFamily}</div>
        <h2><Gauge />主策略决策摘要</h2>
        <div className="decision-line">
          <Badge tone={poolTone}>{data.evPool.status}</Badge>
          <Badge tone={riskTone}>{data.riskState.riskLevel}</Badge>
          <span>{data.mode === 'live_monitoring' ? '当前期实时观察' : '历史回放复盘'}</span>
        </div>
        <p>{data.riskState.reason}</p>
      </div>
      <div className="decision-stat-grid">
        <div><span>固定预算</span><b>{data.riskState.budget.selectedUnits}</b><small>{data.riskState.budget.baseUnits}+{data.riskState.budget.extraUnits} units</small></div>
        <div><span>推荐候选</span><b>{recommendedArm?.label ?? data.riskState.recommendedArm}</b><small>{data.riskState.recommendedArm}</small></div>
        <div><span>EV 票池</span><b>{data.evPool.ticketCount}</b><small>{data.evPool.available ? 'historical tickets' : 'not generated'}</small></div>
        <div><span>风控状态</span><b>{data.riskState.cooldown.state}</b><small>DD {units(data.riskState.cooldown.preDrawdownUnits, 0)} / L{data.riskState.cooldown.preLossStreak}</small></div>
      </div>
    </section>

    <Card title="A/B Strategy Candidates" icon={<WalletCards />}>
      <div className="ab-compare">
        {data.candidates.map((arm) => <div key={arm.armId} className={arm.armId === data.riskState.recommendedArm ? 'arm-panel selected' : 'arm-panel'}>
          <div className="arm-panel-head">
            <div><b>{arm.label}</b><small>{arm.armId}</small></div>
            <Badge tone={arm.role === 'stable' ? 'good' : 'warn'}>{arm.role}</Badge>
          </div>
          <div className="arm-metrics">
            <div><span>ROI</span><b>{pct(arm.roi)}</b></div>
            <div><span>profit/256</span><b>{units(arm.profitPer256, 0)}</b></div>
            <div><span>maxDD</span><b>{units(arm.maxDrawdownUnits, 0)}</b></div>
            <div><span>non-full-loss</span><b>{pct(arm.nonFullLossRate)}</b></div>
            <div><span>issue win</span><b>{pct(arm.issueWinRate)}</b></div>
            <div><span>recent ROI</span><b>{pct(arm.recentRoi)}</b></div>
          </div>
          <div className="allocation-line"><span>{arm.allocation}</span><small>{arm.rationale}</small></div>
        </div>)}
      </div>
      <div className="year-strip">{recentYears.map((row) => <div key={`${row.armId}-${row.year}`}><span>{row.year}</span><b className={row.profitUnits >= 0 ? 'good-text' : 'bad-text'}>{units(row.profitUnits, 0)}</b><small>{row.armId} · ROI {pct(row.roi)}</small></div>)}</div>
    </Card>

    <Card title="EV Ticket Pool">
      <div className="status-row">
        <Badge tone={data.evPool.available ? 'good' : 'warn'}>{data.evPool.status}</Badge>
        <span>{data.evPool.ticketCount} tickets · {data.evPool.source}</span>
      </div>
      {!data.evPool.available && <div className="empty-state"><b>正式 N=7 EV 票池未生成</b><span>当前只展示实时信号和 live proxy，不能当作生产出票。</span>{data.liveProxy && <small>{data.liveProxy.status} · {data.liveProxy.ticketCount} draft · {data.liveProxy.source}</small>}</div>}
      {topTickets.length > 0 && <div className="table-wrap"><table><thead><tr><th>Ticket</th><th>stake</th><th>EV / hit</th><th>topology</th><th>q/conf</th><th>line-gap</th><th>result</th><th>tags</th></tr></thead><tbody>{topTickets.map((ticket) => <tr key={ticket.ticketId}><td>{ticket.ticketIdx}<br/><small>{ticket.sourceStrategy}</small></td><td>{units(ticket.stakeUnits, 2)}</td><td>{units(ticket.predEvPerStake, 1)} / {pct(ticket.predHitProb)}</td><td>{ticket.topology}</td><td>{ticket.avgQScore.toFixed(2)} / {ticket.avgConfidenceWeight.toFixed(2)}</td><td>{ticket.lineGapSupportNet} / abs {ticket.avgAbsLineGap.toFixed(2)}</td><td><Badge tone={ticket.hit ? 'good' : ticket.hit === false ? 'bad' : 'neutral'}>{ticket.hit === undefined || ticket.hit === null ? 'open' : ticket.hit ? 'hit' : 'miss'}</Badge><br/><small>{units(ticket.profitUnits, 1)}</small></td><td><div className="tag-list">{ticket.diagnosticTags.map((tag) => <Badge key={tag}>{tag}</Badge>)}</div></td></tr>)}</tbody></table></div>}
    </Card>

    <Card title="Leg Diagnostics">
      {firstTicket?.legs.length ? <><div className="status-row"><Badge>ticket #{firstTicket.ticketIdx}</Badge><span>{firstTicket.sourceStrategy}</span></div><div className="table-wrap"><table><thead><tr><th>#</th><th>比赛</th><th>选择/结果</th><th>北单/亚盘</th><th>q/conf</th><th>SP</th><th>诊断</th></tr></thead><tbody>{firstTicket.legs.map((leg) => <tr key={leg.legId}><td>{leg.legId}</td><td>{leg.label}<br/><small>{leg.matchId}</small></td><td>{leg.selectionLabel} / {leg.resultLabel || 'open'}<br/><Badge tone={leg.hit ? 'good' : leg.hit === false ? 'bad' : 'neutral'}>{leg.hit === undefined || leg.hit === null ? 'open' : leg.hit ? 'hit' : 'miss'}</Badge></td><td>{leg.beidanHandicap ?? leg.handicap} / {leg.asian1hLine ?? '缺'}<br/><small>gap {leg.lineGap ?? '缺'}</small></td><td>{leg.qScore?.toFixed(2) ?? '缺'} / {leg.confidenceWeight?.toFixed(2) ?? '缺'}<br/><small>p {pct(leg.selectedModelP)}</small></td><td>{leg.winningSp ?? 'open'}<br/><small>mult {leg.predSpMultiplier?.toFixed(2) ?? '缺'}</small></td><td><div className="tag-list">{leg.diagnosticTags.map((tag) => <Badge key={tag}>{tag}</Badge>)}</div></td></tr>)}</tbody></table></div></> : <div className="empty-state"><b>没有历史腿级明细</b><span>真实模式不会用 mock 明细填充。</span></div>}
    </Card>

    <div className="grid two-col">
      <Card title="Risk State / Budget">
        <div className="risk-stack">
          <div><span>latest backtest</span><b>{data.riskState.latestBacktestIssue}</b></div>
          <div><span>pre state</span><b>L{data.riskState.cooldown.preLossStreak} / DD {units(data.riskState.cooldown.preDrawdownUnits, 0)}</b></div>
          <div><span>budget</span><b>{data.riskState.budget.mode} {data.riskState.budget.selectedUnits}</b></div>
        </div>
        <p>{data.riskState.cooldown.policy}</p>
        <div className="guardrails">{data.riskState.guardrails.map((item) => <Badge key={item} tone="warn">{item}</Badge>)}</div>
      </Card>

      <Card title="Line-gap / SP Drift Boundary">
        <div className="policy-list">
          <div><b>line-gap</b><span>{data.diagnostics.lineGapPolicy}</span></div>
          <div><b>SP drift</b><span>{data.diagnostics.spDriftPolicy}</span></div>
        </div>
        <div className="table-wrap"><table><thead><tr><th>paper arm</th><th>ROI</th><th>issue win</th><th>non-full-loss</th><th>maxDD</th><th>streak</th><th>status</th></tr></thead><tbody>{data.diagnostics.paperArms.map((arm) => <tr key={arm.armId}><td>{arm.armId}</td><td>{pct(arm.roi)}</td><td>{pct(arm.issueWinRate)}</td><td>{pct(arm.nonFullLossRate)}</td><td>{units(arm.maxDrawdownUnits, 0)}</td><td>{arm.maxLossStreak}</td><td>{arm.productionStatus}</td></tr>)}</tbody></table></div>
      </Card>
    </div>

    <Card title="Replay Review">
      <div className="review-summary">
        <div><span>review issues</span><b>{data.review.issues.length}</b></div>
        <div><span>visible PnL</span><b className={totalReviewProfit >= 0 ? 'good-text' : 'bad-text'}>{units(totalReviewProfit, 1)}</b></div>
        <div><span>source</span><b>{data.review.source.split('/').slice(-1)[0]}</b></div>
      </div>
      <div className="table-wrap"><table><thead><tr><th>Issue</th><th>Year</th><th>Close</th><th>Arm</th><th>Stake</th><th>Profit</th><th>ROI</th><th>Tickets / hits</th><th>Risk parts</th></tr></thead><tbody>{data.review.issues.flatMap((issue) => issue.arms.map((arm) => <tr key={`${issue.issueId}-${arm.armId}`}><td>{issue.issueId}</td><td>{issue.calendarYear}</td><td>{issue.issueCloseTs}</td><td>{arm.armId}</td><td>{units(arm.stakeUnits, 1)}</td><td className={arm.profitUnits >= 0 ? 'good-text' : 'bad-text'}>{units(arm.profitUnits, 1)}</td><td>{pct(arm.roi)}</td><td>{arm.tickets.toFixed(2)} / {arm.hits.toFixed(2)}</td><td>{arm.parts || arm.allocation}</td></tr>))}</tbody></table></div>
      <p>{data.source.noFutureLeakage}</p>
    </Card>
  </div>;
}

function OperationsStatus({
  data,
  reviewTaskState,
  onRunPostmatchReview,
}: {
  data: DashboardData['operations'];
  reviewTaskState?: ReviewTaskState;
  onRunPostmatchReview: (issueId: string, dryRun: boolean) => Promise<void>;
}) {
  const hasDraft = data.snapshots.draftReplacementCount > 0;
  const unreviewed = data.review.unreviewedSettledCount > 0;
  const failedSources = data.sources.filter((source) => source.status === 'failed');
  const warningSources = data.sources.filter((source) => source.status === 'partial' || source.status === 'stale');
  const sourceHealthTone = failedSources.length ? 'bad' : warningSources.length ? 'warn' : 'good';
  const workflowTone = statusTone(data.workflow.status);
  const reviewTask = data.review.task;
  const reviewTaskTone = statusTone(reviewTask.status);
  const currentReviewTaskState = reviewTaskState?.issueId === data.issueId ? reviewTaskState : undefined;
  const reviewTaskRunning = currentReviewTaskState?.status === 'submitting';
  const runtimeHealth = data.runtime.health;
  const runtimeProblems = [
    runtimeHealth?.api?.ok === false ? 'API 健康检查异常' : '',
    runtimeHealth?.frontendLocal?.ok === false ? '前端本地健康检查异常' : '',
    runtimeHealth?.operations?.ok === false ? '运行状态 API 异常' : '',
  ].filter(Boolean);
  const staleSnapshot = (data.issueStatus.latestSnapshotAgeMinutes ?? 0) > 60;
  const missingSettlementSp = Math.max(0, data.issueStatus.finishedCount - data.issueStatus.settledSpCount);
  const completedWorkflowSteps = data.workflow.steps.filter((step) => statusTone(step.status) === 'good').length;
  const workflowStepSummary = data.workflow.steps.length
    ? `${completedWorkflowSteps}/${data.workflow.steps.length} 步完成`
    : '尚未运行';
  const todoItems: Array<{ key: string; tone: 'good' | 'warn' | 'bad' | 'neutral'; code: string; title: string; detail: string }> = [];
  if (failedSources.length) {
    todoItems.push({
      key: 'source_failed',
      tone: 'bad',
      code: '数据源',
      title: '数据源抓取失败',
      detail: failedSources.map((source) => source.sourceName).join('、'),
    });
  }
  if (warningSources.length) {
    todoItems.push({
      key: 'source_warning',
      tone: 'warn',
      code: '数据源',
      title: '数据源过期或不完整',
      detail: warningSources.map((source) => `${source.sourceName} ${minutesLabel(source.ageMinutes)}`).join('、'),
    });
  }
  if (staleSnapshot) {
    todoItems.push({
      key: 'snapshot_stale',
      tone: 'warn',
      code: '快照',
      title: '当前期快照偏旧',
      detail: `最新快照 ${data.issueStatus.latestSnapshotAt || '缺失'}，距今 ${minutesLabel(data.issueStatus.latestSnapshotAgeMinutes)}`,
    });
  }
  if (missingSettlementSp > 0) {
    todoItems.push({
      key: 'settlement_sp_gap',
      tone: 'warn',
      code: '结算SP',
      title: '已完赛但结算SP未齐',
      detail: `${missingSettlementSp} 场需要继续刷新结算SP`,
    });
  }
  if (hasDraft) {
    todoItems.push({
      key: 'pending_draft',
      tone: 'warn',
      code: '决策',
      title: '待确认决策草稿',
      detail: `${data.snapshots.draftReplacementCount} 条决策草稿需要确认后才进入正式展示`,
    });
  }
  if (unreviewed) {
    todoItems.push({
      key: 'postmatch_review',
      tone: 'warn',
      code: '复盘',
      title: '未复盘赛果',
      detail: `${data.review.unreviewedSettledCount} 场已结算未复盘，建议先 dry-run 再写入`,
    });
  }
  if (data.workflow.error) {
    todoItems.push({
      key: 'workflow_failed',
      tone: 'bad',
      code: '刷新',
      title: '刷新流程失败',
      detail: data.workflow.error,
    });
  }
  if (reviewTask.error) {
    todoItems.push({
      key: 'review_failed',
      tone: 'bad',
      code: '复盘',
      title: '复盘任务失败',
      detail: reviewTask.error,
    });
  }
  if (runtimeProblems.length) {
    todoItems.push({
      key: 'runtime_health',
      tone: 'bad',
      code: '服务',
      title: '服务健康检查异常',
      detail: runtimeProblems.join('、'),
    });
  }
  return <div className="grid page-grid operations-page">
    <Card title={`实盘健康检查 / Issue ${data.issueId}`} icon={<Activity />}>
      <div className="hero-stats">
        <div><span>当前期</span><b>{data.issueStatus.currentIssue || data.issueId}</b><small>{data.generatedAt}</small></div>
        <div><span>比赛</span><b>{data.issueStatus.matchCount}</b><small>{data.issueStatus.finishedCount} 已完赛 / {data.issueStatus.openCount} 未完赛</small></div>
        <div><span>数据源</span><b><Badge tone={sourceHealthTone}>{opsStatusLabel(data.issueStatus.captureStatus)}</Badge></b><small>最新 {data.issueStatus.latestSnapshotAt || '缺'} · {minutesLabel(data.issueStatus.latestSnapshotAgeMinutes)}</small></div>
        <div><span>待处理</span><b>{data.snapshots.draftReplacementCount + data.review.unreviewedSettledCount}</b><small>{data.snapshots.draftReplacementCount} 草稿 / {data.review.unreviewedSettledCount} 未复盘</small></div>
      </div>
    </Card>

    <Card title="待处理事项" icon={<AlertTriangle />}>
      {todoItems.length ? <div className="ops-warning-list">{todoItems.map((item) => <div key={item.key} className={`ops-warning ${item.tone}`}>
        <Badge tone={item.tone}>{item.code}</Badge>
        <b>{item.title}</b>
        <span>{item.detail}</span>
      </div>)}</div> : <div className="empty-state"><b>没有阻断项</b><span>当前数据、决策快照和复盘状态可用于实盘检查。</span></div>}
    </Card>

    <Card title="数据源健康" icon={<Database />}>
      <div className="table-wrap"><table><thead><tr><th>数据源</th><th>状态</th><th>最后成功</th><th>新鲜度</th><th>采集</th><th>错误摘要</th></tr></thead><tbody>{data.sources.map((source) => <tr key={source.sourceName}><td>{source.sourceName}</td><td><Badge tone={statusTone(source.status)}>{opsStatusLabel(source.status)}</Badge></td><td>{source.lastSuccessAt || '-'}</td><td>{minutesLabel(source.ageMinutes)}</td><td>{source.okCount}/{source.totalAttempts}<br/><small>失败 {source.failCount}</small></td><td>{source.error || '-'}</td></tr>)}</tbody></table></div>
    </Card>

    <div className="grid two-col">
      <Card title="决策快照">
        <div className="ops-kpi-grid">
          <div><span>正式</span><b>{data.snapshots.activeCount}</b></div>
          <div><span>待确认</span><b className={hasDraft ? 'warn-value' : undefined}>{data.snapshots.draftReplacementCount}</b></div>
          <div><span>历史</span><b>{data.snapshots.supersededCount}</b></div>
        </div>
        {hasDraft ? <div className="table-wrap"><table><thead><tr><th>#</th><th>比赛</th><th>生成</th><th>检查</th></tr></thead><tbody>{data.snapshots.pendingDrafts.map((draft) => <tr key={draft.matchId}><td>{draft.matchIdx}</td><td>{draft.matchId}</td><td>{draft.generatedAt}</td><td>{draft.checkedAt}</td></tr>)}</tbody></table></div> : <p>没有待确认决策草稿。</p>}
      </Card>

      <Card title="复盘进度">
        <div className="ops-kpi-grid">
          <div><span>已结算</span><b>{data.review.settledMatchCount}</b></div>
          <div><span>已复盘</span><b>{data.review.reviewedMatchCount}</b></div>
          <div><span>未复盘</span><b className={unreviewed ? 'warn-value' : undefined}>{data.review.unreviewedSettledCount}</b></div>
        </div>
        <p>最新复盘 {data.review.latestReviewAt || '-'}</p>
        <div className="review-task-panel">
          <div className="review-task-head">
            <div><span>任务</span><b><Badge tone={reviewTaskTone}>{opsStatusLabel(reviewTask.status)}</Badge></b><small>{reviewTask.dryRun ? '试运行' : '正式写入'}</small></div>
            <div><span>检查</span><b>{reviewTask.result.wouldInsert ?? '-'}</b><small>预计写入</small></div>
            <div><span>耗时</span><b>{secondsLabel(reviewTask.elapsedSec)}</b><small>{reviewTask.finishedAt || reviewTask.startedAt || '-'}</small></div>
          </div>
          <div className="snapshot-action-row">
            <button type="button" disabled={reviewTaskRunning} onClick={() => onRunPostmatchReview(data.issueId, true)}>
              {reviewTaskRunning ? '运行中...' : '复盘 dry-run'}
            </button>
            <button type="button" disabled={reviewTaskRunning || data.review.unreviewedSettledCount === 0} onClick={() => onRunPostmatchReview(data.issueId, false)}>
              执行复盘写入
            </button>
            <small className={currentReviewTaskState?.status === 'failed' ? 'bad-value' : currentReviewTaskState?.status === 'succeeded' ? 'good-text' : undefined}>
              {currentReviewTaskState?.message || '试运行先检查，正式写入只处理未复盘赛果'}
            </small>
          </div>
          {reviewTask.error ? <div className="ops-warning bad"><Badge tone="bad">复盘</Badge><b>复盘失败</b><span>{reviewTask.error}</span></div> : null}
          <div className="review-task-result">
            <span>预计写入 {reviewTask.result.wouldInsert ?? '-'}</span>
            <span>已写入 {reviewTask.result.inserted ?? '-'}</span>
            <span>覆盖命中 {reviewTask.result.coverageHits ?? '-'}</span>
            <span>收益 {reviewTask.result.profit !== undefined ? money(reviewTask.result.profit) : '-'}</span>
          </div>
        </div>
        {unreviewed && <div className="table-wrap"><table><thead><tr><th>#</th><th>比赛</th><th>赛果</th><th>SP</th></tr></thead><tbody>{data.review.unreviewedMatches.map((match) => <tr key={match.matchId}><td>{match.matchIdx}</td><td>{match.label}<br/><small>{match.matchId}</small></td><td>{match.resultLabel}</td><td>{match.winningSp ?? '-'}</td></tr>)}</tbody></table></div>}
      </Card>
    </div>

    <Card title="操作区" icon={<Server />}>
      <div className="workflow-head">
        <div><span>刷新流程</span><b><Badge tone={workflowTone}>{opsStatusLabel(data.workflow.status)}</Badge></b><small>{workflowStepSummary}</small></div>
        <div><span>数据检查</span><b><Badge tone={statusTone(data.runtime.apiHealth)}>{healthProbeLabel(runtimeHealth?.api)}</Badge></b><small>{data.runtime.checkedAt || '未检查'}</small></div>
        <div><span>页面访问</span><b>{accessModeLabel(data.runtime.accessMode, data.runtime.externalAccessConfigured)}</b><small>{data.runtime.publicDiagnostics ? '诊断开启' : '诊断关闭'}</small></div>
        <div><span>最近耗时</span><b>{secondsLabel(data.workflow.elapsedSec)}</b><small>{data.workflow.finishedAt || data.workflow.startedAt || '-'}</small></div>
      </div>
    </Card>
  </div>;
}

function LiveSignals({ data }: { data: DashboardData['liveSignals'] }) {
  return <div className="grid two-col"><Card title={`Live Signals / Issue ${data.issueId}`} icon={<Clock />}><p>截止倒计时: {data.timeToDeadline} · 数据健康: {pct(data.sourceHealthScore)} · 最后抓取: {data.lastGlobalScrapeAt} · 下一次: {data.nextScrapeAt}</p><p>stale={data.staleSourceCount} failed={data.failedSourceCount}</p></Card><Card title="Source Monitor">{data.sources.map((s) => <div className="source" key={s.sourceName}><Badge tone={s.status === 'ok' ? 'good' : s.status === 'failed' ? 'bad' : 'warn'}>{s.status}</Badge><b>{s.sourceName}</b><span>{s.lastSuccessAt}</span><small>{s.errorMessage}</small></div>)}</Card><Card title="Drift Alert Feed">{data.alerts.map((a) => <div className="alert" key={a.alertId}><Badge tone={a.severity === 'high' ? 'bad' : 'warn'}>{a.severity}</Badge> {a.alertType} {a.matchId}: {a.beforeValue} → {a.afterValue}; action={a.recommendedAction}</div>)}</Card><Card title="Ticket Impact">{data.ticketImpacts.map((t) => <p key={t.ticketId}>{t.ticketId}: {t.affectedLegCount}腿受影响 EV {t.evBefore}→{t.evAfter}; risk {t.riskBefore}→{t.riskAfter}; stale={String(t.staleSnapshotFlag)}; reprice={String(t.repriceRequiredFlag)}</p>)}</Card></div>;
}

function SettlementReview({
  data,
  availableIssues,
  decisionVariantOptions,
  selectedIssue,
  selectedDecisionVariant,
  onIssueChange,
  onDecisionVariantChange,
  onOpenMatch,
}: {
  data: DashboardData['settlement'];
  availableIssues: DashboardData['availableIssues'];
  decisionVariantOptions: DecisionVariantOption[];
  selectedIssue: string;
  selectedDecisionVariant: string;
  onIssueChange: (issueId: string) => void;
  onDecisionVariantChange: (variantId: string) => void;
  onOpenMatch: (matchId: string) => void;
}) {
  const rawDecisionOptions = data.strategyVersionContext?.options?.length
    ? data.strategyVersionContext.options
    : data.decisionVariantOptions?.length
      ? data.decisionVariantOptions
      : decisionVariantOptions;
  const reviewDecisionOptions = displayableDecisionVariants(rawDecisionOptions);
  const selectedDecisionOption = reviewDecisionOptions.find((option) => option.variantId === selectedDecisionVariant)
    ?? reviewDecisionOptions.find((option) => option.isDefault)
    ?? reviewDecisionOptions[0];
  const summary = data.postmatchSummary;
  const tagEntries = Object.entries(summary?.tagCounts ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const defaultTag = tagEntries[0]?.[0] ?? '';
  const [selectedTag, setSelectedTag] = useState(defaultTag);
  useEffect(() => {
    setSelectedTag(defaultTag);
  }, [data.issueId, defaultTag]);
  const activeTag = selectedTag;
  const visibleReviews = activeTag ? data.postmatchReviews.filter((row) => row.tags.includes(activeTag)) : data.postmatchReviews;
  const uncoveredCount = summary?.tagCounts.uncovered_result ?? 0;
  const reviewCount = summary?.reviewCount ?? data.postmatchReviews.length;
  const topTags = tagEntries.slice(0, 8);
  const reviewIssueOptions = availableIssues.filter(isSettlementReviewIssue);
  const takeaways = settlementTakeaways(data);
  const focusRows = settlementFocusRows(data);
  return <div className="grid page-grid settlement-review-page">
    <Card title={`赛后复盘 / Issue ${data.issueId}`} icon={<AlertTriangle />}>
      <div className="issue-toolbar settlement-toolbar">
        {reviewIssueOptions.length ? <label>
          <span>期号</span>
          <select value={selectedIssue} onChange={(event) => onIssueChange(event.target.value)} aria-label="选择复盘期号">
            {reviewIssueOptions.map((issue) => <option key={issue.issueId} value={issue.issueId}>{issue.label}</option>)}
          </select>
        </label> : <div className="empty-state"><b>暂无已完结期</b><span>当前没有可复盘的完整结算期。</span></div>}
        {reviewDecisionOptions.length ? <label>
          <span>决策链版本</span>
          <select value={selectedDecisionOption?.variantId || selectedDecisionVariant || ''} onChange={(event) => onDecisionVariantChange(event.target.value)} aria-label="选择复盘决策链版本" disabled={reviewDecisionOptions.length <= 1}>
            {reviewDecisionOptions.map((option) => <option key={option.variantId} value={option.variantId}>{decisionVersionLabel(option)}</option>)}
          </select>
        </label> : null}
      </div>
      <div className="hero-stats">
        <div><span>投入</span><b>{money(data.totalStake)}</b></div>
        <div><span>回报</span><b>{money(data.grossReturn)}</b></div>
        <div><span>Profit</span><b className={data.netReturn >= 0 ? 'profit-good' : 'profit-bad'}>{money(data.netReturn)}</b></div>
        <div><span>ROI</span><b>{pct(data.roi)}</b></div>
      </div>
      <div className="review-kpi-grid">
        <div><span>已复盘</span><b>{reviewCount}</b></div>
        <div><span>主押命中</span><b>{summary?.primaryHits ?? '-'}</b></div>
        <div><span>保护救回</span><b>{summary?.protectHits ?? '-'}</b></div>
        <div><span>押+保覆盖</span><b>{summary?.coverageHits ?? '-'}</b></div>
        <div><span>未覆盖</span><b className={uncoveredCount > 0 ? 'bad-value' : undefined}>{uncoveredCount}</b></div>
      </div>
    </Card>

    <Card title="错因标签">
      {topTags.length ? <div className="tag-filter-list">
        <button type="button" className={!activeTag ? 'tag-filter active' : 'tag-filter'} onClick={() => setSelectedTag('')}>
          <span>全部</span><b>{data.postmatchReviews.length}</b>
        </button>
        {topTags.map(([tag, count]) => <button key={tag} type="button" className={activeTag === tag ? 'tag-filter active' : 'tag-filter'} onClick={() => setSelectedTag(tag)}>
          <span>{reviewTagLabel(tag)}</span><b>{count}</b>
        </button>)}
      </div> : <div className="empty-state"><b>暂无复盘标签</b></div>}
    </Card>

    <Card title="复盘焦点">
      {focusRows.length ? <div className="table-wrap"><table className="postmatch-review-table focus-review-table">
        <thead><tr><th>类型</th><th>比赛</th><th>押 / 保 / 赛果</th><th>收益</th><th>判断</th><th>下一步</th></tr></thead>
        <tbody>{focusRows.map((item) => <tr key={item.key}>
          <td><Badge tone={item.tone}>{item.label}</Badge></td>
          <td><b>#{item.row.matchIdx}</b> {item.row.home || item.row.matchId}{item.row.away ? ` vs ${item.row.away}` : ''}<br/><small>{item.row.league || '-'} · {item.row.kickoffTime || '-'}</small></td>
          <td>{item.row.llmJudgment || item.row.selectedOutcomes.join('+') || '-'}<br/><small>{item.row.score || '-'} · {item.row.resultLabel || '-'} {item.row.winningSp ? `(${item.row.winningSp})` : ''}</small></td>
          <td><b className={item.row.profit >= 0 ? 'profit-good' : 'profit-bad'}>{money(item.row.profit)}</b><br/><small>ROI {pct(item.row.roi)}</small></td>
          <td>{item.reason}</td>
          <td>{item.row.actionSuggestion || '保留到下一轮规则复核。'}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state"><b>暂无焦点场次</b><span>复盘脚本尚未写入逐场标签。</span></div>}
    </Card>

    <Card title="标签对应比赛">
      {visibleReviews.length ? <div className="table-wrap"><table className="postmatch-review-table">
        <thead><tr><th>#</th><th>比赛</th><th>下注 / 赛果</th><th>命中</th><th>收益</th><th>标签</th><th>动作</th></tr></thead>
        <tbody>{visibleReviews.map((row) => <tr key={`${row.matchId}-${row.outcomeLabel}`}>
          <td>{row.matchIdx}<br/><small>{row.kickoffTime || '-'}</small></td>
          <td><b>{row.league || '-'}</b><br/>{row.home || row.matchId} {row.away ? `vs ${row.away}` : ''}</td>
          <td>{row.llmJudgment || row.selectedOutcomes.join('+') || '-'}<br/><small>{row.score || '-'} · {row.resultLabel || '-'} {row.winningSp ? `(${row.winningSp})` : ''}</small></td>
          <td><Badge tone={reviewTone(row.outcomeLabel)}>{row.outcomeLabel || (row.coverageHit ? '覆盖' : '未评估')}</Badge><br/><small>主 {row.primaryHit ? '中' : '-'} / 保 {row.protectHit ? '中' : '-'}</small></td>
          <td><b className={row.profit >= 0 ? 'profit-good' : 'profit-bad'}>{money(row.profit)}</b><br/><small>{money(row.stake)} → {money(row.grossReturn)}</small></td>
          <td><div className="tag-list">{row.tags.map((tag) => <Badge key={tag} tone={tag.includes('uncovered') || tag.includes('missed') || tag.includes('wrong') || tag.includes('trap') ? 'bad' : tag.includes('saved') || tag.includes('hit') ? 'good' : 'warn'}>{reviewTagLabel(tag)}</Badge>)}</div></td>
          <td><button type="button" onClick={() => onOpenMatch(row.matchId)}>查看</button></td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state"><b>没有匹配比赛</b></div>}
    </Card>

    <Card title="复盘结论">
      <div className="review-takeaway-list">
        {takeaways.map((item) => <div key={item.title} className={`review-takeaway ${item.tone}`}>
          <span>{item.title}</span>
          <b>{item.body}</b>
        </div>)}
      </div>
    </Card>
  </div>;
}

function SelectorShadow({ data }: { data: DashboardData['selectorShadow'] }) {
  const selectorArm = data.arms.find((arm) => arm.role === 'selector');
  const baselineArm = data.arms.find((arm) => arm.role === 'baseline');
  const chosenTone = data.currentDecision.chosenArm === data.currentDecision.defensiveArm ? 'warn' : 'good';
  return <div className="grid page-grid">
    <Card title={`Selector Shadow / Issue ${data.issueId}`} icon={<ShieldAlert />}>
      <div className="selector-banner">
        <div>
          <span>frozen rule</span>
          <b>{data.ruleName}</b>
        </div>
        <div>
          <span>mode</span>
          <b>{data.mode}</b>
        </div>
        <div>
          <span>chosen arm</span>
          <b><Badge tone={chosenTone}>{data.currentDecision.chosenArm}</Badge></b>
        </div>
        <div>
          <span>budget</span>
          <b>{data.currentDecision.budgetUnits} units</b>
        </div>
      </div>
      <div className="selector-reason">
        <Badge tone={data.currentDecision.stateSignal ? 'warn' : 'neutral'}>state={String(data.currentDecision.stateSignal)}</Badge>
        <Badge tone={data.currentDecision.qualitySignal ? 'warn' : 'neutral'}>quality={String(data.currentDecision.qualitySignal)}</Badge>
        <span>{data.currentDecision.reason}</span>
      </div>
    </Card>

    <Card title="Live Decision Inputs">
      <div className="metric-grid">
        <div><span>pre loss streak</span><b>{data.currentDecision.preLossStreak}</b></div>
        <div><span>pre drawdown</span><b>{units(data.currentDecision.preDrawdownUnits)}</b></div>
        <div><span>weak count</span><b>{data.currentDecision.weakCount}</b></div>
        <div><span>weak score</span><b>{data.currentDecision.weakScore.toFixed(2)}</b></div>
        <div><span>history</span><b>{data.currentDecision.qualityHistoryIssues}</b></div>
        <div><span>generated</span><b>{data.generatedAt}</b></div>
      </div>
      <div className="flag-list">{data.featureFlags.map((flag) => <div key={flag.feature} className={flag.weak ? 'flag weak' : 'flag'}>
        <b>{flag.feature}</b><span>value {flag.value}</span><span>threshold {flag.threshold}</span><Badge tone={flag.weak ? 'warn' : 'good'}>{flag.weak ? 'weak' : 'ok'}</Badge>
      </div>)}</div>
    </Card>

    <Card title="Arm Comparison">
      <div className="table-wrap"><table><thead><tr><th>Arm</th><th>Role</th><th>profit/256</th><th>ROI</th><th>maxDD</th><th>loss streak</th><th>issue win</th><th>recent profit/256</th><th>Δ profit</th><th>Δ maxDD</th></tr></thead><tbody>
        {data.arms.map((arm) => <tr key={arm.armId} className={arm.role === 'selector' ? 'selected-row' : ''}><td>{arm.label}<br/><small>{arm.armId}</small></td><td>{arm.role}</td><td>{units(arm.profitPer256, 1)}</td><td>{pct(arm.roi)}</td><td>{units(arm.maxDrawdownUnits, 1)}</td><td>{arm.maxLossStreak}</td><td>{pct(arm.issueWinRate)}</td><td>{units(arm.recentProfitPer256, 1)}</td><td className={arm.deltaProfitPer256VsBase >= 0 ? 'delta good-text' : 'delta bad-text'}>{units(arm.deltaProfitPer256VsBase, 1)}</td><td className={arm.deltaMaxDrawdownUnitsVsBase >= 0 ? 'delta good-text' : 'delta bad-text'}>{units(arm.deltaMaxDrawdownUnitsVsBase, 1)}</td></tr>)}
      </tbody></table></div>
      <p>{baselineArm && selectorArm ? `selector v2 相比 baseline 少 ${Math.abs(selectorArm.deltaProfitPer256VsBase).toFixed(1)} profit/256，换来 ${selectorArm.deltaMaxDrawdownUnitsVsBase.toFixed(1)} maxDD 改善和 ${Math.abs(selectorArm.deltaLossStreakVsBase)} 期最长亏损改善。` : data.guardrail}</p>
    </Card>

    <Card title="Switch Attribution">
      <div className="attribution-grid">{data.switchAttribution.map((row) => <div key={row.group}><b>{row.group}</b><span>{row.count} switches</span><span>Δ {units(row.deltaVsBaseUnits, 1)}</span><small>helped {row.helped} / hurt {row.hurt} / flat {row.flat}</small></div>)}</div>
    </Card>

    <Card title="Rolling Stability">
      <table><thead><tr><th>Window</th><th>profit+ rate</th><th>maxDD+ rate</th><th>both+ rate</th><th>avg profit Δ</th><th>avg maxDD Δ</th><th>avg streak Δ</th></tr></thead><tbody>{data.rollingStability.map((row) => <tr key={row.window}><td>{row.window}</td><td>{pct(row.profitPositiveRate)}</td><td>{pct(row.maxDrawdownPositiveRate)}</td><td>{pct(row.bothPositiveRate)}</td><td>{units(row.avgProfitDelta, 1)}</td><td>{units(row.avgMaxDrawdownDelta, 1)}</td><td>{units(row.avgLossStreakDelta, 2)}</td></tr>)}</tbody></table>
    </Card>

    <Card title="Recent Decision Log">
      <div className="table-wrap"><table><thead><tr><th>Issue</th><th>Year</th><th>Chosen</th><th>Reason</th><th>Δ vs base</th><th>Base</th><th>Selector</th><th>Weak</th><th>Pre state</th><th>Outcome</th></tr></thead><tbody>{data.recentDecisions.map((row) => <tr key={row.issueId}><td>{row.issueId}</td><td>{row.year}</td><td>{row.chosenArm}</td><td>{row.reason}</td><td className={row.deltaVsBaseUnits >= 0 ? 'good-text' : 'bad-text'}>{units(row.deltaVsBaseUnits, 1)}</td><td>{units(row.baseProfitUnits, 1)}</td><td>{units(row.selectorProfitUnits, 1)}</td><td>{row.weakCount}</td><td>L{row.preLossStreak} / DD {units(row.preDrawdownUnits)}</td><td><Badge tone={row.outcome === 'helped' ? 'good' : row.outcome === 'hurt' ? 'bad' : 'neutral'}>{row.outcome}</Badge></td></tr>)}</tbody></table></div>
      <p>{data.guardrail}</p>
    </Card>
  </div>;
}

function StrategyLab({ data }: { data: DashboardData['strategyLab'] }) {
  return <div className="grid page-grid"><Card title="Strategy Lab" icon={<LineChart />}><p>Arms: {data.arms.map((a) => <Badge key={a.armId}>{a.armId}</Badge>)}</p><div className="curve">{data.arms.map((a) => <div key={a.armId}><b>{a.armId}</b><span>{a.equityCurve.map((p) => '▇').join('')}</span><small>ROI {pct(a.roi)} MaxDD {pct(a.maxDrawdown)} — {a.description}</small></div>)}</div></Card><Card title="年度表现"><table><thead><tr><th>Arm</th><th>Year</th><th>Issues</th><th>Stake</th><th>Return</th><th>ROI</th><th>MaxDD</th><th>HitRate</th></tr></thead><tbody>{data.annualPerformance.map((r) => <tr key={`${r.armId}-${r.year}`}><td>{r.armId}</td><td>{r.year}</td><td>{r.issueCount}</td><td>{money(r.totalStake)}</td><td>{money(r.grossReturn)}</td><td>{pct(r.roi)}</td><td>{pct(r.maxDrawdown)}</td><td>{pct(r.hitTicketRate)}</td></tr>)}</tbody></table></Card><Card title="Recent Performance / Arm Difference Explainer"><p>{data.arms.map((a) => `${a.armId} recent ROI ${pct(a.recentRoi)}`).join('；')}</p><p>allocator: 降低高风险全包，增加保护腿；smooth: 少选低 confidence 高SP候选；384: 候选重合率 63%。</p></Card><Card title="失败聚类 / 上线护栏">{data.failureClusters.map((f) => <p key={f.errorTag}>{reviewTagLabel(f.errorTag)}: {f.count}次 impact {money(f.stakeImpact)} issues {f.topIssues.join(',')}</p>)}<p>建议: {data.guardrail}</p></Card></div>;
}

export default function App() {
	  const [page, setPage] = useState<Page>('Issue Dashboard');
		  const [selectedIssue, setSelectedIssue] = useState('current');
			  const [selectedMatchId, setSelectedMatchId] = useState<string | undefined>();
					  const [selectedDecisionVariant, setSelectedDecisionVariant] = useState(DEFAULT_DECISION_VARIANT_ID);
					  const [selectedSegmentBudgetYuan, setSelectedSegmentBudgetYuan] = useState('1000');
				  const [selectedSegmentStakeMode, setSelectedSegmentStakeMode] = useState('scale_to_budget');
				  const [selectedBettingPlanScope, setSelectedBettingPlanScope] = useState<BettingPlanScope>(DEFAULT_BETTING_PLAN_SCOPE);
			  const [data, setData] = useState<DashboardShellData | null>(null);
	  const [error, setError] = useState<string | null>(null);
	  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'refreshing'>('idle');
	  const [pageLoadState, setPageLoadState] = useState<DeferredPageState | undefined>();
	  const [pageErrors, setPageErrors] = useState<Partial<Record<Page, string>>>({});
	  const [refreshTick, setRefreshTick] = useState(0);
	  const [confirmDraftState, setConfirmDraftState] = useState<ConfirmDraftState | undefined>();
	  const [reviewTaskState, setReviewTaskState] = useState<ReviewTaskState | undefined>();
	  const requestSeq = useRef(0);
	  const pageRequestSeq = useRef(0);
	  const shellVariantRef = useRef(selectedDecisionVariant);
  const dataMode = import.meta.env.VITE_DATA_MODE as string | undefined;
  const baseUrl = dashboardApiBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined);
  const adapter = useMemo(() => new ApiDashboardAdapter({ mode: dataMode === 'mock' ? 'mock' : 'fetch', baseUrl }), [dataMode, baseUrl]);
  const shellMatchId = dataMode === 'mock' ? selectedMatchId : undefined;

  useEffect(() => {
    if (dataMode === 'mock') return;
    const refreshMs = Number((import.meta.env.VITE_REFRESH_MS as string | undefined) ?? 60000);
    if (!Number.isFinite(refreshMs) || refreshMs <= 0) return;
    const timer = window.setInterval(() => setRefreshTick((value) => value + 1), refreshMs);
    return () => window.clearInterval(timer);
  }, [dataMode]);

		  useEffect(() => {
		    const requestId = requestSeq.current + 1;
		    requestSeq.current = requestId;
		    setLoadState(data ? 'refreshing' : 'loading');
		    const previousVariant = shellVariantRef.current;
		    const request = dataMode === 'mock'
		      ? adapter.getDashboardData(selectedIssue, shellMatchId, selectedDecisionVariant)
		      : adapter.getDashboardShell(selectedIssue, selectedDecisionVariant);
		    request
		      .then((nextData) => {
		        if (requestSeq.current !== requestId) return;
		        setData((prev) => {
		          if (dataMode === 'mock') return nextData as DashboardData;
		          const shell = nextData as Pick<DashboardData, 'availableIssues' | 'issue'>;
		          const sameIssue = prev?.issue.issueId === shell.issue.issueId;
		          const sameVariant = previousVariant === selectedDecisionVariant;
		          return sameIssue && sameVariant ? { ...prev, ...shell } : shell;
		        });
		        shellVariantRef.current = selectedDecisionVariant;
		        setError(null);
		        setLoadState('idle');
		      })
		      .catch((err: unknown) => {
		        if (requestSeq.current !== requestId) return;
		        setError(err instanceof Error ? err.message : String(err));
		        setLoadState('idle');
		      });
		  }, [adapter, selectedIssue, shellMatchId, selectedDecisionVariant, refreshTick, dataMode]);

  useEffect(() => {
    if (!data || dataMode === 'mock') return;
    const issueId = data.issue.issueId || selectedIssue;
    const firstMatchId = data.issue.matches[0]?.matchId;
    const matchId = selectedMatchId ?? firstMatchId;
    const settlementReviewIssues = data.availableIssues.filter(isSettlementReviewIssue);
    const settlementIssueId = settlementReviewIssues.some((issue) => issue.issueId === selectedIssue)
      ? selectedIssue
      : data.settlement?.issueId ?? settlementReviewIssues[0]?.issueId ?? issueId;
    let promise: Promise<unknown> | undefined;
    let apply: ((prev: DashboardShellData, payload: unknown) => DashboardShellData) | undefined;
    let loaded = false;
    let message = '正在读取真实数据...';

    if (page === 'Match Detail') {
      if (!matchId) return;
      loaded = data.matchDetail?.matchId === matchId;
      promise = loaded ? undefined : adapter.getMatchDetail(issueId, matchId, selectedDecisionVariant);
      apply = (prev, payload) => ({ ...prev, matchDetail: payload as DashboardData['matchDetail'] });
      message = '正在加载单场详情...';
    } else if (page === 'Settlement Review') {
      const loadedSettlementVariant = data.settlement?.strategyVersionContext?.selectedVariantId || '';
      loaded = data.settlement?.issueId === settlementIssueId
        && (!loadedSettlementVariant || loadedSettlementVariant === selectedDecisionVariant);
      promise = loaded ? undefined : adapter.getSettlementReview(settlementIssueId, selectedDecisionVariant);
      apply = (prev, payload) => ({ ...prev, settlement: payload as DashboardData['settlement'] });
      message = '正在加载最近完结期复盘...';
    } else if (page === 'Operations') {
      loaded = data.operations?.issueId === issueId;
      promise = loaded ? undefined : adapter.getOperationsStatus(issueId);
      apply = (prev, payload) => ({ ...prev, operations: payload as DashboardData['operations'] });
      message = '正在加载运行状态...';
	    } else if (page === 'Betting Plan') {
	      const requestedBudgetYuan = selectedSegmentBudgetYuan.trim() ? Number(selectedSegmentBudgetYuan) : undefined;
	      const normalizedBudgetYuan = requestedBudgetYuan !== undefined && Number.isFinite(requestedBudgetYuan) ? requestedBudgetYuan : undefined;
	      loaded = data.segmentBettingPlan?.issueId === issueId
	        && data.segmentBettingPlan?.requestedDecisionVariantId === selectedDecisionVariant
	        && data.segmentBettingPlan?.requestedPlanningScope === selectedBettingPlanScope
	        && (normalizedBudgetYuan === undefined || data.segmentBettingPlan?.requestedSegmentBudgetYuan === normalizedBudgetYuan)
	        && (!selectedSegmentStakeMode || data.segmentBettingPlan?.requestedStakeMode === selectedSegmentStakeMode);
	      promise = loaded ? undefined : adapter.getSegmentBettingPlan(issueId, selectedDecisionVariant, undefined, {
	        planningScope: selectedBettingPlanScope,
	        segmentBudgetYuan: normalizedBudgetYuan,
	        stakeMode: selectedSegmentStakeMode,
	      });
	      apply = (prev, payload) => ({ ...prev, segmentBettingPlan: payload as DashboardData['segmentBettingPlan'] });
      message = '正在加载下注设计...';
    } else if (page === 'Live Signals') {
      loaded = data.liveSignals?.issueId === issueId;
      promise = loaded ? undefined : adapter.getLiveSignals(issueId);
      apply = (prev, payload) => ({ ...prev, liveSignals: payload as DashboardData['liveSignals'] });
      message = '正在加载实时信号...';
    } else if (page === 'Strategy Lab') {
      loaded = Boolean(data.strategyLab);
      promise = loaded ? undefined : adapter.getStrategyLab();
      apply = (prev, payload) => ({ ...prev, strategyLab: payload as DashboardData['strategyLab'] });
      message = '正在加载策略实验...';
    }

    if (!promise || !apply) return;
    const requestId = pageRequestSeq.current + 1;
    pageRequestSeq.current = requestId;
    setPageLoadState({ page, status: loaded ? 'refreshing' : 'loading', message });
    setPageErrors((prev) => ({ ...prev, [page]: undefined }));
    promise
      .then((payload) => {
        if (pageRequestSeq.current !== requestId) return;
        setData((prev) => (prev ? apply(prev, payload) : prev));
        setPageLoadState(undefined);
      })
      .catch((err: unknown) => {
        if (pageRequestSeq.current !== requestId) return;
        setPageErrors((prev) => ({ ...prev, [page]: err instanceof Error ? err.message : String(err) }));
        setPageLoadState(undefined);
      });
	  }, [adapter, data, dataMode, page, selectedBettingPlanScope, selectedDecisionVariant, selectedIssue, selectedMatchId, selectedSegmentBudgetYuan, selectedSegmentStakeMode]);

  const rawAvailableDecisionVariants = data?.issue.strategyVersionContext?.options?.length
    ? data.issue.strategyVersionContext.options
    : data?.issue.decisionVariantOptions?.length
      ? data.issue.decisionVariantOptions
      : data?.matchDetail?.strategyVersionContext?.options?.length
        ? data.matchDetail.strategyVersionContext.options
        : data?.matchDetail?.decisionVariantOptions ?? [];
  const availableDecisionVariants = displayableDecisionVariants(rawAvailableDecisionVariants);
  const contextSelectedDecisionVariant = data?.issue.strategyVersionContext?.selectedVariantId
    || data?.matchDetail?.strategyVersionContext?.selectedVariantId
    || '';
  const defaultAvailableDecisionVariant = contextSelectedDecisionVariant
    || availableDecisionVariants.find((option) => option.isDefault)?.variantId
    || availableDecisionVariants[0]?.variantId
    || '';
  const effectiveSelectedDecisionVariant = selectedDecisionVariant || defaultAvailableDecisionVariant;
  const availableDecisionVariantKey = availableDecisionVariants.map((option) => option.variantId).join('|');
  useEffect(() => {
    if (!data || availableDecisionVariants.length === 0) return;
    if (selectedDecisionVariant && !availableDecisionVariants.some((option) => option.variantId === selectedDecisionVariant)) {
      setSelectedDecisionVariant('');
    }
  }, [data, availableDecisionVariantKey, availableDecisionVariants, selectedDecisionVariant]);

  const handleConfirmDraft = async (matchId: string) => {
    setConfirmDraftState({ matchId, status: 'submitting', message: '正在确认 draft 覆盖...' });
    try {
      const result = await adapter.confirmDecisionSnapshot(matchId);
      const activeId = result.active?.snapshotId ? `active=${result.active.snapshotId}` : result.action;
      setConfirmDraftState({ matchId, status: 'succeeded', message: `确认完成，${activeId}，正在刷新 Issue/Operations 状态。` });
      setData((prev) => prev ? { ...prev, matchDetail: undefined, operations: undefined } : prev);
      setRefreshTick((value) => value + 1);
    } catch (err: unknown) {
      setConfirmDraftState({ matchId, status: 'failed', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const handleRunPostmatchReview = async (issueId: string, dryRun: boolean) => {
    setReviewTaskState({ issueId, status: 'submitting', message: dryRun ? '正在检查未复盘比赛...' : '正在写入赛后复盘...' });
    try {
      const result = await adapter.runPostmatchReview(issueId, dryRun);
      const count = dryRun ? result.result.wouldInsert ?? 0 : result.result.inserted ?? 0;
      setReviewTaskState({ issueId, status: 'succeeded', message: dryRun ? `dry-run 完成，预计写入 ${count} 场。` : `复盘写入完成，新增 ${count} 场，正在刷新。` });
      setData((prev) => prev ? { ...prev, operations: undefined, settlement: undefined } : prev);
      setRefreshTick((value) => value + 1);
    } catch (err: unknown) {
      setReviewTaskState({ issueId, status: 'failed', message: err instanceof Error ? err.message : String(err) });
    }
  };

	  const handleDecisionVariantChange = (variantId: string) => {
	    setSelectedDecisionVariant(variantId);
	  };

	  if (!data) return <main><h1>北单实盘决策台</h1><p role={error ? 'alert' : undefined}>{error ? `数据加载失败：${error}` : 'Loading dashboard data...'}</p></main>;

	  const settlementReviewIssues = data.availableIssues.filter(isSettlementReviewIssue);
	  const selectedSettlementIssue = settlementReviewIssues.some((issue) => issue.issueId === selectedIssue)
	    ? selectedIssue
	    : data.settlement?.issueId ?? settlementReviewIssues[0]?.issueId ?? data.issue.issueId;
	  const selectedIssueOption = selectedIssue === 'current' ? data.issue.issueId : selectedIssue;
	  const activePageLoad = pageLoadState?.page === page ? pageLoadState : undefined;
	  const activePageError = pageErrors[page];

		  return <main>
		    <header>
		      <div className="header-title"><h1>北单实盘决策台</h1><span className="ui-build-badge">{UI_BUILD_LABEL}</span></div>
		      <nav>{pages.map((p) => <button key={p} className={page === p ? 'active' : ''} onClick={() => setPage(p)}>{PAGE_LABELS[p]}</button>)}</nav>
		    </header>
		    {error ? <div className="sync-banner bad" role="alert"><b>数据刷新失败</b><span>{error}</span><small>继续显示上一次成功数据；真实模式不会回退到 mock。</small></div> : null}
		    {loadState === 'refreshing' ? <div className="sync-banner"><b>正在刷新数据</b><span>页面暂时保留当前快照。</span></div> : null}
		    {page === 'Issue Dashboard' && <IssueDashboard
		      data={data.issue}
		      availableIssues={data.availableIssues}
		      selectedIssue={selectedIssueOption}
		      selectedDecisionVariant={effectiveSelectedDecisionVariant}
		      onIssueChange={(issueId) => {
		        setSelectedIssue(issueId);
		        setSelectedMatchId(undefined);
		      }}
	      onDecisionVariantChange={handleDecisionVariantChange}
	      onOpenMatch={(matchId) => {
	        setSelectedMatchId(matchId);
	        setPage('Match Detail');
	      }}
	    />}
	    {page === 'Betting Plan' && (data.segmentBettingPlan ? <BettingPlan
	      data={data.segmentBettingPlan}
	      availableIssues={data.availableIssues}
	      decisionVariantOptions={availableDecisionVariants}
	      issueMatches={data.issue.matches}
	      selectedIssue={selectedIssueOption}
	      selectedDecisionVariant={effectiveSelectedDecisionVariant}
		      onIssueChange={(issueId) => {
		        setSelectedIssue(issueId);
		        setSelectedMatchId(undefined);
		      }}
		      onDecisionVariantChange={handleDecisionVariantChange}
		      selectedPlanningScope={selectedBettingPlanScope}
		      onPlanningScopeChange={setSelectedBettingPlanScope}
		      selectedSegmentBudgetYuan={selectedSegmentBudgetYuan}
		      onSegmentBudgetChange={setSelectedSegmentBudgetYuan}
		      selectedStakeMode={selectedSegmentStakeMode}
		      onStakeModeChange={setSelectedSegmentStakeMode}
		    /> : <DeferredPage title="下注设计" loading={activePageLoad} error={activePageError} />)}
	    {page === 'Match Detail' && (data.matchDetail ? <MatchDetail
	      data={data.matchDetail}
	      selectedDecisionVariant={effectiveSelectedDecisionVariant}
	      onDecisionVariantChange={handleDecisionVariantChange}
	      confirmDraftState={confirmDraftState}
	      onConfirmDraft={handleConfirmDraft}
	    /> : <DeferredPage title="比赛详情" loading={activePageLoad} error={activePageError} />)}
	    {page === 'Operations' && (data.operations
	      ? <OperationsStatus data={data.operations} reviewTaskState={reviewTaskState} onRunPostmatchReview={handleRunPostmatchReview} />
	      : <DeferredPage title="运行状态" loading={activePageLoad} error={activePageError} />)}
	    {page === 'Live Signals' && (data.liveSignals
	      ? <LiveSignals data={data.liveSignals} />
	      : <DeferredPage title="实时信号" loading={activePageLoad} error={activePageError} />)}
	    {page === 'Settlement Review' && (data.settlement ? <SettlementReview
	      data={data.settlement}
	      availableIssues={data.availableIssues}
	      decisionVariantOptions={availableDecisionVariants}
	      selectedIssue={selectedSettlementIssue}
	      selectedDecisionVariant={effectiveSelectedDecisionVariant}
		      onIssueChange={(issueId) => {
		        setSelectedIssue(issueId);
		        setSelectedMatchId(undefined);
		      }}
	      onDecisionVariantChange={handleDecisionVariantChange}
	      onOpenMatch={(matchId) => {
	        setSelectedMatchId(matchId);
	        setPage('Match Detail');
	      }} /> : <DeferredPage title="赛后复盘" loading={activePageLoad} error={activePageError} />)}
	    {page === 'Strategy Lab' && (data.strategyLab
	      ? <StrategyLab data={data.strategyLab} />
	      : <DeferredPage title="策略实验" loading={activePageLoad} error={activePageError} />)}
	  </main>;
	}
