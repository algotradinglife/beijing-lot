// Exact bounded #193 replay glue.
//
// This translation unit deliberately reuses the accepted #167 wrapper and
// the byte-frozen #145 allocator.  It adds only one diagnostic sink: per-seed
// fold totals for stochastic WR/WOR cells.  The production economics continue
// to flow through bj167_scientific_* and are aggregated over all 100 seeds
// before any #193 screen, model, choice, oracle, or regret calculation.
#include "bj167_exact_atlas.cpp"

extern "C" {

static double *BJ193_SEED_NET = nullptr;
static double *BJ193_SEED_STAKE = nullptr;
static double *BJ193_ISSUE_NET = nullptr;
static double *BJ193_ISSUE_STAKE = nullptr;
static double *BJ193_ISSUE_GROSS = nullptr;
static double *BJ193_ISSUE_TAX = nullptr;
static double *BJ193_ISSUE_HIT = nullptr;
static double *BJ193_ISSUE_TAX_LINE_HIT = nullptr;
static int BJ193_LOCAL_SELECTOR_COUNT = 0;
static int BJ193_FOLD_COUNT = 0;
static int BJ193_CURRENT_FOLD = -1;

void bj193_set_seed_fold_buffers(double *seed_net, double *seed_stake,
                                 int local_selector_count, int fold_count) {
    BJ193_SEED_NET = seed_net;
    BJ193_SEED_STAKE = seed_stake;
    BJ193_LOCAL_SELECTOR_COUNT = local_selector_count;
    BJ193_FOLD_COUNT = fold_count;
}

void bj193_set_action_issue_buffers(double *net, double *stake, double *gross,
                                    double *tax, double *hit,
                                    double *tax_line_hit) {
    BJ193_ISSUE_NET = net;
    BJ193_ISSUE_STAKE = stake;
    BJ193_ISSUE_GROSS = gross;
    BJ193_ISSUE_TAX = tax;
    BJ193_ISSUE_HIT = hit;
    BJ193_ISSUE_TAX_LINE_HIT = tax_line_hit;
}

void bj193_begin_issue(int issue_index, int year_index, int fold_index) {
    BJ193_CURRENT_FOLD = fold_index;
    bj167_scientific_begin_issue(issue_index, year_index, fold_index);
}

void bj193_end_issue() {
    if (BJ193_ISSUE_NET == nullptr || SCI_ISSUE < 0) std::abort();
    const std::size_t cell_count =
        static_cast<std::size_t>(BJ193_LOCAL_SELECTOR_COUNT) *
        SCI_CELLS_PER_SELECTOR;
    for (std::size_t at = 0; at < cell_count; ++at) {
        const std::size_t out = at * SCI_ISSUE_COUNT + SCI_ISSUE;
        BJ193_ISSUE_NET[out] = SCI_TMP_NET[at];
        BJ193_ISSUE_STAKE[out] = SCI_TMP_STAKE[at];
        BJ193_ISSUE_GROSS[out] = SCI_TMP_GROSS[at];
        BJ193_ISSUE_TAX[out] = SCI_TMP_TAX[at];
        BJ193_ISSUE_HIT[out] = SCI_TMP_HIT[at];
        BJ193_ISSUE_TAX_LINE_HIT[out] = SCI_TMP_TAX_LINE_HIT[at];
    }
    bj167_scientific_end_issue();
}

static void bj193_add_seed_fold(int selector, int source_index, int mechanism_index,
                                int m_index, int seed_index, const int *metrics,
                                double payout) {
    if (BJ193_SEED_NET == nullptr || BJ193_SEED_STAKE == nullptr) return;
    if (selector < 0 || selector >= BJ193_LOCAL_SELECTOR_COUNT ||
        BJ193_CURRENT_FOLD < 0 || BJ193_CURRENT_FOLD >= BJ193_FOLD_COUNT ||
        source_index < 0 || source_index >= 6 ||
        mechanism_index < 0 || mechanism_index >= 2 ||
        m_index < 0 || m_index >= MCOUNT ||
        seed_index < 0 || seed_index >= SEEDCOUNT) {
        std::abort();
    }
    // [selector][source][WR/WOR][M][seed][fold]
    const std::size_t at =
        (((((static_cast<std::size_t>(selector) * 6u + source_index) * 2u +
             mechanism_index) * MCOUNT + m_index) * SEEDCOUNT + seed_index) *
             BJ193_FOLD_COUNT + BJ193_CURRENT_FOLD);
    const double stake = 2.0 * static_cast<double>(metrics[1] + metrics[2]);
    const double gross = payout * static_cast<double>(metrics[0]);
    BJ193_SEED_NET[at] += gross - stake;
    BJ193_SEED_STAKE[at] += stake;
}

void bj193_process_source(const double *role_probs, int truth,
                          const char *seed_signature, double payout,
                          const int *selector_ids, int occurrence_count,
                          int source_index) {
    if (source_index < 0 || source_index >= 6) std::abort();
    std::array<int, SEEDCOUNT * MCOUNT * 4> wr{}, wor{};
    std::array<int, MCOUNT * 4> residual{}, top{};
    std::array<int, 4 * MCOUNT * 4> capped{};
    std::array<int, 4> full{};
    bj167_profile_allocation(role_probs, truth, seed_signature, wr.data(), wor.data(),
                             residual.data(), capped.data(), top.data(), full.data());

    const int source_base = source_index * 160;
    for (int mi = 0; mi < MCOUNT; ++mi) {
        int wr_sum[4] = {0, 0, 0, 0};
        int wor_sum[4] = {0, 0, 0, 0};
        for (int seed = 0; seed < SEEDCOUNT; ++seed) {
            const int *wr_one = wr.data() + (seed * MCOUNT + mi) * 4;
            const int *wor_one = wor.data() + (seed * MCOUNT + mi) * 4;
            for (int k = 0; k < 4; ++k) {
                wr_sum[k] += wr_one[k];
                wor_sum[k] += wor_one[k];
            }
            for (int oi = 0; oi < occurrence_count; ++oi) {
                bj193_add_seed_fold(selector_ids[oi], source_index, 0, mi, seed,
                                    wr_one, payout);
                bj193_add_seed_fold(selector_ids[oi], source_index, 1, mi, seed,
                                    wor_one, payout);
            }
        }
        for (int oi = 0; oi < occurrence_count; ++oi) {
            scientific_add(selector_ids[oi], source_base + mi, wr_sum, payout);
            scientific_add(selector_ids[oi], source_base + 20 + mi, wor_sum, payout);
            scientific_add(selector_ids[oi], source_base + 40 + mi,
                           residual.data() + mi * 4, payout);
            scientific_add(selector_ids[oi], source_base + 140 + mi,
                           top.data() + mi * 4, payout);
            for (int cap = 0; cap < 4; ++cap) {
                scientific_add(selector_ids[oi], source_base + 60 + cap * MCOUNT + mi,
                               capped.data() + (cap * MCOUNT + mi) * 4, payout);
            }
        }
        if (mi == MCOUNT - 1) {
            for (int k = 0; k < 4; ++k) {
                if (wor_sum[k] != full[k] * SEEDCOUNT ||
                    top[mi * 4 + k] != full[k]) {
                    std::abort();
                }
            }
        }
    }
}

}  // extern "C"
