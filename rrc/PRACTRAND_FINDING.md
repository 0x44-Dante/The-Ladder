# PractRand 0.94: missing `return` in `show_checkpoint` — robustness check

As of 2026-08-18. All runs on Ryzen 7 5700X, Windows 11, TDM-GCC 10.3.0.
Verified against a byte-for-byte unmodified original source (section 1).

## 1. The missing line

- **Version:** PractRand 0.94, official release from SourceForge
  (`PractRand_0.94.zip`, SHA-256
  `3e6e52d8ddfc1060d0de7a354f6bc813f8717987786b43e441c901fa64236849`).
- **File/function:** `tools/RNG_test.cpp`, function
  `double show_checkpoint(...)`, **lines 297-364**.
- **Finding:** The function is declared as `double`. Its last statement
  is line 363, the closing brace is line 364 — on the normal path there
  is **no `return`**:

  ```cpp
  	std::printf("\n");
  	std::fflush(stdout);
  	if (end_on_failure && biggest_decimal_suspicion > 8.5) std::exit(0);
  }                                        // <- line 364, no return
  ```

  Falling off the end of a value-returning function without `return` is
  undefined behavior in C++. GCC reports it at build time:

  ```
  tools/RNG_test.cpp:364:1: warning: control reaches end of non-void function
  ```

  (at `-O0`; at `-O3` the optimizer places the same warning on line
  326). The fix is one line before the closing brace:
  `return biggest_decimal_suspicion;`
- **Side finding**, not investigated further: the same warning appears
  for `tools/RNG_from_name.h:310` (different function).

## 2. Counter-check: known-bad case passes / fails

Known-bad case: **Stafford mix13 on a pure counter stream** — fails
according to the literature (Evensen 2018) and our own measurement at
~2^19 bytes. Identical command in all runs:

```
feeder mix13 0 0 0 | RNG_test stdin64 -tf 2 -tlmin 1KB -tlmax 1GB
```

**A — original unmodified, g++ -O3** (the known-bad case *appears to
pass*; the process ends silently after the first checkpoint):

```
rng=RNG_stdin64, seed=unknown
length= 1 kilobyte (2^10 bytes), time= 0.1 seconds
  no anomalies in 6 test result(s)
```

**C — patched with the one line, g++ -O3** (the same stream fails
correctly):

```
length= 512 kilobytes (2^19 bytes), time= 4.4 seconds
  [Low8/32]Gap-16:A                 R= +20.6  p =  7.7e-16    FAIL !
```

## 3. Original or integration?

There is no "integration" in the API sense: what gets called is the
unmodified command line tool `RNG_test` with its documented stdin
protocol. Run A above uses the freshly unpacked original source without
any change at all.

The decisive evidence is **run B**: the same unmodified source, merely
built without optimization (`-O0`):

```
length= 512 kilobytes (2^19 bytes), time= 4.6 seconds
  [Low8/32]Gap-16:A                 R= +20.6  p =  7.7e-16    FAIL !
```

This build keeps running correctly and delivers word for word the same
verdict as the patched build. A fault in the feeder, the pipe, or the
protocol could not disappear because of the optimization level of the
*test program*.

**Conclusion for point 3:** The bug is in the original source. Whether
it has any effect is decided by the compiler: g++ with `-O3` turns it
into a silent test abort after the first checkpoint, `-O0` is
accidentally benign. The official Windows binaries (MSVS 2012) were not
checked; nothing is claimed here about MSVC builds. Precise wording for
a publication: *"source-level bug (UB) in PractRand 0.94 that shows up
in self-built GCC builds with optimization as a silent test abort —
affected is the usual approach 'download the source and build it with
g++ -O3'."*

## 4. Prior art — the bug is known and fixed upstream

Result of the research (2026-08-18), sources checked:

- **SourceForge bug #12** (Christoph Conrads, 2019-04-09, status open):
  attachment `practrand-0.94-fix-ub-missing-return-value.patch` treats
  **exactly this spot** (adds `return quiet_NaN()` after line 363).
  https://sourceforge.net/p/pracrand/bugs/12/
