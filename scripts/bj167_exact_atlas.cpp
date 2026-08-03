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

}
