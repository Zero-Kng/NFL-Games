"""Tarefa 3: CacheDeRespostas isolado (sem servidor)."""

import json
import sys
import threading
import time

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "server"))
from response_cache import CacheDeRespostas  # noqa: E402


def test_hit_devolve_o_mesmo_conteudo():
    c = CacheDeRespostas()
    r1, hit1 = c.get_or_build("/a", lambda: {"x": 1.5, "nome": "Mahomes"})
    r2, hit2 = c.get_or_build("/a", lambda: pytest.fail("nao deveria reconstruir"))
    assert (hit1, hit2) == (False, True)
    assert r1 is r2
    assert json.loads(r2.corpo()) == {"x": 1.5, "nome": "Mahomes"}
    assert r1.etag.startswith('"') and r1.raw_size == len(r1.corpo())


def test_single_flight_10_threads_constroem_uma_vez():
    """1.3: 10 usuarios no mesmo jogo -> 1 calculo, 10 respostas identicas."""
    c = CacheDeRespostas()
    chamadas = []
    largada = threading.Barrier(10)

    def lento():
        chamadas.append(1)
        time.sleep(0.2)
        return {"jogo": 2021090900}

    resultados = []

    def usuario():
        largada.wait()
        resultados.append(c.get_or_build("/api/games/2021090900", lento)[0])

    ts = [threading.Thread(target=usuario) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(chamadas) == 1
    assert len(resultados) == 10
    assert all(r is resultados[0] for r in resultados)


def test_cache_excecao_nao_envenena_nem_bloqueia_outras_chaves():
    """1.5: um erro chega a quem esperava, nada e guardado, a proxima tenta de novo."""
    c = CacheDeRespostas()
    liberar = threading.Event()
    erros = []

    def falha():
        liberar.wait(2)
        raise ValueError("dado ruim")

    def pedir():
        try:
            c.get_or_build("/ruim", falha)
        except ValueError as e:
            erros.append(e)

    ts = [threading.Thread(target=pedir) for _ in range(3)]
    [t.start() for t in ts]
    time.sleep(0.1)
    # enquanto "/ruim" esta travada, outra chave responde normalmente
    t0 = time.perf_counter()
    r, _ = c.get_or_build("/boa", lambda: {"ok": True})
    assert time.perf_counter() - t0 < 0.1
    assert json.loads(r.corpo()) == {"ok": True}
    liberar.set()
    [t.join() for t in ts]
    assert len(erros) == 3
    assert c.stats()["itens"] == 1  # so "/boa"
    r, hit = c.get_or_build("/ruim", lambda: {"agora": "funciona"})
    assert hit is False and json.loads(r.corpo()) == {"agora": "funciona"}


def test_lru_despeja_o_mais_antigo_quando_passa_do_limite():
    import os
    c = CacheDeRespostas(max_bytes=4000)
    ruido = lambda: {"d": os.urandom(1500).hex()}  # noqa: E731 -- nao comprime
    c.get_or_build("/1", ruido)
    c.get_or_build("/2", ruido)
    c.get_or_build("/1", ruido)  # /1 vira o mais recente
    c.get_or_build("/3", ruido)  # estoura: sai /2, o menos usado
    assert c.stats()["bytes"] <= 4000
    assert c.get_or_build("/1", lambda: pytest.fail("/1 deveria estar no cache"))[1] is True
    assert c.get_or_build("/2", ruido)[1] is False


def test_aquecer_pula_falhas_e_loga_inicio_e_fim():
    c = CacheDeRespostas()
    linhas = []

    def quebra():
        raise RuntimeError("x")

    t = c.aquecer([("/a", lambda: 1), ("/b", quebra), ("/c", lambda: 3)], log=linhas.append, pausa_s=0)
    t.join(5)
    assert linhas[0] == "aquecimento: inicio"
    assert any("falhou /b" in l for l in linhas)
    assert linhas[-1].startswith("aquecimento: concluido")
    assert c.stats()["itens"] == 2
