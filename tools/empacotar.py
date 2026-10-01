"""
Gera o executavel do app com o PyInstaller: um arquivo so, que roda sem Python
instalado. No Windows sai dist/NFL-Games.exe; no Linux, dist/nfl-games.

    python -m pip install -r requirements-dev.txt   # traz o PyInstaller (uma vez)
    python tools/empacotar.py                        # gera o executavel deste sistema

O executavel e o rodar.py com o Python, o pandas, o numpy, o servidor
(server/), o ETL (etl/) e a interface (app/) dentro. Os dados nao vao nele:
ficam numa pasta dados/ ao lado do executavel, baixados na primeira execucao.
Cada sistema gera o seu (o PyInstaller nao faz executavel de outro sistema);
o GitHub Actions (.github/workflows/executaveis.yml) gera os dois nas versoes.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
NOME = "NFL-Games" if os.name == "nt" else "nfl-games"
# Instalados na maquina de quem empacota, mas o app nao usa: ficam de fora (tamanho).
FORA = ["matplotlib", "scipy", "IPython", "jupyter", "notebook", "tkinter", "pytest", "playwright",
        "PyInstaller", "setuptools", "pyarrow"]


def argumentos(dist: Path, trabalho: Path, windows: bool | None = None) -> list[str]:
    windows = os.name == "nt" if windows is None else windows
    sep = os.pathsep                                   # o PyInstaller usa ';' no Windows e ':' no Linux
    args = [
        str(RAIZ / "rodar.py"),
        "--onefile", "--noconfirm", "--clean",
        "--name", NOME,
        "--distpath", str(dist), "--workpath", str(trabalho), "--specpath", str(trabalho),
        "--paths", str(RAIZ / "server"), "--paths", str(RAIZ / "etl"),
        "--hidden-import", "serve",                     # importado pelo rodar.py so na hora de subir
        "--add-data", f"{RAIZ / 'app'}{sep}app",
    ]
    if windows:
        # Spec sem-terminal: no Windows, sem console e com a logo na hora do duplo clique (a tela
        # de abertura do PyInstaller, que fecha quando o navegador abre: rodar.fechar_abertura).
        args += ["--windowed", "--splash", str(RAIZ / "tools" / "abertura.png"),
                 "--icon", str(RAIZ / "app" / "img" / "icone.ico")]
    else:                                               # Linux: segue no terminal, como antes
        args += ["--console"]
    for modulo in FORA:
        args += ["--exclude-module", modulo]
    return args


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("[erro] PyInstaller nao instalado: python -m pip install -r requirements-dev.txt")
        return 1
    dist, trabalho = RAIZ / "dist", RAIZ / "build"
    t0 = time.perf_counter()
    pyinstaller.run(argumentos(dist, trabalho))
    exe = dist / (NOME + (".exe" if os.name == "nt" else ""))
    if not exe.is_file():
        print(f"[erro] o executavel nao foi gerado em {exe}")
        return 1
    print(f"\n{exe}  ({exe.stat().st_size / 1e6:.0f} MB, {time.perf_counter() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
