# 0x44 RRC-LADDER
#
#   Measuring instruments that do not question themselves lie.
#
# Drives feeder|RNG_test pairs in parallel with
# native pipes (no shell &, no PowerShell: both mangle the byte stream
# resp. the process group). Collects the verdict per stream: first
# FAIL size or "clean to 2^k".
#
# Usage: python ladder.py [tlmax]     (default 2GB)
import hashlib
import os
import re
import shutil
import signal
import subprocess
import threading
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
FEEDER = HERE / ("feeder.exe" if os.name == "nt" else "feeder")
# The two stall anchors run as .bat on Windows and .sh elsewhere.
# Both must start with exec, so that no shell is left standing as a
# parent process -- see _kill().
STALL_LATE = ("stall_feeder_late.bat" if os.name == "nt"
              else "stall_feeder_late.sh")
OUT = HERE / "results"


def use_campaign(name):
    """Give this run its own folder for everything it produces.

    One bucket for every stream ever measured does not survive contact
    with an enumeration: a full K5 writes over 100,000 stream logs, and
    on 29.08. simply listing the directory timed out. Worse than slow,
    it is unreadable: a filter written in a hurry that day nearly
    classified the lu9 diploma logs as leftovers, because the twelve
    streams the whole K9END paper rests on sat namelessly among 25,000
    enumeration files.

    So each campaign gets a folder: its stream logs, its anchors, its
    evals and its result, together. What belongs to one measurement
    stays together, and what a run produced can be seen at a glance
    instead of grepped out of a pile.
    """
    global OUT
    OUT = HERE / "results" / name
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT


def _find_rng_test():
    """PractRand is not bundled (own license, and it must be built with
    the documented patch (see README). Look in this order:
      1. $PRACTRAND            -- full path to the RNG_test binary
      2. $PRACTRAND_DIR        -- directory containing it
      3. rrc/practrand.txt     -- one line: the path to binary or folder
      4. ./practrand094/PractRand_094/  -- the layout the README builds
      5. RNG_test[.exe] on PATH
    Fail loudly rather than measure nothing: a missing judge must not
    look like a clean stream."""
    exe = "RNG_test.exe" if os.name == "nt" else "RNG_test"
    direct = os.environ.get("PRACTRAND")
    if direct and Path(direct).is_file():
        return Path(direct)
    env_dir = os.environ.get("PRACTRAND_DIR")
    if env_dir and (Path(env_dir) / exe).is_file():
        return Path(env_dir) / exe
    # A file beside the ladder, holding one line: the path to the binary.
    # An environment variable is forgotten by every new shell window, so it
    # has to be retyped before every session, which is not configuration,
    # it is a trap that fires on the person least able to diagnose it.
    note = HERE / "practrand.txt"
    if note.is_file():
        for line in note.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip('"')
            if not line or line.startswith("#"):
                continue
            p = Path(line)
            if p.is_file():
                return p
            if (p / exe).is_file():          # a directory works too
                return p / exe
    local = HERE / "practrand094" / "PractRand_094" / exe
    if local.is_file():
        return local
    found = shutil.which(exe) or shutil.which("RNG_test")
    return Path(found) if found else local


RNG_TEST = _find_rng_test()

# Acid test: known-weak ones MUST fall, known-strong ones MUST hold.
# The bare `ladder.py` run, and the first thing the README asks a stranger
# to do. Until 30.08.26 it printed eight verdicts and exited 0 whatever
# they said: the words MUST fall and MUST hold sat in these comments and
# nothing checked them. A demonstration that cannot fail demonstrates
# nothing, and this one is the rig's own handshake.
#
# Fifth field: what the verdict has to be. "fall" and "hold" are checked
# and decide the exit code; None is shown for scale and judged by nobody.
ACID_TEST = [
    ("mix13",    0, 0, 0,  "fall"),   # Stafford mix13, bare counter
    ("mix13",    0, 0, 33, "fall"),   # mix13, rotated
    ("mix13",    1, 1, 0,  "fall"),   # mix13, bit-reversed + complement
    ("fmix64",   0, 0, 0,  "fall"),   # Murmur3 finalizer
    ("moremur",  0, 0, 0,  None),     # Evensen improvement: holds longer
    ("mulfold2", 0, 0, 0,  None),     # bare mulfold x2: FIRST rung
    ("nasam",    0, 0, 0,  "hold"),   # passes RRC-64-42
    ("nasam",    1, 1, 33, "hold"),   # NASAM on a transformed stream
]


def run(streams, tlmax="2GB", parallel=12, timeout_s=None, feeder=None,
        quiet=False, watch=0, on_done=None, prefix=""):
    # prefix: separate namespace for the result files. The anchor measures
    # the same mixer on the same gauntlet rotations as the main run, so
    # without a prefix its short 256-MB result lands in the very file that
    # holds the long result and truncates it (mode "wb"). On 26.08. this
    # destroyed the 1-TB logs of four diploma streams, and resume then
    # skipped them because the checkpoint had already booked them. An
    # instrument that checks itself must not overwrite its own evidence.
    # on_done(label, verdict) -> False aborts everything still running.
    # This is how the diploma stops the moment a stream falls: 255 more
    # terabytes for a dead candidate would be pure waste.
    # timeout_s: watchdog per stream. In the night of 17./18.08. about
    # every tenth feeder/RNG_test pair stalled at ~8 KB (RNG_test stopped
    # reading, root cause unknown) and held the whole run hostage.
    # A hung pair gets killed and marked ABORTED, never as 'clean',
    # that would be an invented result.
    # feeder: alternative feeder path (e.g. feeder.exe for the
    # spectrum forge): default is the baseline binary.
    # quiet: suppress the plain "done:" line: the trial presenter says it
    #        better. watch: seconds between progress tables (0 = off).
    feeder = str(feeder) if feeder else str(FEEDER)
    OUT.mkdir(exist_ok=True)
    pending, rest, labels = [], list(streams), []
    last_watch = time.time()
    try:
        return _drive(pending, rest, labels, feeder, tlmax, parallel,
                      timeout_s, quiet, watch, last_watch, on_done, prefix)
    except KeyboardInterrupt:
        # Ctrl+C kills this process, not its children. Without this the
        # feeder/RNG_test pairs keep running, invisible, at full tilt,
        # for as long as the target length takes. On a machine that is
        # also carrying a week-long measurement that is not a nuisance,
        # it is stolen cores.
        print("\n  interrupted, stopping %d stream(s)" % len(pending),
              flush=True)
        for label, f, p, out, _t in pending:
            for proc in (p, f):
                try:
                    proc.kill()
                except OSError:
                    pass
            try:
                out.close()
            except OSError:
                pass
            with open(OUT / ("%s.txt" % label), "a", encoding="utf-8") as m:
                m.write("\nRRC_ABORTED interrupted by user\n")
        raise


# A healthy stream writes its first PractRand checkpoint in 0.15 s
# (measured 29.08.2026 over nasam, mix13 and moremur). STALL_S is a
# hundredfold margin on that, long enough that load can never trip it,
# short enough that the known stall costs seconds instead of minutes.
STALL_S = int(os.environ.get("RRC_STALL_S", "8"))

# The floor of the stall rule, and the only part of it that is a choice.
#
# _stalled() allows four times the age of the run and never less than
# this, so the floor governs the first two seconds and the multiplier
# takes over after that. What it therefore has to cover is the longest a
# healthy stream ever goes without writing, early on, under load.
#
# Measured 30.08.2026: eight healthy 256 MB streams polled ten times a
# second while a K5 campaign was running, 160 gaps:
#
#   age of run     worst write-to-write gap     4x age
#   0-1 s                   0.71 s               0.0 s   <- the floor's job
#   1-2 s                   1.22 s               4.0 s
#   2-5 s                   1.73 s               8.0 s
#   5-15 s                  1.64 s              20.0 s
#   over 15 s               6.25 s              60.0 s
#
# 8 s is 5.6 times the worst case in the window that matters, and
# watchdog_patient() re-measures that same gap before every run and
# refuses to start if it ever climbs past half the floor.
#
# It was 20 s until 30.08., a number inherited from the previous rule,
# which fired only before a stream's first checkpoint and wanted a
# hundredfold margin on the 0.15 s that takes. Under the new rule the
# same 20 s cost 60 % of the machine: in a ten-minute window of the K5
# campaign, 289 stalls at 20 s each against 9,600 slot-seconds of
# capacity. The projection fell from 16 hours to a third of that.
#
# Do not lower this without re-measuring the table above. The failure
# mode is silent and it points the wrong way: too low, and the detector
# starts killing healthy streams and recording them as ABORTED.


# How many feeder|PractRand pairs run at once in the measuring commands.
#
# Measured 30.08.2026 on this machine (Ryzen 7 5700X, 8 physical cores,
# 16 logical). Identical work at every level: NASAM streams, which run
# the full distance at every size, so no branch is cheaper than another,
# and the watchdog set far out of the way so nothing was killed:
#
#   tlmax     p=4    p=6    p=8   p=12   p=16   p=20   p=24   p=32
#   32MB       -      -      -    0.71   0.78     -    0.78     -
#   256MB    0.20   0.29   0.36   0.46   0.51   0.49   0.52   0.52
#   2GB        -      -      -    0.14   0.21     -      -      -
#                                              (streams per second)
#
# The same shape at all three sizes: throughput climbs to 16 and then
# stops. Past 16 only the time a single stream takes keeps growing:
# 31 s at 16, 62 s at 32 for a 256 MB stream, and that is watchdog
# margin spent for nothing. So 16: the plateau at the shortest per-stream
# time. At 2 GB the step from 12 to 16 is worth 50 %.
#
# This also refutes why the K5 run was slow. The suspicion was
# oversubscription: 12 streams is 24 processes on 8 physical cores. The
# measurement says the opposite: more parallelism was faster all
# the way up to the plateau. The rig spends its time waiting, not
# computing.
PAR = int(os.environ.get("RRC_PAR", "16"))
# Both numbers were measured on one machine: 8 physical cores, the one
# named in the README's anchor table. On other hardware they are
# starting points, not constants: RRC_PAR and RRC_STALL_S override
# them. The PATIENT anchor is what tells you STALL_S is too low: it
# refuses to start the run instead of quietly killing healthy streams.


def _stalled(label, t_start, progress):
    """Has this stream stopped producing output for longer than it should?

    The predecessor of this function asked a different question: has the
    stream produced a FIRST checkpoint yet, and so it never fired on the
    stall it was named after. The known failure of the nights of
    17./18.08. does not freeze before the first checkpoint; it freezes at
    about 8 KB, four checkpoints in. Measured again on 30.08. during a K5
    run: 64 streams, each reaching 2^13 in 0.6 s and then writing nothing
    for the remaining 119 seconds until the timeout killed it: twice
    per stream. How common that is was counted afterwards over the
    finished cost-5 campaign rather than estimated from a window: 1,337
    of 92,091 stream logs carry the stall abort, 72 the timeout. Those
    logs are published as k5_campaign.tar.gz with release v1.0. Small
    in total, and regional rather than spread: the first ten minutes
    of that run held hundreds, most later windows none.

    The rule has to catch that without killing a deep run, where hours
    between checkpoints are normal. Both follow from the same fact: a
    checkpoint is written every time the data volume doubles, so the wait
    for the next one is about as long as everything that came before it.
    Four times that, floored at STALL_S, is therefore generous at every
    depth at once: 8 s at 8 KB, most of a day at half a terabyte.

    Progress is read as file growth rather than by parsing, so a 1 TB log
    costs one stat() per poll instead of a re-read.

    How to tell whether this is biting the healthy: the runaway has a
    signature. It always stops at the same place. Across 847 cut-off
    streams in one campaign, every single one stood at 2^13, not one
    at any other depth. A detector that had started killing healthy
    streams would show a spread instead, because healthy streams are
    somewhere different every time. So if the aborted streams of a run
    ever stop at scattered depths, suspect the floor before the mixer.
    """
    now = time.time()
    try:
        size = (OUT / f"{label}.txt").stat().st_size
    except OSError:
        size = 0
    last_size, last_grew = progress.get(label, (-1, t_start))
    if size > last_size:
        progress[label] = (size, now)
        return False
    return now - last_grew > max(STALL_S, 4.0 * (last_grew - t_start))


_PROV_CACHE = {}
_ANCHOR_LOG = []


def note_anchors(verdicts):
    """Record what the anchors actually said, for the result file.

    "Anchor ok" in a console log proves nothing to anyone reading the
    result a year later. The verdicts themselves do: mix13 falling at
    2^19 is checkable against the calibration weights paper, and an
    anchor that fell at 2^24 instead would be visible rather than
    summarised away.
    """
    _ANCHOR_LOG.extend(verdicts)
    return verdicts


def _md5(path):
    """MD5 of a binary, cached. Identifies the exact tool, not its name."""
    path = str(path)
    if path not in _PROV_CACHE:
        import hashlib
        h = hashlib.md5()
        try:
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            _PROV_CACHE[path] = h.hexdigest()
        except OSError:
            _PROV_CACHE[path] = None
    return _PROV_CACHE[path]


