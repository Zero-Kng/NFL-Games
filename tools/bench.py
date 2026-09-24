"""
Tempos por rota com 1 usuario (NFR 1 da spec otimizacao-desempenho).

    python tools/bench.py            # imprime a tabela
    python tools/bench.py --check    # sai com erro se alguma meta por rota falhar

Sobe um servidor novo a cada execucao, para que "primeiro acesso ao jogo" seja
de fato frio. "servidor" = cabecalho X-Query-Time; "cliente" = ida e volta HTTP.
Cada linha e a mediana de varias chamadas DISTINTAS (URLs diferentes), para nao
medir so o cache de respostas.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from servidor_local import servidor  # noqa: E402

# (rotulo, meta em ms no servidor, criterio) -- so as linhas com meta sao checadas
METAS = {
    "tracking, 1o acesso ao jogo": (60, "2.1"),
    "tracking, jogo ja acessado": (20, "2.2"),
    "jogada sem tracking (404)": (20, "2.4"),
    "detalhe do jogo": (60, "4.2"),
    "busca de jogadores (300)": (30, "5.3"),
}
META_STARTUP_S = (5.0, "6.2")


def medir(base: str, path: str) -> tuple[float, float, int]:
    """(ms no servidor, ms no cliente, status)"""
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(base + path, timeout=60) as r:
            r.read()
            status, h = r.status, r.headers
    except urllib.error.HTTPError as e:
        e.read()
        status, h = e.code, e.headers
    cli = (time.perf_counter() - t) * 1000
    # Respostas de erro nao trazem X-Query-Time: usa o tempo do cliente, que e
    # um limite superior do tempo no servidor.
    qt = h.get("X-Query-Time")
    srv = float(qt.rstrip("ms")) if qt else cli
    return srv, cli, status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    with servidor() as srv:
        b = srv.url
        j = lambda p: json.load(urllib.request.urlopen(b + p))  # noqa: E731
        jogos = [g["gameId"] for g in j("/api/games")]
        amostra = jogos[::25][:5]  # 5 jogos espalhados pela temporada
        jogadas = {g: j(f"/api/games/{g}/plays") for g in amostra}
        com = {g: [p["playId"] for p in v if p["hasTracking"]] for g, v in jogadas.items()}
        # No dataset atual toda jogada tem tracking (hasTracking nunca e falso);
        # o 404 de 2.4 e exercitado com um playId que nao existe no jogo.
        sem = [(g, p["playId"]) for g, v in jogadas.items() for p in v if not p["hasTracking"]]
        sem = (sem + [(g, 1) for g in amostra])[:3]
        ids = [p["nflId"] for p in j("/api/players?limit=10")]

        linhas: dict[str, list[str]] = {
            "meta": ["/api/meta"],
            "partidas da semana": [f"/api/games?week={w}" for w in (1, 3, 5)],
            "detalhe do jogo": [f"/api/games/{g}" for g in jogos[1::20][:5]],
            "lista de jogadas": [f"/api/games/{g}/plays" for g in jogos[2::20][:5]],
            "tracking, 1o acesso ao jogo": [f"/api/games/{g}/plays/{com[g][0]}/tracking" for g in amostra],
            "tracking, jogo ja acessado": [f"/api/games/{amostra[0]}/plays/{p}/tracking" for p in com[amostra[0]][1:6]],
            "formacao no snap": [f"/api/games/{amostra[1]}/plays/{p}/formation" for p in com[amostra[1]][1:4]],
            "jogada sem tracking (404)": [f"/api/games/{g}/plays/{p}/tracking" for g, p in sem[:3]],
            "comentarista": [f"/api/games/{g}/broadcast" for g in jogos[3::20][:3]],
            "lista do olheiro (40)": ["/api/players?limit=40"],
            "busca de jogadores (300)": ["/api/players?q=a&limit=300", "/api/players?q=e&limit=300",
                                         "/api/players?q=o&limit=300"],
            "perfil do jogador": [f"/api/players/{i}" for i in ids[:3]],
            "comparacao": [f"/api/compare?a={ids[0]}&b={ids[1]}", f"/api/compare?a={ids[2]}&b={ids[3]}"],
            "lideres": ["/api/leaders?metric=pressureRate&role=Pass+Rush"],
        }

        print(f"startup do servidor: {srv.startup_s:.1f}s   ({time.strftime('%Y-%m-%d %H:%M')})\n")
        print(f"{'rota':<30} {'servidor':>9} {'cliente':>9}   meta")
        falhas = []
        s_meta, crit = META_STARTUP_S
        if srv.startup_s > s_meta:
            falhas.append(f"startup {srv.startup_s:.1f}s > {s_meta}s ({crit})")
        for rotulo, paths in linhas.items():
            res = [medir(b, p) for p in paths]
            ms_srv = statistics.median(r[0] for r in res)
            ms_cli = statistics.median(r[1] for r in res)
            meta = METAS.get(rotulo)
            marca = ""
            if meta:
                ok = ms_srv <= meta[0]
                marca = f"<= {meta[0]} ms ({meta[1]}) {'ok' if ok else 'FALHA'}"
                if not ok:
                    falhas.append(f"{rotulo}: {ms_srv:.0f} ms > {meta[0]} ms ({meta[1]})")
            print(f"{rotulo:<30} {ms_srv:7.0f}ms {ms_cli:7.0f}ms   {marca}", flush=True)

    if a.check:
        print("\n" + ("METAS OK" if not falhas else "METAS FALHARAM:\n  " + "\n  ".join(falhas)))
        return 1 if falhas else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
