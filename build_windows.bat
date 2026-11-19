@echo off
REM Gera dist\Certifica.exe (rodar no Windows).
setlocal
cd /d "%~dp0"

if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements-dev.txt
if errorlevel 1 goto :error

.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name Certifica ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --collect-data customtkinter ^
  --hidden-import keyring.backends.Windows ^
  main.py
if errorlevel 1 goto :error

echo.
echo Pronto: dist\Certifica.exe
goto :eof

:error
echo.
echo Falha ao gerar o executavel.
exit /b 1