def provenance(command, feeder=None, anchors=None):
    """Where a result came from, written into the result itself.

    A verdict here depends only on the byte stream, so the numbers are
    reproducible by construction. What was NOT reproducible until now is
    the chain of custody: nothing in a result file said which tool, which
    binaries or which anchors produced it. Two years on, or in someone
    else's hands, that leaves a number you have to take on trust.

    So every result carries its own origin: the command, the commit, the
    md5 of both binaries that touched the stream, and what the anchors
    actually said. An artifact that cannot say where it came from is
    eventually just a number.

    `dirty` is not cosmetic. A result produced from an edited working tree
    cannot be re-derived from its commit, and saying so is the difference
    between a provenance record and a decoration.
    """
    import subprocess as _sp

    def _git(*args):
        try:
            r = _sp.run(["git", "-C", str(HERE)] + list(args),
                        capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    fe = str(feeder) if feeder else str(FEEDER)
    dirty = _git("status", "--porcelain")
    return {
        "command": command,
        "tool": "ladder.py",
        "commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(dirty) if dirty is not None else None,
        "feeder": os.path.basename(fe), "feeder_md5": _md5(fe),
        "rng_test": "PractRand 0.94 (built -std=gnu++14, return patch)",
        "rng_test_md5": _md5(RNG_TEST),
        "anchors": anchors if anchors is not None else list(_ANCHOR_LOG),
        "measured": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def watchdog_sleeper():
    """Does the stall detector actually bite on the stall that happens?

    Split out into its own function so the court can run it in front of
    every measurement. It costs about STALL_S, which is more than the
    patient, and it buys the half that was missing: until 30.08. no
    biting test ran before a measurement at all, and the detector spent
    its whole existence never firing on the failure it was named after.
    A stall costs one stream two full watchdog timeouts, so twenty
    seconds up front is cheap at any run length worth anchoring.
    """
    t0 = time.time()
    lbl = run([("stalltest", 0, 0, 0)], tlmax="64MB", parallel=1,
              timeout_s=600, quiet=True,
              feeder=str(HERE / STALL_LATE), prefix="wd_")[0]
    took = time.time() - t0
    v = verdict(lbl)
    return ("ABORTED" in v and not is_clean(v) and took < STALL_S * 3,
            v, took)


def watchdog_patient():
    """Is the stall margin holding on this machine right now?

    This used to time a whole 16 KB run and require it inside STALL_S/2.
    That measured the wrong thing. _stalled() does not care how long a
    stream takes; it cares how long a stream goes without writing, and
    only the first seconds of that are governed by the floor: after
    that the four-times-elapsed term is larger and takes over.

    So the anchor now measures exactly that: the longest write-to-write
    gap of a healthy stream, polled ten times a second, in the window
    where the floor is what stands between a healthy stream and being
    killed. Measured 30.08. across eight streams under full campaign
    load, the worst gap in the first second was 0.71 s.

    It is a load canary as well as a bound. If this machine ever gets so
    busy that a healthy stream goes quiet for half the floor, the
    detector is about to start killing the living, and nothing else in
    the court would notice.
    """
    label = "wd_nasam_T0C0r00"
    worst = {"gap": 0.0, "n": 0}
    stop = threading.Event()

    def poll():
        # last_size starts at None, not at a number: run() opens the log
        # with "wb", so the file SHRINKS at the start of the run. A poller
        # that only reacts to growth would sit through the whole run
        # having seen nothing and report a worst gap of 0.00 s: which
        # reads exactly like a healthy stream and is in fact no
        # measurement at all. That is the silent pass this whole court
        # exists to prevent, and it was in here for an hour.
        last_size, last_t = None, time.time()
        while not stop.is_set():
            now = time.time()
            try:
                size = (OUT / f"{label}.txt").stat().st_size
            except OSError:
                time.sleep(0.1)
                continue
            if last_size is None or size < last_size:
                last_size, last_t = size, now      # fresh file, start over
            elif size > last_size:
                worst["gap"] = max(worst["gap"], now - last_t)
                worst["n"] += 1
                last_size, last_t = size, now
            time.sleep(0.1)

    watcher = threading.Thread(target=poll, daemon=True)
    watcher.start()
    t0 = time.time()
    lbl = run([("nasam", 0, 0, 0)], tlmax="16KB", parallel=1,
              timeout_s=600, quiet=True, prefix="wd_")[0]
    took = time.time() - t0
    stop.set()
    watcher.join(timeout=2)
    v = verdict(lbl)
    gap = worst["gap"]
    # Fewer than two observed writes means nothing was measured. An
    # unmeasured margin must never read as a good one.
    measured = worst["n"] >= 2
    return (is_clean(v) and measured and gap < STALL_S / 2.0, v, gap, took)


def court_of_record(candidate=None, candidate_name=None, low_rot=0,
                    low_tlmax="64MB", high_tlmax="256MB",
                    parallel_high=4, feeder=None):
    """Every anchor a measuring command must pass, in one place.

    This used to live as six copies: one per command, and that is
    precisely why they drifted apart: the trial ended up with four
    anchors plus the watchdog check, while the commands that do the
    actual measuring kept two. Nobody decided that; it happened because a
    principle kept as a habit at six sites gets applied at some of them.

    The calibration pair is fixed and never varies, because a weight you
    cannot check against the outside world is not a weight:

      mix13 MUST fall   Evensen publishes 2^16..2^22; this rig measures
                        2^16..2^21 (see The Calibration Weights)
      NASAM MUST hold   Evensen publishes it as passing RRC-64-42

    Both are famous, both are published by someone else, and anyone can
    re-measure them in minutes. mfx9 sat in the upper slot until 29.08.,
    and it should not have: it is our own mixer, nobody outside has ever
    measured it, so "mfx9 holds" is a self-report rather than a
    calibration. It says the rig still agrees with itself.

    `candidate` is a different thing and keeps its own slot: a pre-flight
    check that the mixer about to be measured does not already fall at
    256 MB, so a week of diploma is not spent on something that dies in a
    minute. Useful, but not a calibration, and mixing the two is what
    left the measuring commands without a checkable upper weight.

    Returns True if the rig is fit to judge. Every verdict is recorded
    via note_anchors(), so it reaches the result file rather than
    scrolling past in a console nobody kept.

      lower       mix13 MUST fall                  (calibration)
      upper       NASAM MUST hold the gauntlets    (calibration)
      candidate   optional pre-flight, MUST hold the gauntlets
      mistrial    an unmeasurable stream MUST come back NOT MEASURED
      adjourned   a watchdog kill MUST come back ABORTED
      patient     a healthy stream MUST survive the stall detector
    """
    fe = feeder if feeder is not None else FEEDER

    lbl = run([(MIX13_CHAIN, 0, 0, low_rot)], tlmax=low_tlmax, parallel=1,
              timeout_s=300, feeder=fe, prefix="anchor_")[0]
    if "FAIL" not in verdict(lbl):
        print(f"ANCHOR VIOLATED: mix13 -> {verdict(lbl)}. No start.",
              flush=True)
        return False
    note_anchors([f"mix13 (r{low_rot:02d}) -> {verdict(lbl)}"])

    def _gauntlets(mix, name, tag):
        labels = run([(mix, T, C, r) for (T, C, r) in GAUNTLET],
                     tlmax=high_tlmax, parallel=parallel_high,
                     timeout_s=900, feeder=fe, prefix=f"{tag}_")
        # Positively require "clean": an ABORTED or NOT MEASURED gauntlet
        # is not a gauntlet that held.
        bad = {l: verdict(l) for l in labels if not is_clean(verdict(l))}
        if bad:
            print(f"ANCHOR VIOLATED: {name} does not hold the "
                  f"{high_tlmax} gauntlets: {bad}", flush=True)
            return False
        note_anchors([f"{name} {l.split('_', 1)[-1]} -> {verdict(l)}"
                      for l in labels])
        return True

    if not _gauntlets("nasam", "nasam", "anchor"):
        return False
    if candidate is not None:
        if not _gauntlets(candidate, candidate_name or "candidate",
                          "preflight"):
            return False

    (ok_mis, mistrial), (ok_adj, adjourned) = judgment_anchors()
    note_anchors([f"mistrial -> {mistrial}", f"adjourned -> {adjourned}"])
    if not (ok_mis and ok_adj):
        print(f"ANCHOR VIOLATED: the court cannot say 'I did not rule' "
              f"({mistrial} / {adjourned}). No start.", flush=True)
        return False

    ok_slp, sleeper_v, sleeper_s = watchdog_sleeper()
    note_anchors([f"sleeper -> {sleeper_v} in {sleeper_s:.1f} s"])
    if not ok_slp:
        print(f"ANCHOR VIOLATED: a stream that writes 16 KB and then "
              f"freezes came back as {sleeper_v} after {sleeper_s:.1f} s. "
              f"The stall detector is not biting, and every stalled "
              f"stream will cost a full watchdog timeout twice over. "
              f"No start.", flush=True)
        return False

    ok_pat, patient_v, patient_gap, patient_s = watchdog_patient()
    note_anchors([f"patient -> {patient_v}, worst write gap "
                  f"{patient_gap:.2f} s in {patient_s:.1f} s "
                  f"(limit {STALL_S / 2.0:.1f} s)"])
    if not ok_pat:
        print(f"ANCHOR VIOLATED: the stall margin is gone: a healthy "
              f"stream went {patient_gap:.2f} s without writing, against "
              f"a {STALL_S / 2.0:.1f} s limit. The detector is about to "
              f"start killing healthy streams. No start.", flush=True)
        return False

    extra = f", {candidate_name} holds them too" if candidate else ""
    print(f"Anchor ok: mix13 falls, nasam holds the gauntlets{extra}, "
          f"the court can decline, the stall detector bites and the "
          f"margin holds.", flush=True)
    return True


def _kill(proc, tree=False):
    """Kill one half of a stream pair, and on a .bat feeder its grandchild.

    A .bat runs under cmd.exe: the process we hold is the shell, the
    thing on the pipe is its child. kill() reaches the shell only, and
    the orphan sits there holding the pipe open until its own sleep runs
    out: 600 s per stall-detector anchor, on every acid test.
    taskkill /T takes the tree, addressed by PID. By PID, and never by
    name or command line: a pattern kill matches whatever else on the
    machine looks similar, which on this machine has twice included the
    watcher that issued it.

    Only .bat feeders pay for it. The real feeder is a direct child, and
    a campaign kills tens of thousands of streams: a taskkill each
    would cost more than the stalls do.
    """
    try:
        if tree and os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        elif tree:
            # Linux: same job, different route. The feeder was started
            # with start_new_session=True, so it sits in its own process
            # group and a signal to the group takes all of it. Without
            # this, a .sh anchor leaves a sleeping python3 behind -- and
            # the stall anchor then LOOKS like it fired while the machine
            # slowly fills with orphans. By PID, never by name.
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _drive(pending, rest, labels, feeder, tlmax, parallel,
           timeout_s, quiet, watch, last_watch, on_done=None, prefix=""):
    # label -> (last log size, when it last grew). See _stalled().
    progress = {}
    # Only the stall-detector anchors run their feeder through a .bat.
    tree = str(feeder).lower().endswith((".bat", ".cmd", ".sh"))
    while rest or pending:
        while rest and len(pending) < parallel:
            mixer, T, C, r = rest.pop(0)
            fargs = [feeder]
            if mixer.startswith("chain="):
                # "chain=8:c1hex,8:c2hex,..." -> generic chain feeder;
                # lets every search candidate run without recompiling.
                ops = [op.split(":") for op in mixer[6:].split(",")]
                short = hashlib.md5(mixer.encode()).hexdigest()[:8]
                label = f"chain{short}_T{T}C{C}r{r:02d}"
                fargs += ["chain", str(T), str(C), str(r), str(len(ops))]
                for kind, hexp in ops:
                    fargs += [kind, hexp]
            else:
                label = f"{mixer}_T{T}C{C}r{r:02d}"
                fargs += [mixer, str(T), str(C), str(r)]
            label = prefix + label
            labels.append(label)
            t_start = time.time()
            out = open(OUT / f"{label}.txt", "wb")
            # Own process group, so that _kill() can take the whole
            # group. No effect on Windows.
            f = subprocess.Popen(
                fargs, stdout=subprocess.PIPE,
                start_new_session=(os.name != "nt"))
            p = subprocess.Popen([str(RNG_TEST), "stdin64", "-tf", "2",
                                  "-tlmin", "1KB", "-tlmax", tlmax],
                                 stdin=f.stdout, stdout=out,
                                 stderr=subprocess.STDOUT)
            f.stdout.close()          # end signal goes via the pipe itself
            pending.append((label, f, p, out, t_start))
        for entry in pending[:]:
            label, f, p, out, t_start = entry
            if p.poll() is not None:
                out.close()
                _kill(f, tree)        # feeder hangs on the dead pipe else
                pending.remove(entry)
                if on_done is not None:
                    if on_done(label, verdict(label)) is False:
                        for l2, f2, p2, out2, _t2 in pending:
                            _kill(p2)
                            _kill(f2, tree)
                            try:
                                out2.close()
                            except OSError:
                                pass
                            # Mark the corpse. Without this a killed
                            # stream's partial log reads "clean to 2^k"
                            # to any later out-of-band verdict() call:
                            # a truncated measurement must never look
                            # like a finished one.
                            with open(OUT / f"{l2}.txt", "a",
                                      encoding="utf-8") as m:
                                m.write("\nRRC_ABORTED run aborted "
                                        "(on_done stop)\n")
                        del pending[:]
                        del rest[:]
                        break
                elif quiet:
                    announce(label, verdict(label), time.time() - t_start)
                else:
                    print(f"  done: {label}  ->  {verdict(label)}", flush=True)
            elif _stalled(label, t_start, progress):
                # The known stall (nights of 17./18.08.): the feeder and
                # RNG_test freeze at about 8 KB, not a slow stream, a
                # dead one. Waiting out timeout_s for these is what makes
                # a K5 run cost days, because run() is a barrier and every
                # batch waits for its slowest member. _stalled() carries
                # the reasoning, and what it cost to have had it wrong.
                _kill(p)
                _kill(f, tree)
                out.close()
                with open(OUT / f"{label}.txt", "a", encoding="utf-8") as m:
                    m.write("\nRRC_ABORTED stalled: output stopped "
                            "growing\n")
                pending.remove(entry)
                if on_done is not None:
                    on_done(label, verdict(label))
                if STAGE is None:
                    print(f"  WATCHDOG: {label} stalled (no output in "
                          f"{STALL_S} s): recorded ABORTED", flush=True)
            elif timeout_s and time.time() - t_start > timeout_s:
                _kill(p)
                _kill(f, tree)
                out.close()
                with open(OUT / f"{label}.txt", "a", encoding="utf-8") as m:
                    m.write(f"\nRRC_ABORTED timeout after {timeout_s} s\n")
                pending.remove(entry)
                if on_done is not None:
                    on_done(label, verdict(label))
                if STAGE is None:
                    # With the board up, a raw print lands inside the block
                    # being repainted and smears it. The final tally lists
                    # every aborted stream either way. "WATCHDOG" is kept
                    # in the text on purpose: diploma operators grep
                    # their logs for it.
                    print(f"  WATCHDOG: {label} killed after {timeout_s} s "
                          f"-- recorded ABORTED", flush=True)
        if STAGE is not None:
            # Depths come off disk, so they are read twice a second at most;
            # the rain animates in between. Reading 32 logs at frame rate
            # would spend more time on I/O than the measurement does.
            now = time.time()
            if now - last_watch >= 0.5:
                for lbl in labels:
                    STAGE.set_depth(lbl, depth_now(lbl))
                last_watch = now
            STAGE.frame()                    # self-throttling to its fps
            time.sleep(0.04)
        else:
            if watch and pending and time.time() - last_watch >= watch:
                show_progress(pending)
                last_watch = time.time()
            time.sleep(0.5)
    return labels


def verdict(label):
    text = (OUT / f"{label}.txt").read_text(errors="replace")
    if "RRC_ABORTED" in text:
        # Two different deaths, and the log must not call one the other:
        # a stream killed for producing nothing after STALL_S seconds did
        # not time out, it stalled. Both remain ABORTED and neither ever
        # reads as clean, but "timeout" on a 20 s kill under a 600 s
        # limit would be a small lie in every log that carries it.
        return ("ABORTED (stalled)" if "stalled" in text
                else "ABORTED (timeout)")
    last = "?"
    for part in re.split(r"(?=length= )", text):
        m = re.match(r"length= .*?\(2\^(\d+) bytes\)", part)
        if not m:
            continue
        last = "2^" + m.group(1)
        if "FAIL" in part:
            return f"FAIL at {last}"
    if last == "?":
        # PractRand wrote nothing measurable. This is the 17.08. trap one
        # level up: a judge that silently said nothing must never read as
        # an acquittal. Not clean, not fallen, not measured.
        return "NOT MEASURED (no PractRand output)"
    n_susp = len(re.findall(r"suspicious", text))
    extra = f"  ({n_susp}x suspicious)" if n_susp else ""
    return f"clean to {last}{extra}"


def smoke_streams(mixer):
    """RRC pre-stage: 8 rotations x 4 transformations = 32 streams."""
    return [(mixer, T, C, r) for (T, C) in ((0, 0), (1, 0), (0, 1), (1, 1))
            for r in range(0, 64, 8)]


# ===================================================================
#  THE TRIAL: bring your own mixer
# ===================================================================
#
#  This rig exists so a stranger can put a mixer in and get an honest
#  number out. Everything below is that path: build, prove the court
#  works, then judge.
#
#  A real verdict takes hours. What makes the wait bearable is not
#  decoration but that every line printed is a measurement that just
#  happened: a stream reports 2^28 because PractRand wrote it down,
#  not because a spinner spun.

FEEDER_SRC = HERE / "feeder.cpp"
USER_HEADER = HERE / "mixer_user.h"


def build_feeder(march="native"):
    """Compile the feeder. Picks up mixer_user.h automatically if present."""
    cmd = ["g++", "-O3", "-march=" + march, "-std=gnu++14",
           str(FEEDER_SRC), "-o", str(FEEDER)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stderr or "").strip(), " ".join(cmd)


def depth_now(label):
    """How deep is this stream right now? Straight out of PractRand's own
    log. None means 'nothing measured yet', never 'fine so far'."""
    f = OUT / (label + ".txt")
    if not f.exists():
        return None
    try:
        hits = re.findall(r"\(2\^(\d+) bytes\)", f.read_text(errors="replace"))
    except OSError:
        return None
    return int(hits[-1]) if hits else None


def cause_of_death(label):
    """The test that caught it. A death notice without a cause is gossip."""
    f = OUT / (label + ".txt")
    if not f.exists():
        return None
    lines = [l.strip() for l in f.read_text(errors="replace").splitlines()
             if "FAIL" in l]
    return lines[-1] if lines else None


def hms(sec):
    sec = int(sec)
    if sec < 60:
        return "%d s" % sec
    if sec < 3600:
        return "%d min %02d s" % (sec // 60, sec % 60)
    return "%d h %02d min" % (sec // 3600, (sec % 3600) // 60)


# -------------------------------------------------------------------
#  Terminal theatre
# -------------------------------------------------------------------
#
#  A death on the ladder is worth watching. But the same output also
#  ends up in log files, long runs are started detached with the
#  output redirected, and escape codes in a log file are garbage.
#  So the theatre only plays on a real terminal. Piped, it degrades to
#  the plain line, same information, no decoration.

def _utf8_stdout():
    """The board is drawn with block glyphs (block, shade, heavy rule, skull).
    A Windows console defaults to cp1252 and raises UnicodeEncodeError on the
    first one: the run would die of its own decoration. Fail soft: if the
    stream cannot be switched, ASCII_ONLY takes over below."""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:                     # noqa: BLE001
                return False
    return True


UTF8 = _utf8_stdout()


def _enable_ansi():
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:                                  # Windows 10+ needs VT switched on
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            k.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:                     # noqa: BLE001
            return False
    return True


THEATRE = _enable_ansi() and UTF8
THEATRE_ARMED = False        # only the candidate gets the full show
ANNOUNCE_SILENT = False      # the court reports itself, stream by stream
                             # announcements would say it twice
def _c(n):
    return "\033[38;5;%dm" % n           # 256-colour foreground


OFF, BOLD = "\033[0m", "\033[1m"
# One hue, many depths. Everything on this rig is green; the only thing
# that is not is a death. That way red never has to compete for your eye
# with a heading, a border or a banner: if you see red, something died.
GLEAM, BRIGHT, GREEN = _c(48), _c(46), _c(40)
MOSS, DEEP, SHADOW = _c(34), _c(28), _c(22)
GREY, DIM, WHITE = _c(238), _c(240), _c(231)
RED, DARKRED, EMBER = _c(196), _c(88), _c(52)

# Depth ramp: shallow is dim, deep is bright. The colour IS the number:
# you read the room at a glance and only then look at the digits.
DEPTH_RAMP = ((14, SHADOW), (18, DEEP), (24, MOSS), (30, BRIGHT), (99, GLEAM))


def depth_colour(d):
    if d is None:
        return GREY
    for edge, col in DEPTH_RAMP:
        if d < edge:
            return col
    return GREEN


# Block font, 5 rows. Only the glyphs the banner needs.
FONT = {
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "H": ("█   █", "█   █", "█████", "█   █", "█   █"),
    "E": ("█████", "█    ", "████ ", "█    ", "█████"),
    "L": ("█    ", "█    ", "█    ", "█    ", "█████"),
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "D": ("████ ", "█   █", "█   █", "█   █", "████ "),
    "R": ("████ ", "█   █", "████ ", "█  █ ", "█   █"),
    " ": ("     ", "     ", "     ", "     ", "     "),
}
BANNER_COLS = (GLEAM, BRIGHT, GREEN, MOSS, DEEP, SHADOW)


def banner(word="THE LADDER", sub="64-bit mixers, judged by how deep they get"):
    if not THEATRE:
        print("=" * 68)
        print("  %s -- %s" % (word, sub))
        print("=" * 68)
        return
    rows = ["", "", "", "", ""]
    for ch in word:
        g = FONT.get(ch.upper(), FONT[" "])
        for i in range(5):
            rows[i] += g[i] + " "
    print()
    for i, row in enumerate(rows):
        # gradient down the rows, so the letters look lit from above
        print("   " + BANNER_COLS[i % len(BANNER_COLS)] + row + OFF)
    print("   " + DIM + sub + OFF)
    print()


def rule_heavy(width=68, col=None):
    return (col or GREY) + "━" * width + OFF if THEATRE else "-" * width


STAGE = None                 # set by trial() while the board is up


def epitaph(label):
    """The test that caught it, on one readable line. PractRand pads its
    columns generously; collapsing the runs of spaces keeps 'FAIL !!' from
    being cut off, and that is the one word you must not lose."""
    why = cause_of_death(label)
    return " ".join(why.split()) if why else None


def announce(label, v, secs=None):
    """One stream finished. With the board up, the board says it: printing
    here would shove the board up the screen and break the repaint."""
    if ANNOUNCE_SILENT:
        return
    if STAGE is not None and label in STAGE.state:
        if v.startswith("FAIL"):
            STAGE.fell(label)
        else:
            STAGE.held(label)
        return
    took = "  (%s)" % hms(secs) if secs else ""
    print("  %-26s %s%s" % (label, v, took), flush=True)
    if v.startswith("FAIL"):
        why = epitaph(label)
        if why:
            print("      caught by: " + why[:78], flush=True)


def show_progress(pending):
    """Fallback for runs without a board (piped output, other modules).
    Never called while a board is up; _drive owns the board directly."""
    parts = []
    for label, _f, _p, _out, t_start in pending:
        d = depth_now(label)
        parts.append("%s %s" % (label.split("_")[-1],
                                ("2^%d" % d) if d else "--"))
    if parts:
        print("  ... still standing: " + "  ".join(parts), flush=True)


def hold_court(tlmax="16MB", parallel=2):
    """Before judging a stranger, the court proves it can judge, and the
    proof has to span every verdict it is able to hand down, plus the
    watchdog that decides which streams reach a verdict at all:

        FAIL          a known guilty mixer MUST fall
        clean         a known innocent one MUST hold
        NOT MEASURED  an unmeasurable stream MUST be declared unmeasured
        ABORTED       a killed stream MUST be declared aborted
        (it bites)    a stream that freezes MUST be cut off
        (the margin)  a healthy stream MUST survive the stall detector

    The first two were here from the start; they prove the rig can tell
    weak from strong. The last two were added 28.08., after ten separate
    places were found reading a silent judge as an acquittal. A verdict
    nobody ever checked the rig can produce is a verdict you cannot trust
    it to produce, and those two only ever come up once something has
    already gone wrong, which is precisely when nobody is watching.

    If any of the six misbehaves, every verdict that would follow is
    worthless, so stop instead of issuing one."""
    print("  " + rule_heavy(66, MOSS if THEATRE else None))
    print("  %sTHE COURT CONVENES%s" % (BOLD + GLEAM if THEATRE else "",
                                        OFF if THEATRE else ""))
    print("  " + rule_heavy(66, MOSS if THEATRE else None))
    print("  %sBefore it judges a stranger, it proves it can judge.%s"
          % (GREEN if THEATRE else "", OFF if THEATRE else ""))
    print("  (six anchors in three pairs: two on the mixers, two on the")
    print("   court itself, two on the watchdog that decides which streams")
    print("   count: each pair asked from both sides)")
    print("  The next three lines are the court breaking itself on purpose")
    print("  -- an unknown mixer, a killed stream, a frozen one. All three")
    print("  are meant to happen.")
    print()
    global ANNOUNCE_SILENT
    ANNOUNCE_SILENT = True               # the court speaks once, below
    try:
        # The feeder writes its own complaint straight to the console while
        # our prints are still sitting in Python's buffer: without this
        # flush the "unknown mixer" line lands ABOVE the banner announcing
        # it, and the deliberate break reads like a crash.
        sys.stdout.flush()
        # The cheap pair first. If the court cannot say "I did not rule on
        # this", nothing it says afterwards is worth the minutes it costs.
        (ok_mis, mistrial), (ok_adj, adjourned) = judgment_anchors()
        # Both halves of the watchdog pair run here. Until 30.08. only
        # the patient did, on the argument that "can the detector fire?"
        # is a property of the code and belongs somewhere cheaper. That
        # argument cost the rig dearly: the property was wrong for the
        # detector's entire existence: it looked for a missing FIRST
        # checkpoint, while the stall it is named after happens four
        # checkpoints in, and the place it supposedly belonged did not
        # check it either. A fifth of the streams in a campaign each paid
        # two full watchdog timeouts before anyone noticed.
        #
        # The two ask different questions and both are needed. The sleeper
        # asks whether the detector bites at all; the patient asks whether
        # today's load has eroded the margin, so that it bites the
        # healthy. Twenty-two seconds together, in front of a trial that
        # then spends minutes on a 32-stream smoke.
        (ok_slp, sleeper_v, sleeper_s) = watchdog_sleeper()
        (ok_pat, patient_v, patient_gap, patient_s) = watchdog_patient()
        labels = run([("mix13", 0, 0, 0), ("nasam", 0, 0, 0)],
                     tlmax=tlmax, parallel=parallel, quiet=True)
    finally:
        ANNOUNCE_SILENT = False
    guilty, innocent = verdict(labels[0]), verdict(labels[1])
    ok_guilty = guilty.startswith("FAIL")
    # "clean" must be proven, not inferred: an ABORTED or NOT MEASURED
    # anchor is not an innocent that held, it is a court that never sat.
    ok_innocent = is_clean(innocent)
    def _mark(ok):
        if not THEATRE:
            return "OK" if ok else "*** WRONG ***"
        return (GLEAM + "OK" + OFF) if ok else (RED + BOLD + "*** WRONG ***" + OFF)
    tone = GREEN if THEATRE else ""
    print("  %sTHE GUILTY     mix13     must fall      %-34s%s %s"
          % (tone, guilty, OFF if THEATRE else "", _mark(ok_guilty)))
    print("  %sTHE INNOCENT   nasam     must hold      %-34s%s %s"
          % (tone, innocent, OFF if THEATRE else "", _mark(ok_innocent)))
    print("  %sTHE MISTRIAL   no mixer  must not clear %-34s%s %s"
          % (tone, mistrial, OFF if THEATRE else "", _mark(ok_mis)))
    print("  %sTHE ADJOURNED  killed    must not clear %-34s%s %s"
          % (tone, adjourned, OFF if THEATRE else "", _mark(ok_adj)))
    print("  %sTHE SLEEPER    frozen    must be cut    %-34s%s %s"
          % (tone, "%s (%.1f s)" % (sleeper_v, sleeper_s),
             OFF if THEATRE else "", _mark(ok_slp)))
    print("  %sTHE PATIENT    healthy   must survive   %-34s%s %s"
          % (tone, "%s (gap %.2f s, limit %.1f s)" % (patient_v,
                                                       patient_gap,
                                                       STALL_S / 2.0),
             OFF if THEATRE else "", _mark(ok_pat)))
    print()
    if not (ok_guilty and ok_innocent and ok_mis and ok_adj
            and ok_slp and ok_pat):
        print("  The court is NOT fit to sit. No verdict will be issued --")
        print("  a rig that cannot condemn the guilty cannot acquit anyone,")
        print("  and one that cannot say 'I did not rule' acquits by silence.")
        return False
    print("  The court is fit to sit.")
    print()
    return True


def check_judge():
    """Is the judge actually there? _find_rng_test() hands back a best-guess
    path even when nothing exists, and the miss then surfaces four frames
    deep inside subprocess as WinError 2, which tells you nothing about
    PractRand. A missing judge is the one failure that must be unmistakable:
    without it nothing gets measured at all."""
    if Path(RNG_TEST).is_file():
        return True
    print("PractRand's RNG_test was not found. Nothing can be measured.")
    print()
    note = HERE / "practrand.txt"
    print("  looked for : %s" % RNG_TEST)
    print("  note file  : %s%s" % (note, "" if note.is_file()
                                   else "   (does not exist yet)"))
    print("  $PRACTRAND : %s" % (os.environ.get("PRACTRAND") or "not set"))
    print()
    print("Write the path to your build into that file, one line, and it")
    print("holds for every shell window from now on:")
    print()
    print('    C:/tools/PractRand_094/RNG_test.exe')
    print()
    print("An environment variable works too, but only in the window you")
    print("set it in, which is why the file is the one that gets read first.")
    print()
    print("PractRand is not bundled (own licence, and it needs the documented")
    print("patch). See the README for building it.")
    return False


def trial(tlmax="2GB", parallel=4, streams=None, watch=30):
    # parallel=4 and not PAR on purpose: the trial runs with the live
    # board up, and 16 columns climbing at once is not readable. The
    # verdict does not depend on the width, only the wall clock does.
    # watch only matters for the text fallback: the board paces itself.
    # At 1 s it printed a "still standing" line every second for hours.
    """Full path for a stranger's mixer: build, prove the court, judge."""
    banner()
    if not check_judge():
        return False
    if not USER_HEADER.exists():
        print("No mixer_user.h next to feeder.cpp.")
        print()
        print("Write one. It needs exactly this:")
        print()
        print("    static inline uint64_t user_mix(uint64_t x) {")
        print("        /* your mixer */")
        print("        return x;")
        print("    }")
        print()
        print("Then run this again. Nothing else needs editing.")
        return False

    print()
    print("  Compiling the feeder with your mixer ...")
    rc, err, cmd = build_feeder()
    if rc != 0:
        print("  The build failed. Your mixer never reached the court:")
        print()
        for line in err.splitlines()[:15]:
            print("    " + line)
        print()
        print("  Command was: " + cmd)
        return False
    print("  Built.")
    print()

    if not hold_court():
        return False

    if streams is None:              # the full smoke: 4 disguises x 8 rotations
        streams = smoke_streams("user")
    print()
    print("  " + rule_heavy(62, GREEN if THEATRE else None))
    print("  %sTHE CANDIDATE%s  %suser_mix from mixer_user.h%s"
          % (BOLD + GREEN if THEATRE else "", OFF if THEATRE else "",
             DIM if THEATRE else "", OFF if THEATRE else ""))
    print("  %s%d streams, each to %s%s"
          % (DIM if THEATRE else "", len(streams), tlmax, OFF if THEATRE else ""))
    print("  " + rule_heavy(62, GREEN if THEATRE else None))
    print()

    global THEATRE_ARMED, STAGE
    t0 = time.time()
    # Labels are derivable before anything runs, so the board can show
    # every stream from the first frame: including the ones still queued.
    labels_expected = ["%s_T%dC%dr%02d" % (m, T, C, r) for (m, T, C, r) in streams]
    board = None
    if THEATRE:
        rows, cw, why = fit(len(labels_expected))
        if rows:
            board = Board(labels_expected, tlmax,
                                  feeder=FEEDER, rows=rows, cw=cw)
            board.frame(force=True)
        else:
            # Never fall back in silence, that reads as "there is no
            # board in this program", and you go looking for the wrong bug.
            print("  (no board: %s; falling back to text)" % why)
    else:
        print("  (no board: output is not a terminal, text only)")
    STAGE = board
    THEATRE_ARMED = True
    try:
        labels = run(streams, tlmax=tlmax, parallel=parallel,
                     quiet=True, watch=watch)
        if board:
            for lbl in labels:
                board.set_depth(lbl, depth_now(lbl))
            board.rank()                 # the skyline becomes a ranking
            board.close()
    finally:
        THEATRE_ARMED = False
        STAGE = None

    # Each stream already announced itself as it finished; this is the
    # tally, not a repeat. Verdicts are read once: each call re-reads
    # the stream's log from disk.
    verdicts_by_label = {l: verdict(l) for l in labels}
    dead = sum(1 for v in verdicts_by_label.values() if v.startswith("FAIL"))
    # Anything neither fallen nor clean (ABORTED, NOT MEASURED) is a hole
    # in the measurement, and a hole must never be countable as a pass.
    broken = [l for l in labels
              if not (verdicts_by_label[l].startswith("FAIL") or verdicts_by_label[l].startswith("clean"))]
    deepest = [depth_now(l) for l in labels]
    reached = max([d for d in deepest if d] or [0])
    print()
    print("  " + rule_heavy(62, RED if (THEATRE and dead) else (GREEN if THEATRE else None)))
    print("  %sVERDICT%s  after %s, deepest stream %s2^%d%s"
          % (BOLD + (RED if dead else GREEN) if THEATRE else "", OFF if THEATRE else "",
             hms(time.time() - t0),
             depth_colour(reached) if THEATRE else "", reached, OFF if THEATRE else ""))
    print("  " + rule_heavy(62, RED if (THEATRE and dead) else (GREEN if THEATRE else None)))
    # Only the weakest disguises get an epitaph here. Printing all 32 buries
    # the one number that decides the verdict under two screens of text:
    # and on the ladder a mixer is worth exactly its worst stream. The rest
    # is on disk, per stream, where it can be read at leisure.
    dead_labels = [l for l in labels if verdicts_by_label[l].startswith("FAIL")]
    dead_labels.sort(key=lambda l: depth_now(l) or 0)
    for label in dead_labels[:5]:
        why = epitaph(label)
        print("  %s%-12s %s%s" % (RED if THEATRE else "",
                                  label.split("_")[-1], verdicts_by_label[label],
                                  OFF if THEATRE else ""))
        if why:
            print("       %scaught by: %s%s" % (DIM if THEATRE else "",
                                                why[:74], OFF if THEATRE else ""))
    if len(dead_labels) > 5:
        print("  %s... and %d more, all in %s%s"
              % (DIM if THEATRE else "", len(dead_labels) - 5,
                 OUT.name + "/", OFF if THEATRE else ""))
    if broken:
        print("  %d stream(s) were NOT measured to the end:" % len(broken))
        for label in broken:
            print("    %-12s %s" % (label.split("_")[-1], verdicts_by_label[label]))
        print("  These are holes in the verdict, not passes. Re-run them.")
    if dead == 0 and not broken:
        print("  All %d streams held to %s. That is not a certificate:" % (len(labels), tlmax))
        print("  it means nothing in THIS rig at THIS length could tell it")
        print("  from random. Run it longer and it may still fall.")
    elif dead == 0:
        print("  No stream fell, but with %d unmeasured, this is NOT a pass."
              % len(broken))
    else:
        print("  %d of %d streams fell. One death is enough --" % (dead, len(labels)))
        print("  a mixer is only as strong as its weakest disguise.")
    return dead == 0 and not broken


# ===================================================================
#  THE BOARD: the live matrix display (formerly theatre.py)
# ===================================================================
#  The screen IS the ladder: rows are depths, the target on the top
#  rung, each stream a column that climbs while real feeder bytes
#  rain down through it. Optional by design: every path degrades to
#  plain text when the terminal cannot carry a board.


LO, HI = 10, 40                      # depth range the board spans
GUTTER = 5                           # left margin carrying the "2^40" ticks


RISE_CH = "█" if UTF8 else "#"          # full block
DEAD_CH = "▒" if UTF8 else ":"          # medium shade




# Matrix ramp: head is near-white, then the green falls away to almost black.
G = [_c(46), _c(40), _c(34), _c(28), _c(22), _c(238)]
RISEN = GLEAM                       # the climbed part of a column
# The risen column is brightest at its tip, that is the number you are
# actually reading. Below it the light falls away, so a screen of 32
# columns reads as a skyline instead of a wall.
RISE_RAMP = (_c(48), _c(42), _c(36), _c(30), _c(23))
DEAD = _c(236)
LABEL = _c(35)

GLYPHS = "0123456789abcdef"

_UNITS = {"KB": 10, "MB": 20, "GB": 30, "TB": 40}


def target_pow(tlmax, default=40):
    """Turn '8MB' into 23: the exponent the run is actually aiming at.

    The top rung has to BE the target. A board that always runs to 2^40
    while the run stops at 2^23 spends three quarters of its height on
    depth nobody is even attempting: the picture looks empty and the
    climb looks hopeless, when in truth the streams went the distance."""
    try:
        s = str(tlmax).strip().upper()
        for unit, base in _UNITS.items():
            if s.endswith(unit):
                n = float(s[:-len(unit)])
                p = base
                while n >= 2:
                    n /= 2.0
                    p += 1
                return int(p)
        return int(round(float(s)))
    except Exception:                                        # noqa: BLE001
        return default


def sample_bytes(feeder, mixer="user", n=4096):
    """Grab a few kilobytes of the candidate's own output for the rain.

    One short run, killed immediately: it costs a blink of CPU and buys
    a board made of the real thing. If it fails for any reason the rain
    falls back to plain hex digits; a broken sample must not stop a run."""
    try:
        p = subprocess.Popen([str(feeder), mixer, "0", "0", "0"],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
        data = p.stdout.read(n)
        p.stdout.close()
        p.kill()
        return data or b""
    except Exception:                                        # noqa: BLE001
        return b""


def fit(n_streams, min_rows=8):
    """How tall a board this window can carry, or why it cannot carry one.

    A board wider than the window wraps, and every cursor-up after that
    lands on the wrong line and smears the picture, so refusing is
    right. Refusing SILENTLY is not: the run then looks like the board
    was never built into the program at all. Always return a reason."""
    try:
        w, h = shutil.get_terminal_size()
    except Exception as e:                                   # noqa: BLE001
        return None, None, "terminal size unknown (%s)" % e
    # Prefer a gap between columns; drop it before giving up entirely.
    # A dense field of columns still reads fine: an absent board does not.
    for cw in (2, 1):
        if w >= GUTTER + n_streams * cw - (cw - 1):
            break
    else:
        return None, None, ("window is %d columns, %d streams need %d"
                            % (w, n_streams, GUTTER + n_streams))
    rows = min(20, h - 7)                 # 7 lines of chrome and prompt
    if rows < min_rows:
        return None, None, ("window is %d rows, the board needs %d"
                            % (h, min_rows + 7))
    return rows, cw, None


class Board:
    ROWS = 20
    CW = 2                           # cells per column: glyph + gap

    def __init__(self, labels, tlmax, feeder=None, fps=12, rows=None, cw=None):
        if rows:
            self.ROWS = rows              # whatever this window can carry
        if cw:
            self.CW = cw
        self.labels = list(labels)
        self.n = len(self.labels)
        self.tlmax = tlmax
        self.HI = max(LO + 4, target_pow(tlmax))   # the top rung IS the target
        self.depth = {l: None for l in self.labels}
        self.state = {l: "waiting" for l in self.labels}
        self.t0 = time.time()
        self.fps = fps
        self.last_frame = 0.0
        self.last_height = 0
        self.drawn = False
        self.strike = {}             # label -> frames of red left
        self.ranked = False
        self.width = GUTTER + self.n * self.CW - (self.CW - 1)
        self.height = self.ROWS + 5

        pool = sample_bytes(feeder) if feeder else b""
        if pool:
            self.pool = "".join(GLYPHS[b & 15] for b in pool)
        else:
            # Without a sample, walking "0123..f" in order would draw a
            # visible counter down every column. Scramble it so the
            # fallback at least looks like noise instead of a ramp.
            s, x = [], 0x243F6A88
            for _ in range(4096):
                x = (x * 1103515245 + 12345) & 0xFFFFFFFF
                s.append(GLYPHS[(x >> 16) & 15])
            self.pool = "".join(s)
        self.pi = 0
        self.real_rain = bool(pool)

        # One rain drop per column: head row, speed, tail length. Seeded
        # from the column index so the columns never march in step.
        self.drop = []
        for i in range(self.n):
            self.drop.append({
                "row": float(-(i * 7 % self.ROWS)),
                "spd": 0.35 + ((i * 13) % 9) * 0.11,
                "tail": 4 + (i * 5) % 7,
            })

    #: glyph source ------------------------------------------------
    def _g(self):
        self.pi = (self.pi + 1) % len(self.pool)
        return self.pool[self.pi]

    #: geometry ----------------------------------------------------
    def _row_of(self, d):
        """Which row a depth sits on. Row 0 is the top (2^40)."""
        if d is None:
            return None
        f = (min(max(d, LO), self.HI) - LO) / float(self.HI - LO)
        return int(round((1.0 - f) * (self.ROWS - 1)))

    #: painting ----------------------------------------------------
    def _cells(self):
        """Build ROWS x n grid of (char, colour). Nothing here is random
        where it could be measured: column height comes from the depth."""
        grid = [[(" ", None)] * self.n for _ in range(self.ROWS)]
        for i, label in enumerate(self.labels):
            st = self.state[label]
            top = self._row_of(self.depth[label])
            dead = st == "fell"

            # the climbed part: from the bottom up to the reached depth
            if top is not None:
                for r in range(top, self.ROWS):
                    if dead:
                        grid[r][i] = (DEAD_CH, DEAD)
                    else:
                        k = min(len(RISE_RAMP) - 1, (r - top) // 3)
                        grid[r][i] = (RISE_CH, RISE_RAMP[k])

            if dead or st == "held":
                continue

            # the rain above it
            d = self.drop[i]
            d["row"] += d["spd"]
            limit = top if top is not None else self.ROWS
            if d["row"] - d["tail"] > limit:
                d["row"] = float(-(d["tail"] + (i * 3) % 5))
            head = int(d["row"])
            for t in range(d["tail"]):
                r = head - t
                if 0 <= r < limit:
                    shade = WHITE if t == 0 else G[min(len(G) - 1,
                                                      1 + t * len(G) // max(1, d["tail"]))]
                    grid[r][i] = (self._g(), shade)
        return grid

    def _line(self, cells, prefix=""):
        """Emit a row, only changing colour when it actually changes --
        a fresh escape per cell would be five times the bytes and the
        terminal would tear."""
        out, cur = [prefix], None
        last = len(cells) - 1
        for k, (ch, col) in enumerate(cells):
            if col != cur:
                out.append(col or OFF)
                cur = col
            out.append(ch)
            if k != last:                 # no gap after the last column, so
                out.append(" " * (self.CW - 1))   # the board never wraps
        out.append(OFF)
        return "".join(out)

    def render(self):
        grid = self._cells()
        # The board clears the screen, so the banner and the court's verdict
        # scroll out of reach. One line of context has to survive here.
        lines = [LABEL + "  THE LADDER" + OFF + DIM +
                 "   user_mix from mixer_user.h   ->  %s" % self.tlmax + OFF]
        span = self.HI - LO
        ticks = {}
        for k in range(4):
            d = LO + int(round(span * k / 3.0))
            ticks[self._row_of(d)] = "2^%d" % d
        for r in range(self.ROWS):
            tag = ticks.get(r, "")
            for lab, cnt in self.strike.items():
                if cnt > 0:
                    i = self.labels.index(lab)
                    grid[r][i] = (grid[r][i][0] if grid[r][i][0] != " " else "#",
                                  RED if cnt % 2 else DARKRED)
            lines.append(self._line(grid[r], DIM + "%4s " % tag + OFF))
        for lab in list(self.strike):
            self.strike[lab] -= 1
            if self.strike[lab] <= 0:
                del self.strike[lab]

        lines.append("")
        lines.append(self._groups())
        held = sum(1 for l in self.labels if self.state[l] == "held")
        fell = sum(1 for l in self.labels if self.state[l] == "fell")
        deep = max([d for d in self.depth.values() if d] or [0])
        lines.append(LABEL + "  %d streams   " % self.n + OFF +
                     DIM + "deepest " + OFF + RISEN + "2^%d" % deep + OFF +
                     DIM + "   held " + OFF + RISEN + str(held) + OFF +
                     DIM + "   fell " + OFF + RED + str(fell) + OFF +
                     DIM + "   %s   target %s" % (hms(time.time() - self.t0),
                                                    self.tlmax) + OFF)
        lines.append(DIM + "  rain: %s" %
                     ("hex of the candidate's own output"
                      if self.real_rain else "hex (no sample taken)") + OFF)
        return lines

    def _groups(self):
        """32 columns cannot carry 32 labels. During the run they are in run
        order, so the four disguises are the useful marks; once ranked, the
        only thing the axis still means is depth."""
        if self.ranked:
            left = LABEL + "  deepest" + OFF
            right = DIM + "shallowest" + OFF
            pad = max(1, self.width - 2 - 7 - 10)
            return left + " " * pad + right
        per = max(1, self.n // 4)
        out = [" " * GUTTER]
        groups = ("T0C0", "T1C0", "T0C1", "T1C1")
        for k, name in enumerate(groups):
            if k * per >= self.n:
                break
            span = min(per, self.n - k * per) * self.CW
            if k == len(groups) - 1:
                span -= self.CW - 1       # the last column carries no gap
            out.append(LABEL + name.center(span)[:span] + OFF)
        return "".join(out)

    def frame(self, force=False):
        now = time.time()
        if not force and now - self.last_frame < 1.0 / self.fps:
            return
        self.last_frame = now
        lines = self.render()
        out = []
        if self.drawn:
            # Count the lines actually written last time instead of trusting
            # a formula. A formula that is one off does not look one off:
            # it smears the whole board, and the mistake is invisible in the
            # code because the number looks plausible.
            out.append("\033[%dA" % self.last_height)
        else:
            # Own the screen. If anything else is still on it, the board
            # pushes it up, the terminal scrolls, and every cursor-up from
            # then on lands one line too high. Clearing costs one escape
            # sequence and removes the entire class of bug.
            out.append("\033[2J\033[H")
        for line in lines:
            out.append("\r\033[K" + line + "\n")
        self.last_height = len(lines)
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        self.drawn = True

    #: events ------------------------------------------------------
    def set_depth(self, label, d):
        if d is not None:
            self.depth[label] = d
            if self.state[label] == "waiting":
                self.state[label] = "climbing"

    def fell(self, label):
        self.state[label] = "fell"
        self.strike[label] = 10          # frames of red
        for _ in range(10):
            self.frame(force=True)
            time.sleep(0.04)

    def held(self, label):
        self.state[label] = "held"

    def rank(self):
        """The reveal: the columns sort themselves, deepest on the left.

        Only at the end. Reordering while streams are still climbing would
        make the board unreadable: you could never find the one you were
        watching. Once everything has finished, run order carries no
        information any more and depth carries all of it."""
        order = sorted(self.labels, key=lambda l: (-(self.depth[l] or 0), l))
        cur = list(self.labels)
        for k in range(len(order)):
            if cur[k] == order[k]:
                continue
            j = cur.index(order[k])
            cur[k], cur[j] = cur[j], cur[k]
            self.labels = list(cur)
            self.frame(force=True)
            time.sleep(0.035)
        self.labels = order
        self.ranked = True
        self.frame(force=True)

    def close(self):
        if self.drawn:
            self.frame(force=True)
            sys.stdout.write("\n")
            sys.stdout.flush()


# ===================================================================
#  SUBCOMMANDS: the nine former modules, one file
# ===================================================================
#
#  Everything below used to be nine separate modules. Merged 2026-08-26
#  so the public repo ships two files: ladder.py + feeder.cpp. Each
#  subcommand keeps its original argument style and, crucially, its
#  original checkpoint/result FILENAMES: existing resume files stay
#  valid. The git history holds the originals.

import itertools
import json
import random
import struct

FEEDER_EXE = FEEDER                      # the old modules' name for it

#: shared constants (were duplicated across up to four modules) -----
GAUNTLET = [(1, 0, 16), (1, 0, 0), (0, 0, 0), (0, 0, 32)]
SMOKE_TCR = [(T, C, r) for (T, C) in ((0, 0), (1, 0), (0, 1), (1, 1))
             for r in range(0, 64, 8)]
GAM = 0x9E3779B97F4A7C15
MIX13_CHAIN = "chain=0:1e,1:bf58476d1ce4e5b9,0:1b,1:94d049bb133111eb,0:1f"
# Not an anchor. It sat in the upper anchor slot until 29.08.26 and was
# taken out: mfx9 is ours, nobody outside has measured it, so "mfx9
# holds" says the rig agrees with itself. NASAM replaced it: same
# cost on the gauntlets, and Evensen published its range. Kept here
# because the chain form is the record of what was found.
MFX9_CHAIN = (f"chain=6:{GAM:x},8:781f94b96e8edb3b,8:b853d68343f7525b")
CONST_POOL = [
    0xbf58476d1ce4e5b9, 0x94d049bb133111eb, 0x3C79AC492BA7B653,
    0x1C69B3F74AC4AE35, 0x9E6C63D0676A9A99, 0x9E6D62D06F6A9A9B,
    0xff51afd7ed558ccd, 0xc4ceb9fe1a85ec53, 0xd6e8feb86659fd93,
    0x9FB21C651E98DF25, 0xA24BAED4963EE407,
    0x781f94b96e8edb3b, 0xb853d68343f7525b,
    0x9E3779B97F4A7C15,
]


def chain_str(ops):
    return "chain=" + ",".join(f"{t}:{p:x}" for t, p in ops)


def fail_exp(label):
    """FAIL exponent of a finished stream: int = fell at 2^k,
    "ABORTED" = not measured, None = clean."""
    u = verdict(label)
    if "ABORTED" in u or "NOT MEASURED" in u:
        return "ABORTED"
    m = re.search(r"FAIL at 2\^(\d+)", u)
    return int(m.group(1)) if m else None


def is_clean(v):
    """True only for a verdict that positively says the stream came through.

    Every "not FAIL" test reads an unmeasured stream as a passing one: a
    watchdog kill (ABORTED) and a silent PractRand (NOT MEASURED) both
    carry no FAIL, so subtracting the fallen from the total counted them
    as survivors. Absence of a conviction is not innocence: ask for the
    acquittal in writing. Found 28.08. in four places at once, all of them
    one level above the same trap that produced verdict()'s own guard.
    """
    return v.startswith("clean")


def judgment_anchors():
    """The two anchors that test the judge instead of the mixer.

    mix13-must-fall and nasam-must-hold prove the rig can tell a weak
    stream from a strong one. Neither proves the rig can say "I did not
    measure this". That gap is not theoretical: on 28.08. it turned up in
    ten places at once, every one reading a silent judge as an acquittal.

    A verdict nobody ever checked the rig can produce is a verdict you
    cannot trust it to produce when it matters, and these two only ever
    matter when something has already gone wrong, which is exactly when
    nobody is watching. So force them and require them by name.

    Cost is seconds, not minutes: an unknown mixer is rejected before a
    single byte is generated, and the watchdog anchor is killed after 3 s.
    Cheap enough to run in front of every long measurement.
    """
    l_mis = run([("ladder_no_such_mixer", 0, 0, 0)], tlmax="1MB",
                parallel=1, timeout_s=30, quiet=True, prefix="judge_")[0]
    l_adj = run([("nasam", 0, 0, 0)], tlmax="64GB",
                parallel=1, timeout_s=3, quiet=True, prefix="judge_")[0]
    v_mis, v_adj = verdict(l_mis), verdict(l_adj)
    # Both halves: the right words AND a refusal to read as clean. The
    # string alone is not enough: the bug lived in the layer that reads
    # it, not in the layer that writes it.
    return ((("NOT MEASURED" in v_mis) and not is_clean(v_mis), v_mis),
            (("ABORTED" in v_adj) and not is_clean(v_adj), v_adj))


def stay_awake(on=True):
    """Windows must not sleep under a week-long run."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(
            0x80000000 | (0x00000001 if on else 0))
    except Exception:                                     # noqa: BLE001
        pass


# ===================================================================
#  diploma: RRC-64-40 for a single final candidate
# ===================================================================
#  256 streams (T x C x rotation 0..63), 1 TB each. Stream checkpoint:
#  every finished stream lands in diploma40_<name>_ckpt.jsonl and
#  survives restarts. Danger first: C=0 before C=1, gauntlet rotations
#  up front. One FAIL aborts the run (255 more TB would be waste).

def diploma_streams_ordered():
    gauntlet_r = [16, 0, 32, 8, 24, 40, 48, 56]
    rest_r = [r for r in range(64) if r not in gauntlet_r]
    order = gauntlet_r + rest_r
    s = []
    for C in (0, 1):
        for r in order:
            for T in (1, 0):
                s.append((T, C, r))
    return s


def diploma_label(mixer, T, C, r):
    if mixer.startswith("chain="):
        short = hashlib.md5(mixer.encode()).hexdigest()[:8]
        return f"chain{short}_T{T}C{C}r{r:02d}"
    return f"{mixer}_T{T}C{C}r{r:02d}"


def cmd_diploma(argv):
    if not argv:
        print("ladder.py diploma <mixer> [parallel|probe]")
        return 2
    mixer = argv[0]
    probe = "probe" in argv[1:]
    parallel = next((int(a) for a in argv[1:] if a.isdigit()), 10)
    name = ("chain" + hashlib.md5(mixer.encode()).hexdigest()[:8]
            if mixer.startswith("chain=") else mixer)
    if probe:
        name += "_probe"      # never touch the real run's checkpoint
    CKPT = HERE / f"diploma40_{name}_ckpt.jsonl"
    RESULT = HERE / f"diploma40_{name}_result.json"
    DONE = HERE / f"diploma40_{name}_done.txt"
    tlmax = "1GB" if probe else "1TB"
    timeout_s = 600 if probe else 26 * 3600

    t0 = time.time()
    stay_awake(True)

    #: anchor --
    if not court_of_record(candidate=mixer, candidate_name=name,
                           low_tlmax="64MB", feeder=FEEDER_EXE):
        return 2

    #: resume --
    done = {}
    if CKPT.exists():
        for line in CKPT.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done[r["label"]] = r["verdict"]
            except (json.JSONDecodeError, KeyError):
                continue
    all_streams = diploma_streams_ordered()
    if probe:
        all_streams = all_streams[:4]
    pending = [(mixer, T, C, r) for (T, C, r) in all_streams
               if diploma_label(mixer, T, C, r) not in done]
    print(f"DIPLOMA RRC-64-{'30(PROBE)' if probe else '40'}  {name}: "
          f"{len(all_streams)} streams x {tlmax}, {len(done)} already "
          f"recorded, {len(pending)} pending, parallel {parallel}.",
          flush=True)

    ck = open(CKPT, "a", encoding="utf-8")
    state = {"n": len(done)}

    def on_done(lbl, v):
        if "ABORTED" in v:
            print(f"  not recorded (ABORTED): {lbl}", flush=True)
            return True
        ck.write(json.dumps({"label": lbl, "verdict": v,
                             "sec": round(time.time() - t0)}) + "\n")
        ck.flush()
        done[lbl] = v
        state["n"] += 1
        print(f"  [{state['n']:>3}/{len(all_streams)}] {lbl}: {v}  "
              f"({(time.time() - t0) / 3600:.1f} h)", flush=True)
        if "FAIL" in v:
            print(f"\n*** DIPLOMA FAILED: {lbl} -> {v} ***\n",
                  flush=True)
            return False
        return True

    run(pending, tlmax=tlmax, parallel=parallel, timeout_s=timeout_s,
        feeder=FEEDER_EXE, quiet=True, on_done=on_done)
    ck.close()

    fails = {l: v for l, v in done.items() if "FAIL" in v}
    n_susp = sum(int(m.group(1)) for v in done.values()
                 for m in [re.search(r"\((\d+)x suspicious\)", v)] if m)

    # A stream that stopped short is not a stream that passed. "clean to
    # 2^33" from a run that died early carries no FAIL, gets recorded, and
    # counts towards len(done), so without this check the diploma reads
    # PASSED for a distance nobody ran. Counting is not measuring.
    goal = target_pow(tlmax)

    def _went_the_distance(v):
        m = re.match(r"clean to 2\^(\d+)", v)
        return bool(m) and int(m.group(1)) >= goal

    short = {l: v for l, v in done.items() if not _went_the_distance(v)}
    complete = (len(done) == len(all_streams) and not fails and not short)
    verdict_text = ("PASSED" if complete else
                    "FAILED" if fails else "INCOMPLETE")
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump({
            "provenance": provenance("diploma"),
            "candidate": name, "mixer": mixer,
                   "protocol": f"{len(all_streams)} streams x "
                               f"{tlmax}, -tf 2",
                   "verdict": verdict_text, "recorded": len(done),
                   "fails": fails, "short_of_target": short,
                   "target": f"2^{goal}", "suspicious_total": n_susp,
                   # t0 is this process. A resumed campaign pairs a
                   # whole-campaign stream count with one segment's
                   # clock, which is how the meer10 diploma came to
                   # publish 39.5 h for a run that spanned days.
                   "hours_this_segment": round((time.time() - t0) / 3600, 1),
                   "as_of": time.strftime("%Y-%m-%d %H:%M:%S")},
                  f, indent=1)
    print(f"\nDIPLOMA {name}: {verdict_text}  ({len(done)}/"
          f"{len(all_streams)} recorded, {len(fails)} FAIL, "
          f"{n_susp}x suspicious)", flush=True)
    stay_awake(False)
    if verdict_text == "INCOMPLETE":
        return 3          # no marker: bat restarts (resume)
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(f"{verdict_text}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return 0 if complete else 1


# ===================================================================
#  depth: 2^34 pre-stage for the diploma (64 streams x 16 GB)
# ===================================================================

DEPTH_CANDIDATES = [
    ("k10_mf_xsh_mf",
     "K10, hash class, skeleton 8-10-8 (spectrum hash gen<=60)",
     "chain=8:5846dfed2f0e1d49,10:706,8:781f94b96e8edb3b"),
    ("k12_hybrid",
     "K12, bijective, skeleton 10-1-10-1-0 (search-engine checkpoint)",
     "chain=10:5f3,1:3c79ac492ba7b653,10:d62,1:9e6d62d06f6a9a9b,0:1b"),
]


def depth_check_candidate(chain, streams, tlmax, parallel, timeout_s):
    full_streams = [(chain, T, C, r) for (T, C, r) in streams]
    labels = run(full_streams, tlmax=tlmax, parallel=parallel,
                 timeout_s=timeout_s, feeder=FEEDER_EXE)
    u = {}
    rerun = []
    for lbl, stream in zip(labels, full_streams):
        u[lbl] = verdict(lbl)
        if "ABORTED" in u[lbl]:
            rerun.append((lbl, stream))
    if rerun:
        print(f"  {len(rerun)} stalled: re-running ...", flush=True)
        run([s for _, s in rerun], tlmax=tlmax,
            parallel=max(2, parallel // 2), timeout_s=timeout_s * 2,
            feeder=FEEDER_EXE)
        for lbl, _ in rerun:
            u[lbl] = verdict(lbl)
    return labels, u


def cmd_depth(argv):
    probe = "probe" in argv
    path = next((a for a in argv if a.endswith(".json")), None)
    candidates = DEPTH_CANDIDATES
    OUTPUT = os.path.join(str(HERE), "depth_234_result.json")
    DONE = os.path.join(str(HERE), "depth_234_done.txt")
    if path:
        with open(path, encoding="utf-8") as f:
            candidates = [(k["name"], k.get("note", ""), k["chain"])
                          for k in json.load(f)]
    if probe:
        streams = [(T, C, r) for (T, C) in ((0, 0), (1, 1))
                   for r in range(0, 64, 16)]
        tlmax, parallel, timeout_s = "64MB", 4, 300
    else:
        streams = [(T, C, r) for (T, C) in ((0, 0), (1, 0), (0, 1), (1, 1))
                   for r in range(0, 64, 4)]
        tlmax, parallel, timeout_s = "16GB", 8, 2400

    t0 = time.time()
    stay_awake(True)
    print(f"DEPTH TEST  ({'PROBE' if probe else 'full'}: "
          f"{len(streams)} streams x {tlmax} per candidate)", flush=True)

    if not court_of_record(low_tlmax="64MB", feeder=FEEDER_EXE):
        # A detached run's watcher only sees the marker, not the console.
        with open(DONE, "w", encoding="utf-8") as f:
            f.write(f"rc=1  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        return 1

    result = {"protocol": f"{len(streams)} streams x {tlmax}, -tf 2",
              "start": time.strftime("%Y-%m-%d %H:%M:%S"), "candidates": {}}
    rc = 0
    print(f"{len(candidates)} candidates.", flush=True)
    for name, note, chain in candidates:
        print(f"\n== {name}  {chain}  ({note}) ==", flush=True)
        t1 = time.time()
        labels, u = depth_check_candidate(chain, streams, tlmax, parallel,
                                          timeout_s)
        fails = {l: t for l, t in u.items() if "FAIL" in t}
        # Count the clean ones, never infer them by subtraction: a
        # NOT MEASURED stream is in neither set and used to fall into
        # 'clean' by arithmetic alone.
        aborts = {l: t for l, t in u.items()
                  if not is_clean(t) and "FAIL" not in t}
        clean = sum(1 for t in u.values() if is_clean(t))
        verdict_text = ("PASSED" if clean == len(u)
                        else "FAILED" if fails else "INCOMPLETE")
        if verdict_text != "PASSED":
            rc = 1
        print(f"-> {verdict_text}: {clean}/{len(u)} clean, "
              f"{len(fails)} FAIL, {len(aborts)} ABORTED "
              f"({time.time()-t1:.0f} s)", flush=True)
        for l, t in sorted(fails.items()):
            print(f"     {l}: {t}", flush=True)
        result["candidates"][name] = {
            "chain": chain, "note": note, "verdict": verdict_text,
            "clean": clean, "streams": len(u),
            "fails": fails, "aborts": list(aborts),
            "sec": round(time.time() - t1)}
        with open(OUTPUT, "w", encoding="utf-8") as f:
            result["provenance"] = provenance("depth")
            json.dump(result, f, indent=1)

    stay_awake(False)
    print(f"\nDONE after {(time.time()-t0)/60:.0f} min -> {OUTPUT}",
          flush=True)
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(f"rc={rc}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return rc


# ===================================================================
#  gauntlet: the deep filter for the K10..K15 region
# ===================================================================
#  Ten streams that demonstrably execute in depth (from the rig's own
#  measurements: bswap family 23/23, lu9 2^38, mfa9 2^39). Necessary,
#  not sufficient: whoever falls here falls in the diploma for certain;
#  whoever passes is a contender, no more.

DEEP_GAUNTLET = [
    (0, 0, 40),   # lu9 (2^38), mfa9 (2^39)
    (1, 0, 2),    # lu9 (2^38)
    (0, 0, 0),    # 23/23 of the bswap family
    (0, 0, 32),   # 23/23
    (0, 0, 36),   # 23/23
    (0, 0, 44),   # 23/23
    (0, 0, 52),   # 23/23
    (0, 0, 56),   # 23/23
    (0, 0, 60),   # 23/23
    (0, 0, 48),   # 22/23
]
GAUNTLET_STAGES = {36: "64GB", 38: "256GB"}


def gauntlet_check_candidate(mixer, tlmax, parallel, timeout_s):
    labels = run([(mixer, T, C, r) for (T, C, r) in DEEP_GAUNTLET],
                 tlmax=tlmax, parallel=parallel, timeout_s=timeout_s,
                 feeder=FEEDER)
    verdicts = {l: verdict(l) for l in labels}
    fails = {l: v for l, v in verdicts.items() if "FAIL" in v}
    # Not fallen is not the same as held: ABORTED and NOT MEASURED are
    # holes in the measurement, and a hole never counts as a pass.
    aborts = [l for l, v in verdicts.items()
              if not is_clean(v) and "FAIL" not in v]
    verdict_text = ("CONTENDER" if not fails and not aborts else
                    "FALLEN" if fails else "INCOMPLETE")
    return verdict_text, verdicts, fails, aborts


def cmd_gauntlet(argv):
    if not argv:
        print("ladder.py gauntlet <mixer|chain=...|candidates.json> "
              "[36|38] [probe]")
        return 2
    target = argv[0]
    stage = next((int(a) for a in argv[1:] if a in ("36", "38")), 36)
    probe = "probe" in argv[1:]
    tlmax = "1GB" if probe else GAUNTLET_STAGES[stage]
    timeout_s = 900 if probe else 20 * 3600
    parallel = min(10, len(DEEP_GAUNTLET))

    candidates = []
    if target.endswith(".json"):
        with open(target, encoding="utf-8") as f:
            candidates = [(k["name"], k["chain"]) for k in json.load(f)]
    else:
        candidates = [(target.replace("chain=", "c_")[:24], target)]

    RESULT = HERE / f"depth_gauntlet{stage}_result.json"
    DONE = HERE / f"depth_gauntlet{stage}_done.txt"
    t0 = time.time()
    stay_awake(True)

    if not court_of_record(low_rot=40, low_tlmax="64MB", feeder=FEEDER):
        return 1

    print(f"DEPTH GAUNTLET stage {stage} ({tlmax} per stream, "
          f"{len(DEEP_GAUNTLET)} streams, {len(candidates)} candidates)",
          flush=True)

    result, rc = {}, 0
    for name, mixer in candidates:
        t1 = time.time()
        verdict_text, verdicts, fails, aborts = gauntlet_check_candidate(
            mixer, tlmax, parallel, timeout_s)
        print(f"\n== {name}: {verdict_text} "
              f"({len(verdicts) - len(fails) - len(aborts)}/"
              f"{len(verdicts)} clean, {(time.time()-t1)/3600:.1f} h) ==",
              flush=True)
        for l, v in sorted(fails.items()):
            print(f"     {l}: {v}", flush=True)
        result[name] = {"mixer": mixer, "verdict": verdict_text,
                        "clean": len(verdicts) - len(fails) - len(aborts),
                        "streams": len(verdicts), "fails": fails,
                        "aborts": aborts,
                        "hours": round((time.time() - t1) / 3600, 2)}
        if verdict_text != "CONTENDER":
            rc = 1
        with open(RESULT, "w", encoding="utf-8") as f:
            json.dump({
                "provenance": provenance("gauntlet"),
                "stage": stage, "tlmax": tlmax,
                       "streams": [f"T{T}C{C}r{r:02d}"
                                   for (T, C, r) in DEEP_GAUNTLET],
                       "candidates": result,
                       "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, indent=1)

    contenders = [n for n, e in result.items()
                  if e["verdict"] == "CONTENDER"]
    print(f"\nDONE after {(time.time()-t0)/3600:.1f} h: "
          f"{len(contenders)} contenders of {len(candidates)}", flush=True)
    if contenders:
        print("  " + ", ".join(contenders), flush=True)
        print("  -> contender means: holds 10 deep streams. The diploma "
              "checks 256.", flush=True)
    stay_awake(False)
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(f"{len(contenders)}/{len(candidates)} contenders  "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return rc


# ===================================================================
#  anchor: may the rig judge at 2^38 at all?
# ===================================================================

ANCHOR_RUNS = [
    ("nasam", 0, 0, 40, "holds"),
    ("nasam", 1, 0, 2, "holds"),
    ("mfa9", 0, 0, 40, "pending"),
    ("mix13", 0, 0, 40, "fails"),
]


def cmd_anchor(argv):
    probe = bool(argv) and argv[0] == "probe"
    RESULT = HERE / "depth_anchor_result.json"
    DONE = HERE / "depth_anchor_done.txt"
    tlmax = "1GB" if probe else "1TB"
    timeout_s = 900 if probe else 26 * 3600
    t0 = time.time()
    stay_awake(True)

    print(f"DEPTH ANCHOR ({tlmax} per stream, {len(ANCHOR_RUNS)} runs "
          "parallel)", flush=True)
    for m, T, C, r, e in ANCHOR_RUNS:
        print(f"  {m:<6} T{T}C{C}r{r:02d}  expected: {e}", flush=True)

    labels = run([(m, T, C, r) for (m, T, C, r, _) in ANCHOR_RUNS],
                 tlmax=tlmax, parallel=len(ANCHOR_RUNS),
                 timeout_s=timeout_s, feeder=FEEDER_EXE)

    data, violated = {}, []
    for (m, T, C, r, expect), lbl in zip(ANCHOR_RUNS, labels):
        v = verdict(lbl)
        fails = "FAIL" in v
        # NOT MEASURED must count as aborted here too, otherwise a silent
        # PractRand makes an "expected to hold" anchor read as satisfied.
        aborted = not is_clean(v) and not fails
        ok = (expect == "pending" or aborted is False and
              ((expect == "fails") == fails))
        if aborted:
            ok = False
        data[lbl] = {"mixer": m, "stream": f"T{T}C{C}r{r:02d}",
                     "expected": expect, "verdict": v, "as_expected": ok}
        if not ok and expect != "pending":
            violated.append(lbl)
        print(f"  {lbl:<20} {v:<40} expected {expect}: "
              f"{'OK' if ok else 'VIOLATED'}", flush=True)

    depth = "2^30 (PROBE, no depth proof)" if probe else "2^38+"
    conclusion = (
        f"ANCHOR VIOLATED: measurement path at {depth} unproven"
        if violated else
        f"ANCHOR HOLDS to {depth}: the rig judges correctly there"
        + ("" if probe else ", the mfx9 crack is real"))
    print(f"\n{conclusion}  ({(time.time()-t0)/3600:.1f} h)", flush=True)
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump({
            "provenance": provenance("anchor"),
            "tlmax": tlmax, "conclusion": conclusion, "runs": data,
                   # t0 is this process. A resumed campaign pairs a
                   # whole-campaign stream count with one segment's
                   # clock, which is how the meer10 diploma came to
                   # publish 39.5 h for a run that spanned days.
                   "hours_this_segment": round((time.time() - t0) / 3600, 1),
                   "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}, f,
                  indent=1)
    stay_awake(False)
    rc = 1 if violated else 0
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(f"rc={rc}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return rc


# ===================================================================
#  exhaust: enumerate the K9 three-op chain COMPLETELY
# ===================================================================

EXHAUST_SMOKE_CAP = 80
EXHAUST_END_STAGES = {"pregate_dead", "s1_dead", "smoke_dead", "PASSER",
                      "UNCLEAR"}


def exhaust_space():
    """Yields (fam, x_name, c1, c2, ops) for the whole K9 space."""
    pairs = [(c1, c2) for c1 in CONST_POOL for c2 in CONST_POOL]
    x_short = [("bswap", 11, 0), ("not", 13, 0)]
    x_rot = [(f"rot{k}", 2, k) for k in range(1, 64)]
    x_const = ([(f"^{c:x}", 6, c) for c in CONST_POOL]
               + [(f"+{c:x}", 7, c) for c in CONST_POOL])
    for x_name, xt, xp in x_short + x_const + x_rot:
        for c1, c2 in pairs:
            yield ("A", x_name, c1, c2,
                   [(8, c1), (xt, xp), (8, c2)])
    for x_name, xt, xp in x_short + x_rot:
        for c1, c2 in pairs:
            yield ("B", x_name, c1, c2,
                   [(xt, xp), (8, c1), (8, c2)])
    c_probe_x = [("bswap", 11, 0), ("not", 13, 0), ("rot32", 2, 32),
                 (f"^{GAM:x}", 6, GAM)]
    c_pairs = [(0x781f94b96e8edb3b, 0xb853d68343f7525b),
               (GAM, 0x781f94b96e8edb3b),
               (0xff51afd7ed558ccd, 0xc4ceb9fe1a85ec53)]
    for x_name, xt, xp in c_probe_x:
        for c1, c2 in c_pairs:
            yield ("C-probe", x_name, c1, c2,
                   [(8, c1), (8, c2), (xt, xp)])


def cmd_exhaust(argv):
    probe = bool(argv) and argv[0] == "probe"
    LOG = os.path.join(str(HERE), "exhaust_k9_evals.jsonl")
    OUTPUT = os.path.join(str(HERE), "exhaust_k9_result.json")
    DONE = os.path.join(str(HERE), "exhaust_k9_done.txt")
    t0 = time.time()
    stay_awake(True)
    log = open(LOG, "a", encoding="utf-8")
    seen = {}
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            try:
                r = json.loads(line)
                seen[r["chain"]] = r
            except (json.JSONDecodeError, KeyError):
                continue

    all_chains = list(exhaust_space())
    if probe:
        all_chains = all_chains[:40]

    def write_log(entry):
        log.write(json.dumps(entry) + "\n")
        log.flush()
        seen[entry["chain"]] = entry

    def _marker(rc):
        # The original wrapper appended an rc line for every non-probe
        # exit; the runner bat depends on the marker, not the console.
        if not probe:
            with open(DONE, "a", encoding="utf-8") as f:
                f.write(f"rc={rc}  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    #: anchor --
    if not court_of_record(low_tlmax="32MB", feeder=FEEDER_EXE):
        _marker(1)
        return 1

    #: work list --
    pending, smoke_direct = [], []
    for entry in all_chains:
        k = chain_str(entry[4])
        stage = seen.get(k, {}).get("stage")
        if stage in EXHAUST_END_STAGES:
            continue
        if stage == "smoke_pending":
            smoke_direct.append(entry)
        else:                              # new or s1_pending
            pending.append(entry)
    print(f"EXHAUSTION K9  ({len(all_chains)} chains total, "
          f"{len(all_chains) - len(pending) - len(smoke_direct)} done, "
          f"{len(pending)} before S1, {len(smoke_direct)} before smoke"
          f"{', PROBE' if probe else ''})", flush=True)

    n_smoke = sum(1 for r in seen.values()
                  if r.get("stage") in ("smoke_dead", "PASSER"))
    passer = [r for r in seen.values() if r.get("stage") == "PASSER"]
    unclear = []

    def check_smoke(f, x, c1, c2, ops):
        nonlocal n_smoke
        k = chain_str(ops)
        labels = run([(k, T, C, r) for (T, C, r) in SMOKE_TCR],
                     tlmax="2GB", parallel=PAR, timeout_s=240,
                     feeder=FEEDER_EXE)
        exps = [fail_exp(l) for l in labels]
        n_ok = sum(1 for e in exps if e is None)
        n_ab = sum(1 for e in exps if e == "ABORTED")
        stage = ("PASSER" if n_ok == 32
                 else "UNCLEAR" if n_ab else "smoke_dead")
        ff = min((e for e in exps if isinstance(e, int)), default=None)
        entry = {"chain": k, "fam": f, "x": x, "c1": f"{c1:x}",
                 "c2": f"{c2:x}", "stage": stage, "first_fail": ff,
                 "smoke": n_ok}
        write_log(entry)
        n_smoke += 1
        if stage == "PASSER":
            passer.append(entry)
            print(f"\n*** NOVEL K9: full smoke! {f} X={x} "
                  f"c1={c1:x} c2={c2:x}  {k} ***\n", flush=True)
        elif stage == "UNCLEAR":
            unclear.append(entry)
        else:
            print(f"  smoke {f}/{x}/{c1:x}/{c2:x}: {n_ok}/32 "
                  f"(first_fail 2^{ff})", flush=True)
        return stage

    for f, x, c1, c2, ops in smoke_direct:
        if n_smoke > EXHAUST_SMOKE_CAP:
            break
        check_smoke(f, x, c1, c2, ops)

    BATCH = 25
    for start in range(0, len(pending), BATCH):
        if n_smoke > EXHAUST_SMOKE_CAP:
            print(f"SMOKE CAP breached ({n_smoke} > {EXHAUST_SMOKE_CAP}) "
                  "-- stop and look at the situation.", flush=True)
            with open(DONE, "w", encoding="utf-8") as fm:
                fm.write(f"rc=2 CAP  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            _marker(2)          # the wrapper's rc line, as the original had
            return 2
        batch = pending[start:start + BATCH]
        streams = [(chain_str(ops), T, C, r)
                   for (_, _, _, _, ops) in batch for (T, C, r) in GAUNTLET]
        # 120 s, not 900: a 256 MB stream needs about 1.2 s at this
        # parallelism (measured 29.08., 12 streams x 32 MB in 1.79 s under
        # load), so this is still a hundredfold margin. At 900 s the
        # gauntlet watchdog alone ate 46 % of all slot capacity in the K5
        # run: 83 stalled streams x 900 s, because run() is a barrier
        # and every batch waited out its slowest member. A killed stream
        # is never recorded as clean; it is reported as UNCLEAR.
        # Same barrier reasoning as in cmd_cost (see there).
        labels = run(streams, tlmax="256MB", parallel=PAR, timeout_s=120,
                     feeder=FEEDER_EXE)
        for i, (f, x, c1, c2, ops) in enumerate(batch):
            exps = [fail_exp(l) for l in labels[4 * i:4 * i + 4]]
            k = chain_str(ops)
            if any(isinstance(e, int) for e in exps):
                write_log({"chain": k, "fam": f, "x": x, "c1": f"{c1:x}",
                           "c2": f"{c2:x}", "stage": "s1_dead",
                           "first_fail": min(e for e in exps
                                             if isinstance(e, int))})
            elif "ABORTED" in exps:
                e = {"chain": k, "fam": f, "x": x, "c1": f"{c1:x}",
                     "c2": f"{c2:x}", "stage": "UNCLEAR", "first_fail": None}
                write_log(e)
                unclear.append(e)
            else:
                write_log({"chain": k, "fam": f, "x": x, "c1": f"{c1:x}",
                           "c2": f"{c2:x}", "stage": "smoke_pending",
                           "first_fail": None})
                check_smoke(f, x, c1, c2, ops)
        done_n = sum(1 for r in seen.values()
                     if r.get("stage") in EXHAUST_END_STAGES)
        print(f"  S1 {min(start + BATCH, len(pending))}/{len(pending)}  "
              f"done {done_n}/{len(all_chains)}  smokes {n_smoke}  "
              f"passers {len(passer)}  ({time.time() - t0:.0f} s)",
              flush=True)

    counts = {}
    for r in seen.values():
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    result = {
        "space": len(all_chains), "evaluated": len(seen), "stages": counts,
        "passer": passer, "unclear": [u["chain"] for u in unclear],
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "minutes": round((time.time() - t0) / 60),
    }
    with open(OUTPUT, "w", encoding="utf-8") as fj:
        result["provenance"] = provenance("exhaust")
        json.dump(result, fj, indent=1)
    print(f"\nEXHAUSTION {'(PROBE) ' if probe else ''}DONE "
          f"after {result['minutes']} min: {counts}", flush=True)
    if passer:
        for p in passer:
            print(f"  PASSER: {p['fam']} X={p['x']} c1={p['c1']} "
                  f"c2={p['c2']}  {p['chain']}", flush=True)
    else:
        print("  No passer: the K9 three-op chain over the pool is "
              "EMPTY (enumerated, not merely visited).", flush=True)
    log.close()
    stay_awake(False)
    if not probe:
        with open(DONE, "a", encoding="utf-8") as f:
            f.write(f"rc=0  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return 0


# ===================================================================
#  cost: enumeration of a whole cost class K
# ===================================================================

COST_OPS = {
    0:  (2, "shift"),   # ^>>k
    1:  (3, "const"),   # *c
    2:  (1, "shift"),   # rot k
    3:  (2, "shift"),   # ^<<k
    5:  (2, "shift"),   # +<<k
    6:  (1, "const"),   # ^c
    7:  (1, "const"),   # +c
    8:  (4, "const"),   # mulfold c
    9:  (3, "double"),  # xrot2 (a,b)
    10: (2, "double"),  # xsh2 (a,b)
    11: (1, "fix"),     # bswap
    13: (1, "fix"),     # not
}
COST_MULT = (1, 8)                 # nonlinear
COST_PERM = (2, 11, 13)            # pure permutations (end ban)
COST_SELF_INVERSE = (11, 13)
SHIFT_GRID = [5, 8, 11, 14, 17, 20, 23, 26, 27, 29, 30, 31, 32, 33,
              35, 38, 41, 44, 47, 50, 53, 56, 59]
COST_LMAX = 6
COST_ASSIGN_CAP = 400
COST_SMOKE_CAP = 60


def cost_skeletons(K, lmax=COST_LMAX):
    """All op-type sequences with cost sum exactly K. Complete."""
    types = sorted(COST_OPS)
    out = []
    for length in range(1, lmax + 1):
        for seq in itertools.product(types, repeat=length):
            if sum(COST_OPS[t][0] for t in seq) != K:
                continue
            if not any(t in COST_MULT for t in seq):
                continue                       # linear: cannot mix
            if seq[-1] in COST_PERM:
                continue                       # end ban (evidenced)
            if any(seq[i] == seq[i + 1] and seq[i] in COST_SELF_INVERSE
                   for i in range(length - 1)):
                continue                       # cancels itself out
            out.append(seq)
    return out


def cost_assignments(seq, rng, cap):
    """All (or drawn) parameter assignments of one skeleton."""
    axes = []
    for t in seq:
        kind = COST_OPS[t][1]
        if kind == "const":
            axes.append([(t, c) for c in CONST_POOL])
        elif kind == "shift":
            axes.append([(t, s) for s in SHIFT_GRID])
        elif kind == "double":
            pairs = [(a, b) for i, a in enumerate(SHIFT_GRID)
                     for b in SHIFT_GRID[i + 1:]]
            axes.append([(t, (a << 6) | b) for a, b in pairs])
        else:
            axes.append([(t, 0)])
    total = 1
    for a in axes:
        total *= len(a)
    if total <= cap:
        return list(itertools.product(*axes)), True
    drawn = set()
    while len(drawn) < cap:
        drawn.add(tuple(rng.choice(a) for a in axes))
    return list(drawn), False


def cmd_cost(argv):
    if not argv or not argv[0].isdigit():
        print("ladder.py cost <K> [skeletons|probe|pregate|lmax=N|cap=N]")
        return 2
    K = int(argv[0])
    only_skeletons = "skeletons" in argv[1:]
    probe = "probe" in argv[1:]
    pregate = "pregate" in argv[1:]
    lmax = next((int(a.split("=")[1]) for a in argv[1:]
                 if a.startswith("lmax=")), COST_LMAX)
    cap = next((int(a.split("=")[1]) for a in argv[1:]
                if a.startswith("cap=")), COST_ASSIGN_CAP)

    # One folder per cost class, holding everything the run produces:
    # stream logs, anchor runs, evals and result together. See
    # use_campaign() for what a shared bucket cost on 29.08.
    tag = f"k{K}" + (f"_l{lmax}" if lmax != COST_LMAX else "")
    camp = use_campaign(tag)
    LOG = os.path.join(str(camp), "evals.jsonl")
    RESULT = os.path.join(str(camp), "result.json")
    DONE = os.path.join(str(camp), "done.txt")
    # The runner bat checks results/k<K>/done.txt and cannot know the
    # lmax tag: without the plain marker it restarted a finished
    # non-default run until its attempt limit.
    DONE_PLAIN = os.path.join(str(HERE), "results", f"k{K}", "done.txt")
    os.makedirs(os.path.dirname(DONE_PLAIN), exist_ok=True)

    sk = cost_skeletons(K, lmax)
    rng = random.Random(0x44 * 1000 + K)
    plan, complete_sk, sampled_sk = [], 0, 0
    for seq in sk:
        chains, complete = cost_assignments(seq, rng, cap)
        complete_sk += 1 if complete else 0
        sampled_sk += 0 if complete else 1
        for ops in chains:
            plan.append((seq, list(ops), complete))

    print(f"COST CLASS K{K}: {len(sk)} skeletons, {len(plan)} chains "
          f"({complete_sk} skeletons complete, {sampled_sk} as a sample "
          f"of {cap} each)", flush=True)
    if only_skeletons:
        for seq in sk:
            n, v = cost_assignments(seq, rng, cap)
            print(f"  {str(seq):<28} {len(n):>5} assignments "
                  f"{'complete' if v else 'SAMPLE'}", flush=True)
        return 0
    if probe:
        plan = plan[:20]

    t0 = time.time()
    stay_awake(True)

    #: anchor --
    if not court_of_record(low_tlmax="32MB", feeder=FEEDER_EXE):
        return 1

    seen = {}
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            try:
                r = json.loads(line)
                seen[r["chain"]] = r
            except (json.JSONDecodeError, KeyError):
                continue
    log = open(LOG, "a", encoding="utf-8")
    pending = [(s, o, c) for (s, o, c) in plan
               if chain_str(o) not in seen]
    print(f"{len(seen)} already evaluated, {len(pending)} pending.",
          flush=True)

    passer, state = [], {"n_smoke": 0}

    def smoke(seq, ops, complete):
        k = chain_str(ops)
        labels = run([(k, T, C, r) for (T, C, r) in SMOKE_TCR],
                     tlmax="2GB", parallel=PAR, timeout_s=240,
                     feeder=FEEDER_EXE)
        exps = [fail_exp(l) for l in labels]
        n_ok = sum(1 for e in exps if e is None)
        n_ab = sum(1 for e in exps if e == "ABORTED")
        stage = ("PASSER" if n_ok == 32 else
                 "UNCLEAR" if n_ab else "smoke_dead")
        ff = min((e for e in exps if isinstance(e, int)), default=None)
        e = {"chain": k, "skeleton": list(seq), "stage": stage,
             "smoke": n_ok, "first_fail": ff, "complete": complete}
        log.write(json.dumps(e) + "\n"); log.flush()
        seen[k] = e
        state["n_smoke"] += 1
        if stage == "PASSER":
            passer.append(e)
            print(f"\n*** K{K} PASSER: {k}  (skeleton {seq}) ***\n",
                  flush=True)
        else:
            print(f"  smoke {k}: {n_ok}/32", flush=True)

    # BATCH and the pregate watchdog together decide the wall clock, and on
    # 29.08. they cost a K5 run eight days it did not need. run() is a
    # barrier: it returns only when every stream in the batch is finished.
    # About one in twenty feeder/RNG_test pairs stalls (known since 17.08.,
    # root cause open), so with BATCH=25 nearly every batch contained one
    # stall, and the whole batch then waited out the full watchdog while
    # eleven of twelve slots stood empty. The symptom was a CPU at 54 C:
    # the machine was not computing, it was waiting.
    #
    # 91,000 chains at BATCH=25 and 300 s is up to 12 days of pure waiting.
    # At BATCH=200 and 30 s it is under four hours. A 32 MB pregate stream
    # takes one to two seconds, so 30 s is still a fifteenfold margin.
    #
    # Shortening the watchdog loses nothing: a pregate stream that gets
    # killed is not recorded as dead, it falls through to the gauntlet and
    # is measured there properly. A shorter timeout costs gauntlet runs,
    # never information.
    BATCH = 200
    for start in range(0, len(pending), BATCH):
        if state["n_smoke"] > COST_SMOKE_CAP:
            print(f"SMOKE CAP breached ({state['n_smoke']}), stopping.",
                  flush=True)
            break
        batch = pending[start:start + BATCH]
        if pregate:
            pg = run([(chain_str(o), 0, 0, 0) for (_, o, _) in batch],
                     tlmax="32MB", parallel=PAR, timeout_s=30,
                     feeder=FEEDER_EXE)
            survivors = []
            for (seq, ops, complete), lbl in zip(batch, pg):
                e = fail_exp(lbl)
                if isinstance(e, int):
                    r = {"chain": chain_str(ops), "skeleton": list(seq),
                         "stage": "pregate_dead", "first_fail": e,
                         "complete": complete}
                    log.write(json.dumps(r) + "\n"); log.flush()
                    seen[r["chain"]] = r
                else:
                    survivors.append((seq, ops, complete))
            print(f"    Pregate: {len(batch) - len(survivors)}/"
                  f"{len(batch)} dead", flush=True)
            batch = survivors
            if not batch:
                continue
        streams = [(chain_str(o), T, C, r)
                   for (_, o, _) in batch for (T, C, r) in GAUNTLET]
        # 120 s, not 900: a 256 MB stream needs about 1.2 s at this
        # parallelism (measured 29.08., 12 streams x 32 MB in 1.79 s while
        # the machine was already loaded), so this is a hundredfold margin.
        # At 900 s this one watchdog ate 46 % of all slot capacity in the
        # K5 run: 83 stalled streams x 900 s, because run() is a
        # barrier and every batch waited out its slowest member. The
        # symptom was a CPU at 54 C: not computing, waiting. A killed
        # stream is never recorded as clean; it comes back UNCLEAR.
        labels = run(streams, tlmax="256MB", parallel=PAR, timeout_s=120,
                     feeder=FEEDER_EXE)
        for i, (seq, ops, complete) in enumerate(batch):
            exps = [fail_exp(l) for l in labels[4 * i:4 * i + 4]]
            k = chain_str(ops)
            if any(isinstance(e, int) for e in exps):
                e = {"chain": k, "skeleton": list(seq),
                     "stage": "s1_dead",
                     "first_fail": min(x for x in exps
                                       if isinstance(x, int)),
                     "complete": complete}
                log.write(json.dumps(e) + "\n"); log.flush()
                seen[k] = e
            elif "ABORTED" in exps:
                e = {"chain": k, "skeleton": list(seq), "stage": "UNCLEAR",
                     "first_fail": None, "complete": complete}
                log.write(json.dumps(e) + "\n"); log.flush()
                seen[k] = e
            else:
                smoke(seq, ops, complete)
        print(f"  K{K}: {min(start + BATCH, len(pending))}/{len(pending)} "
              f"checked, {state['n_smoke']} smokes, {len(passer)} passers "
              f"({time.time() - t0:.0f} s)", flush=True)

    counts = {}
    for r in seen.values():
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump({
            "provenance": provenance("cost"),
            "K": K, "skeletons": len(sk), "chains_planned": len(plan),
                   "skeletons_complete": complete_sk,
                   "skeletons_sampled": sampled_sk,
                   "lmax": lmax, "assign_cap_used": cap,
                   "shift_grid": SHIFT_GRID, "assign_cap": cap,
                   "evaluated": len(seen), "stages": counts,
                   "passer": passer,
                   # See the note in cmd_diploma: this clock covers this
                   # process, not a resumed campaign.
                   "hours_this_segment": round((time.time() - t0) / 3600, 2),
                   "as_of": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
    print(f"\nK{K} DONE: {counts}, {len(passer)} passers "
          f"({(time.time()-t0)/3600:.1f} h)", flush=True)
    log.close()
    stay_awake(False)
    if probe:
        # A probe measures 20 chains of the class and then stops. Writing
        # the done marker here would tell the runner bat, which watches
        # nothing else, that a 91,000-chain campaign had finished, and
        # it would stop restarting a run that is 0.02 % done. A truncated
        # plan must never report the campaign complete.
        print("  (probe: no done marker: the campaign is not finished)",
              flush=True)
    else:
        for done_path in {DONE, DONE_PLAIN}:
            with open(done_path, "w", encoding="utf-8") as f:
                f.write(f"K{K} {len(passer)} passers  "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return 0


# ===================================================================
#  verify-wyhash: bit-identity before "wyhash" may enter the ladder
# ===================================================================
#  Reference in pure Python (exact integer arithmetic, independent of
#  the C compiler). Source: github.com/wangyi-fudan/wyhash, master.

WY_M = (1 << 64) - 1
WYP0, WYP1 = 0x2d358dccaa6c78a5, 0x8bb84b93962eacc9


def wymix(a, b):
    r = a * b
    return ((r & WY_M) ^ (r >> 64)) & WY_M


def wyrand_fin(x):
    """The mixing step of wyrand, read as a 64-bit finalizer (K5)."""
    return wymix(x, x ^ WYP1)


def wyhash8(x):
    """wyhash for exactly 8 input bytes, seed=0. Cost ~K10."""
    seed = 0
    seed ^= wymix(seed ^ WYP0, WYP1)
    a = ((x << 32) | (x >> 32)) & WY_M
    b = x
    a ^= WYP1
    b ^= seed
    r = a * b
    a, b = r & WY_M, (r >> 64) & WY_M
    return wymix(a ^ WYP0 ^ 8, b ^ WYP1)


def _feeder_values(feeder, mixer, n):
    """mix(counter) raw from the feeder (T=0, C=0, r=0)."""
    p = subprocess.Popen([str(feeder), mixer, "0", "0", "0"],
                         stdout=subprocess.PIPE)
    d = p.stdout.read(8 * n)
    p.kill()
    return list(struct.unpack(f"<{n}Q", d))


def _avalanche(f, n=4096):
    total = 0
    for i in range(n):
        h = f(i)
        for b in range(64):
            total += bin(h ^ f(i ^ (1 << b))).count("1")
    return total / (64.0 * 64.0 * n)


def cmd_verify_wyhash(argv):
    feeder = argv[0] if argv else str(FEEDER)
    n = 1 << 16
    errors = 0
    print(f"VERIFY WYHASH  ({os.path.basename(feeder)}, {n} values)")
    for name, ref in (("wyrand", wyrand_fin), ("wyhash8", wyhash8)):
        actual = _feeder_values(feeder, name, n)
        expected = [ref(i) for i in range(n)]
        diff = sum(1 for a, b in zip(actual, expected) if a != b)
        errors += diff
        print(f"  {name:<8} deviations: {diff}  -> "
              f"{'BIT-IDENTICAL' if diff == 0 else 'NOT BIT-IDENTICAL'}")
    # Context, not a gate: avalanche saturates and does not separate.
    print(f"  Avalanche wyrand  {_avalanche(wyrand_fin):.4f}   "
          f"(ideal 0.5000; measurable bias)")
    print(f"  Avalanche wyhash8 {_avalanche(wyhash8):.4f}")
    return 0 if errors == 0 else 1


# ===================================================================
#  wyhash-depth: does the original code hold where its pattern tears?
# ===================================================================

def cmd_wyhash_depth(argv):
    probe = bool(argv) and argv[0] == "probe"
    OUTPUT = HERE / "wyhash_depth_result.json"
    DONE = HERE / "wyhash_depth_done.txt"
    depth = "1GB" if probe else "1TB"
    t0 = time.time()
    stay_awake(True)

    if not court_of_record(low_rot=40, low_tlmax="64MB", feeder=FEEDER):
        # A detached run's watcher only sees the marker, not the console.
        with open(DONE, "w", encoding="utf-8") as f:
            f.write(f"rc=1  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        return 1

    print(f"WYHASH IN DEPTH  (wyhash8 {depth} on both tearing streams "
          f"+ wyrand follow-up)", flush=True)
    streams = [("wyhash8", 0, 0, 40), ("wyhash8", 1, 0, 2)]
    labels = run(streams, tlmax=depth, parallel=2, timeout_s=26 * 3600,
                 feeder=FEEDER)
    follow_up = run([("wyrand", 1, 0, 0)], tlmax="256MB", parallel=1,
                    timeout_s=3600, feeder=FEEDER)

    data = {}
    for l in labels + follow_up:
        data[l] = verdict(l)
        print(f"  {l:<22} {verdict(l)}", flush=True)

    holds = all(is_clean(v)
                for l, v in data.items() if l.startswith("wyhash8"))
    conclusion = ("wyhash8 HOLDS 1 TB where the pattern (K9) tears at 2^38"
                  if holds else
                  "wyhash8 falls as well: the weakness survives even the "
                  "full hash path")
    print(f"\n{conclusion}  ({(time.time()-t0)/3600:.1f} h)", flush=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({
            "provenance": provenance("wyhash-depth"),
            "tlmax": depth, "conclusion": conclusion, "runs": data,
                   # t0 is this process. A resumed campaign pairs a
                   # whole-campaign stream count with one segment's
                   # clock, which is how the meer10 diploma came to
                   # publish 39.5 h for a run that spanned days.
                   "hours_this_segment": round((time.time() - t0) / 3600, 1),
                   "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}, f,
                  indent=1)
    stay_awake(False)
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(f"rc=0  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return 0


# ===================================================================
#  dispatch: every legacy argument style survives verbatim
# ===================================================================

USAGE = """\
ladder.py: one file, every stage of the rig.

  ladder.py [tlmax]                      acid test (anchors, default 2GB)
  ladder.py smoke <mixer> [tlmax]        32-stream smoke test
  ladder.py trial [tlmax]                your mixer from mixer_user.h
  ladder.py diploma <mixer> [par|probe]  RRC-64-40, 256 streams x 1 TB
  ladder.py depth [probe] [cands.json]   2^34 pre-stage, 64 x 16 GB
  ladder.py gauntlet <target> [36|38]    10-stream deep filter
  ladder.py anchor [probe]               may the rig judge at 2^38?
  ladder.py exhaust [probe]              enumerate the K9 chain space
  ladder.py cost <K> [skeletons|...]     enumerate a whole cost class
  ladder.py verify-wyhash [feeder]       bit-identity check
  ladder.py wyhash-depth [probe]         original code on the 2^38 streams
"""

COMMANDS = {
    "diploma": cmd_diploma,
    "depth": cmd_depth,
    "gauntlet": cmd_gauntlet,
    "anchor": cmd_anchor,
    "exhaust": cmd_exhaust,
    "cost": cmd_cost,
    "verify-wyhash": cmd_verify_wyhash,
    "wyhash-depth": cmd_wyhash_depth,
}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(USAGE)
        sys.exit(0)
    if args and args[0] in COMMANDS:
        sys.exit(COMMANDS[args[0]](args[1:]))
    if args and args[0] == "trial":
        ok = trial(tlmax=args[1] if len(args) > 1 else "2GB")
        sys.exit(0 if ok else 1)
    if args and args[0] == "smoke":
        if len(args) < 2:
            print("ladder.py smoke <mixer> [tlmax]")
            sys.exit(2)
        mixer = args[1]
        tlmax = args[2] if len(args) > 2 else "2GB"
        streams, title = smoke_streams(mixer), f"RRC-SMOKE {mixer}"
    elif not args or re.fullmatch(r"\d+[KMGT]B", args[0], re.I):
        tlmax = args[0] if args else "2GB"
        streams = [t[:4] for t in ACID_TEST]
        title = "ACID TEST"
    else:
        print(f"unknown command: {args[0]}\n")
        print(USAGE)
        sys.exit(2)
    if not check_judge():
        sys.exit(2)
    if not FEEDER.is_file():
        print("feeder.exe is missing next to ladder.py. Build it first:")
        print("  g++ -O3 -march=native -std=gnu++14 feeder.cpp -o feeder.exe")
        sys.exit(2)
    # The bare run is what the README hands a stranger, and what the
    # anchoring section promises: nothing is measured until the rig has
    # shown, in the same run, that it can convict, acquit, decline and
    # cut. Until 31.08. it ran the two mixer weights only, while the
    # prose claimed all six, so the prose was true of the trial and of
    # the six measuring commands, and false of this one. Twenty-five
    # seconds is the honest price of making the sentence true.
    if title == "ACID TEST" and not hold_court():
        sys.exit(1)
    t0 = time.time()
    # Same width as the campaigns: PAR is where this machine stops
    # gaining, measured at three sizes. See the table next to PAR.
    labels = run(streams, tlmax=tlmax, parallel=PAR)
    print(f"\n{title} ({tlmax}, {time.time()-t0:.0f} s):")
    # A "must fall" anchor can only be read once the run is long enough for
    # the fall to be due. Evensen publishes mix13 dying between 2^16 and
    # 2^22, so below 2^22 a clean mix13 is not a violated anchor: it is a
    # run that stopped too early to say anything. Judging it either way
    # would be the same mistake in both directions: an unmeasured anchor
    # counted as passed, or counted as broken.
    long_enough = target_pow(tlmax, default=31) >= 22
    expected = ([t[4] for t in ACID_TEST]
                if title == "ACID TEST" and long_enough
                else [None] * len(labels))
    if title == "ACID TEST" and not long_enough:
        print(f"  (too short at {tlmax} to judge the anchors: mix13 is not "
              f"due to fall before 2^16 and may hold to 2^22.")
        print("   Run without an argument, or with 8MB or more, for a "
              "verdict.)")
    violated = []
    for label, must in zip(labels, expected):
        v = verdict(label)
        mark = ""
        if must == "fall":
            ok = "FAIL" in v
            mark = "   must fall  " + ("ok" if ok else "*** WRONG ***")
        elif must == "hold":
            ok = is_clean(v)
            mark = "   must hold  " + ("ok" if ok else "*** WRONG ***")
        else:
            ok = True
        if not ok:
            violated.append(f"{label}: {v}")
        print(f"  {label:<22} {v:<34}{mark}")
    if violated:
        print("\nANCHOR VIOLATED: this rig is not fit to judge:")
        for line in violated:
            print(f"  {line}")
        print("Nothing measured with it means anything until this is fixed.")
        sys.exit(1)
    if title == "ACID TEST" and long_enough:
        print("\nThe rig convicts the guilty and acquits the innocent.")
    elif title == "ACID TEST":
        # Exit 2, not 0. A run that judged nothing must not report success:
        # a caller reading the exit code would take it for anchors that held.
        print("\nNo verdict on the anchors: the run was too short to give "
              "one.")
        sys.exit(2)
