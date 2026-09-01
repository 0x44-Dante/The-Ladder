# RRC Ladder — PractRand test rig for 64-bit mixers

Measures how long a mixer survives on structured counter streams
(Evensen's RRC scheme: `ror64(T(x)^C, r)` with T ∈ {identity, bit
reversal}, C ∈ {0, ~0}, rotation r). Fail size is the metric that does
not saturate at the top, where avalanche and stream tests can no longer
separate good mixers (demonstrated 2026-08-17).

## Components

- `feeder.cpp` — feeds `mixer(rrc(counter))` to stdout as raw 64-bit LE
  words. Named mixers: mix13, fmix64, mulfold2, moremur, nasam, mfx9,
  mfa9, mf2b, meer10, wyhash8, wyrand, plus `user` (your own, via
  `mixer_user.h`, which you write yourself; `mixer_user.example.h` is the template and the only one in the clone). Anything else runs without rebuilding through
  `chain=`: `chain=8:5846dfed2f0e1d49,10:706,8:781f94b96e8edb3b` is
  meer10. Adding a *named* mixer means function + dispatch + rebuild.
- `candidates_k10_15.json` — a list of seven chains in the shape
  `{name, chain}`, the input format `ladder.py depth <file.json>`
  expects. It is an example as much as a record: meer10 is the first
  entry.
- `ladder.py` — drives feeder|RNG_test pairs in parallel (native pipes),
  collects verdicts. `python ladder.py` = acid test (8 streams),
  `python ladder.py smoke <mixer> [tlmax]` = 32-stream smoke.
- `practrand094/` (not in Git) — PractRand 0.94, built from source.
- `results/` (not in Git) — what this rig writes while it runs. The
  published evidence is one level up, in `../results/`; paths in this
  file point there.

## Building PractRand 0.94 (TDM-GCC, learned the hard way 2026-08-17)

**Why 0.94 and not the current 0.96.** Because every verdict in
`../results/` was produced by 0.94, and a judge swapped mid-campaign
makes old and new numbers incomparable without showing it in the
output. If you are starting fresh rather than reproducing what is here,
take 0.96 (December 2025): it declares `show_checkpoint` as `void` and
needs no patch. If you want to reproduce a number from this repository,
build 0.94 as below. Reasoning and both hashes:
[`PRACTRAND_FINDING.md`](PRACTRAND_FINDING.md).

Starting in this directory (`rrc/`). **Patch before you compile.** A
build from the unpatched source looks like it worked and is worthless.

```
curl.exe -L -o PractRand_0.94.zip "https://downloads.sourceforge.net/project/pracrand/PractRand_0.94.zip"
python -m zipfile -e PractRand_0.94.zip practrand094/
cd practrand094/PractRand_094
```

Apply the patch below to `tools/RNG_test.cpp`, then:

```
g++ -c src/*.cpp src/RNGs/*.cpp src/RNGs/other/*.cpp -O3 -Iinclude -std=gnu++14
ar rcs libPractRand.a *.o
g++ -o RNG_test tools/RNG_test.cpp libPractRand.a -O3 -Iinclude -std=gnu++14
cd ../..
```

**`-std=gnu++14` is mandatory:** PractRand enables Windows code via
`#ifdef WIN32` (no underscore). With strict `-std=c++14` it appears to
compile cleanly, but stdin stays in text mode and CRLF silently destroys
the data stream.

**Mandatory patch** in `tools/RNG_test.cpp`, function `show_checkpoint`
(ends ~line 364): before the closing brace, add the line below. If you
compiled first and patched after, compile again.

```cpp
return biggest_decimal_suspicion;
```

Without the patch a double function is missing its `return` (UB); with
-O3 the process dies after the first checkpoint shown and EVERYTHING
looks "clean to 2^10". Noticed because mix13 appeared to pass, which
contradicts the literature. The bug itself is known since 2019 and gone
upstream since pre0.95 — this patch reproduces that fix in 0.94, it does
not discover it.

Pipes for hand runs via cmd.exe or Python subprocess, never
PowerShell 5.1 (not byte-transparent).

## The cost weights, and what a clock says

