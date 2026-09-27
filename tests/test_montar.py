"""
Tarefa 3 (dados-externos): tabelas montadas a partir das fontes reais.

Lê as tabelas prontas em dados/ (não os brutos, que são descartados nas
temporadas encerradas). Pula se ainda não houver dados montados.
"""

import sys

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl")]
import tabela_npz  # noqa: E402

DADOS = ROOT / "dados"
ANOS = range(2021, 2027)
pytestmark = pytest.mark.skipif(not (DADOS / "jogos.npz").exists(),
                                reason="dados ainda não montados (rode python etl/montar.py)")


@pytest.fixture(scope="module")
def jogos():
    return tabela_npz.carregar(DADOS / "jogos.npz")


@pytest.fixture(scope="module")
def jogadas():
    return {a: tabela_npz.carregar(DADOS / "temporadas" / str(a) / "jogadas.npz") for a in ANOS}


@pytest.fixture(scope="module")
def jogador_jogo():
    return {a: tabela_npz.carregar(DADOS / "temporadas" / str(a) / "jogador_jogo.npz") for a in ANOS}


def test_temporadas_2021_a_2026_com_playoffs(jogos):
    assert sorted(jogos["season"].unique()) == list(ANOS)
    for ano in range(2021, 2026):   # temporadas encerradas: playoffs completos (12 jogos + Super Bowl = 13)
        t = jogos[jogos["season"] == ano]
        assert (t["game_type"] != "REG").sum() == 13, ano


def test_rodadas_de_playoff_com_nome(jogos):
    nomes = set(jogos.loc[jogos["game_type"] != "REG", "rodada"].astype(str))
    assert nomes == {"Wild Card", "Divisional", "Final de Conferência", "Super Bowl"}
    assert jogos.loc[jogos["game_type"] == "REG", "rodada"].astype(str).str.startswith("Semana ").all()


def test_tb_dal_2021_31_29(jogos):
    j = jogos[jogos["gameId"] == 2021090900].iloc[0]
    assert (j["away"], j["away_score"], j["home"], j["home_score"]) == ("DAL", 29, "TB", 31)
    assert str(j["espnId"]) == "401326322"


@pytest.mark.parametrize("ano", list(ANOS))
def test_placar_oficial_confere_com_ultimo_lance(jogos, jogadas, ano):
    jd = jogadas[ano]
    ult = jd.sort_values(["gameId", "seq"]).groupby("gameId")[["total_home_score", "total_away_score"]].last()
    of = jogos.set_index("gameId").loc[ult.index]
    diverge = of[(of["home_score"] != ult["total_home_score"]) | (of["away_score"] != ult["total_away_score"])]
    assert diverge.empty, f"{len(diverge)} jogos com placar diferente do último lance: {list(diverge.index[:5])}"


@pytest.mark.parametrize("ano", list(ANOS))
def test_ordem_cronologica_placar_nunca_diminui(jogadas, ano):
    """O play_id não é cronológico em parte dos jogos; a ordem (seq) vem do order_sequence."""
    jd = jogadas[ano].sort_values(["gameId", "seq"])
    for col in ("total_home_score", "total_away_score"):
        assert (jd.groupby("gameId")[col].diff().fillna(0) >= 0).all(), col


def test_jogadas_incluem_corridas_chutes_retornos(jogadas):
    tipos = set(jogadas[2025]["play_type"].astype(str))
    assert {"pass", "run", "punt", "field_goal", "kickoff", "extra_point"} <= tipos


def test_prorrogacao_marcada(jogos):
    assert (jogos["overtime"] == 1).sum() > 0
    assert set(jogos["overtime"].dropna().unique()) <= {0.0, 1.0}


def test_jogo_futuro_sem_placar(jogos):
    futuros = jogos[(jogos["season"] == 2026) & jogos["home_score"].isna()]
    assert len(futuros) > 0
    assert futuros["gameday"].notna().all() and futuros["gametime"].notna().all()


def test_formacao_e_jogadores_por_temporada(jogadas):
    """2021-2025: formação + nomes (2021-22 via elenco da temporada); 2026: só FTN, sem nomes."""
    for ano in range(2021, 2026):
        jd = jogadas[ano]
        lances = jd[jd["play_type"].astype(str).isin(["pass", "run"])]
        assert lances["formacao"].notna().mean() > 0.9, ano
        assert lances["of_nomes"].notna().mean() > 0.9, ano
    jd = jogadas[2026]
    lances = jd[jd["play_type"].astype(str).isin(["pass", "run"])]
    assert lances["of_nomes"].isna().all()
    assert lances["qb_local"].notna().mean() > 0.9


