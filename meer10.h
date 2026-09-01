/* meer10 and lu9: the two 64-bit mixers this repository measured.
 *
 * Public domain / MIT, same as the rest of the repository. One header,
 * no dependencies, C99 or C++11.
 *
 *   meer10  cost 10  passed RRC-64-40: 256 streams x 1 TB, 256/256 clean,
 *                    no FAIL in 256 terabytes. Evidence:
 *                    results/diploma40_meer10_ckpt.jsonl
 *   lu9     cost  9  passed 32/32 smoke and 64/64 depth, then TORE at 2^38
 *                    on two of twelve diploma streams (p = 6.8e-19 and
 *                    3.0e-27). It is here because a mixer that fails is
 *                    worth publishing. DO NOT USE IT; it is the cautionary
 *                    half of the pair. Evidence:
 *                    results/diploma40_lu9_ckpt.jsonl
 *
 * What "passed" means and does not mean
 * -------------------------------------
 * The test feeds a counter (1, 2, 3, and so on) through the mixer under 256
 * disguises (rotate / bit-reverse / complement, Pelle Evensen's RRC scheme)
 * and asks PractRand how much output it takes before the stream can be told
 * apart from random. For meer10 that is more than a terabyte per stream,
 * across all 256. Textbook finalizers give themselves away after kilobytes.
 *
 * It is not a cryptographic primitive. It has no key, it is not collision
 * resistant against an adversary who knows the constants, and nothing here
 * says anything about behaviour beyond 2^40 bytes per stream, because that
 * is where the measurement stopped.
 *
 * meer10 has a fixed point: meer10(0) == 0. Both multiplications are
 * multiply-fold, and zero survives both. If your inputs include zero and
 * that matters to you, add a constant first, and then it is a different
 * mixer than the one measured here.
 *
 * The two constants came from established mixers (splitmix64 and the wyhash
 * line); they were not grown against this ladder. The chain was found by an
 * enumeration, not derived.
 *
 * Verifying that this file is the function that was measured:
 *
 *   cc -O2 -o verify_meer10 verify_meer10.c && ./verify_meer10
 *
 * and against the rig itself, which is where the numbers come from:
 *
 *   rrc/feeder.exe chain 0 0 0 3 8 5846dfed2f0e1d49 10 706 8 781f94b96e8edb3b
 *
 * writes meer10(0), meer10(1), ... as raw 64-bit little-endian words. The
 * test vectors below were taken from that binary on 30 August 2026, not
 * from this header.
 */
#ifndef MEER10_H
#define MEER10_H

#include <stdint.h>

/* 128-bit multiply, folded down to 64 bits: low half XOR high half.
   GCC and Clang have __uint128_t; MSVC has _umul128. */
#if defined(_MSC_VER) && !defined(__clang__)
#include <intrin.h>
#pragma intrinsic(_umul128)
static __forceinline uint64_t meer10_mulfold(uint64_t v, uint64_t c) {
    uint64_t hi;
    uint64_t lo = _umul128(v, c, &hi);
    return lo ^ hi;
}
#else
static inline uint64_t meer10_mulfold(uint64_t v, uint64_t c) {
    __uint128_t r = (__uint128_t)v * (__uint128_t)c;
    return (uint64_t)r ^ (uint64_t)(r >> 64);
}
#endif

/* meer10, cost 10: fold, double xor-shift, fold.
   Passed RRC-64-40 (256 streams x 1 TB) with 256/256 clean. */
static inline uint64_t meer10(uint64_t x) {
    x = meer10_mulfold(x, 0x5846dfed2f0e1d49ULL);
    x ^= (x >> 28) ^ (x >> 6);
    x = meer10_mulfold(x, 0x781f94b96e8edb3bULL);
    return x;
}

/* lu9, cost 9: xor-constant, fold, fold. The wyhash pattern.
   Holds 2 GB on all 32 disguises and 16 GB on all 64 depth streams, then
   tears at 2^38 on two streams out of twelve at diploma distance. Kept for
   reproduction of that finding. Not a recommendation. */
static inline uint64_t lu9(uint64_t x) {
    x ^= 0x9E3779B97F4A7C15ULL;
    x = meer10_mulfold(x, 0x781f94b96e8edb3bULL);
    x = meer10_mulfold(x, 0xB853D68343F7525BULL);
    return x;
}

/* Known-answer vectors, read off the rig's own feeder on 30 August 2026.
   verify_meer10.c checks these. */
#define MEER10_KAT_COUNT 6
static const uint64_t meer10_kat_in[MEER10_KAT_COUNT] = {
    0x0000000000000000ULL, 0x0000000000000001ULL, 0x0000000000000002ULL,
    0x0000000000000003ULL, 0x8000000000000000ULL, 0x4000000000000000ULL
};
static const uint64_t meer10_kat_out[MEER10_KAT_COUNT] = {
    0x0000000000000000ULL, 0x1b4f5f002ce35862ULL, 0x8efec9b9c8494d9fULL,
    0x72b4cc6132941240ULL, 0xcb3c7fed89594a89ULL, 0x39aeea5a0df413ebULL
};

#define LU9_KAT_COUNT 3
static const uint64_t lu9_kat_in[LU9_KAT_COUNT] = {
    0x0000000000000000ULL, 0x0000000000000001ULL, 0x0000000000000002ULL
};
static const uint64_t lu9_kat_out[LU9_KAT_COUNT] = {
    0x37f28927366a4e7bULL, 0x50388cb4314d97bbULL, 0xff9d7546b24812feULL
};

#endif /* MEER10_H */
