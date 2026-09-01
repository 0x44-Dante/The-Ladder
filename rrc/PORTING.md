# Porting the rig to Linux — what to change, and what to prove

**Status: nobody has run this on Linux.** This file is a map, not a
port. It lists every Windows-specific line I could find, what it would
have to become, and — more importantly — what you have to measure
before you may call it working. If you finish it, the last section is
the part that matters.

Written 1 September 2026, against the tree published as v1.0. The rig
is roughly 3,000 lines of Python plus one C++ file; what follows is all
of it that touches the operating system.

---

## 1. `feeder.cpp` — three lines

```cpp
#include <io.h>          // line 20
#include <fcntl.h>       // line 21
...
_setmode(_fileno(stdout), _O_BINARY);   // line 296
```

They exist because Windows would otherwise translate `\n` in the byte
stream and destroy the data. On Linux stdout is already binary and none
of this is needed. Wrap all three:

```cpp
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
...
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
```

`<immintrin.h>` (line 18) stays: AES-NI and SSE4.1 are the instruction
set, not the operating system. It needs a CPU with AES-NI, which any
x86-64 chip since about 2010 has, and `-march=native` picks it up.

The build line becomes:

```
g++ -O3 -march=native -std=gnu++14 feeder.cpp -o feeder
```

---

## 2. `ladder.py` — the feeder's name

Line 22:

```python
FEEDER = HERE / "feeder.exe"
```

Should follow the pattern the file already uses one line further down
for PractRand (line 58):

```python
FEEDER = HERE / ("feeder.exe" if os.name == "nt" else "feeder")
```

The build hint printed when the feeder is missing (lines 2767-2768)
carries the same name and would need the same treatment.

---

## 3. The two stall anchors — `.bat` becomes `.sh`

`stall_feeder.bat` and `stall_feeder_late.bat` are the anchors that
prove the stall detector bites. Their entire content is one Python
line each:

```sh
#!/bin/sh
# stall_feeder.sh — never produces output at all
exec python3 -c "import time; time.sleep(600)"
```

```sh
#!/bin/sh
# stall_feeder_late.sh — writes 16 KB, then freezes on purpose
exec python3 -c "import sys,os,time; sys.stdout.buffer.write(os.urandom(16384)); sys.stdout.buffer.flush(); time.sleep(600)"
```

`chmod +x` both. The `exec` matters: without it the shell stays as a
parent process, which is exactly the problem the next section is about.

`ladder.py` line 369 names `stall_feeder_late.bat` directly, and line
581 decides by file extension whether a feeder needs tree-killing:

```python
tree = str(feeder).lower().endswith((".bat", ".cmd"))
```

Both need to know about `.sh`.

---

## 4. Killing a stalled stream — the part to get right

Lines 549-566. On Windows a `.bat` runs under `cmd.exe`, so the process
the rig holds is the shell and the real feeder is its child; `taskkill
/F /T /PID` takes the tree. Linux has the same problem and a different
answer:

```python
# when starting a feeder that may have children:
proc = subprocess.Popen(..., start_new_session=True)

# when killing it:
os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
```

`start_new_session=True` puts the feeder in its own process group so
the whole group dies together. Without it, `proc.kill()` reaps the
shell and leaves a `python3` sleeping for ten minutes — and the stall
anchor will then *look* like it passed while the machine slowly fills
with orphans.

With `exec` in the shell scripts above there is no shell left to
orphan, which is why both belong together.

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
- PractRand itself: the build recipe in `README.md` is plain `g++` and
  needs no Windows. The mandatory patch is the same. `-std=gnu++14` is
  needed there for a Windows-specific reason (`#ifdef WIN32`), and on
  Linux it does no harm.
- The `.bat` files that are *runners* rather than anchors
  (`class_run.bat`, `cost_k5.bat`, `diploma_run.bat`,
  `exhaust_run.bat`) only chain commands. Nothing depends on them.

---

## 6. What you have to measure before calling it done

This is the section this file exists for. A port that compiles is not a
port that works, and this rig judges nothing until it has proven it can
judge.

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

On the machine this was built on, the whole court takes about 42
seconds and ends with *"The rig is fit to sit."* Anything less than six
of six means the instrument is not ready to measure, and a number it
produces in that state is worth nothing.

Then, before comparing any figure to one in `../results/`: the numbers
in this repository were produced by PractRand 0.94 with the documented
patch. A different judge — including 0.96, which needs no patch —
measures a different thing, and the two are not comparable. See the
note on that in `README.md`.

---

If you do this and it works, I would like to hear about it, including
what this file got wrong. If it does not work, that is more useful
still.
