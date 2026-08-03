// Exact #167 atlas accelerator.  This translation unit includes the frozen
// #145 allocator implementation verbatim and adds only aggregation glue.
#include "bj145_fast_alloc.cpp"
#include <cfloat>

static constexpr int FULL_TICKETS = 2187;

extern "C" {

static const int MCOUNT = 20;
static const int SEEDCOUNT = 100;

static double *TMP_GROSS = nullptr, *TMP_STAKE = nullptr, *TMP_HIT = nullptr;
static unsigned char *TMP_MARK = nullptr;
static int *TMP_TOUCHED = nullptr, TMP_TOUCHED_LEN = 0;
static double *ISSUE_SUMSQ = nullptr, *ISSUE_TOP = nullptr, *CUM_NET = nullptr;
static double *PEAK_NET = nullptr, *DRAWDOWN = nullptr;
static double *ISSUE_TOP_NET = nullptr, *ISSUE_TOP_STAKE = nullptr;
static int *ISSUE_TOP_INDEX = nullptr;
static int *MISS_STREAK = nullptr, *LONGEST_MISS = nullptr;
static int *CELL_TO_BOOT_TARGET = nullptr, BOOT_TARGET_COUNT = 0, CURRENT_ISSUE = -1;
static double *TMP_BOOT_NET = nullptr, *TMP_BOOT_STAKE = nullptr, *TMP_BOOT_HIT = nullptr;
static double *BOOT_NET = nullptr, *BOOT_STAKE = nullptr, *BOOT_HIT = nullptr;

void bj167_set_issue_buffers(double *tmp_gross, double *tmp_stake, double *tmp_hit,
                             unsigned char *tmp_mark, int *tmp_touched,
                             double *issue_sumsq, double *issue_top,
                             double *cum_net, double *peak_net, double *drawdown,
                             int *miss_streak, int *longest_miss,
                             double *issue_top_net, double *issue_top_stake,
                             int *issue_top_index,
                             int *cell_to_boot_target, int boot_target_count,
                             double *tmp_boot_net, double *tmp_boot_stake, double *tmp_boot_hit,
                             double *boot_net, double *boot_stake, double *boot_hit) {
    TMP_GROSS = tmp_gross; TMP_STAKE = tmp_stake; TMP_HIT = tmp_hit;
    TMP_MARK = tmp_mark; TMP_TOUCHED = tmp_touched;
    ISSUE_SUMSQ = issue_sumsq; ISSUE_TOP = issue_top; CUM_NET = cum_net;
    PEAK_NET = peak_net; DRAWDOWN = drawdown; MISS_STREAK = miss_streak; LONGEST_MISS = longest_miss;
    ISSUE_TOP_NET = issue_top_net; ISSUE_TOP_STAKE = issue_top_stake; ISSUE_TOP_INDEX = issue_top_index;
    CELL_TO_BOOT_TARGET = cell_to_boot_target; BOOT_TARGET_COUNT = boot_target_count;
    TMP_BOOT_NET = tmp_boot_net; TMP_BOOT_STAKE = tmp_boot_stake; TMP_BOOT_HIT = tmp_boot_hit;
    BOOT_NET = boot_net; BOOT_STAKE = boot_stake; BOOT_HIT = boot_hit;
}

void bj167_begin_issue(int issue_index) {
    TMP_TOUCHED_LEN = 0; CURRENT_ISSUE = issue_index;
    if (TMP_BOOT_NET != nullptr) for (int i = 0; i < BOOT_TARGET_COUNT; ++i) TMP_BOOT_NET[i] = TMP_BOOT_STAKE[i] = TMP_BOOT_HIT[i] = 0.0;
}

int bj167_touched_count() { return TMP_TOUCHED_LEN; }

void bj167_end_issue() {
    if (!TMP_TOUCHED) return;
    for (int i = 0; i < TMP_TOUCHED_LEN; ++i) {
        const int at = TMP_TOUCHED[i];
        const double g = TMP_GROSS[at], s = TMP_STAKE[at], h = TMP_HIT[at];
        ISSUE_SUMSQ[at] += g * g;
        if (g > ISSUE_TOP[at]) ISSUE_TOP[at] = g;
        if (g - s > ISSUE_TOP_NET[at]) { ISSUE_TOP_NET[at] = g - s; ISSUE_TOP_STAKE[at] = s; if (ISSUE_TOP_INDEX != nullptr) ISSUE_TOP_INDEX[at] = CURRENT_ISSUE; }
        if (s > 0.0) {
            CUM_NET[at] += g - s;
            if (CUM_NET[at] > PEAK_NET[at]) PEAK_NET[at] = CUM_NET[at];
            const double dd = PEAK_NET[at] - CUM_NET[at];
            if (dd > DRAWDOWN[at]) DRAWDOWN[at] = dd;
            if (h > 0.0) MISS_STREAK[at] = 0;
            else { ++MISS_STREAK[at]; if (MISS_STREAK[at] > LONGEST_MISS[at]) LONGEST_MISS[at] = MISS_STREAK[at]; }
        }
        if (CURRENT_ISSUE >= 0 && BOOT_TARGET_COUNT > 0 && CELL_TO_BOOT_TARGET != nullptr) {
            const int target = CELL_TO_BOOT_TARGET[at];
            if (target >= 0) {
                BOOT_NET[CURRENT_ISSUE * BOOT_TARGET_COUNT + target] = TMP_GROSS[at] - TMP_STAKE[at];
                BOOT_STAKE[CURRENT_ISSUE * BOOT_TARGET_COUNT + target] = TMP_STAKE[at];
                BOOT_HIT[CURRENT_ISSUE * BOOT_TARGET_COUNT + target] = TMP_HIT[at];
            }
        }
        TMP_GROSS[at] = TMP_STAKE[at] = TMP_HIT[at] = 0.0;
        TMP_MARK[at] = 0;
    }
    if (CURRENT_ISSUE >= 0 && BOOT_TARGET_COUNT > 0 && BOOT_NET != nullptr) {
        for (int t = 0; t < BOOT_TARGET_COUNT; ++t) {
            BOOT_NET[CURRENT_ISSUE * BOOT_TARGET_COUNT + t] = TMP_BOOT_NET[t];
            BOOT_STAKE[CURRENT_ISSUE * BOOT_TARGET_COUNT + t] = TMP_BOOT_STAKE[t];
            BOOT_HIT[CURRENT_ISSUE * BOOT_TARGET_COUNT + t] = TMP_BOOT_HIT[t];
        }
    }
    TMP_TOUCHED_LEN = 0;
}

static void add_one(int selector, int cell, int hit, int unique, int duplicate,
                    double payout, int n_occ, double *identity, double *stake,
                    double *gross, double *tax, double *unique_sum,
                    double *duplicate_sum, double *hit_sum, double *coverage_sum) {
    const std::size_t at = static_cast<std::size_t>(selector) * 24723u + static_cast<std::size_t>(cell);
    if (TMP_GROSS != nullptr) {
        if (!TMP_MARK[at]) { TMP_MARK[at] = 1; TMP_TOUCHED[TMP_TOUCHED_LEN++] = static_cast<int>(at); }
        TMP_GROSS[at] += payout * static_cast<double>(hit);
        TMP_STAKE[at] += 2.0 * (unique + duplicate);
    TMP_HIT[at] += static_cast<double>(hit);
    }
    if (CELL_TO_BOOT_TARGET != nullptr && BOOT_TARGET_COUNT > 0) {
        const int target = CELL_TO_BOOT_TARGET[at];
        if (target >= 0) {
            TMP_BOOT_NET[target] += payout * static_cast<double>(hit) - 2.0 * (unique + duplicate);
            TMP_BOOT_STAKE[target] += 2.0 * (unique + duplicate);
            TMP_BOOT_HIT[target] += static_cast<double>(hit);
        }
    }
    identity[at] += 1.0;
    stake[at] += 2.0 * (unique + duplicate);
    gross[at] += payout * static_cast<double>(hit);
    tax[at] += (payout >= 10000.0 ? payout * 0.20 * static_cast<double>(hit) : 0.0);
    unique_sum[at] += static_cast<double>(unique);
    duplicate_sum[at] += static_cast<double>(duplicate);
    hit_sum[at] += static_cast<double>(hit);
    coverage_sum[at] += hit > 0 ? 1.0 : 0.0;
}

static void add_profile(int selector, int cell, const int *metrics, double payout,
                        double *identity, double *stake, double *gross,
                        double *tax, double *unique_sum, double *duplicate_sum,
                        double *hit_sum, double *coverage_sum) {
    add_one(selector, cell, metrics[0], metrics[1], metrics[2], payout, 1,
            identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
}

void bj167_process_source(const double *role_probs, int truth, const char *seed_signature,
                          double payout, const int *selector_ids, int occurrence_count,
                          const int *wr_map, const int *wor_map, const int *residual_map,
                          const int *capped_map, const int *top_map, int full_cell,
                          double *identity, double *stake, double *gross, double *tax,
                          double *unique_sum, double *duplicate_sum, double *hit_sum,
                          double *coverage_sum) {
    std::array<double, FULL_TICKETS> weights{};
    weights[0] = 1.0;
    int used = 1;
    for (int leg = 0; leg < 7; ++leg) {
        std::array<double, FULL_TICKETS> next{};
        int next_used = 0;
        for (int prefix = 0; prefix < used; ++prefix) {
            for (int code = 0; code < 3; ++code) {
                next[next_used++] = weights[prefix] * role_probs[leg * 3 + code];
            }
        }
        weights = next;
        used = next_used;
    }
    std::vector<int> ms;
    ms.reserve(MCOUNT);
    const int m_grid[MCOUNT] = {16,32,48,64,80,96,112,128,144,160,176,192,208,224,240,256,512,1024,1458,2187};
    for (int i = 0; i < MCOUNT; ++i) ms.push_back(m_grid[i]);
    // Profile generation is pure and independent by seed.  Keep all
    // add_profile/add_one calls below serial because they mutate the shared
    // selector/cell/issue ledgers and bootstrap scratch buffers.  Only this
    // precompute is parallelized into disjoint [seed][M][metric] slabs.
    std::array<int, SEEDCOUNT * MCOUNT * 4> wr_metrics{};
    std::array<int, SEEDCOUNT * MCOUNT * 4> wor_metrics{};
    #pragma omp parallel for schedule(static)
    for (int seed_idx = 0; seed_idx < SEEDCOUNT; ++seed_idx) {
        // seed/signature buffers are thread-local; no shared temporary state
        // is used by the frozen profile functions.
        char local_seed[16];
        std::snprintf(local_seed, sizeof(local_seed), "137%03d", seed_idx + 1);
        bj145_wr_profile(weights.data(), FULL_TICKETS, truth, local_seed, seed_signature, ms.data(), MCOUNT, wr_metrics.data() + seed_idx * MCOUNT * 4);
        bj145_wor_profile(weights.data(), FULL_TICKETS, truth, local_seed, seed_signature, ms.data(), MCOUNT, wor_metrics.data() + seed_idx * MCOUNT * 4);
    }
    // WR and WOR are generated once at max M per canonical support and each
    // requested M reads the same prefix metrics.  Replay remains serial.
    for (int seed_idx = 0; seed_idx < SEEDCOUNT; ++seed_idx) {
        for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
            const int cell = wr_map[seed_idx * MCOUNT + m_idx];
            for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], cell, wr_metrics.data() + (seed_idx * MCOUNT + m_idx) * 4, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
        }
        for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
            const int cell = wor_map[seed_idx * MCOUNT + m_idx];
            for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], cell, wor_metrics.data() + (seed_idx * MCOUNT + m_idx) * 4, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
        }
    }
    std::vector<int> metrics(MCOUNT * 4);
    // Deterministic mechanisms are evaluated once per canonical support.
    bj145_profile(weights.data(), FULL_TICKETS, truth, 0, ms.data(), MCOUNT, metrics.data());
    for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
        const int cell = residual_map[m_idx];
        for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], cell, metrics.data() + m_idx * 4, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
    }
    // Frozen capped-repeat grid is the explicit set {1,2,4,8}; the cap value
    // is a mechanism parameter, not a zero-based loop ordinal.
    static constexpr int CAPS[4] = {1, 2, 4, 8};
    for (int cap_idx = 0; cap_idx < 4; ++cap_idx) {
        const int cap = CAPS[cap_idx];
        bj145_profile(weights.data(), FULL_TICKETS, truth, cap, ms.data(), MCOUNT, metrics.data());
        for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
            const int cell = capped_map[cap_idx * MCOUNT + m_idx];
            for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], cell, metrics.data() + m_idx * 4, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
        }
    }
    // Top-mass has the exact deterministic engine semantics.  The frozen
    // engine's public mechanism is called once at each M; no seed is faked.
    for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
        std::vector<int> counts(FULL_TICKETS, 0);
        std::vector<int> order(FULL_TICKETS);
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int a, int b) {
            if (weights[a] != weights[b]) return weights[a] > weights[b];
            return a < b;
        });
        for (int rank = 0; rank < m_grid[m_idx]; ++rank) ++counts[order[rank]];
        int local[4]; write_metrics(counts, truth, m_grid[m_idx], local);
        const int cell = top_map[m_idx];
        for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], cell, local, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
    }
    if (full_cell >= 0) {
        int local[4] = {1, FULL_TICKETS, 0, 0};
        for (int oi = 0; oi < occurrence_count; ++oi) add_profile(selector_ids[oi], full_cell, local, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
    }
}

