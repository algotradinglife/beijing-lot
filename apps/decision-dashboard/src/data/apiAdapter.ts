import { mockDashboardData } from './mockData';
import { DEFAULT_DECISION_VARIANT_ID } from '../decisionVariants';
import type { AdhocBettingEligibilityData, AdhocBettingPlanData, CandidateRole, CoverageType, DashboardData, DecisionArtifactCompleteness, DecisionArtifactGenerateResult, DecisionArtifactStatusData, DecisionSnapshotConfirmResult, DecisionSnapshotData, DecisionVariantData, DecisionVariantOption, ExactNFreezeData, IssueDashboardData, IssueMatchRow, IssueOption, LiveSignalsData, MainStrategyData, MatchDetailData, OddsConsensus, OperationsStatusData, PostmatchReviewData, ScrapeStatus, SegmentBettingPlanData, SelectorShadowData, SettlementData, StrategyLabData, StrategyVersionContext, TicketData } from './types';

export type AdapterMode = 'mock' | 'fetch';

type ApiObject = Record<string, unknown>;

type ApiMatchSummary = ApiObject & {
  match_id?: string;
  match_idx?: number;
  issue?: string;
  league?: string;
  kickoff_ts?: string;
  kickoff_date?: string;
  home?: string;
  away?: string;
  handicap_line?: number;
  score?: string;
  halftime_score?: string;
  live_score_status?: string;
  live_score_status_text?: string;
  sp_3?: number;
  sp_1?: number;
  sp_0?: number;
  eu_home?: number;
  eu_draw?: number;
  eu_away?: number;
  ah_line?: number | string | null;
  ah_home?: number;
  ah_away?: number;
  line_gap?: number | null;
  sp_drift_3?: number | null;
  sp_drift_1?: number | null;
  sp_drift_0?: number | null;
  sp_drift_band?: string;
  sp_snapshot_ts?: string;
  q_input_sp_snapshot_ts?: string;
  q_input_probability_snapshot_ts?: string;
  q_calculated_ts?: string;
  odds_consensus?: unknown;
  market_highlights?: string[];
  q_max?: number;
  q_score?: number;
  confidence_weight?: number;
  model_p_3?: number;
  model_p_1?: number;
  model_p_0?: number;
  model_selection?: string;
  model_selection_codes?: string[];
  model_selection_type?: string;
  model_prediction_hit?: boolean | null;
  selection?: string;
  selection_codes?: string[];
  selection_source?: string;
  selection_type?: string;
  llm_judgment?: string;
  llm_selection?: string;
  llm_selection_codes?: string[];
  llm_selection_type?: string;
  llm_q_score?: number;
  llm_probability?: number;
  llm_confidence?: number;
  llm_confidence_label?: string;
  llm_source?: string;
  llm_prediction_hit?: boolean | null;
  decision_snapshot_id?: string;
  decision_snapshot_status?: string;
  decision_snapshot_generated_at?: string;
  decision_snapshot_checked_at?: string;
	  draft_decision_snapshot_id?: string;
	  draft_decision_snapshot_status?: string;
	  draft_decision_snapshot_generated_at?: string;
	  postmatch_review?: unknown;
	  postmatch_review_outcome?: string;
	  postmatch_review_summary?: string;
	  postmatch_review_tags?: string[];
	  postmatch_review_action?: string;
	  postmatch_review_profit?: number;
	  postmatch_review_reviewed_at?: string;
	  status?: string;
  capture_status?: string;
  result_code?: string;
  result_label?: string;
  prediction_hit?: boolean | null;
	  winning_sp?: number;
	  candidate_role?: string;
	  decision_variants?: unknown;
	};

type ApiPrediction = ApiObject & {
  q_score?: number;
  confidence_weight?: number;
  model_p_3?: number;
  model_p_1?: number;
  model_p_0?: number;
  market_p_3?: number;
  market_p_1?: number;
  market_p_0?: number;
  llm_judgment?: string;
  llm_explanation?: string;
  llm_confidence?: number;
  llm_confidence_label?: string;
  llm_support?: string[];
  llm_risks?: string[];
  llm_decision_chain?: string[];
  llm_model?: string;
  llm_source?: string;
  generated_ts?: string;
  calculated_ts?: string;
  q_calculated_ts?: string;
  q_input_sp_snapshot_ts?: string;
  q_input_probability_snapshot_ts?: string;
  q_input_policy?: string;
  prediction_sp_source?: string;
  prediction_sp_snapshot_ts?: string;
  probability_snapshot_ts?: string;
  probability_source?: string;
  selection?: string;
  selection_codes?: string[];
  selection_type?: string;
  llm_selection?: string;
  llm_selection_codes?: string[];
  llm_selection_type?: string;
  llm_q_score?: number;
  llm_probability?: number;
	  decision_snapshot_id?: string;
	  decision_snapshot_status?: string;
	  decision_snapshot_generated_at?: string;
	  draft_decision_snapshot_id?: string;
	  prob_model_version?: string;
	  q_model_version?: string;
	  decision_chain_version?: string;
	  decision_config_hash?: string;
	  review_tag_version?: string;
	  version_bundle?: unknown;
	};

function asObject(value: unknown): ApiObject {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as ApiObject : {};
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => asString(item)).filter(Boolean);
  if (typeof value === 'string') return value.split(';').map((item) => item.trim()).filter(Boolean);
  return [];
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' ? value : fallback;
}

function asMaybeNumber(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined;
}

function asNumberRecord(value: unknown): Record<string, number> {
  const obj = asObject(value);
  return Object.fromEntries(Object.entries(obj).map(([key, item]) => [key, asNumber(item)]));
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function asNullableBoolean(value: unknown): boolean | null | undefined {
  return typeof value === 'boolean' ? value : value === null ? null : undefined;
}

function toCoverage(value: unknown, fallback: CoverageType = 'single'): CoverageType {
  if (value === 'single' || value === 'double' || value === 'full' || value === 'no-buy') return value;
  if (value === 'all' || value === 'any') return 'full';
  return fallback;
}

function toScrapeStatus(value: unknown): ScrapeStatus {
  if (value === 'partial' || value === 'missing' || value === 'failed' || value === 'stale') return value;
  return 'ok';
}

function selectionLabel(selection: unknown): string {
  if (selection === '3') return '胜';
  if (selection === '1') return '平';
  if (selection === '0') return '负';
  if (typeof selection === 'string') return selection;
  return '观察';
}

function formatClock(value: unknown): string {
  const text = asString(value, '');
  if (!text) return '';
  const match = text.match(/(?:T| )(\d{2}:\d{2})/);
  return match?.[1] ?? text;
}

function formatDateTimeShort(value: unknown): string {
  const text = asString(value, '');
  if (!text) return '';
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  return match ? `${match[1]} ${match[2]}` : text;
}

function formatDate(value: unknown): string {
  const text = asString(value, '');
  if (!text) return '';
  return text.includes('T') ? text.slice(0, 10) : text.slice(0, 10);
}

function toProb(win?: number, draw?: number, loss?: number): IssueMatchRow['modelProb'] {
  return { win, draw, loss };
}

function transformAnalysis500(raw: unknown): MatchDetailData['analysis500'] {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  const urls = asObject(obj.urls);
  const homeRecent = asObject(obj.home_recent);
  const awayRecent = asObject(obj.away_recent);
  const h2h = asObject(obj.h2h);
  return {
    status: asString(obj.status, 'missing'),
    fetchedAt: asString(obj.fetched_at),
    title: asString(obj.title),
    description: asString(obj.description),
    urls: {
      data: asString(urls.data),
      recommendation: asString(urls.recommendation),
      asian: asString(urls.asian),
      europe: asString(urls.europe),
    },
    homeRecent: {
      team: asString(homeRecent.team),
      summary: asString(homeRecent.summary),
      rows: asArray<Record<string, string>>(homeRecent.rows),
    },
    awayRecent: {
      team: asString(awayRecent.team),
      summary: asString(awayRecent.summary),
      rows: asArray<Record<string, string>>(awayRecent.rows),
    },
    h2h: {
      summary: asString(h2h.summary),
      rows: asArray<Record<string, string>>(h2h.rows),
    },
    leagueTable: asString(obj.league_table),
    source: asString(obj.source, 'odds.500.com/fenxi/shuju'),
    highlights: asArray<string>(obj.highlights),
    marketSummary: asString(obj.market_summary),
    oddsConsensus: transformOddsConsensus(obj.odds_consensus),
    error: asString(obj.error),
  };
}

function transformIntelligence(raw: unknown): MatchDetailData['intelligence'] {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  const stage = asObject(obj.stage);
  return {
    status: asString(obj.status, 'missing'),
    fetchedAt: asString(obj.fetched_at, asString(obj.fetchedAt)),
    headline: asString(obj.headline),
    points: asArray(obj.points).map((value) => asString(value)).filter(Boolean),
    tags: asArray(obj.tags).map((value) => asString(value)).filter(Boolean),
    stage: {
      competitionLabel: asString(stage.competition_label, asString(stage.competitionLabel)) || undefined,
      stageName: asString(stage.stage_name, asString(stage.stageName)) || undefined,
      stageType: asString(stage.stage_type, asString(stage.stageType)) || undefined,
      group: asString(stage.group) || undefined,
      round: asString(stage.round) || undefined,
      homeStanding: asString(stage.home_standing, asString(stage.homeStanding)) || undefined,
      awayStanding: asString(stage.away_standing, asString(stage.awayStanding)) || undefined,
    },
    sources: asArray(obj.sources).map((sourceRaw) => {
      const source = asObject(sourceRaw);
      return {
        source: asString(source.source),
        tier: asString(source.tier),
        status: asString(source.status),
        title: asString(source.title),
        url: asString(source.url),
        error: asString(source.error),
      };
    }),
    sourceCount: asNumber(obj.source_count, asNumber(obj.sourceCount)),
    error: asString(obj.error),
  };
}

function oddsTriplet(raw: unknown): { home?: number; draw?: number; away?: number } {
  const obj = asObject(raw);
  return {
    home: asMaybeNumber(obj.home),
    draw: asMaybeNumber(obj.draw),
    away: asMaybeNumber(obj.away),
  };
}

function transformOddsConsensus(raw: unknown): OddsConsensus | undefined {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  const providers = asArray(obj.providers).map((providerRaw) => {
    const provider = asObject(providerRaw);
    return {
      company: asString(provider.company),
      open: oddsTriplet(provider.open),
      current: oddsTriplet(provider.current),
    };
  }).filter((provider) => provider.company);
  return {
    nCompanies: asNumber(obj.n_companies, asNumber(obj.nCompanies)),
    openAvg: oddsTriplet(obj.open_avg ?? obj.openAvg),
    currentAvg: oddsTriplet(obj.current_avg ?? obj.currentAvg),
    drift: oddsTriplet(obj.drift),
    providers,
  };
}

function transformDecisionSnapshot(raw: unknown): DecisionSnapshotData | undefined {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  return {
    snapshotId: asString(obj.snapshot_id, asString(obj.snapshotId)),
    status: asString(obj.status),
    generatedAt: formatDateTimeShort(obj.generated_at ?? obj.generatedAt),
    checkedAt: formatDateTimeShort(obj.checked_at ?? obj.checkedAt),
    confirmedAt: formatDateTimeShort(obj.confirmed_at ?? obj.confirmedAt) || undefined,
    supersededAt: formatDateTimeShort(obj.superseded_at ?? obj.supersededAt) || undefined,
    supersedesSnapshotId: asString(obj.supersedes_snapshot_id, asString(obj.supersedesSnapshotId)) || undefined,
    inputHash: asString(obj.input_hash, asString(obj.inputHash)),
    recommendation: asString(obj.recommendation),
    primaryPick: asString(obj.primary_pick, asString(obj.primaryPick)) || undefined,
    protectPicks: asArray(obj.protect_picks ?? obj.protectPicks).map((value) => asString(value)).filter(Boolean),
    stopFlag: asBoolean(obj.stop_flag, asBoolean(obj.stopFlag)),
    selectionCodes: asArray(obj.selection_codes ?? obj.selectionCodes).map((value) => asString(value)).filter(Boolean),
    confidence: asMaybeNumber(obj.confidence),
    confidenceLabel: asString(obj.confidence_label, asString(obj.confidenceLabel)) || undefined,
	    qScore: asMaybeNumber(obj.q_score ?? obj.qScore),
	    probability: asMaybeNumber(obj.probability),
	    promptVersion: asString(obj.prompt_version, asString(obj.promptVersion)),
	    modelVersion: asString(obj.model_version, asString(obj.modelVersion)),
	    probModelVersion: asString(obj.prob_model_version, asString(obj.probModelVersion)) || undefined,
	    qModelVersion: asString(obj.q_model_version, asString(obj.qModelVersion)) || undefined,
	    decisionChainVersion: asString(obj.decision_chain_version, asString(obj.decisionChainVersion)) || undefined,
	    decisionConfigHash: asString(obj.decision_config_hash, asString(obj.decisionConfigHash)) || undefined,
	    reviewTagVersion: asString(obj.review_tag_version, asString(obj.reviewTagVersion)) || undefined,
	  };
	}

function transformDecisionSnapshotConfirm(raw: unknown): DecisionSnapshotConfirmResult {
  const obj = asObject(raw);
  return {
    action: asString(obj.action),
    confirmedAt: formatDateTimeShort(obj.confirmed_at ?? obj.confirmedAt) || undefined,
    previousActive: transformDecisionSnapshot(obj.previous_active ?? obj.previousActive),
    active: transformDecisionSnapshot(obj.active),
    error: asString(obj.error) || undefined,
  };
}

function transformDecisionArtifactCompleteness(raw: unknown): DecisionArtifactCompleteness {
  const obj = asObject(raw);
  return {
    issue: asString(obj.issue),
    scope: asString(obj.scope),
    complete: asBoolean(obj.complete),
    expectedCount: asNumber(obj.expected_count, asNumber(obj.expectedCount)),
    actualCount: asNumber(obj.actual_count, asNumber(obj.actualCount)),
    expectedMatchIdx: asArray(obj.expected_match_idx ?? obj.expectedMatchIdx).map((value) => asNumber(value)).filter((value) => Number.isFinite(value)),
    actualMatchIdx: asArray(obj.actual_match_idx ?? obj.actualMatchIdx).map((value) => asNumber(value)).filter((value) => Number.isFinite(value)),
    missingMatchIdx: asArray(obj.missing_match_idx ?? obj.missingMatchIdx).map((value) => asNumber(value)).filter((value) => Number.isFinite(value)),
    extraMatchIdx: asArray(obj.extra_match_idx ?? obj.extraMatchIdx).map((value) => asNumber(value)).filter((value) => Number.isFinite(value)),
  };
}

function transformDecisionArtifactStatus(raw: unknown): DecisionArtifactStatusData {
  const obj = asObject(raw);
  const latestWorkflow = asObject(obj.latest_workflow ?? obj.latestWorkflow);
  const latestGenerationStep = asObject(obj.latest_generation_step ?? obj.latestGenerationStep);
  return {
    issueId: asString(obj.issue, asString(obj.issueId)),
    requestedVariantId: asString(obj.requested_variant_id, asString(obj.requestedVariantId)),
    variantId: asString(obj.variant_id, asString(obj.variantId)),
    artifactVariantId: asString(obj.artifact_variant_id, asString(obj.artifactVariantId)),
    status: asString(obj.status),
    message: asString(obj.message),
    generationSupported: asBoolean(obj.generation_supported, asBoolean(obj.generationSupported)),
    sourcePath: asString(obj.source_path, asString(obj.sourcePath)),
    rowCount: asNumber(obj.row_count, asNumber(obj.rowCount)),
    expectedMatchCount: asNumber(obj.expected_match_count, asNumber(obj.expectedMatchCount)),
    completeness: transformDecisionArtifactCompleteness(obj.completeness),
    snapshotCompleteness: transformDecisionArtifactCompleteness(obj.snapshot_completeness ?? obj.snapshotCompleteness),
    latestWorkflow: Object.keys(latestWorkflow).length ? {
      runId: asString(latestWorkflow.run_id, asString(latestWorkflow.runId)),
      status: asString(latestWorkflow.status),
      startedAt: asString(latestWorkflow.started_at, asString(latestWorkflow.startedAt)),
      finishedAt: asString(latestWorkflow.finished_at, asString(latestWorkflow.finishedAt)),
    } : undefined,
    latestGenerationStep: Object.keys(latestGenerationStep).length ? {
      stepIdx: asMaybeNumber(latestGenerationStep.step_idx ?? latestGenerationStep.stepIdx),
      stepKey: asString(latestGenerationStep.step_key, asString(latestGenerationStep.stepKey)) || undefined,
      label: asString(latestGenerationStep.label) || undefined,
      status: asString(latestGenerationStep.status) || undefined,
      startedAt: asString(latestGenerationStep.started_at, asString(latestGenerationStep.startedAt)) || undefined,
      finishedAt: asString(latestGenerationStep.finished_at, asString(latestGenerationStep.finishedAt)) || undefined,
      error: asString(latestGenerationStep.error) || undefined,
    } : undefined,
  };
}

function transformDecisionArtifactGenerate(raw: unknown): DecisionArtifactGenerateResult {
  const obj = asObject(raw);
  return {
    issueId: asString(obj.issue, asString(obj.issueId)),
    variantId: asString(obj.variant_id, asString(obj.variantId)),
    artifactVariantId: asString(obj.artifact_variant_id, asString(obj.artifactVariantId)),
    status: asString(obj.status),
    materializeSnapshots: asBoolean(obj.materialize_snapshots, asBoolean(obj.materializeSnapshots)),
    artifactStatus: transformDecisionArtifactStatus(obj.artifact_status ?? obj.artifactStatus),
  };
}

function transformDecisionVariantOption(raw: unknown): DecisionVariantOption {
  const obj = asObject(raw);
  return {
    variantId: asString(obj.variant_id, asString(obj.variantId, DEFAULT_DECISION_VARIANT_ID)),
    kind: asString(obj.kind, asString(obj.variant_kind, asString(obj.variantKind))) || undefined,
    family: asString(obj.family) || undefined,
    label: asString(obj.label, asString(obj.variant_id, asString(obj.variantId, 'v3'))),
    displayLabel: asString(obj.display_label, asString(obj.displayLabel)) || undefined,
    version: asString(obj.version),
    versionId: asString(obj.version_id, asString(obj.versionId)) || undefined,
    source: asString(obj.source),
    sourcePath: asString(obj.source_path, asString(obj.sourcePath)) || undefined,
    artifactKey: asString(obj.artifact_key, asString(obj.artifactKey)) || undefined,
    isDefault: asBoolean(obj.is_default, asBoolean(obj.isDefault)),
    selectable: asBoolean(obj.selectable, asBoolean(obj.selectable, true)),
    available: asBoolean(obj.available, asBoolean(obj.available, true)),
    defaultable: asBoolean(obj.defaultable, asBoolean(obj.defaultable, true)),
    readinessStatus: asString(obj.readiness_status, asString(obj.readinessStatus)) || undefined,
    degradedReason: asString(obj.degraded_reason, asString(obj.degradedReason)) || undefined,
  };
}

function transformDecisionCategory(raw: unknown) {
  const obj = asObject(raw);
  return {
    key: asString(obj.key),
    label: asString(obj.label),
    result: asString(obj.result),
    score: asString(obj.score) || undefined,
    verdict: asString(obj.verdict) || undefined,
    evidence: asArray(obj.evidence).map((value) => asString(value)).filter(Boolean),
  };
}

function transformDecisionVariant(raw: unknown): DecisionVariantData {
  const obj = asObject(raw);
  const option = transformDecisionVariantOption(obj);
  return {
    ...option,
    recommendation: asString(obj.recommendation),
    primaryPick: asString(obj.primary_pick, asString(obj.primaryPick)) || undefined,
    protectPicks: asArray(obj.protect_picks ?? obj.protectPicks).map((value) => asString(value)).filter(Boolean),
    selectionCodes: asArray(obj.selection_codes ?? obj.selectionCodes).map((value) => asString(value)).filter(Boolean),
    selectionType: toCoverage(obj.selection_type ?? obj.selectionType, 'no-buy'),
    stopFlag: asBoolean(obj.stop_flag, asBoolean(obj.stopFlag)),
    qScore: asMaybeNumber(obj.q_score ?? obj.qScore),
    probability: asMaybeNumber(obj.probability),
    confidenceLabel: asString(obj.confidence_label, asString(obj.confidenceLabel)) || undefined,
    predictionHit: asNullableBoolean(obj.prediction_hit ?? obj.predictionHit),
    primaryHit: asNullableBoolean(obj.primary_hit ?? obj.primaryHit),
    coverageHit: asNullableBoolean(obj.coverage_hit ?? obj.coverageHit),
    notes: asArray(obj.notes).map((value) => asString(value)).filter(Boolean),
    executionPolicyVersion: asString(obj.execution_policy_version, asString(obj.executionPolicyVersion)) || undefined,
    executionPolicyName: asString(obj.execution_policy_name, asString(obj.executionPolicyName)) || undefined,
    executionAction: asString(obj.execution_action, asString(obj.executionAction)) || undefined,
    executionReasons: asStringList(obj.execution_reasons ?? obj.executionReasons),
    executionSourceAction: asString(obj.execution_source_action, asString(obj.executionSourceAction)) || undefined,
    executionRecommendedCodes: asString(obj.execution_recommended_codes, asString(obj.executionRecommendedCodes)) || undefined,
    executionDoubleCodes: asString(obj.execution_double_codes, asString(obj.executionDoubleCodes)) || undefined,
    executionFullScore: asMaybeNumber(obj.execution_full_score ?? obj.executionFullScore),
    executionFullCandidate: asNullableBoolean(obj.execution_full_candidate ?? obj.executionFullCandidate),
    executionFullKept: asNullableBoolean(obj.execution_full_kept ?? obj.executionFullKept),
    executionSegmentIdx: asMaybeNumber(obj.execution_segment_idx ?? obj.executionSegmentIdx),
    executionUnlockState: asString(obj.execution_unlock_state, asString(obj.executionUnlockState)) || undefined,
    sourceSp: asNumberRecord(obj.source_sp ?? obj.sourceSp),
    sourceQ: asNumberRecord(obj.source_q ?? obj.sourceQ),
    executionSp: asNumberRecord(obj.execution_sp ?? obj.executionSp),
    executionQ: asNumberRecord(obj.execution_q ?? obj.executionQ),
    executionSpSource: asString(obj.execution_sp_source, asString(obj.executionSpSource)) || undefined,
    executionSpSnapshotTs: asString(obj.execution_sp_snapshot_ts, asString(obj.executionSpSnapshotTs)) || undefined,
    executionSpRepriced: asNullableBoolean(obj.execution_sp_repriced ?? obj.executionSpRepriced),
    executionSpRepriceRatioMax: asMaybeNumber(obj.execution_sp_reprice_ratio_max ?? obj.executionSpRepriceRatioMax),
    executionSpMissing: asNullableBoolean(obj.execution_sp_missing ?? obj.executionSpMissing),
    decisionChain: asArray(obj.decision_chain ?? obj.decisionChain).map((value) => asString(value)).filter(Boolean),
    decisionCategories: asArray(obj.decision_categories ?? obj.decisionCategories).map(transformDecisionCategory),
  };
}

function transformStrategyVersionContext(raw: unknown): StrategyVersionContext | undefined {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  const release = asObject(obj.strategy_release ?? obj.strategyRelease);
  const health = asObject(release.artifact_health ?? release.artifactHealth);
  return {
    schemaVersion: asString(obj.schema_version, asString(obj.schemaVersion)),
    requestedVariantId: asString(obj.requested_variant_id, asString(obj.requestedVariantId)),
    selectedVariantId: asString(obj.selected_variant_id, asString(obj.selectedVariantId)),
    selectionStatus: asString(obj.selection_status, asString(obj.selectionStatus, 'ok')),
    selectionError: asString(obj.selection_error, asString(obj.selectionError)) || undefined,
    availableVariantIds: asArray(obj.available_variant_ids ?? obj.availableVariantIds).map((value) => asString(value)).filter(Boolean),
    options: asArray(obj.options).map(transformDecisionVariantOption),
    contractWarnings: asArray(obj.contract_warnings ?? obj.contractWarnings).map((warningRaw) => {
      const warning = asObject(warningRaw);
      return {
        type: asString(warning.type),
        variantIds: asArray(warning.variant_ids ?? warning.variantIds).map((value) => asString(value)).filter(Boolean),
        message: asString(warning.message),
      };
    }),
    strategyRelease: Object.keys(release).length ? {
      releaseId: asString(release.release_id, asString(release.releaseId)),
      activeReleaseId: asString(release.active_release_id, asString(release.activeReleaseId)),
      versionId: asString(release.version_id, asString(release.versionId)),
      generatedAt: asString(release.generated_at, asString(release.generatedAt)),
      effectiveFromIssue: asString(release.effective_from_issue, asString(release.effectiveFromIssue)),
      loadStatus: asString(release.release_load_status, asString(release.releaseLoadStatus, 'ok')),
      loadError: asString(release.release_load_error, asString(release.releaseLoadError)) || undefined,
      fallbackUsed: asBoolean(release.fallback_used, asBoolean(release.fallbackUsed)),
      missingRequiredCount: asArray(health.missing_required ?? health.missingRequired).length,
    } : undefined,
  };
}

function transformPostmatchReview(raw: unknown): PostmatchReviewData | undefined {
  const obj = asObject(raw);
  if (!Object.keys(obj).length) return undefined;
  return {
    issue: asString(obj.issue),
    matchIdx: asNumber(obj.match_idx, asNumber(obj.matchIdx)),
	    matchId: asString(obj.match_id, asString(obj.matchId)),
	    reviewVersion: asString(obj.review_version, asString(obj.reviewVersion)),
	    tagVersion: asString(obj.tag_version, asString(obj.tagVersion)) || undefined,
	    reviewedAt: formatDateTimeShort(obj.reviewed_at ?? obj.reviewedAt),
    decisionSnapshotId: asString(obj.decision_snapshot_id, asString(obj.decisionSnapshotId)) || undefined,
    decisionSnapshotGeneratedAt: formatDateTimeShort(obj.decision_snapshot_generated_at ?? obj.decisionSnapshotGeneratedAt),
    outcomeLabel: asString(obj.outcome_label, asString(obj.outcomeLabel)),
    summary: asString(obj.summary),
    actionSuggestion: asString(obj.action_suggestion, asString(obj.actionSuggestion)),
    tags: asArray(obj.tags).map((value) => asString(value)).filter(Boolean),
    primaryHit: asBoolean(obj.primary_hit, asBoolean(obj.primaryHit)),
    protectHit: asBoolean(obj.protect_hit, asBoolean(obj.protectHit)),
    coverageHit: asBoolean(obj.coverage_hit, asBoolean(obj.coverageHit)),
    stopped: asBoolean(obj.stopped),
    stake: asNumber(obj.stake),
    grossReturn: asNumber(obj.gross_return, asNumber(obj.grossReturn)),
    profit: asNumber(obj.profit),
    roi: asNumber(obj.roi),
  };
}

function transformRuntimeHealthProbe(raw: unknown) {
  const obj = asObject(raw);
  return {
    ok: asBoolean(obj.ok),
    status: asNumber(obj.status),
    url: asString(obj.url),
    hostHeader: asString(obj.host_header, asString(obj.hostHeader)) || undefined,
    latencyMs: asMaybeNumber(obj.latency_ms ?? obj.latencyMs),
    error: asString(obj.error) || undefined,
    issue: asString(obj.issue) || undefined,
    workflowStatus: asString(obj.workflow_status, asString(obj.workflowStatus)) || undefined,
    reviewTaskStatus: asString(obj.review_task_status, asString(obj.reviewTaskStatus)) || undefined,
  };
}

function operatorTokenHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage?.getItem('BEIDAN_OPERATOR_TOKEN')?.trim();
  return token ? { 'X-Beidan-Operator-Token': token } : {};
}

