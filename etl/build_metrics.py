"""
ETL: deriva metricas de tracking do NFL Big Data Bowl 2023.

Varre os arquivos data/tracking/tracking_<gameId>.csv (122 jogos, ~810 MB) e
gera caches que a API usa:

  cache/tracking/<gameId>.npz   -> tracking do jogo em binario (a prancheta le daqui)
  cache/parts/<gameId>.*.csv    -> metricas de cada jogo (fonte da verdade por jogo)
  cache/play_timing.csv         -> 1 linha por jogada  (snap, release, tempo de passe,
                                   tempo ate a primeira pressao, duracao)
  cache/player_play.csv         -> 1 linha por jogador/jogada (velocidade maxima,
                                   distancia percorrida)
  cache/manifest.json           -> o que ja foi processado, de qual versao do CSV

E incremental: so processa jogos novos, alterados ou com arquivo faltando. Uma
partida nova (por exemplo, vinda de outra fonte) nao reprocessa as demais. O
servidor chama ensure_cache() ao subir, entao rodar este script e opcional.

Uso:
    python etl/build_metrics.py                 # prepara o que faltar
    python etl/build_metrics.py --force         # reprocessa todos os jogos
"""

from __future__ import annotations

import argparse
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
DATA = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
TRACKING = DATA / "tracking"
CACHE = ROOT / "cache"

sys.path.insert(0, str(ROOT / "server"))
import tracking_npz  # noqa: E402

# Suba este numero quando mudar o que o ETL calcula ou grava: forca reprocessar tudo.
ETL_VERSION = 2

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
    """Le o CSV do jogo uma vez: calcula as metricas e devolve o tracking para o .npz."""
    game_id = game_id_of(path)
    cols = list(dict.fromkeys(TRACK_COLS + tracking_npz.COLUNAS))
    raw = pd.read_csv(path, usecols=cols)
    track = raw[TRACK_COLS]
    roles = roles_by_game.get(game_id, pd.DataFrame(columns=["playId", "nflId", "pff_role"]))

    timing, per_rusher = play_timing(track, roles)

    motion = player_play_motion(track, timing, per_rusher)
    motion.insert(0, "gameId", game_id)

    timing.insert(0, "gameId", game_id)
    motion["nflId"] = motion["nflId"].astype("int64")
    return timing, motion, raw


# --------------------------------------------------------------------------- #
# preparacao incremental
# --------------------------------------------------------------------------- #
FLOAT_FORMAT = "%.3f"


@dataclass
class Relatorio:
    processados: list[int] = field(default_factory=list)
    removidos: list[int] = field(default_factory=list)
    reaproveitados: int = 0
    segundos: float = 0.0

    @property
    def mudou(self) -> bool:
        return bool(self.processados or self.removidos)


def game_id_of(path: Path) -> int:
    return int(path.stem.split("_")[1])


def _assinatura(path: Path) -> dict:
    st = path.stat()
    return {"size": st.st_size, "mtimeNs": st.st_mtime_ns}


def _arquivos_do_jogo(cache_dir: Path, gid: int) -> list[Path]:
    return [cache_dir / "parts" / f"{gid}.timing.csv", cache_dir / "parts" / f"{gid}.motion.csv",
            cache_dir / "tracking" / f"{gid}.npz"]


def _gravar_atomico(df: pd.DataFrame, destino: Path) -> None:
    tmp = destino.with_name(destino.name + ".tmp")
    df.to_csv(tmp, index=False, float_format=FLOAT_FORMAT)
    os.replace(tmp, destino)


def _ler_manifesto(cache_dir: Path) -> dict:
    try:
        return json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_manifesto(cache_dir: Path, manifesto: dict) -> None:
    destino = cache_dir / "manifest.json"
    tmp = destino.with_name("manifest.json.tmp")
    tmp.write_text(json.dumps(manifesto, indent=1), encoding="utf-8")
    os.replace(tmp, destino)


