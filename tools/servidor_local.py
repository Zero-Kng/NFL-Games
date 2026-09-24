"""
Sobe o server/serve.py num processo separado, numa porta livre, para as
ferramentas de medicao (tools/) e para os testes (tests/).

    with servidor() as srv:
        srv.url          # http://127.0.0.1:<porta>
        srv.startup_s    # segundos ate /api/meta responder
        srv.pid
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / "server" / "serve.py"

# Linhas que o servidor imprime ao aquecer o cache (existem a partir da tarefa 4).
MARCA_AQUECIMENTO_INICIO = "aquecimento: inicio"
MARCA_AQUECIMENTO_FIM = "aquecimento: concluido"


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Servidor:
    url: str
    pid: int
    startup_s: float
    log: deque = field(default_factory=lambda: deque(maxlen=400))


@contextmanager
def servidor(args: tuple[str, ...] = (), esperar_aquecimento: bool = True, timeout_s: float = 180):
    """
    Inicia o servidor e espera /api/meta responder. Se o servidor anunciar que
    esta aquecendo o cache, espera tambem o fim do aquecimento (as medicoes
    devem refletir o regime normal, nao os primeiros segundos).
    """
    porta = porta_livre()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, str(SERVE), "--port", str(porta), *args],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    log: deque = deque(maxlen=400)
    viu = {"inicio": threading.Event(), "fim": threading.Event()}

    def drenar():
        # Precisa ler sempre: se o pipe encher, o servidor trava ao logar.
        for linha in proc.stdout:
            log.append(linha.rstrip())
            if MARCA_AQUECIMENTO_INICIO in linha:
                viu["inicio"].set()
            if MARCA_AQUECIMENTO_FIM in linha:
                viu["fim"].set()

    threading.Thread(target=drenar, daemon=True).start()
    url = f"http://127.0.0.1:{porta}"
    try:
        limite = time.perf_counter() + timeout_s
        while True:
            if proc.poll() is not None:
                raise RuntimeError("servidor encerrou ao iniciar:\n" + "\n".join(log))
            try:
                urllib.request.urlopen(url + "/api/meta", timeout=2).read()
                break
            except OSError:
                if time.perf_counter() > limite:
                    raise TimeoutError("servidor nao respondeu a tempo:\n" + "\n".join(log))
                time.sleep(0.1)
        startup = time.perf_counter() - t0

        if esperar_aquecimento and viu["inicio"].wait(1.0):
            if not viu["fim"].wait(max(1.0, limite - time.perf_counter())):
                raise TimeoutError("aquecimento do cache nao terminou a tempo")

        yield Servidor(url=url, pid=proc.pid, startup_s=startup, log=log)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def pico_memoria_mb(pid: int) -> float | None:
    """Pico de memoria (working set) do processo, em MB. So no Windows."""
    if sys.platform != "win32":
        return None
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid}).PeakWorkingSet64"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out) / 2**20 if out.isdigit() else None