// Add a real P/Q global-delete result.  One frozen role/code is removed from
// the 3^7 space, leaving exactly 2*3^6 tickets.  The actual canonical truth
// is checked at the deleted role; no 2/3 expectation is used.
void bj167_add_delete(int selector, int cell, int truth_code, int deleted_leg, int deleted_code,
                      double payout, double *identity, double *stake, double *gross,
                      double *tax, double *unique_sum, double *duplicate_sum,
                      double *hit_sum, double *coverage_sum) {
    const int hit = ((truth_code / static_cast<int>(std::pow(3, 6 - deleted_leg))) % 3) != deleted_code;
    const int unique = 1458;
    const int local[4] = {hit, unique, 0, 0};
    add_profile(selector, cell, local, payout, identity, stake, gross, tax, unique_sum, duplicate_sum, hit_sum, coverage_sum);
}

// Bounded post-screening replay glue.  It deliberately shares the frozen
// #145 allocation routines used by the full atlas, but returns profiles to a
// caller that has already frozen a small candidate set.  No allocation
// semantics live in Python, which preserves the accepted native tie cases.
void bj167_profile_allocation(const double *role_probs, int truth, const char *seed_signature,
                              int *wr_metrics, int *wor_metrics, int *residual_metrics,
                              int *capped_metrics, int *top_metrics, int *full_metrics) {
    std::array<double, FULL_TICKETS> weights{};
    weights[0] = 1.0;
    int used = 1;
    for (int leg = 0; leg < 7; ++leg) {
        std::array<double, FULL_TICKETS> next{};
        int next_used = 0;
        for (int prefix = 0; prefix < used; ++prefix)
            for (int code = 0; code < 3; ++code)
                next[next_used++] = weights[prefix] * role_probs[leg * 3 + code];
        weights = next;
        used = next_used;
    }
    std::vector<int> ms;
    const int m_grid[MCOUNT] = {16,32,48,64,80,96,112,128,144,160,176,192,208,224,240,256,512,1024,1458,2187};
    ms.assign(m_grid, m_grid + MCOUNT);
    #pragma omp parallel for schedule(static)
    for (int seed_idx = 0; seed_idx < SEEDCOUNT; ++seed_idx) {
        char local_seed[16];
        std::snprintf(local_seed, sizeof(local_seed), "137%03d", seed_idx + 1);
        bj145_wr_profile(weights.data(), FULL_TICKETS, truth, local_seed, seed_signature, ms.data(), MCOUNT,
                         wr_metrics + seed_idx * MCOUNT * 4);
        bj145_wor_profile(weights.data(), FULL_TICKETS, truth, local_seed, seed_signature, ms.data(), MCOUNT,
                          wor_metrics + seed_idx * MCOUNT * 4);
    }
    bj145_profile(weights.data(), FULL_TICKETS, truth, 0, ms.data(), MCOUNT, residual_metrics);
    static constexpr int CAPS[4] = {1, 2, 4, 8};
    for (int cap_idx = 0; cap_idx < 4; ++cap_idx)
        bj145_profile(weights.data(), FULL_TICKETS, truth, CAPS[cap_idx], ms.data(), MCOUNT,
                      capped_metrics + cap_idx * MCOUNT * 4);
    for (int m_idx = 0; m_idx < MCOUNT; ++m_idx) {
        std::vector<int> counts(FULL_TICKETS, 0), order(FULL_TICKETS);
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int a, int b) {
            if (weights[a] != weights[b]) return weights[a] > weights[b];
            return a < b;
        });
        for (int rank = 0; rank < m_grid[m_idx]; ++rank) ++counts[order[rank]];
        write_metrics(counts, truth, m_grid[m_idx], top_metrics + m_idx * 4);
    }
    full_metrics[0] = 1; full_metrics[1] = FULL_TICKETS;
    full_metrics[2] = 0; full_metrics[3] = 0;
}

