"""
Teste de carga: N usuarios fazendo a "sessao tipica" ao mesmo tempo
(Requisito 1 e criterio 6.5 da spec otimizacao-desempenho).

    python tools/carga.py --usuarios 10            # imprime o resultado
    python tools/carga.py --usuarios 10 --check    # sai com erro se falhar alguma meta

Sessao tipica (7 requisicoes): detalhe do jogo, lista de jogadas, 3 trackings,
comentarista e lista do olheiro. Cada usuario faz 2 sessoes. Sorteio com semente
fixa, para que antes e depois comparem a mesma carga.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from servidor_local import pico_memoria_mb, servidor  # noqa: E402

META_P95_MS = 300     # 1.1
META_MEMORIA_MB = 600  # 6.5


def sessoes(base: str, n: int, semente: int = 2021) -> list[list[str]]:
    j = lambda p: json.load(urllib.request.urlopen(base + p))  # noqa: E731
    rnd = random.Random(semente)
    jogos = [g["gameId"] for g in j("/api/games")]
    escolhidos = rnd.sample(jogos, 20)
    com = {g: [p["playId"] for p in j(f"/api/games/{g}/plays") if p["hasTracking"]] for g in escolhidos}
    out = []
    for _ in range(n):
        g = rnd.choice(escolhidos)
        out.append(
            [f"/api/games/{g}", f"/api/games/{g}/plays"]
            + [f"/api/games/{g}/plays/{p}/tracking" for p in rnd.sample(com[g], 3)]
            + [f"/api/games/{g}/broadcast", "/api/players?limit=60"]
        )
    return out


def executar(base: str, paths: list[str]) -> list[tuple[float, str, str]]:
    """[(ms, tipo, resultado)] com resultado em ok | http-XXX | recusada | erro"""
    out = []
    for p in paths:
        tipo = "tracking" if p.endswith("/tracking") else "outras"
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(base + p, timeout=60) as r:
                r.read()
            res = "ok"
        except urllib.error.HTTPError as e:
            res = f"http-{e.code}"
        except urllib.error.URLError as e:
            recusada = isinstance(e.reason, ConnectionRefusedError) or "10061" in str(e.reason)
            res = "recusada" if recusada else "erro"
        except OSError:
            res = "erro"
        out.append(((time.perf_counter() - t) * 1000, tipo, res))
    return out


def p95(v: list[float]) -> float:
    v = sorted(v)
    return v[max(0, int(round(len(v) * 0.95)) - 1)] if v else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usuarios", type=int, default=10)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    with servidor() as srv:
        todas = sessoes(srv.url, a.usuarios * 2)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(a.usuarios) as ex:
            res = [x for r in ex.map(lambda s: executar(srv.url, s), todas) for x in r]
        parede = time.perf_counter() - t0
        pico = pico_memoria_mb(srv.pid)

    ms = [r[0] for r in res]
    trk = [r[0] for r in res if r[1] == "tracking"]
    contagem = {k: sum(1 for r in res if r[2] == k) for k in {r[2] for r in res}}
    recusadas = contagem.get("recusada", 0)
    erros = sum(v for k, v in contagem.items() if k not in ("ok", "recusada"))

    print(f"{a.usuarios} usuarios simultaneos · {len(res)} requisicoes em {parede:.1f}s   ({time.strftime('%Y-%m-%d %H:%M')})")
    print(f"  todas     p50 {statistics.median(ms):6.0f} ms   p95 {p95(ms):6.0f} ms")
    print(f"  tracking  p50 {statistics.median(trk):6.0f} ms   p95 {p95(trk):6.0f} ms")
    print(f"  resultados: {dict(sorted(contagem.items()))}")
    print(f"  pico de memoria do servidor: {pico:.0f} MB" if pico else "  pico de memoria: n/d")

    if not a.check:
        return 0
    falhas = []
    if p95(ms) > META_P95_MS:
        falhas.append(f"p95 {p95(ms):.0f} ms > {META_P95_MS} ms (1.1)")
    if recusadas:
        falhas.append(f"{recusadas} conexoes recusadas (1.2)")
    if erros:
        falhas.append(f"{erros} respostas com erro")
    if pico and pico > META_MEMORIA_MB:
        falhas.append(f"memoria {pico:.0f} MB > {META_MEMORIA_MB} MB (6.5)")
    print("\n" + ("METAS OK" if not falhas else "METAS FALHARAM:\n  " + "\n  ".join(falhas)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
