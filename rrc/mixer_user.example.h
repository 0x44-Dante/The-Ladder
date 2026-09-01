// -------------------------------------------------------------------
//  Copy this file to  mixer_user.h  and put your own mixer in it.
//
//  It must define exactly this function -- nothing else is required:
//
//      static inline uint64_t user_mix(uint64_t x)
//
//  Free to use from feeder.cpp: ror64, rotl64, bitrev64, mulfold.
//
//  Then:  python ladder.py trial 2GB
//
//  The example below is Stafford's mix13, a known-weak reference.
//  Run it as-is and watch it die around 2^19 -- that is what a
//  failure looks like here, so you know the rig is working before
//  you trust it with your own.
// -------------------------------------------------------------------
static inline uint64_t user_mix(uint64_t x) {
    return mix13(x);
}