function toCandidateRole(value: unknown, qScore?: number): CandidateRole {
  if (value === 'core' || value === 'protect' || value === 'watch' || value === 'avoid') return value;
  if (qScore === undefined) return 'watch';
  if (qScore >= 2) return 'core';
  if (qScore >= 1.2) return 'protect';
  return 'watch';
}

function transformIssueOption(raw: unknown): IssueOption {
  const row = asObject(raw);
  return {
    issueId: asString(row.issue, asString(row.issueId)),
    label: asString(row.label, asString(row.issue, asString(row.issueId))),
    status: asString(row.status),
    source: asString(row.source),
    isCurrent: asBoolean(row.is_current, asBoolean(row.isCurrent)),
    year: asMaybeNumber(row.year),
    matchCount: asMaybeNumber(row.match_count ?? row.matchCount),
    settledMatchCount: asMaybeNumber(row.settled_match_count ?? row.settledMatchCount),
    openMatchCount: asMaybeNumber(row.open_match_count ?? row.openMatchCount),
    isFullySettled: asBoolean(row.is_fully_settled, asBoolean(row.isFullySettled)),
    hasSettlement: asBoolean(row.has_settlement, asBoolean(row.hasSettlement)),
    lastSeenAt: asString(row.last_seen_at, asString(row.lastSeenAt)),
    issueCloseTs: asString(row.issue_close_ts, asString(row.issueCloseTs)),
  };
}

function isSettlementIssue(issue: IssueOption): boolean {
  return Boolean(issue.hasSettlement && issue.isFullySettled && (issue.matchCount ?? 0) > 0);
}

function chooseSettlementIssueId(issues: IssueOption[], preferredIssueId: string): string {
  const reviewable = issues.filter(isSettlementIssue);
  if (reviewable.some((issue) => issue.issueId === preferredIssueId)) return preferredIssueId;
  return reviewable[0]?.issueId ?? preferredIssueId;
}

function withDecisionVariant(path: string, decisionVariantId?: string): string {
  if (!decisionVariantId) return path;
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}decision_variant=${encodeURIComponent(decisionVariantId)}`;
}

function withArtifactVariant(path: string, decisionVariantId?: string): string {
  if (!decisionVariantId) return path;
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}variant=${encodeURIComponent(decisionVariantId)}`;
}

function transformMatchRow(raw: unknown): IssueMatchRow {
  const row = asObject(raw) as ApiMatchSummary;
  const matchId = asString(row.match_id);
  const modelQScore = typeof row.q_max === 'number' ? row.q_max : row.q_score;
  const selectionCodes = asArray(row.selection_codes)
    .map((value) => asString(value))
    .filter((value) => value === '3' || value === '1' || value === '0');
  const llmCodes = asArray(row.llm_selection_codes)
    .map((value) => asString(value))
    .filter((value) => value === '3' || value === '1' || value === '0');
  const modelSelectionCodes = asArray(row.model_selection_codes)
    .map((value) => asString(value))
    .filter((value) => value === '3' || value === '1' || value === '0');
  const fallbackModelCodes = modelSelectionCodes.length ? modelSelectionCodes : row.model_selection === '3' || row.model_selection === '1' || row.model_selection === '0' ? [row.model_selection] : [];
  const selectedCodes = selectionCodes.length ? selectionCodes : row.selection === '3' || row.selection === '1' || row.selection === '0' ? [row.selection] : [];
  const fallbackLlmCodes = llmCodes.length ? llmCodes : row.llm_selection === '3' || row.llm_selection === '1' || row.llm_selection === '0' ? [row.llm_selection] : [];
  const llmAvailable = asString(row.llm_source, 'none') !== 'none' && asString(row.llm_source, 'none') !== 'api';
  const recommendedCodes = llmAvailable ? fallbackLlmCodes : selectedCodes;
  const modelCodes = fallbackModelCodes.length ? fallbackModelCodes : selectedCodes;
  const hasRecommendedSelection = recommendedCodes.length > 0;
  const recommendedLabels = recommendedCodes.map(selectionLabel);
  const qScore = typeof row.llm_q_score === 'number' ? row.llm_q_score : modelQScore;
  const confidence = typeof row.llm_probability === 'number' ? row.llm_probability : row.confidence_weight;
  const resultCode = asString(row.result_code);
	  const resultLabel = asString(row.result_label, selectionLabel(resultCode));
	  const status = asString(row.status, row.winning_sp !== undefined || resultCode ? 'settled' : 'open') === 'settled' ? 'settled' : 'open';
	  const postmatchReviewTags = asArray(row.postmatch_review_tags).map((value) => asString(value)).filter(Boolean);
	  const postmatchReviewOutcome = asString(row.postmatch_review_outcome);
	  const postmatchReviewSummary = asString(row.postmatch_review_summary);
	  const decisionVariants = asArray(row.decision_variants).map(transformDecisionVariant);
	  const selectedDecisionVariantRaw = asObject(row.selected_decision_variant ?? row.selectedDecisionVariant);
	  const selectedDecisionVariant = Object.keys(selectedDecisionVariantRaw).length ? transformDecisionVariant(selectedDecisionVariantRaw) : undefined;
	  const drift = {
    win: typeof row.sp_drift_3 === 'number' ? row.sp_drift_3 : undefined,
    draw: typeof row.sp_drift_1 === 'number' ? row.sp_drift_1 : undefined,
    loss: typeof row.sp_drift_0 === 'number' ? row.sp_drift_0 : undefined,
    direction: asString(row.sp_drift_band, 'spec payload'),
  };
  return {
    matchId,
    matchIdx: asMaybeNumber(row.match_idx ?? row.matchIdx),
    league: asString(row.league, ''),
    kickoffDate: asString(row.kickoff_date, formatDate(row.kickoff_ts)),
    kickoffTime: formatClock(row.kickoff_ts),
    home: asString(row.home, ''),
    away: asString(row.away, ''),
    handicap: asNumber(row.handicap_line),
    score: asString(row.score),
    halftimeScore: asString(row.halftime_score),
    scoreStatus: asString(row.live_score_status),
    scoreStatusText: asString(row.live_score_status_text),
    sp: { win: row.sp_3, draw: row.sp_1, loss: row.sp_0 },
    euro: { home: row.eu_home, draw: row.eu_draw, away: row.eu_away },
    asia: { line: row.ah_line ?? undefined, homeOdds: row.ah_home, awayOdds: row.ah_away },
    lineGap: asMaybeNumber(row.line_gap),
    drift,
    scrapeStatus: toScrapeStatus(row.capture_status),
    qScore,
    confidence,
    modelProb: toProb(row.model_p_3, row.model_p_1, row.model_p_0),
    modelEdgeBestOutcome: modelCodes.length ? modelCodes.map(selectionLabel).join('+') : 'no algorithmic signal',
    modelRecommendedOutcome: modelCodes.length ? modelCodes.map(selectionLabel).join('+') : '待预测',
    recommendedOutcome: hasRecommendedSelection ? recommendedLabels.join('+') : llmAvailable ? '不买' : '待预测',
    primaryBetOutcome: recommendedLabels[0],
    protectionOutcomes: recommendedLabels.slice(1),
	    recommendedCoverage: hasRecommendedSelection ? toCoverage(llmAvailable ? row.llm_selection_type : row.selection_type) : 'no-buy',
	    stopFlag: asBoolean(row.llm_stop_flag, asBoolean(row.stop_flag)),
	    recommendationSource: llmAvailable ? 'LLM' : '模型',
	    recommendationConfidenceLabel: llmAvailable ? asString(row.llm_confidence_label, typeof row.llm_confidence === 'number' ? row.llm_confidence.toFixed(2) : '') : undefined,
	    decisionVariants,
    selectedDecisionVariantId: asString(row.selected_decision_variant_id, asString(row.selectedDecisionVariantId)) || undefined,
    selectedDecisionVariantStatus: asString(row.selected_decision_variant_status, asString(row.selectedDecisionVariantStatus)) || undefined,
    selectedDecisionVariant,
	    candidateRole: toCandidateRole(row.candidate_role, qScore),
    resultCode,
    resultLabel,
    predictionHit: row.llm_prediction_hit ?? row.prediction_hit,
    settlementSp: row.winning_sp,
    qInputSpSnapshotAt: formatDateTimeShort(row.q_input_sp_snapshot_ts),
    qInputProbabilitySnapshotAt: formatDateTimeShort(row.q_input_probability_snapshot_ts),
    qCalculatedAt: formatDateTimeShort(row.q_calculated_ts),
    decisionSnapshotId: asString(row.decision_snapshot_id) || undefined,
    decisionSnapshotStatus: asString(row.decision_snapshot_status) || undefined,
	    decisionSnapshotGeneratedAt: formatDateTimeShort(row.decision_snapshot_generated_at),
	    decisionSnapshotCheckedAt: formatDateTimeShort(row.decision_snapshot_checked_at),
	    draftDecisionSnapshotId: asString(row.draft_decision_snapshot_id) || undefined,
	    postmatchReviewOutcome: postmatchReviewOutcome || undefined,
	    postmatchReviewSummary: postmatchReviewSummary || undefined,
	    postmatchReviewTags,
	    postmatchReviewAction: asString(row.postmatch_review_action) || undefined,
	    postmatchReviewProfit: asMaybeNumber(row.postmatch_review_profit),
	    postmatchReviewReviewedAt: formatDateTimeShort(row.postmatch_review_reviewed_at),
	    status,
	    llmAssistSummary: status === 'settled' ? (postmatchReviewSummary || `赛果 ${resultLabel || '缺'}，预测${row.prediction_hit === true ? '命中' : row.prediction_hit === false ? '未命中' : '未评估'}。`) : '真实数据源转换：500.com SQLite / canonical API payload.',
    riskTags: [row.sp_drift_band ? `drift:${row.sp_drift_band}` : '', row.line_gap !== undefined ? `line_gap:${row.line_gap}` : ''].filter(Boolean),
    updatedAt: formatClock(row.generated_ts),
  };
}

function transformIssueDashboard(raw: unknown): IssueDashboardData {
  const obj = asObject(raw);
  const stats = asObject(obj.stats);
  const matches = asArray(obj.matches).map(transformMatchRow);
  const decisionVariantOptions = asArray(obj.decision_variant_options ?? obj.decisionVariantOptions).map(transformDecisionVariantOption);
  const strategyVersionContext = transformStrategyVersionContext(obj.strategy_version_context ?? obj.strategyVersionContext);
  const decisionArtifactStatus = Object.keys(asObject(obj.decision_artifact_status ?? obj.decisionArtifactStatus)).length
    ? transformDecisionArtifactStatus(obj.decision_artifact_status ?? obj.decisionArtifactStatus)
    : undefined;
  const qualityFlag = asString(stats.pool_quality_flag, 'yellow') as 'green' | 'yellow' | 'red';
  return {
    issueId: asString(obj.issue),
    issueDate: asString(obj.issue_date, ''),
    salesDeadline: asString(obj.sales_deadline, ''),
    matchCount: asNumber(stats.n_matches, matches.length),
    candidateCount: asNumber(stats.qualified_matches, matches.length),
    qualifiedCandidateCount: asNumber(stats.qualified_matches, 0),
    dataCompleteRate: asString(obj.capture_status, 'complete') === 'complete' ? 1 : asString(obj.capture_status) === 'partial' ? 0.5 : 0,
    lastScrapedAt: asString(obj.last_snapshot_ts, ''),
    settlementStatus: asString(obj.status, 'open') === 'settled' ? 'settled' : 'open',
    recommendedAction: matches.length > 0 ? 'build-ticket' : 'watch',
    funnel: [
      { label: '全部比赛', count: asNumber(stats.n_matches, matches.length) },
      { label: 'qualified legs', count: asNumber(stats.qualified_legs, 0) },
    ],
	    quality: { grade: qualityFlag === 'green' ? 'A' : qualityFlag === 'red' ? 'C' : 'B', risks: [], score: Math.round(asNumber(stats.q_avg, 0) * 100), poolQualityFlag: qualityFlag },
	    matches,
	    decisionVariantOptions,
    strategyVersionContext,
    decisionArtifactStatus,
	    llmAssistSummary: 'Canonical /api/issues/:issue/dashboard payload transformed from snake_case by ApiDashboardAdapter.',
	  };
	}

