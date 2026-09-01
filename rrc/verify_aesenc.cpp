// 0x44 VERIFY AESENC -- mandatory verification for op 14 (feeder v3),
// BEFORE every ladder run. Four checks:
//
// 1) FIPS-197 appendix C.1 (AES-128):
//      PT  00112233445566778899aabbccddeeff
//      Key 000102030405060708090a0b0c0d0e0f
//      CT  69c4e0d86a7b0430d8cdb78070b4c55a
//    Full 10-round encryption from aesenc/aesenclast plus our own key
//    expansion (aeskeygenassist). If the ciphertext matches byte for
//    byte, the aesenc semantics (SubBytes/ShiftRows/MixColumns/
//    AddRoundKey) are proven on this machine.
// 2) Key cancellation (the reason op 14 has NO param):
//    aesenc(s,k) = MC(SR(SB(s))) ^ k and the fold lo^hi is xor-linear,
//    hence fold(y ^ k) = fold(y) ^ fold(k). With set1(k), fold(k) = k^k
//    = 0 -- the key vanishes COMPLETELY. With a one-sided key (lo only)
//    exactly ^k is left over, i.e. op 6 afterwards. Both identities are
//    recomputed empirically here. A key parameter would be a dead knob,
//    therefore: op 14 = keyless round, constant injection is done by the
//    chain itself (op 6/7 before it).
// 3) Determinism: same inputs computed twice (second run forced past
//    optimization by volatile), checksums must be equal.
// 4) Avalanche (informative, with anchors): mean flip rate of the output
//    bits per flipped input bit. Lower anchor: identity = 1/64. Upper
//    anchor: mix13 ~ 0.5. If the anchors are off, the METRIC is broken
//    -> rc 4. Expectation for ONE aes round: structurally ~0.25 (one
//    input byte reaches only one column = 4 bytes after ShiftRows/
//    MixColumns; the fold stacks column 0+2 and 1+3), only two rounds
//    mix fully. The ladder judges, not this number.
//
// Usage:
//   verify_aesenc              -> checks 1-4
//   verify_aesenc words <n>    -> first n op-14 values on the bare
//     counter (one hex line per value), for a bit-identical comparison
//     with: feeder_v3 chain 0 0 0 1 14 0
//
// Build: g++ -O2 -march=native -std=gnu++14 verify_aesenc.cpp -o verify_aesenc.exe
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <immintrin.h>

// --- Op 14, verbatim as in feeder.cpp chain_mix (keyless) ---
static inline uint64_t op14(uint64_t v) {
    __m128i st = _mm_cvtsi64_si128((long long)v);
    st = _mm_aesenc_si128(st, _mm_setzero_si128());
    return (uint64_t)_mm_cvtsi128_si64(st)
         ^ (uint64_t)_mm_extract_epi64(st, 1);
}
// Proof helper: the same round WITH a key.
static inline uint64_t op14_set1(uint64_t v, uint64_t k) {
    __m128i st = _mm_cvtsi64_si128((long long)v);
    st = _mm_aesenc_si128(st, _mm_set1_epi64x((long long)k));
    return (uint64_t)_mm_cvtsi128_si64(st)
         ^ (uint64_t)_mm_extract_epi64(st, 1);
}
static inline uint64_t op14_lo(uint64_t v, uint64_t k) {
    __m128i st = _mm_cvtsi64_si128((long long)v);
    st = _mm_aesenc_si128(st, _mm_set_epi64x(0, (long long)k));
    return (uint64_t)_mm_cvtsi128_si64(st)
         ^ (uint64_t)_mm_extract_epi64(st, 1);
}

// --- splitmix64 as input stream (as in verify_fmix64.cpp) ---
static inline uint64_t sm(uint64_t& s) {
    s += 0x9E3779B97F4A7C15ULL; uint64_t z = s;
    z ^= z >> 30; z *= 0xbf58476d1ce4e5b9ULL;
    z ^= z >> 27; z *= 0x94d049bb133111ebULL;
    z ^= z >> 31; return z;
}

// --- 1) FIPS-197 KAT --------------------------------------------------------
static inline __m128i exp_step(__m128i k, __m128i g) {
    g = _mm_shuffle_epi32(g, _MM_SHUFFLE(3, 3, 3, 3));
    k = _mm_xor_si128(k, _mm_slli_si128(k, 4));
    k = _mm_xor_si128(k, _mm_slli_si128(k, 4));
    k = _mm_xor_si128(k, _mm_slli_si128(k, 4));
    return _mm_xor_si128(k, g);
}
#define EXP(i, rcon) \
    rk[i] = exp_step(rk[i-1], _mm_aeskeygenassist_si128(rk[i-1], rcon))