- **SourceForge forum, thread "Segmentation fault on Linux (Fedora 29)"**
  (09-10/2019): 0.94 aborts after the first checkpoint, with `-O0` it
  runs. The PractRand author (orz) confirms the cause himself:
  *"gcc really […] doesn't like it when you don't make a return
  statement in a non-void function."*
  https://sourceforge.net/p/pracrand/discussion/366935/thread/c1dc2d0ec7/
- **Upstream fix:** in release **pre0.95** (2019-10-12) the signature is
  `void show_checkpoint(...)`, so the problem no longer exists there
  (verified on the rurban/PractRand mirror; its 0.94 import commit
  conversely shows the missing return in the original 0.94 directly).
- **SourceForge bug #15** (09/2020, open) and MartyMacGyver/PractRand
  PR #3 (merged): the same fix, there additionally for the missing
  return in `tools/RNG_from_name.h`; our side finding from section 1 is
  known there as well.
- **Related case:** lemire/testingRNG issue #20 (2020): RNG_test 0.94
  aborts, the wrapper script still reports "Success!": same root cause,
  documented as "test broken, looks like success".
- **Not verified:** 0.96 (12/2025) was only available as a zip; since it
  builds on 0.95, the fix is very probably included — that is inference,
  not evidence.

**What is still our own in this observation:** the documented
manifestations are segfault resp. double-free (GCC 8/9). Ours, with
TDM-GCC 10.3 under `-O3`, is a **silent, clean-looking exit** after the
first checkpoint: no crash, exit code 0, "no anomalies". None of the
sources describe that shape. It is also the most dangerous one, since
nothing in the output prompts a second look.

## 5. fmix64: original or reimplementation?

What was tested is a **reimplementation** (in `feeder.cpp`). The
reference is Appleby's
original: `MurmurHash3.cpp`, repository `aappleby/smhasher` (master),
function `fmix64`, lines 81-90:

```cpp
FORCE_INLINE uint64_t fmix64 ( uint64_t k )
{
  k ^= k >> 33;
  k *= BIG_CONSTANT(0xff51afd7ed558ccd);
  k ^= k >> 33;
  k *= BIG_CONSTANT(0xc4ceb9fe1a85ec53);
  k ^= k >> 33;

  return k;
}
```

**Bit-identity proven** with `verify_fmix64.cpp` (sits next to this
document; contains the original verbatim and the reimplementation):

```
checked: 2097282 inputs, deviations: 0 -> BIT-IDENTICAL
```

Input set: 0, ~0, all 64 single-bit values, all 64 complemented
single-bit values, 2^20 consecutive counter values, 2^20 splitmix64
random values. This makes the fmix64 ladder results valid for Appleby's
original, not just for the transcription.

## Conclusion

