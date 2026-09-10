@echo off
REM ============================================================
REM  DINAMYT LOCAL - Encender el sistema (NO necesita internet)
REM
REM  Comprueba ANTES de arrancar: que la instalacion esta
REM  completa, que los puertos estan libres, y que los dos
REM  servicios contestan de verdad. Despues ensena la direccion
REM  en grande y un QR para los celulares.
REM
REM  Con --comprobar solo comprueba y no arranca nada. Sirve
REM  para dejar el PC probado LA VISPERA.
REM ============================================================
setlocal
cd /d "%~dp0"

REM El Python del backend es el que instala 1-INSTALAR.bat. Si todavia no
REM existe se usa el del sistema, para que "--comprobar" pueda decir QUE falta
REM en vez de morir sin explicar nada.
set "PY=%~dp0backend\venv\Scripts\python.exe"
if exist "%PY%" goto arrancar

where python >nul 2>&1
if errorlevel 1 goto sin_python
set "PY=python"

:arrancar
"%PY%" "%~dp0iniciar_local.py" %*
set "CODIGO=%ERRORLEVEL%"
echo.
pause
exit /b %CODIGO%

:sin_python
echo.
echo ============================================================
echo  NO SE ENCONTRO PYTHON EN ESTE PC.
echo ============================================================
echo.
echo  Este PC no tiene Python instalado y tampoco el entorno del
echo  backend. Instala Python 3 (marcando "Add to PATH") y corre
echo  despues 1-INSTALAR.bat, que necesita internet.
echo.
pause
exit /b 1
