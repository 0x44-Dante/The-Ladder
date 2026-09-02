# Porting the rig to Linux — what to change, and what it measured

**Status: done, and measured.** On 2 September 2026 the rig ran on
Ubuntu 24.04 (WSL2, gcc 13.3, PractRand 0.94 with the documented
patch). All six anchors pass, three runs in a row, and `mix13` fails
at exactly the `2^19` published in `../results/`.

This file was written the day before as a map, not a port. Where the
map was wrong, the correction stands below with the old claim next to
it — the point of this repository is that a measurement replaces a
guess, including a guess of mine.

The rig is roughly 3,000 lines of Python plus one C++ file; what
follows is all of it that touches the operating system.

---

## 0. What actually blocks you — and it is not the rig

The first version of this file listed PractRand under "what needs
nothing", with the sentence *"the build recipe in README.md is plain
g++ and needs no Windows."* That was wrong, and it was the one thing
that stops a port before it starts.

PractRand 0.94 has **six includes whose case does not match the files
on disk**. Windows does not care; Linux does:

| included as | the file is actually called |
|---|---|
| `PractRand/tests/Birthday.h` | `PractRand/Tests/birthday.h` |
| `PractRand/tests/DistFreq4.h` | `PractRand/Tests/DistFreq4.h` |
| `PractRand/tests/FPMulti.h` | `PractRand/Tests/FPMulti.h` |
| `PractRand/tests/Gap16.h` | `PractRand/Tests/Gap16.h` |
| `PractRand/Tests/Coup16.h` | `PractRand/Tests/coup16.h` |
| `PractRand/Tests/NearSeq.h` | `PractRand/Tests/nearseq.h` |

Note the directory itself: it is `Tests`, and four includes spell it
`tests`.

Fix it with symlinks, not by editing the source. The numbers in
`../results/` were produced by this judge; a judge with edited
includes is a different judge until someone proves otherwise, and
symlinks provably change nothing:

```sh
cd include/PractRand
ln -sf Tests tests
cd Tests
ln -sf birthday.h Birthday.h
ln -sf coup16.h  Coup16.h
ln -sf nearseq.h NearSeq.h
```

Then the recipe from `README.md` builds unchanged — 15 s on the
machine this was measured on:

```sh
g++ -c src/*.cpp src/RNGs/*.cpp src/RNGs/other/*.cpp -O3 -Iinclude -std=gnu++14
ar rcs libPractRand.a *.o
g++ -o RNG_test tools/RNG_test.cpp libPractRand.a -O3 -Iinclude -std=gnu++14
```

`-std=gnu++14` is needed on Windows for a Windows reason (`#ifdef
WIN32`); on Linux it does no harm, and keeping it identical keeps the
judge identical.

**One more thing the build says out loud.** The compiler reports
`tools/RNG_from_name.h:310: control reaches end of non-void function`
— the same class of defect as the mandatory patch in
`show_checkpoint`, at a second site. Not chased here, and not known to
affect a verdict. Written down because an unexplored warning in a
judge is a hole, not a detail.

---

## 1. `feeder.cpp` — nothing to do

The first version of this file asked for three lines to be wrapped in
`#ifdef _WIN32`. **They already are**, at lines 19 and 295 of the
published file. The map described work that had been done before it
was written.

`<immintrin.h>` stays: AES-NI and SSE4.1 are the instruction set, not
the operating system. Any x86-64 chip since about 2010 has them and
`-march=native` picks them up.

```sh
g++ -O3 -march=native -std=gnu++14 feeder.cpp -o feeder
```

---

## 2. `ladder.py` — the feeder's name

```python
FEEDER = HERE / ("feeder.exe" if os.name == "nt" else "feeder")
```

`_find_rng_test()` already handled `RNG_test` versus `RNG_test.exe`;
only the feeder needed it.

---

## 3. The two stall anchors — `.bat` becomes `.sh`

`stall_feeder.sh` and `stall_feeder_late.sh` are in this directory.
`chmod +x` both after cloning — git records the bit, but a checkout on
a Windows filesystem does not carry it.

The `exec` in both is not decoration. Without it the shell stays as a
parent process, which is exactly what the next section is about.

