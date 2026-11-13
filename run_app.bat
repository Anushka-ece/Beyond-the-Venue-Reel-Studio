@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python virtual environment not found at .venv.
    echo Create it with: py -3.13 -m venv .venv
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
if errorlevel 1 (
    echo.
    echo If Streamlit is not installed, run:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

endlocal
