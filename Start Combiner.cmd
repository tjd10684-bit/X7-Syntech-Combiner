@echo off
if not exist "%~dp0.venv\Scripts\python.exe" goto missing
"%~dp0.venv\Scripts\python.exe" "%~dp0combiner.py"
if errorlevel 1 pause
exit /b
:missing
echo Project environment not found. Run "Setup Combiner.cmd" first.
pause
exit /b 1
