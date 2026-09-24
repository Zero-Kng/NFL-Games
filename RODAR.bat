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

if not exist "cache\play_timing.csv" (
    echo Primeira execucao: gerando metricas do tracking ^(~20s^)...
    python etl\build_metrics.py
    if errorlevel 1 goto erro
    echo.
)

echo Abrindo o navegador em http://127.0.0.1:8000
start "" http://127.0.0.1:8000
echo.
echo Servidor iniciado. Feche esta janela (ou Ctrl+C) para parar.
echo.
python server\serve.py
goto fim

:erro
echo.
echo [ERRO] Falha ao gerar o cache. Confira se o Python e o pandas estao instalados:
echo        python -m pip install pandas
pause

:fim
