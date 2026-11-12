@echo off
rem Places .mcp.json and .github\workflows\ci.yml (blocked from remote writes) into their final spots, then removes _setup.
cd /d "%~dp0"
if exist _setup\mcp.json copy /y _setup\mcp.json .mcp.json >nul
if exist _setup\ci.yml (
  if not exist .github\workflows mkdir .github\workflows
  copy /y _setup\ci.yml .github\workflows\ci.yml >nul
)
if exist .mcp.json if exist .github\workflows\ci.yml rmdir /s /q _setup
echo Done: .mcp.json and .github\workflows\ci.yml are in place.
pause
