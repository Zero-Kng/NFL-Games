"""Verificacao rapida da camada de dados: roda todas as consultas e imprime amostras.

Le a copia local em dados/ (nao acessa a internet). Sem copia, suba o servidor
uma vez (python server/serve.py) para baixar e montar os dados.

Uso:  python server/smoke_test.py [temporada]      # padrao: a ultima encerrada
"""

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
    nfl = NFLData(ROOT / "dados")
    print(f"carga: {time.perf_counter() - t0:.1f}s")

    meta = nfl.meta()
    print("temporadas:", [s["season"] for s in meta["seasons"]], "| atual:", meta["season"],
          "semana", meta["currentWeek"])
    print("contagens da atual:", meta["counts"])
    print("ultima atualizacao:", meta["ultimaAtualizacao"])
    print("fontes:", [f["nome"] for f in meta["fontes"]])

    ano = int(sys.argv[1]) if len(sys.argv) > 1 else max(a for a in nfl.temporadas if a < nfl.atual)
    sem = next(s for s in meta["seasons"] if s["season"] == ano)
    print(f"\n{ano}: {sem['counts']} | rodadas: {[w['rodada'] for w in sem['weeks']][-5:]}")

    g3 = nfl.games_list(season=ano, week=3)
    print(f"\njogos na semana 3 de {ano}: {len(g3)}")
    for g in g3[:4]:
        print(f"  {g['away']['abbr']:>3} {g['away']['score']!s:>3} @ {g['home']['abbr']:<3} {g['home']['score']!s:<3}"
              f"  {g['date']} {g['kickoff']}  {g['status']}, {g['plays']} jogadas")

    gid = g3[0]["gameId"]
    game = nfl.game(gid)
    show(f"jogo {gid} · ataque casa", game["teams"]["home"]["offense"], 600)
    show(f"jogo {gid} · defesa visitante", game["teams"]["away"]["defense"], 600)
    print(f"\n=== formações do ataque da casa ===")
    for f in game["tendencies"]["home"]["formations"][:4]:
        print(f"  {f['label']:<14} {f['plays']:>3} jogadas  {f['yardsPerPlay']} jd/jogada")

    print(f"\n=== destaques ({len(game['watch'])}) ===")
    for w in game["watch"]:
        print(f"  {w['rating']:>3}  {w['name']:<22} {w['position']:<3} {w['team']:<3} {w['roleLabel']} ({w['gameSnaps']} snaps)")

    plays = nfl.game_plays(gid)
    print(f"\njogadas: {len(plays)} | com formação: {sum(p['hasFormation'] for p in plays)}")
    show("primeira jogada", plays[0], 1200)

    pid = next(p["playId"] for p in plays if p["hasFormation"])
    tr = nfl.play_tracking(gid, pid)
    print(f"\n=== prancheta da jogada {pid} (ilustrativo={tr['ilustrativo']}, generico={tr['generico']}) ===")
    print(f"  quadros={tr['frameCount']} direcao={tr['playDirection']} jogadores={len(tr['players'])}")
    print(f"  formação: {tr['formacao']}")
    for p in sorted(tr["players"], key=lambda z: (z["side"] or "", z["position"] or ""))[:24]:
        x, y = p["t"][0][:2]
        print(f"  {p['side']:<8} {str(p['position']):<4} #{str(p['jersey']):<3} {str(p['name'])[:20]:<20} "
              f"x={x:>6} y={y:>5} rating={p['rating']}")

    print(f"\n=== busca de jogadores (QB, {ano}) ===")
    for p in nfl.players_list(season=ano, position="QB", limit=8):
        print(f"  {p['rating']!s:>3}  {p['name']:<22} {p['team']:<3} {p['snaps']} snaps  {p['games']} jogos")

    qb = nfl.players_list(season=ano, position="QB", limit=1)[0]
    prof = nfl.player(qb["nflId"], season=ano)
    print(f"\n=== perfil: {prof['name']} ({prof['position']}, {prof['team']}) ===")
    print(f"  {prof['height']} · {prof['weight']} lb · {prof['college']} · {prof['age']} anos · rating {prof['rating']}")
    for r in prof["roles"]:
        print(f"  grupo {r['roleLabel']} ({r['snaps']} snaps, rating {r['rating']}):")
        print("    radar:", [(a["label"], a["value"], a["unit"], a["percentile"]) for a in r["radar"]])
        print("    stats:", [(s["label"], s["value"], s["unit"]) for s in r["stats"]][:6])
    print("  temporadas:", prof["seasons"])
    print("  jogos:", len(prof["gameLog"]), "| ex.:", prof["gameLog"][0] if prof["gameLog"] else None)

    print(f"\n=== líderes: pressão por snap (Edge, {ano}) ===")
    for p in nfl.leaders("pressao_snap", role="EDGE", limit=8, season=ano):
        print(f"  {p['rating']!s:>3}  {p['name']:<22} {p['team']:<3} {p['metric']['value']}")

    print(f"\n=== líderes: EPA por dropback (QB, {ano}) ===")
    for p in nfl.leaders("epa_dropback", role="QB", limit=6, season=ano):
        print(f"  {p['rating']!s:>3}  {p['name']:<22} {p['team']:<3} {p['metric']['value']}")

    edges = nfl.players_list(season=ano, role="EDGE", limit=2)
    cmp = nfl.compare(edges[0]["nflId"], edges[1]["nflId"], season=ano)
    print(f"\n=== comparação: {cmp['left']['name']} vs {cmp['right']['name']} (mesmo grupo: {cmp['sameRole']}) ===")
    for r in cmp["rows"]:
        print(f"  {r['label']:<20} {str(r['left']):>8} {r['unit']:<3} vs {str(r['right']):>8}")

    bc = nfl.broadcast(gid)
    print(f"\n=== transmissão: {bc['away']['abbr']} @ {bc['home']['abbr']} ({len(bc['feed'])} jogadas) ===")
    for p in bc["feed"][:3]:
        n = p["narration"]
        print(f"  Q{p['quarter']} {p['clock']} [{p['score']['away']}-{p['score']['home']}] {n['icon']} {n['headline']}")
    last = bc["feed"][-1]
    print(f"  ...último placar do feed: {last['score']['away']}-{last['score']['home']} "
          f"(oficial: {bc['away']['score']}-{bc['home']['score']})")

    print(f"\ntotal: {time.perf_counter() - t0:.1f}s — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
