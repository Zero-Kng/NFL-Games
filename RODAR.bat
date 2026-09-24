@echo off
REM ============================================================
REM  NFL GAMES - inicia o app (dataset Big Data Bowl 2023)
REM  Duplo-clique neste arquivo.
REM ============================================================
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo.
echo === NFL GAMES ===
echo.
echo Na primeira execucao o servidor prepara o cache do tracking (~45s).
echo Nas proximas, sobe direto. O navegador abre em http://127.0.0.1:8000
echo Feche esta janela (ou Ctrl+C) para parar.
echo.

REM Abre o navegador quando o servidor responder (em segundo plano).
start "" /b powershell -NoProfile -Command "while (-not (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Sleep 1 }; Start-Process http://127.0.0.1:8000"

python server\serve.py
if errorlevel 1 goto erro
goto fim

:erro
echo.
echo [ERRO] O servidor nao subiu. Confira se o Python e o pandas estao instalados:
echo        python -m pip install pandas
pause

:fim
