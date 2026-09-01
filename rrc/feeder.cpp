// 0x44 RRC FEEDER. Feeds mixer(ror64(T(counter)^C, r)) as raw
// 64-bit LE words to stdout, for PractRand RNG_test stdin64.
//
// Call: feeder <mixer> <T> <C> <r>
//   mixer: mix13 | fmix64 | mulfold2 | meer10 | ... | chain | user
//          "user" = your own mixer from mixer_user.h, see below
//   T: 0 = identity, 1 = bit reversal
//   C: 0 = no complement, 1 = complement (^~0)
//   r: rotation 0..63 (ror)
//
// Windows requirement: put stdout into binary mode, otherwise the
// 0x0A->0x0D0A translation silently destroys the stream. Buffered
// (512 KB), ends cleanly when RNG_test closes the pipe.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <immintrin.h>   // AES-NI (aesenc) + SSE4.1 (extract) for op 14
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif

// Op 14 (aesenc) only if the build can do AES-NI + SSE4.1 (-march=native
// on this machine). Without both the feeder still builds, but rejects
// type 14 at runtime. Never silently wave it through as identity.
#if defined(__AES__) && defined(__SSE4_1__)
#define OP14_AVAILABLE 1
#else
#define OP14_AVAILABLE 0
#endif

static inline uint64_t ror64(uint64_t x, int k) {
    k &= 63; return k ? (x >> k) | (x << (64 - k)) : x;
}
static inline uint64_t bitrev64(uint64_t x) {
    x = ((x >> 1)  & 0x5555555555555555ULL) | ((x & 0x5555555555555555ULL) << 1);
    x = ((x >> 2)  & 0x3333333333333333ULL) | ((x & 0x3333333333333333ULL) << 2);
    x = ((x >> 4)  & 0x0F0F0F0F0F0F0F0FULL) | ((x & 0x0F0F0F0F0F0F0F0FULL) << 4);
    x = ((x >> 8)  & 0x00FF00FF00FF00FFULL) | ((x & 0x00FF00FF00FF00FFULL) << 8);
    x = ((x >> 16) & 0x0000FFFF0000FFFFULL) | ((x & 0x0000FFFF0000FFFFULL) << 16);
    return (x >> 32) | (x << 32);
}

