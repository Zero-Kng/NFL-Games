"""
Monta as tabelas que o servidor usa a partir dos brutos do nflverse.

    dados/jogos.npz             todas as temporadas (calendário e placar oficial)
    dados/jogadores_bio.npz     bio, foto e posição de todos os jogadores
    dados/temporadas/{ano}/
        jogadas.npz             play-by-play + formação (participação e FTN) + os 22 jogadores
        jogador_jogo.npz        estatísticas por jogador e jogo (+ avançadas do PFR + snaps)
        origem.json             assinaturas dos brutos usados: a temporada só é refeita se mudarem

Os ratings (jogadores.npz) são montados em etl/ratings.py, logo depois.

Uso:
    python etl/montar.py        # sincroniza as fontes e monta o que mudou
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "etl"))

import fontes  # noqa: E402
import ratings  # noqa: E402
import tabela_npz  # noqa: E402

# Suba quando mudar o que é montado: força refazer todas as temporadas.
ETL_VERSION = 4

FTN_DESDE = next(f.anos_min for f in fontes.CATALOGO if f.nome == "ftn")

RODADAS = {"WC": "Wild Card", "DIV": "Divisional", "CON": "Final de Conferência", "SB": "Super Bowl"}

COLS_JOGADAS = [
    "game_id", "old_game_id", "play_id", "order_sequence", "season", "week", "season_type", "qtr", "time",
    "game_seconds_remaining", "down", "ydstogo", "yardline_100", "side_of_field", "yrdln", "posteam", "defteam",
    "play_type", "yards_gained", "desc", "epa", "wp", "total_home_score", "total_away_score", "pass", "rush",
    "sack", "interception", "touchdown", "pass_touchdown", "rush_touchdown", "return_touchdown", "penalty",
    "penalty_yards", "first_down", "third_down_converted", "third_down_failed", "complete_pass",
    "incomplete_pass", "qb_scramble", "qb_dropback", "air_yards", "yards_after_catch", "passer_player_id",
    "passer_player_name", "rusher_player_id", "rusher_player_name", "receiver_player_id",
    "receiver_player_name", "shotgun", "no_huddle", "pass_length", "pass_location", "run_location",
    "fumble_lost", "field_goal_result", "extra_point_result",
]
COLS_PARTICIPACAO = {
    "offense_formation": "formacao", "offense_personnel": "pessoal_of", "defense_personnel": "pessoal_def",
    "defenders_in_box": "box", "number_of_pass_rushers": "rushers", "defense_coverage_type": "cobertura",
    "defense_man_zone_type": "homem_zona", "was_pressure": "pressao", "time_to_throw": "tempo_lancamento",
    "offense_players": "of_ids", "defense_players": "def_ids",
    "offense_names": "of_nomes", "defense_names": "def_nomes", "offense_positions": "of_posicoes",
    "defense_positions": "def_posicoes", "offense_numbers": "of_numeros", "defense_numbers": "def_numeros",
}
COLS_FTN = {
    "qb_location": "qb_local", "n_offense_backfield": "backfield", "n_defense_box": "ftn_box",
    "n_pass_rushers": "ftn_rushers", "starting_hash": "hash", "is_motion": "motion",
    "is_play_action": "play_action", "n_blitzers": "blitzers",
}
COLS_PFR = {
    # Sem def_sacks/def_ints: o stats_player já tem def_sacks/def_interceptions, e o
    # nome repetido fazia o merge renomear as duas colunas (_x/_y) e o eixo "Sacks" sumia.
    "def": ["def_targets", "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed",
            "def_passer_rating_allowed", "def_times_blitzed", "def_times_hurried", "def_times_hitqb",
            "def_pressures", "def_tackles_combined", "def_missed_tackles"],
    "pass": ["passing_bad_throws", "times_sacked", "times_blitzed", "times_hurried", "times_hit",
             "times_pressured"],
    "rush": ["rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles"],
    "rec": ["receiving_broken_tackles", "receiving_drop", "receiving_int"],
}


@dataclass
class Montagem:
    temporadas: list[int] = field(default_factory=list)
    globais: list[str] = field(default_factory=list)
    liberado_bytes: int = 0
    segundos: float = 0.0


class FaltamBrutos(RuntimeError):
    def __init__(self, anos: set[int]):
        super().__init__(f"faltam os brutos das temporadas {sorted(anos)}")
        self.anos = anos


# --------------------------------------------------------------------------- #
def _manifesto(dados: Path) -> dict:
    try:
        return json.loads((dados / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _brutos(dados: Path, fonte: str, ano: int | None = None) -> list[Path]:
    m = _manifesto(dados).get("arquivos", {})
    return sorted(dados / "brutos" / k for k, v in m.items()
                  if v.get("fonte") == fonte and v.get("ano") == ano and (dados / "brutos" / k).exists())


def _assinatura(dados: Path, ano: int | None, fontes_nomes: list[str]) -> dict:
    m = _manifesto(dados).get("arquivos", {})
    return {"etl": ETL_VERSION, **{k: v["updated_at"] for k, v in sorted(m.items())
                                   if v.get("ano") == ano and v.get("fonte") in fontes_nomes}}


def _ler(caminhos: list[Path], usecols=None) -> pd.DataFrame:
    if not caminhos:
        return pd.DataFrame()
    partes = []
    for p in caminhos:
        cab = pd.read_csv(p, nrows=0).columns
        cols = [c for c in usecols if c in cab] if usecols else None
        partes.append(pd.read_csv(p, usecols=cols, low_memory=False))
    return pd.concat(partes, ignore_index=True)


def _gravar_json(caminho: Path, obj: dict) -> None:
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)


# ------------------------------------------------------------ tabelas gerais
def montar_jogos(dados: Path) -> pd.DataFrame:
    g = _ler(_brutos(dados, "jogos"))
    g = g[g["season"] >= fontes.PRIMEIRA_TEMPORADA].copy()
    out = pd.DataFrame({
        "gameId": g["old_game_id"].astype("int64"),
        "nflverseId": g["game_id"],
        "season": g["season"].astype("int64"),
        "week": g["week"].astype("int64"),
        "game_type": g["game_type"],
        "rodada": [RODADAS.get(t, f"Semana {w}") for t, w in zip(g["game_type"], g["week"])],
        "gameday": g["gameday"], "weekday": g["weekday"], "gametime": g["gametime"],
        "home": g["home_team"], "away": g["away_team"],
        "home_score": g["home_score"].astype("float64"), "away_score": g["away_score"].astype("float64"),
        "overtime": g["overtime"].astype("float64"),
        "espnId": g["espn"].astype("string"),
        "stadium": g["stadium"], "roof": g["roof"],
        "home_coach": g["home_coach"], "away_coach": g["away_coach"],
        "home_qb": g["home_qb_name"], "away_qb": g["away_qb_name"],
    })
    return out.sort_values(["season", "week", "gameday", "gametime", "gameId"]).reset_index(drop=True)


def montar_bio(dados: Path) -> pd.DataFrame:
    p = _ler(_brutos(dados, "jogadores"))
    return pd.DataFrame({
        "playerId": p["gsis_id"], "nome": p["display_name"], "posicao": p["position"],
        "grupo_nflverse": p["position_group"], "pfrId": p["pfr_id"], "foto": p["headshot"],
        "altura": p["height"], "peso": p["weight"], "faculdade": p["college_name"],
        "nascimento": p["birth_date"],
    }).dropna(subset=["playerId"]).drop_duplicates("playerId").reset_index(drop=True)


# --------------------------------------------------------- tabelas por ano
def _elenco(dados: Path, ano: int) -> pd.DataFrame:
    r = _ler(_brutos(dados, "elencos", ano),
             usecols=["season", "team", "position", "jersey_number", "gsis_id", "full_name", "pfr_id",
                      "depth_chart_position"])
    return r.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id", keep="last")


def _nomes_por_id(ids: pd.Series, elenco: pd.DataFrame, bio: pd.DataFrame, campo: str) -> list:
    """'id;id;...' -> 'valor;valor;...' pelo elenco da temporada (ou pela bio, se faltar)."""
    mapa = dict(zip(elenco["gsis_id"], elenco[campo]))
    if campo in ("full_name", "position"):
        extra = dict(zip(bio["playerId"], bio["nome" if campo == "full_name" else "posicao"]))
        mapa = extra | mapa

    def conv(txt):
        if not isinstance(txt, str) or not txt:
            return None
        out = []
        for i in txt.split(";"):
            v = mapa.get(i)
            out.append("" if v is None or (isinstance(v, float) and np.isnan(v))
                       else str(int(v)) if isinstance(v, float) else str(v))
        return ";".join(out)

    return [conv(t) for t in ids]


def _ftn_pendente(p: pd.DataFrame, com_ftn: set, ano: int) -> pd.Series:
    """Jogos ainda à espera do FTN: o nflverse o publica 2 a 3 dias depois do jogo.

    Só conta como pendente o jogo sem FTN a partir da última semana que já o tem;
    um jogo mais antigo sem FTN não vai mais recebê-lo (é "indisponível").
    """
    if ano < FTN_DESDE:
        return pd.Series(False, index=p.index)
    sem = ~p["game_id"].isin(com_ftn)
    if not com_ftn:
        return sem
    return sem & (p["week"] >= p.loc[~sem, "week"].max())


def montar_jogadas(dados: Path, ano: int, bio: pd.DataFrame) -> pd.DataFrame:
    p = _ler(_brutos(dados, "jogadas", ano), usecols=COLS_JOGADAS)
    p = p[p["play_type"].notna()].copy()
    p["gameId"] = p["old_game_id"].astype("int64")
    p["play_id"] = p["play_id"].astype("int64")

    part = _ler(_brutos(dados, "participacao", ano), usecols=["old_game_id", "play_id", *COLS_PARTICIPACAO])
    if not part.empty:
        part = part.rename(columns=COLS_PARTICIPACAO | {"old_game_id": "gameId"})
        part["gameId"] = part["gameId"].astype("int64")
        part = part.drop_duplicates(["gameId", "play_id"])
        p = p.merge(part, on=["gameId", "play_id"], how="left")

    ftn = _ler(_brutos(dados, "ftn", ano), usecols=["nflverse_game_id", "nflverse_play_id", *COLS_FTN])
    if not ftn.empty:
        ftn = ftn.rename(columns=COLS_FTN | {"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
        ftn = ftn.drop_duplicates(["game_id", "play_id"])
        p = p.merge(ftn, on=["game_id", "play_id"], how="left")
    p["ftn_pendente"] = _ftn_pendente(p, set(ftn["game_id"]) if not ftn.empty else set(), ano)

    for c in list(COLS_PARTICIPACAO.values()) + list(COLS_FTN.values()):
        if c not in p:
            p[c] = np.nan
    # Listas de jogadores são texto, mesmo quando a temporada não as traz (a coluna nasceria numérica).
    for c in ("of_ids", "def_ids", "of_nomes", "def_nomes", "of_posicoes", "def_posicoes", "of_numeros", "def_numeros"):
        p[c] = p[c].astype(object)
    # box e rushers: participação primeiro; FTN quando ela não tem (2026).
    p["box"] = p["box"].fillna(p["ftn_box"])
    p["rushers"] = p["rushers"].fillna(p["ftn_rushers"])

    # 2021-2022: a participação só tem os ids; nomes, posições e números vêm do elenco da temporada.
    elenco = _elenco(dados, ano)
    for lado in ("of", "def"):
        ids = p[f"{lado}_ids"]
        sem = p[f"{lado}_nomes"].isna() & ids.notna()
        if sem.any():
            p.loc[sem, f"{lado}_nomes"] = _nomes_por_id(ids[sem], elenco, bio, "full_name")
            p.loc[sem, f"{lado}_posicoes"] = _nomes_por_id(ids[sem], elenco, bio, "position")
            p.loc[sem, f"{lado}_numeros"] = _nomes_por_id(ids[sem], elenco, bio, "jersey_number")

    # Ordem cronológica pelo order_sequence: o play_id NÃO é cronológico em parte
    # dos jogos (59 de 285 em 2021; todos os de 2026 até aqui). "seq" = 1..n no jogo.
    p = p.drop(columns=["old_game_id", "ftn_box", "ftn_rushers"]) \
         .sort_values(["gameId", "order_sequence", "play_id"]).reset_index(drop=True)
    p["seq"] = p.groupby("gameId").cumcount() + 1
    return p


def montar_jogador_jogo(dados: Path, ano: int, jogos: pd.DataFrame, bio: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """(tabela, quantos registros do PFR/snaps ficaram sem ponte para o id gsis)."""
    st = _ler(_brutos(dados, "estatisticas", ano))
    st = st.rename(columns={"player_id": "playerId", "opponent_team": "adversario", "team": "time"})
    # A fonte traz ~22 registros por temporada sem id de jogador: não dá para atribuí-los a ninguém.
    st = st.dropna(subset=["playerId"])

    elenco = _elenco(dados, ano)
    ponte = dict(zip(bio["pfrId"].dropna(), bio.loc[bio["pfrId"].notna(), "playerId"]))
    ponte |= dict(zip(elenco["pfr_id"].dropna(), elenco.loc[elenco["pfr_id"].notna(), "gsis_id"]))

    sem_ponte = 0
    extras = []
    for tipo, cols in COLS_PFR.items():
        a = _ler(_brutos(dados, f"avancadas_{tipo}", ano), usecols=["game_id", "pfr_player_id", "team", *cols])
        if a.empty:
            continue
        a["playerId"] = a["pfr_player_id"].map(ponte)
        sem_ponte += int(a["playerId"].isna().sum())
        extras.append(a.dropna(subset=["playerId"]).drop(columns=["pfr_player_id"])
                       .rename(columns={"team": f"time_{tipo}"})
                       .groupby(["game_id", "playerId"], as_index=False).first())
    sn = _ler(_brutos(dados, "snaps", ano),
              usecols=["game_id", "pfr_player_id", "position", "team", "offense_snaps", "defense_snaps", "st_snaps"])
    sn["playerId"] = sn["pfr_player_id"].map(ponte)
    sem_ponte += int(sn["playerId"].isna().sum())
    sn = (sn.dropna(subset=["playerId"]).drop(columns=["pfr_player_id"])
          .rename(columns={"position": "posicao_snaps", "team": "time_snaps"})
          .groupby(["game_id", "playerId"], as_index=False).first())

    base = st
    for e in extras + [sn]:
        repetidas = (set(base.columns) & set(e.columns)) - {"game_id", "playerId"}
        if repetidas:   # falha alto em vez de gerar _x/_y silenciosos
            raise ValueError(f"colunas repetidas na junção de jogador_jogo: {sorted(repetidas)}")
        base = base.merge(e, on=["game_id", "playerId"], how="outer")

    # Time e posição para quem só aparece nos snaps (a linha ofensiva não tem estatística).
    for c in ("time_snaps", "time_def", "time_pass", "time_rush", "time_rec"):
        if c in base:
            base["time"] = base["time"].fillna(base[c])
    base["position"] = base.get("position", pd.Series(index=base.index, dtype="object")) \
        .fillna(base.get("posicao_snaps"))

    jg = jogos[jogos["season"] == ano][["nflverseId", "gameId", "week", "game_type", "home", "away"]]
    base = base.drop(columns=[c for c in ("week",) if c in base]).merge(
        jg.rename(columns={"nflverseId": "game_id"}), on="game_id", how="inner")
    base["adversario"] = base["adversario"].fillna(
        pd.Series(np.where(base["time"] == base["home"], base["away"], base["home"]), index=base.index))
    base = base.drop(columns=["home", "away"] + [c for c in base if c.startswith("time_")])
    base["season"] = ano   # quem só aparece nos snaps (linha ofensiva) não trazia a temporada
    # DE × DT e OLB × ILB/MLB: separa Edge, linha defensiva e linebacker nos ratings
    base = base.copy()   # desfragmenta (muitas colunas vindas dos merges) antes da coluna nova
    base["posicao_elenco"] = base["playerId"].map(dict(zip(elenco["gsis_id"], elenco["depth_chart_position"])))
    return base.sort_values(["gameId", "playerId"]).reset_index(drop=True), sem_ponte


# --------------------------------------------------------------------------- #
FONTES_TEMPORADA = ["jogadas", "participacao", "ftn", "elencos", "estatisticas", "avancadas_def",
                    "avancadas_pass", "avancadas_rush", "avancadas_rec", "snaps"]


def atualizar(dados: Path = fontes.DADOS, anos: range | None = None, economia: bool = True,
              progresso: Callable[[str], None] = print, depois_da_temporada=None) -> Montagem:
    """
    Monta o que mudou. `depois_da_temporada(ano, jogadas, jogador_jogo, jogos, bio)`
    é chamado a cada temporada montada (os ratings entram por aqui).
    Com `economia`, os brutos das temporadas encerradas são descartados depois de montadas.
    """
    t0 = time.perf_counter()
    dados = Path(dados)
    anos = anos or range(fontes.PRIMEIRA_TEMPORADA, fontes.temporada_atual() + 1)
    res = Montagem()

    ass_g = {"etl": ETL_VERSION, **{k: v["updated_at"] for k, v in _manifesto(dados).get("arquivos", {}).items()
                                    if v.get("fonte") in ("jogos", "jogadores")}}
    orig_g = dados / "origem_geral.json"
    antes_g = json.loads(orig_g.read_text()) if orig_g.exists() else {}
    if ass_g != antes_g or not (dados / "jogos.npz").exists() or not (dados / "jogadores_bio.npz").exists():
        progresso("montando calendário e jogadores...")
        tabela_npz.salvar(montar_jogos(dados), dados / "jogos.npz")
        tabela_npz.salvar(montar_bio(dados), dados / "jogadores_bio.npz")
        _gravar_json(orig_g, ass_g)
        res.globais = ["jogos", "jogadores_bio"]
    jogos = tabela_npz.carregar(dados / "jogos.npz")
    bio = tabela_npz.carregar(dados / "jogadores_bio.npz")
    jogos = jogos.assign(**{c: jogos[c].astype(object) for c in jogos if isinstance(jogos[c].dtype, pd.CategoricalDtype)})
    bio = bio.assign(**{c: bio[c].astype(object) for c in bio if isinstance(bio[c].dtype, pd.CategoricalDtype)})

    atual = fontes.temporada_atual()
    faltam = set()
    for ano in anos:
        pasta = dados / "temporadas" / str(ano)
        ass = _assinatura(dados, ano, FONTES_TEMPORADA)
        orig = pasta / "origem.json"
        prontas = all((pasta / f).exists() for f in ("jogadas.npz", "jogador_jogo.npz", "jogadores.npz"))
        if prontas and orig.exists() and json.loads(orig.read_text()) == ass:
            continue
        if not _brutos(dados, "jogadas", ano):
            faltam.add(ano)
            continue
        progresso(f"montando temporada {ano}...")
        pasta.mkdir(parents=True, exist_ok=True)
        jogadas = montar_jogadas(dados, ano, bio)
        jj, sem_ponte = montar_jogador_jogo(dados, ano, jogos, bio)
        if sem_ponte:
            progresso(f"  [aviso] {ano}: {sem_ponte} registros do PFR/snaps sem ponte para o id do jogador")
        tabela_npz.salvar(jogadas, pasta / "jogadas.npz")
        tabela_npz.salvar(jj, pasta / "jogador_jogo.npz")
        if depois_da_temporada:
            depois_da_temporada(ano, pasta, jogadas, jj, jogos, bio)
        _gravar_json(orig, ass)
        res.temporadas.append(ano)
        if economia and ano < atual:
            res.liberado_bytes += fontes.descartar(dados, {ano})
    if faltam:
        raise FaltamBrutos(faltam)
    res.segundos = time.perf_counter() - t0
    return res


ARQUIVOS_TEMPORADA = ("jogadas.npz", "jogador_jogo.npz", "jogadores.npz", "origem.json")   # origem.json por último


def temporadas_faltando(dados: Path = fontes.DADOS, anos: range | None = None) -> list[int]:
    """
    As temporadas (de 2021 até a atual) que ainda não foram montadas até o fim.
    Uma primeira carga interrompida deixa algumas prontas e outras pela metade;
    só com a lista vazia a cópia local serve para subir o app. Sem o
    calendário (jogos.npz), nenhuma está pronta.
    """
    dados = Path(dados)
    anos = anos or range(fontes.PRIMEIRA_TEMPORADA, fontes.temporada_atual() + 1)
    if not (dados / "jogos.npz").exists():
        return list(anos)
    return [a for a in anos if not all((dados / "temporadas" / str(a) / f).exists() for f in ARQUIVOS_TEMPORADA)]


def sincronizar_e_montar(dados: Path = fontes.DADOS, progresso: Callable[[str], None] = print,
                         rede: fontes.Rede | None = None) -> tuple[fontes.Sincronizacao, Montagem]:
    """
    O ciclo completo de atualização (subida do servidor e atualização diária):
    baixa o que mudou, monta as temporadas afetadas com os ratings e, se uma
    temporada precisar ser remontada sem os brutos (descartados), baixa de novo
    só os dela. Levanta fontes.SemDados sem internet e sem cópia local.
    """
    sinc = fontes.sincronizar(dados, rede=rede, progresso=progresso)
    try:
        mont = atualizar(dados, progresso=progresso, depois_da_temporada=ratings.montar)
    except FaltamBrutos as e:
        extra = fontes.sincronizar(dados, rede=rede, progresso=progresso, forcar=e.anos)
        sinc.baixados += extra.baixados
        sinc.falhas += extra.falhas
        mont = atualizar(dados, progresso=progresso, depois_da_temporada=ratings.montar)
    return sinc, mont


def main(argv: list[str] | None = None, sincronizar=sincronizar_e_montar) -> int:
    """--estrito (usado pelo GitHub Actions, spec site-publico): sai com 1 se alguma fonte
    falhou, para o site não ser publicado de novo sem aviso. Sem ele, segue com a cópia local."""
    import argparse
    ap = argparse.ArgumentParser(description="Sincroniza as fontes e monta o que mudou.")
    ap.add_argument("--estrito", action="store_true", help="sai com erro se alguma fonte falhar")
    args = ap.parse_args(argv)
    s, r = sincronizar(progresso=lambda m: print(m, flush=True))
    print(f"ok em {r.segundos:.0f}s: temporadas {r.temporadas}, gerais {r.globais}, "
          f"{r.liberado_bytes / 2**20:.0f} MB de brutos descartados")
    for f in s.falhas:
        print("FALHA:", f, file=sys.stderr)
    return 1 if args.estrito and s.falhas else 0


if __name__ == "__main__":
    sys.exit(main())
