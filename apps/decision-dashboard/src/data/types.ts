export type ScrapeStatus = 'ok' | 'partial' | 'missing' | 'failed' | 'stale';
export type CoverageType = 'single' | 'double' | 'full' | 'no-buy';
export type CandidateRole = 'core' | 'protect' | 'watch' | 'avoid';

export interface DecisionVariantOption {
  variantId: string;
  kind?: 'active' | 'shadow' | 'other' | string;
  family?: string;
  label: string;
  displayLabel?: string;
  version: string;
  versionId?: string;
  source: string;
  sourcePath?: string;
  artifactKey?: string;
  isDefault?: boolean;
  selectable?: boolean;
  available?: boolean;
  defaultable?: boolean;
  readinessStatus?: string;
  degradedReason?: string;
}

export interface DecisionVariantData extends DecisionVariantOption {
  recommendation: string;
  primaryPick?: string;
  protectPicks: string[];
  selectionCodes: string[];
  selectionType: CoverageType;
  stopFlag: boolean;
  qScore?: number;
  probability?: number;
  confidenceLabel?: string;
  predictionHit?: boolean | null;
  primaryHit?: boolean | null;
  coverageHit?: boolean | null;
  notes?: string[];
  executionPolicyVersion?: string;
  executionPolicyName?: string;
  executionAction?: string;
  executionReasons?: string[];
  executionSourceAction?: string;
  executionRecommendedCodes?: string;
  executionDoubleCodes?: string;
  executionFullScore?: number;
  executionFullCandidate?: boolean | null;
  executionFullKept?: boolean | null;
  executionSegmentIdx?: number;
  executionUnlockState?: string;
  sourceSp?: Record<string, number>;
  sourceQ?: Record<string, number>;
  executionSp?: Record<string, number>;
  executionQ?: Record<string, number>;
  executionSpSource?: string;
  executionSpSnapshotTs?: string;
  executionSpRepriced?: boolean | null;
  executionSpRepriceRatioMax?: number;
  executionSpMissing?: boolean | null;
  decisionChain?: string[];
  decisionCategories?: Array<{
    key: string;
    label: string;
    result: string;
    score?: string;
    verdict?: string;
    evidence?: string[];
  }>;
}

export interface StrategyVersionContext {
  schemaVersion: string;
  requestedVariantId: string;
  selectedVariantId: string;
  selectionStatus: 'ok' | 'degraded' | 'unavailable' | string;
  selectionError?: string;
  availableVariantIds: string[];
  options: DecisionVariantOption[];
  contractWarnings: Array<{ type: string; variantIds: string[]; message: string }>;
  strategyRelease?: {
    releaseId: string;
    activeReleaseId: string;
    versionId: string;
    generatedAt: string;
    effectiveFromIssue: string;
    loadStatus: string;
    loadError?: string;
    fallbackUsed: boolean;
    missingRequiredCount: number;
  };
}

export interface IssueOption {
  issueId: string;
  label: string;
  status: string;
  source: string;
  isCurrent: boolean;
  year?: number;
  matchCount?: number;
  settledMatchCount?: number;
  openMatchCount?: number;
  isFullySettled?: boolean;
  hasSettlement?: boolean;
  lastSeenAt: string;
  issueCloseTs: string;
}

export interface IssueMatchRow {
  matchId: string;
  matchIdx?: number;
  league: string;
  kickoffDate: string;
  kickoffTime: string;
  home: string;
  away: string;
  handicap: number;
  score?: string;
  halftimeScore?: string;
  scoreStatus?: string;
  scoreStatusText?: string;
  sp: { win?: number; draw?: number; loss?: number };
  euro: { home?: number; draw?: number; away?: number };
  asia: { line?: number | string; homeOdds?: number; awayOdds?: number };
  lineGap?: number;
  drift: { win?: number; draw?: number; loss?: number; direction: string };
  scrapeStatus: ScrapeStatus;
  qScore?: number;
  confidence?: number;
  modelProb: { win?: number; draw?: number; loss?: number };
  modelEdgeBestOutcome: string;
  modelRecommendedOutcome?: string;
  recommendedOutcome: string;
  primaryBetOutcome?: string;
  protectionOutcomes?: string[];
  recommendedCoverage: CoverageType;
  stopFlag?: boolean;
		  recommendationSource?: string;
		  recommendationConfidenceLabel?: string;
		  decisionVariants?: DecisionVariantData[];
  selectedDecisionVariantId?: string;
  selectedDecisionVariantStatus?: string;
  selectedDecisionVariant?: DecisionVariantData;
		  candidateRole: CandidateRole;
	  resultCode?: string;
  resultLabel?: string;
  predictionHit?: boolean | null;
  settlementSp?: number;
  qInputSpSnapshotAt?: string;
  qInputProbabilitySnapshotAt?: string;
  qCalculatedAt?: string;
  decisionSnapshotId?: string;
	  decisionSnapshotStatus?: string;
	  decisionSnapshotGeneratedAt?: string;
	  decisionSnapshotCheckedAt?: string;
	  draftDecisionSnapshotId?: string;
	  postmatchReviewOutcome?: string;
	  postmatchReviewSummary?: string;
	  postmatchReviewTags?: string[];
	  postmatchReviewAction?: string;
	  postmatchReviewProfit?: number;
	  postmatchReviewReviewedAt?: string;
	  status: 'open' | 'settled';
	  llmAssistSummary: string;
	  riskTags: string[];
	  updatedAt: string;
	}

