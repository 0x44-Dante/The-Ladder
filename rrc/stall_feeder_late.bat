@echo off
REM 0x44 LATE STALL FEEDER -- writes 16 KB, then freezes on purpose.
REM
REM The second anchor for the stall detector, and the one that matters.
REM stall_feeder.bat reproduces a stream that never starts; this one
REM reproduces the stall that actually happens. On the nights of
REM 17./18.08. the feeder/RNG_test pairs did not freeze before their
REM first checkpoint -- they froze at about 8 KB, four checkpoints in.
REM Measured again on 30.08. during a K5 run: 64 streams reached 2^13 in
REM 0.6 s and then wrote nothing for the remaining 119 seconds until the
REM timeout killed them, twice each. Counted afterwards over the whole
REM finished campaign: 1,337 of 92,091 stream logs carry the stall
REM abort, 72 the timeout. Those logs are published as
REM k5_campaign.tar.gz with release v1.0.
REM
REM The detector in place at the time asked only whether a FIRST
REM checkpoint had appeared, so it never fired on any of them -- the
REM check was built for the wrong shape of the very failure it was named
REM after. A watchdog is only proven by the case it is meant to catch,
REM and this is that case.
REM
REM The bytes are random so PractRand writes real checkpoints rather than
REM failing at once; all-zero data would be caught as a FAIL and would
REM prove nothing about stalling. Arguments are ignored.
python -c "import sys,os,time; sys.stdout.buffer.write(os.urandom(16384)); sys.stdout.buffer.flush(); time.sleep(600)"
