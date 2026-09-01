@echo off
REM 0x44 COST-CLASS RUN -- enumerate one cost class, with auto-restart.
REM Usage: class_run.bat <K> [pregate] [lmax=N] [cap=N]
REM
REM The marker and the log live in the campaign folder, results\k<K>\.
REM Until 31.08.2026 this file looked for class_k<K>_done.txt in rrc\,
REM a name ladder.py has never written: a finished run therefore read as
REM a crash and restarted a hundred times. The lesson is in the shape of
REM the bug -- a runner that checks for the wrong marker cannot tell
REM success from failure, and it fails towards "run it again".
cd /d "%~dp0"
set K=%1
if "%K%"=="" set K=5
set OPT=%2 %3 %4
set MARK=results\k%K%\done.txt
if not exist results\k%K% mkdir results\k%K%
set /a attempt=0
:loop
set /a attempt+=1
echo.
echo ============================================================
echo   COST CLASS K%K%  attempt %attempt%   %date% %time%
echo ============================================================
python -u ladder.py cost %K% %OPT% > results\k%K%\run.log 2>&1
if exist "%MARK%" goto done
if %attempt% geq 100 goto giveup
echo [!] ended without marker - restarting in 10 s ...
timeout /t 10 /nobreak >nul
goto loop
:done
echo === COST CLASS K%K% COMPLETE ===
type results\k%K%\result.json
goto :eof
:giveup
echo === 100 restarts reached - stopping. Check results\k%K%\evals.jsonl. ===
