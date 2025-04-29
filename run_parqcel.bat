@echo off
:: Activate the virtual environment
call [filepath to virtual environment]]\venv\Scripts\activate.bat

:: Change directory to where your main.py is located
cd [filepath to main.py in the src folder]]

:: Run the Python script
python main.py

:: Deactivate the virtual environment (optional)
deactivate