// One common deterministic issue-resample matrix is supplied by Python.  The
// candidate and selector-matched FULL denominators are accumulated together
// for every draw, so the returned lift is genuinely paired.
void bj167_paired_issue_bootstrap(const double *candidate_net, const double *candidate_stake,
                                  const double *full_net, const double *full_stake,
                                  int candidate_count, int issue_count,
                                  const unsigned int *draws, int replicates,
                                  double *candidate_roi, double *full_roi, double *lift_roi) {
    #pragma omp parallel for schedule(static)
    for (int c = 0; c < candidate_count; ++c) {
        const double *cn = candidate_net + static_cast<std::size_t>(c) * issue_count;
        const double *cs = candidate_stake + static_cast<std::size_t>(c) * issue_count;
        const double *fn = full_net + static_cast<std::size_t>(c) * issue_count;
        const double *fs = full_stake + static_cast<std::size_t>(c) * issue_count;
        for (int r = 0; r < replicates; ++r) {
            double cnet = 0.0, cstake = 0.0, fnet = 0.0, fstake = 0.0;
            const unsigned int *ix = draws + static_cast<std::size_t>(r) * issue_count;
            for (int j = 0; j < issue_count; ++j) {
                const unsigned int i = ix[j];
                cnet += cn[i]; cstake += cs[i]; fnet += fn[i]; fstake += fs[i];
            }
            const std::size_t out = static_cast<std::size_t>(c) * replicates + r;
            candidate_roi[out] = cstake > 0.0 ? cnet / cstake : std::numeric_limits<double>::quiet_NaN();
            full_roi[out] = fstake > 0.0 ? fnet / fstake : std::numeric_limits<double>::quiet_NaN();
            lift_roi[out] = (cstake > 0.0 && fstake > 0.0) ? candidate_roi[out] - full_roi[out] : std::numeric_limits<double>::quiet_NaN();
        }
    }
}