export interface DecisionSnapshotData {
  snapshotId: string;
  status: 'active' | 'draft_replacement' | 'superseded' | string;
  generatedAt: string;
  checkedAt: string;
  confirmedAt?: string;
  supersededAt?: string;
  supersedesSnapshotId?: string;
  inputHash: string;
  recommendation: string;
  primaryPick?: string;
  protectPicks: string[];
  stopFlag: boolean;
  selectionCodes: string[];
	  confidence?: number;
	  confidenceLabel?: string;
	  qScore?: number;
	  probability?: number;
	  promptVersion: string;
	  modelVersion: string;
	  probModelVersion?: string;
	  qModelVersion?: string;
	  decisionChainVersion?: string;
	  decisionConfigHash?: string;
	  reviewTagVersion?: string;
	}

export interface DecisionSnapshotConfirmResult {
  action: string;
  confirmedAt?: string;
  previousActive?: DecisionSnapshotData;
  active?: DecisionSnapshotData;
  error?: string;
}

export interface DecisionArtifactCompleteness {
  issue: string;
  scope: string;
  complete: boolean;
  expectedCount: number;
  actualCount: number;
  expectedMatchIdx: number[];
  actualMatchIdx: number[];
  missingMatchIdx: number[];
  extraMatchIdx: number[];
}

export interface DecisionArtifactStatusData {
  issueId: string;
  requestedVariantId: string;
  variantId: string;
  artifactVariantId: string;
  status: 'available' | 'missing' | 'incomplete' | 'unsupported' | string;
  message: string;
  generationSupported: boolean;
  sourcePath: string;
  rowCount: number;
  expectedMatchCount: number;
  completeness: DecisionArtifactCompleteness;
  snapshotCompleteness: DecisionArtifactCompleteness;
  latestWorkflow?: {
    runId: string;
    status: string;
    startedAt: string;
    finishedAt: string;
  };
  latestGenerationStep?: {
    stepIdx?: number;
    stepKey?: string;
    label?: string;
    status?: string;
    startedAt?: string;
    finishedAt?: string;
    error?: string;
  };
}

export interface DecisionArtifactGenerateResult {
  issueId: string;
  variantId: string;
  artifactVariantId: string;
  status: string;
  materializeSnapshots: boolean;
  artifactStatus: DecisionArtifactStatusData;
}

	export interface PostmatchReviewData {
	  issue: string;
	  matchIdx: number;
	  matchId: string;
	  reviewVersion: string;
	  tagVersion?: string;
	  reviewedAt: string;
	  decisionSnapshotId?: string;
	  decisionSnapshotGeneratedAt?: string;
	  outcomeLabel: string;
	  summary: string;
	  actionSuggestion: string;
	  tags: string[];
	  primaryHit: boolean;
	  protectHit: boolean;
	  coverageHit: boolean;
	  stopped: boolean;
	  stake: number;
	  grossReturn: number;
	  profit: number;
	  roi: number;
	}

export interface IssueDashboardData {
  issueId: string;
  issueDate: string;
  salesDeadline: string;
  matchCount: number;
  candidateCount: number;
  qualifiedCandidateCount: number;
  dataCompleteRate: number;
  lastScrapedAt: string;
  settlementStatus: 'open' | 'settled' | 'reviewed';
  recommendedAction: 'build-ticket' | 'watch' | 'no-bet';
  funnel: Array<{ label: string; count: number }>;
  quality: { grade: string; risks: string[]; score: number; poolQualityFlag: 'green' | 'yellow' | 'red' };
		  matches: IssueMatchRow[];
		  decisionVariantOptions?: DecisionVariantOption[];
  strategyVersionContext?: StrategyVersionContext;
  decisionArtifactStatus?: DecisionArtifactStatusData;
		  llmAssistSummary: string;
		}

export interface OddsConsensus {
  nCompanies: number;
  openAvg: { home?: number; draw?: number; away?: number };
  currentAvg: { home?: number; draw?: number; away?: number };
  drift: { home?: number; draw?: number; away?: number };
  providers: Array<{
    company: string;
    open: { home?: number; draw?: number; away?: number };
    current: { home?: number; draw?: number; away?: number };
  }>;
}

