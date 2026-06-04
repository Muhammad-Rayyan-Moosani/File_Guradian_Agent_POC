@echo off
REM ============================================================================
REM  Build the File Guardian Agent into ONE self-contained Windows .exe.
REM
REM  Run this from the repo ROOT on the Windows build machine:
REM      backend\build_windows.bat
REM
REM  Prerequisites (BUILD machine only):
REM      - Python 3.13  (https://www.python.org/downloads/)
REM      - Node.js      (https://nodejs.org/)  -- only to compile the web UI
REM  The finished .exe needs NEITHER installed to RUN on the server.
REM ============================================================================
setlocal

echo.
echo [1/4] Building the web UI (React -^> static files)...
cd frontend || goto :error
call npm install || goto :error
call npm run build || goto :error
cd ..

echo.
echo [2/4] Setting up the Python build environment...
cd backend || goto :error
if not exist venv (
    python -m venv venv || goto :error
)
call venv\Scripts\activate.bat || goto :error
pip install -r requirements.txt || goto :error
pip install pyinstaller || goto :error

echo.
echo [3/4] Bundling the executable with PyInstaller...
pyinstaller file_guardian.spec --noconfirm || goto :error

echo.
echo [4/4] Build complete.
echo.
echo   Executable:  backend\dist\FileGuardianAgent.exe
echo.
echo   Before running it, place a .env file NEXT TO the .exe (copy .env.example
echo   and fill in SMTP / ANTHROPIC values). The SQLite database and the logs
echo   folder are created next to the .exe automatically on first run.
echo.
echo   Start it by double-clicking the .exe (or from a terminal), then open
echo   http://SERVER-NAME-OR-IP:6500 in a browser. First start takes ~30s while
echo   it unpacks; after that the dashboard loads normally.
echo.
endlocal
exit /b 0

:error
echo.
echo BUILD FAILED. See the message above for the step that failed.
endlocal
exit /b 1