// Scientific-cell stability companion.  The first Gate-B pass stores the
// complete seed ledger; this bounded exact companion reduces each stochastic
// 100-seed family to one scientific cell while preserving exact issue totals.
// It is intentionally separate from the full-screen buffers so the active
// screening process remains byte-for-byte untouched.
static constexpr int SCI_CELLS_PER_SELECTOR = 963;
static double *SCI_TMP_NET = nullptr, *SCI_TMP_STAKE = nullptr, *SCI_TMP_GROSS = nullptr, *SCI_TMP_TAX = nullptr, *SCI_TMP_HIT = nullptr, *SCI_TMP_TAX_LINE_HIT = nullptr;
static unsigned char *SCI_MARK = nullptr;
static int *SCI_TOUCHED = nullptr, SCI_TOUCHED_LEN = 0;
static double *SCI_NET = nullptr, *SCI_STAKE = nullptr, *SCI_GROSS = nullptr, *SCI_TAX = nullptr, *SCI_HIT = nullptr, *SCI_GROSS_SUMSQ = nullptr, *SCI_GROSS_TOP = nullptr;
static double *SCI_CUM_NET = nullptr, *SCI_PEAK_NET = nullptr, *SCI_DRAWDOWN = nullptr;
static int *SCI_MISS_STREAK = nullptr, *SCI_LONGEST_MISS = nullptr;
static double *SCI_YEAR_NET = nullptr, *SCI_YEAR_STAKE = nullptr, *SCI_FOLD_NET = nullptr, *SCI_FOLD_STAKE = nullptr;
static double *SCI_LARGEST_NET = nullptr, *SCI_LARGEST_STAKE = nullptr;
static double *SCI_FULL_ISSUE_NET = nullptr, *SCI_FULL_ISSUE_STAKE = nullptr;
static int *SCI_LARGEST_ISSUE = nullptr, SCI_YEAR_COUNT = 0, SCI_FOLD_COUNT = 0, SCI_ISSUE_COUNT = 0, SCI_YEAR = -1, SCI_FOLD = -1, SCI_ISSUE = -1;
// The science replay is also the sole ticket-level producer for the frozen
// post-screen candidates.  ``SCI_CANDIDATE_SCIENCE_AT`` maps each immutable
// candidate key to its pooled 963-cell science address.  At issue end we copy
// its exact temporary ledger and its selector-matched FULL control before the
// temporary buffers are cleared.  Finalizers then consume these arrays without
// a second football/ticket replay.
static const int *SCI_CANDIDATE_SCIENCE_AT = nullptr;
static int SCI_CANDIDATE_COUNT = 0;
static double *SCI_CAND_NET = nullptr, *SCI_CAND_STAKE = nullptr, *SCI_CAND_GROSS = nullptr, *SCI_CAND_TAX = nullptr, *SCI_CAND_HIT = nullptr, *SCI_CAND_TAX_LINE_HIT = nullptr;
static double *SCI_CAND_FULL_NET = nullptr, *SCI_CAND_FULL_STAKE = nullptr, *SCI_CAND_FULL_GROSS = nullptr, *SCI_CAND_FULL_TAX = nullptr, *SCI_CAND_FULL_HIT = nullptr;