static inline uint64_t mix13(uint64_t x) {          // Stafford mix13 (splitmix64)
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31; return x;
}
static inline uint64_t fmix64(uint64_t x) {         // Murmur3 finalizer
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33; return x;
}
static inline uint64_t mulfold(uint64_t v, uint64_t c) {
    __uint128_t r = (__uint128_t)v * (__uint128_t)c;
    return (uint64_t)r ^ (uint64_t)(r >> 64);
}
static inline uint64_t mulfold2(uint64_t x) {       // mulfold x2, bare: hash class, K8
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
static inline uint64_t moremur(uint64_t x) {        // Evensen 12/2019 (verified)
    x ^= x >> 27; x *= 0x3C79AC492BA7B653ULL;
    x ^= x >> 33; x *= 0x1C69B3F74AC4AE35ULL;
    x ^= x >> 27; return x;
}
// K9 candidates against the measured mulfold weakness: inputs with low
// multiplicative weight (small OR many trailing zeros) produce a thin,
// structured 128-bit product. One constant up front (cost 1) makes every
// input generic.
static inline uint64_t mfx9(uint64_t x) {           // ^const + mulfold x2
    x ^= 0x9E3779B97F4A7C15ULL;
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
static inline uint64_t mfa9(uint64_t x) {           // +const + mulfold x2
    x += 0x9E3779B97F4A7C15ULL;
    x = mulfold(x, 0x781f94b96e8edb3bULL);
    return mulfold(x, 0xb853d68343f7525bULL);
}
// meer10, the chain that passed RRC-64-40 (256 streams x 1 TB, 256/256).
// Named here as well as reachable through chain=, because the repository's
// headline result should not exist only as a string in prose. The two forms
// are byte-identical; ladder.py's acid test does not check that, so
// verify_meer10.c does, against a stream written by this binary.
//   chain form: chain=8:5846dfed2f0e1d49,10:706,8:781f94b96e8edb3b
static inline uint64_t meer10(uint64_t x) {         // fold, xsh2(28,6), fold
    x = mulfold(x, 0x5846dfed2f0e1d49ULL);
    x ^= (x >> 28) ^ (x >> 6);
    return mulfold(x, 0x781f94b96e8edb3bULL);
}
static inline uint64_t mf2b(uint64_t x) {           // mulfold x2, other constants
    x = mulfold(x, 0x9E3779B97F4A7C15ULL);          // (constant sensitivity)
    return mulfold(x, 0xC2B2AE3D27D4EB4FULL);
}
// ── wyhash, verbatim from wangyi-fudan/wyhash (master, wyhash.h) ──────────
// Occasion 2026-08-20: mfx9 fails in the diploma at 2^38. mfx9 is NOT
// wyhash, only "its pattern". For a statement about wyhash itself the
// original code has to go on the ladder, so here it is.
//   _wymix(A,B) = lo(A*B) ^ hi(A*B), identical to our mulfold
//   _wyp[0..3]  = the standard secrets from the source
static const uint64_t WYP0 = 0x2d358dccaa6c78a5ULL;
static const uint64_t WYP1 = 0x8bb84b93962eacc9ULL;

static inline uint64_t wymix(uint64_t A, uint64_t B) {
    __uint128_t r = (__uint128_t)A * (__uint128_t)B;
    return (uint64_t)r ^ (uint64_t)(r >> 64);
}
// wyrand finalizer: the step wyrand takes after the counter increment.
// Read as a 64-bit mixer it costs K5 (xor 1 + fold 4).
//   static inline uint64_t wyrand(uint64_t *seed){
//     *seed+=0x2d358dccaa6c78a5ull;
//     return _wymix(*seed,*seed^0x8bb84b93962eacc9ull); }
static inline uint64_t wyrand_fin(uint64_t x) {
    return wymix(x, x ^ WYP1);
}
// The real wyhash hash path for EXACTLY 8 input bytes, seed=0.
// From the source (len<=16, len>=4):
//   a=(_wyr4(p)<<32)|_wyr4(p+((len>>3)<<2));      len=8 -> (lo32<<32)|hi32
//   b=(_wyr4(p+len-4)<<32)|_wyr4(p+len-4-((len>>3)<<2));  ->  x
//   a^=secret[1]; b^=seed; _wymum(&a,&b);
//   return _wymix(a^secret[0]^len, b^secret[1]);
// Seed preparation as in wyhash(): seed^=_wymix(seed^secret[0],secret[1]).
static inline uint64_t wyhash8(uint64_t x) {
    uint64_t seed = 0;
    seed ^= wymix(seed ^ WYP0, WYP1);
    uint64_t a = (x << 32) | (x >> 32);
    uint64_t b = x;
    a ^= WYP1; b ^= seed;
    __uint128_t r = (__uint128_t)a * (__uint128_t)b;
    a = (uint64_t)r; b = (uint64_t)(r >> 64);
    return wymix(a ^ WYP0 ^ 8, b ^ WYP1);
}

static inline uint64_t nasam(uint64_t x) {          // Evensen 01/2020 (verified)
    x ^= ror64(x, 25) ^ ror64(x, 47);
    x *= 0x9E6C63D0676A9A99ULL;
    x ^= x >> 23 ^ x >> 51;
    x *= 0x9E6D62D06F6A9A9BULL;
    x ^= x >> 23 ^ x >> 51;
    return x;
}

// Generic chain: arbitrary op sequence from argv, op inventory as in the
// forge harness. That way EVERY candidate runs on the ladder without the
// feeder having to be rebuilt.
//   feeder chain <T> <C> <r> <n> <type> <hex> [<type> <hex> ...]
struct Op { int type; uint64_t p; };
static Op CHAIN_OPS[12]; static int CHAIN_N = 0;
static inline uint64_t rotl64(uint64_t x, int k) {
    k &= 63; return k ? (x << k) | (x >> (64 - k)) : x;
}
static uint64_t chain_mix(uint64_t v) {
    // Op inventory. Types 0-8 = family 1 (mult+xorshift). Types 9-13 are
    // the STRUCTURALLY NEW building blocks that let the search form the
    // families 2/3 (Evensen/NASAM) for the first time. All guaranteed
    // bijective.
    //   9  xrot2:   v ^= rotl(v,a) ^ rotl(v,b)   param = a*64+b, a!=b
    //  10  xshift2: v ^= v>>a ^ v>>b             param = a*64+b, a!=b, >=1
    //  11  bswap    12 bitreverse    13 not      param irrelevant
    //  14  aesenc (AES-NI class, not portable, cost ~5, param IRRELEVANT):
    //      v into the low XMM half, one AES round (SubBytes/
    //      ShiftRows/MixColumns), then fold lo^hi back to 64 bits.
    //      The round key cancels itself out under the xor fold
    //      (fold(y^k) = fold(y)^fold(k); set1: k^k = 0, every other
    //      assignment is only a ^const afterwards = op 6), so it is
    //      deliberately keyless. Like type 8 HASH class (fold, not
    //      guaranteed bijective), only for the hash space. Proof +
    //      FIPS-197: verify_aesenc.cpp.
    for (int i = 0; i < CHAIN_N; i++) {
        const Op& o = CHAIN_OPS[i]; const int s = (int)(o.p & 63);
        const int a = (int)((o.p >> 6) & 63), b = (int)(o.p & 63);
        switch (o.type) {
            case 0: v ^= v >> s;                        break;
            case 1: v *= o.p;                           break;
            case 2: v = rotl64(v, s);                   break;
            case 3: v ^= v << s;                        break;
            case 4: v ^= rotl64(v, s);                  break;   // NOT bijective
            case 5: v += v << s;                        break;
            case 6: v ^= o.p;                           break;
            case 7: v += o.p;                           break;
            case 8: v = mulfold(v, o.p);                break;
            case 9: v ^= rotl64(v, a) ^ rotl64(v, b);   break;
            case 10: v ^= (v >> a) ^ (v >> b);          break;
            case 11: v = __builtin_bswap64(v);          break;
            case 12: v = bitrev64(v);                   break;
            case 13: v = ~v;                            break;
#if OP14_AVAILABLE
            case 14: {                                  // AES-NI class
                __m128i st = _mm_cvtsi64_si128((long long)v);
                st = _mm_aesenc_si128(st, _mm_setzero_si128());
                v = (uint64_t)_mm_cvtsi128_si64(st)
                  ^ (uint64_t)_mm_extract_epi64(st, 1);
                break;
            }
#endif
            // Unreachable: the parser rejects anything outside 0..14.
            // Loud rather than silent, because the version of this line
            // that simply said "break" turned a typo into a measurement
            // of the identity function.
            default:
                fprintf(stderr, "chain: unreachable op type %d\n", o.type);
                std::exit(2);
        }
    }
    return v;
}

// ---------------------------------------------------------------------
// YOUR MIXER GOES HERE. The whole point of this rig.
//
// Put a file named mixer_user.h next to this one that defines
//
//     static inline uint64_t user_mix(uint64_t x) { ...; return x; }
//
// rebuild, and run it under the name "user". Nothing in feeder.cpp needs
// editing: your mixer survives every update of the ladder, and the
// ladder never has to carry a patch of yours.
//
// Everything above is yours to use: ror64, rotl64, bitrev64, mulfold.
//
// If the header is absent the feeder still builds and simply does not
// know the name "user". That is deliberate: a mixer that was never
// compiled in must look like a mixer that was never compiled in, not
// like one that passed.
// ---------------------------------------------------------------------
#if defined(__has_include)
#  if __has_include("mixer_user.h")
#    include "mixer_user.h"
#    define HAVE_USER_MIX 1
#  endif
#endif

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "feeder <mixer> <T> <C> <r> "
                                    "[chain: <n> <type> <hex> ...]\n"); return 2; }
    const char* name = argv[1];
    const int T = atoi(argv[2]), C = atoi(argv[3]), r = atoi(argv[4]) & 63;
    uint64_t (*mix)(uint64_t) = 0;
    if (!strcmp(name, "chain")) {
        if (argc < 6) { fprintf(stderr, "chain needs <n> <type> <hex>...\n"); return 2; }
        CHAIN_N = atoi(argv[5]);
        if (CHAIN_N < 1 || CHAIN_N > 12 || argc != 6 + 2 * CHAIN_N) {
            fprintf(stderr, "chain: n=%d does not match %d arguments\n", CHAIN_N, argc);
            return 2;
        }
        for (int i = 0; i < CHAIN_N; i++) {
            CHAIN_OPS[i].type = atoi(argv[6 + 2 * i]);
            CHAIN_OPS[i].p    = strtoull(argv[7 + 2 * i], 0, 16);
            // Reject an unknown op type here, at parse time. Until
            // 30.08.26 only type 14 without AES-NI was caught; every
            // other out-of-range value passed the parser, reached
            // "default:" in the switch and was executed as the identity.
            // A typo in a chain therefore measured a DIFFERENT function
            // and reported a clean-looking verdict for it: the exact
            // failure this rig exists to catch, sitting inside the rig.
            if (CHAIN_OPS[i].type < 0 || CHAIN_OPS[i].type > 14) {
                fprintf(stderr, "chain: op type %d is not defined "
                                "(valid: 0..14)\n", CHAIN_OPS[i].type);
                return 2;
            }
            if (CHAIN_OPS[i].type == 14 && !OP14_AVAILABLE) {
                fprintf(stderr, "Op 14 (aesenc): this build cannot do "
                                "AES-NI (-march=native required)\n");
                return 2;
            }
        }
        mix = chain_mix;
    }
    else if (!strcmp(name, "mix13"))    mix = mix13;
    else if (!strcmp(name, "fmix64"))   mix = fmix64;
    else if (!strcmp(name, "mulfold2")) mix = mulfold2;
    else if (!strcmp(name, "moremur"))  mix = moremur;
    else if (!strcmp(name, "nasam"))    mix = nasam;
    else if (!strcmp(name, "mfx9"))     mix = mfx9;
    else if (!strcmp(name, "mfa9"))     mix = mfa9;
    else if (!strcmp(name, "mf2b"))     mix = mf2b;
    else if (!strcmp(name, "meer10"))   mix = meer10;
    else if (!strcmp(name, "wyrand"))   mix = wyrand_fin;
    else if (!strcmp(name, "wyhash8"))  mix = wyhash8;
#ifdef HAVE_USER_MIX
    else if (!strcmp(name, "user"))     mix = user_mix;
#else
    else if (!strcmp(name, "user")) {
        fprintf(stderr, "mixer 'user' was requested, but this feeder was built "
                        "without mixer_user.h.\nPut mixer_user.h next to "
                        "feeder.cpp (it must define user_mix) and rebuild.\n");
        return 2;
    }
#endif
    else { fprintf(stderr, "unknown mixer: %s\n", name); return 2; }
    const uint64_t cmask = C ? ~0ULL : 0ULL;

#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    enum { W = 65536 };                              // 512 KB buffer
    static uint64_t buf[W];
    uint64_t x = 0;
    for (;;) {
        for (int i = 0; i < W; i++, x++) {
            uint64_t u = T ? bitrev64(x) : x;
            buf[i] = mix(ror64(u ^ cmask, r));       // x86 writes little-endian
        }
        if (fwrite(buf, 8, W, stdout) != W) return 0; // pipe closed: done
    }
}
