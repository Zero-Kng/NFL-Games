"""
ETL: deriva metricas de tracking do NFL Big Data Bowl 2023.

Varre os arquivos data/tracking/tracking_<gameId>.csv (122 jogos, ~810 MB) e
gera caches compactos que a API carrega na inicializacao:

  cache/play_timing.csv   -> 1 linha por jogada  (snap, release, tempo de passe,
                             tempo ate a primeira pressao, duracao)
  cache/player_play.csv   -> 1 linha por jogador/jogada (velocidade maxima,
                             distancia percorrida)

Uso:
    python etl/build_metrics.py                 # todos os jogos
    python etl/build_metrics.py --limit 3       # amostra rapida p/ validacao
    python etl/build_metrics.py --force         # ignora cache existente
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
TRACKING = DATA / "tracking"
CACHE = ROOT / "cache"

FPS = 10.0  # tracking a 10 quadros por segundo

# Eventos em ordem de prioridade: a marcacao humana vale mais que o "autoevent".
#
# Isso importa: em jogadas com pre-snap longo (line_set/shift) o
# autoevent_ballsnap dispara falso no inicio do arquivo, muito antes do snap
# real. Misturar os dois e pegar o menor frame gerava "pockets" de 16-19s.
# Por isso o autoevent so entra quando nao existe o evento manual.
SNAP_EVENTS = (
    ("ball_snap",),            # 1a escolha: marcado por humano
    ("autoevent_ballsnap",),   # 2a escolha: deteccao automatica
)
# Eventos que encerram a acao do QB: passe, sack ou corrida (scramble).
RELEASE_EVENTS = (
    ("pass_forward", "qb_sack", "qb_strip_sack", "run", "fumble"),
    ("autoevent_passforward",),
)
# Raio (em jardas) a partir do qual consideramos que o rusher pressionou o QB.
PRESSURE_RADIUS_YD = 2.0

TRACK_COLS = ["playId", "nflId", "frameId", "team", "x", "y", "s", "dis", "event"]


def _first_frame(events: pd.DataFrame, groups: tuple[tuple[str, ...], ...]) -> pd.Series:
    """
    Primeiro frameId de cada jogada, respeitando a prioridade dos grupos:
    so cai para o grupo seguinte nas jogadas que nao tem nenhum evento do grupo
    anterior (evita o autoevent falso mascarar a marcacao humana).
    """
    out: pd.Series | None = None
    for names in groups:
        hit = events[events["event"].isin(names)]
        found = hit.groupby("playId")["frameId"].min()
        out = found if out is None else out.combine_first(found)
    return out if out is not None else pd.Series(dtype="float64")


def play_timing(track: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Tempos por jogada: snap, release, duracao e tempo ate a primeira pressao."""
    ball = track[track["nflId"].isna()]
    events = ball.loc[ball["event"].notna(), ["playId", "frameId", "event"]]

    snap = _first_frame(events, SNAP_EVENTS).rename("snapFrame")
    release = _first_frame(events, RELEASE_EVENTS).rename("releaseFrame")
    end = ball.groupby("playId")["frameId"].max().rename("endFrame")

    timing = pd.concat([snap, release, end], axis=1)
    timing["timeToThrow"] = (timing["releaseFrame"] - timing["snapFrame"]) / FPS
    timing["playSeconds"] = (timing["endFrame"] - timing["snapFrame"]) / FPS
    # Jogadas sem snap marcado ou com release antes do snap nao sao confiaveis.
    timing.loc[timing["timeToThrow"] <= 0, "timeToThrow"] = np.nan

    pressure, per_rusher = _pressure_timing(track, roles, timing)
    timing = timing.join(pressure)

    players = track[track["nflId"].notna()]
    qb_ids = roles.loc[roles["pff_role"] == "Pass", ["playId", "nflId"]]
    qb_track = players.merge(qb_ids, on=["playId", "nflId"], how="inner")
    qb_stats = qb_track.groupby("playId").agg(
        qbMaxSpeed=("s", "max"), qbDistance=("dis", "sum")
    )
    return timing.join(qb_stats).reset_index(), per_rusher


