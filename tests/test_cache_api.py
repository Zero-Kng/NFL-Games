"""Tarefa 4: cache de respostas ligado nas rotas da API."""

import gzip
import json
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from conftest import http_get
from golden import ARQUIVO, impressao


def test_api_envia_x_query_time_e_x_cache(servidor):
    url = servidor.url + "/api/leaders?metric=snaps&role=Coverage&limit=7"
    _, h1, c1 = http_get(url)
    _, h2, c2 = http_get(url)
    assert h1["X-Cache"] == "MISS" and h2["X-Cache"] == "HIT"
    assert h1["X-Query-Time"].endswith("ms") and h2["X-Query-Time"].endswith("ms")
    assert c1 == c2


def test_chave_ignora_ordem_e_parametros_desconhecidos(servidor):
    base = servidor.url + "/api/leaders"
    _, h1, c1 = http_get(base + "?role=Pass&metric=intRate&limit=3")
    _, h2, c2 = http_get(base + "?limit=3&metric=intRate&role=Pass&lixo=123")
    assert h2["X-Cache"] == "HIT"
    assert c1 == c2


def test_gzip_e_sem_gzip_devolvem_o_mesmo_json(servidor):
    url = servidor.url + "/api/games?week=2"
    _, h, zipado = http_get(url, {"Accept-Encoding": "gzip"})
    _, _, puro = http_get(url)
    assert h.get("Content-Encoding") == "gzip"
    assert json.loads(gzip.decompress(zipado)) == json.loads(puro)


def test_respostas_concorrentes_iguais_ao_golden(servidor):
    """1.3: 10 usuarios ao mesmo tempo recebem exatamente o mesmo que 1 sozinho."""
    fotos = json.loads(ARQUIVO.read_text(encoding="utf-8"))["urls"]
    rnd = random.Random(7)
    urls = rnd.sample([u for u, f in fotos.items() if f["status"] == 200], 60)
    pedidos = urls * 3  # cada URL pedida 3x, misturadas entre 10 threads
    rnd.shuffle(pedidos)

    def pedir(u):
        with urllib.request.urlopen(servidor.url + u, timeout=60) as r:
            return u, impressao(r.status, r.read())

    with ThreadPoolExecutor(10) as ex:
        diverge = [u for u, imp in ex.map(pedir, pedidos) if imp != fotos[u]]
    assert diverge == []
