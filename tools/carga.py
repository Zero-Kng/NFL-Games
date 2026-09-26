"""
Teste de carga: N usuarios fazendo a "sessao tipica" ao mesmo tempo
(Requisito 1 e criterio 6.5 da spec otimizacao-desempenho).

    python tools/carga.py --usuarios 10              # cenario da spec (com pausas)
    python tools/carga.py --usuarios 10 --check      # sai com erro se falhar alguma meta
    python tools/carga.py --usuarios 10 --sem-pausa  # estresse: cliques sem intervalo

Sessao tipica (7 requisicoes), na semana mais recente disputada (NFR 1 da spec
dados-externos): detalhe do jogo, lista de jogadas, 3 pranchetas,
comentarista e lista do olheiro, com uma pausa de 1 a 2 s entre um clique e o
proximo, como uma pessoa real (requirements v0.3). So o tempo de cada resposta
e medido; a pausa nao entra na conta. Cada usuario faz 2 sessoes. Sorteios com
semente fixa, para que rodadas diferentes comparem a mesma carga.

O modo --sem-pausa e o cenario antigo (mais agressivo que pessoas reais): fica
como teste de estresse, sem meta de p95.
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
from servidor_local import jogos_da_semana_recente, pico_memoria_mb, servidor  # noqa: E402

META_P95_MS = 300     # 1.1
META_MEMORIA_MB = 1024  # NFR 5 dados-externos (6 temporadas carregadas)


def sessoes(base: str, n: int, semente: int = 2021) -> list[list[str]]:
    j = lambda p: json.load(urllib.request.urlopen(base + p))  # noqa: E731
    rnd = random.Random(semente)
    escolhidos = jogos_da_semana_recente(base)
    com = {g: [p["playId"] for p in j(f"/api/games/{g}/plays") if p["hasFormation"]] for g in escolhidos}
    out = []
    for _ in range(n):
        g = rnd.choice(escolhidos)
        out.append(
            [f"/api/games/{g}", f"/api/games/{g}/plays"]
            + [f"/api/games/{g}/plays/{p}/tracking" for p in rnd.sample(com[g], 3)]
            + [f"/api/games/{g}/broadcast", "/api/players?limit=60"]
        )
    return out


def executar(base: str, paths: list[str], pausa: tuple[float, float] | None = None,
             semente: int = 0) -> list[tuple[float, str, str]]:
    """[(ms, tipo, resultado)] com resultado em ok | http-XXX | recusada | erro"""
    rnd = random.Random(semente)
    out = []
    for i, p in enumerate(paths):
        if pausa and i:
            time.sleep(rnd.uniform(*pausa))  # a pessoa le a tela antes do proximo clique
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
    ap.add_argument("--sem-pausa", action="store_true", help="estresse: cliques sem intervalo (sem meta de p95)")
    ap.add_argument("--pausa-min", type=float, default=1.0)
    ap.add_argument("--pausa-max", type=float, default=2.0)
    a = ap.parse_args()
    pausa = None if a.sem_pausa else (a.pausa_min, a.pausa_max)

    with servidor() as srv:
        todas = sessoes(srv.url, a.usuarios * 2)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(a.usuarios) as ex:
            res = [x for r in ex.map(lambda i: executar(srv.url, todas[i], pausa, semente=i),
                                     range(len(todas))) for x in r]
        parede = time.perf_counter() - t0
        pico = pico_memoria_mb(srv.pid)

    ms = [r[0] for r in res]
    trk = [r[0] for r in res if r[1] == "tracking"]
    contagem = {k: sum(1 for r in res if r[2] == k) for k in {r[2] for r in res}}
    recusadas = contagem.get("recusada", 0)
    erros = sum(v for k, v in contagem.items() if k not in ("ok", "recusada"))

    modo = "SEM pausa (estresse)" if a.sem_pausa else f"pausa de {a.pausa_min:g}-{a.pausa_max:g}s entre cliques"
    print(f"{a.usuarios} usuarios simultaneos, {modo} · {len(res)} requisicoes em {parede:.1f}s   "
          f"({time.strftime('%Y-%m-%d %H:%M')})")
    print(f"  todas     p50 {statistics.median(ms):6.0f} ms   p95 {p95(ms):6.0f} ms")
    print(f"  tracking  p50 {statistics.median(trk):6.0f} ms   p95 {p95(trk):6.0f} ms")
    print(f"  resultados: {dict(sorted(contagem.items()))}")
    print(f"  pico de memoria do servidor: {pico:.0f} MB" if pico else "  pico de memoria: n/d")

    if not a.check:
        return 0
    falhas = []
    if a.sem_pausa:
        print("  (estresse: o p95 nao tem meta; so erros, recusas e memoria sao checados)")
    elif p95(ms) > META_P95_MS:
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