`ladder.py` now picks the name by platform (`STALL_LATE`) and its
tree-kill test knows about `.sh`.

---

## 4. Killing a stalled stream — the part to get right

On Windows a `.bat` runs under `cmd.exe`, so the process the rig holds
is the shell and the real feeder is its child; `taskkill /F /T /PID`
takes the tree. Linux has the same problem and a different answer:

```python
proc = subprocess.Popen(..., start_new_session=(os.name != "nt"))
...
os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
```

`start_new_session=True` puts the feeder in its own process group so
the whole group dies together. Without it, `proc.kill()` reaps the
shell and leaves a `python3` sleeping for ten minutes — and the stall
anchor will then *look* like it passed while the machine slowly fills
with orphans.

One rule from this rig applies with no exception: **kill by PID, never
by name.** An earlier version matched process names and killed
unrelated work on the same machine.

---

## 5. What needs nothing

- `ctypes.windll.kernel32` at line 820 (console colours) already sits
  behind `if os.name == "nt"`.
- `stay_awake()` at line 1659 is already wrapped in `try/except` and
  fails silently off Windows. If a Linux box suspends during a
  week-long run, `systemd-inhibit` is the equivalent, but a machine
  that runs measurements usually is not configured to sleep.
- The `.bat` files that are *runners* rather than anchors
  (`class_run.bat`, `cost_k5.bat`, `diploma_run.bat`,
  `exhaust_run.bat`) only chain commands. Nothing depends on them.

PractRand used to be on this list. See section 0.

---

## 6. What was measured

Ubuntu 24.04 under WSL2, gcc 13.3.0, PractRand 0.94 with the
documented patch and the symlinks from section 0. Three consecutive
runs of `python3 ladder.py`:

```
THE GUILTY     mix13     must fall      FAIL at 2^19                       OK
THE INNOCENT   nasam     must hold      clean to 2^24                      OK
THE MISTRIAL   no mixer  must not clear NOT MEASURED (no PractRand output) OK
THE ADJOURNED  killed    must not clear ABORTED (timeout)                  OK
THE SLEEPER    frozen    must be cut    ABORTED (stalled) (10.0 s)         OK
THE PATIENT    healthy   must survive   clean to 2^14 (gap 0.30 s)         OK

The court is fit to sit.
```

Identical all three times. The court takes **64 s** here against the
*about 42 seconds* this file claimed for the machine it was built on —
slower, not faster, and under a virtual machine.

The acid test that follows agrees with the published numbers where
they are comparable: `mix13` fails at `2^19`, the same figure as in
`../results/`; `fmix64` falls at `2^17`; `nasam` stays clean through
2 GB.

**The two that a bad port breaks both hold.** THE SLEEPER fires after
10 s on a frozen feeder, and THE PATIENT survives with a 0.30 s gap
against a 4.0 s limit — so the kill reaches the child and is not too
eager. Those two are the reason this section exists.

---

## 7. What you have to measure before calling *your* port done

The section above says it worked on one machine, once, in three runs.
That is not the same as saying it works on yours.

Run the court:

```
python3 ladder.py
```

It must show **all six anchors passing**, and two of them are exactly
the ones a bad port breaks:

| Anchor | What a broken port looks like |
|---|---|
| THE GUILTY (mix13 must fail) | passes → your feeder is writing text, not bytes |
| THE INNOCENT (NASAM must hold) | fails → same, or a build problem |
| THE MISTRIAL (no output → NOT MEASURED) | reported clean → the verdict parser is wrong |
| THE ADJOURNED (killed → ABORTED) | reported clean → same |
| **THE SLEEPER** (frozen feeder must be cut) | never fires → your kill does not reach the child |
| **THE PATIENT** (healthy stream survives) | gets cut → your kill is too aggressive |

Anything less than six of six means the instrument is not ready to
measure, and a number it produces in that state is worth nothing.

Then, before comparing any figure to one in `../results/`: the numbers
in this repository were produced by PractRand 0.94 with the documented
patch. A different judge — including 0.96, which needs no patch —
measures a different thing, and the two are not comparable. See the
note on that in `README.md`.

---

If you do this and it works, I would like to hear about it, including
what this file got wrong. If it does not work, that is more useful
still.