void bj167_scientific_set_buffers(double *tmp_net, double *tmp_stake, double *tmp_gross, double *tmp_tax, double *tmp_hit, double *tmp_tax_line_hit,
                                  unsigned char *mark, int *touched,
                                  double *net, double *stake, double *gross, double *tax, double *hit, double *gross_sumsq, double *gross_top,
                                  double *cum_net, double *peak_net, double *drawdown, int *miss_streak, int *longest_miss,
                                  double *year_net, double *year_stake, double *fold_net, double *fold_stake,
                                  double *largest_net, double *largest_stake, int *largest_issue,
                                  double *full_issue_net, double *full_issue_stake,
                                  int year_count, int fold_count, int issue_count) {
    SCI_TMP_NET=tmp_net; SCI_TMP_STAKE=tmp_stake; SCI_TMP_GROSS=tmp_gross; SCI_TMP_TAX=tmp_tax; SCI_TMP_HIT=tmp_hit; SCI_TMP_TAX_LINE_HIT=tmp_tax_line_hit;
    SCI_MARK=mark; SCI_TOUCHED=touched; SCI_NET=net; SCI_STAKE=stake; SCI_GROSS=gross; SCI_TAX=tax; SCI_HIT=hit; SCI_GROSS_SUMSQ=gross_sumsq; SCI_GROSS_TOP=gross_top;
    SCI_CUM_NET=cum_net; SCI_PEAK_NET=peak_net; SCI_DRAWDOWN=drawdown; SCI_MISS_STREAK=miss_streak; SCI_LONGEST_MISS=longest_miss;
    SCI_YEAR_NET=year_net; SCI_YEAR_STAKE=year_stake; SCI_FOLD_NET=fold_net; SCI_FOLD_STAKE=fold_stake;
    SCI_LARGEST_NET=largest_net; SCI_LARGEST_STAKE=largest_stake; SCI_LARGEST_ISSUE=largest_issue;
    SCI_FULL_ISSUE_NET=full_issue_net; SCI_FULL_ISSUE_STAKE=full_issue_stake;
    SCI_YEAR_COUNT=year_count; SCI_FOLD_COUNT=fold_count; SCI_ISSUE_COUNT=issue_count;
}

