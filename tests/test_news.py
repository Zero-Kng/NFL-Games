"""
Tarefa 1 (novo-visual v0.4): notícias geradas dos dados e o resumo.

Os limiares e o placar são conferidos de forma independente, recalculando a
partir das tabelas montadas (não do código que gera as notícias).
"""

import sys

import pandas as pd
import pytest

from conftest import ROOT, http_json

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl")]
DADOS = ROOT / "dados"
pytestmark = pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")

import data_layer  # noqa: E402
import tabela_npz  # noqa: E402

TIPOS = {"resultado", "virada", "prorrogacao", "goleada", "maior_jogada", "atuacao", "defesa"}
CAMPOS = {"id", "gameId", "season", "week", "rodada", "tipo", "tom", "tag", "destaque", "titulo", "texto",
          "incomum", "times"}


@pytest.fixture(scope="module")
def nfl():
    return data_layer.NFLData(DADOS)


def _obj(df):
    return df.astype({c: object for c in df if isinstance(df[c].dtype, pd.CategoricalDtype)})


@pytest.fixture(scope="module")
def tabelas():
    jogos = _obj(tabela_npz.carregar(DADOS / "jogos.npz"))
    jj = _obj(tabela_npz.carregar(DADOS / "temporadas" / "2024" / "jogador_jogo.npz"))
    jogadas = _obj(tabela_npz.carregar(DADOS / "temporadas" / "2024" / "jogadas.npz"))
    return jogos, jj, jogadas


def test_news_so_tipos_permitidos_e_campos(nfl):
    todas = nfl.news(2024)
    assert todas and {n["tipo"] for n in todas} <= TIPOS
    assert all(set(n) == CAMPOS for n in todas)
    assert len({n["id"] for n in todas}) == len(todas)                  # id estável e único
    assert all(0 <= n["incomum"] <= 1 for n in todas)


def test_news_ordenadas_por_incomum(nfl):
    semana = nfl.news(2024, 5)
    assert [n["incomum"] for n in semana] == sorted((n["incomum"] for n in semana), reverse=True)


def test_news_resultado_com_placar_oficial(nfl):
    """7.1: o resultado diz quem venceu, pelo placar oficial (TB 31 x 29 DAL, que o dataset antigo errava)."""
    tb = next(n for n in nfl.news(2021, 1) if n["tipo"] == "resultado" and n["gameId"] == 2021090900)
    assert tb["titulo"] == "TB vence DAL por 31–29"
    for n in nfl.news(2024, 3):
        if n["tipo"] != "resultado":
            continue
        g = next(x for x in nfl.games_list(2024, 3) if x["gameId"] == n["gameId"])
        placar = sorted([g["home"]["score"], g["away"]["score"]], reverse=True)
        assert f"{placar[0]}–{placar[1]}" in n["titulo"]


def test_news_limiares(nfl, tabelas):
    """Cada notícia especial respeita o seu limiar, recalculado direto das tabelas."""
    jogos, jj, jogadas = tabelas
    todas = nfl.news(2024)
    por_jogo = {g: d for g, d in jogadas.groupby("gameId")}
    placar = jogos.set_index("gameId")
    for n in todas:
        g = placar.loc[n["gameId"]]
        margem = abs(g["home_score"] - g["away_score"])
        if n["tipo"] == "goleada":
            assert margem >= 28
        elif n["tipo"] == "prorrogacao":
            assert g["overtime"] == 1
        elif n["tipo"] == "virada":
            d = por_jogo[n["gameId"]].sort_values("seq")
            diff = d["total_home_score"] - d["total_away_score"]
            deficit = -diff.min() if g["home_score"] > g["away_score"] else diff.max()
            assert deficit >= 10 and str(int(deficit)) in n["titulo"]
        elif n["tipo"] == "defesa":
            d = por_jogo[n["gameId"]]
            d = d[d["play_type"].isin(["pass", "run"])]
            time = n["id"].split(":")[2]
            do_time = d[d["defteam"] == time]
            assert do_time["sack"].sum() >= 6 or do_time["interception"].sum() >= 3
        elif n["tipo"] == "atuacao":
            pid = n["id"].split(":")[2]
            r = jj[(jj["gameId"] == n["gameId"]) & (jj["playerId"] == pid)].iloc[0]
            assert (r["passing_yards"] >= 400 or r["passing_tds"] >= 5 or r["rushing_yards"] >= 175
                    or r["receiving_yards"] >= 175 or (r["rushing_tds"] or 0) + (r["receiving_tds"] or 0) >= 4
                    or r["def_sacks"] >= 3.5)
    assert {n["tipo"] for n in todas} >= {"resultado", "virada", "goleada", "atuacao", "defesa", "maior_jogada"}