export interface MatchDetailData {
  matchId: string;
  issueId: string;
  league: string;
  home: string;
  away: string;
  kickoffTime: string;
  salesDeadline: string;
  handicap: number;
  score?: string;
  halftimeScore?: string;
  scoreStatus?: string;
  scoreStatusText?: string;
  resultLabel?: string;
  predictionHit?: boolean | null;
  settlementSp?: number;
  status: 'open' | 'settled';
  sp: IssueMatchRow['sp'];
  euro: IssueMatchRow['euro'];
  asia: IssueMatchRow['asia'];
  lineGap?: number;
  scrapeStatus: ScrapeStatus;
  resultStatus: string;
  modelVersion: string;
  probabilityCalibratedAt: string;
  qInputSpSnapshotAt?: string;
  qInputProbabilitySnapshotAt?: string;
  qCalculatedAt?: string;
	  qInputPolicy?: string;
	  decisionSnapshot?: DecisionSnapshotData;
	  draftDecisionSnapshot?: DecisionSnapshotData;
			  postmatchReview?: PostmatchReviewData;
			  decisionVariants?: DecisionVariantData[];
			  decisionVariantOptions?: DecisionVariantOption[];
  strategyVersionContext?: StrategyVersionContext;
			  selectedOutcomes: string[];
  recommendedAction: 'buy' | 'protect' | 'no-buy' | 'watch';
  recommendedCoverage: CoverageType;
  noBuyReason?: string;
  buyExplanation: string;
  protectExplanation: string;
  humanOverrideReason?: string;
  oddsTimeline: Array<{ at: string; sp: string; lineGap: number; drift: string }>;
  oddsConsensus?: OddsConsensus;
  marketHighlights: string[];
  llm: { summaryId: string; model: string; generatedAt: string; direction: string; confidenceLabel: string; injury: string; schedule: string; motivation: string; support: string[]; risks: string[]; source: string };
  llmSelectedOutcomes: string[];
  llmPrimaryOutcome?: string;
  llmProtectionOutcomes: string[];
  llmStopped: boolean;
  llmDecisionChain?: string[];
  probability: IssueMatchRow['modelProb'];
  impliedProbability: IssueMatchRow['modelProb'];
  edge: IssueMatchRow['modelProb'];
  qScore: number;
  confidence: number;
  analysis500?: {
    status: string;
    fetchedAt: string;
    title: string;
    description: string;
    urls: { data?: string; recommendation?: string; asian?: string; europe?: string };
    homeRecent: { team: string; summary: string; rows: Array<Record<string, string>> };
    awayRecent: { team: string; summary: string; rows: Array<Record<string, string>> };
    h2h: { summary: string; rows: Array<Record<string, string>> };
    leagueTable: string;
    source: string;
    highlights?: string[];
    marketSummary?: string;
    oddsConsensus?: OddsConsensus;
    error?: string;
  };
  intelligence?: {
    status: string;
    fetchedAt: string;
    headline: string;
    points: string[];
    tags: string[];
    stage: {
      competitionLabel?: string;
      stageName?: string;
      stageType?: string;
      group?: string;
      round?: string;
      homeStanding?: string;
      awayStanding?: string;
    };
    sources: Array<{
      source: string;
      tier: string;
      status: string;
      title: string;
      url: string;
      error?: string;
    }>;
    sourceCount: number;
    error?: string;
  };
}

export interface TicketData {
  ticketId: string;
  issueId: string;
  ticketName: string;
  status: 'draft' | 'exported' | 'submitted' | 'settled';
  allocatorArm: string;
  budgetTier: string;
  totalBudget: number;
  usedBudget: number;
  baseStake: number;
  multiplier: string;
  totalCombinations: number;
  expectedReturn: number;
  expectedRoi: number;
  maxPayout: number;
  worstCaseLoss: number;
  riskScore: string;
  concentrationScore: number;
  protectionDepth: number;
  spDriftSensitivity: string;
  legs: Array<{ legId: string; matchId: string; label: string; handicap: number; selectedOutcomes: string[]; coverageType: CoverageType; spSelected: string; modelProbSelected: string; qScore: number; confidence: number; role: CandidateRole; riskTags: string[]; overrideReason?: string }>;
}

export interface LiveSignalsData {
  issueId: string;
  timeToDeadline: string;
  lastGlobalScrapeAt: string;
  nextScrapeAt: string;
  sourceHealthScore: number;
  staleSourceCount: number;
  failedSourceCount: number;
  sources: Array<{ sourceName: string; status: ScrapeStatus | 'running'; lastSuccessAt: string; latencySeconds: number; errorMessage?: string; recordCount: number }>;
  alerts: Array<{ alertId: string; matchId: string; alertType: 'sp_drift' | 'line_gap_jump' | 'source_failed' | 'model_changed' | 'llm_updated'; severity: 'low' | 'medium' | 'high'; beforeValue: string; afterValue: string; threshold: string; detectedAt: string; affectedTicketIds: string[]; recommendedAction: string }>;
  ticketImpacts: Array<{ ticketId: string; status: string; affectedLegCount: number; evBefore: number; evAfter: number; riskBefore: string; riskAfter: string; staleSnapshotFlag: boolean; repriceRequiredFlag: boolean }>;
}

export interface SettlementData {
  issueId: string;
  settledAt: string;
  decisionVariantOptions?: DecisionVariantOption[];
  strategyVersionContext?: StrategyVersionContext;
  ticketCount: number;
  totalStake: number;
  grossReturn: number;
  netReturn: number;
  roi: number;
  candidatePoolQuality: 'Good' | 'Mixed' | 'Poor';
  reviewStatus: 'review_draft' | 'reviewed';
  postmatchSummary?: {
    reviewVersion: string;
    reviewedAt: string;
    reviewCount: number;
    stake: number;
    grossReturn: number;
    profit: number;
    roi: number;
    primaryHits: number;
    protectHits: number;
    coverageHits: number;
    stoppedCorrect: number;
    stoppedWrong: number;
    tagCounts: Record<string, number>;
  };
  postmatchReviews: Array<{
    matchIdx: number;
    matchId: string;
    league: string;
    home: string;
    away: string;
    kickoffTime: string;
    score: string;
    halftimeScore: string;
    resultLabel: string;
    winningSp?: number;
    selectedOutcomes: string[];
    llmJudgment: string;
    outcomeLabel: string;
    primaryHit: boolean;
    protectHit: boolean;
    coverageHit: boolean;
    stopped: boolean;
    stake: number;
    grossReturn: number;
    profit: number;
    roi: number;
    tags: string[];
    summary: string;
    actionSuggestion: string;
    reviewedAt: string;
  }>;
  ticketResults: Array<{ ticketId: string; ticketType: string; legCount: number; hitLegs: number; missedByLegs: number; missedProtection: number; stake: number; payout: number; conclusion: string }>;
  legReviews: Array<{ matchId: string; selectedOutcomes: string[]; actualResult: string; hit: boolean; coverageType: CoverageType; spAtBuild: string; spAtSettlement: string; spDrift: string; qScoreAtBuild: number; confidenceAtBuild: number; llmRiskTagsAtBuild: string[]; protectionRecommended: boolean; protectionTaken: boolean; missedProtection: boolean; tags: string[] }>;
  poolQualityReason: string;
  errorTags: string[];
}