def _pressure_timing(
    track: pd.DataFrame, roles: pd.DataFrame, timing: pd.DataFrame
) -> tuple[pd.Series, pd.Series]:
    """
    Segundos entre o snap e o instante em que um pass rusher entra no raio de
    PRESSURE_RADIUS_YD jardas do QB (considerando so os frames do snap ao release).

    Retorna (por jogada: o rusher mais rapido, por rusher: seu proprio tempo).
    """
    players = track.loc[track["nflId"].notna(), ["playId", "nflId", "frameId", "x", "y"]]

    qb = players.merge(
        roles.loc[roles["pff_role"] == "Pass", ["playId", "nflId"]],
        on=["playId", "nflId"],
        how="inner",
    ).rename(columns={"x": "qbX", "y": "qbY"})[["playId", "frameId", "qbX", "qbY"]]

    rush = players.merge(
        roles.loc[roles["pff_role"] == "Pass Rush", ["playId", "nflId"]],
        on=["playId", "nflId"],
        how="inner",
    )
    empty_play = pd.Series(dtype="float64", name="timeToPressure")
    empty_rusher = pd.Series(
        dtype="float64", name="timeToQb", index=pd.MultiIndex.from_arrays([[], []], names=["playId", "nflId"])
    )
    if rush.empty or qb.empty:
        return empty_play, empty_rusher

    pair = rush.merge(qb, on=["playId", "frameId"], how="inner")
    pair = pair.merge(
        timing[["snapFrame", "releaseFrame"]], left_on="playId", right_index=True, how="left"
    )
    # A janela de pressao vai do snap ao release (ou fim da jogada, se nao houver).
    window_end = pair["releaseFrame"].fillna(np.inf)
    pair = pair[(pair["frameId"] >= pair["snapFrame"]) & (pair["frameId"] <= window_end)]

    dist = np.hypot(pair["x"] - pair["qbX"], pair["y"] - pair["qbY"])
    close = pair.loc[dist <= PRESSURE_RADIUS_YD]
    if close.empty:
        return empty_play, empty_rusher

    # Por jogada: o primeiro rusher a furar a protecao.
    first_play = close.groupby("playId")["frameId"].min()
    per_play = (
        (first_play - timing["snapFrame"].reindex(first_play.index)) / FPS
    ).rename("timeToPressure")

    # Por rusher: quanto ele mesmo levou para chegar ao QB.
    first_rusher = close.groupby(["playId", "nflId"])["frameId"].min()
    snap_of = timing["snapFrame"].reindex(first_rusher.index.get_level_values("playId"))
    per_rusher = pd.Series(
        (first_rusher.to_numpy() - snap_of.to_numpy()) / FPS,
        index=first_rusher.index,
        name="timeToQb",
    )
    return per_play, per_rusher


def player_play_motion(
    track: pd.DataFrame, timing: pd.DataFrame, per_rusher: pd.Series
) -> pd.DataFrame:
    """
    Movimento de cada jogador em cada jogada: velocidade de pico, distancia
    percorrida e deslocamento entre o snap e o release (profundidade da rota /
    recuo do blocker).
    """
    players = track[track["nflId"].notna()]
    agg = players.groupby(["playId", "nflId"]).agg(
        maxSpeed=("s", "max"), distance=("dis", "sum"), frames=("frameId", "count")
    )

    frames = timing.set_index("playId")[["snapFrame", "releaseFrame"]]
    pos = players[["playId", "nflId", "frameId", "x", "y"]].join(frames, on="playId")
    # Fim da janela: o release; se a jogada nao tem release marcado, o ultimo frame.
    pos["endFrame"] = pos["releaseFrame"].fillna(
        pos.groupby("playId")["frameId"].transform("max")
    )

    at_snap = pos[pos["frameId"] == pos["snapFrame"]].set_index(["playId", "nflId"])[["x", "y"]]
    at_end = pos[pos["frameId"] == pos["endFrame"]].set_index(["playId", "nflId"])[["x", "y"]]
    delta = at_end.subtract(at_snap, fill_value=np.nan)

    agg["depth"] = delta["x"].abs()      # jardas ganhas/perdidas no eixo longo
    agg["lateral"] = delta["y"].abs()    # deslocamento no eixo curto
    # Tempo que o rusher levou para alcancar o QB (NaN se nao alcancou).
    agg["timeToQb"] = per_rusher.reindex(agg.index)
    return agg.reset_index()


