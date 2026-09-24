"""
Camada de dados do NFL Big Data Bowl 2023.

Carrega os CSVs oficiais + os caches gerados por etl/build_metrics.py e expoe
consultas prontas para a UI (jogos, jogadas, tracking, scouting, insights).

Observacoes importantes sobre o dataset, que a UI precisa refletir com honestidade:
  * Contem APENAS jogadas de passe (dropbacks) das semanas 1 a 8 de 2021.
    Nao existem jogadas corridas, chutes ou retornos.
  * O placar disponivel e o placar PRE-SNAP de cada dropback. Pontos marcados
    depois do ultimo dropback (field goal decisivo, TD terrestre) nao aparecem,
    entao o "placar final" derivado pode ficar abaixo do oficial.
  * O tracking termina pouco depois do release, logo nao ha dados confiaveis de
    chegada da bola, recepcao ou separacao do recebedor.
"""

from __future__ import annotations

import math
import threading
import zipfile
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

import tracking_npz
from teams import team_info

FPS = 10.0
LEAGUE_ROLES = ("Pass", "Pass Rush", "Pass Block", "Pass Route", "Coverage")

# Snaps minimos para um jogador entrar no ranking/rating de cada funcao.
MIN_SNAPS = {"Pass": 75, "Pass Rush": 50, "Pass Block": 50, "Pass Route": 30, "Coverage": 50}

# Eixos do radar de cada funcao: (rotulo, metrica, menor_e_melhor, unidade)
RADAR_AXES: dict[str, list[tuple[str, str, bool, str]]] = {
    "Pass": [
        ("Precisão", "completionRate", False, "%"),
        ("Produção", "yardsPerDropback", False, "jd"),
        ("Rapidez", "timeToThrow", True, "s"),
        ("Cuidado", "intRate", True, "%"),
        ("Sob pressão", "qbSackRate", True, "%"),
    ],
    "Pass Rush": [
        ("Pressão", "pressureRate", False, "%"),
        ("Finalização", "sackRate", False, "%"),
        ("Chegada", "qbReachRate", False, "%"),
        ("Explosão", "timeToQb", True, "s"),
        ("Velocidade", "maxSpeed", False, "mph"),
    ],
    "Pass Block": [
        ("Proteção", "pressureAllowedRate", True, "%"),
        ("Sacks cedidos", "sackAllowedRate", True, "%"),
        ("Consistência", "beatenRate", True, "%"),
        ("Recuo", "avgDepth", False, "jd"),
        ("Volume", "snaps", False, ""),
    ],
    "Pass Route": [
        ("Velocidade", "maxSpeed", False, "mph"),
        ("Profundidade", "avgDepth", False, "jd"),
        ("Explosão", "avgMaxSpeed", False, "mph"),
        ("Volume", "snaps", False, ""),
        ("Versatilidade", "versatility", False, ""),
    ],
    "Coverage": [
        ("Velocidade", "maxSpeed", False, "mph"),
        ("Alcance", "avgDepth", False, "jd"),
        ("Blitz", "blitzRate", False, "%"),
        ("Volume", "snaps", False, ""),
        ("Versatilidade", "versatility", False, ""),
    ],
}

ROLE_LABELS = {
    "Pass": "Quarterback",
    "Pass Rush": "Pass rusher",
    "Pass Block": "Protetor",
    "Pass Route": "Recebedor",
    "Coverage": "Cobertura",
}

PASS_RESULT_LABELS = {
    "C": "Passe completo",
    "I": "Passe incompleto",
    "S": "Sack",
    "IN": "Interceptação",
    "R": "Scramble",
}


# --------------------------------------------------------------------------- #
# utilidades de conversao segura para JSON
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


def clock_to_seconds(clock) -> int | None:
    s = text(clock)
    if not s or ":" not in s:
        return None
    mm, ss = s.split(":")[:2]
    try:
        return int(mm) * 60 + int(ss)
    except ValueError:
        return None


def yd_s_to_mph(v):
    """Converte jardas/segundo em milhas/hora (1 jd/s = 2.04545 mph)."""
    f = num(v)
    return None if f is None else round(f * 2.04545, 2)


def _registros(df: pd.DataFrame) -> list[dict]:
    """
    Mesmo resultado de df.to_dict("records") (valores em tipos nativos do
    Python), mas convertendo coluna a coluna com .tolist(), que roda em C:
    ~10x mais rapido que o to_dict, que converte celula a celula.
    """
    cols = list(df.columns)
    valores = [df[c].tolist() for c in cols]
    return [dict(zip(cols, linha)) for linha in zip(*valores)]


def _pct_rank(series: pd.Series, lower_is_better: bool) -> pd.Series:
    """Percentil 0-100 dentro do grupo; inverte quando menor e melhor."""
    ranked = series.rank(pct=True, na_option="keep")
    if lower_is_better:
        ranked = 1.0 - ranked
    return ranked * 100.0