Moved here from the front page so the table, the clock that disagrees
with it twice, and the one internal inconsistency it carries all live
next to the code that uses them (`COST_OPS` in `ladder.py`).

The cost column is a latency convention, stated in full so it can be
argued with. These are the weights the enumerations actually use, copied
out of `COST_OPS` in `rrc/ladder.py`:

| operation | weight | | operation | weight |
|---|---:|---|---|---:|
| `*c` multiply | 3 | | `^c` / `+c` constant | 1 |
| `mf c` 128-bit multiply-fold | 4 | | `rot k` rotate | 1 |
| `^>>k` / `^<<k` / `+<<k` shift-xor | 2 | | `bswap`, `not` | 1 |
| `xsh2` double shift-xor | 2 | | `xrot2` double rotate-xor | 3 |

**Measured, on 31 August 2026, and it does not agree with the table.**
Until then the quality axis had 256 terabytes behind it and the cost axis
had nothing at all. `rrc/bench_cost.cpp` times a dependent chain,
`x = mix(x)`, which is the shape a finalizer sits in when a hash table
needs the result before it can probe. Ryzen 7 5700X, g++ 10.3.0 `-O3
-march=native`, 100 million iterations, three runs, spread under 0.17 ns:

| mixer | weighted cost | ns per call | ns per cost point |
|---|---:|---:|---:|
| wyrand step | 5 | 1.59 | 0.32 |
| mulfold ×2 | 8 | 2.58 | 0.32 |
| mfa9 | 9 | 2.82 | 0.31 |
| lu9 | 9 | 2.85 | 0.32 |
| mix13 | 12 | 3.01 | 0.25 |
| fmix64 | 12 | 3.01 | 0.25 |
| moremur | 12 | 3.07 | 0.26 |
| **meer10** | **10** | **3.28** | **0.33** |
| NASAM | ~15 | 3.84 | 0.26 |

Two things fall out, and the second one costs us. The table overprices
the classical shift-multiply mixers: at cost 12 they run at 0.25 ns per
point against 0.32 for the fold-based ones, so a cost point spent on
multiply-fold buys *more* nanoseconds than one spent on shift-multiply,
which is the wrong way round for a column meant to track latency. And
**meer10, at cost 10, is slower than mix13, fmix64 and moremur at cost
12** — by about 0.25 ns, 8 %, stable across runs. The cost figure says
meer10 is cheaper. The clock on this machine says it is not.

What survives: meer10 is faster than NASAM, 3.28 against 3.84, and NASAM
is the mixer with a comparable published reach. So "the same distance
for ten points instead of roughly fifteen" holds as latency too. What
does not survive is any reading of the cost column as a latency ranking
across construction families. Full numbers: `../results/cost_bench.json`.

**Back to the weight table: one of its last two entries is wrong.**
`xsh2` is `v ^= (v>>a) ^ (v>>b)` and `xrot2` is `v ^= rot(v,a) ^
rot(v,b)`: the same shape, two shifts against two rotates. The singles
in the same table price a rotate below a shift-xor, so the doubles ought
to run the other way round, and they do not. Nobody measured either. It
matters because meer10 contains an `xsh2`: under these weights it costs
10, and if the double were priced like its rotate twin it would cost 11.
Every cost figure in this repository, the class boundaries included,
uses the table as printed — so if you disagree with the row, you can
move the numbers yourself, and the structural findings do not move with
them.

## Ladder status 2026-08-17 (32-stream smoke, 2 GB each, -tf 2)

| Mixer | Cost | Result |
|---|---|---|
| fmix64 (Murmur3) | 12 | FAIL from 2^17 |
| mix13 (Stafford) | 12 | FAIL everywhere, early (2^16–2^19) |
| Moremur | 12 | 16/32 streams FAIL (earliest 2^16) |
| mulfold ×2 | 8 | 11/32 FAIL (earliest 2^16), all at C=0 |
| mulfold ×2, other const. | 8 | 8/32 FAIL → weakness is structural |
| **mfx9** = `x^=γ` + mulfold ×2 | **9** | **32/32 clean**, 2^34: 64/64 (08-18) |
| **mfa9** = `x+=γ` + mulfold ×2 | **9** | **32/32 clean** |
| NASAM | ~15 | clean (literature: passes RRC-64-42) |

