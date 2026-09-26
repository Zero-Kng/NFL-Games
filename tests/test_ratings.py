"""Tarefa 4 (dados-externos): ratings por grupo de posição com dados públicos."""

import sys

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

sys.path[:0] = [str(ROOT / "etl"), str(ROOT / "server")]
import ratings  # noqa: E402
import tabela_npz  # noqa: E402

DADOS = ROOT / "dados"


def _jogos(times_jogos: dict[str, int], ano=2025):
    """Calendário sintético: cada time com N jogos disputados."""
    linhas, gid = [], 1
    for time, n in times_jogos.items():
        for _ in range(n):
            linhas.append({"gameId": gid, "season": ano, "home": time, "away": "ZZZ", "home_score": 10.0})
            gid += 1
    return pd.DataFrame(linhas)


def _qb(pid, time, jogos, tentativas_por_jogo, epa=0.1, ints=0, sacks=1):
    return [{"playerId": pid, "gameId": g, "time": time, "position": "QB", "attempts": tentativas_por_jogo,
             "completions": tentativas_por_jogo * 0.6, "passing_yards": tentativas_por_jogo * 7,
             "passing_epa": epa * tentativas_por_jogo, "passing_cpoe": 1.0, "passing_interceptions": ints,
             "sacks_suffered": sacks} for g in range(1, jogos + 1)]


BIO = pd.DataFrame({"playerId": [f"Q{i}" for i in range(6)], "nome": [f"QB {i}" for i in range(6)],
                    "posicao": ["QB"] * 6})


def test_minimo_proporcional_aos_jogos_do_time():
    # mínimo de QB = 15 dropbacks por jogo do time; o time jogou 4 -> 60 dropbacks
    jj = pd.DataFrame(_qb("Q0", "AAA", 4, 20) + _qb("Q1", "AAA", 2, 10))
    t = ratings.calcular(jj, _jogos({"AAA": 4}), BIO, 2025).set_index("playerId")
    assert t.loc["Q0", "minimo"] == 60 and t.loc["Q0", "avaliado"]          # 4 x (20+1) = 84 dropbacks
    assert not t.loc["Q1", "avaliado"] and np.isnan(t.loc["Q1", "rating"])  # 2 x 11 = 22 < 60 -> n/d


def test_rating_percentil_dentro_do_grupo_e_escala_40_99():
    jj = pd.DataFrame(sum((_qb(f"Q{i}", "AAA", 4, 30, epa=0.05 * i, ints=5 - i, sacks=5 - i) for i in range(5)), []))
    t = ratings.calcular(jj, _jogos({"AAA": 4}), BIO, 2025).set_index("playerId")
    r = t.loc[[f"Q{i}" for i in range(5)], "rating"]
    assert r.is_monotonic_increasing          # melhor em todos os eixos -> rating maior
    assert r.min() >= 40 and r.max() <= 99
    # eixo "menor é melhor" (interceptações) foi invertido: quem tem menos, percentil maior
    assert t.loc["Q4", "eixo3_pct"] > t.loc["Q0", "eixo3_pct"]


def test_eixo_sem_dado_fora_da_media_com_motivo():
    jj = pd.DataFrame(sum((_qb(f"Q{i}", "AAA", 4, 30, epa=0.05 * i) for i in range(4)), []))
    jj["passing_cpoe"] = np.nan                # CPOE inexistente na "temporada"
    t = ratings.calcular(jj, _jogos({"AAA": 4}), BIO, 2025)
    q = t[t["avaliado"]]
    assert q["eixo1_pct"].isna().all()
    assert (q["eixo1_motivo"] == "estatística indisponível nesta temporada").all()
    assert q["rating"].notna().all()           # o rating sai com os outros 4 eixos


def test_ol_base_reduzida():
    jj = pd.DataFrame([{"playerId": "O1", "gameId": g, "time": "AAA", "position": "G", "offense_snaps": 60,
                        "penalties": 0} for g in range(1, 5)])
    bio = pd.DataFrame({"playerId": ["O1"], "nome": ["Guarda"], "posicao": ["G"]})
    t = ratings.calcular(jj, _jogos({"AAA": 4}), bio, 2025).set_index("playerId")
    assert t.loc["O1", "grupo"] == "OL" and t.loc["O1", "baseReduzida"]


def test_todo_grupo_tem_eixos_e_minimo():
    assert set(ratings.EIXOS) == set(ratings.MINIMOS) == set(ratings.GRUPOS)
    assert all(len(e) in (4, 5, 6) for e in ratings.EIXOS.values())