void bj167_scientific_set_candidate_issue_buffers(const int *candidate_science_at, int candidate_count,
                                                  double *net, double *stake, double *gross, double *tax, double *hit, double *tax_line_hit,
                                                  double *full_net, double *full_stake, double *full_gross, double *full_tax, double *full_hit) {
    SCI_CANDIDATE_SCIENCE_AT=candidate_science_at; SCI_CANDIDATE_COUNT=candidate_count;
    SCI_CAND_NET=net; SCI_CAND_STAKE=stake; SCI_CAND_GROSS=gross; SCI_CAND_TAX=tax; SCI_CAND_HIT=hit; SCI_CAND_TAX_LINE_HIT=tax_line_hit;
    SCI_CAND_FULL_NET=full_net; SCI_CAND_FULL_STAKE=full_stake; SCI_CAND_FULL_GROSS=full_gross; SCI_CAND_FULL_TAX=full_tax; SCI_CAND_FULL_HIT=full_hit;
}

void bj167_scientific_begin_issue(int issue_index, int year_index, int fold_index) {
    SCI_TOUCHED_LEN=0; SCI_ISSUE=issue_index; SCI_YEAR=year_index; SCI_FOLD=fold_index;
}

static void scientific_add(int selector, int cell, const int *metrics, double payout) {
    const int at = selector * SCI_CELLS_PER_SELECTOR + cell;
    if (!SCI_MARK[at]) { SCI_MARK[at]=1; SCI_TOUCHED[SCI_TOUCHED_LEN++]=at; }
    const double stake=2.0*(metrics[1]+metrics[2]), gross=payout*metrics[0];
    SCI_TMP_NET[at] += gross-stake; SCI_TMP_STAKE[at] += stake; SCI_TMP_GROSS[at] += gross;
    SCI_TMP_TAX[at] += payout >= 10000.0 ? payout*.20*metrics[0] : 0.0; SCI_TMP_HIT[at] += metrics[0]; SCI_TMP_TAX_LINE_HIT[at] += payout >= 10000.0 ? metrics[0] : 0.0;
}

