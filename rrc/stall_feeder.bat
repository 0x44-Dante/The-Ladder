@echo off
REM 0x44 STALL FEEDER -- holds the pipe open and writes nothing, on purpose.
REM
REM This is the anchor for the stall detector: it reproduces the failure
REM mode of the nights of 17./18.08., where a feeder/RNG_test pair froze
REM at about 8 KB and produced no further output. A watchdog that has
REM never been shown to bite on this is a watchdog with untested teeth.
REM
REM Arguments are ignored; run() passes mixer/T/C/r and none of it matters.
python -c "import time; time.sleep(600)"
