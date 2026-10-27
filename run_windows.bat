@echo off
REM Double-click to run the whole Olist analysis on Windows.
REM Finds Anaconda/Python, installs DuckDB if missing, finds the data (zip or CSVs in data\ or the folder
REM above this project), runs src\run_analysis.py. Log: output\run_log_main.txt
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if exist output\RUNNING.lock (
  echo [INFO] Analysis is already running in another window. Close this window.
  pause & exit /b 0
)
if not exist output mkdir output
echo running > output\RUNNING.lock

set "PY="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%PROGRAMDATA%\anaconda3" "%PROGRAMDATA%\Anaconda3" "C:\anaconda3" "D:\anaconda3" "D:\Anaconda3") do (
  if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY (
  echo [ERROR] Python not found. Please install Anaconda.
  del output\RUNNING.lock 2>nul
  pause & exit /b 1
)
echo Using Python: %PY%

"%PY%" -c "import duckdb" 2>nul || (
  echo Installing duckdb ...
  "%PY%" -m pip install duckdb > output\pip_log.txt 2>&1 || "%PY%" -m pip install duckdb -i https://pypi.tuna.tsinghua.edu.cn/simple >> output\pip_log.txt 2>&1
)

"%PY%" -c "import kagglehub" 2>nul || (
  echo Installing kagglehub ...
  "%PY%" -m pip install kagglehub >> output\pip_log.txt 2>&1 || "%PY%" -m pip install kagglehub -i https://pypi.tuna.tsinghua.edu.cn/simple >> output\pip_log.txt 2>&1
)
"%PY%" -c "import scipy" 2>nul || "%PY%" -m pip install scipy >> output\pip_log.txt 2>&1

echo Running analysis, please wait ...
"%PY%" -u src\run_analysis.py > output\run_log_main.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> output\run_log_main.txt
del output\RUNNING.lock 2>nul
type output\run_log_main.txt
echo.
echo ===== Finished. Open output\report.md and output\charts =====
pause
