#!/bin/sh
# stall_feeder_late.sh — writes 16 KB, then freezes on purpose.
#
# THE SLEEPER: a stream that starts healthy and then stops must be cut
# and recorded as ABORTED. The 16 KB matter — a feeder that never
# writes anything is a different failure (that is stall_feeder.sh),
# and the watchdog has to tell the two apart.
#
# exec matters. Without it this shell stays as a parent process, and
# _kill() would reap the shell while a python3 sleeps on for ten
# minutes, holding the pipe open. The anchor would then look like it
# fired while the machine fills with orphans.
exec python3 -c "import sys,os,time; sys.stdout.buffer.write(os.urandom(16384)); sys.stdout.buffer.flush(); time.sleep(600)"
