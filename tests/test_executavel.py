"""
O executavel (tools/empacotar.py): gera, sobe numa pasta qualquer com os dados
ao lado e confere a pagina e a API. Leva ~1 min (o PyInstaller empacota o
Python, o pandas e o numpy), entao so roda quando pedido:

    NFL_EMPACOTAR=1 python -m pytest tests/test_executavel.py -q      (bash)
    $env:NFL_EMPACOTAR=1; python -m pytest tests/test_executavel.py -q   (PowerShell)
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from servidor_local import porta_livre  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("NFL_EMPACOTAR") != "1",
                                reason="empacotar leva ~1 min: rode com NFL_EMPACOTAR=1")
NOME = "NFL-Games.exe" if os.name == "nt" else "nfl-games"


@pytest.fixture(scope="module")
def executavel():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "empacotar.py")], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    exe = ROOT / "dist" / NOME
    assert exe.is_file()
    return exe


def _subir(exe: Path, pasta: Path, porta: int):
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen([str(exe), "--offline", "--sem-navegador", "--port", str(porta)], cwd=pasta,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **extra)


def _encerrar(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(15)


def test_executavel_tem_tamanho_de_um_arquivo_so(executavel):
    assert 10e6 < executavel.stat().st_size < 150e6


def test_executavel_sem_dados_explica_e_sai(executavel, tmp_path):
    """Sem dados/ e sem internet: sobe o Python, o pandas e o servidor e sai com a mensagem."""
    shutil.copy(executavel, tmp_path / NOME)
    proc = _subir(tmp_path / NOME, tmp_path, porta_livre())
    try:
        saida, _ = proc.communicate(timeout=120)
    finally:
        _encerrar(proc)
    assert proc.returncode == 1
    assert "Sem dados para subir o app" in saida and "O servidor nao subiu" in saida


@pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados/ ainda nao montado")
def test_executavel_sobe_o_app_com_os_dados_ao_lado(executavel, tmp_path):
    shutil.copy(executavel, tmp_path / NOME)
    shutil.copytree(ROOT / "dados", tmp_path / "dados", ignore=shutil.ignore_patterns("brutos"))
    porta = porta_livre()
    proc = _subir(tmp_path / NOME, tmp_path, porta)
    try:
        t0 = time.time()
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2) as r:
                    assert b"NFL Games" in r.read()
                break
            except OSError:
                assert proc.poll() is None, "o executavel saiu antes de o app responder"
                assert time.time() - t0 < 120, "o app nao respondeu em 120 s"
                time.sleep(0.5)
        # A porta abre antes de carregar os dados (tela de carregamento): a API
        # responde 503 ate /api/estado dizer "pronto". Mesmo limite de 120 s.
        estado = {"mensagem": "sem resposta de /api/estado"}
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/estado", timeout=5) as r:
                    estado = json.load(r)
            except OSError:
                pass        # a carga ocupa o processo: a resposta pode atrasar
            else:
                if estado["pronto"]:
                    break
                assert estado["fase"] != "erro", f"o app falhou ao carregar: {estado['mensagem']}"
            assert proc.poll() is None, "o executavel saiu antes de carregar os dados"
            assert time.time() - t0 < 120, f"os dados nao carregaram em 120 s ({estado['mensagem']})"
            time.sleep(0.5)
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/meta", timeout=10) as r:
            meta = json.load(r)
        assert len(meta["seasons"]) >= 5
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/js/main.js", timeout=10) as r:
            assert r.headers["Content-Type"].startswith("text/javascript")
    finally:
        _encerrar(proc)
    saida = proc.stdout.read()
    assert str(tmp_path / "dados") in saida.replace("\n", "")        # os dados ao lado do executavel
