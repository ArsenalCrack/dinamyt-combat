@echo off
REM ============================================================
REM  DINAMYT LOCAL - Iniciar el servidor (NO necesita internet)
REM
REM  Este archivo ya solo llama a INICIAR.bat, que es el que
REM  comprueba antes de arrancar.
REM
REM  Se queda por una razon sola: el manual impreso que hay en la
REM  carpeta del evento dice "2-INICIAR", y el dia del campeonato
REM  nadie va a leer un cambio de nombre. Se retira cuando el
REM  manual impreso diga otra cosa.
REM ============================================================
setlocal
cd /d "%~dp0"
call "%~dp0INICIAR.bat" %*
exit /b %ERRORLEVEL%