export interface StrategyLabData {
  arms: Array<{ armId: string; armName: string; active: boolean; roi: number; profit: number; hitRate: number; maxDrawdown: number; equityCurve: number[]; recentRoi: number; description: string }>;
  annualPerformance: Array<{ armId: string; year: number; issueCount: number; ticketCount: number; totalStake: number; grossReturn: number; netReturn: number; roi: number; maxDrawdown: number; hitTicketRate: number }>;
  failureClusters: Array<{ errorTag: string; count: number; stakeImpact: number; roiImpact: number; topIssues: string[] }>;
  guardrail: string;
}

export interface SelectorShadowData {
  issueId: string;
  ruleName: string;
  mode: 'paper' | 'live-shadow' | 'candidate';
  generatedAt: string;
  currentDecision: {
    chosenArm: string;
    baselineArm: string;
    defensiveArm: string;
    stateSignal: boolean;
    qualitySignal: boolean;
    reason: string;
    preLossStreak: number;
    preDrawdownUnits: number;
    weakCount: number;
    weakScore: number;
    qualityHistoryIssues: number;
    budgetUnits: number;
  };
  featureFlags: Array<{ feature: string; value: number | string; threshold: number | string; weak: boolean; severity: number }>;
  arms: Array<{
    armId: string;
    label: string;
    role: 'baseline' | 'state' | 'selector' | 'defensive';
    profitPer256: number;
    roi: number;
    maxDrawdownUnits: number;
    maxLossStreak: number;
    issueWinRate: number;
    fullLossRate: number;
    recentProfitPer256: number;
    deltaProfitPer256VsBase: number;
    deltaMaxDrawdownUnitsVsBase: number;
    deltaLossStreakVsBase: number;
  }>;
  switchAttribution: Array<{ group: string; count: number; deltaVsBaseUnits: number; helped: number; hurt: number; flat: number }>;
  rollingStability: Array<{ window: number; profitPositiveRate: number; maxDrawdownPositiveRate: number; bothPositiveRate: number; avgProfitDelta: number; avgMaxDrawdownDelta: number; avgLossStreakDelta: number }>;
  recentDecisions: Array<{ issueId: string; year: number; chosenArm: string; reason: string; deltaVsBaseUnits: number; baseProfitUnits: number; selectorProfitUnits: number; weakCount: number; preLossStreak: number; preDrawdownUnits: number; outcome: 'helped' | 'hurt' | 'flat' }>;
  guardrail: string;
}

export interface MainStrategyData {
  issueId: string;
  generatedAt: string;
  mode: 'historical_replay' | 'live_monitoring';
  strategyFamily: string;
  decisionVariantOptions?: DecisionVariantOption[];
  strategyVersionContext?: StrategyVersionContext;
  candidates: Array<{
    armId: string;
    label: string;
    role: 'stable' | 'convex';
    recommendedFor: string;
    issueBudget: number;
    extraBudget: number;
    stakeUnits: number;
    profitUnits: number;
    profitPer256: number;
    roi: number;
    issueWinRate: number;
    nonFullLossRate: number;
    fullLossRate: number;
    maxDrawdownUnits: number;
    maxDrawdownPer256: number;
    maxLossStreak: number;
    maxDeadStreak: number;
    recentProfitPer256: number;
    recentRoi: number;
    allocation: string;
    rationale: string;
    riskTags: string[];
  }>;
  annualPerformance: Array<{ armId: string; year: number; issueCount: number; stakeUnits: number; profitUnits: number; roi: number; issueWinRate: number; nonFullLossRate: number; maxDrawdownUnits: number }>;
  evPool: {
    available: boolean;
    status: string;
    source: string;
    ticketCount: number;
    tickets: Array<{
      ticketId: string;
      ticketIdx: number;
      sourceStrategy: string;
      nLegs: number;
      stakeUnits: number;
      predEvPerStake: number;
      predHitProb: number;
      hit?: boolean | null;
      payoutUnits: number;
      profitUnits: number;
      topology: string;
      avgQScore: number;
      avgConfidenceWeight: number;
      lineGapSupportNet: number;
      avgAbsLineGap: number;
      diagnosticTags: string[];
      legs: Array<{
        legId: string;
        matchId: string;
        label: string;
        handicap?: number;
        beidanHandicap?: number;
        asian1hLine?: number;
        lineGap?: number;
        selectionCode: string;
        selectionLabel: string;
        resultCode: string;
        resultLabel: string;
        hit?: boolean | null;
        winningSp?: number;
        qScore?: number;
        confidenceWeight?: number;
        selectedModelP?: number;
        selectedMarketP?: number;
        predSpMultiplier?: number;
        diagnosticTags: string[];
      }>;
    }>;
  };
  liveProxy?: { available: boolean; status: string; source: string; ticketCount: number; tickets: unknown[] } | null;
  riskState: {
    latestBacktestIssue: string;
    riskLevel: 'normal' | 'watch' | 'defensive';
    recommendedArm: string;
    reason: string;
    cooldown: { state: string; policy: string; preLossStreak: number; preDrawdownUnits: number };
    budget: { mode: string; selectedUnits: number; baseUnits: number; extraUnits: number; notes: string };
    guardrails: string[];
  };
  diagnostics: {
    lineGapPolicy: string;
    spDriftPolicy: string;
    paperArms: Array<{ armId: string; issues: number; profitPer256: number; roi: number; issueWinRate: number; nonFullLossRate: number; maxDrawdownUnits: number; maxLossStreak: number; productionStatus: string }>;
  };
  review: {
    issues: Array<{
      issueId: string;
      issueOrder: number;
      calendarYear: number;
      issueCloseTs: string;
      arms: Array<{ armId: string; stakeUnits: number; profitUnits: number; roi: number; tickets: number; hits: number; parts: string; state: string; allocation: string }>;
    }>;
    source: string;
  };
  source: { mainStrategyDir: string; ticketPoolDir: string; modelDb: string; liveDb: string; noFutureLeakage: string };
}

