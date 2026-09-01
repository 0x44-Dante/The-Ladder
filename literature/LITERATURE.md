# Literature check — as of 20 August 2026

Five questions, researched along several tracks, every load-bearing
finding verified against primary sources (verbatim code and blog
citations). Purpose: the novelty and attribution basis for the papers
and for this repository.

> **Added 30 August 2026.** This document is dated and is left as it
> was written. Two things have happened since, and the first correction
> here is to an earlier version of this note, which got them the wrong
> way round.
>
> The diploma of question 3, the wyhash shape called mfx9 here and lu9
> in the papers, was taken and **failed**: ten streams held 1 TB, two
> broke at 2^38. Vigna's 32 TB finding below belongs to the honest
> reading of that failure, much as this document expected it to belong
> to a pass.
>
> What **passed** is the candidate of question 5, the K10 skeleton, now
> named meer10: 256 streams of 1 TB, no `FAIL`, 34 `suspicious`.
> Nothing in the five sections has been rewritten to match.

## 1. bswap between multiplications in deployed hashes — KNOWN

- **CityHash64** (`src/city.cc`, `HashLen33to64`) contains verbatim
  `y = (bswap_64((v + w) * mul) + g) * mul;` (plus two further
  bswap-of-the-product lines). Deployed today via **Abseil**
  (`absl/hash/internal/city.cc`, `absl::gbswap_64`).
- **CityHash32/FarmHash32**: `g ^= bswap_32(g) * 5; h = bswap_32(h);`
  between rounds of multiplication.
- **XXH3-128** (the 9-16 byte path): `m128.low64 ^= XXH_swap64(m128.high64);`
  between two `XXH_mult64to128`, in LLVM's copy as well.
- Verified negatives: Murmur3, MetroHash64, SpookyHash, komihash and
  rapidhash do NOT use bswap for mixing (endian loads only).
- **Nuance:** everywhere only in length-specific sub-paths or 32-bit
  loops. No hash examined uses bswap in the general 64-bit finalizer.

## 2. mul-bswap-mul as a finalizer in its own right — PARTLY KNOWN

- **Remco Bloemen, "MulSwapHash" (27 February 2014):** the core is
  exactly `v *= k; v = bswap64(v); v *= k` (plain 64-bit
  multiplications). SMHasher-tested only; no PractRand, no RRC.
- **Scala standard library** (`scala.util.hashing.byteswap32/64`,
  attributed to Phil Bagwell): `hc = v * 0x9e3775cd;
  hc = reverseBytes(hc); hc * const` — **shipped as a standard-library
  mixer, without any published quality characterisation at all.**
- hash-prospector PR #13 (2021, never merged) proposed byte shuffles as
  a search primitive; HighwayHash uses byte permutation internally in
  SIMD.
- **Consequence for the FAMILY paper:** the construction is prior art
  (Bloemen, Bagwell/Scala). What is new is the mulfold variant and above
  all the **first RRC/PractRand characterisation**: entry passed, depth
  refuted (0/23), mechanism named. For the Scala/City relatives (plain
  muls rather than folds) our finding is a testable hypothesis, not a
  verdict. Open follow-up: put Scala's byteswap64 on the ladder (after
  the diploma, chain 1:...,11:0,1:...).

## 3. The wyhash pattern and RRC — PROBABLY NEW (our diploma would be the first)

- Evensen (mostlymangling) RRC-tested murmur3, variant13 (mix13),
  splitmix64, rrmxmx, rrxmrrxmsx_0, Moremur, degski64, Lea64 and
  NASAM/xNASAM — **never wyhash/mum/fold constructions, never xxh3.**
- **NASAM passes RRC-64-42-TF2-0.94** (256 streams x 4 TB = 1 PB, no
  anomalies), one step DEEPER than our RRC-64-40. Moremur: fails
  RRC-64-40, though far less badly than earlier constants.
