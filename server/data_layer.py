"""
Camada de dados do NFL Games sobre as tabelas montadas do nflverse (spec dados-externos).

Carrega as tabelas de dados/ (etl/montar.py e etl/ratings.py) e responde às
rotas atuais com o mesmo formato de antes, agora para as temporadas de 2021 em
diante (temporada regular e playoffs):

    dados/jogos.npz, dados/jogadores_bio.npz            gerais
    dados/temporadas/{ano}/jogadas.npz                  play-by-play + formação
    dados/temporadas/{ano}/jogador_jogo.npz             estatísticas por jogo
    dados/temporadas/{ano}/jogadores.npz                ratings por grupo

Nada é inventado: campos que a fonte não tem (velocidade de pico, tempo até a
pressão por tracking, coberturas da PFF) saem das respostas. Listas sem fonte
(insights, bastidores, alinhamentos) vão vazias, e o front esconde o bloco.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import threading
from collections import OrderedDict
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import noticias
import prancheta
import tabela_npz
from teams import team_info as _team_info

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
import ratings  # noqa: E402  (grupos e eixos dos ratings)

LESTE = ZoneInfo("America/New_York")      # horários do calendário da NFL
_VERSOES = itertools.count(1)

GRUPO_LABELS = {g: rotulo for g, (rotulo, _) in ratings.GRUPOS.items()}
ORDEM_GRUPOS = ["QB", "RB", "WRTE", "OL", "EDGE", "DL", "LB", "DB"]

PASS_RESULT_LABELS = {
    "C": "Passe completo", "I": "Passe incompleto", "S": "Sack", "IN": "Interceptação", "R": "Scramble",
}
TIPO_LABELS = {
    "run": "Corrida", "punt": "Punt", "field_goal": "Field goal", "kickoff": "Kickoff",
    "extra_point": "Ponto extra", "no_play": "Anulada (falta)", "qb_kneel": "Ajoelhada", "qb_spike": "Spike",
}
FONTES = [
    {"nome": "nflverse", "url": "https://github.com/nflverse/nflverse-data",
     "licenca": "CC-BY-4.0", "credito": "Dados de nflverse (nflverse-data), licença CC-BY-4.0",
     "usadoPara": "calendário, placar oficial, jogadas, jogadores em campo, formação e estatísticas"},
    {"nome": "FTN Data", "url": "https://ftndata.com",
     "licenca": "CC-BY-SA-4.0", "credito": "Charting de FTN Data via nflverse, licença CC-BY-SA-4.0",
     "usadoPara": "posição do QB, backfield, box e rushers (2022 em diante)"},
    {"nome": "Pro Football Reference", "url": "https://www.pro-football-reference.com",
     "licenca": "via nflverse", "credito": "Estatísticas avançadas e snaps de Pro Football Reference, via nflverse",
     "usadoPara": "pressões, tackles perdidos, drops, jardas após contato e snaps"},
    {"nome": "ESPN", "url": "https://www.espn.com/nfl/",
     "licenca": "consulta no navegador", "credito": "Placar ao vivo e matérias: ESPN",
     "usadoPara": "placar ao vivo e matéria do jogo (título, resumo e link)"},
]

# Estatísticas da temporada exibidas no perfil, por grupo: (rótulo, coluna, casas, unidade)
STATS_GRUPO: dict[str, list[tuple[str, str, int, str]]] = {
    "QB": [("Jogos", "jogos", 0, ""), ("Dropbacks", "dropbacks", 0, ""), ("Completos", "completions", 0, ""),
           ("Tentativas", "attempts", 0, ""), ("Jardas de passe", "passing_yards", 0, "jd"),
           ("TDs de passe", "passing_tds", 0, ""), ("Interceptações", "passing_interceptions", 0, ""),
           ("Sacks sofridos", "sacks_suffered", 0, ""), ("EPA de passe", "passing_epa", 1, ""),
           ("Corridas", "carries", 0, ""), ("Jardas correndo", "rushing_yards", 0, "jd"),
           ("TDs correndo", "rushing_tds", 0, "")],
    "RB": [("Jogos", "jogos", 0, ""), ("Corridas", "carries", 0, ""), ("Jardas correndo", "rushing_yards", 0, "jd"),
           ("TDs correndo", "rushing_tds", 0, ""), ("Após o contato", "rushing_yards_after_contact", 0, "jd"),
           ("Recepções", "receptions", 0, ""), ("Jardas recebidas", "receiving_yards", 0, "jd"),
           ("Fumbles perdidos", "rushing_fumbles_lost", 0, "")],
    "WRTE": [("Jogos", "jogos", 0, ""), ("Alvos", "targets", 0, ""), ("Recepções", "receptions", 0, ""),
             ("Jardas recebidas", "receiving_yards", 0, "jd"), ("TDs", "receiving_tds", 0, ""),
             ("Após a recepção", "receiving_yards_after_catch", 0, "jd"), ("Drops", "receiving_drop", 0, "")],
    "OL": [("Jogos", "jogos", 0, ""), ("Snaps de ataque", "offense_snaps", 0, ""), ("Faltas", "penalties", 0, "")],
    "DEF": [("Jogos", "jogos", 0, ""), ("Snaps de defesa", "defense_snaps", 0, ""),
            ("Tackles", "def_tackles_combined", 0, ""), ("Tackles para perda", "def_tackles_for_loss", 0, ""),
            ("Sacks", "def_sacks", 1, ""), ("QB hits", "def_qb_hits", 0, ""), ("Pressões", "def_pressures", 0, ""),
            ("Interceptações", "def_interceptions", 0, ""), ("Passes defendidos", "def_pass_defended", 0, "")],
    "DB": [("Jogos", "jogos", 0, ""), ("Snaps de defesa", "defense_snaps", 0, ""),
           ("Alvos permitidos", "def_targets", 0, ""), ("Completos permitidos", "def_completions_allowed", 0, ""),
           ("Jardas permitidas", "def_yards_allowed", 0, "jd"), ("Interceptações", "def_interceptions", 0, ""),
           ("Passes defendidos", "def_pass_defended", 0, ""), ("Tackles", "def_tackles_combined", 0, "")],
}
STATS_GRUPO.update({g: STATS_GRUPO["DEF"] for g in ("EDGE", "DL", "LB")})
SNAPS_GRUPO = {"QB": "offense_snaps", "RB": "offense_snaps", "WRTE": "offense_snaps", "OL": "offense_snaps"}
# Colunas do jogador_jogo que as rotas usam (a tabela tem ~180): o resto nem fica na memória.
COLS_JJ = sorted({"playerId", "gameId", "week", "time", "adversario", "offense_snaps", "defense_snaps",
                  "def_pressures", "def_sacks"} | {c for st in STATS_GRUPO.values() for _l, c, _d, _u in st} - {"jogos"})


# --------------------------------------------------------------------------- #
# utilidades de conversão segura para JSON
# --------------------------------------------------------------------------- #
def num(value, digits: int | None = None):
    """Converte para float/int nativo, devolvendo None para NaN/inf."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    if digits is not None:
        f = round(f, digits)
    return int(f) if digits == 0 else f