export interface OperationsStatusData {
  schemaVersion: string;
  issueId: string;
  generatedAt: string;
  summary: {
    status: string;
    blockerCount: number;
    warningCount: number;
    nextActionAt: string;
    nextActionTitle: string;
    message: string;
  };
  domains: {
    runtime: {
      status: string;
      checkedAt: string;
      accessMode: string;
      externalAccessConfigured: boolean;
      components: Array<{
        componentId: string;
        label: string;
        status: string;
        processStatus: string;
        checkedAt: string;
        lastSuccessAt: string;
        latencyMs?: number;
        httpStatus?: number;
        detail: string;
      }>;
    };
    collection: {
      status: string;
      planStatus: string;
      planSchemaVersion: string;
      planRef: string;
      planError: string;
      collectors: Array<{
        collectorId: string;
        label: string;
        importance: string;
        enabled: boolean;
        ownerProcess: string;
        processStatus: string;
        status: string;
        statusDetail: string;
        scheduleIntervalSec: number;
        staleAfterSec: number;
        lastAttemptAt: string;
        lastSuccessAt: string;
        lastErrorAt: string;
        nextDueAt: string;
        ageMinutes?: number;
        coverageRate?: number;
        coveredCount: number;
        expectedCount: number;
        missingCount: number;
        missingMatchIds: string[];
        okCount: number;
        failCount: number;
        totalAttempts: number;
        rowsParsed: number;
        error?: string;
        markets: string[];
        autoRecoveryExpected: boolean;
        retryCount?: number;
        maintenanceAction: string;
      }>;
    };
    artifacts: {
      status: string;
      activeDecision: {
        status: string;
        version: string;
        configHash: string;
        generatedAt: string;
        inputAt: string;
        expectedCount: number;
        actualCount: number;
        missingCount: number;
        missingMatchIds: string[];
        detail: string;
      };
      draftCount: number;
      draftMatchIds: string[];
      supersededCount: number;
      scheduledResearchEvidenceEligible: boolean;
      adhocNamespaceUsed: boolean;
    };
    scheduledFreeze: {
      status: string;
      timelineContract: string;
      researchAndAdhocSeparated: boolean;
      nextDueAt: string;
      segments: Array<{
        segmentIdx: number;
        segmentIdentity: string;
        isRecovery: boolean;
        timelineStatus: string;
        freezeAt: string;
        publishedAt: string;
        observedAt: string;
        nextDueAt: string;
        matchCount: number;
        detail: string;
        autoRecoveryExpected: boolean;
        exactN: {
          status: string;
          sourceStatus: string;
          verificationStatus: string;
          eventId: string;
          artifactRef: string;
          alternativeCount: number;
          selectableCount: number;
          researchEvidenceEligible: boolean;
        };
        researchFreeze: {
          status: string;
          verificationStatus: string;
          eventId: string;
          artifactRef: string;
          detail: string;
          pairedOverlapMatches?: number;
          frozenMatchMarkets?: number;
        };
      }>;
    };
    adhocService: {
      status: string;
      serviceStatus: string;
      isolationStatus: string;
      capabilityAvailable: boolean;
      lastRequestAt: string;
      lastSuccessAt: string;
      detail: string;
      scheduledFreezeEventId?: string;
      researchEvidenceEligible: boolean;
      recentRequest?: {
        requestId: string;
        requestedAt: string;
        inputAsof: string;
        status: string;
        validUntil: string;
        saleStatusVerifiedAtGeneration: boolean;
        state: string;
        separationValid: boolean;
      };
    };
    settlementReview: {
      status: string;
      settledMatchCount: number;
      winningSpCount: number;
      reviewedMatchCount: number;
      missingWinningSpMatchIds: string[];
      unreviewedMatchIds: string[];
      latestReviewAt: string;
      lastSettlementSuccessAt: string;
      nextDueAt: string;
      simulationOnly: boolean;
      offlinePurchaseInferred: boolean;
      actualRoiClaimed: boolean;
    };
  };
  alerts: Array<{
    alertId: string;
    code: string;
    domain: string;
    severity: 'blocker' | 'warning' | string;
    status: string;
    title: string;
    detail: string;
    impact: string;
    nextAction: string;
    observedAt: string;
    firstSeenAt: string;
    lastSeenAt: string;
    lastSuccessAt: string;
    nextDueAt: string;
    affectedCount: number;
    affected: {
      segments: string[];
      matches: string[];
      markets: string[];
      sources: string[];
    };
    autoRecoveryExpected: boolean;
    retryCount?: number;
    links: Array<{ kind: string; label: string; ref: string }>;
    blocks: {
      dataDisplay: boolean;
      researchFreeze: boolean;
      adhocGeneration: boolean;
      settlement: boolean;
    };
  }>;
  issueStatus: {
    currentIssue: string;
    matchCount: number;
    finishedCount: number;
    settledSpCount: number;
    openCount: number;
    captureStatus: string;
    latestSnapshotAt: string;
    latestSnapshotAgeMinutes?: number;
  };
  runtime: {
    apiHealth: string;
    apiUrl: string;
    apiHealthUrl: string;
    apiPort: string;
    frontendHealth?: string;
    frontendLocalUrl: string;
    frontendRemoteUrl: string;
    frontendPort: string;
    publicDiagnostics?: boolean;
    accessMode?: string;
    externalAccessConfigured?: boolean;
    checkedAt?: string;
    statusPath?: string;
    runtimeDir?: string;
    urls?: Record<string, string>;
    apiPid?: number;
    apiProcessStatus?: string;
    apiBindHost?: string;
    apiCommand?: string[];
    apiLog?: string;
    frontendPid?: number;
    frontendProcessStatus?: string;
    frontendBindHost?: string;
    frontendCommand?: string[];
    frontendLog?: string;
    health?: {
      api?: RuntimeHealthProbe;
      frontendLocal?: RuntimeHealthProbe;
      operations?: RuntimeHealthProbe & { issue?: string; workflowStatus?: string; reviewTaskStatus?: string };
      hostSmokeCount?: number;
      hostSmokeOkCount?: number;
      hostSmokes?: RuntimeHealthProbe[];
    };
  };
  sources: Array<{
    sourceName: string;
    status: ScrapeStatus;
    lastAttemptAt: string;
    lastSuccessAt: string;
    ageMinutes?: number;
    okCount: number;
    failCount: number;
    totalAttempts: number;
    rowsParsed: number;
    error?: string;
  }>;
  snapshots: {
    activeCount: number;
    draftReplacementCount: number;
    supersededCount: number;
    pendingDrafts: Array<{ matchIdx: number; matchId: string; generatedAt: string; checkedAt: string }>;
  };
  review: {
    reviewVersion: string;
    settledMatchCount: number;
    reviewedMatchCount: number;
    unreviewedSettledCount: number;
    latestReviewAt: string;
    unreviewedMatches: Array<{ matchIdx: number; matchId: string; label: string; resultLabel: string; winningSp?: number }>;
    task: {
      runId: string;
      issue: string;
      mode: string;
      status: string;
      dryRun: boolean;
      requestedBy: string;
      startedAt: string;
      finishedAt: string;
      elapsedSec?: number;
      error?: string;
      triggerEndpoint: string;
      command: string[];
      result: {
        inserted?: number;
        wouldInsert?: number;
        reviewedAt?: string;
        profit?: number;
        coverageHits?: number;
        primaryHits?: number;
        protectHits?: number;
      };
    };
  };
  workflow: {
    runId: string;
    issue: string;
    mode: string;
    status: string;
    dryRun: boolean;
    requestedBy: string;
    startedAt: string;
    finishedAt: string;
    elapsedSec?: number;
    error?: string;
    triggerEndpoint: string;
    steps: Array<{
      stepIdx: number;
      stepKey: string;
      label: string;
      status: string;
      command: string[];
      startedAt: string;
      finishedAt: string;
      elapsedSec?: number;
      error?: string;
    }>;
  };
  versions: {
    schemaVersion: string;
    probModelVersion: string;
    qModelVersion: string;
    decisionChainVersion: string;
    decisionPromptVersion: string;
    decisionModelVersion: string;
    reviewTagVersion: string;
    reviewVersion: string;
    decisionConfigHash: string;
    configPath: string;
  };
  warnings: Array<{ code: string; severity: 'good' | 'warn' | 'bad' | 'neutral' | string; label: string; detail: string }>;
  source: { sqliteDb: string; tables: string[] };
}

