// Exact action-level Stage-3 profiler for #193 Gate B v2.
//
// The accepted allocator implementation is included byte-for-byte.  This
// wrapper only applies the frozen action-specific replay signatures, averages
// nuisance seeds before returning economics, and settles one exact ticket
// truth/payout.  It never changes allocator arithmetic or tie behavior.
#include "bj145_fast_alloc.cpp"

#include <cstdio>
#include <vector>

extern "C" {

enum Bj193Mechanism {
    BJ193_WR = 0,
    BJ193_WOR = 1,
    BJ193_RESIDUAL = 2,
    BJ193_CAPPED = 3,
    BJ193_TOP = 4,
    BJ193_FULL = 5,
    BJ193_P_DELETE = 6,
    BJ193_Q_DELETE = 7,
};

static void bj193_write_money(int hits, int tickets, double payout,
                              double scale, double* gross, double* stake,
                              double* tax, double* net, double* hit) {
    const double one_gross = payout * static_cast<double>(hits);
    const double one_stake = 2.0 * static_cast<double>(tickets);
    const double one_tax = payout >= 10000.0
        ? 0.20 * payout * static_cast<double>(hits) : 0.0;
    *gross += one_gross * scale;
    *stake += one_stake * scale;
    *tax += one_tax * scale;
    *net += (one_gross - one_stake) * scale;
    *hit += static_cast<double>(hits) * scale;
}

void bj193_chain_profile_actions(
    const double* weights_flat, int source_count, int ticket_count, int truth,
    double payout, const int* source_index, const int* mechanism,
    const int* requested_m, const int* cap, const char* const* signatures,
    int action_count, int p_delete_truth_allowed, int p_delete_ticket_count,
    int q_delete_truth_allowed, int q_delete_ticket_count,
    unsigned char* status, double* gross, double* stake, double* tax,
    double* net, double* hit) {
    #pragma omp parallel for schedule(static)
    for (int action = 0; action < action_count; ++action) {
        status[action] = 0;
        gross[action] = stake[action] = tax[action] = net[action] = hit[action] = 0.0;
        const int mech = mechanism[action];
        if (mech == BJ193_P_DELETE || mech == BJ193_Q_DELETE) {
            const int allowed = mech == BJ193_P_DELETE
                ? p_delete_truth_allowed : q_delete_truth_allowed;
            const int tickets = mech == BJ193_P_DELETE
                ? p_delete_ticket_count : q_delete_ticket_count;
            if (tickets <= 0) continue;
            bj193_write_money(allowed, tickets, payout, 1.0, gross + action,
                              stake + action, tax + action, net + action,
                              hit + action);
            status[action] = 1;
            continue;
        }
        const int source = source_index[action];
        if (source < 0 || source >= source_count) continue;
        const double* weights = weights_flat
            + static_cast<std::size_t>(source) * ticket_count;
        int positive = 0;
        for (int ordinal = 0; ordinal < ticket_count; ++ordinal) {
            if (weights[ordinal] > 0.0) ++positive;
        }
        const int m = requested_m[action];
        if (positive == 0) continue;
        if ((mech == BJ193_WOR || mech == BJ193_TOP) && m > positive) continue;
        if (mech == BJ193_CAPPED &&
            (cap[action] <= 0 || m > positive * cap[action])) continue;
        if (mech == BJ193_FULL) {
            bj193_write_money(weights[truth] > 0.0 ? 1 : 0, positive, payout,
                              1.0, gross + action, stake + action,
                              tax + action, net + action, hit + action);
            status[action] = 1;
            continue;
        }
        if (mech == BJ193_TOP) {
            std::vector<int> order(ticket_count);
            std::iota(order.begin(), order.end(), 0);
            std::sort(order.begin(), order.end(), [&](int left, int right) {
                if (weights[left] != weights[right]) return weights[left] > weights[right];
                return left < right;
            });
            int hits = 0;
            for (int rank = 0; rank < m; ++rank) hits += order[rank] == truth;
            bj193_write_money(hits, m, payout, 1.0, gross + action,
                              stake + action, tax + action, net + action,
                              hit + action);
            status[action] = 1;
            continue;
        }
        int metrics[4] = {0, 0, 0, 0};
        if (mech == BJ193_RESIDUAL || mech == BJ193_CAPPED) {
            bj145_profile(weights, ticket_count, truth,
                          mech == BJ193_CAPPED ? cap[action] : 0,
                          requested_m + action, 1, metrics);
            bj193_write_money(metrics[0], metrics[1] + metrics[2], payout,
                              1.0, gross + action, stake + action,
                              tax + action, net + action, hit + action);
            status[action] = 1;
            continue;
        }
        if (mech == BJ193_WR || mech == BJ193_WOR) {
            char seed[16];
            for (int replicate = 0; replicate < 100; ++replicate) {
                std::snprintf(seed, sizeof(seed), "%d", 137001 + replicate);
                if (mech == BJ193_WR) {
                    bj145_wr_profile(weights, ticket_count, truth, seed,
                                     signatures[action], requested_m + action,
                                     1, metrics);
                } else {
                    bj145_wor_profile(weights, ticket_count, truth, seed,
                                      signatures[action], requested_m + action,
                                      1, metrics);
                }
                bj193_write_money(metrics[0], metrics[1] + metrics[2], payout,
                                  0.01, gross + action, stake + action,
                                  tax + action, net + action, hit + action);
            }
            status[action] = 1;
        }
    }
}

}  // extern "C"
