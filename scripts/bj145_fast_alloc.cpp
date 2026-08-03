#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <numeric>
#include <string>
#include <random>
#include <vector>

// Small, dependency-free accelerator for the frozen Python allocator.  The
// arithmetic and tie order intentionally mirror bj145_allocation_engine.py;
// it returns only the four settlement metrics needed for each M.
extern "C" {

struct Sha256 {
    uint32_t h[8] = {0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    uint8_t block[64]{}; std::size_t used = 0; uint64_t bits = 0;
    static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
    static uint32_t be32(const uint8_t* p) { return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|uint32_t(p[3]); }
    static void put32(uint8_t* p, uint32_t x) { p[0]=uint8_t(x>>24); p[1]=uint8_t(x>>16); p[2]=uint8_t(x>>8); p[3]=uint8_t(x); }
    void transform(const uint8_t* p) {
        static const uint32_t k[64] = {
            0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
            0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
            0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
            0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
            0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
            0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
            0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
            0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
        uint32_t w[64]; for (int i=0;i<16;++i) w[i]=be32(p+4*i);
        for (int i=16;i<64;++i) { uint32_t a=w[i-15], b=w[i-2]; uint32_t s0=rotr(a,7)^rotr(a,18)^(a>>3); uint32_t s1=rotr(b,17)^rotr(b,19)^(b>>10); w[i]=w[i-16]+s0+w[i-7]+s1; }
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],x=h[7];
        for (int i=0;i<64;++i) { uint32_t s1=rotr(e,6)^rotr(e,11)^rotr(e,25); uint32_t ch=(e&f)^((~e)&g); uint32_t t1=x+s1+ch+k[i]+w[i]; uint32_t s0=rotr(a,2)^rotr(a,13)^rotr(a,22); uint32_t maj=(a&b)^(a&c)^(b&c); uint32_t t2=s0+maj; x=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2; }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=x;
    }
    void update(const uint8_t* p, std::size_t n) { bits += uint64_t(n)*8; while(n) { std::size_t take=std::min<std::size_t>(n,64-used); std::memcpy(block+used,p,take); used+=take; p+=take; n-=take; if(used==64){transform(block);used=0;} } }
    std::array<uint8_t,32> final() { block[used++]=0x80; if(used>56){while(used<64)block[used++]=0;transform(block);used=0;} while(used<56)block[used++]=0; for(int i=0;i<8;++i)block[56+i]=uint8_t(bits>>(56-8*i)); transform(block); std::array<uint8_t,32> out{}; for(int i=0;i<8;++i)put32(out.data()+4*i,h[i]); return out; }
};

static double stable_uniform(const char* family, const char* seed, const char* signature, int index) {
    std::string payload = std::string("bj137|") + family + "|" + seed + "|" + signature + "|" + std::to_string(index);
    Sha256 sha; sha.update(reinterpret_cast<const uint8_t*>(payload.data()), payload.size()); auto digest=sha.final();
    uint64_t value=0; for(int i=0;i<8;++i)value=(value<<8)|digest[i];
    return (static_cast<double>(value)+0.5) / 18446744073709551616.0;
}

static void write_metrics(const std::vector<int>& counts, int truth, int m, int* out) {
    int unique = 0, duplicate = 0, groups = 0;
    for (int value : counts) {
        if (value > 0) ++unique;
        if (value > 1) duplicate += value - 1;
        if (value > 1) ++groups;
    }
    out[0] = counts[truth];
    out[1] = unique;
    out[2] = duplicate;
    out[3] = groups;
}

static void hamilton(const double* weights, int k, int m, std::vector<int>& counts) {
    double total = 0.0;
    for (int i = 0; i < k; ++i) total += weights[i];
    std::vector<double> fractions(k);
    counts.assign(k, 0);
    int used = 0;
    for (int i = 0; i < k; ++i) {
        const double quota = static_cast<double>(m) * weights[i] / total;
        const int base = static_cast<int>(std::floor(quota));
        counts[i] = base;
        used += base;
        fractions[i] = quota - static_cast<double>(base);
    }
    std::vector<int> order(k);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (fractions[a] != fractions[b]) return fractions[a] > fractions[b];
        return a < b;
    });
    for (int j = 0; j < m - used; ++j) ++counts[order[j]];
}