export interface RuntimeHealthProbe {
  ok: boolean;
  status: number;
  url?: string;
  hostHeader?: string;
  latencyMs?: number;
  error?: string;
  issue?: string;
  workflowStatus?: string;
  reviewTaskStatus?: string;
}

export interface SegmentBettingPlanData {
  schemaVersion: string;
  issueId: string;
  mode: string;
  requestedDecisionVariantId: string;
  requestedPlanningScope: string;
  requestedDecisionTime: string;
  requestedSegmentBudgetYuan?: number;
  requestedStakeMode?: string;
  requestedBettingStrategyVersion: string;
  requestedLabel: string;
  selectedPlanId: string;
  availabilityStatus: 'available' | 'degraded' | 'missing' | string;
  unavailableReason?: string;
  notice: string;
  source: { artifactKey: string; artifactDir: string };
  artifactPath: string;
  artifactStatus: {
    status: string;
    artifactKey: string;
    artifactDir: string;
    artifactPath: string;
    sourcePath: string;
    updatedAt: string;
    reason: string;
  };
  strategyRelease: {
    activeReleaseId: string;
    releaseId: string;
    versionId: string;
    status: string;
  };
  availablePlans: Array<{
    planId: string;
    label: string;
    decisionVariantId: string;
    strategyFamily: string;
    bettingStrategyVersion: string;
	    artifactSchemaVersion: string;
	    planningScope: string;
	    artifactPlanningScope?: string;
	    decisionTime: string;
    stakeMode: string;
    availableSegments?: number;
    spDriftRiskAccepted: boolean;
    spDriftRiskLevel: string;
    arm: string;
    segmentBudgetYuan?: number;
    sampleSeed?: number;
    seedCount?: number;
    summaryMode?: string;
    sourceRows?: number;
    eligibleRows?: number;
    segments?: number;
    selectedBundles?: number;
    baseCostYuan?: number;
    stakeMultiplierUnits?: number;
    selectedCostYuan?: number;
    profitYuan?: number;
    roi?: number;
    updatedAt?: string;
    artifactPath: string;
  }>;
  selectedPlan?: SegmentBettingPlanData['availablePlans'][number];
  strategyFamily: string;
  bettingStrategyVersion: string;
  artifactSchemaVersion: string;
	  planningScope: string;
	  artifactPlanningScope?: string;
	  decisionTime: string;
	  availableSegments?: number;
	  dynamicSegmentsAvailable?: number;
	  selectionBinding?: {
	    matchSelectionSource: string;
	    frontendDisplaySource: string;
	    refreshPolicy: string;
	    planningScope?: string;
	  };
	  spDriftRisk: {
    accepted: boolean;
    level: string;
    reason: string;
  };
  settings: {
    planningScope?: string;
    decisionTime?: string;
    stakeMode?: string;
    windowHours?: number;
    extendHours?: string;
    minMatches?: number;
    maxMatches?: number;
    segmentBudgetYuan?: number;
    stakeYuanPerTicket?: number;
    sampleAttempts?: number;
    sampleSeed?: number;
    minN?: number;
    maxN?: number;
    positiveEvOnly?: boolean;
	    seedCount?: number;
	    sampleSeeds?: number[];
	    maxOverlap?: number;
	    maxBundleSpendPct?: number;
	    bettingStrategyVersion?: string;
	  };
  seedAggregate: {
    seedCount?: number;
    seeds: number[];
    summaryMode: string;
    metrics: Record<string, {
      min?: number;
      p10?: number;
      mean?: number;
      median?: number;
      p90?: number;
      max?: number;
    }>;
  };
  parameterSchema: Array<{
    key: string;
    label: string;
    uiLevel: 'basic' | 'advanced' | 'debug' | string;
    type: string;
    unit?: string;
    defaultValue?: string | number | boolean | null;
    options?: string[];
    min?: number;
    step?: number;
    effect: string;
  }>;
  segmentCsv: string;
  bundleCsv: string;
  seedSummaryCsv: string;
  segmentSeedSummaryCsv: string;
  summary: {
    settlementStatus?: string;
    primaryMetricMode?: string;
    segments?: number;
    selectedSegments?: number;
    deadSegments?: number;
    selectedBundles?: number;
    baseCostYuan?: number;
    stakeMultiplierUnits?: number;
    selectedCostYuan?: number;
    expectedPayoutYuan?: number;
    expectedProfitYuan?: number;
    expectedRoi?: number;
    payoutYuan?: number;
    profitYuan?: number;
    roi?: number;
  };
  segments: Array<{
    sampleSeed?: number;
    segmentIdx?: number;
    arm: string;
    planningScope: string;
    hoursFromDecisionStart?: number;
    hoursFromDecisionEnd?: number;
    spDriftRiskAccepted: boolean;
    spDriftRiskLevel: string;
    spDriftRiskReason: string;
    stakeMode: string;
    segmentStart: string;
    segmentEnd: string;
    windowHours?: number;
    eligibleMatches?: number;
    expectedCoverageHitRate?: number;
    actualCoverageHits?: number;
    actualCoverageHitRate?: number;
    recommendedN?: number;
    initialRecommendedN?: number;
    selectedBundles?: number;
    candidateBundles?: number;
    baseCostYuan?: number;
    stakeMultiplierUnits?: number;
    selectedCostYuan?: number;
    segmentBudgetYuan?: number;
    expectedProfitYuan?: number;
    payoutYuan?: number;
    profitYuan?: number;
    roi?: number;
    deadSegment: boolean;
    widthCounts: string;
    reasons: string[];
    matchIndices: number[];
  }>;
  bundles: Array<{
    sampleSeed?: number;
    segmentIdx?: number;
    bundleIdx?: number;
    arm: string;
    nValue?: number;
    matchIndices: number[];
    legCodes: string[];
    widths: number[];
    stakeMultiplier?: number;
    costYuan?: number;
    scaledCostYuan?: number;
    expectedPayoutYuan?: number;
    expectedProfitYuan?: number;
    scaledExpectedProfitYuan?: number;
    expectedRoi?: number;
    hitProb?: number;
    realizedHit: boolean;
    payoutYuan?: number;
    scaledPayoutYuan?: number;
    profitYuan?: number;
    scaledProfitYuan?: number;
  }>;
  seedSummaries: Array<{
    sampleSeed?: number;
    selectedSegments?: number;
    deadSegments?: number;
    selectedBundles?: number;
    selectedCostYuan?: number;
    payoutYuan?: number;
    profitYuan?: number;
    roi?: number;
  }>;
  segmentSeedSummary: Array<{
    segmentIdx?: number;
    arm: string;
    sampleCount?: number;
    segmentStart: string;
    segmentEnd: string;
    eligibleMatches?: number;
    expectedCoverageHitRate?: number;
    actualCoverageHits?: number;
    actualCoverageHitRate?: number;
    recommendedNValues: number[];
    recommendedNStable: boolean;
    selectedBundlesMean?: number;
    selectedBundlesMin?: number;
    selectedBundlesMax?: number;
    baseCostYuanMean?: number;
    stakeMultiplierUnitsMean?: number;
    costYuanMean?: number;
    payoutYuanMean?: number;
    profitYuanMin?: number;
    profitYuanP10?: number;
    profitYuanMean?: number;
    profitYuanMedian?: number;
    profitYuanP90?: number;
    profitYuanMax?: number;
    roiMin?: number;
    roiMean?: number;
    roiMax?: number;
    deadSegmentRate?: number;
    widthCounts: string;
    matchIndices: number[];
  }>;
}

