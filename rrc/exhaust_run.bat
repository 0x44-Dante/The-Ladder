@echo off
REM 0x44 EXHAUSTION RUN -- enumerate K9 triple chains exhaustively.
REM Auto-restart; resume comes from exhaust_k9_evals.jsonl.
cd /d "%~dp0"
del exhaust_k9_done.txt 2>nul
set /a attempt=0
:loop
set /a attempt+=1
echo.
echo ============================================================
echo   EXHAUSTION %attempt%   %date% %time%
echo ============================================================
python -u ladder.py exhaust > exhaust_k9.log 2>&1
if exist exhaust_k9_done.txt goto done
if %attempt% geq 30 goto abort
echo [!] Process ended WITHOUT marker - restart in 5 s ...
timeout /t 5 /nobreak >nul
goto loop
:done
echo.
echo === EXHAUSTION ENDED NORMALLY ===
type exhaust_k9_done.txt
echo Result: exhaust_k9_result.json
goto :eof
:abort
echo.
echo === 30 restarts reached - stop. Check exhaust_k9_evals.jsonl. ===
