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


JANELA = os.name == "nt"        # spec sem-terminal: no Windows o .exe nao tem console; as mensagens vao para o log


def _subir(exe: Path, pasta: Path, porta: int | None, env: dict | None = None):
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    porta_args = ["--port", str(porta)] if porta else []
    # NFL_SEM_AVISO: a janela de aviso do Windows travaria o teste esperando um clique
    return subprocess.Popen([str(exe), "--offline", "--sem-navegador", *porta_args], cwd=pasta,
                            env={**os.environ, "NFL_SEM_AVISO": "1", **(env or {})},
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **extra)


def _saida(proc, pasta: Path) -> str:
    """O que o app escreveu: o log no Windows (sem console), a saida do processo no Linux."""
    texto = proc.stdout.read() or ""
    log = pasta / "dados" / "nfl-games.log"
    return log.read_text(encoding="utf-8", errors="replace") if JANELA and log.exists() else texto


def _esperar_pronto(porta: int, proc, limite_s: float = 120):
    t0 = time.time()
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/estado", timeout=5) as r:
                estado = json.load(r)
            if estado["pronto"]:
                return
            assert estado["fase"] != "erro", f"o app falhou ao carregar: {estado['mensagem']}"
        except OSError:
            pass
        assert proc.poll() is None, "o executavel saiu antes de carregar os dados"
        assert time.time() - t0 < limite_s, f"os dados nao carregaram em {limite_s} s"
        time.sleep(0.5)


@pytest.fixture(scope="module")
def pasta_com_dados(executavel, tmp_path_factory):
    if not (ROOT / "dados" / "jogos.npz").exists():
        pytest.skip("dados/ ainda nao montado")
    pasta = tmp_path_factory.mktemp("exe")
    shutil.copy(executavel, pasta / NOME)
    shutil.copytree(ROOT / "dados", pasta / "dados", ignore=shutil.ignore_patterns("brutos"))
    return pasta


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


@pytest.mark.skipif(not JANELA, reason="o executavel sem console e so o do Windows")
def test_executavel_e_janela(executavel):
    """sem-terminal 1.1: o subsistema no cabecalho PE e 2 (GUI), nao 3 (console)."""
    dados = executavel.read_bytes()[:4096]
    pe = int.from_bytes(dados[0x3C:0x40], "little")
    assert dados[pe:pe + 4] == b"PE\0\0"
    assert int.from_bytes(dados[pe + 0x5C:pe + 0x5E], "little") == 2


def test_executavel_sem_dados_explica_no_log_e_sai(executavel, tmp_path):
    """Sem dados/ e sem internet: sobe o Python, o pandas e o servidor e sai com a mensagem, sem travar
    (foco de revisao 4 da sem-terminal: antes esperava um Enter)."""
    shutil.copy(executavel, tmp_path / NOME)
    proc = _subir(tmp_path / NOME, tmp_path, porta_livre())
    try:
        proc.wait(timeout=120)
    finally:
        _encerrar(proc)
    saida = _saida(proc, tmp_path)
    assert proc.returncode == 1
    assert "Sem dados para subir o app" in saida
    assert ("O NFL Games não conseguiu abrir." if JANELA else "O servidor nao subiu") in saida


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
    saida = _saida(proc, tmp_path)
    assert str(tmp_path / "dados") in saida.replace("\n", "")        # os dados ao lado do executavel


@pytest.mark.skipif(not JANELA, reason="encerrar pelo app e a copia unica sao do .exe do Windows")
def test_executavel_encerra_pela_rota(pasta_com_dados):
    porta = porta_livre()
    proc = _subir(pasta_com_dados / NOME, pasta_com_dados, porta)
    try:
        _esperar_pronto(porta, proc)
        req = urllib.request.Request(f"http://127.0.0.1:{porta}/api/encerrar", data=b"", method="POST",
                                     headers={"X-NFL-App": "1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            assert r.status == 200
        proc.wait(timeout=5)                                           # RNF 2
    finally:
        _encerrar(proc)
    assert proc.returncode == 0
    assert "encerrado pelo app" in _saida(proc, pasta_com_dados)


@pytest.mark.skipif(not JANELA, reason="encerrar pelo app e a copia unica sao do .exe do Windows")
def test_executavel_segunda_abertura_reaproveita(pasta_com_dados):
    base = porta_livre()                                               # longe da 8000 (o app aberto do José)
    env = {"NFL_PORTA_PADRAO": str(base)}
    primeiro = _subir(pasta_com_dados / NOME, pasta_com_dados, None, env)
    try:
        _esperar_pronto(base, primeiro)
        segundo = _subir(pasta_com_dados / NOME, pasta_com_dados, None, env)
        try:
            segundo.wait(timeout=15)
        finally:
            _encerrar(segundo)
        assert segundo.returncode == 0
        for porta in range(base + 1, base + 20):                       # nenhuma copia nova subiu
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/estado", timeout=0.5) as r:
                    assert json.load(r).get("app") != "NFL Games", porta
            except OSError:
                pass
        assert primeiro.poll() is None
    finally:
        _encerrar(primeiro)
