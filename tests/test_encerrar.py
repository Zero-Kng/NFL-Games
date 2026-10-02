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


def test_servidor_responde_sem_stderr(monkeypatch):
    """Important 2 (segunda camada): com sys.stderr None, o servidor ainda responde."""
    from http.server import ThreadingHTTPServer
    from servidor_local import porta_livre
    monkeypatch.setattr(sys, "stderr", None)
    porta = porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), serve.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, estado = http_json(f"http://127.0.0.1:{porta}/api/estado")
        assert status == 200 and estado["app"] == "NFL Games"
    finally:
        srv.shutdown()
        srv.server_close()


def test_estado_diz_se_esta_sem_terminal():
    """Important 3: a tela de carregamento precisa saber se há terminal para indicar onde ver o erro."""
    assert serve.ESTADO.get("semTerminal") is False


# ------------------------------------------------ itens menores da revisão final
def _servidor_em_processo():
    from http.server import ThreadingHTTPServer
    from servidor_local import porta_livre
    porta = porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), serve.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, porta


def test_post_erro_inesperado_responde_500(monkeypatch):
    """Item 1: um erro inesperado no POST responde 500, como o GET, em vez de derrubar a conexão."""
    class Quebrada:
        def sinal(self, aba):
            raise RuntimeError("falha simulada")
    monkeypatch.setattr(serve, "PRESENCA", Quebrada())
    srv, porta = _servidor_em_processo()
    try:
        status, _, corpo = pedir(f"http://127.0.0.1:{porta}/api/presenca", corpo={"aba": "t", "saiu": False},
                                 cabecalhos=APP)
        assert status == 500 and json.loads(corpo)["error"] == "erro interno no servidor"
    finally:
        srv.shutdown()
        srv.server_close()


def test_corpo_incompleto_nao_prende_a_thread(monkeypatch):
    """Item 2: Content-Length maior que o corpo não prende a thread para sempre."""
    import socket
    assert serve.Handler.timeout == 10
    monkeypatch.setattr(serve.Handler, "timeout", 1)
    srv, porta = _servidor_em_processo()
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as s:
            s.sendall(b"POST /api/presenca HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-NFL-App: 1\r\n"
                      b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{\"aba\"" % porta)
            t0 = time.time()
            while s.recv(4096):
                pass                                   # o servidor desiste e fecha a conexão
            assert time.time() - t0 < 4
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize("host, esperado", [
    ("127.0.0.1:8000", True), ("localhost:8000", True), (None, True),
    ("exemplo.com:8000", False), ("127.0.0.1:9999", False),
])
def test_pedido_confiavel_confere_o_host(host, esperado):
    """Item 6: com DNS rebinding num navegador sem Origin, o Host denuncia o site de fora."""
    cab = {"X-NFL-App": "1", **({"Host": host} if host else {})}
    assert serve.pedido_confiavel("127.0.0.1", cab, 8000) is esperado