function transformMatchDetail(raw: unknown): MatchDetailData {
  const obj = asObject(raw);
  const match = asObject(obj.match) as ApiMatchSummary;
  const prediction = asObject(obj.prediction) as ApiPrediction;
  const analysis500 = transformAnalysis500(obj.analysis_500);
	  const intelligence = transformIntelligence(obj.intelligence);
	  const decisionSnapshot = transformDecisionSnapshot(obj.decision_snapshot);
	  const draftDecisionSnapshot = transformDecisionSnapshot(obj.draft_decision_snapshot);
	  const postmatchReview = transformPostmatchReview(obj.postmatch_review);
	  const decisionVariants = asArray(obj.decision_variants ?? match.decision_variants).map(transformDecisionVariant);
	  const decisionVariantOptions = asArray(obj.decision_variant_options ?? obj.decisionVariantOptions).map(transformDecisionVariantOption);
	  const strategyVersionContext = transformStrategyVersionContext(obj.strategy_version_context ?? obj.strategyVersionContext);
	  const strategyArms = asArray(prediction.strategy_arms);
  const activeArm = asObject(strategyArms.find((arm) => asBoolean(asObject(arm).active)) ?? strategyArms[0]);
  const modelSelectedOutcome = activeArm.selection ?? prediction.selection ?? 'pass';
  const selectedCodes = asArray(activeArm.selection_codes ?? prediction.selection_codes)
    .map((value) => asString(value))
    .filter((value) => value === '3' || value === '1' || value === '0');
  const explicitLlmCodes = asArray(prediction.llm_selection_codes)
    .map((value) => asString(value))
    .filter((value) => value === '3' || value === '1' || value === '0');
  const fallbackLlmCode = prediction.llm_selection === '3' || prediction.llm_selection === '1' || prediction.llm_selection === '0'
    ? prediction.llm_selection
    : prediction.llm_judgment === '3' || prediction.llm_judgment === '1' || prediction.llm_judgment === '0'
      ? prediction.llm_judgment
      : '';
  const llmCodes = explicitLlmCodes.length ? explicitLlmCodes : fallbackLlmCode ? [fallbackLlmCode] : [];
  const llmSelectedOutcomes = llmCodes.map(selectionLabel);
  const selectionType = activeArm.selection_type;
  const probability = toProb(prediction.model_p_3, prediction.model_p_1, prediction.model_p_0);
  const impliedProbability = toProb(prediction.market_p_3, prediction.market_p_1, prediction.market_p_0);
  const resultCode = asString(match.result_code);
  const llmSource = asString(prediction.llm_source, 'none');
  const llmAvailable = llmSource !== 'none' && llmSource !== 'api';
  const llmJudgment = asString(prediction.llm_judgment, asString(modelSelectedOutcome));
  const llmSupport = asArray(prediction.llm_support).map((value) => asString(value)).filter(Boolean);
  const llmRisks = asArray(prediction.llm_risks).map((value) => asString(value)).filter(Boolean);
  const llmChain = asArray(prediction.llm_decision_chain).map((value) => asString(value)).filter(Boolean);
  const llmConfidenceLabel = asString(prediction.llm_confidence_label, llmAvailable ? `${asNumber(prediction.llm_confidence).toFixed(2)}` : '未接入');
  const llmGeneratedAt = decisionSnapshot?.generatedAt || formatClock(prediction.generated_ts);
  const status = asString(match.status, match.winning_sp !== undefined || resultCode ? 'settled' : 'open') === 'settled' ? 'settled' : 'open';
  return {
    matchId: asString(match.match_id),
    issueId: asString(match.issue),
    league: asString(match.league),
    home: asString(match.home),
    away: asString(match.away),
    kickoffTime: formatClock(match.kickoff_ts),
    salesDeadline: asString(match.sales_deadline, ''),
    handicap: asNumber(match.handicap_line),
    score: asString(match.score),
    halftimeScore: asString(match.halftime_score),
    scoreStatus: asString(match.live_score_status),
    scoreStatusText: asString(match.live_score_status_text),
    resultLabel: asString(match.result_label, selectionLabel(resultCode)),
    predictionHit: asNullableBoolean(match.prediction_hit),
    settlementSp: asMaybeNumber(match.winning_sp),
    status,
    sp: { win: match.sp_3, draw: match.sp_1, loss: match.sp_0 },
    euro: { home: match.eu_home, draw: match.eu_draw, away: match.eu_away },
    asia: { line: match.ah_line ?? undefined, homeOdds: match.ah_home, awayOdds: match.ah_away },
    lineGap: asMaybeNumber(match.line_gap),
    scrapeStatus: toScrapeStatus(match.capture_status),
    resultStatus: asString(match.status, 'open'),
    modelVersion: asString(prediction.model_version, 'canonical-api'),
    probabilityCalibratedAt: formatClock(prediction.generated_ts),
    qInputSpSnapshotAt: formatDateTimeShort(prediction.q_input_sp_snapshot_ts),
    qInputProbabilitySnapshotAt: formatDateTimeShort(prediction.q_input_probability_snapshot_ts),
    qCalculatedAt: formatDateTimeShort(prediction.q_calculated_ts ?? prediction.calculated_ts),
	    qInputPolicy: asString(prediction.q_input_policy),
	    decisionSnapshot,
	    draftDecisionSnapshot,
	    postmatchReview,
	    decisionVariants,
	    decisionVariantOptions,
    strategyVersionContext,
	    selectedOutcomes: modelSelectedOutcome === 'pass' ? [] : selectedCodes.length ? selectedCodes.map(selectionLabel) : [selectionLabel(modelSelectedOutcome)],
    recommendedAction: modelSelectedOutcome === 'pass' ? 'no-buy' : 'buy',
    recommendedCoverage: toCoverage(selectionType),
    buyExplanation: asString(prediction.llm_explanation, 'Canonical API payload.'),
    protectExplanation: 'Protection decision is computed downstream from ticket coverage and drift.',
    oddsTimeline: [{ at: formatClock(match.sp_snapshot_ts ?? prediction.generated_ts ?? match.kickoff_ts), sp: `${match.sp_3 ?? '-'} / ${match.sp_1 ?? '-'} / ${match.sp_0 ?? '-'}`, lineGap: asNumber(match.line_gap), drift: asString(match.sp_drift_band, 'api') }],
    oddsConsensus: transformOddsConsensus(match.odds_consensus),
    marketHighlights: asArray<string>(match.market_highlights),
    llm: {
      summaryId: asString(prediction.summary_id, 'api'),
      model: asString(prediction.llm_model, 'gpt-fixed-chain-v1'),
      generatedAt: llmGeneratedAt,
      direction: llmAvailable ? selectionLabel(llmJudgment) : '待决策',
      confidenceLabel: llmConfidenceLabel,
      injury: '',
      schedule: '',
      motivation: '',
      support: llmAvailable ? (llmSupport.length ? llmSupport : [asString(prediction.llm_explanation, '')].filter(Boolean)) : [],
      risks: llmAvailable ? llmRisks : [],
      source: llmSource,
    },
    llmSelectedOutcomes,
    llmPrimaryOutcome: llmSelectedOutcomes[0],
    llmProtectionOutcomes: llmSelectedOutcomes.slice(1),
    llmStopped: llmAvailable && llmSelectedOutcomes.length === 0,
    llmDecisionChain: llmChain,
    probability,
    impliedProbability,
    edge: toProb(
      (prediction.model_p_3 ?? 0) - (prediction.market_p_3 ?? 0),
      (prediction.model_p_1 ?? 0) - (prediction.market_p_1 ?? 0),
      (prediction.model_p_0 ?? 0) - (prediction.market_p_0 ?? 0),
    ),
    qScore: asNumber(prediction.q_score),
    confidence: asNumber(prediction.confidence_weight),
    analysis500,
    intelligence,
  };
}

function transformTicket(raw: unknown): TicketData {
  const obj = asObject(raw);
  const ticket = asObject(asArray(obj.tickets)[0]);
  const ticketId = asString(ticket.candidate_id, asString(ticket.ticket_id, 'draft'));
  const legs = asArray(ticket.legs).map((legRaw, index) => {
    const leg = asObject(legRaw);
    const selectionCodes = asArray(leg.selection_codes)
      .map((value) => asString(value))
      .filter((value) => value === '3' || value === '1' || value === '0');
    return {
      legId: asString(leg.leg_id, `L${index + 1}`),
      matchId: asString(leg.match_id),
      label: `${asString(leg.home)} vs ${asString(leg.away)}`,
      handicap: asNumber(leg.handicap),
      selectedOutcomes: selectionCodes.length ? selectionCodes.map(selectionLabel) : [selectionLabel(leg.selection)],
      coverageType: toCoverage(leg.cover_type),
      spSelected: String(leg.sp ?? ''),
      modelProbSelected: String(leg.llm_confidence ?? ''),
      qScore: asNumber(leg.llm_q_score, asNumber(leg.q_score)),
      confidence: asNumber(leg.llm_confidence, asNumber(leg.confidence_weight)),
      role: 'watch' as CandidateRole,
      riskTags: asArray<string>(leg.risk_warnings).length > 0 ? asArray<string>(leg.risk_warnings) : asArray<string>(ticket.risk_warnings),
    };
  });
  const totalBudget = asNumber(ticket.stake_yuan);
  const expectedReturn = asNumber(ticket.expected_return_yuan);
  const coverageDetail = asObject(ticket.coverage_detail);
  const totalCombinations = Math.max(1, 3 ** asNumber(coverageDetail.n_full) * 2 ** asNumber(coverageDetail.n_double));
  return {
    ticketId,
    issueId: asString(obj.issue),
    ticketName: asString(obj.plan_id, ticketId),
    status: 'draft',
    allocatorArm: 'canonical-api',
    budgetTier: 'api',
    totalBudget,
    usedBudget: totalBudget,
    baseStake: 2,
    multiplier: 'api',
    totalCombinations,
    expectedReturn,
    expectedRoi: asNumber(ticket.pred_ev_per_stake),
    maxPayout: asNumber(ticket.expected_payout),
    worstCaseLoss: -totalBudget,
    riskScore: 'api',
    concentrationScore: 0,
    protectionDepth: 0,
    spDriftSensitivity: 'api',
    legs,
  };
}

function transformLiveSignals(raw: unknown): LiveSignalsData {
  const obj = asObject(raw);
  const signals = asArray(obj.signals);
  return {
    issueId: asString(obj.issue),
    timeToDeadline: '',
    lastGlobalScrapeAt: formatClock(obj.generated_ts),
    nextScrapeAt: '',
    sourceHealthScore: 1,
    staleSourceCount: 0,
    failedSourceCount: 0,
    sources: [{ sourceName: 'canonical-api', status: 'ok', lastSuccessAt: formatClock(obj.generated_ts), latencySeconds: 0, recordCount: signals.length }],
    alerts: signals.flatMap((signalRaw) => {
      const signal = asObject(signalRaw);
      return asArray(signal.qualified_options).map((optionRaw, index) => {
        const option = asObject(optionRaw);
        return {
          alertId: `${asString(signal.match_id)}-${index + 1}`,
          matchId: asString(signal.match_id),
          alertType: 'model_changed' as const,
          severity: 'medium' as const,
          beforeValue: '',
          afterValue: selectionLabel(option.selection),
          threshold: asString(option.sp_drift_band, ''),
          detectedAt: formatClock(obj.generated_ts),
          affectedTicketIds: asArray<string>(option.arms_recommending),
          recommendedAction: 'review',
        };
      });
    }),
    ticketImpacts: [],
  };
}


function emptySettlement(issueId: string): SettlementData {
  return {
    issueId,
    settledAt: '',
    ticketCount: 0,
    totalStake: 0,
    grossReturn: 0,
    netReturn: 0,
    roi: 0,
    candidatePoolQuality: 'Mixed',
    reviewStatus: 'review_draft',
    postmatchReviews: [],
    ticketResults: [],
    legReviews: [],
    poolQualityReason: 'Canonical settlement endpoint returned 404: issue is not settled yet.',
    errorTags: ['not_settled'],
  };
}

function transformSettlement(raw: unknown): SettlementData {
  const obj = asObject(raw);
  const summaryObj = asObject(obj.postmatch_review_issue_summary ?? obj.postmatchSummary);
  const decisionVariantOptions = asArray(obj.decision_variant_options ?? obj.decisionVariantOptions).map(transformDecisionVariantOption);
  const strategyVersionContext = transformStrategyVersionContext(obj.strategy_version_context ?? obj.strategyVersionContext);
  const hasSummary = Object.keys(summaryObj).length > 0;
  const postmatchSummary = hasSummary ? {
    reviewVersion: asString(summaryObj.review_version, asString(summaryObj.reviewVersion)),
    reviewedAt: formatDateTimeShort(summaryObj.reviewed_at ?? summaryObj.reviewedAt),
    reviewCount: asNumber(summaryObj.n_reviews, asNumber(summaryObj.reviewCount)),
    stake: asNumber(summaryObj.stake),
    grossReturn: asNumber(summaryObj.gross_return, asNumber(summaryObj.grossReturn)),
    profit: asNumber(summaryObj.profit),
    roi: asNumber(summaryObj.roi),
    primaryHits: asNumber(summaryObj.primary_hits, asNumber(summaryObj.primaryHits)),
    protectHits: asNumber(summaryObj.protect_hits, asNumber(summaryObj.protectHits)),
    coverageHits: asNumber(summaryObj.coverage_hits, asNumber(summaryObj.coverageHits)),
    stoppedCorrect: asNumber(summaryObj.stopped_correct, asNumber(summaryObj.stoppedCorrect)),
    stoppedWrong: asNumber(summaryObj.stopped_wrong, asNumber(summaryObj.stoppedWrong)),
    tagCounts: asNumberRecord(summaryObj.tag_counts ?? summaryObj.tagCounts),
  } : undefined;
  const postmatchReviews = asArray(obj.postmatch_reviews ?? obj.postmatchReviews).map((reviewRaw) => {
    const review = asObject(reviewRaw);
    const selectedCodes = asArray(review.llm_selection_codes ?? review.selection_codes).map((value) => asString(value)).filter(Boolean);
    return {
      matchIdx: asNumber(review.match_idx, asNumber(review.matchIdx)),
      matchId: asString(review.match_id, asString(review.matchId)),
      league: asString(review.league),
      home: asString(review.home),
      away: asString(review.away),
      kickoffTime: formatClock(review.kickoff_ts ?? review.kickoffTime),
      score: asString(review.score),
      halftimeScore: asString(review.halftime_score, asString(review.halftimeScore)),
      resultLabel: asString(review.result_label, selectionLabel(review.result_code)),
      winningSp: asMaybeNumber(review.winning_sp ?? review.winningSp),
      selectedOutcomes: selectedCodes.map(selectionLabel),
      llmJudgment: asString(review.llm_judgment, asString(review.llmJudgment)),
      outcomeLabel: asString(review.outcome_label, asString(review.outcomeLabel)),
      primaryHit: asBoolean(review.primary_hit, asBoolean(review.primaryHit)),
      protectHit: asBoolean(review.protect_hit, asBoolean(review.protectHit)),
      coverageHit: asBoolean(review.coverage_hit, asBoolean(review.coverageHit)),
      stopped: asBoolean(review.stopped),
      stake: asNumber(review.stake),
      grossReturn: asNumber(review.gross_return, asNumber(review.grossReturn)),
      profit: asNumber(review.profit),
      roi: asNumber(review.roi),
      tags: asArray(review.tags ?? review.failure_tags).map((value) => asString(value)).filter(Boolean),
      summary: asString(review.review_summary, asString(review.summary)),
      actionSuggestion: asString(review.action_suggestion, asString(review.actionSuggestion)),
      reviewedAt: formatDateTimeShort(review.reviewed_at ?? review.reviewedAt),
    };
  });
  const tagCounts = postmatchSummary?.tagCounts ?? {};
  const totalStake = postmatchSummary?.stake ?? asNumber(obj.total_stake);
  const grossReturn = postmatchSummary?.grossReturn ?? asNumber(obj.total_payout);
  const netReturn = postmatchSummary?.profit ?? asNumber(obj.pnl);
  const roi = postmatchSummary?.roi ?? asNumber(obj.roi);
  return {
    issueId: asString(obj.issue),
    settledAt: asString(obj.settled_ts),
    decisionVariantOptions,
    strategyVersionContext,
    ticketCount: postmatchSummary?.reviewCount ?? asNumber(obj.n_tickets),
    totalStake,
    grossReturn,
    netReturn,
    roi,
    candidatePoolQuality: 'Good',
    reviewStatus: 'review_draft',
    postmatchSummary,
    postmatchReviews,
    ticketResults: [{ ticketId: 'summary', ticketType: postmatchSummary ? 'postmatch_review_issue_summary' : 'aggregate', legCount: postmatchSummary?.reviewCount ?? asNumber(obj.n_legs_total), hitLegs: postmatchSummary?.coverageHits ?? asNumber(obj.n_legs_hit), missedByLegs: tagCounts.uncovered_result ?? asNumber(obj.n_legs_missed_by_1), missedProtection: tagCounts.uncovered_high_prob_alt ?? asNumber(obj.protection_missed_loss), stake: totalStake, payout: grossReturn, conclusion: asString(obj.quality_review, postmatchSummary ? 'postmatch review issue summary' : 'canonical settlement summary') }],
    legReviews: asArray(obj.per_match_settlements).map((settlementRaw) => {
      const settlement = asObject(settlementRaw);
      const armHits = asObject(settlement.arm_hits);
      const selectedArms = asArray<string>(settlement.selected_by_arms);
      const hit = selectedArms.length > 0 ? selectedArms.some((armId) => asBoolean(armHits[armId])) : false;
      return {
        matchId: asString(settlement.match_id),
        selectedOutcomes: [],
        actualResult: selectionLabel(settlement.result_code),
        hit,
        coverageType: 'single' as CoverageType,
        spAtBuild: '',
        spAtSettlement: String(settlement.winning_sp ?? ''),
        spDrift: String(settlement.sp_drift ?? ''),
        qScoreAtBuild: 0,
        confidenceAtBuild: 0,
        llmRiskTagsAtBuild: [],
        protectionRecommended: false,
        protectionTaken: false,
        missedProtection: false,
        tags: selectedArms.map((armId) => `arm:${armId}`),
      };
    }),
    poolQualityReason: asString(obj.quality_review),
    errorTags: Object.keys(tagCounts),
  };
}

function transformStrategyLab(raw: unknown): StrategyLabData {
  const obj = asObject(raw);
  const strategies = asArray(obj.strategies).map(asObject);
  return {
    arms: strategies.flatMap((strategy) => asArray(strategy.arms).map((armRaw) => {
      const arm = asObject(armRaw);
      return {
        armId: asString(arm.arm_id),
        armName: asString(arm.arm_name),
        active: asBoolean(arm.active),
        roi: asNumber(arm.roi),
        profit: asNumber(arm.profit),
        hitRate: asNumber(arm.hit_rate),
        maxDrawdown: asNumber(arm.max_dd),
        equityCurve: asArray<number>(arm.equity_curve).filter((value): value is number => typeof value === 'number'),
        recentRoi: asNumber(arm.recent_roi, asNumber(arm.roi)),
        description: asString(arm.description),
      };
    })),
    annualPerformance: strategies.flatMap((strategy) => asArray(strategy.annual_performance).map((yearRaw) => {
      const year = asObject(yearRaw);
      const profit = asNumber(year.profit);
      const stake = asNumber(year.stake);
      return {
        armId: asString(year.arm_id, asString(strategy.strategy_id, 'combined')),
        year: asNumber(year.year),
        issueCount: asNumber(year.n_issues),
        ticketCount: asNumber(year.tickets),
        totalStake: stake,
        grossReturn: stake + profit,
        netReturn: profit,
        roi: asNumber(year.roi),
        maxDrawdown: asNumber(year.max_dd),
        hitTicketRate: asNumber(year.hit_rate),
      };
    })),
    failureClusters: [],
    guardrail: strategies.map((strategy) => asString(strategy.strategy_name)).filter(Boolean).join(' / ') || 'Canonical /api/strategies/lab payload.',
  };
}