def test_news_maior_jogada_uma_por_semana(nfl, tabelas):
    _jogos, _jj, jogadas = tabelas
    esc = jogadas[jogadas["play_type"].isin(["pass", "run"])]
    for w in (1, 9, 22):
        maiores = [n for n in nfl.news(2024, w) if n["tipo"] == "maior_jogada"]
        assert len(maiores) == 1
        jardas = int(esc[esc["week"] == w]["yards_gained"].max())
        assert maiores[0]["destaque"] == str(jardas) and f"{jardas} jardas" in maiores[0]["titulo"]


@pytest.mark.parametrize("ano", [2021, 2022, 2023, 2024, 2025])
def test_news_toda_semana_disputada_tem_noticia(nfl, ano):
    """7.6 e o risco do design: pelo menos 1 notícia por semana disputada, no máximo 40."""
    for w in sorted({g["week"] for g in nfl.games_list(ano)}):
        n = len(nfl.news(ano, w))
        assert 1 <= n <= 40, (ano, w, n)


def test_news_semana_sem_jogos_disputados_vazia(nfl):
    ultima = max(g["week"] for g in nfl.games_list(2026))
    if all(g["status"] != "encerrado" for g in nfl.games_list(2026, ultima)):
        assert nfl.news(2026, ultima) == []


def test_news_referencia_o_jogo(nfl):
    """7.2: cada notícia aponta para um jogo da semana, com os dois times."""
    jogos = {g["gameId"]: g for g in nfl.games_list(2025, 22)}
    for n in nfl.news(2025, 22):
        g = jogos[n["gameId"]]
        assert n["season"] == 2025 and n["week"] == 22 and n["rodada"] == "Super Bowl"
        assert n["times"] == [g["away"]["abbr"], g["home"]["abbr"]]


def test_summary_rated_players(nfl):
    """4.3: jogadores com avaliação na temporada."""
    t = nfl.temporadas[2024].jogadores
    assert nfl.summary(2024) == {"season": 2024, "ratedPlayers": int(t["avaliado"].sum())}


# ------------------------------------------------------------------ rotas
def test_rotas_news_e_summary(servidor):
    s, semana = http_json(servidor.url + "/api/news?season=2024&week=1")
    assert s == 200 and semana and semana[0]["week"] == 1
    s, todas = http_json(servidor.url + "/api/news?season=2024")
    assert s == 200 and len(todas) > len(semana)
    s, resumo = http_json(servidor.url + "/api/summary?season=2024")
    assert s == 200 and resumo["season"] == 2024 and resumo["ratedPlayers"] > 500
    s, meta = http_json(servidor.url + "/api/meta")
    assert http_json(servidor.url + "/api/summary")[1]["season"] == meta["season"]


@pytest.mark.parametrize("url,status", [("/api/news?week=abc", 400), ("/api/news?season=2019", 404),
                                        ("/api/summary?season=2019", 404)])
def test_rotas_news_caminho_infeliz(servidor, url, status):
    assert http_json(servidor.url + url)[0] == status
