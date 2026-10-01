"""
Spec sem-terminal, tarefa 2: as rotas que mudam o estado do servidor
(POST /api/encerrar e POST /api/presenca), a proteção delas e o encerramento
sozinho (--encerrar-sozinho).
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import ROOT, http_json

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl"), str(ROOT / "tools")]
pytestmark = pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados ainda não montados")

import serve  # noqa: E402
from servidor_local import servidor as subir  # noqa: E402

APP = {"X-NFL-App": "1"}


def pedir(url, metodo="POST", corpo=None, cabecalhos=None):
    dados = corpo if isinstance(corpo, bytes) or corpo is None else json.dumps(corpo).encode()
    req = urllib.request.Request(url, data=dados, method=metodo, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def esperar_sair(proc, limite_s):
    t0 = time.time()
    while proc.poll() is None and time.time() - t0 < limite_s:
        time.sleep(0.1)
    return proc.poll()


@pytest.mark.parametrize("ip, cab, esperado", [
    ("127.0.0.1", {"X-NFL-App": "1"}, True),
    ("127.0.0.1", {"X-NFL-App": "1", "Origin": "http://127.0.0.1:8000"}, True),
    ("127.0.0.1", {"X-NFL-App": "1", "Origin": "http://localhost:8000"}, True),
    ("::1", {"X-NFL-App": "1"}, True),
    ("::ffff:127.0.0.1", {"X-NFL-App": "1"}, True),
    ("192.168.0.10", {"X-NFL-App": "1"}, False),
    ("127.0.0.1", {}, False),
    ("127.0.0.1", {"X-NFL-App": "1", "Origin": "https://exemplo.com"}, False),
    ("127.0.0.1", {"X-NFL-App": "1", "Origin": "http://127.0.0.1:9999"}, False),
])
def test_pedido_confiavel(ip, cab, esperado):
    assert serve.pedido_confiavel(ip, cab, 8000) is esperado


def test_estado_identifica_o_app(servidor):
    status, estado = http_json(servidor.url + "/api/estado")
    assert status == 200 and estado["app"] == "NFL Games"


def test_rotas_que_mudam_estado_recusam_pedidos_de_fora(servidor):
    for rota in ("/api/encerrar", "/api/presenca"):
        assert pedir(servidor.url + rota, corpo={"aba": "t", "saiu": False})[0] == 403
        assert pedir(servidor.url + rota, corpo={"aba": "t", "saiu": False},
                     cabecalhos={**APP, "Origin": "https://exemplo.com"})[0] == 403
    assert pedir(servidor.url + "/api/encerrar", metodo="GET")[0] == 404
    status, cab, _ = pedir(servidor.url + "/api/encerrar", metodo="OPTIONS",
                           cabecalhos={"Origin": "https://exemplo.com", "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "x-nfl-app"})
    assert not 200 <= status < 300 and "Access-Control-Allow-Origin" not in cab
    assert http_json(servidor.url + "/api/meta")[0] == 200            # continua de pé


def test_presenca_corpo_invalido(servidor):
    url = servidor.url + "/api/presenca"
    for corpo in (b"", b"x", b"[]", json.dumps({"aba": "a" * 2000, "saiu": False}).encode()):
        assert pedir(url, corpo=corpo, cabecalhos=APP)[0] == 400, corpo[:20]
    assert pedir(url, corpo={"aba": "t", "saiu": False}, cabecalhos=APP)[0] == 204


def test_encerrar_termina_o_processo():
    with subir() as srv:
        status, _, corpo = pedir(srv.url + "/api/encerrar", cabecalhos=APP)
        assert status == 200 and json.loads(corpo) == {"encerrando": True}
        assert esperar_sair(srv.proc, 5) == 0
        assert any("encerrado pelo app" in linha for linha in srv.log)


RAPIDO = {"NFL_PRESENCA_SAIDA_S": "1", "NFL_PRESENCA_LIMITE_S": "3", "NFL_VIGIA_S": "0.2"}


def test_encerra_sozinho_depois_da_ultima_aba():
    with subir(args=("--encerrar-sozinho",), env=RAPIDO) as srv:
        pedir(srv.url + "/api/presenca", corpo={"aba": "t", "saiu": False}, cabecalhos=APP)
        pedir(srv.url + "/api/presenca", corpo={"aba": "t", "saiu": True}, cabecalhos=APP)
        assert esperar_sair(srv.proc, 5) == 0
        assert any("encerrado: a última aba do app foi fechada" in linha for linha in srv.log)


def test_sem_aba_nao_encerra_sozinho():
    with subir(args=("--encerrar-sozinho",), env=RAPIDO) as srv:
        time.sleep(4)
        assert srv.proc.poll() is None and http_json(srv.url + "/api/meta")[0] == 200


def test_sem_a_opcao_nao_encerra_sozinho():
    with subir(env=RAPIDO) as srv:
        pedir(srv.url + "/api/presenca", corpo={"aba": "t", "saiu": False}, cabecalhos=APP)
        pedir(srv.url + "/api/presenca", corpo={"aba": "t", "saiu": True}, cabecalhos=APP)
        time.sleep(4)
        assert srv.proc.poll() is None and http_json(srv.url + "/api/meta")[0] == 200


def test_encerrar_forca_a_saida_se_a_carga_nao_terminar():
    saidas = []
    serve.encerrar_em(0.2, threading.Event(), sair=saidas.append)
    assert saidas == [0]
    terminou = threading.Event()
    terminou.set()
    serve.encerrar_em(0.2, terminou, sair=saidas.append)
    assert saidas == [0]
