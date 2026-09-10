@echo off
REM ============================================================
REM  DINAMYT LOCAL - Apagar el sistema de verdad
REM
REM  Cerrar las dos ventanas negras casi siempre funciona, pero
REM  no siempre: mata al cmd y deja al servidor vivo escuchando
REM  en su puerto. Esto para lo que ESTA escuchando en el 5000 y
REM  el 3000, y cierra las dos ventanas.
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=%~dp0backend\venv\Scripts\python.exe"
if exist "%PY%" goto apagar

where python >nul 2>&1
if errorlevel 1 goto sin_python
set "PY=python"

:apagar
"%PY%" "%~dp0apagar_local.py"
set "CODIGO=%ERRORLEVEL%"
echo.
pause
exit /b %CODIGO%

:sin_python
echo.
echo  No se encontro Python en este PC, asi que no hay nada que
echo  este arrancado por DINAMYT. Si ves ventanas abiertas,
echo  cierralas a mano.
echo.
pause
exit /b 1