function transformSelectorShadow(raw: unknown): SelectorShadowData {
  const obj = asObject(raw);
  if (!obj.rule_name && !obj.ruleName) throw new Error('selector-shadow payload missing rule_name');
  const current = asObject(obj.current_decision ?? obj.currentDecision);
  return {
    issueId: asString(obj.issue, asString(obj.issueId)),
    ruleName: asString(obj.rule_name, asString(obj.ruleName)),
    mode: asString(obj.mode, 'live-shadow') as SelectorShadowData['mode'],
    generatedAt: asString(obj.generated_at, asString(obj.generatedAt, '')),
    currentDecision: {
      chosenArm: asString(current.chosen_arm, asString(current.chosenArm, '')),
      baselineArm: asString(current.baseline_arm, asString(current.baselineArm, '')),
      defensiveArm: asString(current.defensive_arm, asString(current.defensiveArm, '')),
      stateSignal: asBoolean(current.state_signal, asBoolean(current.stateSignal)),
      qualitySignal: asBoolean(current.quality_signal, asBoolean(current.qualitySignal)),
      reason: asString(current.reason),
      preLossStreak: asNumber(current.pre_loss_streak, asNumber(current.preLossStreak)),
      preDrawdownUnits: asNumber(current.pre_drawdown_units, asNumber(current.preDrawdownUnits)),
      weakCount: asNumber(current.weak_count, asNumber(current.weakCount)),
      weakScore: asNumber(current.weak_score, asNumber(current.weakScore)),
      qualityHistoryIssues: asNumber(current.quality_history_issues, asNumber(current.qualityHistoryIssues)),
      budgetUnits: asNumber(current.budget_units, asNumber(current.budgetUnits, 384)),
    },
    featureFlags: asArray(obj.feature_flags ?? obj.featureFlags).map((flagRaw) => {
      const flag = asObject(flagRaw);
      return {
        feature: asString(flag.feature),
        value: typeof flag.value === 'number' ? flag.value : asString(flag.value),
        threshold: typeof flag.threshold === 'number' ? flag.threshold : asString(flag.threshold),
        weak: asBoolean(flag.weak),
        severity: asNumber(flag.severity),
      };
    }),
    arms: asArray(obj.arms).map((armRaw) => {
      const arm = asObject(armRaw);
      return {
        armId: asString(arm.arm_id, asString(arm.armId)),
        label: asString(arm.label),
        role: asString(arm.role, 'selector') as SelectorShadowData['arms'][number]['role'],
        profitPer256: asNumber(arm.profit_per_256, asNumber(arm.profitPer256)),
        roi: asNumber(arm.roi),
        maxDrawdownUnits: asNumber(arm.max_drawdown_units, asNumber(arm.maxDrawdownUnits)),
        maxLossStreak: asNumber(arm.max_loss_streak, asNumber(arm.maxLossStreak)),
        issueWinRate: asNumber(arm.issue_win_rate, asNumber(arm.issueWinRate)),
        fullLossRate: asNumber(arm.full_loss_rate, asNumber(arm.fullLossRate)),
        recentProfitPer256: asNumber(arm.recent_profit_per_256, asNumber(arm.recentProfitPer256)),
        deltaProfitPer256VsBase: asNumber(arm.delta_profit_per_256_vs_base, asNumber(arm.deltaProfitPer256VsBase)),
        deltaMaxDrawdownUnitsVsBase: asNumber(arm.delta_max_drawdown_units_vs_base, asNumber(arm.deltaMaxDrawdownUnitsVsBase)),
        deltaLossStreakVsBase: asNumber(arm.delta_loss_streak_vs_base, asNumber(arm.deltaLossStreakVsBase)),
      };
    }),
    switchAttribution: asArray(obj.switch_attribution ?? obj.switchAttribution).map((groupRaw) => {
      const group = asObject(groupRaw);
      return {
        group: asString(group.group),
        count: asNumber(group.count, asNumber(group.n)),
        deltaVsBaseUnits: asNumber(group.delta_vs_base_units, asNumber(group.deltaVsBaseUnits)),
        helped: asNumber(group.helped, asNumber(group.helped_count)),
        hurt: asNumber(group.hurt, asNumber(group.hurt_count)),
        flat: asNumber(group.flat, asNumber(group.flat_count)),
      };
    }),
    rollingStability: asArray(obj.rolling_stability ?? obj.rollingStability).map((rowRaw) => {
      const row = asObject(rowRaw);
      return {
        window: asNumber(row.window),
        profitPositiveRate: asNumber(row.profit_positive_rate, asNumber(row.profitPositiveRate)),
        maxDrawdownPositiveRate: asNumber(row.max_drawdown_positive_rate, asNumber(row.maxDrawdownPositiveRate)),
        bothPositiveRate: asNumber(row.both_positive_rate, asNumber(row.bothPositiveRate)),
        avgProfitDelta: asNumber(row.avg_profit_delta, asNumber(row.avgProfitDelta)),
        avgMaxDrawdownDelta: asNumber(row.avg_maxdrawdown_delta, asNumber(row.avg_max_drawdown_delta, asNumber(row.avgMaxDrawdownDelta))),
        avgLossStreakDelta: asNumber(row.avg_loss_streak_delta, asNumber(row.avgLossStreakDelta)),
      };
    }),
    recentDecisions: asArray(obj.recent_decisions ?? obj.recentDecisions).map((decisionRaw) => {
      const decision = asObject(decisionRaw);
      return {
        issueId: asString(decision.issue, asString(decision.issueId)),
        year: asNumber(decision.year),
        chosenArm: asString(decision.chosen_arm, asString(decision.chosenArm)),
        reason: asString(decision.reason),
        deltaVsBaseUnits: asNumber(decision.delta_vs_base_units, asNumber(decision.deltaVsBaseUnits)),
        baseProfitUnits: asNumber(decision.base_profit_units, asNumber(decision.baseProfitUnits)),
        selectorProfitUnits: asNumber(decision.selector_profit_units, asNumber(decision.selectorProfitUnits)),
        weakCount: asNumber(decision.weak_count, asNumber(decision.weakCount)),
        preLossStreak: asNumber(decision.pre_loss_streak, asNumber(decision.preLossStreak)),
        preDrawdownUnits: asNumber(decision.pre_drawdown_units, asNumber(decision.preDrawdownUnits)),
        outcome: asString(decision.outcome, 'flat') as SelectorShadowData['recentDecisions'][number]['outcome'],
      };
    }),
    guardrail: asString(obj.guardrail),
  };
}

function transformMainStrategy(raw: unknown): MainStrategyData {
  const obj = asObject(raw);
  const evPool = asObject(obj.ev_pool ?? obj.evPool);
  const risk = asObject(obj.risk_state ?? obj.riskState);
  const cooldown = asObject(risk.cooldown);
  const budget = asObject(risk.budget);
  const diagnostics = asObject(obj.diagnostics);
  const review = asObject(obj.review);
  const source = asObject(obj.source);
  const decisionVariantOptions = asArray(obj.decision_variant_options ?? obj.decisionVariantOptions).map(transformDecisionVariantOption);
  const strategyVersionContext = transformStrategyVersionContext(obj.strategy_version_context ?? obj.strategyVersionContext);
  return {
    issueId: asString(obj.issue, asString(obj.issueId)),
    generatedAt: asString(obj.generated_ts, asString(obj.generatedAt)),
    mode: asString(obj.mode, 'live_monitoring') as MainStrategyData['mode'],
    strategyFamily: asString(obj.strategy_family, asString(obj.strategyFamily)),
    decisionVariantOptions,
    strategyVersionContext,
    candidates: asArray(obj.candidates).map((candidateRaw) => {
      const candidate = asObject(candidateRaw);
      return {
        armId: asString(candidate.arm_id, asString(candidate.armId)),
        label: asString(candidate.label),
        role: asString(candidate.role, 'stable') as MainStrategyData['candidates'][number]['role'],
        recommendedFor: asString(candidate.recommended_for, asString(candidate.recommendedFor)),
        issueBudget: asNumber(candidate.issue_budget, asNumber(candidate.issueBudget)),
        extraBudget: asNumber(candidate.extra_budget, asNumber(candidate.extraBudget)),
        stakeUnits: asNumber(candidate.stake_units, asNumber(candidate.stakeUnits)),
        profitUnits: asNumber(candidate.profit_units, asNumber(candidate.profitUnits)),
        profitPer256: asNumber(candidate.profit_per_256, asNumber(candidate.profitPer256)),
        roi: asNumber(candidate.roi),
        issueWinRate: asNumber(candidate.issue_win_rate, asNumber(candidate.issueWinRate)),
        nonFullLossRate: asNumber(candidate.non_full_loss_rate, asNumber(candidate.nonFullLossRate)),
        fullLossRate: asNumber(candidate.full_loss_rate, asNumber(candidate.fullLossRate)),
        maxDrawdownUnits: asNumber(candidate.max_drawdown_units, asNumber(candidate.maxDrawdownUnits)),
        maxDrawdownPer256: asNumber(candidate.max_drawdown_per_256, asNumber(candidate.maxDrawdownPer256)),
        maxLossStreak: asNumber(candidate.max_loss_streak, asNumber(candidate.maxLossStreak)),
        maxDeadStreak: asNumber(candidate.max_dead_streak, asNumber(candidate.maxDeadStreak)),
        recentProfitPer256: asNumber(candidate.recent_profit_per_256, asNumber(candidate.recentProfitPer256)),
        recentRoi: asNumber(candidate.recent_roi, asNumber(candidate.recentRoi)),
        allocation: asString(candidate.allocation),
        rationale: asString(candidate.rationale),
        riskTags: asArray<string>(candidate.risk_tags ?? candidate.riskTags),
      };
    }),
    annualPerformance: asArray(obj.annual_performance ?? obj.annualPerformance).map((yearRaw) => {
      const year = asObject(yearRaw);
      return {
        armId: asString(year.arm_id, asString(year.armId)),
        year: asNumber(year.year),
        issueCount: asNumber(year.n_issues, asNumber(year.issueCount)),
        stakeUnits: asNumber(year.stake_units, asNumber(year.stakeUnits)),
        profitUnits: asNumber(year.profit_units, asNumber(year.profitUnits)),
        roi: asNumber(year.roi),
        issueWinRate: asNumber(year.issue_win_rate, asNumber(year.issueWinRate)),
        nonFullLossRate: asNumber(year.non_full_loss_rate, asNumber(year.nonFullLossRate)),
        maxDrawdownUnits: asNumber(year.max_drawdown_units, asNumber(year.maxDrawdownUnits)),
      };
    }),
    evPool: {
      available: asBoolean(evPool.available),
      status: asString(evPool.status),
      source: asString(evPool.source),
      ticketCount: asNumber(evPool.ticket_count, asNumber(evPool.ticketCount)),
      tickets: asArray(evPool.tickets).map((ticketRaw) => {
        const ticket = asObject(ticketRaw);
        return {
          ticketId: asString(ticket.ticket_id, asString(ticket.ticketId)),
          ticketIdx: asNumber(ticket.ticket_idx, asNumber(ticket.ticketIdx)),
          sourceStrategy: asString(ticket.source_strategy, asString(ticket.sourceStrategy)),
          nLegs: asNumber(ticket.n_legs, asNumber(ticket.nLegs)),
          stakeUnits: asNumber(ticket.stake_units, asNumber(ticket.stakeUnits)),
          predEvPerStake: asNumber(ticket.pred_ev_per_stake, asNumber(ticket.predEvPerStake)),
          predHitProb: asNumber(ticket.pred_hit_prob, asNumber(ticket.predHitProb)),
          hit: asNullableBoolean(ticket.hit),
          payoutUnits: asNumber(ticket.payout_units, asNumber(ticket.payoutUnits)),
          profitUnits: asNumber(ticket.profit_units, asNumber(ticket.profitUnits)),
          topology: asString(ticket.topology),
          avgQScore: asNumber(ticket.avg_q_score, asNumber(ticket.avgQScore)),
          avgConfidenceWeight: asNumber(ticket.avg_confidence_weight, asNumber(ticket.avgConfidenceWeight)),
          lineGapSupportNet: asNumber(ticket.line_gap_support_net, asNumber(ticket.lineGapSupportNet)),
          avgAbsLineGap: asNumber(ticket.avg_abs_line_gap, asNumber(ticket.avgAbsLineGap)),
          diagnosticTags: asArray<string>(ticket.diagnostic_tags ?? ticket.diagnosticTags),
          legs: asArray(ticket.legs).map((legRaw) => {
            const leg = asObject(legRaw);
            return {
              legId: asString(leg.leg_id, asString(leg.legId)),
              matchId: asString(leg.match_id, asString(leg.matchId)),
              label: asString(leg.label),
              handicap: asMaybeNumber(leg.handicap),
              beidanHandicap: asMaybeNumber(leg.beidan_handicap ?? leg.beidanHandicap),
              asian1hLine: asMaybeNumber(leg.asian_1h_line ?? leg.asian1hLine),
              lineGap: asMaybeNumber(leg.line_gap ?? leg.lineGap),
              selectionCode: asString(leg.selection_code, asString(leg.selectionCode)),
              selectionLabel: asString(leg.selection_label, asString(leg.selectionLabel)),
              resultCode: asString(leg.result_code, asString(leg.resultCode)),
              resultLabel: asString(leg.result_label, asString(leg.resultLabel)),
              hit: asNullableBoolean(leg.hit),
              winningSp: asMaybeNumber(leg.winning_sp ?? leg.winningSp),
              qScore: asMaybeNumber(leg.q_score ?? leg.qScore),
              confidenceWeight: asMaybeNumber(leg.confidence_weight ?? leg.confidenceWeight),
              selectedModelP: asMaybeNumber(leg.selected_model_p ?? leg.selectedModelP),
              selectedMarketP: asMaybeNumber(leg.selected_market_p ?? leg.selectedMarketP),
              predSpMultiplier: asMaybeNumber(leg.pred_sp_multiplier ?? leg.predSpMultiplier),
              diagnosticTags: asArray<string>(leg.diagnostic_tags ?? leg.diagnosticTags),
            };
          }),
        };
      }),
    },
    liveProxy: obj.live_proxy === null || obj.liveProxy === null ? null : (() => {
      const live = asObject(obj.live_proxy ?? obj.liveProxy);
      return {
        available: asBoolean(live.available),
        status: asString(live.status),
        source: asString(live.source),
        ticketCount: asNumber(live.ticket_count, asNumber(live.ticketCount)),
        tickets: asArray(live.tickets),
      };
    })(),
    riskState: {
      latestBacktestIssue: asString(risk.latest_backtest_issue, asString(risk.latestBacktestIssue)),
      riskLevel: asString(risk.risk_level, 'normal') as MainStrategyData['riskState']['riskLevel'],
      recommendedArm: asString(risk.recommended_arm, asString(risk.recommendedArm)),
      reason: asString(risk.reason),
      cooldown: {
        state: asString(cooldown.state),
        policy: asString(cooldown.policy),
        preLossStreak: asNumber(cooldown.pre_loss_streak, asNumber(cooldown.preLossStreak)),
        preDrawdownUnits: asNumber(cooldown.pre_drawdown_units, asNumber(cooldown.preDrawdownUnits)),
      },
      budget: {
        mode: asString(budget.mode),
        selectedUnits: asNumber(budget.selected_units, asNumber(budget.selectedUnits)),
        baseUnits: asNumber(budget.base_units, asNumber(budget.baseUnits)),
        extraUnits: asNumber(budget.extra_units, asNumber(budget.extraUnits)),
        notes: asString(budget.notes),
      },
      guardrails: asArray<string>(risk.guardrails),
    },
    diagnostics: {
      lineGapPolicy: asString(diagnostics.line_gap_policy, asString(diagnostics.lineGapPolicy)),
      spDriftPolicy: asString(diagnostics.sp_drift_policy, asString(diagnostics.spDriftPolicy)),
      paperArms: asArray(diagnostics.paper_arms ?? diagnostics.paperArms).map((armRaw) => {
        const arm = asObject(armRaw);
        return {
          armId: asString(arm.arm_id, asString(arm.armId)),
          issues: asNumber(arm.issues),
          profitPer256: asNumber(arm.profit_per_256, asNumber(arm.profitPer256)),
          roi: asNumber(arm.roi),
          issueWinRate: asNumber(arm.issue_win_rate, asNumber(arm.issueWinRate)),
          nonFullLossRate: asNumber(arm.non_full_loss_rate, asNumber(arm.nonFullLossRate)),
          maxDrawdownUnits: asNumber(arm.max_drawdown_units, asNumber(arm.maxDrawdownUnits)),
          maxLossStreak: asNumber(arm.max_loss_streak, asNumber(arm.maxLossStreak)),
          productionStatus: asString(arm.production_status, asString(arm.productionStatus)),
        };
      }),
    },
    review: {
      issues: asArray(review.issues).map((issueRaw) => {
        const item = asObject(issueRaw);
        return {
          issueId: asString(item.issue, asString(item.issueId)),
          issueOrder: asNumber(item.issue_order, asNumber(item.issueOrder)),
          calendarYear: asNumber(item.calendar_year, asNumber(item.calendarYear)),
          issueCloseTs: asString(item.issue_close_ts, asString(item.issueCloseTs)),
          arms: asArray(item.arms).map((armRaw) => {
            const arm = asObject(armRaw);
            return {
              armId: asString(arm.arm_id, asString(arm.armId)),
              stakeUnits: asNumber(arm.stake_units, asNumber(arm.stakeUnits)),
              profitUnits: asNumber(arm.profit_units, asNumber(arm.profitUnits)),
              roi: asNumber(arm.roi),
              tickets: asNumber(arm.tickets),
              hits: asNumber(arm.hits),
              parts: asString(arm.parts),
              state: asString(arm.state),
              allocation: asString(arm.allocation),
            };
          }),
        };
      }),
      source: asString(review.source),
    },
    source: {
      mainStrategyDir: asString(source.main_strategy_dir, asString(source.mainStrategyDir)),
      ticketPoolDir: asString(source.ticket_pool_dir, asString(source.ticketPoolDir)),
      modelDb: asString(source.model_db, asString(source.modelDb)),
      liveDb: asString(source.live_db, asString(source.liveDb)),
      noFutureLeakage: asString(source.no_future_leakage, asString(source.noFutureLeakage)),
    },
  };
}

