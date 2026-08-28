@echo off
echo ============================================
echo  Compilando OptiChek.exe (version grafica)
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo [2/3] Compilando con PyInstaller...
pyinstaller --onefile --windowed --uac-admin --clean --noconfirm --hidden-import win32timezone --collect-all customtkinter --name OptiChek diagnostico.py
if errorlevel 1 (
    echo [ERROR] Fallo la compilacion.
    pause
    exit /b 1
)

echo.
echo [3/3] Limpiando archivos temporales...
if exist build rmdir /s /q build

echo.
echo ============================================
echo  LISTO. El ejecutable esta en:
echo  %cd%\dist\OptiChek.exe
echo ============================================
pause
