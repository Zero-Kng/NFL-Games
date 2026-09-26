"""
Ratings dos jogadores a partir de estatísticas públicas (spec dados-externos, Requisito 5).

Para cada temporada e grupo de posição, cada eixo vira um percentil (0-100)
entre os jogadores do grupo que atingiram o volume mínimo. O rating é
`40 + média dos percentis × 0,59` (escala 40-99, a mesma da versão com PFF).

O volume mínimo é por jogo do time, multiplicado pelos jogos que o time já
disputou na temporada: assim o rating também funciona no meio da temporada.

A linha ofensiva não tem pressão cedida individual em fonte pública: 2 dos 4
eixos dela são do time, nos jogos em que o jogador atuou (baseReduzida).

Edge × linha defensiva × linebacker vem do depth chart do elenco (DE × DT,
OLB × ILB/MLB). "OLB" também cobre o SAM/WILL do 4-3, que joga em cobertura:
um OLB só é Edge se teve mais pressões que alvos permitidos (validação 4.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import tabela_npz


@dataclass(frozen=True)
class Eixo:
    rotulo: str
    chave: str
    menor_melhor: bool = False
    unidade: str = ""


GRUPOS = {
    "QB": ("Quarterback", ["QB"]),
    "RB": ("Running back", ["RB", "FB", "HB"]),
    "WRTE": ("Recebedor", ["WR", "TE"]),
    "OL": ("Linha ofensiva", ["T", "G", "C", "OT", "OG", "OL", "LT", "RT", "LG", "RG"]),
    "EDGE": ("Edge", ["DE", "OLB"]),
    "DL": ("Linha defensiva", ["DT", "NT", "DL"]),
    "LB": ("Linebacker", ["LB", "ILB", "MLB"]),
    "DB": ("Secundária", ["CB", "S", "FS", "SS", "DB", "SAF"]),
}
POSICAO_GRUPO = {p: g for g, (_, ps) in GRUPOS.items() for p in ps}
PAPEL_PELOS_NUMEROS = {"OLB", "LB"}      # Edge ou LB conforme pressões × alvos permitidos

# (volume usado para o mínimo, mínimo por jogo do time)
MINIMOS = {"QB": ("dropbacks", 15), "RB": ("toques", 6), "WRTE": ("alvos", 3), "OL": ("snaps_of", 30),
           "EDGE": ("snaps_def", 20), "DL": ("snaps_def", 20), "LB": ("snaps_def", 20), "DB": ("snaps_def", 20)}

EIXOS: dict[str, list[Eixo]] = {
    # CPOE já vem em pontos percentuais (5.39 = +5,39 pp), não em fração.
    "QB": [Eixo("EPA por dropback", "epa_dropback"), Eixo("Precisão (CPOE)", "cpoe", unidade="pp"),
           Eixo("Jardas por tentativa", "jd_tentativa", unidade="jd"),
           Eixo("Cuidado com a bola", "int_tentativa", True, "%"), Eixo("Sob pressão", "sack_dropback", True, "%"),
           Eixo("Corrida", "epa_corrida_jogo")],     # EPA das corridas do QB por jogo (validação 4.4)
    "RB": [Eixo("EPA por corrida", "epa_corrida"), Eixo("Após o contato", "jd_apos_contato", unidade="jd"),
           Eixo("Tackles quebrados", "quebrados_toque", unidade="%"), Eixo("Recepção", "jd_rec_jogo", unidade="jd"),
           Eixo("Segurança", "fumble_toque", True, "%")],
    "WRTE": [Eixo("Jardas por alvo", "jd_alvo", unidade="jd"), Eixo("EPA por alvo", "epa_alvo"),
             Eixo("Aproveitamento", "rec_alvo", unidade="%"), Eixo("Alvos por jogo", "alvos_jogo"),
             Eixo("Mãos", "drop_alvo", True, "%")],
    "OL": [Eixo("Volume", "snaps_of"), Eixo("Disciplina", "faltas_100", True),
           Eixo("Proteção do time", "pressao_time", True, "%"), Eixo("Corrida do time", "antes_contato_time", unidade="jd")],
    "EDGE": [Eixo("Pressão", "pressao_snap", unidade="%"), Eixo("Sacks", "sack_snap", unidade="%"),
             Eixo("QB hits", "hit_snap", unidade="%"), Eixo("Tackles para perda", "tfl_snap", unidade="%"),
             Eixo("Tackles perdidos", "perdidos_pct", True, "%")],
    "DL": [Eixo("Pressão", "pressao_snap", unidade="%"), Eixo("Sacks", "sack_snap", unidade="%"),
           Eixo("QB hits", "hit_snap", unidade="%"), Eixo("Tackles para perda", "tfl_snap", unidade="%"),
           Eixo("Tackles perdidos", "perdidos_pct", True, "%")],
    "LB": [Eixo("Tackles", "tackles_snap", unidade="%"), Eixo("Tackles para perda", "tfl_snap", unidade="%"),
           Eixo("Pressão", "pressao_snap", unidade="%"), Eixo("Cobertura", "rating_permitido", True),
           Eixo("Tackles perdidos", "perdidos_pct", True, "%")],
    "DB": [Eixo("Rating permitido", "rating_permitido", True), Eixo("Passes completados", "comp_permitido", True, "%"),
           Eixo("Jardas por alvo", "jd_alvo_permitido", True, "jd"), Eixo("Bolas na mão", "bolas_alvo", unidade="%"),
           Eixo("Tackles perdidos", "perdidos_pct", True, "%")],
}
BASE_REDUZIDA = {"OL"}
N_EIXOS = max(len(e) for e in EIXOS.values())

SOMAS = [
    "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
    "passing_epa", "carries", "rushing_yards", "rushing_tds", "rushing_epa", "rushing_fumbles_lost", "receptions",
    "targets", "receiving_yards", "receiving_tds", "receiving_epa", "receiving_yards_after_catch",
    "receiving_fumbles_lost", "def_tackles_solo", "def_tackle_assists", "def_tackles_for_loss", "def_sacks",
    "def_qb_hits", "def_interceptions", "def_pass_defended", "penalties", "passing_bad_throws", "times_pressured",
    "rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles",
    "receiving_broken_tackles", "receiving_drop", "def_targets", "def_completions_allowed", "def_yards_allowed",
    "def_pressures", "def_missed_tackles", "def_tackles_combined", "offense_snaps", "defense_snaps", "st_snaps",
]


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    """a / b alinhado pelo índice (id do jogador); NaN quando b <= 0 ou ausente."""
    a, b = a.astype(float), b.astype(float)
    return a / b.where(b > 0)


def _moda(s: pd.Series):
    s = s.dropna()
    return s.mode().iloc[0] if len(s) else None


def _contexto_time(jj: pd.DataFrame) -> pd.DataFrame:
    """Por (jogo, time): taxa de pressão sofrida e jardas antes do contato por corrida (base da OL)."""
    t = jj.groupby(["gameId", "time"]).agg(
        pressoes=("times_pressured", "sum"), tentativas=("attempts", "sum"), sacks=("sacks_suffered", "sum"),
        antes=("rushing_yards_before_contact", "sum"), corridas=("carries", "sum")).reset_index()
    t["pressao_time"] = _div(t["pressoes"], t["tentativas"] + t["sacks"])
    t["antes_contato_time"] = _div(t["antes"], t["corridas"])
    return t[["gameId", "time", "pressao_time", "antes_contato_time"]]


def _grupo(t: pd.DataFrame) -> pd.Series:
    """Grupo pela posição do depth chart (ou a da estatística, se faltar); OLB/LB pelo papel."""
    pos = t["posicao_elenco"].where(t["posicao_elenco"].notna(), t["posicao"])
    grupo = pos.map(POSICAO_GRUPO)
    pressoes, alvos = t["def_pressures"].fillna(0), t["def_targets"].fillna(0)
    com_numeros = pos.isin(PAPEL_PELOS_NUMEROS) & ((pressoes + alvos) > 0)
    grupo[com_numeros] = np.where(pressoes[com_numeros] > alvos[com_numeros], "EDGE", "LB")
    return grupo


def calcular(jj: pd.DataFrame, jogos: pd.DataFrame, bio: pd.DataFrame, ano: int) -> pd.DataFrame:
    jj = jj.copy()
    for c in SOMAS:
        if c not in jj:
            jj[c] = np.nan
    jj["time"] = jj["time"].astype(object)
    jj["position"] = jj["position"].astype(object)
    if "posicao_elenco" not in jj:
        jj["posicao_elenco"] = None
    jj["posicao_elenco"] = jj["posicao_elenco"].astype(object)

    # ---- totais por jogador na temporada
    g = jj.groupby("playerId")
    t = g[SOMAS].sum(min_count=1)
    t["jogos"] = g["gameId"].nunique()
    t["time"] = g["time"].agg(_moda)
    t["posicao"] = g["position"].agg(_moda)
    t["posicao_elenco"] = g["posicao_elenco"].agg(_moda)
    # CPOE e rating permitido: médias ponderadas pelo volume de cada jogo
    jj["_cpoe_x"] = jj["passing_cpoe"] * jj["attempts"] if "passing_cpoe" in jj else np.nan
    jj["_cpoe_w"] = jj["attempts"].where(jj.get("passing_cpoe", pd.Series(np.nan, index=jj.index)).notna())
    jj["_rat_x"] = jj["def_passer_rating_allowed"] * jj["def_targets"] if "def_passer_rating_allowed" in jj else np.nan
    jj["_rat_w"] = jj["def_targets"].where(jj.get("def_passer_rating_allowed", pd.Series(np.nan, index=jj.index)).notna())
    pond = jj.groupby("playerId")[["_cpoe_x", "_cpoe_w", "_rat_x", "_rat_w"]].sum(min_count=1)
    t["cpoe"] = _div(pond["_cpoe_x"], pond["_cpoe_w"])
    t["rating_permitido"] = _div(pond["_rat_x"], pond["_rat_w"])

    # ---- contexto do time para a OL (ponderado pelos snaps do jogador em cada jogo)
    ctx = jj[["gameId", "time", "playerId", "offense_snaps"]].merge(_contexto_time(jj), on=["gameId", "time"], how="left")
    for c in ("pressao_time", "antes_contato_time"):
        w = ctx["offense_snaps"].where(ctx[c].notna())
        num = (ctx[c] * ctx["offense_snaps"]).groupby(ctx["playerId"]).sum(min_count=1)
        den = w.groupby(ctx["playerId"]).sum(min_count=1)
        t[c] = _div(num, den).reindex(t.index)

    # ---- eixos
    dropbacks = t["attempts"].fillna(0) + t["sacks_suffered"].fillna(0)
    toques = t["carries"].fillna(0) + t["receptions"].fillna(0)
    t["dropbacks"], t["toques"], t["alvos"] = dropbacks, toques, t["targets"]
    t["snaps_of"], t["snaps_def"] = t["offense_snaps"], t["defense_snaps"]
    t["epa_dropback"] = _div(t["passing_epa"], dropbacks)
    t["epa_corrida_jogo"] = _div(t["rushing_epa"].fillna(0), t["jogos"])
    t["jd_tentativa"] = _div(t["passing_yards"], t["attempts"])
    t["int_tentativa"] = _div(t["passing_interceptions"], t["attempts"])
    t["sack_dropback"] = _div(t["sacks_suffered"], dropbacks)
    t["epa_corrida"] = _div(t["rushing_epa"], t["carries"])
    t["jd_apos_contato"] = _div(t["rushing_yards_after_contact"], t["carries"])
    t["quebrados_toque"] = _div(t["rushing_broken_tackles"].fillna(0) + t["receiving_broken_tackles"].fillna(0), toques)
    t["jd_rec_jogo"] = _div(t["receiving_yards"].fillna(0), t["jogos"])
    t["fumble_toque"] = _div(t["rushing_fumbles_lost"].fillna(0) + t["receiving_fumbles_lost"].fillna(0), toques)
    t["jd_alvo"] = _div(t["receiving_yards"], t["targets"])
    t["epa_alvo"] = _div(t["receiving_epa"], t["targets"])
    t["rec_alvo"] = _div(t["receptions"], t["targets"])
    t["alvos_jogo"] = _div(t["targets"], t["jogos"])
    t["drop_alvo"] = _div(t["receiving_drop"], t["targets"])
    t["faltas_100"] = _div(t["penalties"].fillna(0) * 100, t["offense_snaps"])
    snaps_d = t["defense_snaps"]
    t["pressao_snap"] = _div(t["def_pressures"], snaps_d)
    t["sack_snap"] = _div(t["def_sacks"], snaps_d)
    t["hit_snap"] = _div(t["def_qb_hits"], snaps_d)
    t["tfl_snap"] = _div(t["def_tackles_for_loss"], snaps_d)
    t["tackles_snap"] = _div(t["def_tackles_solo"].fillna(0) + t["def_tackle_assists"].fillna(0), snaps_d)
    t["perdidos_pct"] = _div(t["def_missed_tackles"], t["def_tackles_combined"].fillna(0) + t["def_missed_tackles"].fillna(0))
    t["comp_permitido"] = _div(t["def_completions_allowed"], t["def_targets"])
    t["jd_alvo_permitido"] = _div(t["def_yards_allowed"], t["def_targets"])
    t["bolas_alvo"] = _div(t["def_interceptions"].fillna(0) + t["def_pass_defended"].fillna(0), t["def_targets"])

    # ---- grupo, bio e mínimo proporcional aos jogos do time
    b = bio.set_index("playerId")
    t["posicao"] = t["posicao"].fillna(b["posicao"].reindex(t.index))
    t["grupo"] = _grupo(t)
    t["nome"] = b["nome"].reindex(t.index)
    disputados = jogos[(jogos["season"] == ano) & jogos["home_score"].notna()]
    jogos_time = pd.concat([disputados["home"], disputados["away"]]).astype(str).value_counts()
    t["jogos_time"] = t["time"].astype(str).map(jogos_time).fillna(0)
    t["minimo"] = np.nan
    t["volume"] = np.nan
    for grupo, (col, por_jogo) in MINIMOS.items():
        m = t["grupo"] == grupo
        t.loc[m, "minimo"] = t.loc[m, "jogos_time"] * por_jogo
        t.loc[m, "volume"] = t.loc[m, col]
    t["avaliado"] = (t["volume"].fillna(0) >= t["minimo"]) & (t["minimo"] > 0)
    t["baseReduzida"] = t["grupo"].isin(BASE_REDUZIDA)

    # ---- percentis e rating, dentro do grupo e da temporada
    t["rating"] = np.nan
    for i in range(N_EIXOS):
        t[f"eixo{i}_valor"] = np.nan
        t[f"eixo{i}_pct"] = np.nan
        t[f"eixo{i}_motivo"] = None
    for grupo, eixos in EIXOS.items():
        m = (t["grupo"] == grupo) & t["avaliado"]
        do_grupo = t["grupo"] == grupo
        pcts = []
        for i, e in enumerate(eixos):
            t.loc[do_grupo, f"eixo{i}_valor"] = t.loc[do_grupo, e.chave]
            valores = t.loc[m, e.chave]
            if valores.notna().sum() == 0:       # estatística inexistente na temporada (5.5)
                t.loc[do_grupo, f"eixo{i}_motivo"] = "estatística indisponível nesta temporada"
                continue
            r = valores.rank(pct=True, na_option="keep")
            p = (1.0 - r if e.menor_melhor else r) * 100.0
            t.loc[m, f"eixo{i}_pct"] = p
            pcts.append(p)
        if pcts:
            t.loc[m, "rating"] = (40 + pd.concat(pcts, axis=1).mean(axis=1) * 0.59).round(0)

    t["season"] = ano
    t = t.reset_index()
    t["grupo"] = t["grupo"].astype(object)
    return t


def montar(ano: int, pasta: Path, jogadas, jj: pd.DataFrame, jogos: pd.DataFrame, bio: pd.DataFrame) -> pd.DataFrame:
    """Gancho do etl/montar.py: grava dados/temporadas/{ano}/jogadores.npz."""
    t = calcular(jj, jogos, bio, ano)
    tabela_npz.salvar(t, Path(pasta) / "jogadores.npz")
    return t