function transformOperationsStatus(raw: unknown): OperationsStatusData {
  const obj = asObject(raw);
  const summary = asObject(obj.summary);
  const domains = asObject(obj.domains);
  const runtimeDomain = asObject(domains.runtime);
  const collectionDomain = asObject(domains.collection);
  const artifactsDomain = asObject(domains.artifacts);
  const activeDecision = asObject(artifactsDomain.active_decision ?? artifactsDomain.activeDecision);
  const freezeDomain = asObject(domains.scheduled_freeze ?? domains.scheduledFreeze);
  const adhocDomain = asObject(domains.adhoc_service ?? domains.adhocService);
  const adhocRecent = asObject(adhocDomain.recent_request ?? adhocDomain.recentRequest);
  const settlementDomain = asObject(domains.settlement_review ?? domains.settlementReview);
  const issueStatus = asObject(obj.issue_status ?? obj.issueStatus);
  const runtime = asObject(obj.runtime);
  const snapshots = asObject(obj.snapshots);
  const review = asObject(obj.review);
  const reviewTask = asObject(review.task);
  const reviewTaskResult = asObject(reviewTask.result);
  const workflow = asObject(obj.workflow);
  const versions = asObject(obj.versions);
  const source = asObject(obj.source);
  const runtimeHealth = asObject(runtime.health);
  const runtimeDiagnostics = asObject(runtime.diagnostics);
  const runtimeUrls = asObject(runtime.urls ?? runtimeDiagnostics.urls);
  return {
    schemaVersion: asString(obj.schema_version, asString(obj.schemaVersion, 'operations_status_v1')),
    issueId: asString(obj.issue, asString(obj.issueId)),
    generatedAt: asString(obj.generated_at, asString(obj.generatedAt)),
    summary: {
      status: asString(summary.status, 'missing'),
      blockerCount: asNumber(summary.blocker_count, asNumber(summary.blockerCount)),
      warningCount: asNumber(summary.warning_count, asNumber(summary.warningCount)),
      nextActionAt: asString(summary.next_action_at, asString(summary.nextActionAt)),
      nextActionTitle: asString(summary.next_action_title, asString(summary.nextActionTitle)),
      message: asString(summary.message),
    },
    domains: {
      runtime: {
        status: asString(runtimeDomain.status, 'missing'),
        checkedAt: asString(runtimeDomain.checked_at, asString(runtimeDomain.checkedAt)),
        accessMode: asString(runtimeDomain.access_mode, asString(runtimeDomain.accessMode)),
        externalAccessConfigured: asBoolean(runtimeDomain.external_access_configured, asBoolean(runtimeDomain.externalAccessConfigured)),
        components: asArray(runtimeDomain.components).map((rawComponent) => {
          const component = asObject(rawComponent);
          return {
            componentId: asString(component.component_id, asString(component.componentId)),
            label: asString(component.label),
            status: asString(component.status, 'missing'),
            processStatus: asString(component.process_status, asString(component.processStatus)),
            checkedAt: asString(component.checked_at, asString(component.checkedAt)),
            lastSuccessAt: asString(component.last_success_at, asString(component.lastSuccessAt)),
            latencyMs: asMaybeNumber(component.latency_ms ?? component.latencyMs),
            httpStatus: asMaybeNumber(component.http_status ?? component.httpStatus),
            detail: asString(component.detail),
          };
        }),
      },
      collection: {
        status: asString(collectionDomain.status, 'missing'),
        planStatus: asString(collectionDomain.plan_status, asString(collectionDomain.planStatus)),
        planSchemaVersion: asString(collectionDomain.plan_schema_version, asString(collectionDomain.planSchemaVersion)),
        planRef: asString(collectionDomain.plan_ref, asString(collectionDomain.planRef)),
        planError: asString(collectionDomain.plan_error, asString(collectionDomain.planError)),
        collectors: asArray(collectionDomain.collectors).map((rawCollector) => {
          const collector = asObject(rawCollector);
          return {
            collectorId: asString(collector.collector_id, asString(collector.collectorId)),
            label: asString(collector.label),
            importance: asString(collector.importance),
            enabled: asBoolean(collector.enabled),
            ownerProcess: asString(collector.owner_process, asString(collector.ownerProcess)),
            processStatus: asString(collector.process_status, asString(collector.processStatus)),
            status: asString(collector.status, 'missing'),
            statusDetail: asString(collector.status_detail, asString(collector.statusDetail)),
            scheduleIntervalSec: asNumber(collector.schedule_interval_sec, asNumber(collector.scheduleIntervalSec)),
            staleAfterSec: asNumber(collector.stale_after_sec, asNumber(collector.staleAfterSec)),
            lastAttemptAt: asString(collector.last_attempt_at, asString(collector.lastAttemptAt)),
            lastSuccessAt: asString(collector.last_success_at, asString(collector.lastSuccessAt)),
            lastErrorAt: asString(collector.last_error_at, asString(collector.lastErrorAt)),
            nextDueAt: asString(collector.next_due_at, asString(collector.nextDueAt)),
            ageMinutes: asMaybeNumber(collector.age_minutes ?? collector.ageMinutes),
            coverageRate: asMaybeNumber(collector.coverage_rate ?? collector.coverageRate),
            coveredCount: asNumber(collector.covered_count, asNumber(collector.coveredCount)),
            expectedCount: asNumber(collector.expected_count, asNumber(collector.expectedCount)),
            missingCount: asNumber(collector.missing_count, asNumber(collector.missingCount)),
            missingMatchIds: asArray(collector.missing_match_ids ?? collector.missingMatchIds).map((value) => asString(value)).filter(Boolean),
            okCount: asNumber(collector.ok_count, asNumber(collector.okCount)),
            failCount: asNumber(collector.fail_count, asNumber(collector.failCount)),
            totalAttempts: asNumber(collector.total_attempts, asNumber(collector.totalAttempts)),
            rowsParsed: asNumber(collector.rows_parsed, asNumber(collector.rowsParsed)),
            error: asString(collector.error) || undefined,
            markets: asArray(collector.markets).map((value) => asString(value)).filter(Boolean),
            autoRecoveryExpected: asBoolean(collector.auto_recovery_expected, asBoolean(collector.autoRecoveryExpected)),
            retryCount: asMaybeNumber(collector.retry_count ?? collector.retryCount),
            maintenanceAction: asString(collector.maintenance_action, asString(collector.maintenanceAction)),
          };
        }),
      },
      artifacts: {
        status: asString(artifactsDomain.status, 'missing'),
        activeDecision: {
          status: asString(activeDecision.status, 'missing'),
          version: asString(activeDecision.version),
          configHash: asString(activeDecision.config_hash, asString(activeDecision.configHash)),
          generatedAt: asString(activeDecision.generated_at, asString(activeDecision.generatedAt)),
          inputAt: asString(activeDecision.input_at, asString(activeDecision.inputAt)),
          expectedCount: asNumber(activeDecision.expected_count, asNumber(activeDecision.expectedCount)),
          actualCount: asNumber(activeDecision.actual_count, asNumber(activeDecision.actualCount)),
          missingCount: asNumber(activeDecision.missing_count, asNumber(activeDecision.missingCount)),
          missingMatchIds: asArray(activeDecision.missing_match_ids ?? activeDecision.missingMatchIds).map((value) => asString(value)).filter(Boolean),
          detail: asString(activeDecision.detail),
        },
        draftCount: asNumber(artifactsDomain.draft_count, asNumber(artifactsDomain.draftCount)),
        draftMatchIds: asArray(artifactsDomain.draft_match_ids ?? artifactsDomain.draftMatchIds).map((value) => asString(value)).filter(Boolean),
        supersededCount: asNumber(artifactsDomain.superseded_count, asNumber(artifactsDomain.supersededCount)),
        scheduledResearchEvidenceEligible: asBoolean(artifactsDomain.scheduled_research_evidence_eligible, asBoolean(artifactsDomain.scheduledResearchEvidenceEligible)),
        adhocNamespaceUsed: asBoolean(artifactsDomain.adhoc_namespace_used, asBoolean(artifactsDomain.adhocNamespaceUsed)),
      },
      scheduledFreeze: {
        status: asString(freezeDomain.status, 'missing'),
        timelineContract: asString(freezeDomain.timeline_contract, asString(freezeDomain.timelineContract)),
        researchAndAdhocSeparated: asBoolean(freezeDomain.research_and_adhoc_separated, asBoolean(freezeDomain.researchAndAdhocSeparated)),
        nextDueAt: asString(freezeDomain.next_due_at, asString(freezeDomain.nextDueAt)),
        segments: asArray(freezeDomain.segments).map((rawSegment) => {
          const segment = asObject(rawSegment);
          const exactN = asObject(segment.exact_n ?? segment.exactN);
          const researchFreeze = asObject(segment.research_freeze ?? segment.researchFreeze);
          return {
            segmentIdx: asNumber(segment.segment_idx, asNumber(segment.segmentIdx)),
            segmentIdentity: asString(segment.segment_identity, asString(segment.segmentIdentity)),
            isRecovery: asBoolean(segment.is_recovery, asBoolean(segment.isRecovery)),
            timelineStatus: asString(segment.timeline_status, asString(segment.timelineStatus, 'unavailable')),
            freezeAt: asString(segment.freeze_at, asString(segment.freezeAt)),
            publishedAt: asString(segment.published_at, asString(segment.publishedAt)),
            observedAt: asString(segment.observed_at, asString(segment.observedAt)),
            nextDueAt: asString(segment.next_due_at, asString(segment.nextDueAt)),
            matchCount: asNumber(segment.match_count, asNumber(segment.matchCount)),
            detail: asString(segment.detail),
            autoRecoveryExpected: asBoolean(segment.auto_recovery_expected, asBoolean(segment.autoRecoveryExpected)),
            exactN: {
              status: asString(exactN.status, 'missing'),
              sourceStatus: asString(exactN.source_status, asString(exactN.sourceStatus)),
              verificationStatus: asString(exactN.verification_status, asString(exactN.verificationStatus)),
              eventId: asString(exactN.event_id, asString(exactN.eventId)),
              artifactRef: asString(exactN.artifact_ref, asString(exactN.artifactRef)),
              alternativeCount: asNumber(exactN.alternative_count, asNumber(exactN.alternativeCount)),
              selectableCount: asNumber(exactN.selectable_count, asNumber(exactN.selectableCount)),
              researchEvidenceEligible: asBoolean(exactN.research_evidence_eligible, asBoolean(exactN.researchEvidenceEligible)),
            },
            researchFreeze: {
              status: asString(researchFreeze.status, 'missing'),
              verificationStatus: asString(researchFreeze.verification_status, asString(researchFreeze.verificationStatus)),
              eventId: asString(researchFreeze.event_id, asString(researchFreeze.eventId)),
              artifactRef: asString(researchFreeze.artifact_ref, asString(researchFreeze.artifactRef)),
              detail: asString(researchFreeze.detail),
              pairedOverlapMatches: asMaybeNumber(researchFreeze.paired_overlap_matches ?? researchFreeze.pairedOverlapMatches),
              frozenMatchMarkets: asMaybeNumber(researchFreeze.frozen_match_markets ?? researchFreeze.frozenMatchMarkets),
            },
          };
        }),
      },
      adhocService: {
        status: asString(adhocDomain.status, 'missing'),
        serviceStatus: asString(
          adhocDomain.service_status,
          asString(adhocDomain.serviceStatus, asString(adhocDomain.status, 'missing')),
        ),
        isolationStatus: asString(
          adhocDomain.isolation_status,
          asString(adhocDomain.isolationStatus, 'missing'),
        ),
        capabilityAvailable: asBoolean(adhocDomain.capability_available, asBoolean(adhocDomain.capabilityAvailable)),
        lastRequestAt: asString(adhocDomain.last_request_at, asString(adhocDomain.lastRequestAt)),
        lastSuccessAt: asString(adhocDomain.last_success_at, asString(adhocDomain.lastSuccessAt)),
        detail: asString(adhocDomain.detail),
        scheduledFreezeEventId: asString(adhocDomain.scheduled_freeze_event_id, asString(adhocDomain.scheduledFreezeEventId)) || undefined,
        researchEvidenceEligible: asBoolean(adhocDomain.research_evidence_eligible, asBoolean(adhocDomain.researchEvidenceEligible)),
        recentRequest: Object.keys(adhocRecent).length ? {
          requestId: asString(adhocRecent.request_id, asString(adhocRecent.requestId)),
          requestedAt: asString(adhocRecent.requested_at, asString(adhocRecent.requestedAt)),
          inputAsof: asString(adhocRecent.input_asof, asString(adhocRecent.inputAsof)),
          status: asString(adhocRecent.status),
          validUntil: asString(adhocRecent.valid_until, asString(adhocRecent.validUntil)),
          saleStatusVerifiedAtGeneration: asBoolean(adhocRecent.sale_status_verified_at_generation, asBoolean(adhocRecent.saleStatusVerifiedAtGeneration)),
          state: asString(adhocRecent.state),
          separationValid: asBoolean(adhocRecent.separation_valid, asBoolean(adhocRecent.separationValid)),
        } : undefined,
      },
      settlementReview: {
        status: asString(settlementDomain.status, 'missing'),
        settledMatchCount: asNumber(settlementDomain.settled_match_count, asNumber(settlementDomain.settledMatchCount)),
        winningSpCount: asNumber(settlementDomain.winning_sp_count, asNumber(settlementDomain.winningSpCount)),
        reviewedMatchCount: asNumber(settlementDomain.reviewed_match_count, asNumber(settlementDomain.reviewedMatchCount)),
        missingWinningSpMatchIds: asArray(settlementDomain.missing_winning_sp_match_ids ?? settlementDomain.missingWinningSpMatchIds).map((value) => asString(value)).filter(Boolean),
        unreviewedMatchIds: asArray(settlementDomain.unreviewed_match_ids ?? settlementDomain.unreviewedMatchIds).map((value) => asString(value)).filter(Boolean),
        latestReviewAt: asString(settlementDomain.latest_review_at, asString(settlementDomain.latestReviewAt)),
        lastSettlementSuccessAt: asString(settlementDomain.last_settlement_success_at, asString(settlementDomain.lastSettlementSuccessAt)),
        nextDueAt: asString(settlementDomain.next_due_at, asString(settlementDomain.nextDueAt)),
        simulationOnly: asBoolean(settlementDomain.simulation_only, asBoolean(settlementDomain.simulationOnly)),
        offlinePurchaseInferred: asBoolean(settlementDomain.offline_purchase_inferred, asBoolean(settlementDomain.offlinePurchaseInferred)),
        actualRoiClaimed: asBoolean(settlementDomain.actual_roi_claimed, asBoolean(settlementDomain.actualRoiClaimed)),
      },
    },
    alerts: asArray(obj.alerts).map((rawAlert) => {
      const alert = asObject(rawAlert);
      const affected = asObject(alert.affected);
      const blocks = asObject(alert.blocks);
      return {
        alertId: asString(alert.alert_id, asString(alert.alertId)),
        code: asString(alert.code),
        domain: asString(alert.domain),
        severity: asString(alert.severity, 'blocker'),
        status: asString(alert.status, 'open'),
        title: asString(alert.title),
        detail: asString(alert.detail),
        impact: asString(alert.impact),
        nextAction: asString(alert.next_action, asString(alert.nextAction)),
        observedAt: asString(alert.observed_at, asString(alert.observedAt)),
        firstSeenAt: asString(alert.first_seen_at, asString(alert.firstSeenAt)),
        lastSeenAt: asString(alert.last_seen_at, asString(alert.lastSeenAt)),
        lastSuccessAt: asString(alert.last_success_at, asString(alert.lastSuccessAt)),
        nextDueAt: asString(alert.next_due_at, asString(alert.nextDueAt)),
        affectedCount: asNumber(alert.affected_count, asNumber(alert.affectedCount)),
        affected: {
          segments: asArray(affected.segments).map((value) => asString(value)).filter(Boolean),
          matches: asArray(affected.matches).map((value) => asString(value)).filter(Boolean),
          markets: asArray(affected.markets).map((value) => asString(value)).filter(Boolean),
          sources: asArray(affected.sources).map((value) => asString(value)).filter(Boolean),
        },
        autoRecoveryExpected: asBoolean(alert.auto_recovery_expected, asBoolean(alert.autoRecoveryExpected)),
        retryCount: asMaybeNumber(alert.retry_count ?? alert.retryCount),
        links: asArray(alert.links).map((rawLink) => {
          const link = asObject(rawLink);
          return { kind: asString(link.kind), label: asString(link.label), ref: asString(link.ref) };
        }),
        blocks: {
          dataDisplay: asBoolean(blocks.data_display, asBoolean(blocks.dataDisplay)),
          researchFreeze: asBoolean(blocks.research_freeze, asBoolean(blocks.researchFreeze)),
          adhocGeneration: asBoolean(blocks.adhoc_generation, asBoolean(blocks.adhocGeneration)),
          settlement: asBoolean(blocks.settlement),
        },
      };
    }),
    issueStatus: {
      currentIssue: asString(issueStatus.current_issue, asString(issueStatus.currentIssue)),
      matchCount: asNumber(issueStatus.match_count, asNumber(issueStatus.matchCount)),
      finishedCount: asNumber(issueStatus.finished_count, asNumber(issueStatus.finishedCount)),
      settledSpCount: asNumber(issueStatus.settled_sp_count, asNumber(issueStatus.settledSpCount)),
      openCount: asNumber(issueStatus.open_count, asNumber(issueStatus.openCount)),
      captureStatus: asString(issueStatus.capture_status, asString(issueStatus.captureStatus)),
      latestSnapshotAt: asString(issueStatus.latest_snapshot_at, asString(issueStatus.latestSnapshotAt)),
      latestSnapshotAgeMinutes: asMaybeNumber(issueStatus.latest_snapshot_age_minutes ?? issueStatus.latestSnapshotAgeMinutes),
    },
    runtime: {
      apiHealth: asString(runtime.api_health, asString(runtime.apiHealth)),
      apiUrl: asString(runtime.api_url, asString(runtime.apiUrl)),
      apiHealthUrl: asString(runtime.api_health_url, asString(runtime.apiHealthUrl)),
      apiPort: asString(runtime.api_port, asString(runtime.apiPort)),
      frontendHealth: asString(runtime.frontend_health, asString(runtime.frontendHealth)) || undefined,
      frontendLocalUrl: asString(runtime.frontend_local_url, asString(runtime.frontendLocalUrl)),
      frontendRemoteUrl: asString(runtime.frontend_remote_url, asString(runtime.frontendRemoteUrl)),
      frontendPort: asString(runtime.frontend_port, asString(runtime.frontendPort)),
      publicDiagnostics: asBoolean(runtime.public_diagnostics, asBoolean(runtime.publicDiagnostics)),
      accessMode: asString(runtime.access_mode, asString(runtime.accessMode)) || undefined,
      externalAccessConfigured: asBoolean(runtime.external_access_configured, asBoolean(runtime.externalAccessConfigured)),
      checkedAt: asString(runtime.checked_at, asString(runtime.checkedAt)) || undefined,
      statusPath: asString(runtime.status_path, asString(runtime.statusPath, asString(runtimeDiagnostics.status_path, asString(runtimeDiagnostics.statusPath)))) || undefined,
      runtimeDir: asString(runtime.runtime_dir, asString(runtime.runtimeDir, asString(runtimeDiagnostics.runtime_dir, asString(runtimeDiagnostics.runtimeDir)))) || undefined,
      urls: Object.fromEntries(Object.entries(runtimeUrls).map(([key, value]) => [key, asString(value)])),
      apiPid: asMaybeNumber(runtime.api_pid ?? runtime.apiPid ?? runtimeDiagnostics.api_pid ?? runtimeDiagnostics.apiPid),
      apiProcessStatus: asString(runtime.api_process_status, asString(runtime.apiProcessStatus)) || undefined,
      apiBindHost: asString(runtime.api_bind_host, asString(runtime.apiBindHost, asString(runtimeDiagnostics.api_bind_host, asString(runtimeDiagnostics.apiBindHost)))) || undefined,
      apiCommand: asArray(runtime.api_command ?? runtime.apiCommand ?? runtimeDiagnostics.api_command ?? runtimeDiagnostics.apiCommand).map((value) => asString(value)).filter(Boolean),
      apiLog: asString(runtime.api_log, asString(runtime.apiLog, asString(runtimeDiagnostics.api_log, asString(runtimeDiagnostics.apiLog)))) || undefined,
      frontendPid: asMaybeNumber(runtime.frontend_pid ?? runtime.frontendPid ?? runtimeDiagnostics.frontend_pid ?? runtimeDiagnostics.frontendPid),
      frontendProcessStatus: asString(runtime.frontend_process_status, asString(runtime.frontendProcessStatus)) || undefined,
      frontendBindHost: asString(runtime.frontend_bind_host, asString(runtime.frontendBindHost, asString(runtimeDiagnostics.frontend_bind_host, asString(runtimeDiagnostics.frontendBindHost)))) || undefined,
      frontendCommand: asArray(runtime.frontend_command ?? runtime.frontendCommand ?? runtimeDiagnostics.frontend_command ?? runtimeDiagnostics.frontendCommand).map((value) => asString(value)).filter(Boolean),
      frontendLog: asString(runtime.frontend_log, asString(runtime.frontendLog, asString(runtimeDiagnostics.frontend_log, asString(runtimeDiagnostics.frontendLog)))) || undefined,
      health: {
        api: transformRuntimeHealthProbe(runtimeHealth.api),
        frontendLocal: transformRuntimeHealthProbe(runtimeHealth.frontend_local ?? runtimeHealth.frontendLocal),
        operations: transformRuntimeHealthProbe(runtimeHealth.operations),
        hostSmokeCount: asMaybeNumber(runtimeHealth.host_smoke_count ?? runtimeHealth.hostSmokeCount),
        hostSmokeOkCount: asMaybeNumber(runtimeHealth.host_smoke_ok_count ?? runtimeHealth.hostSmokeOkCount),
        hostSmokes: asArray(runtimeHealth.host_smokes ?? runtimeHealth.hostSmokes).map(transformRuntimeHealthProbe),
      },
    },
    sources: asArray(obj.sources).map((sourceRaw) => {
      const row = asObject(sourceRaw);
      return {
        sourceName: asString(row.source_name, asString(row.sourceName)),
        status: toScrapeStatus(row.status),
        lastAttemptAt: asString(row.last_attempt_at, asString(row.lastAttemptAt)),
        lastSuccessAt: asString(row.last_success_at, asString(row.lastSuccessAt)),
        ageMinutes: asMaybeNumber(row.age_minutes ?? row.ageMinutes),
        okCount: asNumber(row.ok_count, asNumber(row.okCount)),
        failCount: asNumber(row.fail_count, asNumber(row.failCount)),
        totalAttempts: asNumber(row.total_attempts, asNumber(row.totalAttempts)),
        rowsParsed: asNumber(row.rows_parsed, asNumber(row.rowsParsed)),
        error: asString(row.error) || undefined,
      };
    }),
    snapshots: {
      activeCount: asNumber(snapshots.active_count, asNumber(snapshots.activeCount)),
      draftReplacementCount: asNumber(snapshots.draft_replacement_count, asNumber(snapshots.draftReplacementCount)),
      supersededCount: asNumber(snapshots.superseded_count, asNumber(snapshots.supersededCount)),
      pendingDrafts: asArray(snapshots.pending_drafts ?? snapshots.pendingDrafts).map((draftRaw) => {
        const draft = asObject(draftRaw);
        return {
          matchIdx: asNumber(draft.match_idx, asNumber(draft.matchIdx)),
          matchId: asString(draft.match_id, asString(draft.matchId)),
          generatedAt: asString(draft.generated_at, asString(draft.generatedAt)),
          checkedAt: asString(draft.checked_at, asString(draft.checkedAt)),
        };
      }),
    },
    review: {
      reviewVersion: asString(review.review_version, asString(review.reviewVersion)),
      settledMatchCount: asNumber(review.settled_match_count, asNumber(review.settledMatchCount)),
      reviewedMatchCount: asNumber(review.reviewed_match_count, asNumber(review.reviewedMatchCount)),
      unreviewedSettledCount: asNumber(review.unreviewed_settled_count, asNumber(review.unreviewedSettledCount)),
      latestReviewAt: asString(review.latest_review_at, asString(review.latestReviewAt)),
      unreviewedMatches: asArray(review.unreviewed_matches ?? review.unreviewedMatches).map((matchRaw) => {
        const match = asObject(matchRaw);
        return {
          matchIdx: asNumber(match.match_idx, asNumber(match.matchIdx)),
          matchId: asString(match.match_id, asString(match.matchId)),
          label: asString(match.label),
          resultLabel: asString(match.result_label, asString(match.resultLabel)),
          winningSp: asMaybeNumber(match.winning_sp ?? match.winningSp),
        };
      }),
      task: {
        runId: asString(reviewTask.run_id, asString(reviewTask.runId)),
        issue: asString(reviewTask.issue),
        mode: asString(reviewTask.mode),
        status: asString(reviewTask.status, 'not_run'),
        dryRun: asBoolean(reviewTask.dry_run, asBoolean(reviewTask.dryRun)),
        requestedBy: asString(reviewTask.requested_by, asString(reviewTask.requestedBy)),
        startedAt: asString(reviewTask.started_at, asString(reviewTask.startedAt)),
        finishedAt: asString(reviewTask.finished_at, asString(reviewTask.finishedAt)),
        elapsedSec: asMaybeNumber(reviewTask.elapsed_sec ?? reviewTask.elapsedSec),
        error: asString(reviewTask.error) || undefined,
        triggerEndpoint: asString(reviewTask.trigger_endpoint, asString(reviewTask.triggerEndpoint)),
        command: asArray(reviewTask.command).map((value) => asString(value)).filter(Boolean),
        result: {
          inserted: asMaybeNumber(reviewTaskResult.inserted),
          wouldInsert: asMaybeNumber(reviewTaskResult.would_insert ?? reviewTaskResult.wouldInsert),
          reviewedAt: asString(reviewTaskResult.reviewed_at, asString(reviewTaskResult.reviewedAt)) || undefined,
          profit: asMaybeNumber(reviewTaskResult.profit),
          coverageHits: asMaybeNumber(reviewTaskResult.coverage_hits ?? reviewTaskResult.coverageHits),
          primaryHits: asMaybeNumber(reviewTaskResult.primary_hits ?? reviewTaskResult.primaryHits),
          protectHits: asMaybeNumber(reviewTaskResult.protect_hits ?? reviewTaskResult.protectHits),
        },
      },
    },
    workflow: {
      runId: asString(workflow.run_id, asString(workflow.runId)),
      issue: asString(workflow.issue),
      mode: asString(workflow.mode),
      status: asString(workflow.status, 'not_run'),
      dryRun: asBoolean(workflow.dry_run, asBoolean(workflow.dryRun)),
      requestedBy: asString(workflow.requested_by, asString(workflow.requestedBy)),
      startedAt: asString(workflow.started_at, asString(workflow.startedAt)),
      finishedAt: asString(workflow.finished_at, asString(workflow.finishedAt)),
      elapsedSec: asMaybeNumber(workflow.elapsed_sec ?? workflow.elapsedSec),
      error: asString(workflow.error) || undefined,
      triggerEndpoint: asString(workflow.trigger_endpoint, asString(workflow.triggerEndpoint)),
      steps: asArray(workflow.steps).map((stepRaw) => {
        const step = asObject(stepRaw);
        return {
          stepIdx: asNumber(step.step_idx, asNumber(step.stepIdx)),
          stepKey: asString(step.step_key, asString(step.stepKey)),
          label: asString(step.label),
          status: asString(step.status),
          command: asArray(step.command).map((value) => asString(value)).filter(Boolean),
          startedAt: asString(step.started_at, asString(step.startedAt)),
          finishedAt: asString(step.finished_at, asString(step.finishedAt)),
          elapsedSec: asMaybeNumber(step.elapsed_sec ?? step.elapsedSec),
          error: asString(step.error) || undefined,
        };
      }),
    },
    versions: {
      schemaVersion: asString(versions.schema_version, asString(versions.schemaVersion)),
      probModelVersion: asString(versions.prob_model_version, asString(versions.probModelVersion)),
      qModelVersion: asString(versions.q_model_version, asString(versions.qModelVersion)),
      decisionChainVersion: asString(versions.decision_chain_version, asString(versions.decisionChainVersion)),
      decisionPromptVersion: asString(versions.decision_prompt_version, asString(versions.decisionPromptVersion)),
      decisionModelVersion: asString(versions.decision_model_version, asString(versions.decisionModelVersion)),
      reviewTagVersion: asString(versions.review_tag_version, asString(versions.reviewTagVersion)),
      reviewVersion: asString(versions.review_version, asString(versions.reviewVersion)),
      decisionConfigHash: asString(versions.decision_config_hash, asString(versions.decisionConfigHash)),
      configPath: asString(versions.config_path, asString(versions.configPath)),
    },
    warnings: asArray(obj.warnings).map((warningRaw) => {
      const warning = asObject(warningRaw);
      return {
        code: asString(warning.code),
        severity: asString(warning.severity, 'neutral'),
        label: asString(warning.label),
        detail: asString(warning.detail),
      };
    }),
    source: {
      sqliteDb: asString(source.sqlite_db, asString(source.sqliteDb)),
      tables: asArray(source.tables).map((value) => asString(value)).filter(Boolean),
    },
  };
}