Mechanism of the mulfold weakness: inputs with low multiplicative weight
(small, or many trailing zeros) produce a thin or structured 128-bit
product. The fold has nothing to fold. The complement (C=1) makes
inputs generic, which is why that half is flawless; the constant up
front (mfx9/mfa9, cost +1) does the same for every stream. Pattern of
the wyhash family. Name the attribution on publication.

Context: smoke (2^31) is the ladder's entrance test. A full RRC-64-40
diploma = 256 streams of 1 TB each, ~1 week of continuous running, only
for final candidates.

**Correction of 2026-08-21 to the table above.** mfx9 does not survive
the full distance. In the RRC-64-40 diploma two independent streams
broke at 2^38 (p = 6.8e-19 and 3.0e-27) while 10 others held 1 TB:
`../results/diploma40_lu9_ckpt.jsonl` and the two stream logs beside it;
the papers call this mixer lu9 and `lu9/` is its datasheet. The table
stays as it was measured on 17./18.08.; the row is not the last word on
that mixer. The cheapest chain we know that does hold the full distance
is meer10, at cost 10.

The `2^34: 64/64` in that row also carried a date it had not earned: no
depth run of mfx9 existed in this repository or in the private rig. It
was made up for on 30.08. The run came back 64/64 clean in 40 minutes,
all six anchors in the result file `../results/depth_lu9_result.json`.
The number was right; it had just never been measured.

## Depth test 2^34 — 2026-08-19 (`ladder.py depth`, 64 streams × 16 GB)

What ran that night were the **23 bswap candidates**, and nothing else.
The candidate list is `../results/depth_candidates.json`, the run log
`../results/depth_234.log`, the verdicts `../results/depth_234_result.json`.
The mix13 rejection anchor in the same run died at 2^19, as it must.

- **bswap family (08-20):** the K9 exhaustion (`ladder.py exhaust`) found 23
  full passers of the form `mf(c1) bswap mf(c2)`, the first family on
  smoke-level par with the wyhash pattern (the cap tripped at 90 smokes,
  enumeration of the remaining rotation families paused). Depth test:
  **0/23 passed.** All die at 2^31–2^34, and 100 % of the 260 fails sit
  on C=0 streams (217× T0C0, 43× T1C0, none on C=1), the signature of
  the mulfold weakness. Finding: **bswap hides the weakness, ^const
  removes it.** The +1 step must make the input generic, not reorder the
  intermediate product. The family is a real one, but it does not
  survive depth.

**Two bullets were withdrawn from this section on 2026-08-30.** They
claimed that the K10 chain (meer10) had passed this depth test 64/64,
and that a K12 hybrid had failed it 56/64. Neither mixer is in the
candidate list of that run, neither has a log anywhere in this
repository, and the first of the two is the sentence that later sent
meer10 into the 1 TB diploma with its depth stage skipped. That stage
was made up for on 28.08.: **64/64 clean to 2^34**, 39 minutes, both
anchors in the same run (mix13 fell at 2^19, NASAM held to 2^31):
`../results/depth_meer10_result.json`, `../results/depth_meer10.log`,
streams in `../results/depth_meer10_logs/`. On the K12 hybrid this
repository now makes no claim at all: the number had no file behind it,
so it is gone rather than repeated.

## AES-NI probe 2026-08-18 — class dead (negative result)

Question: does ONE aesenc round (cost ~5) pass the ladder as a 64-bit
finalizer? Answer: **No. Worse than everything in the table.**

- Construction (feeder v3, op 14): v into the low XMM half, one AES
  round, fold lo^hi. Keyless, because the round key cancels itself out
  under the xor fold (set1: k^k = 0; any other assignment is just a
  ^const afterwards = op 6). Proven in `verify_aesenc.cpp`, together
  with FIPS-197 KAT, determinism and avalanche including anchors.
