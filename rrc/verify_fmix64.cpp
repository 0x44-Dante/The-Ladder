#include <cstdio>
#include <cstdint>
// --- Original Appleby: MurmurHash3.cpp lines 81-90, verbatim ---
#define FORCE_INLINE inline
#define BIG_CONSTANT(x) (x##LLU)
FORCE_INLINE uint64_t fmix64 ( uint64_t k )
{
  k ^= k >> 33;
  k *= BIG_CONSTANT(0xff51afd7ed558ccd);
  k ^= k >> 33;
  k *= BIG_CONSTANT(0xc4ceb9fe1a85ec53);
  k ^= k >> 33;

  return k;
}
// --- Our replica (feeder.cpp) ---
static inline uint64_t fmix64_replica(uint64_t x) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33; return x;
}
static inline uint64_t sm(uint64_t& s){
    s += 0x9E3779B97F4A7C15ULL; uint64_t z = s;
    z ^= z >> 30; z *= 0xbf58476d1ce4e5b9ULL;
    z ^= z >> 27; z *= 0x94d049bb133111ebULL;
    z ^= z >> 31; return z;
}
int main(){
    unsigned long long n = 0, diff = 0;
    auto chk = [&](uint64_t v){ n++; if (fmix64(v) != fmix64_replica(v)) diff++; };
    chk(0); chk(~0ULL);
    for (int b = 0; b < 64; b++){ chk(1ULL << b); chk(~(1ULL << b)); }
    for (uint64_t i = 0; i < (1ULL << 20); i++) chk(i);
    uint64_t s = 0x44;
    for (uint64_t i = 0; i < (1ULL << 20); i++) chk(sm(s));
    printf("checked: %llu inputs, deviations: %llu -> %s\n",
           n, diff, diff ? "NOT BIT-IDENTICAL" : "BIT-IDENTICAL");
    return diff ? 1 : 0;
}