function transformSegmentBettingPlan(raw: unknown): SegmentBettingPlanData {
  const obj = asObject(raw);
  const source = asObject(obj.source);
  const artifactStatus = asObject(obj.artifact_status ?? obj.artifactStatus);
  const strategyRelease = asObject(obj.strategy_release ?? obj.strategyRelease);
  const settings = asObject(obj.settings);
  const summary = asObject(obj.summary);
  const spDriftRisk = asObject(obj.sp_drift_risk ?? obj.spDriftRisk);
  const selectionBinding = asObject(obj.selection_binding ?? obj.selectionBinding);
  const seedAggregate = asObject(obj.seed_aggregate ?? obj.seedAggregate);
  const seedMetrics = asObject(seedAggregate.metrics);
  const transformSeedMetric = (rawMetric: unknown) => {
    const metric = asObject(rawMetric);
    return {
      min: asMaybeNumber(metric.min),
      p10: asMaybeNumber(metric.p10),
      mean: asMaybeNumber(metric.mean),
      median: asMaybeNumber(metric.median),
      p90: asMaybeNumber(metric.p90),
      max: asMaybeNumber(metric.max),
    };
  };
  const transformPlanOption = (rawPlan: unknown): SegmentBettingPlanData['availablePlans'][number] => {
    const plan = asObject(rawPlan);
    return {
      planId: asString(plan.plan_id, asString(plan.planId)),
      label: asString(plan.label),
      decisionVariantId: asString(plan.decision_variant_id, asString(plan.decisionVariantId)),
      strategyFamily: asString(plan.strategy_family, asString(plan.strategyFamily)),
      bettingStrategyVersion: asString(plan.betting_strategy_version, asString(plan.bettingStrategyVersion)),
	      artifactSchemaVersion: asString(plan.artifact_schema_version, asString(plan.artifactSchemaVersion)),
	      planningScope: asString(plan.planning_scope, asString(plan.planningScope)),
	      artifactPlanningScope: asString(plan.artifact_planning_scope, asString(plan.artifactPlanningScope)) || undefined,
	      decisionTime: asString(plan.decision_time, asString(plan.decisionTime)),
      stakeMode: asString(plan.stake_mode, asString(plan.stakeMode)),
      availableSegments: asMaybeNumber(plan.available_segments ?? plan.availableSegments),
      spDriftRiskAccepted: asBoolean(plan.sp_drift_risk_accepted, asBoolean(plan.spDriftRiskAccepted)),
      spDriftRiskLevel: asString(plan.sp_drift_risk_level, asString(plan.spDriftRiskLevel)),
      arm: asString(plan.arm),
      segmentBudgetYuan: asMaybeNumber(plan.segment_budget_yuan ?? plan.segmentBudgetYuan),
      sampleSeed: asMaybeNumber(plan.sample_seed ?? plan.sampleSeed),
      seedCount: asMaybeNumber(plan.seed_count ?? plan.seedCount),
      summaryMode: asString(plan.summary_mode, asString(plan.summaryMode)),
      sourceRows: asMaybeNumber(plan.source_rows ?? plan.sourceRows),
      eligibleRows: asMaybeNumber(plan.eligible_rows ?? plan.eligibleRows),
      segments: asMaybeNumber(plan.segments),
      selectedBundles: asMaybeNumber(plan.selected_bundles ?? plan.selectedBundles),
      baseCostYuan: asMaybeNumber(plan.base_cost_yuan ?? plan.baseCostYuan),
      stakeMultiplierUnits: asMaybeNumber(plan.stake_multiplier_units ?? plan.stakeMultiplierUnits),
      selectedCostYuan: asMaybeNumber(plan.selected_cost_yuan ?? plan.selectedCostYuan),
      profitYuan: asMaybeNumber(plan.profit_yuan ?? plan.profitYuan),
      roi: asMaybeNumber(plan.roi),
      updatedAt: formatDateTimeShort(plan.updated_at ?? plan.updatedAt),
      artifactPath: asString(plan.artifact_path, asString(plan.artifactPath)),
    };
  };
  return {
	    schemaVersion: asString(obj.schema_version, asString(obj.schemaVersion)),
	    issueId: asString(obj.issue, asString(obj.issueId)),
	    mode: asString(obj.mode),
	    requestedDecisionVariantId: asString(obj.requested_decision_variant_id, asString(obj.requestedDecisionVariantId)),
	    requestedPlanningScope: asString(obj.requested_planning_scope, asString(obj.requestedPlanningScope)),
	    requestedDecisionTime: asString(obj.requested_decision_time, asString(obj.requestedDecisionTime)),
	    requestedSegmentBudgetYuan: asMaybeNumber(obj.requested_segment_budget_yuan ?? obj.requestedSegmentBudgetYuan),
	    requestedStakeMode: asString(obj.requested_stake_mode, asString(obj.requestedStakeMode)) || undefined,
	    requestedBettingStrategyVersion: asString(obj.requested_betting_strategy_version, asString(obj.requestedBettingStrategyVersion)),
	    requestedLabel: asString(obj.requested_label, asString(obj.requestedLabel)),
	    selectedPlanId: asString(obj.selected_plan_id, asString(obj.selectedPlanId)),
    availabilityStatus: asString(obj.availability_status, asString(obj.availabilityStatus, 'missing')),
    unavailableReason: asString(obj.unavailable_reason, asString(obj.unavailableReason)) || undefined,
    notice: asString(obj.notice),
    source: {
      artifactKey: asString(source.artifact_key, asString(source.artifactKey)),
      artifactDir: asString(source.artifact_dir, asString(source.artifactDir)),
    },
    artifactPath: asString(obj._artifact_path, asString(obj.artifactPath)),
    artifactStatus: {
      status: asString(artifactStatus.status, asString(obj.availability_status, asString(obj.availabilityStatus, 'missing'))),
      artifactKey: asString(artifactStatus.artifact_key, asString(artifactStatus.artifactKey)),
      artifactDir: asString(artifactStatus.artifact_dir, asString(artifactStatus.artifactDir)),
      artifactPath: asString(artifactStatus.artifact_path, asString(artifactStatus.artifactPath)),
      sourcePath: asString(artifactStatus.source_path, asString(artifactStatus.sourcePath)),
      updatedAt: formatDateTimeShort(artifactStatus.updated_at ?? artifactStatus.updatedAt),
      reason: asString(artifactStatus.reason),
    },
    strategyRelease: {
      activeReleaseId: asString(strategyRelease.active_release_id, asString(strategyRelease.activeReleaseId)),
      releaseId: asString(strategyRelease.release_id, asString(strategyRelease.releaseId)),
      versionId: asString(strategyRelease.version_id, asString(strategyRelease.versionId)),
      status: asString(strategyRelease.status),
    },
    availablePlans: asArray(obj.available_plans ?? obj.availablePlans).map(transformPlanOption),
    selectedPlan: Object.keys(asObject(obj.selected_plan ?? obj.selectedPlan)).length
      ? transformPlanOption(obj.selected_plan ?? obj.selectedPlan)
      : undefined,
    strategyFamily: asString(obj.strategy_family, asString(obj.strategyFamily)),
	    bettingStrategyVersion: asString(obj.betting_strategy_version, asString(obj.bettingStrategyVersion)),
	    artifactSchemaVersion: asString(obj.artifact_schema_version, asString(obj.artifactSchemaVersion)),
	    planningScope: asString(obj.planning_scope, asString(obj.planningScope)),
	    artifactPlanningScope: asString(obj.artifact_planning_scope, asString(obj.artifactPlanningScope)) || undefined,
	    decisionTime: asString(obj.decision_time, asString(obj.decisionTime)),
	    availableSegments: asMaybeNumber(obj.available_segments ?? obj.availableSegments),
	    dynamicSegmentsAvailable: asMaybeNumber(obj.dynamic_segments_available ?? obj.dynamicSegmentsAvailable),
	    selectionBinding: Object.keys(selectionBinding).length ? {
	      matchSelectionSource: asString(selectionBinding.match_selection_source, asString(selectionBinding.matchSelectionSource)),
	      frontendDisplaySource: asString(selectionBinding.frontend_display_source, asString(selectionBinding.frontendDisplaySource)),
	      refreshPolicy: asString(selectionBinding.refresh_policy, asString(selectionBinding.refreshPolicy)),
	      planningScope: asString(selectionBinding.planning_scope, asString(selectionBinding.planningScope)) || undefined,
	    } : undefined,
    spDriftRisk: {
      accepted: asBoolean(spDriftRisk.accepted),
      level: asString(spDriftRisk.level),
      reason: asString(spDriftRisk.reason),
    },
    settings: {
      planningScope: asString(settings.planning_scope, asString(settings.planningScope)) || undefined,
      decisionTime: asString(settings.decision_time, asString(settings.decisionTime)) || undefined,
      stakeMode: asString(settings.stake_mode, asString(settings.stakeMode)) || undefined,
      windowHours: asMaybeNumber(settings.window_hours ?? settings.windowHours),
      extendHours: asString(settings.extend_hours, asString(settings.extendHours)),
      minMatches: asMaybeNumber(settings.min_matches ?? settings.minMatches),
      maxMatches: asMaybeNumber(settings.max_matches ?? settings.maxMatches),
      segmentBudgetYuan: asMaybeNumber(settings.segment_budget_yuan ?? settings.segmentBudgetYuan),
      stakeYuanPerTicket: asMaybeNumber(settings.stake_yuan_per_ticket ?? settings.stakeYuanPerTicket),
      sampleAttempts: asMaybeNumber(settings.sample_attempts ?? settings.sampleAttempts),
      sampleSeed: asMaybeNumber(settings.sample_seed ?? settings.sampleSeed),
      seedCount: asMaybeNumber(settings.seed_count ?? settings.seedCount),
      sampleSeeds: asArray(settings.sample_seeds ?? settings.sampleSeeds).filter((value): value is number => typeof value === 'number'),
      minN: asMaybeNumber(settings.min_n ?? settings.minN),
      maxN: asMaybeNumber(settings.max_n ?? settings.maxN),
	      maxOverlap: asMaybeNumber(settings.max_overlap ?? settings.maxOverlap),
	      maxBundleSpendPct: asMaybeNumber(settings.max_bundle_spend_pct ?? settings.maxBundleSpendPct),
	      positiveEvOnly: asBoolean(settings.positive_ev_only, asBoolean(settings.positiveEvOnly)),
      bettingStrategyVersion: asString(settings.betting_strategy_version, asString(settings.bettingStrategyVersion)) || undefined,
    },
    seedAggregate: {
      seedCount: asMaybeNumber(seedAggregate.seed_count ?? seedAggregate.seedCount),
      seeds: asArray(seedAggregate.seeds).filter((value): value is number => typeof value === 'number'),
      summaryMode: asString(seedAggregate.summary_mode, asString(seedAggregate.summaryMode, 'single_seed')),
      metrics: Object.fromEntries(Object.entries(seedMetrics).map(([key, value]) => [key, transformSeedMetric(value)])),
    },
    parameterSchema: asArray(obj.parameter_schema ?? obj.parameterSchema).map((rawParam) => {
      const param = asObject(rawParam);
      return {
        key: asString(param.key),
        label: asString(param.label),
        uiLevel: asString(param.ui_level, asString(param.uiLevel, 'basic')),
        type: asString(param.type),
        unit: asString(param.unit) || undefined,
        defaultValue: (param.default ?? param.defaultValue) as string | number | boolean | null | undefined,
        options: asArray(param.options).map((value) => asString(value)).filter(Boolean),
        min: asMaybeNumber(param.min),
        step: asMaybeNumber(param.step),
        effect: asString(param.effect),
      };
    }).filter((param) => param.key),
    segmentCsv: asString(obj.segment_csv, asString(obj.segmentCsv)),
    bundleCsv: asString(obj.bundle_csv, asString(obj.bundleCsv)),
    seedSummaryCsv: asString(obj.seed_summary_csv, asString(obj.seedSummaryCsv)),
    segmentSeedSummaryCsv: asString(obj.segment_seed_summary_csv, asString(obj.segmentSeedSummaryCsv)),
    summary: {
      settlementStatus: asString(summary.settlement_status, asString(summary.settlementStatus)) || undefined,
      primaryMetricMode: asString(summary.primary_metric_mode, asString(summary.primaryMetricMode)) || undefined,
      segments: asMaybeNumber(summary.segments),
      selectedSegments: asMaybeNumber(summary.selected_segments ?? summary.selectedSegments),
      deadSegments: asMaybeNumber(summary.dead_segments ?? summary.deadSegments),
      selectedBundles: asMaybeNumber(summary.selected_bundles ?? summary.selectedBundles),
      baseCostYuan: asMaybeNumber(summary.base_cost_yuan ?? summary.baseCostYuan),
      stakeMultiplierUnits: asMaybeNumber(summary.stake_multiplier_units ?? summary.stakeMultiplierUnits),
      selectedCostYuan: asMaybeNumber(summary.selected_cost_yuan ?? summary.selectedCostYuan),
      expectedPayoutYuan: asMaybeNumber(summary.expected_payout_yuan ?? summary.expectedPayoutYuan),
      expectedProfitYuan: asMaybeNumber(summary.expected_profit_yuan ?? summary.expectedProfitYuan),
      expectedRoi: asMaybeNumber(summary.expected_roi ?? summary.expectedRoi),
      payoutYuan: asMaybeNumber(summary.payout_yuan ?? summary.payoutYuan),
      profitYuan: asMaybeNumber(summary.profit_yuan ?? summary.profitYuan),
      roi: asMaybeNumber(summary.roi),
    },
    segments: asArray(obj.segments).map((rawSegment) => {
      const segment = asObject(rawSegment);
      return {
        sampleSeed: asMaybeNumber(segment.sample_seed ?? segment.sampleSeed),
        segmentIdx: asMaybeNumber(segment.segment_idx ?? segment.segmentIdx),
        arm: asString(segment.arm),
        planningScope: asString(segment.planning_scope, asString(segment.planningScope)),
        hoursFromDecisionStart: asMaybeNumber(segment.hours_from_decision_start ?? segment.hoursFromDecisionStart),
        hoursFromDecisionEnd: asMaybeNumber(segment.hours_from_decision_end ?? segment.hoursFromDecisionEnd),
        spDriftRiskAccepted: asBoolean(segment.sp_drift_risk_accepted, asBoolean(segment.spDriftRiskAccepted)),
        spDriftRiskLevel: asString(segment.sp_drift_risk_level, asString(segment.spDriftRiskLevel)),
        spDriftRiskReason: asString(segment.sp_drift_risk_reason, asString(segment.spDriftRiskReason)),
        stakeMode: asString(segment.stake_mode, asString(segment.stakeMode)),
        segmentStart: asString(segment.segment_start, asString(segment.segmentStart)),
        segmentEnd: asString(segment.segment_end, asString(segment.segmentEnd)),
        windowHours: asMaybeNumber(segment.window_hours ?? segment.windowHours),
        eligibleMatches: asMaybeNumber(segment.eligible_matches ?? segment.eligibleMatches),
        expectedCoverageHitRate: asMaybeNumber(segment.expected_coverage_hit_rate ?? segment.expectedCoverageHitRate),
        actualCoverageHits: asMaybeNumber(segment.actual_coverage_hits ?? segment.actualCoverageHits),
        actualCoverageHitRate: asMaybeNumber(segment.actual_coverage_hit_rate ?? segment.actualCoverageHitRate),
        recommendedN: asMaybeNumber(segment.recommended_n ?? segment.recommendedN),
        initialRecommendedN: asMaybeNumber(segment.initial_recommended_n ?? segment.initialRecommendedN),
        selectedBundles: asMaybeNumber(segment.selected_bundles ?? segment.selectedBundles),
        candidateBundles: asMaybeNumber(segment.candidate_bundles ?? segment.candidateBundles),
        baseCostYuan: asMaybeNumber(segment.base_cost_yuan ?? segment.baseCostYuan),
        stakeMultiplierUnits: asMaybeNumber(segment.stake_multiplier_units ?? segment.stakeMultiplierUnits),
        selectedCostYuan: asMaybeNumber(segment.selected_cost_yuan ?? segment.selectedCostYuan),
        segmentBudgetYuan: asMaybeNumber(segment.segment_budget_yuan ?? segment.segmentBudgetYuan),
        expectedProfitYuan: asMaybeNumber(segment.expected_profit_yuan ?? segment.expectedProfitYuan),
        payoutYuan: asMaybeNumber(segment.payout_yuan ?? segment.payoutYuan),
        profitYuan: asMaybeNumber(segment.profit_yuan ?? segment.profitYuan),
        roi: asMaybeNumber(segment.roi),
        deadSegment: asBoolean(segment.dead_segment, asBoolean(segment.deadSegment)),
        widthCounts: asString(segment.width_counts, asString(segment.widthCounts)),
        reasons: asStringList(segment.reasons),
        matchIndices: asArray(segment.match_indices ?? segment.matchIndices).filter((value): value is number => typeof value === 'number'),
      };
    }),
    bundles: asArray(obj.bundles).map((rawBundle) => {
      const bundle = asObject(rawBundle);
      return {
        sampleSeed: asMaybeNumber(bundle.sample_seed ?? bundle.sampleSeed),
        segmentIdx: asMaybeNumber(bundle.segment_idx ?? bundle.segmentIdx),
        bundleIdx: asMaybeNumber(bundle.bundle_idx ?? bundle.bundleIdx),
        arm: asString(bundle.arm),
        nValue: asMaybeNumber(bundle.n_value ?? bundle.nValue),
        matchIndices: asArray(bundle.match_indices ?? bundle.matchIndices).filter((value): value is number => typeof value === 'number'),
        legCodes: asArray(bundle.leg_codes ?? bundle.legCodes).map((value) => asString(value)).filter(Boolean),
        widths: asArray(bundle.widths).filter((value): value is number => typeof value === 'number'),
        stakeMultiplier: asMaybeNumber(bundle.stake_multiplier ?? bundle.stakeMultiplier),
        costYuan: asMaybeNumber(bundle.cost_yuan ?? bundle.costYuan),
        scaledCostYuan: asMaybeNumber(bundle.scaled_cost_yuan ?? bundle.scaledCostYuan),
        expectedPayoutYuan: asMaybeNumber(bundle.expected_payout_yuan ?? bundle.expectedPayoutYuan),
        expectedProfitYuan: asMaybeNumber(bundle.expected_profit_yuan ?? bundle.expectedProfitYuan),
        scaledExpectedProfitYuan: asMaybeNumber(bundle.scaled_expected_profit_yuan ?? bundle.scaledExpectedProfitYuan),
        expectedRoi: asMaybeNumber(bundle.expected_roi ?? bundle.expectedRoi),
        hitProb: asMaybeNumber(bundle.hit_prob ?? bundle.hitProb),
        realizedHit: asBoolean(bundle.realized_hit, asBoolean(bundle.realizedHit)),
        payoutYuan: asMaybeNumber(bundle.payout_yuan ?? bundle.payoutYuan),
        scaledPayoutYuan: asMaybeNumber(bundle.scaled_payout_yuan ?? bundle.scaledPayoutYuan),
        profitYuan: asMaybeNumber(bundle.profit_yuan ?? bundle.profitYuan),
        scaledProfitYuan: asMaybeNumber(bundle.scaled_profit_yuan ?? bundle.scaledProfitYuan),
      };
    }),
    seedSummaries: asArray(obj.seed_summaries ?? obj.seedSummaries).map((rawSeed) => {
      const seed = asObject(rawSeed);
      return {
        sampleSeed: asMaybeNumber(seed.sample_seed ?? seed.sampleSeed),
        selectedSegments: asMaybeNumber(seed.selected_segments ?? seed.selectedSegments),
        deadSegments: asMaybeNumber(seed.dead_segments ?? seed.deadSegments),
        selectedBundles: asMaybeNumber(seed.selected_bundles ?? seed.selectedBundles),
        selectedCostYuan: asMaybeNumber(seed.selected_cost_yuan ?? seed.selectedCostYuan),
        payoutYuan: asMaybeNumber(seed.payout_yuan ?? seed.payoutYuan),
        profitYuan: asMaybeNumber(seed.profit_yuan ?? seed.profitYuan),
        roi: asMaybeNumber(seed.roi),
      };
    }),
    segmentSeedSummary: asArray(obj.segment_seed_summary ?? obj.segmentSeedSummary).map((rawSegment) => {
      const segment = asObject(rawSegment);
      return {
        segmentIdx: asMaybeNumber(segment.segment_idx ?? segment.segmentIdx),
        arm: asString(segment.arm),
        sampleCount: asMaybeNumber(segment.sample_count ?? segment.sampleCount),
        segmentStart: asString(segment.segment_start, asString(segment.segmentStart)),
        segmentEnd: asString(segment.segment_end, asString(segment.segmentEnd)),
        eligibleMatches: asMaybeNumber(segment.eligible_matches ?? segment.eligibleMatches),
        expectedCoverageHitRate: asMaybeNumber(segment.expected_coverage_hit_rate ?? segment.expectedCoverageHitRate),
        actualCoverageHits: asMaybeNumber(segment.actual_coverage_hits ?? segment.actualCoverageHits),
        actualCoverageHitRate: asMaybeNumber(segment.actual_coverage_hit_rate ?? segment.actualCoverageHitRate),
        recommendedNValues: asArray(segment.recommended_n_values ?? segment.recommendedNValues).filter((value): value is number => typeof value === 'number'),
        recommendedNStable: asBoolean(segment.recommended_n_stable, asBoolean(segment.recommendedNStable)),
        selectedBundlesMean: asMaybeNumber(segment.selected_bundles_mean ?? segment.selectedBundlesMean),
        selectedBundlesMin: asMaybeNumber(segment.selected_bundles_min ?? segment.selectedBundlesMin),
        selectedBundlesMax: asMaybeNumber(segment.selected_bundles_max ?? segment.selectedBundlesMax),
        baseCostYuanMean: asMaybeNumber(segment.base_cost_yuan_mean ?? segment.baseCostYuanMean),
        stakeMultiplierUnitsMean: asMaybeNumber(segment.stake_multiplier_units_mean ?? segment.stakeMultiplierUnitsMean),
        costYuanMean: asMaybeNumber(segment.cost_yuan_mean ?? segment.costYuanMean),
        payoutYuanMean: asMaybeNumber(segment.payout_yuan_mean ?? segment.payoutYuanMean),
        profitYuanMin: asMaybeNumber(segment.profit_yuan_min ?? segment.profitYuanMin),
        profitYuanP10: asMaybeNumber(segment.profit_yuan_p10 ?? segment.profitYuanP10),
        profitYuanMean: asMaybeNumber(segment.profit_yuan_mean ?? segment.profitYuanMean),
        profitYuanMedian: asMaybeNumber(segment.profit_yuan_median ?? segment.profitYuanMedian),
        profitYuanP90: asMaybeNumber(segment.profit_yuan_p90 ?? segment.profitYuanP90),
        profitYuanMax: asMaybeNumber(segment.profit_yuan_max ?? segment.profitYuanMax),
        roiMin: asMaybeNumber(segment.roi_min ?? segment.roiMin),
        roiMean: asMaybeNumber(segment.roi_mean ?? segment.roiMean),
        roiMax: asMaybeNumber(segment.roi_max ?? segment.roiMax),
        deadSegmentRate: asMaybeNumber(segment.dead_segment_rate ?? segment.deadSegmentRate),
        widthCounts: asString(segment.width_counts, asString(segment.widthCounts)),
        matchIndices: asArray(segment.match_indices ?? segment.matchIndices).filter((value): value is number => typeof value === 'number'),
      };
    }),
  };
}

