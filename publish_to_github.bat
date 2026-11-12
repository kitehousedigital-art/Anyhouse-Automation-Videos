@echo off
rem Creates a PRIVATE GitHub repo "anyhouse-video-studio" from this folder and pushes it.
rem Needs Git (https://git-scm.com) and, for one-step creation, the GitHub CLI (https://cli.github.com).
cd /d "%~dp0"
if exist _setup call finish_setup.bat
where git >nul 2>nul
if errorlevel 1 goto nogit
if not exist .git (
  git init -b main
  git add -A
  git commit -m "Initial commit: AnyHouse Video Studio (engine, web UI, MCP server, agent skill)"
)
where gh >nul 2>nul
if errorlevel 1 goto nogh
gh auth status >nul 2>nul
if errorlevel 1 gh auth login
gh repo create anyhouse-video-studio --private --source . --remote origin --push
goto done
:nogh
echo.
echo GitHub CLI not found. Create an EMPTY private repo named anyhouse-video-studio at https://github.com/new , then run:
echo   git remote add origin https://github.com/YOUR_USER/anyhouse-video-studio.git
echo   git push -u origin main
goto done
:nogit
echo Git is not installed. Get it from https://git-scm.com/download/win and run this again.
:done
echo.
pause
