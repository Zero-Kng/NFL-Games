"""
Notícias da semana geradas a partir dos dados (spec novo-visual v0.4, Requisito 7).

Cada notícia é um fato de um jogo disputado, com texto montado só com números
do dado (placar oficial, jardas, TDs, sacks). Nada de texto livre.

Tipos e limiares (medidos em 2021–2025, média por semana entre parênteses):
    resultado     todo jogo: quem venceu e o placar oficial            (12,9)
    virada        o vencedor reverteu desvantagem de 10+ pontos        (1,7)
    prorrogacao   jogo decidido na prorrogação                         (0,8)
    goleada       margem de 28+ pontos                                 (0,9)
    maior_jogada  a jogada de mais jardas da semana (só a 1ª)          (1)
    atuacao       400+ jd de passe, 5+ TD de passe, 175+ jd correndo
                  ou recebendo, 4+ TD, ou 3,5+ sacks                  (1,6)
    defesa        time com 6+ sacks ou 3+ interceptações              (2,7)

"incomum" (0–1) é o percentil do fato dentro da própria família, na
temporada. O resultado fica com metade do percentil da margem, abaixo dos
fatos raros: o carrossel mostra primeiro o que foge do comum.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

VIRADA_MIN = 10
GOLEADA_MIN = 28
SACKS_MIN, INTS_MIN = 6, 3
# (coluna, limiar, rótulo no singular/plural, casas)
ATUACAO = [
    ("passing_yards", 400, "jardas de passe", 0),
    ("passing_tds", 5, "TDs de passe", 0),
    ("rushing_yards", 175, "jardas correndo", 0),
    ("receiving_yards", 175, "jardas recebidas", 0),
    ("total_tds", 4, "touchdowns", 0),
    ("def_sacks", 3.5, "sacks", 1),
]
TOM = {"resultado": "dark", "virada": "red", "prorrogacao": "blue", "goleada": "red",
       "maior_jogada": "blue", "atuacao": "red", "defesa": "dark"}
TAG = {"resultado": "Resultado", "virada": "Virada", "prorrogacao": "Prorrogação", "goleada": "Goleada",
       "maior_jogada": "Jogada", "atuacao": "Atuação", "defesa": "Defesa"}


def _pct(valor: float, universo: np.ndarray) -> float:
    """Fração do universo menor ou igual ao valor (0–1)."""
    u = universo[~np.isnan(universo)]
    return float((u <= valor).mean()) if len(u) else 0.0


def _num(v, casas=0) -> str:
    f = float(v)
    return str(int(round(f))) if casas == 0 or f.is_integer() else f"{f:.{casas}f}".replace(".", ",")


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def gerar(jogos: pd.DataFrame, jogadas: pd.DataFrame, jj: pd.DataFrame, nomes: dict[str, str]) -> list[dict]:
    """
    Todas as notícias de uma temporada, ordenadas por "incomum" (desc).
    `jogos`: os jogos da temporada (calendário); `jogadas`/`jj`: as tabelas dela;
    `nomes`: playerId -> nome de exibição.
    """
    disputados = jogos[jogos["home_score"].notna() & jogos["away_score"].notna()].copy()
    if disputados.empty:
        return []
    disputados["margem"] = (disputados["home_score"] - disputados["away_score"]).abs()

    # desvantagem máxima revertida pelo vencedor, pelo placar oficial jogada a jogada
    diff = (jogadas["total_home_score"] - jogadas["total_away_score"]).astype(float)
    extremos = diff.groupby(jogadas["gameId"], observed=True).agg(["min", "max"])
    ext = extremos.reindex(disputados["gameId"])
    casa_venceu = (disputados["home_score"] > disputados["away_score"]).to_numpy()
    fora_venceu = (disputados["away_score"] > disputados["home_score"]).to_numpy()
    deficit = np.where(casa_venceu, -ext["min"].to_numpy(), np.where(fora_venceu, ext["max"].to_numpy(), 0.0))
    disputados["deficit"] = np.clip(np.nan_to_num(deficit, nan=0.0), 0, None)

    esc = jogadas[jogadas["play_type"].isin(["pass", "run"])]
    defesa = esc.groupby(["gameId", "defteam"], observed=True)[["sack", "interception"]].sum().reset_index()

    jj = jj.copy()
    jj["total_tds"] = jj["rushing_tds"].fillna(0) + jj["receiving_tds"].fillna(0)

    # universos de cada família (percentis na temporada)
    u_margem = disputados["margem"].to_numpy(float)
    u_deficit = disputados["deficit"].to_numpy(float)
    u_sacks = defesa["sack"].to_numpy(float)
    u_ints = defesa["interception"].to_numpy(float)
    u_atuacao = {c: jj.loc[jj[c].fillna(0) > 0, c].to_numpy(float) for c, *_ in ATUACAO}
    frac_ot = float((disputados["overtime"] == 1).mean())
    maior_por_semana = esc.groupby("week", observed=True)["yards_gained"].max().to_numpy(float)

    noticias: list[dict] = []
    info = {int(r["gameId"]): r for r in disputados.to_dict("records")}

    def nova(g: dict, tipo: str, extra: str, destaque: str, titulo: str, texto: str, incomum: float) -> None:
        noticias.append({
            "id": f"{int(g['gameId'])}:{tipo}" + (f":{extra}" if extra else ""),
            "gameId": int(g["gameId"]), "season": int(g["season"]), "week": int(g["week"]),
            "rodada": g["rodada"], "tipo": tipo, "tom": TOM[tipo], "tag": TAG[tipo], "destaque": destaque,
            "titulo": titulo, "texto": texto, "incomum": round(min(max(incomum, 0.0), 1.0), 4),
            "times": [g["away"], g["home"]],
        })

    for gid, g in info.items():
        hs, as_ = int(g["home_score"]), int(g["away_score"])
        if hs == as_:
            venc, perd, pv, pp = g["home"], g["away"], hs, as_
        elif hs > as_:
            venc, perd, pv, pp = g["home"], g["away"], hs, as_
        else:
            venc, perd, pv, pp = g["away"], g["home"], as_, hs
        ot = g["overtime"] == 1
        placar = f"{g['away']} {as_} x {hs} {g['home']}"
        # resultado (todo jogo)
        if hs == as_:
            titulo = f"{g['away']} e {g['home']} empatam em {hs}–{hs}"
        else:
            titulo = f"{venc} vence {perd} por {pv}–{pp}" + (" na prorrogação" if ot else "")
        nova(g, "resultado", "", str(pv), titulo, f"{g['rodada']}: placar final {placar}.",
             0.5 * _pct(g["margem"], u_margem))
        if hs == as_:
            continue
        if g["deficit"] >= VIRADA_MIN:
            d = int(g["deficit"])
            nova(g, "virada", "", str(d), f"{venc} vira sobre {perd} depois de estar {d} pontos atrás",
                 f"Vitória por {pv}–{pp}. {g['rodada']}: placar final {placar}.", _pct(g["deficit"], u_deficit))
        if ot:
            nova(g, "prorrogacao", "", "OT", f"{g['away']} x {g['home']} é decidido na prorrogação",
                 f"{venc} vence por {pv}–{pp}.", 1.0 - frac_ot)
        if g["margem"] >= GOLEADA_MIN:
            m = int(g["margem"])
            nova(g, "goleada", "", str(m), f"{venc} vence {perd} por {m} pontos de diferença",
                 f"Placar final: {placar}.", _pct(g["margem"], u_margem))

    # defesa: 6+ sacks ou 3+ interceptações de um time num jogo
    for r in defesa.to_dict("records"):
        gid = int(r["gameId"])
        if gid not in info or not (r["sack"] >= SACKS_MIN or r["interception"] >= INTS_MIN):
            continue
        g, time = info[gid], r["defteam"]
        adv = g["home"] if time == g["away"] else g["away"]
        partes = []
        if r["sack"] >= SACKS_MIN:
            partes.append(f"{_num(r['sack'])} sacks")
        if r["interception"] >= INTS_MIN:
            partes.append(f"{_num(r['interception'])} interceptações")
        principal = partes[0].split()[0]
        nova(g, "defesa", str(time), principal, f"Defesa de {time} tem {' e '.join(partes)} contra {adv}",
             f"Placar final: {g['away']} {int(g['away_score'])} x {int(g['home_score'])} {g['home']}.",
             max(_pct(r["sack"], u_sacks) if r["sack"] >= SACKS_MIN else 0,
                 _pct(r["interception"], u_ints) if r["interception"] >= INTS_MIN else 0))

    # atuação individual
    cols = [c for c, *_ in ATUACAO]
    alvo = jj[jj["gameId"].isin(info.keys())]
    marca = np.zeros(len(alvo), dtype=bool)
    for c, lim, *_ in ATUACAO:
        marca |= (alvo[c].fillna(0) >= lim).to_numpy()
    for r in alvo[marca].to_dict("records"):
        g = info[int(r["gameId"])]
        batidos = [(c, rot, casas, _pct(r[c], u_atuacao[c])) for c, lim, rot, casas in ATUACAO
                   if not _vazio(r[c]) and r[c] >= lim]
        batidos.sort(key=lambda x: -x[3])
        c0, rot0, casas0, pct0 = batidos[0]
        nome = nomes.get(r["playerId"]) or str(r["playerId"])
        adv = r.get("adversario") or (g["home"] if r.get("time") == g["away"] else g["away"])
        linha = ", ".join(f"{_num(r[c], casas)} {rot}" for c, rot, casas, _p in batidos)
        nova(g, "atuacao", str(r["playerId"]), _num(r[c0], casas0),
             f"{nome} tem {_num(r[c0], casas0)} {rot0} contra {adv}",
             f"{linha[0].upper() + linha[1:]}. Placar final: {g['away']} {int(g['away_score'])} x "
             f"{int(g['home_score'])} {g['home']}.", pct0)

    # maior jogada de cada semana (só a 1ª em caso de empate)
    esc_disp = esc[esc["gameId"].isin(info.keys())]
    for _w, d in esc_disp.groupby("week", observed=True):
        if d.empty or d["yards_gained"].isna().all():
            continue
        r = d.sort_values(["yards_gained", "gameId", "seq"], ascending=[False, True, True]).iloc[0]
        g = info[int(r["gameId"])]
        y = int(r["yards_gained"])
        nova(g, "maior_jogada", "", str(y), f"Maior jogada da semana: {y} jardas",
             f"{r['posteam']} x {r['defteam']}: {r['desc']}", _pct(y, maior_por_semana))

    noticias.sort(key=lambda n: (-n["incomum"], n["gameId"], n["id"]))
    return noticias
