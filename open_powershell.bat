@echo off
setlocal

:: Папка, где лежит этот bat-файл
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

:: Проверяем venv
set "VENV_ACTIVATE=%PROJECT_ROOT%\.venv\Scripts\Activate.ps1"
if not exist "%VENV_ACTIVATE%" (
    echo ERROR: .venv not found at %PROJECT_ROOT%\.venv
    echo Run first: python -m venv .venv
    pause
    exit /b 1
)

:: Запуск PowerShell с активированным venv
start "PowerShell" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -ExecutionPolicy Bypass -NoExit -Command "Set-Location '%PROJECT_ROOT%'; & '%VENV_ACTIVATE%'; Write-Host '' ; Write-Host '(.venv) Activated' -ForegroundColor Green; Write-Host 'Folder:  %PROJECT_ROOT%' -ForegroundColor DarkGray; Write-Host ''"

endlocal