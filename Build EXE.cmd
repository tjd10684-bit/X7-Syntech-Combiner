@echo off
if not exist "%~dp0.venv\Scripts\python.exe" goto missing
if exist "%~dp0dist\SyntecCombiner.exe" goto exists
"%~dp0.venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name SyntecCombiner --distpath "%~dp0dist" --workpath "%~dp0build\pyinstaller" --specpath "%~dp0build" "%~dp0combiner.py"
if errorlevel 1 goto failed
echo Built: "%~dp0dist\SyntecCombiner.exe"
pause
exit /b 0
:missing
echo Run "Setup Combiner.cmd" and install requirements-build.txt first.
pause
exit /b 1
:exists
echo dist\SyntecCombiner.exe already exists. Move it before building again.
pause
exit /b 1
:failed
echo Build failed. Install requirements-build.txt and check the error above.
pause
exit /b 1