export interface DashboardData {
  availableIssues: IssueOption[];
  issue: IssueDashboardData;
  matchDetail: MatchDetailData;
  ticket: TicketData;
  liveSignals: LiveSignalsData;
  settlement: SettlementData;
  strategyLab: StrategyLabData;
  selectorShadow: SelectorShadowData;
  mainStrategy: MainStrategyData;
  operations: OperationsStatusData;
  segmentBettingPlan: SegmentBettingPlanData;
  exactNFreezes: ExactNFreezeData;
}

export interface ExactNFreezeData {
  schemaVersion: string;
  issueId: string;
  status: string;
  segmentManifestSha256: string;
  exactNFrontendSelectable: boolean;
  recoverySegments: Array<{
    segmentIdentity: string;
    parentSegmentIdx: number;
    parentStatus: string;
    status: string;
    matchCount: number;
    freezeAt: string;
    recoveryManifestSha256: string;
  }>;
  segments: Array<{
    segmentIdx: number;
    segmentIdentity: string;
    isRecovery: boolean;
    parentSegmentIdx?: number;
    parentStatus: string;
    recoveryManifestSha256: string;
    matchCount: number;
    freezeAt: string;
    effectiveDecisionAt: string;
    status: string;
    alternatives: Array<{
      planId: string;
      exactN: boolean;
      requestedN: number;
      artifactN: number;
      recommendedN: number;
      requestedBudgetYuan: number;
      baseCostYuan: number;
      actualCostYuan: number;
      unusedBudgetYuan: number;
      budgetUtilization: number;
      ticketCount: number;
      decisionInputSha256: string;
      freezeAt: string;
      status: string;
      frontendSelectable: boolean;
    }>;
    correctScore?: {
      status: string;
      frontendSelectable: boolean;
    };
  }>;
}

