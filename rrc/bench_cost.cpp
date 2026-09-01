/* What the cost column is worth, measured instead of asserted.
 *
 *   g++ -O3 -march=native -std=gnu++14 bench_cost.cpp -o bench_cost.exe
 *   ./bench_cost.exe [iterations]
 *
 * Every cost figure in this repository comes from a weight table: multiply
 * 3, multiply-fold 4, shift-xor 2, rotate 1, constant 1. The table is a
 * latency convention, and until this file existed there was no measurement
 * behind it at all: the quality axis had 256 terabytes, the cost axis had
 * a spreadsheet. That asymmetry is worth closing, and closing it may well
 * disagree with the table. Disagreement is the point: a convention that
 * survives its own measurement is worth more afterwards.
 *
 * What is measured: latency of a dependent chain, x = mix(x), which is the
 * shape a finalizer sits in when a hash table needs the result before it
 * can probe. Not throughput; independent calls pipeline and would flatter
 * the wide mixers.
 *
 * What is not measured: throughput, code size, the cost of the constants in
 * i-cache, and anything about a different CPU. One machine, one compiler.
 * The numbers below are a datum, not a law.
 *
 * The clock: steady_clock. On this toolchain high_resolution_clock is an
 * alias for system_clock and moves in half-millisecond steps, so a naive
 * timing loop reports quantised nonsense. That trap cost a day once.
 */
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <chrono>
#include <immintrin.h>

static inline uint64_t ror64(uint64_t x, int k) {
    k &= 63; return k ? (x >> k) | (x << (64 - k)) : x;
}
static inline uint64_t mulfold(uint64_t v, uint64_t c) {
    __uint128_t r = (__uint128_t)v * (__uint128_t)c;
    return (uint64_t)r ^ (uint64_t)(r >> 64);
}

static inline uint64_t mix13(uint64_t x) {          /* cost 12 */
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31; return x;
}
static inline uint64_t fmix64(uint64_t x) {         /* cost 12 */
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33; return x;
}
static inline uint64_t moremur(uint64_t x) {        /* cost 12 */
    x ^= x >> 27; x *= 0x3C79AC492BA7B653ULL;
    x ^= x >> 33; x *= 0x1C69B3F74AC4AE35ULL;
    x ^= x >> 27; return x;
}
static inline uint64_t nasam(uint64_t x) {          /* cost ~15 */
    x ^= ror64(x, 25) ^ ror64(x, 47);
    x *= 0x9E6C63D0676A9A99ULL;
    x ^= x >> 23 ^ x >> 51;
    x *= 0x9E6D62D06F6A9A9BULL;
    x ^= x >> 23 ^ x >> 51;
    return x;
}
static inline uint64_t mulfold2(uint64_t x) {       /* cost 8 */
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
static inline uint64_t lu9(uint64_t x) {            /* cost 9 */
    x ^= 0x9E3779B97F4A7C15ULL;
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
static inline uint64_t mfa9(uint64_t x) {           /* cost 9 */
    x += 0x9E3779B97F4A7C15ULL;
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
static inline uint64_t meer10(uint64_t x) {         /* cost 10 */
    x = mulfold(x, 0x5846dfed2f0e1d49ULL);
    x ^= (x >> 28) ^ (x >> 6);
    return mulfold(x, 0x781f94b96e8edb3bULL);
}
static inline uint64_t wyrand_fin(uint64_t x) {     /* cost 5 */
    return mulfold(x, x ^ 0x8bb84b93962eacc9ULL);
}

struct Row { const char *name; int cost; uint64_t (*f)(uint64_t); };
static const Row ROWS[] = {
    {"wyrand step", 5, wyrand_fin}, {"mulfold x2", 8, mulfold2},
    {"lu9", 9, lu9}, {"mfa9", 9, mfa9}, {"meer10", 10, meer10},
    {"mix13", 12, mix13}, {"fmix64", 12, fmix64}, {"moremur", 12, moremur},
    {"nasam", 15, nasam},
};

int main(int argc, char **argv) {
    const uint64_t N = (argc > 1) ? strtoull(argv[1], 0, 10) : 200000000ULL;
    printf("dependent-chain latency, %llu iterations each\n",
           (unsigned long long)N);
    printf("%-13s %5s %11s %11s %9s\n",
           "mixer", "cost", "ns/call", "per point", "ratio");

    double base_ns = 0.0, base_cost = 0.0;
    for (unsigned i = 0; i < sizeof(ROWS) / sizeof(ROWS[0]); i++) {
        /* warm-up, so the first row is not the one that pays for the
           frequency ramp, which alone moved the first entry by 15 % */
        uint64_t x = 0x9E3779B97F4A7C15ULL;
        for (uint64_t j = 0; j < N / 20; j++) x = ROWS[i].f(x);
        volatile uint64_t sink0 = x; (void)sink0;

        auto t0 = std::chrono::steady_clock::now();
        for (uint64_t j = 0; j < N; j++) x = ROWS[i].f(x);
        auto t1 = std::chrono::steady_clock::now();
        volatile uint64_t sink = x; (void)sink;

        double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / N;
        if (i == 0) { base_ns = ns; base_cost = ROWS[i].cost; }
        printf("%-13s %5d %11.3f %11.3f %9.2f\n", ROWS[i].name, ROWS[i].cost,
               ns, ns / ROWS[i].cost,
               (ns / base_ns) / (ROWS[i].cost / base_cost));
    }
    printf("\n'per point' is nanoseconds divided by the weighted cost: if the\n");
    printf("table were a good latency model these would be equal. 'ratio' is\n");
    printf("measured slowdown over predicted slowdown, against the first row.\n");
    return 0;
}