- Gauntlet probe (64 MB): aes1 bare (K5), ^γ+aes1 (K6), ^γ+aes1+xsh
  (K8), aes2 (K10). **All 16 streams FAIL at 2^10–2^11**, the first
  checkpoint. Anchor in the same run: mfx9 4/4 clean to 2^26.
- Mechanism: 64 bits occupy only 2 of the 4 AES columns; after
  ShiftRows/MixColumns every output byte depends on exactly 2 input
  bytes. The fold after ONE round throws away AES' diffusion; chaining
  folded rounds (aes2: ≤4 input bytes per output byte) does not heal it
  either. Avalanche looked perfect at 0.4998 (aes2). Once more the
  avalanche score did not separate; the ladder did.
- Consequence: op 14 stays in the feeder (reproducible), but does NOT
  enter the search alphabet of the search rig, which is not part of this
  repository. What that rests on: four measured constructions and one
  mechanism. Nothing was enumerated. The ≤K8 space around them was
  never run, so "every ≤K8 combination dies" stays an argument and not
  a measurement. The one conceivable remainder is 2 rounds on a HELD
  128-bit state, folding only at the end (~K10); it cannot undercut K9,
  so it was not built.
- For the cost-bounds paper: these four AES constructions do not
  undercut the K9 bound, they die at 2^10–2^11. That is a probe of
  hardware crypto as a cheap finalizer. It proves nothing about the
  rest.

## 2026-08-28 to 30 — the diploma, and six anchors instead of two

- **meer10 passed RRC-64-40.** 256 streams x 1 TB, ten at a time, finished
  28.08. 13:18. All 256 `clean to 2^40`, no `FAIL`, 32 streams carrying
  a `suspicious` note (34 events). This is the cheapest chain known to
  us that holds the full distance, at cost 10:
  `chain=8:5846dfed2f0e1d49,10:706,8:781f94b96e8edb3b`. Evidence:
  `../results/diploma40_meer10_ckpt.jsonl`.
- **The depth stage it had skipped was run.** 64/64 at 2^34 on 28.08.
  The cascade is gauntlet → smoke → depth → diploma, and meer10 had gone
  around the third step while five documents said it had not.
- **Two anchors became six, in three pairs.** The old pair (mix13 must
  fall, NASAM must hold) proves the rig judges *correctly* and silently
  assumes it judged at all. The second pair asks whether a verdict was
  reached: an unknown mixer name must come back `NOT MEASURED`, a
  watchdog kill must come back `ABORTED`. The third pair holds the stall
  detector to both its duties: a frozen stream must actually be cut
  (THE SLEEPER), and a healthy one must survive (THE PATIENT). Ten
  places in the reading layer treated "no FAIL" as a pass; they now ask
  positively. `python ladder.py` runs all six and exits non-zero if any
  of them misbehaves; that has been true since 31.08., when it turned
  out the bare run had only ever checked the two mixer weights while
  three documents said six. `smoke` still anchors nothing, on purpose,
  and says so where it is documented.
- **mfx9 left the upper anchor slot on 29.08.** It is our own mixer, so
  "mfx9 holds" only ever said the rig agreed with itself. NASAM took the
  slot: Evensen publishes it as passing RRC-64-42, and it holds all four
  gauntlets to 2^28 in 18 s; same cost, checkable from outside.
- **The anchor had been overwriting the evidence.** It ran the same
  mixer on the same four gauntlet streams under the same labels, into
  the same logs, and destroyed four finished 1 TB diploma streams.
  Anchor runs now carry their own prefix; the four were re-measured, and
  256/256 come from primary data again.
- **16 streams at once, not 12.** Measured at three sizes on this
  machine (8 physical cores): throughput climbs to 16 and then stops.
  32 MB 0.71→0.78, 256 MB 0.46→0.51, 2 GB 0.14→0.21 streams/s. The
  suspicion had been oversubscription; the measurement says the
  opposite. Table in `ladder.py` next to `PAR`.
- **The K9 enumeration was never finished**, and the papers said it was.
  1,309 of 30,980 chains decided, all inside one of three shape
  families, stopped by the smoke cap at 90, which the section above
  already recorded correctly. The 23 passers and their deaths at depth
  are unaffected; the claim of completeness was not.