export interface AdhocMatchEligibilityData {
  matchIdx: number;
  matchId: string;
  league: string;
  home: string;
  away: string;
  handicapLine?: number | string | null;
  kickoffAt: string;
  eligible: boolean;
  exclusionReasons: string[];
}

export interface AdhocBettingEligibilityData {
  schemaVersion: string;
  capabilityId: string;
  issueId: string;
  observedAt: string;
  inputAsOf: string;
  status: string;
  eligibleMatchCount: number;
  excludedMatchCount: number;
  exclusionCounts: Record<string, number>;
  matches: AdhocMatchEligibilityData[];
  safetyMarginSeconds: number;
  previewOnly: boolean;
  researchEvidenceEligible: false;
  scheduledFreezeEventId: null;
}

export interface AdhocBettingPlanData {
  schemaVersion: string;
  capabilityId: string;
  packageSchemaVersion: string;
  concentrationContractApplied: boolean;
  requestId: string;
  immutableRequestId: string;
  publishedPackageCount: number;
  generationBatchCount: number;
  issueId: string;
  requestedAt: string;
  inputAsOf: string;
  requestedN: number;
  requestedBudgetYuan: number;
  baseCostYuan: number;
  actualCostYuan: number;
  unusedBudgetYuan: number;
  budgetUtilization: number;
  validUntil: string;
  status: string;
  currentStatus: string;
  currentStatusRecheckScope: 'VALID_UNTIL_SERVER_CLOCK_ONLY' | string;
  saleEligibilityScope: 'GENERATION_TIME_SNAPSHOT_ONLY' | string;
  shopSaleConfirmationRequired: boolean;
  structuralVerificationStatus: string;
  saleStatusVerified: boolean;
  operationalDownloadsEnabled: boolean;
  auditDownloadsAvailable: boolean;
  ticketCount: number;
  eligibleMatchCount: number;
  maxTicketOccurrencesPerMatch?: number;
  totalMatchOccurrenceCapacity?: number;
  theoreticalTicketCountCap?: number;
  maxActualTicketOccurrencesPerMatch?: number;
  averageTicketOccurrencesPerMatch?: number;
  matchOccurrencesSha256?: string;
  matchOccurrences?: Array<{
    matchIdx: number;
    matchId: string;
    ticketNumbers: number[];
    distinctTicketOccurrenceCount: number;
    spendWeightedExposureYuan: number;
    spendWeightedExposureRatio: number;
  }>;
  excludedMatchCount: number;
  exclusionCounts: Record<string, number>;
  denominator: AdhocMatchEligibilityData[];
  tickets: Array<{
    ticketNo: number;
    actualN: number;
    stakeMultiplier: number;
    baseCostYuan: number;
    costYuan: number;
    legs: Array<{
      matchIdx: number;
      matchId: string;
      selectionCode: string;
      selectionLabel: string;
      kickoffAt: string;
      league: string;
      home: string;
      away: string;
      handicapLine?: number | string | null;
      matchTicketOccurrenceCount?: number;
      matchTicketNumbers?: number[];
    }>;
  }>;
  planReason: string;
  unavailableReasons: string[];
  inputSha256: string;
  manifestSha256: string;
  packageId: string;
  researchEvidenceEligible: false;
  scheduledFreezeEventId: null;
  correctScoreStatus: string;
  idempotent: boolean;
}