def process_game(path: Path, roles_by_game: dict[int, pd.DataFrame]):
    game_id = int(path.stem.split("_")[1])
    track = pd.read_csv(path, usecols=TRACK_COLS)
    roles = roles_by_game.get(game_id, pd.DataFrame(columns=["playId", "nflId", "pff_role"]))

    timing, per_rusher = play_timing(track, roles)

    motion = player_play_motion(track, timing, per_rusher)
    motion.insert(0, "gameId", game_id)

    timing.insert(0, "gameId", game_id)
    motion["nflId"] = motion["nflId"].astype("int64")
    return timing, motion


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="processa apenas N jogos")
    ap.add_argument("--force", action="store_true", help="recalcula mesmo se o cache existir")
    args = ap.parse_args()

    if not TRACKING.is_dir():
        print(f"[erro] pasta de tracking nao encontrada: {TRACKING}", file=sys.stderr)
        return 1

    CACHE.mkdir(exist_ok=True)
    out_timing = CACHE / "play_timing.csv"
    out_motion = CACHE / "player_play.csv"
    if out_timing.exists() and out_motion.exists() and not args.force and not args.limit:
        print("[skip] cache ja existe. use --force para recalcular.")
        return 0

    print("[1/3] lendo pffScoutingData (funcoes por jogada)...")
    roles = pd.read_csv(
        DATA / "pffScoutingData.csv", usecols=["gameId", "playId", "nflId", "pff_role"]
    )
    roles_by_game = {gid: df for gid, df in roles.groupby("gameId")}

    files = sorted(TRACKING.glob("tracking_*.csv"))
    if args.limit:
        files = files[: args.limit]
    print(f"[2/3] processando {len(files)} arquivos de tracking...")

    timings, motions = [], []
    t0 = time.perf_counter()
    for i, path in enumerate(files, start=1):
        timing, motion = process_game(path, roles_by_game)
        timings.append(timing)
        motions.append(motion)
        elapsed = time.perf_counter() - t0
        eta = elapsed / i * (len(files) - i)
        print(
            f"  {i:3d}/{len(files)}  {path.name}  "
            f"{len(timing):4d} jogadas  ({elapsed:5.1f}s decorridos, ~{eta:5.1f}s restantes)",
            flush=True,
        )

    all_timing = pd.concat(timings, ignore_index=True)
    all_motion = pd.concat(motions, ignore_index=True)

    print("[3/3] gravando cache...")
    all_timing.to_csv(out_timing, index=False, float_format="%.3f")
    all_motion.to_csv(out_motion, index=False, float_format="%.3f")

    tt = all_timing["timeToThrow"].dropna()
    tp = all_timing["timeToPressure"].dropna()
    print(
        f"\nok: {len(all_timing)} jogadas | tempo de passe medio {tt.mean():.2f}s "
        f"(mediana {tt.median():.2f}s) | pressao em {len(tp)} jogadas "
        f"({100 * len(tp) / len(all_timing):.1f}%), media {tp.mean():.2f}s"
    )
    print(f"  {out_timing}  ({out_timing.stat().st_size / 1e6:.1f} MB)")
    print(f"  {out_motion}  ({out_motion.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
