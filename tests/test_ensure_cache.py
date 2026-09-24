"""Tarefa 5: preparacao incremental do cache (6.3, 6.4 e a restricao de novas fontes)."""

import json
import os
import shutil
import sys
import time

import pandas as pd
import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "etl"))
import build_metrics as etl  # noqa: E402

DADOS = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
JOGOS = [2021090900, 2021091200, 2021091201]


def _recortar(origem, destino, jogadas=3):
    """Copia um CSV de tracking so com as primeiras N jogadas (teste rapido)."""
    df = pd.read_csv(origem)
    df[df["playId"].isin(df["playId"].unique()[:jogadas])].to_csv(destino, index=False)


@pytest.fixture
def dataset(tmp_path):
    """Dataset em miniatura com 2 jogos; o 3o fica guardado para simular 'jogo novo'."""
    data = tmp_path / "data"
    (data / "tracking").mkdir(parents=True)
    pff = pd.read_csv(DADOS / "pffScoutingData.csv")
    pff[pff["gameId"].isin(JOGOS)].to_csv(data / "pffScoutingData.csv", index=False)
    for g in JOGOS[:2]:
        _recortar(DADOS / "tracking" / f"tracking_{g}.csv", data / "tracking" / f"tracking_{g}.csv")
    reserva = tmp_path / "reserva.csv"
    _recortar(DADOS / "tracking" / f"tracking_{JOGOS[2]}.csv", reserva)
    return data, tmp_path / "cache", reserva


def _rodar(data, cache):
    return etl.ensure_cache(data, cache, progress=lambda m: None)


def test_primeira_vez_processa_todos_e_gera_os_arquivos(dataset):
    data, cache, _ = dataset
    rel = _rodar(data, cache)
    assert sorted(rel.processados) == JOGOS[:2]
    for g in JOGOS[:2]:
        assert all(f.exists() for f in etl._arquivos_do_jogo(cache, g))
    timing = pd.read_csv(cache / "play_timing.csv")
    assert sorted(timing["gameId"].unique()) == JOGOS[:2]
    assert json.loads((cache / "manifest.json").read_text())["etlVersion"] == etl.ETL_VERSION


def test_ensure_cache_sem_mudancas_nao_reprocessa(dataset):
    data, cache, _ = dataset
    _rodar(data, cache)
    rel = _rodar(data, cache)
    assert rel.processados == [] and rel.reaproveitados == 2 and not rel.mudou


def test_ensure_cache_jogo_novo_processa_so_ele(dataset):
    data, cache, reserva = dataset
    _rodar(data, cache)
    shutil.copy(reserva, data / "tracking" / f"tracking_{JOGOS[2]}.csv")
    rel = _rodar(data, cache)
    assert rel.processados == [JOGOS[2]]
    assert rel.reaproveitados == 2
    timing = pd.read_csv(cache / "play_timing.csv")
    assert sorted(timing["gameId"].unique()) == JOGOS


def test_ensure_cache_csv_alterado_reprocessa_so_ele(dataset):
    data, cache, _ = dataset
    _rodar(data, cache)
    alvo = data / "tracking" / f"tracking_{JOGOS[0]}.csv"
    _recortar(DADOS / "tracking" / f"tracking_{JOGOS[0]}.csv", alvo, jogadas=2)
    os.utime(alvo, ns=(time.time_ns(), time.time_ns() + 10**9))
    rel = _rodar(data, cache)
    assert rel.processados == [JOGOS[0]]
    timing = pd.read_csv(cache / "play_timing.csv")
    assert (timing["gameId"] == JOGOS[0]).sum() == 2  # o agregado reflete a mudanca


def test_ensure_cache_npz_apagado_e_regenerado(dataset):
    data, cache, _ = dataset
    _rodar(data, cache)
    (cache / "tracking" / f"{JOGOS[1]}.npz").unlink()
    rel = _rodar(data, cache)
    assert rel.processados == [JOGOS[1]]
    assert (cache / "tracking" / f"{JOGOS[1]}.npz").exists()


def test_ensure_cache_versao_diferente_reprocessa_tudo(dataset, monkeypatch):
    data, cache, _ = dataset
    _rodar(data, cache)
    monkeypatch.setattr(etl, "ETL_VERSION", etl.ETL_VERSION + 1)
    assert sorted(_rodar(data, cache).processados) == JOGOS[:2]


def test_ensure_cache_sem_manifest_reprocessa_tudo(dataset):
    data, cache, _ = dataset
    _rodar(data, cache)
    (cache / "manifest.json").unlink()
    assert sorted(_rodar(data, cache).processados) == JOGOS[:2]


def test_ensure_cache_jogo_removido_sai_dos_agregados(dataset):
    data, cache, _ = dataset
    _rodar(data, cache)
    (data / "tracking" / f"tracking_{JOGOS[1]}.csv").unlink()
    rel = _rodar(data, cache)
    assert rel.removidos == [JOGOS[1]]
    assert sorted(pd.read_csv(cache / "play_timing.csv")["gameId"].unique()) == [JOGOS[0]]
    assert not (cache / "tracking" / f"{JOGOS[1]}.npz").exists()


def test_ensure_cache_sem_pasta_de_tracking_falha_explicito(tmp_path):
    with pytest.raises(FileNotFoundError):
        etl.ensure_cache(tmp_path / "nada", tmp_path / "cache", progress=lambda m: None)


@pytest.mark.lento
def test_primeiro_preparo_ate_90s(tmp_path):
    """6.3: os 122 jogos reais, do zero, numa pasta temporaria (~45 s, ~110 MB)."""
    mensagens = []
    rel = etl.ensure_cache(DADOS, tmp_path / "cache", progress=mensagens.append)
    assert len(rel.processados) == 122
    assert rel.segundos <= 90, f"preparo levou {rel.segundos:.0f}s"
    assert any("restantes" in m for m in mensagens)  # progresso visivel no terminal


def test_startup_com_cache_pronto_ate_5s(servidor):
    """6.2 (o cache real ja foi preparado; a fixture mede ate /api/meta responder)."""
    assert servidor.startup_s <= 5.0, f"startup levou {servidor.startup_s:.1f}s"
