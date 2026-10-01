"""
Jogo com FTN pendente: o nflverse publica o FTN charting 2 a 3 dias depois
do jogo, e até lá o jogo já está no play-by-play sem formação. Dados sintéticos.
"""

import sys

import pandas as pd

from conftest import ROOT

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl")]
import montar  # noqa: E402


def _jogadas(*jogos):
    """Duas jogadas por jogo: (game_id, semana)."""
    return pd.DataFrame([{"game_id": g, "week": w} for g, w in jogos for _ in range(2)])


def _pendentes(p, com_ftn, ano=2026):
    r = montar._ftn_pendente(p, set(com_ftn), ano)
    return sorted(p.loc[r, "game_id"].unique())


def test_pendente_so_a_partir_da_ultima_semana_com_ftn():
    p = _jogadas(("A", 1), ("B", 2), ("C", 3), ("D", 3), ("E", 4))
    # FTN até o jogo de quinta da semana 3 (C): D e E ainda não saíram.
    assert _pendentes(p, {"A", "B", "C"}) == ["D", "E"]


def test_buraco_antigo_nao_e_pendente():
    # B (semana 2) nunca saiu, mas a semana 3 já saiu: B é "indisponível", não pendente.
    p = _jogadas(("A", 1), ("B", 2), ("C", 3))
    assert _pendentes(p, {"A", "C"}) == []


def test_temporada_sem_ftn_ainda_tem_tudo_pendente():
    p = _jogadas(("A", 1), ("B", 1))
    assert _pendentes(p, set()) == ["A", "B"]


def test_temporada_anterior_ao_ftn_nunca_e_pendente():
    p = _jogadas(("A", 1), ("B", 1))
    assert _pendentes(p, set(), ano=2021) == []


def test_tudo_publicado_nada_pendente():
    p = _jogadas(("A", 1), ("B", 2))
    r = montar._ftn_pendente(p, {"A", "B"}, 2026)
    assert r.dtype == bool and not r.any()
