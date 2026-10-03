"""
Cria o atalho NFL Games.lnk na raiz do projeto (Windows): abre o app pelo Python
instalado (pythonw.exe, sem console), rodando o codigo atual do repositorio.

    python tools/atalho.py

Por que um atalho, e nao o NFL-Games.exe: o Controle Inteligente de Aplicativos do
Windows so deixa rodar programas assinados ou de reputacao conhecida. Cada .exe que o
PyInstaller gera e um arquivo novo, sem assinatura, e costuma ser bloqueado. O
pythonw.exe e assinado pela Python Software Foundation; e os .py nao passam pelo
bloqueio. O atalho nunca fica desatualizado: roda o rodar.py do repositorio, no modo
sem terminal (log em dados/nfl-games.log, logo de abertura, "Encerrar o app" e
encerramento sozinho). O .exe para distribuir continua: tools/empacotar.py e o
GitHub Actions.

O .lnk guarda caminhos desta maquina (o Python instalado e o projeto): nao vai para o
Git. Refaca-o se o Python mudar de lugar.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "NFL Games.lnk"
ICONE = RAIZ / "app" / "img" / "icone.ico"

# Os caminhos vao por variaveis de ambiente: nada de aspas para escapar no PowerShell.
_CRIAR = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:NFL_LNK); "
          "$s.TargetPath = $env:NFL_ALVO; $s.Arguments = 'rodar.py'; "
          "$s.WorkingDirectory = $env:NFL_PASTA; $s.IconLocation = $env:NFL_ICONE + ',0'; "
          "$s.Description = 'NFL Games'; $s.Save()")
_LER = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:NFL_LNK); "
        "'{0}|{1}|{2}|{3}' -f $s.TargetPath, $s.Arguments, $s.WorkingDirectory, $s.IconLocation")


def _powershell(comando: str, env: dict) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
                       env={**os.environ, **env}, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"powershell falhou: {r.stderr.strip()}")
    return r.stdout.strip()


def criar_atalho(destino: Path, pythonw: Path, raiz: Path, icone: Path) -> Path:
    _powershell(_CRIAR, {"NFL_LNK": str(destino), "NFL_ALVO": str(pythonw),
                         "NFL_PASTA": str(raiz), "NFL_ICONE": str(icone)})
    return destino


def ler_atalho(lnk: Path) -> dict:
    alvo, args, pasta, icone = _powershell(_LER, {"NFL_LNK": str(lnk)}).split("|")
    return {"TargetPath": alvo, "Arguments": args, "WorkingDirectory": pasta, "IconLocation": icone}


def main() -> int:
    if os.name != "nt":
        print("[erro] o atalho .lnk e do Windows; no Linux e no macOS use ./rodar.sh")
        return 1
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        print(f"[erro] nao achei {pythonw}: rode este script com o Python que vai abrir o app")
        return 1
    criar_atalho(DESTINO, pythonw, RAIZ, ICONE)
    print(f"{DESTINO.name} criado: {pythonw} rodar.py (em {RAIZ})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
