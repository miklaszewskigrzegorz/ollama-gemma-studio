@echo off
setlocal EnableDelayedExpansion
title Local LLM Assistant
cd /d "%~dp0"

echo ============================================
echo  Local LLM Assistant - starting up
echo ============================================
echo.

REM --- Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install from: https://python.org
    echo         Check "Add Python to PATH" during install.
    goto :ERROR
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

REM --- Ollama ---
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Ollama not found.
    echo         Install from: https://ollama.com
    goto :ERROR
)
echo [OK] Ollama found

REM --- Virtual environment ---
if not exist ".venv\" (
    echo [..] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 ( echo [ERROR] Failed to create venv & goto :ERROR )
)
call .venv\Scripts\activate.bat
echo [OK] Virtual environment active

REM --- Dependencies ---
echo [..] Checking dependencies...
pip install -r requirements.txt -q --no-warn-script-location
echo [OK] Dependencies ready

REM --- .env ---
if not exist ".env" (
    copy .env.example .env >nul
    echo [OK] .env created from template
) else (
    echo [OK] .env found
)

REM --- Docker + SearXNG ---
echo.
echo [..] Checking Docker...
docker info >nul 2>&1
if not errorlevel 1 goto :DOCKER_READY

echo [..] Docker not running - starting Docker Desktop...
set "DOCKER_EXE="
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if exist "%LocalAppData%\Docker\Docker Desktop.exe"        set "DOCKER_EXE=%LocalAppData%\Docker\Docker Desktop.exe"

if "%DOCKER_EXE%"=="" (
    echo [--] Docker Desktop not installed - skipping SearXNG
    goto :START_APP
)

start "" "%DOCKER_EXE%"
echo [..] Waiting for Docker (max 60 sec)...
set WAIT=0

:WAIT_LOOP
timeout /t 5 /nobreak >nul
set /a WAIT+=5
docker info >nul 2>&1
if not errorlevel 1 goto :DOCKER_READY
if %WAIT% lss 60 goto :WAIT_LOOP
echo [--] Docker took too long - SearXNG unavailable, fallback to DuckDuckGo
goto :START_APP

:DOCKER_READY
echo [OK] Docker running
echo [..] Starting SearXNG...
docker compose -f docker-compose.searxng.yml up -d >nul 2>&1
if errorlevel 1 (
    echo [--] SearXNG failed - using DuckDuckGo fallback (check: docker compose -f docker-compose.searxng.yml logs)
) else (
    echo [OK] SearXNG ready at http://localhost:8889
    set SEARXNG_URL=http://localhost:8889
)

REM --- Launch app ---
:START_APP
echo.
echo ============================================
echo  Opening http://127.0.0.1:7860
echo  Press Ctrl+C to stop
echo ============================================
echo.
python app.py
echo.
echo App stopped.
goto :DONE

:ERROR
echo.
echo Fix the error above and try again.

:DONE
echo.
pause
endlocal
