# What is in this folder, and what it is worth

Raw evidence. Every number a *finding* rests on comes from a file here.
Not every number in the prose does: the AES probe, the avalanche scores,
the constant sweeps, the throughput table in `../rrc/README.md` and the
two `wyhash` rows of the front-page comparison come from runs whose logs
were never published. The smoke and depth runs used to be on that list
and are not any more; they are in the table below, measured again where
the original logs were gone. Where that is the case it is said at the
place the number appears. The cost-5 campaign left that list on
1 September: its 92,091 raw logs are attached to
[release v1.0](https://github.com/0x44-Dante/The-Ladder/releases/tag/v1.0)
as `k5_campaign.tar.gz`, 10.7 MB packed. They live outside the git tree
because 92,091 files would make every clone pay for them, not because
they are secret. Read this page before reading the data. Two
things about it would otherwise be confusing, and one of them is a
limitation you are entitled to know about up front.

## The provenance gap

The repository README describes a `provenance` block: command, commit,
whether the tree was dirty, the md5 of both binaries, and what the
anchors said. That block is real, and every result written by a
`ladder.py` measuring command from 30 August 2026 onwards carries it.

**Eight files here have one**, counted from the folder: two in this
directory (`class_k5_complete_result.json`, `depth_lu9_result.json`)
and the six `smoke_*_result.json` under `smoke_evidence/`. Each carries
nine anchor verdicts; one was measured on a clean tree, the other seven
report `dirty: true`.

**Nine files have none**, and they fall into three groups. Six were
measured between 19 and 28 August 2026 on the German-language rig that
preceded `ladder.py` — before provenance existed, and before the anchor
set grew from two to six. `class_k5_remeasured.json` is dated 30 August
and is a report about a re-measurement, not the output of a measuring
command. And two are younger than the rule and still lack it:
`null_run_result.json` and `cost_bench.json`, both 31 August.
`cost_bench.json` is not a ladder run at all — it is a C++ latency
benchmark with no feeder, no PractRand and no anchors, and it names its
own machine and compiler instead. The null run has no such excuse: it
went through the same judge at the same depth as the entry test, it
should carry a block, and it does not. That is a gap, not a category.

They are not retro-stamped, and they will not be. The commit a run
started from and the md5 of the binary that fed it are not recoverable
after the fact; writing plausible values into old files would turn a
gap in the record into a fabrication, which is far worse. The gap is
stated instead.

So you can weigh it yourself:

- Every run here passed the anchors it had. For most that was two: a
  known-weak mixer (mix13) fell, and a known-strong one held. The depth
  run of 19 August logged only the first — its log records
  `Anker ok: mix13 -> FAIL bei 2^19` and no upper weight at all.
- What is missing is the four younger anchors, plus the written record
  tying each result to a commit. Two of those anchors catch a run that
  produces *no* verdict instead of a wrong one; the other two check
  that the stall detector both bites and spares.
- The diploma runs are the weakest case: their upper anchor was the
  candidate itself holding its own gauntlets. That is a useful
  pre-flight check, though it calibrates nothing, and it means the
  longest and most expensive runs here had only one. This was found
  on 29 August and fixed in `ladder.py`; the runs themselves predate
  the fix. `anchor/` section 8.1 has the reasoning.

Re-measuring under the corrected rig is the only thing that fully closes
this, and it is expensive: the last segment of the meer10 diploma alone
took 39.5 hours, and it was not the only segment. Where it matters most
it will be re-run, and this page will say so when it happens.

## Two mixers, two names

The papers call the cost-9 chain **lu9**. The rig calls it **mfx9**, and
so does every label inside every data file, because that is the name it
was measured under. They are the same chain: `x ^= 0x9e3779b97f4a7c15`
followed by two 128-bit multiply-folds.

`diploma40_lu9_ckpt.jsonl` is named for the papers and labelled for the
rig. That mismatch is deliberate: the file name should lead you from
`lu9/` to the evidence, and the labels should stay exactly as measured.

## Why the keys are German

`kette`, `urteil`, `stufe`, `first_fail`, `sauber bis 2^40`. The rig
that produced these files was written in German, and its output is left
as it came out. Translating keys inside a data file is a small edit
with a large failure mode: the file stops being the file that was
written. `ladder.py` writes English keys, so newer results differ
from older ones in vocabulary. A glossary:

| German | English |
|---|---|
| `kette` | chain |
| `urteil` | verdict |
| `stufe` | stage |
| `sauber bis 2^k` | clean to 2^k |
| `FAIL bei 2^k` | FAIL at 2^k |
| `skelett` | skeleton |
| `stunden` | hours |
| `stand` | as of (timestamp) |

## The files

| File | What it holds | Measured |
|---|---|---|
| `diploma40_meer10_ckpt.jsonl` | the diploma that passed: 256 streams × 1 TB, all `sauber bis 2^40`, 32 of them carrying a `suspicious` note (34 events). The `sek` field is seconds since its segment started, not the stream's own runtime, so it does not sum to anything | 22.-28.08. |
| `diploma40_meer10_logs/` | all 256 raw PractRand stream logs of that run, 1.1 MB together. Every one reaches 2^40 as its deepest checkpoint, none contains `FAIL`, 34 `suspicious` lines across 32 of them. Published 31.08. after an audit pointed out that the failing diploma had its raw logs here and the passing one did not | 26.-28.08. |
| `diploma40_meer10.log`, `diploma40_meer10_restart.log` | the run logs. The second is the restart of 22.08.: 20 streams already booked, 236 open. Both open with the anchor line of the rig as it was then, and it is worth reading: `Anker ok: mix13 faellt, meer10 haelt die Henker` — the lower weight is external, the upper weight is the candidate holding its own gauntlets, which calibrates nothing | 26.-28.08. |
| `diploma40_meer10_result.json` | its summary: 256 booked, verdict BESTANDEN. Its `stunden: 39.5` is the last run segment, not the campaign: the clock starts with the process, the stream count comes from the checkpoint file, and a resumed run pairs the two | 28.08. |
| `diploma40_lu9_ckpt.jsonl` | the diploma that failed: 10 streams held 1 TB, two independent ones broke at 2^38. Labelled `mfx9_*`; see above | 21.08. |
| `diploma40_mfx9.log` | the run log behind it | 21.08. |
| `mfx9_T0C0r40.txt`, `mfx9_T1C0r02.txt` | the two streams that broke, as PractRand wrote them. This is where the numbers quoted everywhere else come from: `[Low1/64]FPF-14+6/16:(0,14-0) R= +20.8 p = 6.8e-19 FAIL` and `[Low8/64]FPF-14+6/16:(1,14-0) R= +29.9 p = 3.0e-27 FAIL`. 29 checkpoints each, out to 2^38 | 20.08. |
| `exhaust_k9_evals.jsonl` | the cost-9 enumeration, as an append log: 5,083 lines for **4,840 distinct chains** (63 appear twice and 90 three times, one line per stage reached; the 243 surplus lines are those repeats). All in shape family A; **1,309 of them decided**, 3,774 left open (`stufe` ending in `_offen` means not yet run, never "passed"). 23 entry-test passers. The full space is 30,980 chains in three families; B and C were never started | 19.08. |
| `exhaust_k9.log` | its run log. It ends with `erledigt 1309/30980` and `SMOKE-KAPPE gerissen (90 > 80) -- anhalten und Lage ansehen`. The run stopped on purpose when too many candidates reached the expensive 2 GB stage, and was never resumed. Its closing line names a summary file that was never published and does not exist here; the log stays as the run wrote it | 19.08. |
| `cost_bench.json` | the first measurement of the cost axis: dependent-chain latency of nine mixers, 100 M iterations, three runs, on the machine named inside. It disagrees with the weight table in two places, and both are written into README.md rather than filed away here | 31.08. |
| `null_run_result.json`, `null_run_logs/` | what PractRand says when nothing is wrong: three sources whose randomness is not in dispute (chacha8, sfc64, xsm64), ten 2 GB streams each, same flags as the entry test. **3 suspicious lines in 30 streams, 0 FAIL** — 28 of the 30 ran completely clean. That is the baseline the `suspicious` counts elsewhere in this folder should be read against; at diploma depth the baseline is not measured | 31.08. |
| `smoke_evidence/` | six mixers put through the 32-stream entry test again on 30.08., because the papers quoted their numbers and no file held them: mfx9, meer10 and mfa9 hold 32/32; mulfold2 falls on 11 of 32, mf2b on 8, moremur on 16. Every figure matches what the papers say, thirteen days later on the current rig. Six result files with the six anchor verdicts inside them, and 192 stream logs | 30.08. |
| `class_k5_complete_evals.jsonl` | **cost class 5, exhausted.** All 91,000 chains of all 58 skeletons, no cap and no sampling: 89,556 dead at the pregate, 1,444 at the gauntlet, **0 passers, 0 undecided**. 2.45 hours. 13 MB, one JSON object per chain. Complete over the enumerated space, which is bounded by choice: 14 constants from a pool, 23 shift amounts from a grid, 12 operation types; not all 2^64 constants and all 63 shifts | 30.08. |
| `../assets/k5_map.png` | the whole class as one picture: one row per skeleton, one band per chain, coloured by the volume at which it fell. Drawn by `../assets/k5_map.py` from the eval file beside this line, so it can be redrawn and checked. What the colours rest on: for 89,556 of the 91,000 chains — 98.4 % — the depth comes from one undisguised stream (`T0C0r00` at 32 MB, the pre-gate); only the 1,444 survivors saw four streams, none the full 32 | 30.08. |
| `k5_remeasured_logs/` | the 3,251 stream logs from that re-measurement, 4.8 MB, exactly as PractRand wrote them on 30 August. The folder that holds them occupies about 13 MB on disk, because a 1.5 KB log still uses a whole cluster. Separate from the campaign folder on purpose: they are a later measurement of the same chains and stand outside the original run. The name inside `class_k5_remeasured.json` is the older one, `k5_nachmessung` — that file is dated and stays as written | 30.08. |
| two notes on `class_k5_complete_*` | **(a)** 400 of the 91,000 eval lines carry `"complete": false`, all in skeleton `(1,10)`. That flag is stale, from a segment that ran under a cap of 400: the skeleton's space is 3,542 assignments and the file holds all 3,542 of them, so the coverage claim holds and the flag does not. **(b)** the summary's `hours: 2.45` is the last run segment, not the campaign, for the same reason as the diploma's 39.5. Both files are left as the run wrote them | noted 31.08. |
| `class_k5_remeasured.json` | the audit behind that file. 3,017 of the 91,000 chains (3.3 %, all from the run that predates the 30.08. campaign) carried a verdict whose stream log was gone. All 3,017 were measured again on 30.08.: **3,017 identical verdicts, zero deviations**, 8.2 minutes. The evals file is unchanged because it was right; what was missing was the evidence, and it is published here as `k5_remeasured_logs/` | 30.08. |
| `class_k5_complete_result.json` | its summary. It carries a full `provenance` block — clean tree, and all six anchor verdicts including the two that guard the stall detector; the commit hash in it points into the private archive, see the note on redactions below this table | 30.08. |
| `class_k5_evals.jsonl` | cost class 5 as it stood on 21.08.: the capped run, 2,793 chains, all dead. Superseded by the complete run above and kept because the papers written before 30.08. quote it | 21.08. |
| `class_k5_result.json` | the header of that run: 58 skeletons, the 23-value shift grid, `beleg_cap` 400, which is what records it as a capped pass rather than an exhaustion. **Its count fields do not describe the evals file:** `ketten_geplant` 20, `bewertet` 20, `stunden` 0.01 come from an aborted pre-run that wrote the summary and stopped, while the evals file next to it holds 2,793 chains. Left as written, with this note standing in for the correction | 21.08. |
| `class_k10_l3_evals.jsonl` | cost class 10, a 20-chain level-3 slice. All 20 died — 17 at the gauntlet, 3 at the smoke test. No passer here; meer10 came from elsewhere and this file does not contain it | 24.08. |
| `depth_234_result.json`, `depth_234.log` | the 2^34 depth stage of the bswap family: 23 candidates, 64 streams × 16 GB each, **0 passed**. The mix13 anchor in the same run died at 2^19. These 23 are the entire content of that run; a claim that meer10 or a K12 hybrid had been depth-tested here was withdrawn on 30.08. | 19.–20.08. |
| `depth_candidates.json` | the candidate list that stage was given: 23 entries, all of shape `mf(c1) bswap mf(c2)` | 19.08. |
| `depth_meer10_result.json`, `depth_meer10.log` | meer10's own depth stage, run on 28.08. after the audit found it had been skipped: **64/64 clean to 2^34**, 0 FAIL, 0 aborts, 39 minutes. Both anchors ran in the same job — mix13 fell at 2^19, NASAM held to 2^31 | 28.08. |
| `depth_lu9_result.json`, `depth_lu9.log` | lu9's own depth stage, run on 30.08. for the same reason meer10's was: four documents carried it as measured and no file recorded it. **64/64 clean to 2^34**, 0 FAIL, 0 aborts, 40 minutes. The claim turned out to be true; it just had not been measured. All six anchor verdicts sit inside the file itself | 30.08. |
| `depth_lu9_logs/` | its 64 stream logs plus the nine anchor streams of the same run — mix13, four NASAM gauntlets, the unknown-mixer stream, the killed one, the frozen one and the healthy one | 30.08. |
| `depth_meer10_logs/` | the 64 stream logs of that run plus its two anchor streams, exactly as PractRand wrote them. Two streams (`T0C0r40`, `T0C0r52`) carry one `mildly suspicious` note each — recorded, not acted on | 28.08. |
| `depth_anchor_result.json` | may the rig judge at all at 2^38? The anchor run behind the lu9 finding | 21.08. |

A note on those two stream logs, because the same names appear twice
in the private rig. A shallower run of the same chain on the same
streams exists, from 21.08., which stops at 2^30 and reports no
anomalies at all. It does not contradict the crack at 2^38; it never
got there. A clean verdict covers only the depth the run reached,
which is why every verdict here carries its depth and why
`_went_the_distance` exists in the tool.

**Two redactions.** `depth_234.log` and `depth_lu9.log` each ended with
a line naming the output path of the run: an absolute path carrying a
user name, and in the first case the name of the private search rig.
Those two lines are replaced by a marker saying so. They carried no
measurement; every verdict in both files is untouched. It is noted here
rather than done quietly, because editing a record without saying so is
how a record stops being one.

Both redactions apply to the file as it is published. The published
repository is a single commit of the final state, on purpose: earlier
working versions of some files carried an old account name and absolute
paths from the machine they ran on, and the development history — a
working diary of one author and one assistant, not evidence — lives on
as a private archive rather than as public history. That is also why the
`commit` hashes inside the `provenance` blocks of the result files do
not resolve here: they point into that archive. They date a run and
identify the code state it ran under; they were never a replay button,
and the working tree flag next to them matters more than the hash.

## What "exhausted" means, exactly

Moved here from the front page; it belongs next to the eval files it
qualifies. One phrase in the cost-5 headline carries more weight than it
looks like it does, and what bounds it is a set of choices, not facts.

**That phrase is "every chain."** The skeletons are complete: all
58 op-sequences of cost 5, none omitted. The assignments are complete
too — the largest skeleton has 7,406 of them and the cap was 10,000, so
nothing was sampled. But the *space those assignments are drawn from* is
bounded, and the bound is a choice rather than a fact:

| axis | enumerated | possible |
|---|---:|---:|
| constants | **14** from a pool of established mixers' constants | 2^64 |
| shift amounts | **23** from a grid | 63 |
| operation types | **12** defined | open-ended |
| the weight table | **this one** | any other draws a different class |

That last row is the one people miss. "Cost class 5" is whatever the
weights say it is, and moving a single entry moves the whole set:
priced with multiply-fold at 3 instead of 4, class 5 holds 102 skeletons
and 179,732 chains instead of 58 and 91,000; with the double shift-xor
at 3 instead of 2, it holds 56 and 83,916. Counted by re-running the
enumerator with the changed weight, not estimated.

**And the mixer on the front page is not in that grid.** meer10 shifts
by 28 and 6; the grid holds neither. Its first constant,
`0x5846dfed2f0e1d49`, is not in the pool either — only its second one
is. It came out of the search rig, which draws from a wider space, not
out of the enumeration published here. The enumeration can therefore say
what it did not find; it could not have found meer10.

Three filters also drop skeletons before they are ever built: purely
linear chains (no multiply), chains ending in a pure permutation, and
chains with two identical self-inverse operations in a row.

So the claim that holds is: **over this pool and this grid, no chain
of cost 5 holds even the 256 MB gauntlet.** The sentence that does not
hold is "there is no cost-5 mixer" — a chain built on a constant outside
those fourteen was never measured. The result is suggestive against it
(87,291 of 91,000 die at 1–8 KB, which does not look like a space where
a different constant rescues anything) but suggestive is not measured,
and it is written here as a hunch rather than as a finding.

Suspicious and unusual verdicts get recorded but never acted on. Only
an explicit `FAIL` counts as a death. The sentence that used to stand
here — that a run with no `suspicious` at all would itself be suspect —
was a claim about a null distribution nobody had measured, and it is
wrong at entry-test depth: of 30 streams from sources whose randomness
is not in dispute, 28 came through with none at all, and the rate is
0.10 per 2 GB stream (`null_run_result.json`). meer10's own entry test
sits at 0.09 per stream, mulfold2's at 0.59. At diploma depth, where
there are far more checkpoints and subtests, the baseline is still
unmeasured, and the 34 events across 256 terabytes stand without one.