function transformExactNFreezes(raw: unknown): ExactNFreezeData {
  const obj = asObject(raw);
  return {
    schemaVersion: asString(obj.schema_version),
    issueId: asString(obj.issue),
    status: asString(obj.status),
    segmentManifestSha256: asString(obj.segment_manifest_sha256),
    exactNFrontendSelectable: asBoolean(obj.exact_n_frontend_selectable),
    recoverySegments: asArray(obj.recovery_segments).map((rawRecovery) => {
      const recovery = asObject(rawRecovery);
      return {
        segmentIdentity: asString(recovery.segment_identity),
        parentSegmentIdx: asMaybeNumber(recovery.parent_segment_idx) ?? 0,
        parentStatus: asString(recovery.parent_status),
        status: asString(recovery.status),
        matchCount: asMaybeNumber(recovery.match_count) ?? 0,
        freezeAt: asString(recovery.freeze_at),
        recoveryManifestSha256: asString(recovery.recovery_manifest_sha256),
      };
    }),
    segments: asArray(obj.segments).map((rawSegment) => {
      const segment = asObject(rawSegment);
      const correctScore = asObject(segment.correct_score);
      return {
        segmentIdx: asMaybeNumber(segment.segment_idx) ?? 0,
        segmentIdentity: asString(segment.segment_identity) || `segment_${asMaybeNumber(segment.segment_idx) ?? 0}`,
        isRecovery: asBoolean(segment.is_recovery),
        parentSegmentIdx: asMaybeNumber(segment.parent_segment_idx),
        parentStatus: asString(segment.parent_status),
        recoveryManifestSha256: asString(segment.recovery_manifest_sha256),
        matchCount: asMaybeNumber(segment.match_count) ?? 0,
        freezeAt: asString(segment.freeze_at),
        effectiveDecisionAt: asString(segment.effective_decision_at),
        status: asString(segment.status),
        alternatives: asArray(segment.alternatives).map((rawAlternative) => {
          const alternative = asObject(rawAlternative);
          return {
            planId: asString(alternative.plan_id),
            exactN: asBoolean(alternative.exact_n),
            requestedN: asMaybeNumber(alternative.requested_n) ?? 0,
            artifactN: asMaybeNumber(alternative.artifact_n) ?? 0,
            recommendedN: asMaybeNumber(alternative.recommended_n) ?? 0,
            requestedBudgetYuan: asMaybeNumber(alternative.requested_budget_yuan) ?? 0,
            baseCostYuan: asMaybeNumber(alternative.base_cost_yuan) ?? 0,
            actualCostYuan: asMaybeNumber(alternative.actual_cost_yuan) ?? 0,
            unusedBudgetYuan: asMaybeNumber(alternative.unused_budget_yuan) ?? 0,
            budgetUtilization: asMaybeNumber(alternative.budget_utilization) ?? 0,
            ticketCount: asMaybeNumber(alternative.ticket_count) ?? 0,
            decisionInputSha256: asString(alternative.decision_input_sha256),
            freezeAt: asString(alternative.freeze_at),
            status: asString(alternative.status),
            frontendSelectable: asBoolean(alternative.frontend_selectable),
          };
        }),
        correctScore: Object.keys(correctScore).length ? {
          status: asString(correctScore.status),
          frontendSelectable: asBoolean(correctScore.frontend_selectable),
        } : undefined,
      };
    }),
  };
}

function transformAdhocMatchEligibility(raw: unknown) {
  const row = asObject(raw);
  const handicap = row.handicap_line;
  return {
    matchIdx: asNumber(row.match_idx),
    matchId: asString(row.match_id),
    league: asString(row.league),
    home: asString(row.home),
    away: asString(row.away),
    handicapLine: typeof handicap === 'number' || typeof handicap === 'string' ? handicap : null,
    kickoffAt: asString(row.kickoff_at_hkt),
    eligible: asBoolean(row.eligible),
    exclusionReasons: asStringList(row.exclusion_reasons),
  };
}

function transformAdhocBettingEligibility(raw: unknown): AdhocBettingEligibilityData {
  const obj = asObject(raw);
  return {
    schemaVersion: asString(obj.schema_version),
    capabilityId: asString(obj.capability_id),
    issueId: asString(obj.issue),
    observedAt: asString(obj.observed_at_hkt),
    inputAsOf: asString(obj.input_asof_hkt),
    status: asString(obj.status),
    eligibleMatchCount: asNumber(obj.eligible_match_count),
    excludedMatchCount: asNumber(obj.excluded_match_count),
    exclusionCounts: asNumberRecord(obj.exclusion_counts),
    matches: asArray(obj.matches).map(transformAdhocMatchEligibility),
    safetyMarginSeconds: asNumber(obj.safety_margin_seconds),
    previewOnly: asBoolean(obj.preview_only),
    researchEvidenceEligible: false,
    scheduledFreezeEventId: null,
  };
}

function transformAdhocBettingPlan(raw: unknown): AdhocBettingPlanData {
  const obj = asObject(raw);
  return {
    schemaVersion: asString(obj.schema_version),
    capabilityId: asString(obj.capability_id),
    requestId: asString(obj.request_id),
    immutableRequestId: asString(obj.immutable_request_id),
    publishedPackageCount: asNumber(obj.published_package_count),
    generationBatchCount: asNumber(obj.generation_batch_count),
    issueId: asString(obj.issue),
    requestedAt: asString(obj.requested_at_hkt),
    inputAsOf: asString(obj.input_asof_hkt),
    requestedN: asNumber(obj.requested_n),
    requestedBudgetYuan: asNumber(obj.requested_budget_yuan),
    baseCostYuan: asNumber(obj.base_cost_yuan),
    actualCostYuan: asNumber(obj.actual_cost_yuan),
    unusedBudgetYuan: asNumber(obj.unused_budget_yuan),
    budgetUtilization: asNumber(obj.budget_utilization),
    validUntil: asString(obj.valid_until_hkt),
    status: asString(obj.status),
    currentStatus: asString(obj.current_status),
    currentStatusRecheckScope: asString(obj.current_status_recheck_scope),
    saleEligibilityScope: asString(obj.sale_eligibility_scope),
    shopSaleConfirmationRequired: asBoolean(obj.shop_sale_confirmation_required),
    structuralVerificationStatus: asString(obj.structural_verification_status),
    saleStatusVerified: asBoolean(obj.sale_status_verified),
    operationalDownloadsEnabled: asBoolean(obj.operational_downloads_enabled),
    auditDownloadsAvailable: asBoolean(obj.audit_downloads_available),
    ticketCount: asNumber(obj.ticket_count),
    eligibleMatchCount: asNumber(obj.eligible_match_count),
    maxTicketOccurrencesPerMatch: asNumber(obj.max_ticket_occurrences_per_match),
    totalMatchOccurrenceCapacity: asNumber(obj.total_match_occurrence_capacity),
    theoreticalTicketCountCap: asNumber(obj.theoretical_ticket_count_cap),
    maxActualTicketOccurrencesPerMatch: asNumber(obj.max_actual_ticket_occurrences_per_match),
    averageTicketOccurrencesPerMatch: asNumber(obj.average_ticket_occurrences_per_match),
    matchOccurrencesSha256: asString(obj.match_occurrences_sha256),
    matchOccurrences: asArray(obj.match_occurrences).map((rawOccurrence) => {
      const occurrence = asObject(rawOccurrence);
      return {
        matchIdx: asNumber(occurrence.match_idx),
        matchId: asString(occurrence.match_id),
        ticketNumbers: asArray(occurrence.ticket_numbers).map(asNumber),
        distinctTicketOccurrenceCount: asNumber(occurrence.distinct_ticket_occurrence_count),
        spendWeightedExposureYuan: asNumber(occurrence.spend_weighted_exposure_yuan),
        spendWeightedExposureRatio: asNumber(occurrence.spend_weighted_exposure_ratio),
      };
    }),
    excludedMatchCount: asNumber(obj.excluded_match_count),
    exclusionCounts: asNumberRecord(obj.exclusion_counts),
    denominator: asArray(obj.denominator).map(transformAdhocMatchEligibility),
    tickets: asArray(obj.tickets).map((rawTicket) => {
      const ticket = asObject(rawTicket);
      return {
        ticketNo: asNumber(ticket.ticket_no),
        actualN: asNumber(ticket.actual_n),
        stakeMultiplier: asNumber(ticket.stake_multiplier),
        baseCostYuan: asNumber(ticket.base_cost_yuan),
        costYuan: asNumber(ticket.cost_yuan),
        legs: asArray(ticket.legs).map((rawLeg) => {
          const leg = asObject(rawLeg);
          const handicap = leg.handicap_line;
          return {
            matchIdx: asNumber(leg.match_idx),
            matchId: asString(leg.match_id),
            selectionCode: asString(leg.selection_code),
            selectionLabel: asString(leg.selection_label),
            kickoffAt: asString(leg.kickoff_at_hkt),
            league: asString(leg.league),
            home: asString(leg.home),
            away: asString(leg.away),
            handicapLine: typeof handicap === 'number' || typeof handicap === 'string' ? handicap : null,
            matchTicketOccurrenceCount: asNumber(leg.match_ticket_occurrence_count),
            matchTicketNumbers: asArray(leg.match_ticket_numbers).map(asNumber),
          };
        }),
      };
    }),
    planReason: asString(obj.plan_reason),
    unavailableReasons: asStringList(obj.unavailable_reasons),
    inputSha256: asString(obj.input_sha256),
    manifestSha256: asString(obj.manifest_sha256),
    packageId: asString(obj.package_id),
    researchEvidenceEligible: false,
    scheduledFreezeEventId: null,
    correctScoreStatus: asString(obj.correct_score_status),
    idempotent: asBoolean(obj.idempotent),
  };
}

