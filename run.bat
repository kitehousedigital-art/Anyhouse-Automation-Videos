@echo off
cd /d "%~dp0"
echo.
echo  AnyHouse Video Studio
echo  1 = Open the web UI (recommended)
echo  2 = Watch inbox (drop a video, it renders)
echo  3 = Render all videos from the command line
echo  0 = First-time setup (installs Pillow + FFmpeg helper)
set /p c=Choose [1]: 
if "%c%"=="" set c=1
if "%c%"=="0" python -m pip install -r requirements.txt
if "%c%"=="1" python engine\server.py
if "%c%"=="2" python engine\render.py watch
if "%c%"=="3" python engine\render.py render --quality standard
pause