void bj167_scientific_end_issue() {
    // Capture every frozen candidate, including a legitimate zero-stake
    // no-bet, before clearing the per-issue scratch ledger.  The layout is
    // candidate-major / chronological issue-minor and is checkpointed as-is.
    if (SCI_CANDIDATE_COUNT > 0) {
        if (SCI_CANDIDATE_SCIENCE_AT == nullptr || SCI_CAND_NET == nullptr || SCI_CAND_TAX_LINE_HIT == nullptr || SCI_ISSUE < 0) std::abort();
        for (int ci=0; ci<SCI_CANDIDATE_COUNT; ++ci) {
            const int at=SCI_CANDIDATE_SCIENCE_AT[ci];
            if (at < 0) std::abort();
            const int full_at=(at/SCI_CELLS_PER_SELECTOR)*SCI_CELLS_PER_SELECTOR+960;
            const std::size_t out=static_cast<std::size_t>(ci)*SCI_ISSUE_COUNT+SCI_ISSUE;
            const int local=at%SCI_CELLS_PER_SELECTOR;
            // WR/WOR science cells are pooled over the real 100 seeds, so
            // their matched FULL control must carry the same ticket scale.
            const int source_local=local%160;
            const double full_scale=(local<960 && source_local<40) ? static_cast<double>(SEEDCOUNT) : 1.0;
            SCI_CAND_NET[out]=SCI_TMP_NET[at]; SCI_CAND_STAKE[out]=SCI_TMP_STAKE[at]; SCI_CAND_GROSS[out]=SCI_TMP_GROSS[at]; SCI_CAND_TAX[out]=SCI_TMP_TAX[at]; SCI_CAND_HIT[out]=SCI_TMP_HIT[at]; SCI_CAND_TAX_LINE_HIT[out]=SCI_TMP_TAX_LINE_HIT[at];
            SCI_CAND_FULL_NET[out]=SCI_TMP_NET[full_at]*full_scale; SCI_CAND_FULL_STAKE[out]=SCI_TMP_STAKE[full_at]*full_scale; SCI_CAND_FULL_GROSS[out]=SCI_TMP_GROSS[full_at]*full_scale; SCI_CAND_FULL_TAX[out]=SCI_TMP_TAX[full_at]*full_scale; SCI_CAND_FULL_HIT[out]=SCI_TMP_HIT[full_at]*full_scale;
        }
    }
    for (int j=0;j<SCI_TOUCHED_LEN;++j) {
        const int at=SCI_TOUCHED[j]; const double net=SCI_TMP_NET[at], stake=SCI_TMP_STAKE[at];
        SCI_NET[at]+=net; SCI_STAKE[at]+=stake; SCI_GROSS[at]+=SCI_TMP_GROSS[at]; SCI_TAX[at]+=SCI_TMP_TAX[at]; SCI_HIT[at]+=SCI_TMP_HIT[at];
        SCI_GROSS_SUMSQ[at]+=SCI_TMP_GROSS[at]*SCI_TMP_GROSS[at]; if (SCI_TMP_GROSS[at] > SCI_GROSS_TOP[at]) SCI_GROSS_TOP[at]=SCI_TMP_GROSS[at];
        if (stake > 0.0) {
            SCI_CUM_NET[at] += net; if (SCI_CUM_NET[at] > SCI_PEAK_NET[at]) SCI_PEAK_NET[at]=SCI_CUM_NET[at];
            const double dd=SCI_PEAK_NET[at]-SCI_CUM_NET[at]; if (dd > SCI_DRAWDOWN[at]) SCI_DRAWDOWN[at]=dd;
            if (SCI_TMP_HIT[at] > 0.0) SCI_MISS_STREAK[at]=0; else { ++SCI_MISS_STREAK[at]; if (SCI_MISS_STREAK[at]>SCI_LONGEST_MISS[at]) SCI_LONGEST_MISS[at]=SCI_MISS_STREAK[at]; }
        }
        if (SCI_YEAR>=0) { const std::size_t yi=static_cast<std::size_t>(at)*SCI_YEAR_COUNT+SCI_YEAR; SCI_YEAR_NET[yi]+=net; SCI_YEAR_STAKE[yi]+=stake; }
        if (SCI_FOLD>=0) { const std::size_t fi=static_cast<std::size_t>(at)*SCI_FOLD_COUNT+SCI_FOLD; SCI_FOLD_NET[fi]+=net; SCI_FOLD_STAKE[fi]+=stake; }
        if (net > SCI_LARGEST_NET[at]) { SCI_LARGEST_NET[at]=net; SCI_LARGEST_STAKE[at]=stake; SCI_LARGEST_ISSUE[at]=SCI_ISSUE; }
        if (at % SCI_CELLS_PER_SELECTOR == 960 && SCI_ISSUE >= 0) {
            const int selector=at/SCI_CELLS_PER_SELECTOR;
            SCI_FULL_ISSUE_NET[static_cast<std::size_t>(selector)*SCI_ISSUE_COUNT+SCI_ISSUE]=net;
            SCI_FULL_ISSUE_STAKE[static_cast<std::size_t>(selector)*SCI_ISSUE_COUNT+SCI_ISSUE]=stake;
        }
        SCI_TMP_NET[at]=SCI_TMP_STAKE[at]=SCI_TMP_GROSS[at]=SCI_TMP_TAX[at]=SCI_TMP_HIT[at]=SCI_TMP_TAX_LINE_HIT[at]=0.0; SCI_MARK[at]=0;
    }
    SCI_TOUCHED_LEN=0;
}