def test_nomes_de_2021_vem_do_elenco(jogadas):
    jd = jogadas[2021]
    j = jd[(jd["gameId"] == 2021090900) & jd["of_nomes"].astype(str).str.contains("Tom Brady")]
    assert len(j) > 0
    linha = j.iloc[0]
    nomes = str(linha["of_nomes"]).split(";")
    pos = str(linha["of_posicoes"]).split(";")
    num = str(linha["of_numeros"]).split(";")
    assert len(nomes) == len(pos) == len(num) == 11
    i = nomes.index("Tom Brady")
    assert (pos[i], num[i]) == ("QB", "12")


def test_jogador_jogo_inclui_linha_ofensiva(jogador_jogo):
    jj = jogador_jogo[2025]
    ol = jj[jj["position"].astype(str).isin(["T", "G", "C"])]
    assert ol["playerId"].nunique() > 150
    # Todo registro de OL tem snaps; ~19% são só de times especiais (reservas no field goal/extra point).
    snaps = ol[["offense_snaps", "st_snaps"]].fillna(0).sum(axis=1)
    assert (snaps > 0).all()


def test_jogador_jogo_traz_posicao_do_depth_chart(jogador_jogo):
    """Base do grupo Edge (ratings): o elenco separa OLB × ILB e DE × DT; os brutos são descartados depois."""
    jj = jogador_jogo[2025]
    dc = jj.dropna(subset=["posicao_elenco"]).drop_duplicates("playerId").set_index("playerId")["posicao_elenco"]
    assert {"DE", "DT", "OLB", "ILB", "MLB"} <= set(dc.astype(str))
    assert dc["00-0036932"] == "OLB" and dc["00-0034815"] == "MLB"     # Micah Parsons, Fred Warner


@pytest.mark.parametrize("ano", list(ANOS))
def test_jogador_jogo_sempre_com_id(jogador_jogo, ano):
    assert jogador_jogo[ano]["playerId"].notna().all()


# ------------------------------------------------------ cópia completa (carga interrompida)
def _temporada(pasta, completa=True, origem=True):
    pasta.mkdir(parents=True)
    for f in ("jogadas.npz", "jogador_jogo.npz") + (("jogadores.npz",) if completa else ()):
        (pasta / f).write_bytes(b"x")
    if origem:
        (pasta / "origem.json").write_text("{}")


def test_temporadas_faltando_numa_carga_interrompida(tmp_path, monkeypatch):
    """Só está pronta a cópia com todas as temporadas de 2021 até a atual montadas até o fim
    (os 3 .npz e o origem.json, gravado por último)."""
    import fontes
    import montar
    monkeypatch.setattr(fontes, "temporada_atual", lambda hoje=None: 2023)
    (tmp_path / "jogos.npz").write_bytes(b"x")
    _temporada(tmp_path / "temporadas" / "2021")
    _temporada(tmp_path / "temporadas" / "2022", completa=False)            # parou no meio
    assert montar.temporadas_faltando(tmp_path) == [2022, 2023]
    _temporada(tmp_path / "temporadas" / "2023", origem=False)              # sem o marcador final
    (tmp_path / "temporadas" / "2022" / "jogadores.npz").write_bytes(b"x")
    assert montar.temporadas_faltando(tmp_path) == [2023]
    (tmp_path / "temporadas" / "2023" / "origem.json").write_text("{}")
    assert montar.temporadas_faltando(tmp_path) == []
    (tmp_path / "jogos.npz").unlink()                                       # sem o calendário, nada está pronto
    assert montar.temporadas_faltando(tmp_path) == [2021, 2022, 2023]


# ------------------------------------------------ site-publico, tarefa 6 (3.4)
def _sincronizacao_falsa(falhas):
    from types import SimpleNamespace
    sinc = SimpleNamespace(falhas=list(falhas), baixados=[])
    mont = SimpleNamespace(segundos=1.0, temporadas=[], globais=[], liberado_bytes=0)
    return lambda progresso=print: (sinc, mont)


@pytest.mark.parametrize("argv, falhas, codigo", [
    ([], ["pbp: sem acesso à fonte"], 0),               # o app do PC segue com a cópia local
    (["--estrito"], ["pbp: sem acesso à fonte"], 1),    # o Actions não publica e avisa
    (["--estrito"], [], 0),
])
def test_main_estrito_falha_quando_uma_fonte_falha(argv, falhas, codigo):
    import montar
    assert montar.main(argv, sincronizar=_sincronizacao_falsa(falhas)) == codigo
