"""Tarefa 6: tracking lido do .npz, com fallback para o CSV (2.4, 2.5)."""

import json
import sys
import time

import pytest

from conftest import ROOT, http_get

sys.path.insert(0, str(ROOT / "server"))
from data_layer import NFLData  # noqa: E402

DADOS = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
JOGO = 2021090900
canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False)  # noqa: E731


@pytest.fixture(scope="module")
def nfl():
    return NFLData(DADOS, ROOT / "cache")


@pytest.fixture
def jogada(nfl):
    return int(nfl.game_plays(JOGO)[3]["playId"])


def _limpar_lru(nfl):
    nfl._tracking_cache.clear()


def test_npz_corrompido_cai_no_csv(nfl, jogada, tmp_path, monkeypatch, capsys):
    esperado = canon(nfl.play_tracking(JOGO, jogada))
    (tmp_path / "tracking").mkdir()
    ruim = tmp_path / "tracking" / f"{JOGO}.npz"
    ruim.write_bytes(b"isto nao e um zip")
    monkeypatch.setattr(nfl, "cache_dir", tmp_path)
    _limpar_lru(nfl)
    try:
        assert canon(nfl.play_tracking(JOGO, jogada)) == esperado
        assert "ilegivel" in capsys.readouterr().out
        # apagado: o ensure_cache da proxima subida regenera este jogo
        assert not ruim.exists()
    finally:
        _limpar_lru(nfl)


def test_sem_npz_usa_o_csv_sem_aviso(nfl, jogada, tmp_path, monkeypatch, capsys):
    esperado = canon(nfl.play_tracking(JOGO, jogada))
    monkeypatch.setattr(nfl, "cache_dir", tmp_path)  # sem pasta tracking/
    _limpar_lru(nfl)
    try:
        assert canon(nfl.play_tracking(JOGO, jogada)) == esperado
        assert "ilegivel" not in capsys.readouterr().out
    finally:
        _limpar_lru(nfl)


def test_sem_npz_e_sem_csv_404(nfl, jogada, tmp_path, monkeypatch):
    monkeypatch.setattr(nfl, "cache_dir", tmp_path)
    monkeypatch.setattr(nfl, "tracking_dir", tmp_path)
    _limpar_lru(nfl)
    try:
        assert nfl.play_tracking(JOGO, jogada) is None      # a rota transforma em 404
        # os outros jogos seguem sendo servidos normalmente
        monkeypatch.undo()
        assert nfl.play_tracking(JOGO, jogada) is not None
    finally:
        _limpar_lru(nfl)


def test_jogada_sem_tracking_404_rapido(servidor):
    """2.4: com o jogo ja aberto por alguem, a jogada inexistente responde em ate 20 ms."""
    base = f"{servidor.url}/api/games/{JOGO}/plays"
    _, _, corpo = http_get(base)
    primeira = json.loads(corpo)[0]["playId"]
    assert http_get(f"{base}/{primeira}/tracking")[0] == 200
    tempos = []
    for _ in range(5):
        t = time.perf_counter()
        status, _, corpo = http_get(f"{base}/1/tracking")
        tempos.append((time.perf_counter() - t) * 1000)
        assert status == 404 and b"tracking indisponivel" in corpo
    assert sorted(tempos)[2] <= 20, f"mediana {sorted(tempos)[2]:.0f} ms"