function mockAdhocBettingEligibility(issueId: string): AdhocBettingEligibilityData {
  return {
    schemaVersion: 'adhoc_betting_eligibility_preview_v1',
    capabilityId: 'BJ-ADHOC-BET-001',
    issueId,
    observedAt: '2026-07-25T12:00:00+08:00',
    inputAsOf: '2026-07-25T12:00:00+08:00',
    status: 'ELIGIBILITY_PREVIEW',
    eligibleMatchCount: 8,
    excludedMatchCount: 0,
    exclusionCounts: {},
    matches: Array.from({ length: 8 }, (_, index) => ({
      matchIdx: index + 1,
      matchId: `${issueId}_${String(index + 1).padStart(3, '0')}`,
      league: '示例联赛',
      home: `示例主队 ${index + 1}`,
      away: `示例客队 ${index + 1}`,
      handicapLine: null,
      kickoffAt: '2026-07-25T20:30:00+08:00',
      eligible: true,
      exclusionReasons: [],
    })),
    safetyMarginSeconds: 120,
    previewOnly: true,
    researchEvidenceEligible: false,
    scheduledFreezeEventId: null,
  };
}

function mockAdhocBettingPlan(
  issueId: string,
  requestedN: number,
  requestedBudgetYuan: number,
): AdhocBettingPlanData {
  const choices = [
    { matchIdx: 1, matchId: `${issueId}_001`, selectionCode: '3', selectionLabel: '胜', league: '英超', home: '示例主队 A', away: '示例客队 A' },
    { matchIdx: 2, matchId: `${issueId}_002`, selectionCode: '1', selectionLabel: '平', league: '西甲', home: '示例主队 B', away: '示例客队 B' },
    { matchIdx: 3, matchId: `${issueId}_003`, selectionCode: '0', selectionLabel: '负', league: '意甲', home: '示例主队 C', away: '示例客队 C' },
    { matchIdx: 4, matchId: `${issueId}_004`, selectionCode: '3', selectionLabel: '胜', league: '德甲', home: '示例主队 D', away: '示例客队 D' },
    { matchIdx: 5, matchId: `${issueId}_005`, selectionCode: '1', selectionLabel: '平', league: '法甲', home: '示例主队 E', away: '示例客队 E' },
    { matchIdx: 6, matchId: `${issueId}_006`, selectionCode: '0', selectionLabel: '负', league: '荷甲', home: '示例主队 F', away: '示例客队 F' },
    { matchIdx: 7, matchId: `${issueId}_007`, selectionCode: '3', selectionLabel: '胜', league: '葡超', home: '示例主队 G', away: '示例客队 G' },
    { matchIdx: 8, matchId: `${issueId}_008`, selectionCode: '1', selectionLabel: '平', league: '比甲', home: '示例主队 H', away: '示例客队 H' },
  ];
  const legCount = requestedN;
  const ticketCost = 2;
  const tickets = Array.from({ length: 2 }, (_, ticketIndex) => ({
    ticketNo: ticketIndex + 1,
    actualN: legCount,
    stakeMultiplier: 1,
    baseCostYuan: ticketCost,
    costYuan: ticketCost,
    legs: Array.from({ length: legCount }, (_, legIndex) => choices[(ticketIndex + legIndex) % choices.length]).map((choice) => ({
        ...choice,
        kickoffAt: '2026-07-25T20:30:00+08:00',
        handicapLine: null,
      })),
  }));
  const matchOccurrences = choices.map((choice) => {
    const ticketNumbers = tickets
      .filter((ticket) => ticket.legs.some((leg) => leg.matchIdx === choice.matchIdx))
      .map((ticket) => ticket.ticketNo);
    return {
      matchIdx: choice.matchIdx,
      matchId: choice.matchId,
      ticketNumbers,
      distinctTicketOccurrenceCount: ticketNumbers.length,
      spendWeightedExposureYuan: ticketNumbers.length * ticketCost,
      spendWeightedExposureRatio: ticketNumbers.length / tickets.length,
    };
  });
  tickets.forEach((ticket) => {
    ticket.legs.forEach((leg) => {
      const occurrence = matchOccurrences.find((item) => item.matchIdx === leg.matchIdx);
      Object.assign(leg, {
        matchTicketOccurrenceCount: occurrence?.distinctTicketOccurrenceCount || 0,
        matchTicketNumbers: occurrence?.ticketNumbers || [],
      });
    });
  });
  const actualCostYuan = tickets.reduce((total, ticket) => total + ticket.costYuan, 0);
  const requestId = `mock-${issueId}-n${legCount}-b${requestedBudgetYuan}`;
  return {
    schemaVersion: 'adhoc_betting_package_v2',
    capabilityId: 'BJ-ADHOC-BET-001',
    requestId,
    immutableRequestId: requestId,
    publishedPackageCount: 1,
    generationBatchCount: 1,
    issueId,
    requestedAt: '2026-07-25T12:00:00+08:00',
    inputAsOf: '2026-07-25T12:00:00+08:00',
    requestedN: legCount,
    requestedBudgetYuan,
    baseCostYuan: tickets.reduce((total, ticket) => total + ticket.baseCostYuan, 0),
    actualCostYuan,
    unusedBudgetYuan: requestedBudgetYuan - actualCostYuan,
    budgetUtilization: actualCostYuan / requestedBudgetYuan,
    validUntil: '2026-07-25T20:28:00+08:00',
    status: 'READY_FOR_REVIEW',
    currentStatus: 'DOWNLOADABLE_CURRENT',
    currentStatusRecheckScope: 'VALID_UNTIL_SERVER_CLOCK_ONLY',
    saleEligibilityScope: 'GENERATION_TIME_SNAPSHOT_ONLY',
    shopSaleConfirmationRequired: true,
    structuralVerificationStatus: 'STRUCTURAL_INTEGRITY_PASS',
    saleStatusVerified: true,
    operationalDownloadsEnabled: true,
    auditDownloadsAvailable: true,
    ticketCount: tickets.length,
    eligibleMatchCount: 8,
    maxTicketOccurrencesPerMatch: 2,
    totalMatchOccurrenceCapacity: 16,
    theoreticalTicketCountCap: Math.floor(16 / legCount),
    maxActualTicketOccurrencesPerMatch: Math.max(...matchOccurrences.map((item) => item.distinctTicketOccurrenceCount)),
    averageTicketOccurrencesPerMatch: (tickets.length * legCount) / choices.length,
    matchOccurrencesSha256: 'mock-occurrences-sha256',
    matchOccurrences,
    excludedMatchCount: 0,
    exclusionCounts: {},
    denominator: choices.map((choice) => ({
      ...choice,
      handicapLine: null,
      kickoffAt: '2026-07-25T20:30:00+08:00',
      eligible: true,
      exclusionReasons: [],
    })),
    tickets,
    planReason: 'mock exact-N portfolio',
    unavailableReasons: [],
    inputSha256: 'mock-current-input-sha256',
    manifestSha256: 'mock-adhoc-manifest-sha256',
    packageId: 'mock-adhoc-package-id',
    researchEvidenceEligible: false,
    scheduledFreezeEventId: null,
    correctScoreStatus: 'UNAVAILABLE_ADHOC_CORRECT_SCORE',
    idempotent: false,
  };
}

export class ApiDashboardAdapter {
  private mode: AdapterMode;
  private baseUrl: string;

  constructor(options: { mode?: AdapterMode; baseUrl?: string } = {}) {
    this.mode = options.mode ?? 'fetch';
    this.baseUrl = options.baseUrl ?? '';
  }

  private async getJson<T>(path: string, fallback: T, transform: (payload: unknown) => T = (payload) => payload as T): Promise<T> {
    if (this.mode === 'mock') return fallback;
    const response = await fetch(`${this.baseUrl}${path}`);
    if (!response.ok) throw new Error(`API ${path} failed: ${response.status}`);
    return transform(await response.json());
  }

  private async postJson<T>(
    path: string,
    fallback: T,
    transform: (payload: unknown) => T = (payload) => payload as T,
    body?: unknown,
  ): Promise<T> {
    if (this.mode === 'mock') return fallback;
    const headers = operatorTokenHeaders();
    const request = body === undefined
      ? { method: 'POST', headers }
      : {
        method: 'POST',
        headers: (() => {
          const requestHeaders = new Headers(headers);
          requestHeaders.set('Content-Type', 'application/json');
          return requestHeaders;
        })(),
        body: JSON.stringify(body),
      };
    const response = await fetch(`${this.baseUrl}${path}`, request);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = asString(asObject(payload).error, `API ${path} failed: ${response.status}`);
      throw new Error(message);
    }
    return transform(payload);
  }

  getIssueDashboard(issueId: string, decisionVariantId?: string, options: { summary?: boolean } = {}): Promise<IssueDashboardData> {
    const path = options.summary ? `/api/issues/${issueId}/dashboard?view=summary` : `/api/issues/${issueId}/dashboard`;
    return this.getJson(withDecisionVariant(path, decisionVariantId), mockDashboardData.issue, transformIssueDashboard);
  }

  getAvailableIssues(options: { limit?: number; includeReplay?: boolean } = {}): Promise<IssueOption[]> {
    const limit = options.limit ?? 120;
    const params = new URLSearchParams({ limit: String(limit) });
    if (options.includeReplay === false) params.set('include_replay', '0');
    return this.getJson(`/api/issues?${params.toString()}`, mockDashboardData.availableIssues, (payload) => asArray(asObject(payload).issues).map(transformIssueOption));
  }

  getMatchDetail(_issueId: string, matchId: string, decisionVariantId?: string): Promise<MatchDetailData> {
    return this.getJson(withDecisionVariant(`/api/matches/${matchId}`, decisionVariantId), mockDashboardData.matchDetail, transformMatchDetail);
  }

  confirmDecisionSnapshot(matchId: string): Promise<DecisionSnapshotConfirmResult> {
    return this.postJson(
      `/api/matches/${matchId}/decision-snapshot/confirm`,
      {
        action: 'mock_confirm_disabled',
        confirmedAt: '',
        previousActive: mockDashboardData.matchDetail.decisionSnapshot,
        active: mockDashboardData.matchDetail.draftDecisionSnapshot ?? mockDashboardData.matchDetail.decisionSnapshot,
      },
      transformDecisionSnapshotConfirm,
    );
  }

  getDecisionArtifactStatus(issueId: string, decisionVariantId?: string): Promise<DecisionArtifactStatusData> {
    return this.getJson(
      withArtifactVariant(`/api/issues/${issueId}/decision-artifacts/status`, decisionVariantId),
      mockDashboardData.issue.decisionArtifactStatus!,
      transformDecisionArtifactStatus,
    );
  }

  generateDecisionArtifact(issueId: string, decisionVariantId?: string): Promise<DecisionArtifactGenerateResult> {
    return this.postJson(
      withArtifactVariant(`/api/issues/${issueId}/decision-artifacts/generate`, decisionVariantId),
      {
        issueId,
        variantId: decisionVariantId ?? DEFAULT_DECISION_VARIANT_ID,
        artifactVariantId: 'shadow_v3.3.3',
        status: 'mock_generated',
        materializeSnapshots: true,
        artifactStatus: mockDashboardData.issue.decisionArtifactStatus!,
      },
      transformDecisionArtifactGenerate,
    );
  }

  getTicketDraft(issueId: string): Promise<TicketData> {
    return this.getJson(`/api/issues/${issueId}/tickets?status=candidate`, mockDashboardData.ticket, transformTicket);
  }

  getLiveSignals(issueId: string): Promise<LiveSignalsData> {
    return this.getJson(`/api/issues/${issueId}/signals`, mockDashboardData.liveSignals, transformLiveSignals);
  }

  getSettlementReview(issueId: string, decisionVariantId?: string): Promise<SettlementData> {
    return this.getJson(withDecisionVariant(`/api/issues/${issueId}/settlement`, decisionVariantId), mockDashboardData.settlement, transformSettlement);
  }

  getStrategyLab(): Promise<StrategyLabData> {
    return this.getJson('/api/strategies/lab', mockDashboardData.strategyLab, transformStrategyLab);
  }

  getSelectorShadow(issueId: string): Promise<SelectorShadowData> {
    return this.getJson(`/api/issues/${issueId}/selector-shadow`, mockDashboardData.selectorShadow, transformSelectorShadow);
  }

  getMainStrategy(issueId: string, decisionVariantId?: string): Promise<MainStrategyData> {
    return this.getJson(withDecisionVariant(`/api/issues/${issueId}/main-strategy`, decisionVariantId), mockDashboardData.mainStrategy, transformMainStrategy);
  }

  getSegmentBettingPlan(
	    issueId: string,
	    decisionVariantId?: string,
	    planId?: string,
	    options?: {
	      planningScope?: string;
	      segmentBudgetYuan?: string | number;
	      stakeMode?: string;
	      bettingStrategyVersion?: string;
	      label?: string;
	    },
	  ): Promise<SegmentBettingPlanData> {
	    const basePath = withDecisionVariant(`/api/issues/${issueId}/segment-betting-plan`, decisionVariantId);
	    const params = new URLSearchParams();
	    if (planId) params.set('plan_id', planId);
	    if (options?.planningScope) params.set('planning_scope', options.planningScope);
	    if (options?.segmentBudgetYuan !== undefined && `${options.segmentBudgetYuan}`.trim()) params.set('segment_budget_yuan', `${options.segmentBudgetYuan}`.trim());
	    if (options?.stakeMode) params.set('stake_mode', options.stakeMode);
	    if (options?.bettingStrategyVersion) params.set('betting_strategy_version', options.bettingStrategyVersion);
	    if (options?.label) params.set('label', options.label);
    const suffix = params.toString();
    const path = suffix ? `${basePath}${basePath.includes('?') ? '&' : '?'}${suffix}` : basePath;
    return this.getJson(path, mockDashboardData.segmentBettingPlan, transformSegmentBettingPlan);
  }

  getExactNFreezes(issueId: string): Promise<ExactNFreezeData> {
    return this.getJson(
      `/api/issues/${issueId}/exact-n-freezes`,
      mockDashboardData.exactNFreezes,
      transformExactNFreezes,
    );
  }

  getOperationsStatus(issueId: string): Promise<OperationsStatusData> {
    return this.getJson(`/api/issues/${issueId}/operations`, mockDashboardData.operations, transformOperationsStatus);
  }

  getAdhocBettingEligibility(issueId: string): Promise<AdhocBettingEligibilityData> {
    const issue = encodeURIComponent(issueId);
    return this.getJson(
      `/api/adhoc-betting-plans/eligibility?issue=${issue}`,
      mockAdhocBettingEligibility(issueId),
      transformAdhocBettingEligibility,
    );
  }

  createAdhocBettingPlan(request: {
    issueId: string;
    requestedN: number;
    requestedBudgetYuan: number;
    idempotencyKey: string;
  }): Promise<AdhocBettingPlanData> {
    return this.postJson(
      '/api/adhoc-betting-plans',
      mockAdhocBettingPlan(request.issueId, request.requestedN, request.requestedBudgetYuan),
      transformAdhocBettingPlan,
      {
        issue: request.issueId,
        requested_n: request.requestedN,
        requested_budget_yuan: request.requestedBudgetYuan,
        idempotency_key: request.idempotencyKey,
      },
    );
  }

  getAdhocBettingPlan(requestId: string): Promise<AdhocBettingPlanData> {
    const encodedId = encodeURIComponent(requestId);
    return this.getJson(
      `/api/adhoc-betting-plans/${encodedId}`,
      mockAdhocBettingPlan('mock', 3, 512),
      transformAdhocBettingPlan,
    );
  }

  adhocBettingDownloadUrl(
    requestId: string,
    format: 'pdf' | 'html' | 'csv',
    auditOnly = false,
  ): string {
    const endpoint = auditOnly ? 'audit-download' : 'download';
    return `${this.baseUrl}/api/adhoc-betting-plans/${encodeURIComponent(requestId)}/${endpoint}?format=${format}`;
  }

  async getDashboardShell(issueId: string, decisionVariantId?: string): Promise<Pick<DashboardData, 'availableIssues' | 'issue'>> {
    if (this.mode === 'mock') return { availableIssues: mockDashboardData.availableIssues, issue: mockDashboardData.issue };
    const [availableIssues, issue] = await Promise.all([
      this.getAvailableIssues({ includeReplay: false }),
      this.getIssueDashboard(issueId, decisionVariantId, { summary: true }),
    ]);
    const resolvedIssueId = issue.issueId || issueId;
    const decisionArtifactStatus = await this.getDecisionArtifactStatus(resolvedIssueId, decisionVariantId).catch(() => undefined);
    return { availableIssues, issue: decisionArtifactStatus ? { ...issue, decisionArtifactStatus } : issue };
  }

  runPostmatchReview(issueId: string, dryRun: boolean): Promise<OperationsStatusData['review']['task']> {
    return this.postJson(
      `/api/issues/${issueId}/postmatch-review?dry_run=${dryRun ? '1' : '0'}`,
      mockDashboardData.operations.review.task,
      (payload) => transformOperationsStatus({ issue: issueId, review: { task: payload } }).review.task,
    );
  }

  async getDashboardData(issueId: string, matchId?: string, decisionVariantId?: string): Promise<DashboardData> {
    if (this.mode === 'mock') return mockDashboardData;
    const [availableIssues, issue] = await Promise.all([
      this.getAvailableIssues(),
      this.getIssueDashboard(issueId, decisionVariantId),
    ]);
    const resolvedIssueId = issue.issueId || issueId;
    const settlementIssueId = chooseSettlementIssueId(availableIssues, resolvedIssueId);
    const resolvedMatchId = matchId ?? issue.matches[0]?.matchId;
    if (!resolvedMatchId) throw new Error(`No matches available for issue ${issue.issueId}`);
    const [decisionArtifactStatus, matchDetail, ticket, liveSignals, settlement, strategyLab, selectorShadow, mainStrategy, operations, segmentBettingPlan, exactNFreezes] = await Promise.all([
      this.getDecisionArtifactStatus(resolvedIssueId, decisionVariantId).catch(() => undefined),
      this.getMatchDetail(resolvedIssueId, resolvedMatchId, decisionVariantId),
      this.getTicketDraft(resolvedIssueId),
      this.getLiveSignals(resolvedIssueId),
      this.getSettlementReview(settlementIssueId, decisionVariantId).catch((error: unknown) => {
        if (error instanceof Error && error.message.includes('404')) return emptySettlement(settlementIssueId);
        throw error;
      }),
      this.getStrategyLab(),
      this.getSelectorShadow(resolvedIssueId),
      this.getMainStrategy(resolvedIssueId, decisionVariantId),
      this.getOperationsStatus(resolvedIssueId),
      this.getSegmentBettingPlan(resolvedIssueId, decisionVariantId),
      this.getExactNFreezes(resolvedIssueId),
    ]);
    return {
      availableIssues,
      issue: decisionArtifactStatus ? { ...issue, decisionArtifactStatus } : issue,
      matchDetail,
      ticket,
      liveSignals,
      settlement,
      strategyLab,
      selectorShadow,
      mainStrategy,
      operations,
      segmentBettingPlan,
      exactNFreezes,
    };
  }
}