static void capped_hamilton(const double* weights, int k, int m, int cap, std::vector<int>& counts) {
    counts.assign(k, 0);
    int remaining = m;
    std::vector<int> active;
    std::vector<double> quotas(k);
    while (remaining) {
        active.clear();
        for (int i = 0; i < k; ++i) if (counts[i] < cap) active.push_back(i);
        double active_weight = 0.0;
        for (int i : active) active_weight += weights[i];
        const bool uniform = active_weight <= 0.0;
        int added = 0;
        for (int i : active) {
            const double effective = uniform ? 1.0 : weights[i];
            const double quota = static_cast<double>(remaining) * effective / (uniform ? static_cast<double>(active.size()) : active_weight);
            quotas[i] = quota;
            const int amount = std::min(static_cast<int>(std::floor(quota)), cap - counts[i]);
            if (amount > 0) { counts[i] += amount; added += amount; }
        }
        if (added) { remaining -= added; continue; }
        int chosen = active.front();
        double best_fraction = quotas[chosen] - std::floor(quotas[chosen]);
        for (std::size_t j = 1; j < active.size(); ++j) {
            const int candidate = active[j];
            const double fraction = quotas[candidate] - std::floor(quotas[candidate]);
            if (fraction > best_fraction || (fraction == best_fraction && candidate < chosen)) {
                chosen = candidate; best_fraction = fraction;
            }
        }
        ++counts[chosen]; --remaining;
    }
}

void bj145_profile(const double* weights, int k, int truth, int cap, const int* ms, int n_m, int* out) {
    std::vector<int> counts;
    for (int j = 0; j < n_m; ++j) {
        const int m = ms[j];
        if (cap == 0) hamilton(weights, k, m, counts);
        else capped_hamilton(weights, k, m, cap, counts);
        write_metrics(counts, truth, m, out + j * 4);
    }
}

void bj145_wr_profile(const double* weights, int k, int truth, const char* seed, const char* signature, const int* ms, int n_m, int* out) {
    const int maximum = ms[n_m - 1];
    std::vector<double> cumulative(k); double running=0.0;
    for(int i=0;i<k;++i){running+=weights[i];cumulative[i]=running;}
    std::vector<int> counts(k,0); int hits=0,unique=0,groups=0,grid=0;
    for(int draw=1;draw<=maximum;++draw){
        const double unit=stable_uniform("WR",seed,signature,draw-1);
        const auto found = std::lower_bound(cumulative.begin(), cumulative.end(), unit);
        const int ticket = found == cumulative.end() ? k - 1 : static_cast<int>(found - cumulative.begin());
        const int prior=counts[ticket]; ++counts[ticket]; if(ticket==truth)++hits; if(prior==0)++unique; if(prior==1)++groups;
        if(grid<n_m && draw==ms[grid]){out[grid*4]=hits;out[grid*4+1]=unique;out[grid*4+2]=draw-unique;out[grid*4+3]=groups;++grid;}
    }
}

void bj145_wor_profile(const double* weights, int k, int truth, const char* seed, const char* signature, const int* ms, int n_m, int* out) {
    std::vector<std::pair<double,int>> keys; keys.reserve(k);
    for(int i=0;i<k;++i){double key=weights[i]>0.0 ? -std::log(std::max(stable_uniform("WOR",seed,signature,i),1e-18))/weights[i] : INFINITY; keys.emplace_back(key,i);}
    std::sort(keys.begin(),keys.end(),[](const auto&a,const auto&b){if(a.first!=b.first)return a.first<b.first;return a.second<b.second;});
    int rank=0; for(int i=0;i<k;++i)if(keys[i].second==truth){rank=i+1;break;}
    for(int j=0;j<n_m;++j){int m=ms[j];out[j*4]=rank<=m;out[j*4+1]=m;out[j*4+2]=0;out[j*4+3]=0;}
}

// Aggregate complete ticket-code marginals for a frozen identity cohort.  The
// existing profile entry points intentionally return only settlement metrics;
// this additive entry point exposes the full allocation vector needed by the
// Gate-B outcome-code atlas.  It does not accept outcomes or payouts: `truths`
// is used only to keep actual-hit counts separate from allocation frequency.
static void snapshot(const std::vector<int>& counts, int truth, int m, int k, int index,
                     long long* allocated, long long* actual_identity, long long* actual_hit) {
    for (int ordinal = 0; ordinal < k; ++ordinal) {
        allocated[index * k + ordinal] += counts[ordinal];
    }
    if (truth >= 0 && truth < k) {
        actual_identity[index * k + truth] += 1;
        actual_hit[index * k + truth] += counts[truth];
    }
}

