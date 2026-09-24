"""Verificacao rapida da camada de dados: roda todas as consultas e imprime amostras."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_layer import NFLData  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def show(label, obj, depth=900):
    s = json.dumps(obj, ensure_ascii=False, indent=1, default=str)
    print(f"\n=== {label} ===")
    print(s[:depth] + (" ...[cortado]" if len(s) > depth else ""))


def main():
    t0 = time.perf_counter()
    nfl = NFLData(ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data", ROOT / "cache")
    print(f"carga: {time.perf_counter() - t0:.1f}s")

    meta = nfl.meta()
    print("\ncontagens:", meta["counts"])
    print("liga:", json.dumps(meta["league"], ensure_ascii=False))
    print("times:", len(meta["teams"]), "| semanas:", [w["week"] for w in meta["weeks"]])

    g3 = nfl.games_list(week=3)
    print(f"\njogos na semana 3: {len(g3)}")
    for g in g3[:4]:
        print(f"  {g['away']['abbr']:>3} {g['away']['score']:>3} @ {g['home']['abbr']:<3} {g['home']['score']:<3}"
              f"  {g['date']}  {g['dropbacks']} dropbacks, {g['sacks']} sacks")

    gid = g3[0]["gameId"]
    game = nfl.game(gid)
    show(f"jogo {gid} · ataque casa", game["teams"]["home"]["offense"], 600)
    show(f"jogo {gid} · defesa visitante", game["teams"]["away"]["defense"], 600)

    print(f"\n=== insights ({len(game['insights'])}) ===")
    for c in game["insights"]:
        print(f"  {c['icon']} [{c['team']}] {c['title']}\n      {c['text']}")

    print(f"\n=== bastidores ({len(game['notes'])}) ===")
    for n in game["notes"]:
        print(f"  {n['icon']} {n['title']} — {n['text'][:100]}")

    print(f"\n=== destaques ({len(game['watch'])}) ===")
    for w in game["watch"]:
        print(f"  {w['rating']:>3}  {w['name']:<22} {w['position']:<3} {w['team']:<3} {w['roleLabel']} ({w['gameSnaps']} snaps)")

    plays = nfl.game_plays(gid)
    print(f"\njogadas: {len(plays)} | com tracking: {sum(p['hasTracking'] for p in plays)}")
    show("primeira jogada", plays[0], 1200)

    pid = next(p["playId"] for p in plays if p["hasTracking"])
    tr = nfl.play_tracking(gid, pid)
    print(f"\n=== tracking jogada {pid} ===")
    print(f"  frames={tr['frameCount']} direcao={tr['playDirection']} snap={tr['snapIndex']} "
          f"release={tr['releaseIndex']} jogadores={len(tr['players'])} eventos={len(tr['events'])}")
    print(f"  eventos: {tr['events']}")
    p0 = tr["players"][0]
    print(f"  ex.: {p0['name']} #{p0['jersey']} {p0['team']} {p0['linedUp']} -> {p0['t'][:3]}")

    snap = nfl.snap_formation(gid, pid)
    print(f"\n=== formação no snap ({len(snap['players'])} jogadores) ===")
    for p in sorted(snap["players"], key=lambda z: (z["side"] or "", z["linedUp"] or ""))[:24]:
        print(f"  {p['side']:<8} {str(p['linedUp']):<6} {str(p['name'])[:20]:<20} x={p['x']:>6} y={p['y']:>5} rating={p['rating']}")

    print("\n=== busca de jogadores (QB) ===")
    for p in nfl.players_list(position="QB", limit=8):
        print(f"  {p['rating']:>3}  {p['name']:<22} {p['team']:<3} {p['snaps']} snaps  top {p['topSpeed']} mph")

    qb = nfl.players_list(position="QB", limit=1)[0]
    prof = nfl.player(qb["nflId"])
    print(f"\n=== perfil: {prof['name']} ({prof['position']}, {prof['team']}) ===")
    print(f"  {prof['height']} · {prof['weight']} lb · {prof['college']} · {prof['age']} anos · rating {prof['rating']}")
    for r in prof["roles"]:
        print(f"  função {r['role']} ({r['snaps']} snaps, rating {r['rating']}):")
        print("    radar:", [(a["label"], a["value"], a["unit"], a["percentile"]) for a in r["radar"]])
        print("    stats:", [(s["label"], s["value"], s["unit"]) for s in r["stats"]])
    print("  posições:", [(x["position"], x["snaps"]) for x in prof["positionsLinedUp"]])
    print("  jogos:", len(prof["gameLog"]), "| ex.:", prof["gameLog"][0])

    print("\n=== líderes: taxa de pressão (pass rush) ===")
    for p in nfl.leaders("pressureRate", role="Pass Rush", limit=8):
        print(f"  {p['rating']:>3}  {p['name']:<22} {p['team']:<3} {p['metric']['value']}")

    print("\n=== líderes: velocidade máxima (rotas) ===")
    for p in nfl.leaders("maxSpeed", role="Pass Route", limit=6):
        print(f"  {p['rating']:>3}  {p['name']:<22} {p['team']:<3} {p['topSpeed']} mph")

    rushers = nfl.players_list(role="Pass Rush", limit=2)
    cmp = nfl.compare(rushers[0]["nflId"], rushers[1]["nflId"])
    print(f"\n=== comparação: {cmp['left']['name']} vs {cmp['right']['name']} (mesma função: {cmp['sameRole']}) ===")
    for r in cmp["rows"]:
        print(f"  {r['label']:<20} {str(r['left']):>8} {r['unit']:<3} vs {str(r['right']):>8}")

    bc = nfl.broadcast(gid)
    print(f"\n=== transmissão: {bc['away']['abbr']} @ {bc['home']['abbr']} ({len(bc['feed'])} jogadas) ===")
    for p in bc["feed"][:3]:
        n = p["narration"]
        print(f"  Q{p['quarter']} {p['clock']} [{p['score']['away']}-{p['score']['home']}] {n['icon']} {n['headline']}")
        print(f"      {n['context']}")
    last = bc["feed"][-1]
    print(f"  ...acumulado final: casa={last['cumulative']['home']}")

    print(f"\ntotal: {time.perf_counter() - t0:.1f}s — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