def ensure_cache(data_dir: Path = DATA, cache_dir: Path = CACHE, force: bool = False,
                 progress: Callable[[str], None] = print) -> Relatorio:
    """
    Garante que o cache esteja completo e de acordo com o dataset, processando
    so o necessario. Um jogo e (re)processado se for novo, se o CSV mudou
    (tamanho/mtime), se faltar algum arquivo dele, se a versao do ETL mudou ou
    se o pffScoutingData mudou (as funcoes por jogada entram nas metricas).
    Os agregados play_timing.csv/player_play.csv sao remontados a partir das
    partes quando algo muda. O manifest.json e gravado por ultimo: se o
    processo for interrompido, a proxima execucao refaz so o que faltou.
    """
    t0 = time.perf_counter()
    tracking_dir = Path(data_dir) / "tracking"
    pff = Path(data_dir) / "pffScoutingData.csv"
    cache_dir = Path(cache_dir)
    if not tracking_dir.is_dir():
        raise FileNotFoundError(f"pasta de tracking nao encontrada: {tracking_dir}")
    (cache_dir / "parts").mkdir(parents=True, exist_ok=True)
    (cache_dir / "tracking").mkdir(parents=True, exist_ok=True)

    antigo = _ler_manifesto(cache_dir)
    entradas = {"pffScoutingData.csv": _assinatura(pff)}
    tudo = (force or antigo.get("etlVersion") != ETL_VERSION or antigo.get("entradas") != entradas)
    feitos = {} if tudo else antigo.get("jogos", {})

    arquivos = {game_id_of(p): p for p in sorted(tracking_dir.glob("tracking_*.csv"))}
    pendentes = [
        gid for gid, p in arquivos.items()
        if feitos.get(str(gid)) != _assinatura(p)
        or not all(f.exists() for f in _arquivos_do_jogo(cache_dir, gid))
    ]
    rel = Relatorio(reaproveitados=len(arquivos) - len(pendentes))

    # Jogos que sumiram do dataset saem do cache (senao continuariam nos agregados).
    for gid_txt in set(feitos) - {str(g) for g in arquivos}:
        for f in _arquivos_do_jogo(cache_dir, int(gid_txt)):
            f.unlink(missing_ok=True)
        rel.removidos.append(int(gid_txt))

    agregados = [cache_dir / "play_timing.csv", cache_dir / "player_play.csv"]
    if not pendentes and not rel.removidos and all(a.exists() for a in agregados):
        rel.segundos = time.perf_counter() - t0
        return rel

    if pendentes:
        motivo = "reprocessando tudo" if tudo else "jogos novos ou alterados"
        progress(f"preparando cache: {len(pendentes)} de {len(arquivos)} jogos ({motivo})...")
        roles = pd.read_csv(pff, usecols=["gameId", "playId", "nflId", "pff_role"])
        roles_by_game = {gid: df for gid, df in roles.groupby("gameId")}
        for i, gid in enumerate(pendentes, start=1):
            timing, motion, raw = process_game(arquivos[gid], roles_by_game)
            f_timing, f_motion, f_npz = _arquivos_do_jogo(cache_dir, gid)
            tracking_npz.salvar(raw, f_npz)
            _gravar_atomico(timing, f_timing)
            _gravar_atomico(motion, f_motion)
            rel.processados.append(gid)
            passado = time.perf_counter() - t0
            falta = passado / i * (len(pendentes) - i)
            progress(f"  {i:3d}/{len(pendentes)}  jogo {gid}  {len(timing):4d} jogadas  "
                     f"({passado:5.1f}s decorridos, ~{falta:5.1f}s restantes)")

    # Remonta os agregados na ordem dos arquivos, igual ao ETL original.
    for nome, sufixo in (("play_timing.csv", "timing"), ("player_play.csv", "motion")):
        partes = [pd.read_csv(cache_dir / "parts" / f"{gid}.{sufixo}.csv") for gid in arquivos]
        _gravar_atomico(pd.concat(partes, ignore_index=True), cache_dir / nome)

    _gravar_manifesto(cache_dir, {
        "etlVersion": ETL_VERSION,
        "entradas": entradas,
        "jogos": {str(gid): _assinatura(p) for gid, p in arquivos.items()},
    })
    rel.segundos = time.perf_counter() - t0
    progress(f"cache pronto em {rel.segundos:.1f}s ({len(rel.processados)} processados, "
             f"{rel.reaproveitados} reaproveitados)")
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="reprocessa todos os jogos")
    args = ap.parse_args()

    try:
        rel = ensure_cache(force=args.force, progress=lambda m: print(m, flush=True))
    except FileNotFoundError as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 1
    if not rel.mudou:
        print(f"[ok] cache ja estava completo ({rel.reaproveitados} jogos). use --force para recalcular.")

    out_timing = CACHE / "play_timing.csv"
    out_motion = CACHE / "player_play.csv"
    all_timing = pd.read_csv(out_timing)
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
