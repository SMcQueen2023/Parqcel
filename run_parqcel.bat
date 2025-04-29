@echo off
:: Activate the virtual environment
call "[path to venv]\Scripts\activate.bat"

:: Change directory to where your main.py is located
cd /d [path to Parqcel src folder]\src"

:: Run the Python script
python main.py