- **Vigna, April 2023** (wyhash issue #135): PractRand on bit-reversed
  wyrand OUTPUT fails at **32 TB** ([Low8/64]Gap-16), acknowledged in
  the wyhash README. That is the next public stress on the pattern:
  generator output rather than the bare finalizer, and 32 TB is beyond
  our 1 TB stream depth. **For the mfx9 diploma this means the outcome
  is genuinely open, and if it passes, Vigna's finding belongs in the
  honest reading of that pass.**
- The wyhash repository: zero hits for RRC or Evensen, which confirms
  "never cleanly presented".

## 4. Systematic cheapest-first search against PractRand depth — PARTLY KNOWN

- **Jon Maiga, "Tuning bit mixers" (3 August 2020):** enumerates
  skeletons (m, mx, xm, ..., mxmxmx, xmxmxm), tunes constants, and
  tabulates maximum PractRand depth; verbatim: "It seems that passing,
  PractRand 40 we need either mxmxmx or xmxmxm." That is **published
  construction minimality against PractRand depth.** BUT: a bare
  counter (no RRC), a raw operation count (no weighted cost model), and
  plain muls (no folds, no hash class).
- **Maiga, "Improved mx3 and the RRC test":** adopts Evensen's RRC for
  six constructions (xmxmx dies at 2^20, mxmxmx at 2^34, xmxmxmx
  passes).
- **Consequence for the COST LIMIT paper:** Maiga is the nearest
  relative and is cited explicitly. Our delta: a weighted cost model
  including mulfold, RRC at every stage, exhaustion instead of
  heuristics, a K9 lower bound (Maiga's cheapest PractRand-40 passers
  are roughly K15-K17 in our model) plus the hardness tests.

## 5. The K10 skeleton fold-xsh2-fold — PROBABLY NEW

- A double xorshift between PLAIN muls exists (NASAM, Maiga's mx3:
  `x *= C; x ^= (x>>57) ^ (x>>33); x *= C`).
- Fold finalizers WITHOUT a xorshift exist (mum-hash: hi+lo fold,
  wyhash, a5hash; UMASH: xor fold plus a double-rotate finish).
- **The combination fold + double xorshift + fold: found nowhere.** The
  K10 passer (2^34: 64/64) remains a candidate for a real novelty
  claim, after its diploma.

## Attribution list (for the repository and the papers)

Evensen (the RRC scheme, NASAM, Moremur, rrmxmx), Doty-Humphrey
(PractRand), Stafford (mix13), Appleby (Murmur3/fmix64), Wang Yi (the
wyhash pattern), Maiga (systematic skeleton tables, mx3), Bloemen
(MulSwapHash), Bagwell/Scala (byteswap32/64), Pike/Alakuijala
(CityHash/FarmHash), Collet (xxHash/XXH3), Wellons (hash-prospector,
the avalanche-bias search).

**Addendum of 30 August 2026: one name was missing.** Martin
Leitner-Ankerl belongs in this list and was not in it. He measured
twenty mixers over RRC streams against a cost axis in 2020, with a
declared Pareto front; that is the same pair of axes the COST LIMIT
paper uses, and five of the seven papers cite him. The list above is
left as it was written on 20 August.

Two things are open, and are named here rather than smoothed over: the
primary source is cited in the papers by author and year, with no URL
recorded anywhere in this repository, and the numbers attributed to him
(twenty mixers; two AES-based mixers dying between 2^13 and 2^20) are
his, not ours — nobody here has opened his data. They carry no
conclusion in these papers, and they should not be read as measured on
this rig.

**Addendum of 31 August 2026: both open points were closed, and one of
the numbers above was wrong.** The addendum of 30 August stands as
written; this is what happened after it.

His data was opened the same day. The COST LIMIT paper now cites the
source with its URL — `github.com/martinus/better-faster-stronger-mixer`,
README written January 2020 — and counts his tables cell by cell instead
of quoting a range: **aes2** dies between 2^13 and 2^16 in all 128 of
his cells, and **aes3** carries the note *only tested up to -tlmax 20*
and does not fail there in 124 of 128. So "two AES-based mixers dying
between 2^13 and 2^20", written above, is not what his tables say. One
mixer dies early; for the other, 2^20 is where his test stopped, not
where the mixer broke. Reading a test ceiling as a death is its own kind
of error, and it is an entry in `errata/`.

What has not changed: the figures are still his, counted from his
published tables and never re-measured on this rig, and they still carry
no conclusion here.
