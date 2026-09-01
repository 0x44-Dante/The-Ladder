@echo off
REM 0x44 COST CLASS 5 -- COMPLETE, on the published rig.
REM
REM Everything this run produces lands in results\k5\: the stream logs,
REM the anchor runs, evals.jsonl and result.json. One folder per campaign,
REM because a shared bucket does not survive an enumeration -- a full K5
REM writes over 100,000 stream logs, and mixed in with the diploma
REM evidence they made the directory unlistable on 29.08.
REM
REM cap=10000 lifts the assignment cap: the largest K5 skeleton has 7406
REM assignments, so at 10000 nothing is a sample any more. That makes it
REM 91,000 chains instead of the capped 16,718 -- and only then is
REM "cost class 5 exhausted" a sentence that holds.
cd /d "%~dp0"
set /a attempt=0
:loop
set /a attempt+=1
echo.
echo ============================================================
echo   COST CLASS K5 COMPLETE  attempt %attempt%   %date% %time%
echo ============================================================
python -u ladder.py cost 5 pregate cap=10000
if exist results\k5\done.txt goto done
if %attempt% geq 30 goto giveup
echo [!] ended without marker - retrying in 15 s ...
timeout /t 15 /nobreak >nul
goto loop
:giveup
echo.
echo [X] 30 attempts without a done marker - stopping.
goto out
:done
echo.
echo [OK] COST CLASS K5 finished.
type results\k5\done.txt
:out
