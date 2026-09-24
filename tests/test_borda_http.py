"""Tarefa 2: borda HTTP (admissao, 503, estaticos com ETag, path traversal)."""

import http.client
import os
import shutil
import sys
import threading
import time
from urllib.parse import urlparse

from conftest import ROOT, http_get
from servidor_local import servidor as subir_servidor

APP = ROOT / "app"


def get_bruto(base: str, path: str) -> tuple[int, bytes]:
    """GET sem normalizar o caminho (urllib resolveria o '../' no cliente)."""
    u = urlparse(base)
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
    try:
        c.request("GET", path)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


# ------------------------------------------------------------------ S.1 ----
def test_estatico_fora_de_app_403(servidor):
    status, _ = get_bruto(servidor.url, "/../server/serve.py")
    assert status == 403


def test_estatico_pasta_vizinha_com_prefixo_igual_403(servidor):
    # Com a checagem antiga (str.startswith) "app2/" passava por comecar com "app".
    vizinha = ROOT / "app2"
    assert not vizinha.exists(), "pasta app2/ ja existe; o teste nao quer apaga-la"
    vizinha.mkdir()
    try:
        (vizinha / "segredo.txt").write_text("nao deveria ser servido")
        status, corpo = get_bruto(servidor.url, "/../app2/segredo.txt")
        assert status == 403
        assert b"nao deveria" not in corpo
    finally:
        shutil.rmtree(vizinha)


# ------------------------------------------------------------------ S.2 ----
def test_parametro_invalido_400(servidor):
    for _ in range(2):  # a 2a vez tambem: erro nunca vira resposta guardada
        status, h, corpo = http_get(servidor.url + "/api/games?week=abc")
        assert status == 400
        assert b"inteiro" in corpo
        assert h.get("X-Cache") in (None, "MISS")


# --------------------------------------------------------------- 4.3 / 4.4 ----
def test_estatico_revalidado_com_304(servidor):
    status, h, corpo = http_get(servidor.url + "/js/app.js")
    assert status == 200 and corpo
    assert h["Cache-Control"] == "no-cache"
    etag = h["ETag"]
    status, h2, corpo2 = http_get(servidor.url + "/js/app.js", {"If-None-Match": etag})
    assert status == 304
    assert corpo2 == b""
    assert h2["ETag"] == etag


def test_estatico_alterado_devolve_200_com_etag_nova(servidor):
    arq = APP / "_teste_etag.txt"
    try:
        arq.write_text("versao 1")
        _, h, _ = http_get(servidor.url + "/_teste_etag.txt")
        etag1 = h["ETag"]
        arq.write_text("versao 2 (diferente)")
        st = arq.stat()
        os.utime(arq, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))  # garante mtime novo
        status, h, corpo = http_get(servidor.url + "/_teste_etag.txt", {"If-None-Match": etag1})
        assert status == 200
        assert corpo == b"versao 2 (diferente)"
        assert h["ETag"] != etag1
    finally:
        arq.unlink(missing_ok=True)


# ------------------------------------------------------------ 1.4 / S.3 ----
def test_api_responde_503_quando_lotado():
    # 1 vaga + 600 ms de atraso artificial: a 1a requisicao segura a vaga.
    with subir_servidor(args=("--max-pendentes", "1"), env={"NFL_ATRASO_API_MS": "600"}) as srv:
        primeira = {}
        t = threading.Thread(target=lambda: primeira.update(r=http_get(srv.url + "/api/meta")))
        t.start()
        time.sleep(0.2)
        status, h, corpo = http_get(srv.url + "/api/meta")
        t.join()
        assert status == 503
        assert h.get("Retry-After") == "2"
        assert b"ocupado" in corpo
        assert primeira["r"][0] == 200  # a que tinha vaga termina normalmente
        # vaga liberada: volta a atender
        assert http_get(srv.url + "/api/meta")[0] == 200


# ------------------------------------------------------------------ S.4 ----
def test_host_padrao_e_localhost():
    sys.path.insert(0, str(ROOT / "server"))
    import serve

    assert serve.parser().parse_args([]).host == "127.0.0.1"