void bj167_scientific_process_source(const double *role_probs, int truth, const char *seed_signature, double payout,
                                     const int *selector_ids, int occurrence_count, int source_base) {
    std::array<int, SEEDCOUNT*MCOUNT*4> wr{}, wor{};
    std::array<int, MCOUNT*4> residual{}, top{};
    std::array<int, 4*MCOUNT*4> capped{};
    std::array<int,4> full{};
    bj167_profile_allocation(role_probs, truth, seed_signature, wr.data(), wor.data(), residual.data(), capped.data(), top.data(), full.data());
    // source layout: WR[0:20], WOR[20:40], residual[40:60], capped[60:140], top[140:160].
    // WR/WOR aggregate all actual seeds; no fake repeated deterministic rows.
    for (int mi=0;mi<MCOUNT;++mi) {
        int wr_sum[4]={0,0,0,0}, wor_sum[4]={0,0,0,0};
        for (int si=0;si<SEEDCOUNT;++si) for (int k=0;k<4;++k) { wr_sum[k]+=wr[(si*MCOUNT+mi)*4+k]; wor_sum[k]+=wor[(si*MCOUNT+mi)*4+k]; }
        for (int oi=0;oi<occurrence_count;++oi) { scientific_add(selector_ids[oi],source_base+mi,wr_sum,payout); scientific_add(selector_ids[oi],source_base+20+mi,wor_sum,payout); scientific_add(selector_ids[oi],source_base+40+mi,residual.data()+mi*4,payout); scientific_add(selector_ids[oi],source_base+140+mi,top.data()+mi*4,payout); }
        for (int cap=0;cap<4;++cap) for (int oi=0;oi<occurrence_count;++oi) scientific_add(selector_ids[oi],source_base+60+cap*MCOUNT+mi,capped.data()+(cap*MCOUNT+mi)*4,payout);
        // Contractual equivalence at M=2187: WOR (after removing the 100x
        // seed multiplicity) and top-mass are exactly FULL ticket profiles.
        if (mi==MCOUNT-1) {
            for (int k=0;k<4;++k) if (wor_sum[k] != full[k]*SEEDCOUNT || top[mi*4+k] != full[k]) std::abort();
        }
    }
}

void bj167_scientific_add_structural(int selector, int truth_code, int p_leg, int p_code, int q_leg, int q_code, double payout) {
    const int full[4]={1,FULL_TICKETS,0,0};
    const int p_hit=((truth_code/static_cast<int>(std::pow(3,6-p_leg)))%3)!=p_code;
    const int q_hit=((truth_code/static_cast<int>(std::pow(3,6-q_leg)))%3)!=q_code;
    const int p[4]={p_hit,1458,0,0}, q[4]={q_hit,1458,0,0};
    scientific_add(selector,960,full,payout); scientific_add(selector,961,p,payout); scientific_add(selector,962,q,payout);
}

}
