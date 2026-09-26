@echo off
REM ============================================================
REM  NFL GAMES - inicia o app (dados do nflverse, 2021 em diante)
REM  Duplo-clique neste arquivo.
REM ============================================================
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo.
echo === NFL GAMES ===
echo.
echo Na primeira execucao o servidor baixa e monta os dados do nflverse
echo (~330 MB, alguns minutos; o progresso aparece abaixo). Precisa de internet.
echo Nas proximas, sobe direto com a copia local e busca so o que mudou.
echo O navegador abre em http://127.0.0.1:8000
echo Feche esta janela (ou Ctrl+C) para parar.
echo.

REM Abre o navegador quando o servidor responder (em segundo plano).
start "" /b powershell -NoProfile -Command "while (-not (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Sleep 1 }; Start-Process http://127.0.0.1:8000"

python server\serve.py
if errorlevel 1 goto erro
goto fim

:erro
echo.
echo [ERRO] O servidor nao subiu. Veja a mensagem acima.
echo        Se for a primeira execucao, confira a conexao com a internet.
echo        Se faltar biblioteca, instale:  python -m pip install pandas numpy
pause

:fim
