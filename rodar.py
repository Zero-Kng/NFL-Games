"""
NFL GAMES - inicia o app (dados do nflverse, 2021 em diante) em Windows,
Linux e macOS.

    python rodar.py                  # sobe o servidor e abre o navegador
    python rodar.py --port 9000      # outra porta
    python rodar.py --offline        # so a copia local em dados/, sem internet
    python rodar.py --sem-navegador  # nao abre o navegador (so mostra o endereco)

As demais opcoes (--host, --max-pendentes) vao direto para o server/serve.py.
Do codigo: python rodar.py (ou ./rodar.sh no Linux e no macOS). Empacotado:
NFL-Games.exe (Windows) e nfl-games (Linux), gerados por tools/empacotar.py;
eles aceitam as mesmas opcoes.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PYTHON_MINIMO = (3, 10)
BIBLIOTECAS = ("pandas", "numpy")
PYTHON = "python" if os.name == "nt" else "python3"     # o nome que a pessoa digita no terminal
CONGELADO = bool(getattr(sys, "frozen", False))          # rodando como executavel (PyInstaller)


def _utf8() -> None:
    """Acentos certos em qualquer terminal (no Windows, sem precisar do PYTHONIOENCODING)."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def checar_python(versao=sys.version_info) -> bool:
    if tuple(versao[:2]) >= PYTHON_MINIMO:
        return True
    print(f"[ERRO] O app precisa do Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} ou mais novo "
          f"(este e o {versao[0]}.{versao[1]}). Instale em https://www.python.org/downloads/", flush=True)
    return False


def faltando() -> list[str]:
    return [b for b in BIBLIOTECAS if importlib.util.find_spec(b) is None]


def pastas(congelado: bool = CONGELADO, interno: Path | None = None,
           executavel: Path | None = None) -> tuple[Path, Path]:
    """
    (interface, dados). A partir do codigo: as pastas do repositorio. No
    executavel: a interface vem de dentro dele (so leitura) e os dados ficam
    numa pasta dados/ ao lado do .exe, baixados na primeira execucao.
    """
    if not congelado:
        return RAIZ / "app", RAIZ / "dados"
    interno = Path(interno or getattr(sys, "_MEIPASS", RAIZ))
    executavel = Path(executavel or sys.executable)
    return interno / "app", executavel.resolve().parent / "dados"


def ler_opcoes(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--offline", action="store_true", help="usa so a copia local em dados/, sem internet")
    ap.add_argument("--sem-navegador", action="store_true", help="nao abre o navegador")
    return ap.parse_known_args(argv)


def opcoes_servidor(args: argparse.Namespace, extras: list[str]) -> list[str]:
    opcoes = ["--host", args.host, "--port", str(args.port)]
    if args.offline:
        opcoes.append("--offline")
    return opcoes + list(extras)


def _host_local(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "") else host


def endereco(host: str, porta: int) -> str:
    return f"http://{_host_local(host)}:{porta}"


def vigiar_e_abrir(host: str, porta: int, processo, abrir=webbrowser.open, intervalo_s: float = 0.5) -> bool:
    """
    Espera o servidor aceitar conexoes e abre o navegador. Na primeira subida
    isso leva alguns minutos (download dos dados), entao espera enquanto o
    servidor estiver no ar (processo.poll() None). Sem navegador (maquina sem
    tela), mostra o endereco.
    """
    url = endereco(host, porta)
    while processo.poll() is None:
        try:
            with socket.create_connection((_host_local(host), porta), timeout=1):
                pass
        except OSError:
            time.sleep(intervalo_s)
            continue
        try:
            abriu = abrir(url)
        except Exception:  # noqa: BLE001 - qualquer falha do navegador vira "abra voce"
            abriu = False
        if abriu is False:
            print(f"\nAbra no navegador: {url}\n", flush=True)
        return True
    return False


class _Servindo:
    """O servidor roda neste processo; poll() diz se ele ja terminou (como um subprocesso)."""

    def __init__(self):
        self.codigo = None

    def poll(self):
        return self.codigo


def rodar_servidor(opcoes: list[str]) -> int:
    """Roda o server/serve.py neste processo (no executavel nao ha outro Python para chamar)."""
    for pasta in (RAIZ / "server", RAIZ / "etl"):
        if str(pasta) not in sys.path:
            sys.path.insert(0, str(pasta))
    import serve  # noqa: PLC0415 - depende das pastas acima e do NFL_APP/NFL_DADOS ja definidos
    sys.argv = ["serve.py", *opcoes]
    return serve.main()


def _esperar_enter() -> None:
    """Executavel aberto com duplo clique: a janela fecharia antes de a pessoa ler o erro."""
    if CONGELADO and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPressione Enter para fechar...")
        except (EOFError, KeyboardInterrupt):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8()
    if not checar_python():
        return 1
    falta = [] if CONGELADO else faltando()          # o executavel ja traz as bibliotecas
    if falta:
        print(f"[ERRO] Faltam bibliotecas do Python: {', '.join(falta)}.\n"
              f"       Instale com:  {PYTHON} -m pip install pandas numpy", flush=True)
        return 1

    args, extras = ler_opcoes(argv)
    app, dados = pastas()
    os.environ.setdefault("NFL_APP", str(app))
    os.environ.setdefault("NFL_DADOS", str(dados))
    url = endereco(args.host, args.port)
    print("\n=== NFL GAMES ===\n\n"
          "Na primeira execucao o servidor baixa e monta os dados do nflverse\n"
          f"(~330 MB, alguns minutos; o progresso aparece abaixo) em {os.environ['NFL_DADOS']}.\n"
          "Precisa de internet. Nas proximas, sobe direto com a copia local e busca so o que mudou.\n"
          f"O app fica em {url}" + ("" if args.sem_navegador else " (o navegador abre sozinho)") + "\n"
          "Ctrl+C (ou fechar esta janela) para parar.\n", flush=True)

    servindo = _Servindo()
    if not args.sem_navegador:
        threading.Thread(target=vigiar_e_abrir, args=(args.host, args.port, servindo), daemon=True).start()
    try:
        codigo = rodar_servidor(opcoes_servidor(args, extras))
    except KeyboardInterrupt:                       # Ctrl+C antes de o servidor ficar no ar
        print("\nencerrado.", flush=True)
        return 0
    finally:
        servindo.codigo = -1

    if codigo:
        print("\n[ERRO] O servidor nao subiu. Veja a mensagem acima.\n"
              "       Se for a primeira execucao, confira a conexao com a internet.", flush=True)
        if not CONGELADO:
            print(f"       Se faltar biblioteca, instale:  {PYTHON} -m pip install pandas numpy", flush=True)
        _esperar_enter()
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
