@echo off
if exist "%~dp0.venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto python
py -3 -m venv "%~dp0.venv"
if errorlevel 1 goto failed
goto install
:python
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv "%~dp0.venv"
if errorlevel 1 goto failed
:install
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto failed
echo Setup complete. Start the application with "Start Combiner.cmd".
pause
exit /b 0
:missing
echo Python 3 is required to set up the combiner.
pause
exit /b 1
:failed
echo Setup failed. Check the error above and retry.
pause
exit /b 1
