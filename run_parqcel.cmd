@echo off
setlocal
REM Use the py launcher if available, falling back to python on PATH
py -3 -m parqcel %*
endlocal
