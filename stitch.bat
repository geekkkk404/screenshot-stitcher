@echo off
chcp 65001 >nul

echo ========================================
echo   Screenshot Stitcher
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "STITCH_SCRIPT=%SCRIPT_DIR%stitch.py"
set "INPUT_DIR=%SCRIPT_DIR%input"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Python venv not found
    pause
    exit /b 1
)

if not exist "%INPUT_DIR%" mkdir "%INPUT_DIR%"

set COUNT=0
for %%f in ("%INPUT_DIR%\*.png" "%INPUT_DIR%\*.jpg" "%INPUT_DIR%\*.jpeg" "%INPUT_DIR%\*.bmp" "%INPUT_DIR%\*.webp") do (
    if exist "%%f" set /a COUNT+=1
)

if %COUNT%==0 (
    echo No images found in input folder.
    echo Please put screenshots into: %INPUT_DIR%
    echo.
    pause
    exit /b 0
)

echo Found %COUNT% image(s). Stitching...
echo.

"%VENV_PYTHON%" "%STITCH_SCRIPT%"

echo.
echo ========================================
echo Done. Press any key to exit...
echo ========================================
pause >nul
