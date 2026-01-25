@echo off
setlocal
REM Use the py launcher if available, falling back to python on PATH
where py >nul 2>&1
if %errorlevel%==0 (
	py -3 -m parqcel %*
) else (
	where python >nul 2>&1
	if %errorlevel%==0 (
		python -m parqcel %*
	) else (
		echo Python not found. Please install Python 3 and try again.
		endlocal
		exit /b 1
	)
)
endlocal
