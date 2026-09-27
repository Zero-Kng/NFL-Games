"""
O servidor responde desde o primeiro segundo: enquanto carrega os dados, entrega
a interface e o estado da carga (/api/estado), e as outras rotas da API
respondem 503 ("carregando") até os dados ficarem prontos. O navegador abre na
hora e mostra a tela de carregamento (testada em test_ui_novo.py).

A carga fica lenta de propósito com NFL_ATRASO_CARGA_S (só para testes).
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from servidor_local import porta_livre  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados/ ainda nao montado")


def _get(url, timeout=3):
    """(status, cabecalhos, corpo) sem lançar em 4xx/5xx."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _subir(porta, env_extra, args=()):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", **env_extra}
    return subprocess.Popen([sys.executable, str(ROOT / "server" / "serve.py"), "--offline", "--port", str(porta), *args],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")


def _esperar_porta(url, proc, limite_s=15):
    t0 = time.time()
    while time.time() - t0 < limite_s:
        try:
            return _get(url + "/api/estado", timeout=1)
        except OSError:
            assert proc.poll() is None, proc.stdout.read()
            time.sleep(0.05)
    raise AssertionError("a porta nao abriu")


def test_responde_durante_a_carga_e_libera_a_api_quando_pronto():
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    proc = _subir(porta, {"NFL_ATRASO_CARGA_S": "4"})
    try:
        t0 = time.time()
        status, _h, corpo = _esperar_porta(url, proc)
        assert time.time() - t0 < 3                                   # a porta abre antes da carga terminar
        estado = json.loads(corpo)
        assert status == 200 and estado["pronto"] is False and estado["fase"] in ("iniciando", "carregando")
        assert estado["mensagem"] and estado["primeiraCarga"] is False

        status, h, corpo = _get(url + "/api/meta")                    # a API espera os dados
        assert status == 503 and h["Retry-After"] == "1"
        assert json.loads(corpo)["error"] == "carregando os dados"
        status, _h, corpo = _get(url + "/")                            # a interface já sai
        assert status == 200 and b"NFL Games" in corpo

        while not json.loads(_get(url + "/api/estado")[2])["pronto"]:
            assert time.time() - t0 < 60, "nao ficou pronto"
            time.sleep(0.2)
        estado = json.loads(_get(url + "/api/estado")[2])
        assert estado["fase"] == "pronto"
        status, _h, corpo = _get(url + "/api/meta")
        assert status == 200 and len(json.loads(corpo)["seasons"]) >= 5
    finally:
        proc.terminate()
        proc.wait(10)


def test_erro_na_carga_fica_visivel_antes_de_sair(tmp_path):
    """Sem dados e sem internet: /api/estado mostra o erro por alguns segundos, e o servidor sai com 1."""
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    proc = _subir(porta, {"NFL_DADOS": str(tmp_path / "dados")})
    try:
        estado = None
        t0 = time.time()
        while time.time() - t0 < 30 and proc.poll() is None:
            try:
                estado = json.loads(_get(url + "/api/estado", timeout=1)[2])
                if estado["fase"] == "erro":
                    break
            except OSError:
                pass
            time.sleep(0.05)
        assert estado and estado["fase"] == "erro" and estado["primeiraCarga"] is True, estado
        assert "Sem dados" in estado["mensagem"]
        assert proc.wait(15) == 1
    finally:
        if proc.poll() is None:
            proc.kill()


def test_primeira_carga_interrompida_aparece_como_primeira_carga(tmp_path):
    """Completar uma carga interrompida também é "primeira carga" (a tela avisa que leva minutos)."""
    dados = tmp_path / "dados"
    (dados / "temporadas").mkdir(parents=True)
    for f in ("jogos.npz", "jogadores_bio.npz", "manifest.json", "origem_geral.json"):
        shutil.copy(ROOT / "dados" / f, dados / f)
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    proc = _subir(porta, {"NFL_DADOS": str(dados), "NFL_ESPERA_ERRO_S": "5"})
    try:
        visto = []
        t0 = time.time()
        while time.time() - t0 < 30 and proc.poll() is None:
            try:
                visto.append(json.loads(_get(url + "/api/estado", timeout=1)[2]))
            except OSError:
                pass
            if visto and visto[-1]["fase"] == "erro":
                break
            time.sleep(0.05)
        # "iniciando": a porta abriu antes de o servidor saber se e a primeira carga
        depois = [e for e in visto if e["fase"] != "iniciando"]
        assert depois and all(e["primeiraCarga"] for e in depois)
        assert any("completando a primeira carga" in e["mensagem"] or e["fase"] == "erro" for e in visto)
    finally:
        proc.kill()
        proc.wait(10)


def test_servidor_abre_a_porta_sem_esperar_o_pandas():
    """A porta (e a tela de carregamento) nao espera o pandas e o numpy: importar o servidor
    usa so a biblioteca padrao; o ETL e a camada de dados entram depois de a porta abrir."""
    codigo = ("import sys; sys.path[:0] = [r'%s', r'%s']; import serve; "
              "print(sorted(m for m in ('pandas', 'numpy', 'montar', 'data_layer') if m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", codigo % (ROOT / "server", ROOT / "etl")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]", r.stdout