def _defensor(pid, pos, dc, pressoes, alvos, jogos=4):
    return [{"playerId": pid, "gameId": g, "time": "AAA", "position": pos, "posicao_elenco": dc,
             "defense_snaps": 50, "def_pressures": pressoes, "def_targets": alvos} for g in range(1, jogos + 1)]


def test_edge_pelo_depth_chart_e_pelo_papel():
    # DE -> Edge; DT -> linha defensiva; ILB/MLB -> LB. OLB depende do papel:
    # mais pressões que alvos permitidos = pass rusher (Edge); o contrário = LB de cobertura (SAM/WILL do 4-3).
    linhas = (_defensor("E1", "DL", "DE", 3, 0) + _defensor("D1", "DL", "DT", 1, 0)
              + _defensor("E2", "LB", "OLB", 3, 1) + _defensor("L1", "LB", "OLB", 1, 4)
              + _defensor("L2", "LB", "ILB", 0, 3) + _defensor("L3", "LB", "MLB", 3, 0)
              + _defensor("E3", "LB", None, 3, 0))
    bio = pd.DataFrame({"playerId": ["E1", "D1", "E2", "L1", "L2", "L3", "E3"], "nome": list("abcdefg"),
                        "posicao": ["DL", "DL", "LB", "LB", "LB", "LB", "OLB"]})
    t = ratings.calcular(pd.DataFrame(linhas), _jogos({"AAA": 4}), bio, 2025).set_index("playerId")
    assert t["grupo"].to_dict() == {"E1": "EDGE", "D1": "DL", "E2": "EDGE", "L1": "LB", "L2": "LB",
                                    "L3": "LB", "E3": "EDGE"}   # E3: sem depth chart, cai na posição (OLB)


def test_qb_tem_eixo_de_corrida_por_jogo():
    jj = pd.DataFrame(sum((_qb(f"Q{i}", "AAA", 4, 30) for i in range(4)), []))
    jj["rushing_epa"] = jj["playerId"].map({"Q0": -0.5, "Q1": 0.0, "Q2": 1.0, "Q3": 3.0})
    t = ratings.calcular(jj, _jogos({"AAA": 4}), BIO, 2025).set_index("playerId")
    assert [e.rotulo for e in ratings.EIXOS["QB"]][-1] == "Corrida"
    assert t.loc["Q3", "eixo5_valor"] == pytest.approx(3.0)             # EPA de corrida por jogo
    assert t.loc["Q3", "eixo5_pct"] > t.loc["Q0", "eixo5_pct"]
    assert t.loc["Q3", "rating"] > t.loc["Q0", "rating"]               # o resto é igual: a corrida decide


def test_recebedor_tem_volume_alvos_por_jogo():
    rotulos = [e.rotulo for e in ratings.EIXOS["WRTE"]]
    assert "Alvos por jogo" in rotulos and "Após a recepção" not in rotulos
    jj = pd.DataFrame([{"playerId": p, "gameId": g, "time": "AAA", "position": "WR", "targets": n,
                        "receptions": n / 2, "receiving_yards": n * 8, "receiving_epa": n * 0.2}
                       for p, n in (("W1", 4), ("W2", 10)) for g in range(1, 5)])
    bio = pd.DataFrame({"playerId": ["W1", "W2"], "nome": ["a", "b"], "posicao": ["WR", "WR"]})
    t = ratings.calcular(jj, _jogos({"AAA": 4}), bio, 2025).set_index("playerId")
    i = rotulos.index("Alvos por jogo")
    assert t.loc["W2", f"eixo{i}_valor"] == 10 and t.loc["W2", f"eixo{i}_pct"] > t.loc["W1", f"eixo{i}_pct"]


@pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")
@pytest.mark.parametrize("ano", [2021, 2025])
def test_dados_reais_nenhum_eixo_vazio_por_grupo(ano):
    """Pegou o bug do def_sacks: um eixo inteiro vazio num grupo com jogadores avaliados."""
    jogos = tabela_npz.carregar(DADOS / "jogos.npz")
    bio = tabela_npz.carregar(DADOS / "jogadores_bio.npz")
    jj = tabela_npz.carregar(DADOS / "temporadas" / str(ano) / "jogador_jogo.npz")
    cat = lambda d: d.astype({c: object for c in d if isinstance(d[c].dtype, pd.CategoricalDtype)})  # noqa: E731
    t = ratings.calcular(cat(jj), cat(jogos), cat(bio), ano)
    for grupo, eixos in ratings.EIXOS.items():
        g = t[(t["grupo"] == grupo) & t["avaliado"]]
        assert len(g) >= 20, f"{grupo}: só {len(g)} avaliados"
        for i, e in enumerate(eixos):
            assert g[f"eixo{i}_pct"].notna().mean() > 0.5, f"{ano} {grupo} eixo '{e.rotulo}' quase vazio"
