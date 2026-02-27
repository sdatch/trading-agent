@echo off
REM Trading Agent Runner
REM Run this script to execute the trading agent

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Run the agent
python src\main.py %*

REM Pause only if run interactively (not from Task Scheduler)
if "%1"=="" (
    pause
)
