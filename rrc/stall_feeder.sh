#!/bin/sh
# stall_feeder.sh — never produces output at all.
#
# One half of THE MISTRIAL/THE SLEEPER pair: a feeder that writes
# nothing must be recorded as ABORTED, never as clean.
#
# exec matters. Without it this shell stays as a parent process, and
# _kill() would reap the shell while a python3 sleeps on for ten
# minutes, holding the pipe open. The anchor would then look like it
# fired while the machine fills with orphans.
exec python3 -c "import time; time.sleep(600)"