def text(value):
    """Normaliza texto, transformando NaN/'NA' em None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    return None if s in ("", "nan", "NA", "None") else s


def flag(value) -> bool:
    return bool(num(value))


def clock_to_seconds(clock) -> int | None:
    s = text(clock)
    if not s or ":" not in s:
        return None
    mm, ss = s.split(":")[:2]
    try:
        return int(mm) * 60 + int(ss)
    except ValueError:
        return None


def _registros(df: pd.DataFrame) -> list[dict]:
    """df.to_dict("records") coluna a coluna (~10x mais rápido)."""
    cols = list(df.columns)
    valores = [df[c].tolist() for c in cols]
    return [dict(zip(cols, linha)) for linha in zip(*valores)]


def _media(s: pd.Series, digits: int = 3):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return num(s.mean(), digits) if len(s) else None


def team_info(abbr: str, season: int | None = None) -> dict:
    info = _team_info(abbr)
    if abbr == "WAS":   # o nome mudou em 2022
        info["name"] = "Washington Football Team" if season == 2021 else "Washington Commanders"
        info["nick"] = "Football Team" if season == 2021 else "Commanders"
    return info


def _objeto(df: pd.DataFrame) -> pd.DataFrame:
    """Categorias do .npz viram object: comparações e .tolist() ficam simples."""
    cats = [c for c in df.columns if isinstance(df[c].dtype, pd.CategoricalDtype)]
    return df.astype({c: object for c in cats}) if cats else df


def _faixas(ids: np.ndarray) -> dict[int, tuple[int, int]]:
    """{id: (início, fim)} de um vetor já ordenado."""
    if not len(ids):
        return {}
    cortes = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    fins = np.r_[cortes[1:], len(ids)]
    return {int(ids[i]): (int(i), int(f)) for i, f in zip(cortes, fins)}


# --------------------------------------------------------------------------- #
class Temporada:
    """As três tabelas de um ano, com índices por jogo e por jogador."""

    def __init__(self, pasta: Path, ano: int):
        self.ano = ano
        # As tabelas grandes ficam com o texto como categoria (~3x menos memória que object).
        j = tabela_npz.carregar(pasta / "jogadas.npz")
        self.jogadas = j.sort_values(["gameId", "seq"], kind="stable").reset_index(drop=True)
        self.faixa_jogo = _faixas(self.jogadas["gameId"].to_numpy())
        esc = self.jogadas[self.jogadas["play_type"].isin(["pass", "run"])]
        self.resumo_jogo = {
            int(g): (int(r["n"]), int(r["db"]), int(r["sk"]))
            for g, r in esc.groupby("gameId", observed=True).agg(n=("play_id", "size"), db=("qb_dropback", "sum"),
                                                  sk=("sack", "sum")).iterrows()}
        self._linhas: OrderedDict[int, dict[int, dict]] = OrderedDict()
        self._lock = threading.Lock()

        jj = tabela_npz.carregar(pasta / "jogador_jogo.npz")
        jj = jj[[c for c in COLS_JJ if c in jj.columns]]
        self.jj = jj.sort_values(["gameId", "playerId"], kind="stable").reset_index(drop=True)
        self.faixa_jj = _faixas(self.jj["gameId"].to_numpy())
        self.jj_jogador = self.jj.groupby("playerId", sort=False, observed=True).indices

        jog = _objeto(tabela_npz.carregar(pasta / "jogadores.npz"))
        jog = jog[jog["grupo"].notna()].copy()
        jog["avaliado"] = jog["avaliado"].astype(bool)
        jog["posicao_exibida"] = jog["posicao_elenco"].where(jog["posicao_elenco"].notna(), jog["posicao"])
        jog["snaps"] = np.where(jog["grupo"].map(SNAPS_GRUPO).notna(), jog["offense_snaps"], jog["defense_snaps"])
        self.jogadores = jog.set_index("playerId", drop=False)
        self.league = self._baselines()

    def jogadas_do_jogo(self, game_id: int) -> pd.DataFrame | None:
        f = self.faixa_jogo.get(game_id)
        return None if f is None else self.jogadas.iloc[f[0]:f[1]]

    def linhas_do_jogo(self, game_id: int) -> dict[int, dict] | None:
        """{play_id: linha} de um jogo, montado uma vez (LRU): abrir uma jogada vira consulta direta."""
        with self._lock:
            if game_id in self._linhas:
                self._linhas.move_to_end(game_id)
                return self._linhas[game_id]
        plays = self.jogadas_do_jogo(game_id)
        if plays is None:
            return None
        linhas: dict[int, dict] = {}
        for r in _registros(plays):
            linhas.setdefault(int(r["play_id"]), r)
        with self._lock:
            self._linhas[game_id] = linhas
            while len(self._linhas) > 24:
                self._linhas.popitem(last=False)
        return linhas

    def jj_do_jogo(self, game_id: int) -> pd.DataFrame | None:
        f = self.faixa_jj.get(game_id)
        return None if f is None else self.jj.iloc[f[0]:f[1]]

    def _baselines(self) -> dict:
        p = self.jogadas
        esc = p[p["play_type"].isin(["pass", "run"])]
        db = esc[esc["qb_dropback"] == 1]
        tent = db["complete_pass"].fillna(0) + db["incomplete_pass"].fillna(0) + db["interception"].fillna(0)
        n_tent = float(tent.sum())
        terceira = esc[esc["down"] == 3]
        rush = pd.to_numeric(db["rushers"], errors="coerce").dropna()
        return {
            "plays": int(len(esc)), "games": int(esc["gameId"].nunique()),
            "completionRate": num(db["complete_pass"].sum() / n_tent, 3) if n_tent else None,
            "timeToThrow": _media(db["tempo_lancamento"], 2),
            "pressureRate": _media(db["pressao"]),
            "sackRate": _media(db["sack"]),
            "intRate": num(db["interception"].sum() / n_tent, 3) if n_tent else None,
            "yardsPerDropback": _media(db["yards_gained"], 2),
            "yardsPerPlay": _media(esc["yards_gained"], 2),
            "blitzRate": num((rush > 4).mean(), 3) if len(rush) else None,
            "explosiveRate": num((esc["yards_gained"] >= 20).mean(), 3) if len(esc) else None,
            "playActionRate": _media(db["play_action"]),
            "thirdDownRate": _media(terceira["third_down_converted"]),
        }


# --------------------------------------------------------------------------- #
class NFLData:
    """Tudo em memória; as respostas prontas ficam no cache do servidor."""

    def __init__(self, dados: Path, hoje=None):
        self.dados = Path(dados)
        self._hoje = hoje            # só para testes: data fixa em vez de hoje
        self.versao = next(_VERSOES)  # entra na chave do cache: resposta de dados velhos nunca é servida
        self.jogos = _objeto(tabela_npz.carregar(self.dados / "jogos.npz"))
        self.jogos = self.jogos.sort_values(["season", "week", "gameday", "gametime", "gameId"]).reset_index(drop=True)
        self._jogo_idx = {int(g): i for i, g in enumerate(self.jogos["gameId"].tolist())}
        bio = _objeto(tabela_npz.carregar(self.dados / "jogadores_bio.npz"))
        self.bio = bio.set_index("playerId", drop=False)
        self.temporadas: dict[int, Temporada] = {}
        for ano in sorted(int(a) for a in self.jogos["season"].unique()):
            pasta = self.dados / "temporadas" / str(ano)
            if all((pasta / f).exists() for f in ("jogadas.npz", "jogador_jogo.npz", "jogadores.npz")):
                self.temporadas[ano] = Temporada(pasta, ano)
        if not self.temporadas:
            raise FileNotFoundError(f"nenhuma temporada montada em {self.dados / 'temporadas'}")
        self.atual = max(self.temporadas)
        self._noticias: dict[int, list[dict]] = {}
        self._lock_noticias = threading.Lock()

    # ------------------------------ auxiliares ---------------------------- #
    def hoje(self) -> datetime:
        return self._hoje or datetime.now(timezone.utc)

    def temporada(self, season: int | None) -> Temporada | None:
        return self.temporadas.get(self.atual if season is None else season)

    def _linha_jogo(self, game_id: int) -> dict | None:
        i = self._jogo_idx.get(game_id)
        return None if i is None else _registros(self.jogos.iloc[i:i + 1])[0]

    def _inicio_utc(self, g: dict) -> datetime | None:
        dia, hora = text(g.get("gameday")), text(g.get("gametime"))
        if not dia:
            return None
        try:
            d = date.fromisoformat(dia)
            h = dtime.fromisoformat(hora) if hora else dtime(13, 0)
        except ValueError:
            return None
        return datetime.combine(d, h, tzinfo=LESTE).astimezone(timezone.utc)

    def _status(self, g: dict) -> str:
        if num(g.get("home_score")) is not None and num(g.get("away_score")) is not None:
            return "encerrado"
        inicio = self._inicio_utc(g)
        return "agendado" if inicio is None or inicio > self.hoje() else "sem_resultado"

    def _semana_atual(self, ano: int) -> int | None:
        j = self.jogos[self.jogos["season"] == ano]
        if j.empty:
            return None
        hoje = self.hoje().astimezone(LESTE).date().isoformat()
        ja_comecou = j[j["gameday"].astype(str) <= hoje]
        # a última semana que já começou; antes do 1º jogo, a primeira
        return int(ja_comecou["week"].iloc[-1]) if len(ja_comecou) else int(j["week"].iloc[0])

    # --------------------------------- meta -------------------------------- #
    def meta(self) -> dict:
        temporadas = []
        for ano, t in sorted(self.temporadas.items(), reverse=True):
            j = self.jogos[self.jogos["season"] == ano]
            semanas = []
            for (week, gt, rod), g in j.groupby(["week", "game_type", "rodada"], sort=True):
                semanas.append({"week": int(week), "gameType": text(gt), "rodada": text(rod),
                                "games": int(len(g)), "dates": sorted({text(d) for d in g["gameday"]})})
            temporadas.append({
                "season": ano, "currentWeek": self._semana_atual(ano), "weeks": semanas,
                "counts": {"games": int(len(j)), "played": int(j["home_score"].notna().sum()),
                           "plays": int(len(t.jogadas)), "players": int(len(t.jogadores))},
            })
        atual = next(x for x in temporadas if x["season"] == self.atual)
        abbrs = sorted(set(self.jogos["home"].dropna()) | set(self.jogos["away"].dropna()))
        manifesto = self.dados / "manifest.json"
        ultima = None
        if manifesto.exists():
            try:
                ultima = json.loads(manifesto.read_text(encoding="utf-8")).get("ultimaSincronizacao")
            except (OSError, ValueError):
                ultima = None
        return {
            "season": self.atual,
            "currentWeek": atual["currentWeek"],
            "seasons": temporadas,
            "weeks": atual["weeks"],
            "teams": {a: team_info(a, self.atual) for a in abbrs},
            "counts": atual["counts"],
            "league": self.temporadas[self.atual].league,
            "roleLabels": {g: GRUPO_LABELS[g] for g in ORDEM_GRUPOS},
            "ultimaAtualizacao": ultima,
            "fontes": FONTES,
        }

    # --------------------------------- jogos ------------------------------- #
    def games_list(self, season: int | None = None, week: int | None = None, date: str | None = None) -> list[dict]:
        ano = self.atual if season is None else season
        g = self.jogos[self.jogos["season"] == ano]
        if week is not None:
            g = g[g["week"] == week]
        if date:
            g = g[g["gameday"] == date]
        return [self._game_card(r) for r in _registros(g)]

    def _game_card(self, g: dict) -> dict:
        gid, ano = int(g["gameId"]), int(g["season"])
        t = self.temporadas.get(ano)
        resumo = t.resumo_jogo.get(gid) if t else None      # (jogadas, dropbacks, sacks)
        home, away = text(g["home"]), text(g["away"])
        inicio = self._inicio_utc(g)
        return {
            "gameId": gid,
            "season": ano,
            "week": int(g["week"]),
            "gameType": text(g["game_type"]),
            "rodada": text(g["rodada"]),
            "date": text(g["gameday"]),
            "kickoff": text(g["gametime"]),
            "kickoffUtc": inicio.isoformat().replace("+00:00", "Z") if inicio else None,
            "home": {**team_info(home, ano), "score": num(g["home_score"], 0)},
            "away": {**team_info(away, ano), "score": num(g["away_score"], 0)},
            "overtime": None if num(g["overtime"]) is None else bool(num(g["overtime"])),
            "status": self._status(g),
            "espnId": text(g["espnId"]),
            "stadium": text(g.get("stadium")),
            "plays": resumo[0] if resumo else None,
            "dropbacks": resumo[1] if resumo else None,
            "sacks": resumo[2] if resumo else None,
        }

    def game(self, game_id: int) -> dict | None:
        g = self._linha_jogo(game_id)
        if g is None:
            return None
        card = self._game_card(g)
        home, away = card["home"]["abbr"], card["away"]["abbr"]
        t = self.temporadas.get(card["season"])
        plays = t.jogadas_do_jogo(game_id) if t else None
        card["teams"] = {"home": self._team_game(plays, home, card["season"]),
                         "away": self._team_game(plays, away, card["season"])}
        card["tendencies"] = {"home": self._tendencies(plays, home), "away": self._tendencies(plays, away)}
        card["insights"] = []    # sugestões táticas saem na novo-visual (não são portadas)
        card["notes"] = []
        card["watch"] = self.watch_list(game_id)
        return card

    @staticmethod
    def _team_game(plays: pd.DataFrame | None, abbr: str, season: int) -> dict:
        base = team_info(abbr, season)
        if plays is None or plays.empty:
            return {**base, "offense": {}, "defense": {}}
        esc = plays[plays["play_type"].isin(["pass", "run"])]
        of, de = esc[esc["posteam"] == abbr], esc[esc["defteam"] == abbr]

        def lado(p: pd.DataFrame) -> dict:
            db = p[p["qb_dropback"] == 1]
            tent = int((db["complete_pass"].fillna(0) + db["incomplete_pass"].fillna(0)
                        + db["interception"].fillna(0)).sum())
            comp = int(db["complete_pass"].fillna(0).sum())
            corr = p[p["play_type"] == "run"]
            terc = p[p["down"] == 3]
            rush = pd.to_numeric(db["rushers"], errors="coerce").dropna()
            return {
                "plays": int(len(p)), "dropbacks": int(len(db)), "attempts": tent, "completions": comp,
                "completionRate": num(comp / tent, 4) if tent else None,
                "passYards": num(db["yards_gained"].sum(), 0), "rushes": int(len(corr)),
                "rushYards": num(corr["yards_gained"].sum(), 0), "netYards": num(p["yards_gained"].sum(), 0),
                "yardsPerPlay": _media(p["yards_gained"], 2), "yardsPerDropback": _media(db["yards_gained"], 2),
                "sacks": int(p["sack"].fillna(0).sum()), "interceptions": int(p["interception"].fillna(0).sum()),
                "fumblesLost": int(p["fumble_lost"].fillna(0).sum()),
                "touchdowns": int((p["touchdown"].fillna(0) - p["return_touchdown"].fillna(0)).clip(lower=0).sum()),
                "explosive": int((p["yards_gained"] >= 20).sum()),
                "thirdDownAtt": int(len(terc)), "thirdDownConv": int(terc["third_down_converted"].fillna(0).sum()),
                "timeToThrow": _media(db["tempo_lancamento"], 2), "pressureRate": _media(db["pressao"]),
                "playActionRate": _media(db["play_action"]),
                "blitzRate": num((rush > 4).mean(), 3) if len(rush) else None,
            }

        o, d = lado(of), lado(de)
        offense = {k: o[k] for k in ("plays", "dropbacks", "attempts", "completions", "completionRate", "passYards",
                                     "rushes", "rushYards", "netYards", "yardsPerPlay", "yardsPerDropback",
                                     "interceptions", "fumblesLost", "touchdowns", "explosive", "thirdDownAtt",
                                     "thirdDownConv", "timeToThrow", "playActionRate")}
        offense["sacksTaken"] = o["sacks"]
        offense["pressureRateAllowed"] = o["pressureRate"]
        pressoes = pd.to_numeric(de[de["qb_dropback"] == 1]["pressao"], errors="coerce")
        defense = {"dropbacksFaced": d["dropbacks"], "pressures": int(pressoes.fillna(0).sum()) if pressoes.notna().any() else None,
                   "pressureRate": d["pressureRate"], "sacks": d["sacks"], "interceptions": d["interceptions"],
                   "blitzRate": d["blitzRate"], "completionRateAllowed": d["completionRate"],
                   "yardsAllowed": d["netYards"], "explosiveAllowed": d["explosive"]}
        limpa = lambda x: {k: v for k, v in x.items() if v is not None}  # noqa: E731  sem fonte: fora (8.3)
        return {**base, "offense": limpa(offense), "defense": limpa(defense)}

    @staticmethod
    def _tendencies(plays: pd.DataFrame | None, abbr: str) -> dict:
        vazio = {"formations": [], "personnel": [], "coverages": [], "coverageTypes": []}
        if plays is None or plays.empty:
            return vazio
        esc = plays[plays["play_type"].isin(["pass", "run"])]
        of, de = esc[esc["posteam"] == abbr], esc[esc["defteam"] == abbr]

        def dist(frame: pd.DataFrame, col: str) -> list[dict]:
            f = frame[frame[col].notna()]
            if f.empty:
                return []
            grp = f.groupby(col, observed=True).agg(plays=("play_id", "size"), yards=("yards_gained", "mean"),
                                     comp=("complete_pass", "sum"), db=("qb_dropback", "sum"))
            grp = grp.sort_values("plays", ascending=False)
            total = int(grp["plays"].sum())
            return [{"label": text(k), "plays": int(r["plays"]), "share": num(r["plays"] / total, 3),
                     "yardsPerPlay": num(r["yards"], 2),
                     "completionRate": num(r["comp"] / r["db"], 3) if r["db"] else None}
                    for k, r in grp.iterrows() if text(k)]

        return {"formations": dist(of, "formacao"), "personnel": dist(of, "pessoal_of"),
                "coverages": dist(de, "cobertura"), "coverageTypes": dist(de, "homem_zona")}

    # -------------------------------- jogadas ------------------------------ #
    def _plays(self, game_id: int) -> tuple[pd.DataFrame | None, Temporada | None]:
        g = self._linha_jogo(game_id)
        t = self.temporadas.get(int(g["season"])) if g else None
        return (t.jogadas_do_jogo(game_id) if t else None), t

    def game_plays(self, game_id: int, quarter: int | None = None, team: str | None = None) -> list[dict]:
        plays, _t = self._plays(game_id)
        if plays is None:
            return []
        if quarter:
            plays = plays[plays["qtr"] == quarter]
        if team:
            plays = plays[plays["posteam"] == team]
        return [self._play_card(r) for r in _registros(plays)]

    @staticmethod
    def _eh_timeout(r: dict) -> bool:
        """O nflverse marca os pedidos de tempo como no_play, como as jogadas anuladas por falta."""
        return text(r.get("play_type")) == "no_play" and "timeout" in (text(r.get("desc")) or "").lower()

    @staticmethod
    def _pass_result(r: dict) -> str | None:
        if text(r.get("play_type")) != "pass":
            return None
        if flag(r.get("sack")):
            return "S"
        if flag(r.get("interception")):
            return "IN"
        if flag(r.get("qb_scramble")):
            return "R"
        if flag(r.get("complete_pass")):
            return "C"
        if flag(r.get("incomplete_pass")):
            return "I"
        return None

    def _play_card(self, r: dict) -> dict:
        pr = self._pass_result(r)
        tipo = text(r.get("play_type"))
        result = num(r.get("yards_gained"), 0)
        rushers = num(r.get("rushers"), 0)
        tags = []
        if flag(r.get("touchdown")):
            tags.append("TOUCHDOWN")
        if pr == "S":
            tags.append("SACK")
        if pr == "IN":
            tags.append("INTERCEPTAÇÃO")
        if flag(r.get("fumble_lost")):
            tags.append("FUMBLE")
        if tipo in ("pass", "run") and result is not None and result >= 20:
            tags.append("JOGADA EXPLOSIVA")
        if flag(r.get("penalty")):
            tags.append("FALTA")
        if rushers is not None and rushers > 4:
            tags.append("BLITZ")
        if flag(r.get("play_action")):
            tags.append("PLAY ACTION")
        tem_formacao = text(r.get("formacao")) is not None or text(r.get("qb_local")) in ("S", "U", "P")
        # O FTN sai 2 a 3 dias depois do jogo: até lá o passe/corrida está "pendente", não "indisponível".
        pendente = not tem_formacao and tipo in ("pass", "run") and flag(r.get("ftn_pendente"))
        card = {
            "gameId": int(r["gameId"]),
            "playId": int(r["play_id"]),
            "seq": num(r.get("seq"), 0),
            "quarter": num(r.get("qtr"), 0),
            "clock": text(r.get("time")),
            "clockSeconds": clock_to_seconds(r.get("time")),
            "down": num(r.get("down"), 0),
            "yardsToGo": num(r.get("ydstogo"), 0),
            "offense": text(r.get("posteam")),
            "defense": text(r.get("defteam")),
            "yardline": text(r.get("yrdln")) or "",
            "absoluteYardline": None if num(r.get("yardline_100")) is None else 110 - num(r.get("yardline_100"), 0),
            "description": text(r.get("desc")) or "",
            "playType": tipo,
            "result": result,
            "epa": num(r.get("epa"), 3),
            "passResult": pr,
            "passResultLabel": PASS_RESULT_LABELS.get(pr or "") or
                               ("Tempo técnico" if self._eh_timeout(r) else TIPO_LABELS.get(tipo or "", "—")),
            "formation": text(r.get("formacao")) or prancheta.NOME_QB.get(text(r.get("qb_local")) or ""),
            "personnelO": text(r.get("pessoal_of")),
            "personnelD": text(r.get("pessoal_def")),
            "coverage": text(r.get("cobertura")),
            "coverageType": text(r.get("homem_zona")),
            "playAction": None if num(r.get("play_action")) is None else flag(r.get("play_action")),
            "defendersInBox": num(r.get("box"), 0),
            "rushers": rushers,
            "blitz": None if rushers is None else rushers > 4,
            "pressured": None if num(r.get("pressao")) is None else flag(r.get("pressao")),
            "timeToThrow": num(r.get("tempo_lancamento"), 2),
            "penaltyYards": num(r.get("penalty_yards"), 0),
            "score": {"home": num(r.get("total_home_score"), 0), "away": num(r.get("total_away_score"), 0)},
            "hasFormation": tem_formacao,
            "semFormacao": not tem_formacao,
            "formacaoPendente": pendente,
            "tags": tags,
        }
        return {k: v for k, v in card.items() if v is not None or k in ("down", "yardsToGo", "passResult", "result")}

    def _jogada(self, game_id: int, play_id: int) -> tuple[dict | None, Temporada | None]:
        g = self._linha_jogo(game_id)
        t = self.temporadas.get(int(g["season"])) if g else None
        linhas = t.linhas_do_jogo(game_id) if t else None
        return (linhas.get(play_id) if linhas else None), t

    def play(self, game_id: int, play_id: int) -> dict | None:
        r, t = self._jogada(game_id, play_id)
        if r is None:
            return None
        card = self._play_card(r)
        card["players"] = self._participantes(r, t)
        return card

    def _rating(self, t: Temporada | None, pid) -> int | None:
        if t is None or not pid or pid not in t.jogadores.index:
            return None
        return num(t.jogadores.at[pid, "rating"], 0)

    def _participantes(self, r: dict, t: Temporada | None) -> list[dict]:
        out = []
        for lado, pre, time_ in (("offense", "of", r.get("posteam")), ("defense", "def", r.get("defteam"))):
            ids, nomes, pos, nums = (str(r.get(f"{pre}_{c}") or "").split(";")
                                     for c in ("ids", "nomes", "posicoes", "numeros"))
            if not text(r.get(f"{pre}_posicoes")):
                continue
            for i, p in enumerate(pos):
                pid = text(ids[i]) if i < len(ids) else None
                out.append({"nflId": pid, "name": text(nomes[i]) if i < len(nomes) else None,
                            "position": text(p), "jersey": num(nums[i], 0) if i < len(nums) else None,
                            "side": lado, "team": text(time_), "rating": self._rating(t, pid)})
        return out

    # --------------------------------- prancheta --------------------------- #
    def play_tracking(self, game_id: int, play_id: int) -> dict | None:
        """Esquema ilustrativo da formação no formato do /tracking (1 quadro)."""
        r, t = self._jogada(game_id, play_id)
        if r is None:
            return None
        e = prancheta.esquema(r)
        if e is None:
            return None
        for p in e["players"]:
            p["rating"] = self._rating(t, p["nflId"])
        e["play"] = self._play_card(r)
        return e

    def snap_formation(self, game_id: int, play_id: int) -> dict | None:
        tr = self.play_tracking(game_id, play_id)
        if not tr:
            return None
        players = [{k: p[k] for k in ("nflId", "name", "jersey", "team", "side", "position", "rating")}
                   | {"x": p["t"][0][0], "y": p["t"][0][1]} for p in tr["players"]]
        return {"gameId": game_id, "playId": play_id, "playDirection": tr["playDirection"],
                "lineOfScrimmage": tr["lineOfScrimmage"], "yardsToGo": tr["yardsToGo"], "ball": tr["ball"][0],
                "players": players, "play": tr["play"], "ilustrativo": True, "generico": tr["generico"],
                "formacao": tr["formacao"]}

    # ------------------------------- jogadores ----------------------------- #
    def players_list(self, season: int | None = None, q: str | None = None, position: str | None = None,
                     role: str | None = None, team: str | None = None, rated_only: bool = True,
                     limit: int = 40) -> list[dict]:
        t = self.temporada(season)
        if t is None:
            return []
        p = t.jogadores
        if rated_only:
            p = p[p["avaliado"]]
        if q:
            p = p[p["nome"].astype(str).str.contains(q, case=False, na=False, regex=False)]
        if position:
            wanted = {s.strip().upper() for s in position.split(",") if s.strip()}
            p = p[p["posicao_exibida"].astype(str).str.upper().isin(wanted)]
        if role:
            p = p[p["grupo"] == role.upper()]
        if team:
            p = p[p["time"] == team.upper()]
        p = p.sort_values(["rating", "volume"], ascending=[False, False], na_position="last").head(limit)
        return [self._player_card(r, t.ano) for r in _registros(p)]

    @staticmethod
    def _player_card(r: dict, ano: int) -> dict:
        grupo = text(r["grupo"])
        return {
            "nflId": text(r["playerId"]),
            "name": text(r["nome"]),
            "position": text(r["posicao_exibida"]),
            "team": text(r["time"]),
            "teamInfo": team_info(text(r["time"]) or "", ano),
            "season": ano,
            "role": grupo,
            "roleLabel": GRUPO_LABELS.get(grupo or "", ""),
            "rating": num(r["rating"], 0),
            "rated": bool(r["avaliado"]),
            "baseReduzida": bool(r["baseReduzida"]),
            "snaps": num(r["snaps"], 0),
            "games": num(r["jogos"], 0),
        }

    def player(self, pid: str, season: int | None = None) -> dict | None:
        anos = [a for a, t in sorted(self.temporadas.items()) if pid in t.jogadores.index]
        if not anos:
            return None
        ano = season if season in anos else (None if season is not None else anos[-1])
        if ano is None:
            return None
        t = self.temporadas[ano]
        r = _registros(t.jogadores.loc[[pid]])[0]
        b = _registros(self.bio.loc[[pid]])[0] if pid in self.bio.index else {}
        grupo = text(r["grupo"])
        papel = {"role": grupo, "roleLabel": GRUPO_LABELS.get(grupo or "", ""), "snaps": num(r["snaps"], 0),
                 "rating": num(r["rating"], 0), "rated": bool(r["avaliado"]),
                 "baseReduzida": bool(r["baseReduzida"]),
                 "minimo": num(r["minimo"], 0), "volume": num(r["volume"], 0),
                 "radar": self._radar(r), "stats": self._stats(r)}
        return {
            **self._player_card(r, ano),
            "seasons": anos,
            "foto": text(b.get("foto")),
            "height": self._altura(b.get("altura")),
            "weight": num(b.get("peso"), 0),
            "college": text(b.get("faculdade")),
            "birthDate": text(b.get("nascimento")),
            "age": self._age(text(b.get("nascimento")), ano),
            "roles": [papel],
            "positionsLinedUp": [],   # alinhamento por jogada: sem fonte pública
            "gameLog": self._game_log(pid, t),
        }

    @staticmethod
    def _altura(pol) -> str | None:
        """Polegadas -> pés-polegadas (73 -> "6-1"), como no dataset antigo."""
        n = num(pol, 0)
        return None if not n else f"{n // 12}-{n % 12}"

    @staticmethod
    def _age(birth: str | None, ano: int) -> int | None:
        if not birth:
            return None
        try:
            born = pd.Timestamp(birth)
        except (ValueError, TypeError):
            return None
        return int((pd.Timestamp(f"{ano}-09-01") - born).days // 365.25)   # idade no início da temporada

    @staticmethod
    def _radar(r: dict) -> list[dict]:
        out = []
        for i, e in enumerate(ratings.EIXOS.get(text(r["grupo"]) or "", [])):
            raw = num(r.get(f"eixo{i}_valor"))
            if raw is None:
                valor = None
            elif e.unidade == "%":
                valor = round(raw * 100, 1)
            elif e.chave == "snaps_of":
                valor = int(raw)
            elif e.unidade == "pp":
                valor = round(raw, 1)
            else:
                valor = round(raw, 2)
            eixo = {"label": e.rotulo, "metric": e.chave, "value": valor, "unit": e.unidade,
                    "percentile": num(r.get(f"eixo{i}_pct"), 0), "lowerIsBetter": e.menor_melhor}
            if text(r.get(f"eixo{i}_motivo")):
                eixo["motivo"] = text(r[f"eixo{i}_motivo"])
            out.append(eixo)
        return out

    @staticmethod
    def _stats(r: dict) -> list[dict]:
        out = []
        for label, col, digits, unit in STATS_GRUPO.get(text(r["grupo"]) or "", []):
            v = num(r.get(col), digits)
            if v is not None:
                out.append({"label": label, "value": v, "unit": unit})
        return out

    def _game_log(self, pid: str, t: Temporada) -> list[dict]:
        idx = t.jj_jogador.get(pid)
        if idx is None:
            return []
        grupo = text(t.jogadores.at[pid, "grupo"]) if pid in t.jogadores.index else None
        picks = [s for s in STATS_GRUPO.get(grupo or "", []) if s[1] != "jogos"][:5]
        rows = []
        for r in _registros(t.jj.iloc[np.sort(idx)]):
            g = self._linha_jogo(int(r["gameId"])) or {}
            snaps = (num(r.get("offense_snaps")) or 0) + (num(r.get("defense_snaps")) or 0)
            linha = {"gameId": int(r["gameId"]), "week": num(r.get("week"), 0), "rodada": text(g.get("rodada")),
                     "team": text(r.get("time")), "opponent": text(r.get("adversario")),
                     "snaps": int(snaps) if snaps else None,
                     "stats": [{"label": lb, "value": num(r.get(c), d), "unit": u} for lb, c, d, u in picks
                               if num(r.get(c), d) is not None]}
            for chave, col in (("pressures", "def_pressures"), ("sacks", "def_sacks")):
                if num(r.get(col)) is not None:
                    linha[chave] = num(r.get(col), 1 if chave == "sacks" else 0)
            rows.append({k: v for k, v in linha.items() if v is not None})
        rows.sort(key=lambda x: (x.get("week") or 0, x["gameId"]))
        return rows

    def compare(self, a: str, b: str, season: int | None = None) -> dict | None:
        """Só compara jogadores do mesmo grupo e da mesma temporada (5.6)."""
        ano = self.atual if season is None else season
        pa, pb = self.player(a, ano), self.player(b, ano)
        if not pa or not pb:
            return None
        ra, rb = pa["roles"][0], pb["roles"][0]
        mesmo = ra["role"] == rb["role"]
        rows = []
        if mesmo:
            por = {s["label"]: s for s in rb["stats"]}
            rows = [{"label": s["label"], "unit": s["unit"], "left": s["value"], "right": por[s["label"]]["value"]}
                    for s in ra["stats"] if s["label"] in por]
        return {"sameRole": mesmo, "season": ano, "role": ra["role"], "roleLabel": ra["roleLabel"],
                "left": pa, "right": pb, "rows": rows}

    def leaders(self, metric: str, role: str | None = None, limit: int = 10, season: int | None = None) -> list[dict]:
        t = self.temporada(season)
        if t is None or metric not in t.jogadores.columns:
            return []
        eixos = [(g, e) for g, es in ratings.EIXOS.items() for e in es if e.chave == metric]
        if not eixos:
            return []
        s = t.jogadores[t.jogadores["avaliado"]]
        grupos = {g for g, _ in eixos}
        if role:
            s = s[s["grupo"] == role.upper()]
        else:
            s = s[s["grupo"].isin(grupos)]
        menor = eixos[0][1].menor_melhor
        s = s.dropna(subset=[metric]).sort_values(metric, ascending=menor).head(limit)
        out = []
        for r in _registros(s):
            card = self._player_card(r, t.ano)
            card["metric"] = {"key": metric, "value": num(r[metric], 3)}
            out.append(card)
        return out

    def watch_list(self, game_id: int) -> list[dict]:
        """Destaques do jogo: o melhor avaliado de cada grupo entre os que atuaram."""
        g = self._linha_jogo(game_id)
        t = self.temporadas.get(int(g["season"])) if g else None
        jj = t.jj_do_jogo(game_id) if t else None
        if jj is None or jj.empty:
            return []
        snaps = (jj["offense_snaps"].fillna(0) + jj["defense_snaps"].fillna(0)).to_numpy()
        ids = [pid for pid, s in zip(jj["playerId"].tolist(), snaps) if s >= 8 and pid in t.jogadores.index]
        cand = t.jogadores.loc[ids]
        cand = cand[cand["avaliado"]]
        out = []
        for grupo in ORDEM_GRUPOS:
            top = cand[cand["grupo"] == grupo].sort_values("rating", ascending=False).head(1)
            for r in _registros(top):
                card = self._player_card(r, t.ano)
                card["gameSnaps"] = int(snaps[jj["playerId"].tolist().index(r["playerId"])])
                out.append(card)
        return out

    # -------------------------------- notícias ---------------------------- #
    def news(self, season: int | None = None, week: int | None = None) -> list[dict]:
        """Notícias geradas dos dados (novo-visual, Requisito 7), da mais incomum para a menos."""
        ano = self.atual if season is None else season
        t = self.temporadas.get(ano)
        if t is None:
            return []
        with self._lock_noticias:          # uma vez por temporada; depois vem da memória
            if ano not in self._noticias:
                nomes = dict(zip(self.bio["playerId"].tolist(), self.bio["nome"].tolist()))
                self._noticias[ano] = noticias.gerar(self.jogos[self.jogos["season"] == ano], t.jogadas, t.jj, nomes)
        todas = self._noticias[ano]
        return [n for n in todas if n["week"] == week] if week is not None else list(todas)

    def summary(self, season: int | None = None) -> dict:
        ano = self.atual if season is None else season
        t = self.temporadas[ano]
        return {"season": ano, "ratedPlayers": int(t.jogadores["avaliado"].sum())}

    # ------------------------------ comentarista -------------------------- #
    def broadcast(self, game_id: int) -> dict | None:
        """Todas as jogadas em ordem, com o placar oficial de cada momento e a narração."""
        g = self._linha_jogo(game_id)
        plays, _t = self._plays(game_id)
        if g is None or plays is None or plays.empty:
            return None
        ano = int(g["season"])
        home, away = text(g["home"]), text(g["away"])
        zero = {"plays": 0, "dropbacks": 0, "completions": 0, "attempts": 0, "yards": 0, "sacksTaken": 0,
                "pressures": 0, "touchdowns": 0}
        cum = {home: dict(zero), away: dict(zero)}
        feed = []
        for r in _registros(plays):
            of, de = text(r.get("posteam")), text(r.get("defteam"))
            tipo = text(r.get("play_type"))
            if of in cum and tipo in ("pass", "run"):
                c = cum[of]
                c["plays"] += 1
                c["dropbacks"] += int(flag(r.get("qb_dropback")))
                c["completions"] += int(flag(r.get("complete_pass")))
                c["attempts"] += int(flag(r.get("complete_pass")) or flag(r.get("incomplete_pass"))
                                     or flag(r.get("interception")))
                c["yards"] += int(num(r.get("yards_gained"), 0) or 0)
                c["sacksTaken"] += int(flag(r.get("sack")))
                if de in cum and flag(r.get("pressao")):
                    cum[de]["pressures"] += 1
            if of in cum and flag(r.get("touchdown")) and not flag(r.get("return_touchdown")):
                cum[of]["touchdowns"] += 1
            card = self._play_card(r)
            card["narration"] = self._narrate(r, card)
            card["cumulative"] = {"home": dict(cum[home]), "away": dict(cum[away])}
            feed.append(card)
        return {
            "gameId": game_id,
            "home": {**team_info(home, ano), "score": num(g["home_score"], 0)},
            "away": {**team_info(away, ano), "score": num(g["away_score"], 0)},
            "feed": feed,
            "totals": {"home": self._team_game(plays, home, ano), "away": self._team_game(plays, away, ano)},
        }

    @staticmethod
    def _narrate(r: dict, card: dict) -> dict:
        pr, tipo = card["passResult"], card.get("playType")
        yards = card["result"] or 0
        off = card.get("offense") or ""
        if card["tags"] and "TOUCHDOWN" in card["tags"]:
            icon, tone, headline = "🏈", "td", "TOUCHDOWN!"
        elif pr == "S":
            icon, tone, headline = "💪", "sack", "SACK!"
        elif pr == "IN":
            icon, tone, headline = "🛑", "turnover", "INTERCEPTADO!"
        elif "FUMBLE" in card["tags"]:
            icon, tone, headline = "🛑", "turnover", "FUMBLE perdido!"
        elif pr == "C" and yards >= 20:
            icon, tone, headline = "🚀", "big", f"Passe de {yards} jardas!"
        elif pr == "C":
            icon, tone, headline = "✅", "normal", f"Completo, {yards} jd"
        elif pr == "I":
            icon, tone, headline = "❌", "normal", "Passe incompleto"
        elif pr == "R":
            icon, tone, headline = "🏃", "normal", f"QB corre, {yards} jd"
        elif tipo == "run" and yards >= 20:
            icon, tone, headline = "🚀", "big", f"Corrida de {yards} jardas!"
        elif tipo == "run":
            icon, tone, headline = "🏃", "normal", f"Corrida, {yards} jd"
        elif tipo == "field_goal":
            ok = text(r.get("field_goal_result")) == "made"
            icon, tone, headline = ("🎯", "big", "Field goal convertido") if ok else ("❌", "normal", "Field goal perdido")
        elif tipo == "extra_point":
            ok = text(r.get("extra_point_result")) == "good"
            icon, tone, headline = "🎯", "normal", "Ponto extra" + ("" if ok else " perdido")
        elif tipo in ("punt", "kickoff"):
            # a posse no chute é do time que recebe: sem o prefixo do time
            off = ""
            icon, tone, headline = "🦶", "normal", "Punt" if tipo == "punt" else "Kickoff"
        elif NFLData._eh_timeout(r):
            off = ""
            icon, tone, headline = "⏱️", "normal", "Tempo técnico"
        elif tipo == "no_play":
            icon, tone, headline = "⚑", "normal", "Jogada anulada por falta"
        else:
            icon, tone, headline = "🏈", "normal", TIPO_LABELS.get(tipo or "", "Jogada")
        bits = []
        if card.get("down"):
            bits.append(f"{card['down']}ª e {card['yardsToGo']}")
        if card.get("blitz"):
            bits.append(f"blitz de {card['rushers']}")
        if card.get("coverage"):
            bits.append(card["coverage"])
        if card.get("timeToThrow"):
            bits.append(f"{card['timeToThrow']:.1f}s no pocket")
        if card.get("pressured"):
            bits.append("sob pressão")
        return {"icon": icon, "tone": tone, "headline": f"{off}: {headline}" if off else headline,
                "detail": card["description"], "context": " · ".join(bits)}