The finding is **technically sound, but not a new discovery**: the line
is named and proven on the original, the counter-check runs in both
directions, and the cause sits in the original. But it has been
documented upstream since 04/2019 (bug #12), confirmed by the author
(09/2019) and fixed since pre0.95. As "we found a bug in PractRand"
this is not publishable.

The story is publishable in a different, honest form:

1. **As an anchor parable:** a bug known for years and long since fixed
   upstream is still sitting in the most-linked release (0.94, the only
   one with official Windows binaries) and shows up with a modern GCC as
   a *silent pass*, the most dangerous form, and described nowhere in
   this shape. Nobody found it by reading code; it surfaced because a
   known-bad case suddenly passed, which is the job the anchor does.
2. **As a practical warning:** anyone who builds PractRand 0.94 with
   `g++ -O2/-O3` themselves today (the usual route) may be testing
   nothing at all and will never learn of it. Remedy: use
   pre0.95 / the rurban fork, or patch the one line.

fmix64 is verified bit-identical with Appleby; the ladder results hold
for the original.

---

# A second finding: `-tf 2` never returns on some streams

As of 2026-08-30. Same machine, same binary, with the `return` patch of
section 1 applied.

## 6. What happens

A cost-class-5 chain, run through the ladder in the usual way:

```
feeder chain 0 0 0 2 8 94d049bb133111eb 6 ff51afd7ed558ccd
  | RNG_test stdin64 -tf 2 -tlmin 1KB -tlmax 32MB
```

writes its checkpoints up to `length= 8 kilobytes (2^13 bytes), time=
0.6 seconds` and then produces nothing further. It has been given 40 s
in a controlled test and 120 s in production, and has not come back. A
longer observation was started and then ended early on purpose, because
it was taking one and a half cores away from the campaign it was
supposed to be explaining. The ceiling that can be claimed here is
therefore 120 s and no more.

It is not idle. Sampled through CIM at five-second intervals, the
`RNG_test` process consumes **7.4 to 7.8 seconds of CPU per 5 seconds of
wall clock**, about one and a half cores, steadily, with a constant
270 MB working set. The feeder behind it uses no CPU at all: it is
blocked on a full pipe. That rules out a deadlock; the process is
computing the whole time, and does not stop.

## 7. What it depends on

| Setting | Outcome |
|---|---|
| `-tf 2 -tlmin 1KB` | never returns |
| `-tf 1 -tlmin 1KB` | finishes in 0.5 s, `FAIL` at 2^13 |
| `-tf 0 -tlmin 1KB` | finishes in 0.5 s, `FAIL` at 2^13 |
| `-tf 2 -tlmin 1MB` | never returns |

So the folded-test path at level 2 is what does it, and where the
checkpoints start makes no difference. The stream itself is a
straightforward failure: at folding level 1 the same bytes are rejected
at 8 KB in half a second.

Ruled out by measurement:

- **The feeder.** Run alone into a byte counter, this chain delivers
  946 MB/s — faster than `meer10` at 724 MB/s, which never stalls.
- **The chain interpreter.** A generic `chain=` stream costs 28.1 s at
  256 MB against 27.6 s for a compiled mixer.
- **Chance.** The same chain was run alone ten times and stalled every
  time. It is deterministic.

## 8. Why it matters more than it looks

In a running cost-class enumeration **a third of all streams did this**,
134 of 400 in one ten-minute window. At one and a half cores each,
sixteen such streams demand twenty-four cores from a machine with eight,
so this stops being a nuisance and becomes the load itself. The rig was
not idling while they hung, it was being eaten by them, and every
throughput measurement taken during such a run is measuring the wrong
thing.

The rig's own stall detector did not fire, and the reason is worth
stating: it asked whether a stream had produced a *first* checkpoint,
and these streams produce four. It now watches for the log to stop
growing instead, so a runaway is cut off in about 20 s rather than at
the full watchdog timeout. A second anchor, a feeder that writes 16 KB
and then freezes, proves before every run that it still bites.

What this does **not** do is change a verdict. A stream that never
returns is recorded `ABORTED`, never as clean and never as a failure,
even though `-tf 1` shows the chain does fail. A chain is only called
dead when a disguise it *did* complete rejects it.

## 8a. The signature, and how to tell a false kill from a real one

The runaway always stops at the same place. Across **847 cut-off streams
in one campaign, every one stood at 2^13**: not a single one at any
other depth.

It confirms that the mechanism is one specific thing and not a general
fragility, and it gives a cheap test of the detector itself: a detector
that had begun killing healthy streams would produce a *spread* of
depths, because a healthy stream is somewhere different every time it is
interrupted. So when the stall rate of a run looks alarming, the useful
question is at what depth, not how many. On the run that prompted this
check the rate had jumped from 10.8 % to 26.6 % after the detector was
sharpened, and all 847 stood at 2^13. The jump was the enumeration
walking into a stall-dense region, not the detector misfiring.

## 8b. The obvious remedy does not work

Since the same bytes are rejected at 2^13 in half a second at folding
level 1, the obvious thought is a fallback: when a stream stalls under
`-tf 2`, re-run it once at `-tf 1` and take a real verdict for the price
of a rounding error instead of leaving a hole.

Tested against chains actually taken from a running campaign's stall
list. The first one **also fails to return at `-tf 1`**, past sixty
seconds, on a 32 MB target a healthy stream reaches in a second or two.
So the behaviour is not confined to the level-2 folded path: some
streams stall at level 1 as well, and the earlier case that resolved in
half a second was not representative.

That kills the fallback as a general remedy. As an opportunistic one it
might still be worth something: try `-tf 1` briefly and take the verdict
if it comes. But that changes what a verdict means, and the decision
belongs to whoever owns the protocol, not to a convenient patch.

(The measurement was cut short on purpose: each stalling stream costs
one and a half cores, and it was running against the campaign whose
throughput was being measured at the same time. Twelve chains were
queued, one was measured. The conclusion needs only the one, since a
single counterexample is enough to refute "always".)

## 9. What is not known

- Whether it terminates given unbounded time. The longest clean
  observation is 120 s, against a target a healthy stream reaches in
  18 s. Unusable follows from that; infinite does not, and the gap
  between the two is left open here.
- What property of the byte stream triggers it. The stalling chains show
  a mild enrichment in one operation (`^const`, 0.31 per chain against
  0.11 in the others) over 52 samples, which is a hint and not a cause.
- Whether pre0.95 or the rurban fork behave the same. Not tested.

Anyone building 0.94 and passing `-tf 2` should know that some inputs
cost unbounded CPU and return no verdict, and should time-limit each
stream by its output rather than by the clock.

---

## Addendum of 1 September 2026: 0.96 checked, and why this rig still runs 0.94

The section above lists 0.96 under "not verified" and infers the fix
from 0.95. That inference is now a measurement, and one thing it forces
is a correction of emphasis.

**0.96 does not have this bug.** Downloaded from SourceForge on
1 September 2026 (`PractRand_0.96.zip`, SHA-256
`e4caf7fda98b2c597bbda3b576753cf5a0f6047aab837c82be370ab798a672e1`,
released 2025-12-26), extracted, and read: `tools/RNG_test.cpp` line 417
declares `void show_checkpoint(...)`. No return value, so no missing
return, so no undefined behaviour. For contrast, in 0.94 — re-downloaded
the same day, SHA-256 `3e6e52d8…`, unchanged from the hash recorded
above — line 297 declares `double show_checkpoint(...)`.

**And the project page hands out 0.96.** `sourceforge.net/projects/pracrand`
offers `PractRand_0.96.zip` at the top today. Anyone following the link
in this repository's README gets a build in which this bug does not
exist, and would be entitled to conclude the finding is fiction. It is
not; it is version-bound, it has been known since 2019, and upstream
fixed it in pre0.95. What is ours has always been narrow, and section 4
already said so: the *shape* of the failure under TDM-GCC 10.3 with
`-O3` — a silent exit with code 0 rather than the segfault the
bugreports describe.

**Why every measurement here still runs 0.94.** Because all of them ran
on 0.94. Every verdict in `../results/` — 3,870 stream logs, the
256 TB diploma, the 91,000-chain enumeration — was produced by that
binary with that patch. Swapping the judge in the middle of a campaign
does not make the old numbers wrong; it makes them *incomparable* to
the new ones, which is worse, because nothing in the output shows it.
This rig's own rule covers exactly this case: a running instrument does
not get modified.

**What this costs, stated as a debt rather than a footnote.** New
measurements should move to 0.96, and the move is not free: it needs
the anchors re-run on the new judge first, because "the anchors hold"
is a statement about a specific judge, and mix13's and NASAM's ranges
were checked against 0.94's verdicts. Until that happens, this
repository measures on a judge that is two releases old and says so at
the place the version appears. Nobody should read the choice as a
recommendation to build 0.94 for new work.