static int kat_fips197(void) {
    const uint8_t pt[16]       = {0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,
                                  0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff};
    const uint8_t key[16]      = {0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,
                                  0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f};
    const uint8_t expected[16] = {0x69,0xc4,0xe0,0xd8,0x6a,0x7b,0x04,0x30,
                                  0xd8,0xcd,0xb7,0x80,0x70,0xb4,0xc5,0x5a};
    __m128i rk[11];
    rk[0] = _mm_loadu_si128((const __m128i*)key);
    EXP(1, 0x01); EXP(2, 0x02); EXP(3, 0x04); EXP(4, 0x08); EXP(5, 0x10);
    EXP(6, 0x20); EXP(7, 0x40); EXP(8, 0x80); EXP(9, 0x1b); EXP(10, 0x36);
    __m128i s = _mm_xor_si128(_mm_loadu_si128((const __m128i*)pt), rk[0]);
    for (int r = 1; r <= 9; r++) s = _mm_aesenc_si128(s, rk[r]);
    s = _mm_aesenclast_si128(s, rk[10]);
    uint8_t actual[16]; _mm_storeu_si128((__m128i*)actual, s);
    printf("FIPS-197 C.1:  actual ");
    for (int i = 0; i < 16; i++) printf("%02x", actual[i]);
    printf("\n             expected ");
    for (int i = 0; i < 16; i++) printf("%02x", expected[i]);
    const int ok = memcmp(actual, expected, 16) == 0;
    printf("  -> %s\n", ok ? "BIT-IDENTICAL" : "NOT BIT-IDENTICAL");
    return ok;
}

// --- 2) key cancellation ----------------------------------------------------
static int cancellation(void) {
    const uint64_t K1 = 0x9E3779B97F4A7C15ULL, K2 = 0xB853D68343F7525BULL;
    uint64_t s = 0x44; unsigned long long errors = 0, n = 0;
    for (uint64_t i = 0; i < (1ULL << 20); i++) {
        for (int w = 0; w < 2; w++) {
            const uint64_t v = w ? sm(s) : i; n++;
            if (op14_set1(v, K1) != op14(v)) errors++;      // set1: gone
            if (op14_set1(v, K2) != op14(v)) errors++;
            if (op14_lo(v, K1) != (op14(v) ^ K1)) errors++; // one-sided: ^k
        }
    }
    printf("Cancellation:  %llu inputs, violations: %llu -> %s\n", n, errors,
           errors ? "KEY HAS AN EFFECT (assumption wrong!)" : "PROVEN "
           "(set1 inconsequential, one-sided = ^k after; param rightly moot)");
    return errors == 0;
}

// --- 3) determinism ---------------------------------------------------------
static int determinism(void) {
    volatile uint64_t zero_v = 0;        // forces the 2nd run to recompute
    uint64_t h1 = 0, h2 = 0, s1 = 0x44, s2 = 0x44;
    for (uint64_t i = 0; i < (1ULL << 20); i++) {
        h1 ^= op14(i) + op14(sm(s1));
        h1 = (h1 << 1) | (h1 >> 63);
    }
    for (uint64_t i = 0; i < (1ULL << 20); i++) {
        h2 ^= op14(i ^ zero_v) + op14(sm(s2) ^ zero_v);
        h2 = (h2 << 1) | (h2 >> 63);
    }
    const int ok = h1 == h2;
    printf("Determinism:   2x 2^21 inputs, checksums %016llx / %016llx "
           "-> %s\n", (unsigned long long)h1, (unsigned long long)h2,
           ok ? "EQUAL" : "DIFFERENT");
    return ok;
}

// --- 4) avalanche with anchors ----------------------------------------------
static uint64_t ident(uint64_t v) { return v; }
static uint64_t mix13(uint64_t x) {
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31; return x;
}
static uint64_t aes1(uint64_t v) { return op14(v); }
static uint64_t aes2(uint64_t v) { return op14(op14(v)); }

static double avalanche(const char* name, uint64_t (*mix)(uint64_t)) {
    const int N = 1 << 16;
    uint64_t counts[64] = {0};
    uint64_t s = 0x44;
    for (int i = 0; i < N; i++) {
        const uint64_t v = sm(s), h = mix(v);
        for (int b = 0; b < 64; b++)
            counts[b] += (uint64_t)__builtin_popcountll(
                             h ^ mix(v ^ (1ULL << b)));
    }
    double mn = 1.0, mx = 0.0, sum = 0.0;
    for (int b = 0; b < 64; b++) {
        const double p = (double)counts[b] / (64.0 * N);
        if (p < mn) mn = p;
        if (p > mx) mx = p;
        sum += p;
    }
    const double mean = sum / 64.0;
    printf("Avalanche %-10s mean %.4f  min %.4f  max %.4f\n",
           name, mean, mn, mx);
    return mean;
}

int main(int argc, char** argv) {
    if (argc >= 3 && !strcmp(argv[1], "words")) {
        const long n = atol(argv[2]);
        for (long i = 0; i < n; i++)
            printf("%016llx\n", (unsigned long long)op14((uint64_t)i));
        return 0;
    }
    if (!kat_fips197()) return 1;
    if (!cancellation()) return 2;
    if (!determinism()) return 3;
    const double a_id = avalanche("identity", ident);
    const double a_13 = avalanche("mix13", mix13);
    avalanche("aes1", aes1);
    avalanche("aes2", aes2);
    if (a_id < 0.014 || a_id > 0.018 || a_13 < 0.49 || a_13 > 0.51) {
        printf("ANCHOR VIOLATED -- the avalanche metric itself is broken.\n");
        return 4;
    }
    printf("Anchors ok (identity %.4f, mix13 %.4f). Op 14 verified: "
           "FIPS-197 + cancellation + determinism passed.\n", a_id, a_13);
    return 0;
}