void bj145_code_aggregate_grid(const double* weights_flat, int n_identity, int k,
                               const int* truths, const char* const* signatures,
                               int mechanism, int cap, const char* seed,
                               const int* ms, int n_m, long long* allocated,
                               long long* actual_identity, long long* actual_hit) {
    if (n_identity < 0 || k <= 0 || n_m <= 0) return;
    for (int identity = 0; identity < n_identity; ++identity) {
        const double* weights = weights_flat + static_cast<std::size_t>(identity) * k;
        const int truth = truths[identity];
        const char* signature = signatures[identity];
        std::vector<int> counts;
        if (mechanism == 0 || mechanism == 1) {
            // WR/WOR can be generated once and copied at each requested M.
            counts.assign(k, 0);
            if (mechanism == 0) {
                std::vector<double> cumulative(k); double running = 0.0;
                for (int ordinal = 0; ordinal < k; ++ordinal) { running += weights[ordinal]; cumulative[ordinal] = running; }
                int grid = 0;
                for (int draw = 1; draw <= ms[n_m - 1]; ++draw) {
                    const double unit = stable_uniform("WR", seed, signature, draw - 1);
                    const auto found = std::lower_bound(cumulative.begin(), cumulative.end(), unit);
                    const int ticket = found == cumulative.end() ? k - 1 : static_cast<int>(found - cumulative.begin());
                    ++counts[ticket];
                    if (grid < n_m && draw == ms[grid]) { snapshot(counts, truth, draw, k, grid, allocated, actual_identity, actual_hit); ++grid; }
                }
            } else {
                std::vector<std::pair<double, int>> keys; keys.reserve(k);
                for (int ordinal = 0; ordinal < k; ++ordinal) {
                    const double key = weights[ordinal] > 0.0 ? -std::log(std::max(stable_uniform("WOR", seed, signature, ordinal), 1e-18)) / weights[ordinal] : INFINITY;
                    keys.emplace_back(key, ordinal);
                }
                std::sort(keys.begin(), keys.end(), [](const auto& a, const auto& b) { if (a.first != b.first) return a.first < b.first; return a.second < b.second; });
                int grid = 0;
                for (int rank = 0; rank < k && grid < n_m; ++rank) {
                    ++counts[keys[rank].second];
                    if (rank + 1 == ms[grid]) { snapshot(counts, truth, rank + 1, k, grid, allocated, actual_identity, actual_hit); ++grid; }
                }
            }
            continue;
        }
        for (int grid = 0; grid < n_m; ++grid) {
            const int m = ms[grid];
            if (mechanism == 2) hamilton(weights, k, m, counts);
            else if (mechanism == 3) capped_hamilton(weights, k, m, cap, counts);
            else if (mechanism == 4) {
                counts.assign(k, 0);
                std::vector<int> order(k); std::iota(order.begin(), order.end(), 0);
                std::sort(order.begin(), order.end(), [&](int a, int b) { if (weights[a] != weights[b]) return weights[a] > weights[b]; return a < b; });
                for (int rank = 0; rank < m; ++rank) ++counts[order[rank]];
            } else if (mechanism == 5) counts.assign(k, 1);
            else return;
            snapshot(counts, truth, m, k, grid, allocated, actual_identity, actual_hit);
        }
    }
}

void bj145_bootstrap(const double* candidate_net, const double* candidate_stake, const double* baseline_net, const double* baseline_stake, int n, int replicates, uint64_t seed, double* out) {
    double total_cn=0.0,total_cs=0.0,total_bn=0.0,total_bs=0.0;
    for(int i=0;i<n;++i){total_cn+=candidate_net[i];total_cs+=candidate_stake[i];total_bn+=baseline_net[i];total_bs+=baseline_stake[i];}
    const double point=total_cn/total_cs-total_bn/total_bs;
    std::mt19937_64 rng(seed); std::uniform_int_distribution<int> pick(0,n-1); std::vector<double> samples; samples.reserve(replicates); int ge=0,le=0;
    for(int r=0;r<replicates;++r){double cn=0.0,cs=0.0,bn=0.0,bs=0.0; for(int j=0;j<n;++j){int i=pick(rng);cn+=candidate_net[i];cs+=candidate_stake[i];bn+=baseline_net[i];bs+=baseline_stake[i];} double d=cn/cs-bn/bs;samples.push_back(d);if(d>=0)++ge;if(d<=0)++le;}
    std::sort(samples.begin(),samples.end());
    const int low=std::max(0,static_cast<int>(std::floor(0.025*replicates))); const int high=std::max(0,static_cast<int>(std::ceil(0.975*replicates))-1);
    out[0]=point;out[1]=samples[low];out[2]=samples[high];out[3]=double(1+le)/double(1+replicates);out[4]=std::min(1.0,2.0*std::min(double(1+ge)/double(1+replicates),double(1+le)/double(1+replicates)));
}

}