# --------------------------------------------------------------------------- #
class NFLData:
    """Tudo carregado em memoria, exceto o tracking (lido por jogo, com cache)."""

    def __init__(self, data_dir: Path, cache_dir: Path, tracking_cache_size: int = 12):
        self.data_dir = Path(data_dir)
        self.cache_dir = Path(cache_dir)
        self.tracking_dir = self.data_dir / "tracking"
        self._tracking_cache: OrderedDict[int, pd.DataFrame] = OrderedDict()
        self._tracking_cache_size = tracking_cache_size
        self._lock = threading.Lock()
        self._load()

    # ---------------------------- carregamento ---------------------------- #
    def _load(self) -> None:
        d = self.data_dir
        self.games = pd.read_csv(d / "games.csv")
        self.players = pd.read_csv(d / "players.csv")
        self.plays = pd.read_csv(d / "plays.csv")
        self.pff = pd.read_csv(d / "pffScoutingData.csv")

        timing_path = self.cache_dir / "play_timing.csv"
        motion_path = self.cache_dir / "player_play.csv"
        if not timing_path.exists() or not motion_path.exists():
            raise SystemExit(
                "Cache de metricas ausente. Rode primeiro:  python etl/build_metrics.py"
            )
        self.timing = pd.read_csv(timing_path)
        self.motion = pd.read_csv(motion_path)
        # (gameId, playId) -> (snapFrame, releaseFrame): evita varrer self.timing por jogada.
        self._timing_idx = {
            (g, p): (s, r)
            for g, p, s, r in zip(
                self.timing["gameId"].tolist(), self.timing["playId"].tolist(),
                self.timing["snapFrame"].astype(float).tolist(), self.timing["releaseFrame"].astype(float).tolist(),
            )
        }

        self._build_play_index()
        self._build_participants()
        self._build_team_game_stats()
        self._build_scouting()
        self._build_league_baselines()

    def _build_play_index(self) -> None:
        """plays.csv + tempos do tracking + flag de pressao, em ordem cronologica."""
        p = self.plays.merge(
            self.timing[
                [
                    "gameId", "playId", "snapFrame", "releaseFrame", "endFrame",
                    "timeToThrow", "playSeconds", "timeToPressure", "qbMaxSpeed", "qbDistance",
                ]
            ],
            on=["gameId", "playId"],
            how="left",
        )

        # Pressao "oficial": qualquer defensor com hit/hurry/sack creditado.
        flags = self.pff[["gameId", "playId", "pff_hit", "pff_hurry", "pff_sack"]].copy()
        flags["anyPressure"] = flags[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).max(axis=1)
        press = flags.groupby(["gameId", "playId"], as_index=False)["anyPressure"].max()
        p = p.merge(press, on=["gameId", "playId"], how="left")
        p["pressured"] = p["anyPressure"].fillna(0).astype(bool)

        # Numero de rushers de cada jogada -> blitz quando passa de 4.
        rushers = (
            self.pff[self.pff["pff_role"] == "Pass Rush"]
            .groupby(["gameId", "playId"], as_index=False)
            .size()
            .rename(columns={"size": "rushers"})
        )
        p = p.merge(rushers, on=["gameId", "playId"], how="left")
        p["blitz"] = p["rushers"].fillna(0) > 4

        p["clockSeconds"] = p["gameClock"].map(clock_to_seconds)
        p["completed"] = p["passResult"] == "C"
        p["isSack"] = p["passResult"] == "S"
        p["isInt"] = p["passResult"] == "IN"
        p["isScramble"] = p["passResult"] == "R"
        # Tentativa de passe = exclui sacks e scrambles (que nao viram passe).
        p["isAttempt"] = p["passResult"].isin(["C", "I", "IN"])
        p["explosive"] = p["playResult"] >= 20
        p["penalty"] = p["foulName1"].notna()
        p["thirdDown"] = p["down"] == 3
        p["thirdConv"] = p["thirdDown"] & (p["playResult"] >= p["yardsToGo"])
        p["playAction"] = p["pff_playAction"].fillna(0).astype(int).astype(bool)

        # playId cresce cronologicamente (verificado: 0 violacoes nos 122 jogos).
        self.play_idx = p.sort_values(["gameId", "playId"]).reset_index(drop=True)
        self.play_idx["seq"] = self.play_idx.groupby("gameId").cumcount() + 1
        self._plays_by_game = {g: df for g, df in self.play_idx.groupby("gameId")}

    def _build_participants(self) -> None:
        """
        pffScoutingData enriquecido: time do jogador (derivado do lado da jogada),
        nome, posicao oficial e metricas de movimento do tracking.
        """
        side_cols = self.play_idx[["gameId", "playId", "possessionTeam", "defensiveTeam", "quarter"]]
        part = self.pff.merge(side_cols, on=["gameId", "playId"], how="left")
        part["side"] = np.where(
            part["pff_role"].isin(["Pass", "Pass Block", "Pass Route"]), "offense", "defense"
        )
        part["team"] = np.where(
            part["side"] == "offense", part["possessionTeam"], part["defensiveTeam"]
        )
        part["pressure"] = part[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).max(axis=1)
        part["pressureAllowed"] = (
            part[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]].fillna(0).max(axis=1)
        )

        part = part.merge(
            self.motion[["gameId", "playId", "nflId", "maxSpeed", "distance", "depth", "lateral", "timeToQb"]],
            on=["gameId", "playId", "nflId"],
            how="left",
        )
        part = part.merge(
            self.players[["nflId", "displayName", "officialPosition", "height", "weight", "collegeName", "birthDate"]],
            on="nflId",
            how="left",
        )
        self.participants = part
        self._part_by_game = {g: df for g, df in part.groupby("gameId")}
        self._linhas_cache: OrderedDict[int, dict] = OrderedDict()

        # Time principal de cada jogador (o que ele mais representou no periodo).
        team_mode = (
            part.groupby(["nflId", "team"]).size().rename("n").reset_index()
            .sort_values(["nflId", "n"], ascending=[True, False])
            .drop_duplicates("nflId")
        )
        self._player_team = dict(zip(team_mode["nflId"], team_mode["team"]))

    def _build_team_game_stats(self) -> None:
        """Estatisticas de ataque e defesa de cada time em cada jogo."""
        p = self.play_idx

        off = p.groupby(["gameId", "possessionTeam"]).apply(
            self._offense_row, include_groups=False
        )
        self._offense = pd.DataFrame(list(off.values), index=off.index)

        de = p.groupby(["gameId", "defensiveTeam"]).apply(
            self._defense_row, include_groups=False
        )
        self._defense = pd.DataFrame(list(de.values), index=de.index)

    @staticmethod
    def _offense_row(g: pd.DataFrame) -> dict:
        attempts = int(g["isAttempt"].sum())
        comp = int(g["completed"].sum())
        third = int(g["thirdDown"].sum())
        return {
            "dropbacks": int(len(g)),
            "attempts": attempts,
            "completions": comp,
            "completionRate": comp / attempts if attempts else None,
            "netYards": num(g["playResult"].sum(), 0),
            "yardsPerDropback": num(g["playResult"].mean(), 2),
            "sacksTaken": int(g["isSack"].sum()),
            "interceptions": int(g["isInt"].sum()),
            "scrambles": int(g["isScramble"].sum()),
            "explosive": int(g["explosive"].sum()),
            "thirdDownAtt": third,
            "thirdDownConv": int(g["thirdConv"].sum()),
            "timeToThrow": num(g["timeToThrow"].mean(), 2),
            "pressureRateAllowed": num(g["pressured"].mean(), 3),
            "playActionRate": num(g["playAction"].mean(), 3),
            "penalties": int(g["penalty"].sum()),
            "penaltyYards": num(g["penaltyYards"].fillna(0).sum(), 0),
        }

    @staticmethod
    def _defense_row(g: pd.DataFrame) -> dict:
        attempts = int(g["isAttempt"].sum())
        comp = int(g["completed"].sum())
        return {
            "dropbacksFaced": int(len(g)),
            "pressures": int(g["pressured"].sum()),
            "pressureRate": num(g["pressured"].mean(), 3),
            "sacks": int(g["isSack"].sum()),
            "interceptions": int(g["isInt"].sum()),
            "blitzRate": num(g["blitz"].mean(), 3),
            "timeToPressure": num(g["timeToPressure"].mean(), 2),
            "completionRateAllowed": comp / attempts if attempts else None,
            "yardsAllowed": num(g["playResult"].sum(), 0),
            "explosiveAllowed": int(g["explosive"].sum()),
        }

    # ------------------------------ scouting ------------------------------ #
    def _build_scouting(self) -> None:
        """Tabela de scouting por jogador+funcao, com percentis e rating 40-99."""
        part = self.participants
        rows = []

        for role in LEAGUE_ROLES:
            sub = part[part["pff_role"] == role]
            if sub.empty:
                continue
            agg = sub.groupby("nflId").agg(
                snaps=("playId", "size"),
                games=("gameId", "nunique"),
                maxSpeed=("maxSpeed", "max"),
                avgMaxSpeed=("maxSpeed", "mean"),
                avgDepth=("depth", "mean"),
                avgLateral=("lateral", "mean"),
                avgDistance=("distance", "mean"),
                versatility=("pff_positionLinedUp", "nunique"),
                pressures=("pressure", "sum"),
                sacks=("pff_sack", "sum"),
                hurries=("pff_hurry", "sum"),
                hits=("pff_hit", "sum"),
                pressuresAllowed=("pressureAllowed", "sum"),
                sacksAllowed=("pff_sackAllowed", "sum"),
                hurriesAllowed=("pff_hurryAllowed", "sum"),
                beaten=("pff_beatenByDefender", "sum"),
                qbReaches=("timeToQb", "count"),
                timeToQb=("timeToQb", "mean"),
            )
            agg["role"] = role
            agg["pressureRate"] = agg["pressures"] / agg["snaps"]
            agg["sackRate"] = agg["sacks"] / agg["snaps"]
            agg["qbReachRate"] = agg["qbReaches"] / agg["snaps"]
            agg["pressureAllowedRate"] = agg["pressuresAllowed"] / agg["snaps"]
            agg["sackAllowedRate"] = agg["sacksAllowed"] / agg["snaps"]
            agg["beatenRate"] = agg["beaten"] / agg["snaps"]
            rows.append(agg.reset_index())

        scout = pd.concat(rows, ignore_index=True)
        scout = self._safe_merge(scout, self._qb_production(), ["nflId", "role"])
        scout = self._safe_merge(scout, self._blitz_rate(), ["nflId"])

        # Percentis por funcao, apenas entre quem bateu o minimo de snaps.
        scout["rated"] = False
        scout["rating"] = np.nan
        for role, axes in RADAR_AXES.items():
            mask = (scout["role"] == role) & (scout["snaps"] >= MIN_SNAPS[role])
            if not mask.any():
                continue
            pcts = []
            for label, metric, lower_better, _unit in axes:
                col = f"pct_{metric}"
                if col not in scout:
                    scout[col] = np.nan
                vals = _pct_rank(scout.loc[mask, metric], lower_better)
                scout.loc[mask, col] = vals
                pcts.append(vals)
            mean_pct = pd.concat(pcts, axis=1).mean(axis=1)
            scout.loc[mask, "rating"] = (40 + mean_pct * 0.59).round(0)
            scout.loc[mask, "rated"] = True

        scout = scout.merge(
            self.players[["nflId", "displayName", "officialPosition", "height", "weight", "collegeName", "birthDate"]],
            on="nflId",
            how="left",
        )
        scout["team"] = scout["nflId"].map(self._player_team)
        self.scouting = scout

        # Funcao principal de cada jogador = aquela com mais snaps.
        primary = scout.sort_values(["nflId", "snaps"], ascending=[True, False]).drop_duplicates("nflId")
        self.primary = primary.set_index("nflId")
        self._scout_by_player = {i: df for i, df in scout.groupby("nflId")}

    @staticmethod
    def _safe_merge(left: pd.DataFrame, right: pd.DataFrame, on: list[str]) -> pd.DataFrame:
        """
        Merge que falha alto em colisao de coluna, em vez de criar _x/_y silenciosos
        (foi assim que 'sackRate' do QB e do pass rusher se atropelaram).
        """
        clash = (set(left.columns) & set(right.columns)) - set(on)
        if clash:
            raise ValueError(f"colisao de colunas no merge: {sorted(clash)}")
        return left.merge(right, on=on, how="left")

    def _qb_production(self) -> pd.DataFrame:
        """Producao de passe por QB, a partir das jogadas em que ele foi o passador."""
        qb = self.participants[self.participants["pff_role"] == "Pass"][["gameId", "playId", "nflId"]]
        j = qb.merge(
            self.play_idx[
                ["gameId", "playId", "isAttempt", "completed", "isSack", "isInt", "isScramble",
                 "playResult", "timeToThrow", "pressured", "explosive", "playAction"]
            ],
            on=["gameId", "playId"],
            how="left",
        )
        agg = j.groupby("nflId").agg(
            dropbacks=("playId", "size"),
            attempts=("isAttempt", "sum"),
            completions=("completed", "sum"),
            qbSacks=("isSack", "sum"),
            ints=("isInt", "sum"),
            scrambles=("isScramble", "sum"),
            passYards=("playResult", "sum"),
            timeToThrow=("timeToThrow", "mean"),
            pressureFacedRate=("pressured", "mean"),
            explosives=("explosive", "sum"),
            playActionRate=("playAction", "mean"),
        )
        agg["completionRate"] = agg["completions"] / agg["attempts"].replace(0, np.nan)
        agg["yardsPerDropback"] = agg["passYards"] / agg["dropbacks"]
        agg["intRate"] = agg["ints"] / agg["attempts"].replace(0, np.nan)
        # Nome proprio: "sackRate" do pass rusher e outra coisa (sacks/rush).
        agg["qbSackRate"] = agg["qbSacks"] / agg["dropbacks"]
        agg["role"] = "Pass"
        return agg.reset_index()

    def _blitz_rate(self) -> pd.DataFrame:
        """Para defensores: fatia dos snaps em que pressionou em vez de cobrir."""
        d = self.participants[self.participants["pff_role"].isin(["Pass Rush", "Coverage"])]
        counts = d.pivot_table(index="nflId", columns="pff_role", values="playId", aggfunc="size").fillna(0)
        rush = counts.get("Pass Rush", pd.Series(0, index=counts.index))
        cov = counts.get("Coverage", pd.Series(0, index=counts.index))
        total = (rush + cov).replace(0, np.nan)
        return pd.DataFrame({"nflId": counts.index, "blitzRate": (rush / total).values})

    def _build_league_baselines(self) -> None:
        p = self.play_idx
        att = int(p["isAttempt"].sum())
        self.league = {
            "plays": int(len(p)),
            "games": int(p["gameId"].nunique()),
            "completionRate": num(p["completed"].sum() / att, 3),
            "timeToThrow": num(p["timeToThrow"].mean(), 2),
            "timeToPressure": num(p["timeToPressure"].mean(), 2),
            "pressureRate": num(p["pressured"].mean(), 3),
            "sackRate": num(p["isSack"].mean(), 3),
            "intRate": num(p["isInt"].sum() / att, 3),
            "yardsPerDropback": num(p["playResult"].mean(), 2),
            "blitzRate": num(p["blitz"].mean(), 3),
            "explosiveRate": num(p["explosive"].mean(), 3),
            "playActionRate": num(p["playAction"].mean(), 3),
            "thirdDownRate": num(
                p.loc[p["thirdDown"], "thirdConv"].mean(), 3
            ),
        }
        # Aproveitamento do ataque contra cada esquema de cobertura (base da liga).
        cov = p[p["isAttempt"]].groupby("pff_passCoverage").agg(
            plays=("playId", "size"),
            completionRate=("completed", "mean"),
            yardsPerDropback=("playResult", "mean"),
        )
        self.league_coverage = cov[cov["plays"] >= 50]

    # ------------------------------ consultas ----------------------------- #
    def meta(self) -> dict:
        abbrs = sorted(set(self.games["homeTeamAbbr"]) | set(self.games["visitorTeamAbbr"]))
        weeks = []
        for week, g in self.games.groupby("week"):
            weeks.append(
                {
                    "week": int(week),
                    "games": int(len(g)),
                    "dates": sorted(set(g["gameDate"])),
                }
            )
        return {
            "season": int(self.games["season"].iloc[0]),
            "weeks": weeks,
            "teams": {a: team_info(a) for a in abbrs},
            "counts": {
                "games": int(len(self.games)),
                "plays": int(len(self.play_idx)),
                "players": int(self.players["nflId"].nunique()),
                "trackingRows": int(len(self.motion)),
            },
            "league": self.league,
            "roleLabels": ROLE_LABELS,
            "dataset": {
                "name": "NFL Big Data Bowl 2023",
                "scope": "Semanas 1 a 8 da temporada 2021 — somente jogadas de passe (dropbacks)",
                "caveats": [
                    "O dataset cobre apenas dropbacks: não há jogadas corridas, chutes ou retornos.",
                    "O placar exibido é o placar pré-snap do último dropback registrado, "
                    "então pode ficar abaixo do resultado oficial.",
                    "O tracking termina pouco após o lançamento, sem dados de recepção.",
                ],
            },
        }

    # --------------------------------- jogos ------------------------------ #
    def games_list(self, week: int | None = None, date: str | None = None) -> list[dict]:
        g = self.games
        if week is not None:
            g = g[g["week"] == week]
        if date:
            g = g[g["gameDate"] == date]
        return [self._game_card(row) for _, row in g.iterrows()]

    def _game_card(self, row: pd.Series) -> dict:
        gid = int(row["gameId"])
        plays = self._plays_by_game.get(gid)
        home, away = row["homeTeamAbbr"], row["visitorTeamAbbr"]
        score = self._derived_score(plays)
        return {
            "gameId": gid,
            "season": int(row["season"]),
            "week": int(row["week"]),
            "date": row["gameDate"],
            "kickoff": row["gameTimeEastern"],
            "home": {**team_info(home), "score": score["home"]},
            "away": {**team_info(away), "score": score["away"]},
            "dropbacks": int(len(plays)) if plays is not None else 0,
            "sacks": int(plays["isSack"].sum()) if plays is not None else 0,
            "overtime": bool(plays["quarter"].max() > 4) if plays is not None else False,
            "scoreIsPartial": True,
            "status": "FINAL",
        }

    @staticmethod
    def _derived_score(plays: pd.DataFrame | None) -> dict:
        """
        Placar a partir dos scores pre-snap. Usa o maximo observado, que equivale
        ao placar no momento do ultimo dropback do jogo.
        """
        if plays is None or plays.empty:
            return {"home": None, "away": None}
        return {
            "home": num(plays["preSnapHomeScore"].max(), 0),
            "away": num(plays["preSnapVisitorScore"].max(), 0),
        }

    def game(self, game_id: int) -> dict | None:
        row = self.games[self.games["gameId"] == game_id]
        if row.empty:
            return None
        row = row.iloc[0]
        card = self._game_card(row)
        home, away = card["home"]["abbr"], card["away"]["abbr"]
        card["teams"] = {
            "home": self._team_game(game_id, home),
            "away": self._team_game(game_id, away),
        }
        card["tendencies"] = {
            "home": self._tendencies(game_id, home),
            "away": self._tendencies(game_id, away),
        }
        card["insights"] = self.insights(game_id)
        card["notes"] = self.notes(game_id)
        card["watch"] = self.watch_list(game_id)
        return card

    def _team_game(self, game_id: int, abbr: str) -> dict:
        off = self._offense.loc[(game_id, abbr)].to_dict() if (game_id, abbr) in self._offense.index else {}
        de = self._defense.loc[(game_id, abbr)].to_dict() if (game_id, abbr) in self._defense.index else {}

        def clean(d: dict) -> dict:
            out = {}
            for k, v in d.items():
                if isinstance(v, str):
                    out[k] = text(v)
                elif isinstance(v, (bool, np.bool_)):
                    out[k] = bool(v)
                else:
                    f = num(v, 4)
                    out[k] = int(f) if f is not None and float(f).is_integer() else f
            return out

        return {**team_info(abbr), "offense": clean(off), "defense": clean(de)}

    def _tendencies(self, game_id: int, abbr: str) -> dict:
        """Tendencias do time: formacoes/dropbacks no ataque, coberturas na defesa."""
        plays = self._plays_by_game.get(game_id)
        if plays is None:
            return {}
        off = plays[plays["possessionTeam"] == abbr]
        de = plays[plays["defensiveTeam"] == abbr]

        def dist(frame: pd.DataFrame, col: str) -> list[dict]:
            if frame.empty:
                return []
            grp = frame.groupby(col).agg(
                plays=("playId", "size"),
                yards=("playResult", "mean"),
                completionRate=("completed", "mean"),
            )
            grp = grp.sort_values("plays", ascending=False)
            total = int(grp["plays"].sum())
            return [
                {
                    "label": text(idx),
                    "plays": int(r["plays"]),
                    "share": num(r["plays"] / total, 3),
                    "yardsPerPlay": num(r["yards"], 2),
                    "completionRate": num(r["completionRate"], 3),
                }
                for idx, r in grp.iterrows()
                if text(idx)
            ]

        return {
            "formations": dist(off, "offenseFormation"),
            "dropbacks": dist(off, "dropBackType"),
            "personnel": dist(off, "personnelO"),
            "coverages": dist(de, "pff_passCoverage"),
            "coverageTypes": dist(de, "pff_passCoverageType"),
        }

    # -------------------------------- jogadas ----------------------------- #
    def game_plays(self, game_id: int, quarter: int | None = None, team: str | None = None) -> list[dict]:
        plays = self._plays_by_game.get(game_id)
        if plays is None:
            return []
        if quarter:
            plays = plays[plays["quarter"] == quarter]
        if team:
            plays = plays[plays["possessionTeam"] == team]
        return [self._play_card(r) for _, r in plays.iterrows()]

    def _play_card(self, r: pd.Series) -> dict:
        tags = []
        pr = text(r["passResult"])
        desc = text(r["playDescription"]) or ""
        if "TOUCHDOWN" in desc.upper():
            tags.append("TOUCHDOWN")
        if pr == "S":
            tags.append("SACK")
        if pr == "IN":
            tags.append("INTERCEPTAÇÃO")
        if r["explosive"]:
            tags.append("JOGADA EXPLOSIVA")
        if r["penalty"]:
            tags.append("FALTA")
        if bool(r["blitz"]):
            tags.append("BLITZ")
        if bool(r["playAction"]):
            tags.append("PLAY ACTION")

        return {
            "gameId": int(r["gameId"]),
            "playId": int(r["playId"]),
            "seq": int(r["seq"]),
            "quarter": int(r["quarter"]),
            "clock": text(r["gameClock"]),
            "clockSeconds": num(r["clockSeconds"], 0),
            "down": num(r["down"], 0),
            "yardsToGo": num(r["yardsToGo"], 0),
            "offense": text(r["possessionTeam"]),
            "defense": text(r["defensiveTeam"]),
            "yardline": f"{text(r['yardlineSide']) or ''} {num(r['yardlineNumber'], 0) or ''}".strip(),
            "absoluteYardline": num(r["absoluteYardlineNumber"], 0),
            "description": desc,
            "result": num(r["playResult"], 0),
            "passResult": pr,
            "passResultLabel": PASS_RESULT_LABELS.get(pr or "", "—"),
            "formation": text(r["offenseFormation"]),
            "personnelO": text(r["personnelO"]),
            "personnelD": text(r["personnelD"]),
            "coverage": text(r["pff_passCoverage"]),
            "coverageType": text(r["pff_passCoverageType"]),
            "dropback": text(r["dropBackType"]),
            "playAction": bool(r["playAction"]),
            "defendersInBox": num(r["defendersInBox"], 0),
            "rushers": num(r["rushers"], 0),
            "blitz": bool(r["blitz"]),
            "pressured": bool(r["pressured"]),
            "timeToThrow": num(r["timeToThrow"], 2),
            "timeToPressure": num(r["timeToPressure"], 2),
            "penaltyYards": num(r["penaltyYards"], 0),
            "foul": text(r["foulName1"]),
            "score": {"home": num(r["preSnapHomeScore"], 0), "away": num(r["preSnapVisitorScore"], 0)},
            "hasTracking": bool(pd.notna(r["snapFrame"])),
            "tags": tags,
        }

    def play(self, game_id: int, play_id: int) -> dict | None:
        jogo = self._linhas_do_jogo(game_id)
        if jogo is None:
            return None
        r = jogo["jogadas"].get(play_id)
        if r is None:
            return None
        card = self._play_card(r)
        card["players"] = self.play_participants(game_id, play_id)
        return card

    # Colunas que play_participants le.
    _COLS_PARTICIPANTES = [
        "playId", "nflId", "displayName", "officialPosition", "pff_positionLinedUp", "pff_role",
        "side", "team", "maxSpeed", "distance", "depth", "timeToQb", "pff_sack", "pff_hurry",
        "pff_hit", "pff_sackAllowed", "pff_hurryAllowed", "pff_hitAllowed",
        "pff_beatenByDefender", "pff_blockType", "pff_nflIdBlockedPlayer",
    ]

    def _linhas_do_jogo(self, game_id: int) -> dict | None:
        """
        Linhas de jogadas e participantes de um jogo ja como dicionarios,
        agrupadas por playId, montadas uma vez por jogo (LRU, como o tracking).
        Abrir uma jogada vira consulta direta, sem filtrar tabelas largas nem
        chamar to_dict a cada vez. A ordem das linhas e a original.
        """
        with self._lock:
            if game_id in self._linhas_cache:
                self._linhas_cache.move_to_end(game_id)
                return self._linhas_cache[game_id]
        plays = self._plays_by_game.get(game_id)
        if plays is None:
            return None
        jogadas: dict[int, dict] = {}
        for r in _registros(plays):
            jogadas.setdefault(int(r["playId"]), r)  # 1a ocorrencia, como plays[...].iloc[0]
        participantes: dict[int, list[dict]] = {}
        part = self._part_by_game.get(game_id)
        if part is not None:
            for r in _registros(part[self._COLS_PARTICIPANTES]):
                participantes.setdefault(int(r["playId"]), []).append(r)
        jogo = {"jogadas": jogadas, "participantes": participantes}
        with self._lock:
            self._linhas_cache[game_id] = jogo
            while len(self._linhas_cache) > self._tracking_cache_size:
                self._linhas_cache.popitem(last=False)
        return jogo

    def play_participants(self, game_id: int, play_id: int) -> list[dict]:
        jogo = self._linhas_do_jogo(game_id)
        if jogo is None:
            return []
        out = []
        for r in jogo["participantes"].get(play_id, []):
            nfl_id = num(r["nflId"], 0)
            out.append(
                {
                    "nflId": nfl_id,
                    "name": text(r["displayName"]),
                    "position": text(r["officialPosition"]),
                    "linedUp": text(r["pff_positionLinedUp"]),
                    "role": text(r["pff_role"]),
                    "roleLabel": ROLE_LABELS.get(text(r["pff_role"]) or "", ""),
                    "side": text(r["side"]),
                    "team": text(r["team"]),
                    "maxSpeed": yd_s_to_mph(r["maxSpeed"]),
                    "distance": num(r["distance"], 2),
                    "depth": num(r["depth"], 2),
                    "timeToQb": num(r["timeToQb"], 2),
                    "rating": num(self._rating_of(nfl_id), 0),
                    "pff": {
                        "sack": num(r["pff_sack"], 0),
                        "hurry": num(r["pff_hurry"], 0),
                        "hit": num(r["pff_hit"], 0),
                        "sackAllowed": num(r["pff_sackAllowed"], 0),
                        "hurryAllowed": num(r["pff_hurryAllowed"], 0),
                        "hitAllowed": num(r["pff_hitAllowed"], 0),
                        "beaten": num(r["pff_beatenByDefender"], 0),
                        "blockType": text(r["pff_blockType"]),
                        "blockedPlayer": num(r["pff_nflIdBlockedPlayer"], 0),
                    },
                }
            )
        return out

    def _rating_of(self, nfl_id) -> float | None:
        if nfl_id is None or nfl_id not in self.primary.index:
            return None
        return self.primary.at[nfl_id, "rating"]

    # ------------------------------- tracking ----------------------------- #
    def _tracking_for_game(self, game_id: int) -> tuple[pd.DataFrame, dict] | None:
        """
        (quadros do jogo ordenados por playId, {playId: (inicio, fim)}), com LRU.
        Le o binario cache/tracking/<id>.npz; se faltar ou estiver ilegivel, cai
        no CSV original. A ordenacao e estavel: dentro de cada jogada as linhas
        mantem a ordem do arquivo, como no filtro df[df.playId == x] de antes.
        """
        with self._lock:
            if game_id in self._tracking_cache:
                self._tracking_cache.move_to_end(game_id)
                return self._tracking_cache[game_id]
        df = self._ler_tracking(game_id)
        if df is None:
            return None
        df = df.sort_values("playId", kind="stable").reset_index(drop=True)
        pids = df["playId"].to_numpy()
        inicios = np.flatnonzero(np.r_[True, pids[1:] != pids[:-1]]) if len(pids) else np.array([], int)
        fins = np.r_[inicios[1:], len(pids)]
        entrada = (df, {int(pids[a]): (int(a), int(b)) for a, b in zip(inicios, fins)})
        with self._lock:
            self._tracking_cache[game_id] = entrada
            while len(self._tracking_cache) > self._tracking_cache_size:
                self._tracking_cache.popitem(last=False)
        return entrada

    def _ler_tracking(self, game_id: int) -> pd.DataFrame | None:
        npz = self.cache_dir / "tracking" / f"{game_id}.npz"
        try:
            return tracking_npz.carregar(npz)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile) as e:
            print(f"[aviso] {npz.name} ilegivel ({e!r}); lendo o CSV original "
                  f"(o arquivo sera regenerado na proxima subida)", flush=True)
            # Apagar faz o ensure_cache do proximo startup refazer este jogo;
            # senao o arquivo ruim ficaria para sempre (o CSV de origem nao mudou).
            try:
                npz.unlink()
            except OSError:
                pass
        csv = self.tracking_dir / f"tracking_{game_id}.csv"
        if not csv.exists():
            return None
        return pd.read_csv(csv, usecols=tracking_npz.COLUNAS)

    def play_tracking(self, game_id: int, play_id: int) -> dict | None:
        entrada = self._tracking_for_game(game_id)
        if entrada is None:
            return None
        df, faixas = entrada
        if play_id not in faixas:
            return None
        a, b = faixas[play_id]
        sub = df.iloc[a:b]

        info = self.play(game_id, play_id) or {}
        roster = {p["nflId"]: p for p in info.get("players", [])}

        frame_ids = sub["frameId"].to_numpy()
        frames = np.unique(frame_ids)                      # ordenados, como sorted(unique())
        frame_pos = {f: i for i, f in enumerate(frames.tolist())}
        n = len(frames)
        idx_quadro = np.searchsorted(frames, frame_ids).tolist()

        nfl = sub["nflId"].to_numpy(dtype=float)
        eh_jogador = ~np.isnan(nfl)
        x, y = sub["x"].to_numpy().tolist(), sub["y"].to_numpy().tolist()
        vel, ori, dire = sub["s"].to_numpy().tolist(), sub["o"].to_numpy().tolist(), sub["dir"].to_numpy().tolist()
        camisa = sub["jerseyNumber"].to_numpy()
        time_col = sub["team"].to_numpy(dtype=object)

        # Jogadores em ordem de nflId e, dentro de cada um, por quadro (o groupby +
        # sort_values de antes). Arredondamento com round() do Python, igual ao original.
        linhas = np.flatnonzero(eh_jogador)
        linhas = linhas[np.lexsort((frame_ids[linhas], nfl[linhas]))]
        ids = nfl[linhas]
        cortes = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]]) if len(ids) else np.array([], int)
        players = []
        for c0, c1 in zip(cortes.tolist(), np.r_[cortes[1:], len(ids)].tolist()):
            grupo = linhas[c0:c1].tolist()
            primeira = grupo[0]
            nfl_id = int(nfl[primeira])
            meta = roster.get(nfl_id, {})
            track = [None] * n
            for k in grupo:
                track[idx_quadro[k]] = [
                    round(x[k], 2), round(y[k], 2), round(vel[k], 2), round(ori[k], 1), round(dire[k], 1),
                ]
            players.append(
                {
                    "nflId": nfl_id,
                    "name": meta.get("name"),
                    "jersey": num(camisa[primeira], 0),
                    "team": text(time_col[primeira]),
                    "side": meta.get("side"),
                    "role": meta.get("role"),
                    "linedUp": meta.get("linedUp"),
                    "position": meta.get("position"),
                    "rating": meta.get("rating"),
                    "t": track,
                }
            )

        bola = np.flatnonzero(~eh_jogador)
        bola = bola[np.argsort(frame_ids[bola], kind="stable")].tolist()
        evento = sub["event"].to_numpy(dtype=object)
        ball = [None] * n
        events = []
        for k in bola:
            ball[idx_quadro[k]] = [round(x[k], 2), round(y[k], 2)]
            nome = text(evento[k])
            if nome:
                events.append({"frame": idx_quadro[k], "name": nome})

        snap = release = None
        tempos = self._timing_idx.get((game_id, play_id))
        if tempos is not None:
            snap = frame_pos.get(tempos[0])      # NaN -> None, como antes
            release = frame_pos.get(tempos[1])

        return {
            "gameId": game_id,
            "playId": play_id,
            "fps": FPS,
            "frameCount": n,
            "playDirection": text(sub["playDirection"].iloc[0]),
            "snapIndex": snap,
            "releaseIndex": release,
            "lineOfScrimmage": info.get("absoluteYardline"),
            "yardsToGo": info.get("yardsToGo"),
            "players": players,
            "ball": ball,
            "events": events,
            "play": {k: v for k, v in info.items() if k != "players"},
        }

    def snap_formation(self, game_id: int, play_id: int) -> dict | None:
        """Posicoes reais dos 22 jogadores no instante do snap (prancheta tatica)."""
        tr = self.play_tracking(game_id, play_id)
        if not tr:
            return None
        idx = tr["snapIndex"] if tr["snapIndex"] is not None else 0
        players = []
        for p in tr["players"]:
            pos = p["t"][idx] if idx < len(p["t"]) else None
            if not pos:
                continue
            players.append(
                {k: p[k] for k in ("nflId", "name", "jersey", "team", "side", "role", "linedUp", "position", "rating")}
                | {"x": pos[0], "y": pos[1], "o": pos[3]}
            )
        ball = tr["ball"][idx] if idx < len(tr["ball"]) else None
        return {
            "gameId": game_id,
            "playId": play_id,
            "playDirection": tr["playDirection"],
            "lineOfScrimmage": tr["lineOfScrimmage"],
            "yardsToGo": tr["yardsToGo"],
            "ball": ball,
            "players": players,
            "play": tr["play"],
        }

    # ------------------------------- jogadores ---------------------------- #
    def players_list(
        self, q: str | None = None, position: str | None = None, role: str | None = None,
        team: str | None = None, rated_only: bool = True, limit: int = 40,
    ) -> list[dict]:
        p = self.primary.reset_index()
        if rated_only:
            p = p[p["rated"]]
        if q:
            p = p[p["displayName"].str.contains(q, case=False, na=False)]
        if position:
            wanted = {s.strip().upper() for s in position.split(",")}
            p = p[p["officialPosition"].str.upper().isin(wanted)]
        if role:
            p = p[p["role"] == role]
        if team:
            p = p[p["team"] == team.upper()]
        p = p.sort_values("rating", ascending=False, na_position="last").head(limit)
        return [self._player_card(r) for r in p.to_dict("records")]

    def _player_card(self, r: pd.Series) -> dict:
        return {
            "nflId": int(r["nflId"]),
            "name": text(r["displayName"]),
            "position": text(r["officialPosition"]),
            "team": text(r["team"]),
            "teamInfo": team_info(text(r["team"]) or ""),
            "role": text(r["role"]),
            "roleLabel": ROLE_LABELS.get(text(r["role"]) or "", ""),
            "rating": num(r["rating"], 0),
            "rated": bool(r["rated"]),
            "snaps": num(r["snaps"], 0),
            "games": num(r["games"], 0),
            "topSpeed": yd_s_to_mph(r["maxSpeed"]),
        }

    def player(self, nfl_id: int) -> dict | None:
        base = self.players[self.players["nflId"] == nfl_id]
        if base.empty:
            return None
        b = base.iloc[0]
        if nfl_id not in self.primary.index:
            return None
        prim = self.primary.loc[nfl_id]

        roles = []
        for _, r in self._scout_by_player.get(nfl_id, pd.DataFrame()).iterrows():
            roles.append(
                {
                    "role": text(r["role"]),
                    "roleLabel": ROLE_LABELS.get(text(r["role"]) or "", ""),
                    "snaps": num(r["snaps"], 0),
                    "rating": num(r["rating"], 0),
                    "rated": bool(r["rated"]),
                    "radar": self._radar(r),
                    "stats": self._role_stats(r),
                }
            )
        roles.sort(key=lambda x: -(x["snaps"] or 0))

        return {
            **self._player_card(prim.to_frame().T.assign(nflId=nfl_id).iloc[0]),
            "height": text(b["height"]),
            "weight": num(b["weight"], 0),
            "college": text(b["collegeName"]),
            "birthDate": text(b["birthDate"]),
            "age": self._age(text(b["birthDate"])),
            "roles": roles,
            "positionsLinedUp": self._positions_lined_up(nfl_id),
            "gameLog": self._game_log(nfl_id),
        }

    @staticmethod
    def _age(birth: str | None) -> int | None:
        if not birth:
            return None
        try:
            born = pd.Timestamp(birth)
        except Exception:
            return None
        # Idade na temporada coberta pelo dataset (2021).
        ref = pd.Timestamp("2021-09-09")
        return int((ref - born).days // 365.25)

    def _radar(self, r: pd.Series) -> list[dict]:
        role = text(r["role"])
        axes = RADAR_AXES.get(role or "", [])
        out = []
        for label, metric, lower_better, unit in axes:
            raw = num(r.get(metric))
            pct = r.get(f"pct_{metric}")
            if raw is None:
                display = None
            elif unit == "%":
                display = round(raw * 100, 1)   # escala antes de arredondar
            elif unit == "mph":
                display = yd_s_to_mph(raw)
            else:
                display = round(raw, 2)
            out.append(
                {
                    "label": label,
                    "metric": metric,
                    "value": display,
                    "unit": unit,
                    "percentile": num(pct, 0),
                    "lowerIsBetter": lower_better,
                }
            )
        return out

    @staticmethod
    def _role_stats(r: pd.Series) -> list[dict]:
        role = text(r["role"])
        pick = {
            "Pass": [
                ("Dropbacks", "dropbacks", 0, ""), ("Completos", "completions", 0, ""),
                ("Aproveitamento", "completionRate", 1, "%"), ("Jardas", "passYards", 0, "jd"),
                ("Jd/dropback", "yardsPerDropback", 2, "jd"), ("Sacks sofridos", "qbSacks", 0, ""),
                ("Interceptações", "ints", 0, ""), ("Tempo p/ lançar", "timeToThrow", 2, "s"),
                ("Pressionado", "pressureFacedRate", 1, "%"),
            ],
            "Pass Rush": [
                ("Rushes", "snaps", 0, ""), ("Pressões", "pressures", 0, ""),
                ("Taxa de pressão", "pressureRate", 1, "%"), ("Sacks", "sacks", 0, ""),
                ("Hurries", "hurries", 0, ""), ("Hits", "hits", 0, ""),
                ("Chegou ao QB", "qbReachRate", 1, "%"), ("Tempo até o QB", "timeToQb", 2, "s"),
            ],
            "Pass Block": [
                ("Snaps de proteção", "snaps", 0, ""), ("Pressões cedidas", "pressuresAllowed", 0, ""),
                ("Taxa cedida", "pressureAllowedRate", 1, "%"), ("Sacks cedidos", "sacksAllowed", 0, ""),
                ("Superado", "beaten", 0, ""), ("Recuo médio", "avgDepth", 2, "jd"),
            ],
            "Pass Route": [
                ("Rotas", "snaps", 0, ""), ("Profundidade média", "avgDepth", 2, "jd"),
                ("Deslocamento lateral", "avgLateral", 2, "jd"), ("Distância/rota", "avgDistance", 2, "jd"),
                ("Posições usadas", "versatility", 0, ""),
            ],
            "Coverage": [
                ("Snaps de cobertura", "snaps", 0, ""), ("Alcance médio", "avgDepth", 2, "jd"),
                ("Distância/snap", "avgDistance", 2, "jd"), ("Taxa de blitz", "blitzRate", 1, "%"),
                ("Posições usadas", "versatility", 0, ""),
            ],
        }.get(role or "", [])

        out = []
        for label, metric, digits, unit in pick:
            raw = num(r.get(metric))
            if raw is None:
                continue
            # Escala primeiro, arredonda depois (senao 0.566 -> 0.6 -> 60%).
            if unit == "%":
                raw *= 100
            elif unit == "mph":
                raw = raw * 2.04545
            v = round(raw, digits)
            out.append({"label": label, "value": int(v) if digits == 0 else v, "unit": unit})
        return out

    def _positions_lined_up(self, nfl_id: int) -> list[dict]:
        sub = self.participants[self.participants["nflId"] == nfl_id]
        if sub.empty:
            return []
        counts = sub["pff_positionLinedUp"].value_counts()
        total = int(counts.sum())
        return [
            {"position": text(k), "snaps": int(v), "share": num(v / total, 3)}
            for k, v in counts.items()
        ][:8]

    def _game_log(self, nfl_id: int) -> list[dict]:
        sub = self.participants[self.participants["nflId"] == nfl_id]
        if sub.empty:
            return []
        rows = []
        for gid, g in sub.groupby("gameId"):
            info = self.games[self.games["gameId"] == gid]
            week = int(info["week"].iloc[0]) if not info.empty else None
            team = text(g["team"].iloc[0])
            opp = None
            if not info.empty:
                h, a = info["homeTeamAbbr"].iloc[0], info["visitorTeamAbbr"].iloc[0]
                opp = a if team == h else h
            rows.append(
                {
                    "gameId": int(gid),
                    "week": week,
                    "team": team,
                    "opponent": opp,
                    "snaps": int(len(g)),
                    "topSpeed": yd_s_to_mph(g["maxSpeed"].max()),
                    "pressures": num(g["pressure"].sum(), 0),
                    "sacks": num(g["pff_sack"].sum(), 0),
                    "pressuresAllowed": num(g["pressureAllowed"].sum(), 0),
                }
            )
        rows.sort(key=lambda r: r["week"] or 0)
        return rows

    def compare(self, a: int, b: int) -> dict | None:
        pa, pb = self.player(a), self.player(b)
        if not pa or not pb:
            return None
        role_a = pa["roles"][0] if pa["roles"] else None
        role_b = next((r for r in pb["roles"] if role_a and r["role"] == role_a["role"]), None)
        if role_b is None:
            role_b = pb["roles"][0] if pb["roles"] else None

        rows = []
        if role_a and role_b and role_a["role"] == role_b["role"]:
            by_label = {s["label"]: s for s in role_b["stats"]}
            for s in role_a["stats"]:
                other = by_label.get(s["label"])
                if other is None:
                    continue
                rows.append(
                    {
                        "label": s["label"],
                        "unit": s["unit"],
                        "left": s["value"],
                        "right": other["value"],
                    }
                )
        return {
            "sameRole": bool(role_a and role_b and role_a["role"] == role_b["role"]),
            "role": role_a["role"] if role_a else None,
            "roleLabel": role_a["roleLabel"] if role_a else None,
            "left": pa,
            "right": pb,
            "rows": rows,
        }

    def leaders(self, metric: str, role: str | None = None, limit: int = 10) -> list[dict]:
        s = self.scouting[self.scouting["rated"]]
        if role:
            s = s[s["role"] == role]
        if metric not in s.columns:
            return []
        lower_better = any(
            m == metric and lb for axes in RADAR_AXES.values() for _l, m, lb, _u in axes
        )
        s = s.dropna(subset=[metric]).sort_values(metric, ascending=lower_better).head(limit)
        out = []
        for _, r in s.iterrows():
            card = self._player_card(r)
            v = num(r[metric], 3)
            card["metric"] = {"key": metric, "value": v}
            out.append(card)
        return out

    def watch_list(self, game_id: int, per_role: int = 1) -> list[dict]:
        """Destaques do jogo: melhor avaliado de cada funcao entre os que atuaram."""
        part = self._part_by_game.get(game_id)
        if part is None:
            return []
        snaps = part.groupby(["nflId", "pff_role"]).size().rename("gameSnaps").reset_index()
        merged = snaps.merge(
            self.scouting[["nflId", "role", "rating", "rated", "snaps"]],
            left_on=["nflId", "pff_role"], right_on=["nflId", "role"], how="left",
        )
        merged = merged[merged["rated"].fillna(False) & (merged["gameSnaps"] >= 8)]
        out = []
        for role in LEAGUE_ROLES:
            top = merged[merged["role"] == role].nlargest(per_role, "rating")
            for _, r in top.iterrows():
                nfl_id = int(r["nflId"])
                if nfl_id not in self.primary.index:
                    continue
                card = self._player_card(self.primary.loc[nfl_id].to_frame().T.assign(nflId=nfl_id).iloc[0])
                card["role"] = role
                card["roleLabel"] = ROLE_LABELS[role]
                card["rating"] = num(r["rating"], 0)
                card["gameSnaps"] = int(r["gameSnaps"])
                out.append(card)
        return out

    # -------------------------------- insights ---------------------------- #
    def insights(self, game_id: int, limit: int = 6) -> list[dict]:
        """
        Sugestoes taticas geradas a partir do jogo, ordenadas pelo tamanho do
        desvio em relacao a media da liga (o que realmente foge do padrao).
        """
        plays = self._plays_by_game.get(game_id)
        if plays is None or plays.empty:
            return []
        row = self.games[self.games["gameId"] == game_id].iloc[0]
        teams = [row["homeTeamAbbr"], row["visitorTeamAbbr"]]
        lg = self.league
        cards: list[dict] = []

        for abbr in teams:
            opp = teams[1] if abbr == teams[0] else teams[0]
            off = plays[plays["possessionTeam"] == abbr]
            de = plays[plays["defensiveTeam"] == abbr]
            if off.empty or de.empty:
                continue

            # 1) Cobertura predileta da defesa e o que o ataque tirou dela.
            cov = de.groupby("pff_passCoverage").agg(
                n=("playId", "size"), comp=("completed", "mean"), yds=("playResult", "mean")
            )
            cov = cov[cov.index.notna()]
            if not cov.empty:
                top = cov.nlargest(1, "n").iloc[0]
                name = cov.nlargest(1, "n").index[0]
                share = top["n"] / len(de)
                base = (
                    self.league_coverage.loc[name, "completionRate"]
                    if name in self.league_coverage.index else None
                )
                delta = (top["comp"] - base) if base is not None and top["comp"] == top["comp"] else 0.0
                cards.append(
                    {
                        "icon": "🛡️", "tone": "blue", "team": abbr, "weight": abs(share - 0.3) + abs(delta),
                        "title": f"{abbr} vive de {name}",
                        "text": (
                            f"{self._pct(share)} dos snaps defensivos em {name}. "
                            f"Nesse esquema o ataque de {opp} completou {self._pct(top['comp'])} "
                            f"(liga: {self._pct(base)}) e tirou {top['yds']:.1f} jd/jogada."
                        ),
                        "metric": {"label": f"Uso de {name}", "value": self._pct(share)},
                    }
                )

            # 2) Pressao gerada pela defesa.
            pr = de["pressured"].mean()
            ttp = de["timeToPressure"].mean()
            cards.append(
                {
                    "icon": "⚡", "tone": "red", "team": abbr, "weight": abs(pr - (lg["pressureRate"] or 0)) * 2,
                    "title": (
                        f"Pressão de {abbr} {'acima' if pr > (lg['pressureRate'] or 0) else 'abaixo'} da média"
                    ),
                    "text": (
                        f"{abbr} pressionou o QB em {self._pct(pr)} dos dropbacks "
                        f"(liga: {self._pct(lg['pressureRate'])}), com {int(de['isSack'].sum())} sacks"
                        + (f" e primeira pressão em {ttp:.1f}s." if ttp == ttp else ".")
                    ),
                    "metric": {"label": "Taxa de pressão", "value": self._pct(pr)},
                }
            )

            # 3) Velocidade de decisao do QB do ataque.
            tt = off["timeToThrow"].mean()
            if tt == tt:
                qb = self._main_qb(game_id, abbr)
                diff = tt - (lg["timeToThrow"] or 0)
                cards.append(
                    {
                        "icon": "⏱️", "tone": "navy", "team": abbr, "weight": abs(diff),
                        "title": (
                            f"{qb or abbr} solta a bola em {tt:.1f}s"
                            if diff < 0 else f"{qb or abbr} segura a bola {abs(diff):.1f}s a mais"
                        ),
                        "text": (
                            f"Média de {tt:.1f}s entre o snap e o lançamento contra {lg['timeToThrow']:.1f}s da liga. "
                            + (
                                "Janela curta: blitz tende a chegar tarde."
                                if diff < 0 else "Pressão de 4 homens já costuma render."
                            )
                        ),
                        "metric": {"label": "Tempo p/ lançar", "value": f"{tt:.1f}s"},
                    }
                )

            # 4) Elo fraco da protecao adversaria.
            weak = self._weakest_blocker(game_id, opp)
            if weak:
                cards.append(
                    {
                        "icon": "🎯", "tone": "red", "team": abbr, "weight": 0.25 + 0.05 * weak["allowed"],
                        "title": f"Ataque o lado de {weak['name']}",
                        "text": (
                            f"O {weak['linedUp']} de {opp} cedeu {weak['allowed']} pressões "
                            f"em {weak['snaps']} snaps de proteção neste jogo."
                        ),
                        "metric": {"label": "Pressões cedidas", "value": weak["allowed"]},
                    }
                )

            # 5) Formacao mais produtiva do ataque.
            form = off.groupby("offenseFormation").agg(n=("playId", "size"), yds=("playResult", "mean"))
            form = form[(form.index.notna()) & (form["n"] >= 5)]
            if len(form) >= 2:
                best = form.nlargest(1, "yds")
                worst = form.nsmallest(1, "yds")
                bn, bv = best.index[0], best.iloc[0]
                wn, wv = worst.index[0], worst.iloc[0]
                cards.append(
                    {
                        "icon": "📋", "tone": "blue", "team": abbr,
                        "weight": abs(bv["yds"] - wv["yds"]) / 10,
                        "title": f"{bn} é a formação que rende para {abbr}",
                        "text": (
                            f"{bv['yds']:.1f} jd/jogada em {int(bv['n'])} snaps de {bn}, "
                            f"contra {wv['yds']:.1f} jd em {int(wv['n'])} de {wn}."
                        ),
                        "metric": {"label": f"{bn}", "value": f"{bv['yds']:.1f} jd"},
                    }
                )

            # 6) Blitz.
            bl = de["blitz"].mean()
            if abs(bl - (lg["blitzRate"] or 0)) > 0.08:
                cards.append(
                    {
                        "icon": "💥", "tone": "navy", "team": abbr, "weight": abs(bl - (lg["blitzRate"] or 0)),
                        "title": f"{abbr} {'abusa do' if bl > (lg['blitzRate'] or 0) else 'evita'} blitz",
                        "text": (
                            f"{self._pct(bl)} dos snaps com 5+ rushers (liga: {self._pct(lg['blitzRate'])}). "
                            + ("Protecao extra e passe rapido neutralizam." if bl > (lg["blitzRate"] or 0)
                               else "Tempo de pocket maior para rotas profundas.")
                        ),
                        "metric": {"label": "Taxa de blitz", "value": self._pct(bl)},
                    }
                )

            # 7) Terceira descida.
            third = off[off["thirdDown"]]
            if len(third) >= 4:
                rate = third["thirdConv"].mean()
                cards.append(
                    {
                        "icon": "🔁", "tone": "blue", "team": abbr,
                        "weight": abs(rate - (lg["thirdDownRate"] or 0)),
                        "title": f"3ª descida de {abbr}: {int(third['thirdConv'].sum())}/{len(third)}",
                        "text": (
                            f"{self._pct(rate)} de conversão (liga: {self._pct(lg['thirdDownRate'])}), "
                            f"com {third['yardsToGo'].mean():.1f} jd a vencer em média."
                        ),
                        "metric": {"label": "Conversão 3ª", "value": self._pct(rate)},
                    }
                )

        cards.sort(key=lambda c: -c.get("weight", 0))
        for c in cards:
            c.pop("weight", None)
        return cards[:limit]

    @staticmethod
    def _pct(v) -> str:
        f = num(v)
        return "—" if f is None else f"{f * 100:.0f}%"

    def _main_qb(self, game_id: int, abbr: str) -> str | None:
        part = self._part_by_game.get(game_id)
        if part is None:
            return None
        qbs = part[(part["pff_role"] == "Pass") & (part["team"] == abbr)]
        if qbs.empty:
            return None
        return text(qbs["displayName"].value_counts().index[0])

    def _weakest_blocker(self, game_id: int, abbr: str) -> dict | None:
        part = self._part_by_game.get(game_id)
        if part is None:
            return None
        bl = part[(part["pff_role"] == "Pass Block") & (part["team"] == abbr)]
        if bl.empty:
            return None
        agg = bl.groupby(["nflId", "displayName", "pff_positionLinedUp"]).agg(
            allowed=("pressureAllowed", "sum"), snaps=("playId", "size")
        ).reset_index()
        agg = agg[agg["snaps"] >= 8]
        if agg.empty or agg["allowed"].max() <= 0:
            return None
        top = agg.nlargest(1, "allowed").iloc[0]
        return {
            "nflId": int(top["nflId"]),
            "name": text(top["displayName"]),
            "linedUp": text(top["pff_positionLinedUp"]),
            "allowed": int(top["allowed"]),
            "snaps": int(top["snaps"]),
        }

    def notes(self, game_id: int, limit: int = 4) -> list[dict]:
        """'Bastidores': fatos concretos extraidos do proprio jogo."""
        plays = self._plays_by_game.get(game_id)
        part = self._part_by_game.get(game_id)
        if plays is None or plays.empty:
            return []
        out = []

        big = plays.nlargest(1, "playResult")
        if not big.empty and num(big.iloc[0]["playResult"], 0):
            b = big.iloc[0]
            out.append(
                {
                    "icon": "🚀",
                    "title": f"Maior jogada: {int(b['playResult'])} jardas",
                    "text": f"{text(b['possessionTeam'])} no {int(b['quarter'])}º quarto — {text(b['playDescription'])}",
                }
            )

        pocket = plays.dropna(subset=["timeToThrow"]).nlargest(1, "timeToThrow")
        if not pocket.empty:
            p = pocket.iloc[0]
            out.append(
                {
                    "icon": "⏳",
                    "title": f"Pocket mais longo: {p['timeToThrow']:.1f}s",
                    "text": (
                        f"{text(p['possessionTeam'])} segurou a proteção por {p['timeToThrow']:.1f}s "
                        f"({PASS_RESULT_LABELS.get(text(p['passResult']) or '', 'jogada')})."
                    ),
                }
            )

        if part is not None and part["maxSpeed"].notna().any():
            fast = part.loc[part["maxSpeed"].idxmax()]
            out.append(
                {
                    "icon": "💨",
                    "title": f"Mais rápido: {yd_s_to_mph(fast['maxSpeed'])} mph",
                    "text": (
                        f"{text(fast['displayName'])} ({text(fast['pff_positionLinedUp'])}, "
                        f"{text(fast['team'])}) atingiu o pico do jogo."
                    ),
                }
            )

        fouls = plays["foulName1"].dropna()
        if not fouls.empty:
            top = fouls.value_counts()
            out.append(
                {
                    "icon": "⚑",
                    "title": f"{int(len(fouls))} faltas em dropbacks",
                    "text": f"Mais comum: {top.index[0]} ({int(top.iloc[0])}x).",
                }
            )

        if plays["quarter"].max() > 4:
            out.append({"icon": "⏰", "title": "Jogo decidido na prorrogação", "text": "Houve dropbacks no 5º período."})

        return out[:limit]

    # ------------------------------ comentarista -------------------------- #
    def broadcast(self, game_id: int) -> dict | None:
        """
        Sequencia cronologica do jogo para o modo comentarista: cada dropback com
        placar pre-snap, narracao e estatisticas acumuladas ate ali.
        """
        plays = self._plays_by_game.get(game_id)
        if plays is None or plays.empty:
            return None
        row = self.games[self.games["gameId"] == game_id].iloc[0]
        home, away = row["homeTeamAbbr"], row["visitorTeamAbbr"]

        cum = {
            home: {"dropbacks": 0, "completions": 0, "attempts": 0, "yards": 0, "sacksTaken": 0, "pressures": 0},
            away: {"dropbacks": 0, "completions": 0, "attempts": 0, "yards": 0, "sacksTaken": 0, "pressures": 0},
        }
        feed = []
        for _, r in plays.iterrows():
            off = text(r["possessionTeam"])
            de = text(r["defensiveTeam"])
            if off in cum:
                c = cum[off]
                c["dropbacks"] += 1
                c["attempts"] += int(bool(r["isAttempt"]))
                c["completions"] += int(bool(r["completed"]))
                c["yards"] += int(num(r["playResult"], 0) or 0)
                c["sacksTaken"] += int(bool(r["isSack"]))
            if de in cum and bool(r["pressured"]):
                cum[de]["pressures"] += 1

            card = self._play_card(r)
            card["narration"] = self._narrate(r)
            card["cumulative"] = {
                "home": dict(cum[home]),
                "away": dict(cum[away]),
            }
            feed.append(card)

        score = self._derived_score(plays)
        return {
            "gameId": game_id,
            "home": {**team_info(home), "score": score["home"]},
            "away": {**team_info(away), "score": score["away"]},
            "feed": feed,
            "totals": {
                "home": self._team_game(game_id, home),
                "away": self._team_game(game_id, away),
            },
        }

    def _narrate(self, r: pd.Series) -> dict:
        """Monta a linha de narracao de uma jogada a partir dos dados reais."""
        pr = text(r["passResult"])
        desc = text(r["playDescription"]) or ""
        yards = int(num(r["playResult"], 0) or 0)
        off = text(r["possessionTeam"])
        touchdown = "TOUCHDOWN" in desc.upper()

        if touchdown:
            icon, tone, headline = "🏈", "td", "TOUCHDOWN!"
        elif pr == "S":
            icon, tone, headline = "💪", "sack", "SACK!"
        elif pr == "IN":
            icon, tone, headline = "🛑", "turnover", "INTERCEPTADO!"
        elif pr == "C" and yards >= 20:
            icon, tone, headline = "🚀", "big", f"Passe de {yards} jardas!"
        elif pr == "C":
            icon, tone, headline = "✅", "normal", f"Completo, {yards} jd"
        elif pr == "I":
            icon, tone, headline = "❌", "normal", "Passe incompleto"
        elif pr == "R":
            icon, tone, headline = "🏃", "normal", f"QB corre, {yards} jd"
        else:
            icon, tone, headline = "🏈", "normal", "Dropback"

        bits = []
        if num(r["down"], 0):
            bits.append(f"{int(r['down'])}ª e {int(r['yardsToGo'])}")
        if bool(r["blitz"]):
            bits.append(f"blitz de {int(r['rushers'])}")
        if text(r["pff_passCoverage"]):
            bits.append(text(r["pff_passCoverage"]))
        if num(r["timeToThrow"], 1):
            bits.append(f"{r['timeToThrow']:.1f}s no pocket")
        if bool(r["pressured"]):
            bits.append("sob pressão")

        return {
            "icon": icon,
            "tone": tone,
            "headline": f"{off}: {headline}",
            "detail": desc,
            "context": " · ".join(b for b in bits if b),
        }
