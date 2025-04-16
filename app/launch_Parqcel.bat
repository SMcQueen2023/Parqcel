@echo off
echo Activating virtual environment...

cd C:\Users\scott\OneDrive\Documents\GitHub\Parqcel

:: Check if PowerShell exists and activate the virtual environment
if exist .\.venv\Scripts\Activate.ps1 (
    powershell -ExecutionPolicy Bypass -File .\.venv\Scripts\Activate.ps1
) else (
    echo Virtual environment not found. Exiting...
    exit /b
)

echo Running the app...
python -m app.main

echo Script finished.
pause
