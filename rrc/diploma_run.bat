@echo off
REM 0x44 DIPLOMA RUN -- RRC-64-40 with auto-restart and stream resume.
REM Usage: diploma_run.bat <mixer>   (default mfx9)
REM Pause: kill the python process AND close this window;
REM Resume: start the bat again -- recorded streams get skipped.
cd /d "%~dp0"
set MIXER=%1
if "%MIXER%"=="" set MIXER=mfx9
set /a attempt=0
:loop
set /a attempt+=1
echo.
echo ============================================================
echo   DIPLOMA %MIXER%  attempt %attempt%   %date% %time%
echo ============================================================
python -u ladder.py diploma %MIXER% 10 > diploma40_%MIXER%.log 2>&1
if exist diploma40_%MIXER%_done.txt goto end
if %attempt% geq 200 goto aborted
echo [!] End without marker (crash/incomplete) - retry in 10 s ...
timeout /t 10 /nobreak >nul
goto loop
:end
echo.
echo === DIPLOMA COMPLETE ===
type diploma40_%MIXER%_done.txt
type diploma40_%MIXER%_result.json
goto :eof
:aborted
echo === 200 restarts reached - stop. Check the checkpoint. ===
