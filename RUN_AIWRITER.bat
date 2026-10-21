@echo off
cd /d "%~dp0"
echo Installing/checking required Python packages...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package installation failed. Check the error above.
  pause
  exit /b 1
)
echo.
echo Starting AIWriter Pro...
python web_app.py
echo.
echo AIWriter Pro has stopped. If there is an error above, copy it for support.
pause
