"""
Teste de regressao "golden": prova que nenhuma resposta da API mudou.

    python tools/golden.py capture          # fotografa a versao atual (so uma vez!)
    python tools/golden.py check            # compara a versao atual com a foto
    python tools/golden.py check --url http://127.0.0.1:8000   # usa servidor ja de pe

Guarda em tests/golden/hashes.json, para cada URL, o status HTTP e o SHA-256 do
JSON canonico (chaves ordenadas). A ordem das chaves nao conta; a ordem das
listas e todos os valores contam. So hashes sao guardados, nao o conteudo.

A lista de URLs e montada na captura (a partir das respostas da versao atual) e
gravada junto; o check refaz exatamente as mesmas chamadas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
from servidor_local import ROOT, servidor  # noqa: E402

ARQUIVO = ROOT / "tests" / "golden" / "hashes.json"

# Metricas do endpoint /api/leaders por grupo (espelha ratings.EIXOS, fixado aqui
# de proposito: o golden nao pode depender do codigo que ele verifica).
LEADERS = {
    "QB": ["epa_dropback", "cpoe", "jd_tentativa", "int_tentativa", "sack_dropback", "epa_corrida_jogo"],
    "RB": ["epa_corrida", "jd_apos_contato", "quebrados_toque", "jd_rec_jogo", "fumble_toque"],
    "WRTE": ["jd_alvo", "epa_alvo", "rec_alvo", "alvos_jogo", "drop_alvo"],
    "OL": ["snaps_of", "faltas_100", "pressao_time", "antes_contato_time"],
    "EDGE": ["pressao_snap", "sack_snap", "hit_snap", "tfl_snap", "perdidos_pct"],
    "DL": ["pressao_snap", "sack_snap", "hit_snap", "tfl_snap", "perdidos_pct"],
    "LB": ["tackles_snap", "tfl_snap", "pressao_snap", "rating_permitido", "perdidos_pct"],
    "DB": ["rating_permitido", "comp_permitido", "jd_alvo_permitido", "bolas_alvo", "perdidos_pct"],
}
# So temporadas encerradas: a atual muda todo dia (placar, status, semana atual).
TEMPORADAS = (2021, 2025)                 # com jogos e jogadas verificados um a um
JOGOS_COMPLETOS = 2      # por temporada, jogos com TODAS as jogadas verificadas (esquema + formacao)
JOGADAS_POR_JOGO = 3     # nos demais jogos


def buscar(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def impressao(status: int, corpo: bytes) -> dict:
    try:
        canon = json.dumps(json.loads(corpo), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        canon = corpo.decode("utf-8", "replace")
    return {"status": status, "sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest()}


def montar_urls(base: str) -> list[str]:
    j = lambda p: json.loads(buscar(base + p)[1])  # noqa: E731
    meta = j("/api/meta")
    encerradas = [t for t in meta["seasons"] if t["season"] != meta["season"]]
    urls = []
    for t in encerradas:
        a = t["season"]
        urls += [f"/api/games?season={a}&week={w['week']}" for w in t["weeks"]]
        urls += [f"/api/games?season={a}&date={quote(d, safe='')}" for d in t["weeks"][0]["dates"]]
        urls += [f"/api/players?season={a}&limit=300", f"/api/players?season={a}&rated=0&limit=300"]
        for role, metricas in LEADERS.items():
            urls += [f"/api/leaders?season={a}&metric={m}&role={role}&limit=10" for m in metricas]

    ids: dict[int, list[str]] = {}
    for a in TEMPORADAS:
        t = next(x for x in encerradas if x["season"] == a)
        semanas = [t["weeks"][0]["week"], t["weeks"][-1]["week"]]          # semana 1 e o Super Bowl
        jogos = [g["gameId"] for w in semanas for g in j(f"/api/games?season={a}&week={w}")]
        completos = set(jogos[:JOGOS_COMPLETOS])
        for g in jogos:
            urls += [f"/api/games/{g}", f"/api/games/{g}/plays", f"/api/games/{g}/broadcast"]
            jogadas = j(f"/api/games/{g}/plays")
            com = [p["playId"] for p in jogadas if p["hasFormation"]]
            sem = [p["playId"] for p in jogadas if not p["hasFormation"]]
            escolhidas = com if g in completos else com[:JOGADAS_POR_JOGO]
            for p in escolhidas:
                urls += [f"/api/games/{g}/plays/{p}/tracking", f"/api/games/{g}/plays/{p}/formation"]
            for p in escolhidas[:JOGADAS_POR_JOGO] + sem[:1]:
                urls.append(f"/api/games/{g}/plays/{p}")
            if sem:  # caminho de erro: jogada sem formacao (chutes)
                urls.append(f"/api/games/{g}/plays/{sem[0]}/tracking")
            if g in completos:
                urls += [f"/api/games/{g}/plays?quarter=2", f"/api/games/{g}/plays?team={jogadas[0]['offense']}"]
        # Olheiro
        urls += [f"/api/players?season={a}", f"/api/players?season={a}&q=a&limit=300",
                 f"/api/players?season={a}&q=smith", f"/api/players?season={a}&team=KC",
                 f"/api/players?season={a}&role=EDGE&limit=60", f"/api/players?season={a}&role=DB&position=CB&limit=60"]
        ids[a] = []
        for pos in ("QB", "WR", "T,G,C", "DE,DT,NT", "CB", "FS,SS,DB", "OLB,ILB,MLB,LB", "TE", "RB,FB"):
            url = f"/api/players?season={a}&position={pos}&limit=8"
            urls.append(url)
            ids[a] += [p["nflId"] for p in j(url)]
        urls += [f"/api/players/{i}?season={a}" for i in ids[a]]
        urls += [f"/api/compare?season={a}&a={x}&b={y}" for x, y in zip(ids[a][0::2], ids[a][1::2])]

    # Caminhos de erro (o contrato inclui as mensagens)
    g0 = j(f"/api/games?season={TEMPORADAS[0]}&week=1")[0]["gameId"]
    urls += [
        "/api/games/1", "/api/games/1/broadcast", f"/api/games/{g0}/plays/1/tracking",
        "/api/players/1", "/api/players/00-0000000", "/api/compare?a=1", "/api/leaders",
        "/api/games?week=abc", "/api/games?season=2019", "/api/players?season=abc", "/api/nada",
    ]
    return urls


def capture(base: str) -> int:
    if ARQUIVO.exists():
        print(f"[erro] {ARQUIVO} ja existe. A foto e a base de comparacao e so deve ser refeita\n"
              f"       quando o contrato da API muda de proposito. Se for o caso, apague o arquivo.")
        return 1
    t0 = time.perf_counter()
    urls = montar_urls(base)
    print(f"capturando {len(urls)} URLs...")
    fotos = {}
    for i, u in enumerate(urls, 1):
        fotos[u] = impressao(*buscar(base + u))
        if i % 250 == 0:
            print(f"  {i}/{len(urls)}", flush=True)
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(
        {"capturado_em": time.strftime("%Y-%m-%d %H:%M"), "urls": fotos}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    print(f"ok: {len(fotos)} URLs em {time.perf_counter() - t0:.0f}s -> {ARQUIVO}")
    return 0


def check(base: str) -> int:
    fotos = json.loads(ARQUIVO.read_text(encoding="utf-8"))["urls"]
    t0 = time.perf_counter()
    diverge = []
    for u, esperado in fotos.items():
        atual = impressao(*buscar(base + u))
        if atual != esperado:
            diverge.append((u, esperado["status"], atual["status"]))
    print(f"{len(fotos) - len(diverge)}/{len(fotos)} URLs identicas em {time.perf_counter() - t0:.0f}s")
    for u, antes, agora in diverge[:40]:
        print(f"  DIVERGE  {u}  (status {antes} -> {agora})")
    if len(diverge) > 40:
        print(f"  ... e mais {len(diverge) - 40}")
    print("GOLDEN OK" if not diverge else "GOLDEN FALHOU")
    return 0 if not diverge else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["capture", "check"])
    ap.add_argument("--url", help="usa um servidor ja de pe em vez de subir um")
    a = ap.parse_args()
    ctx = nullcontext(None) if a.url else servidor()
    with ctx as srv:
        base = a.url or srv.url
        return capture(base) if a.modo == "capture" else check(base)


if __name__ == "__main__":
    raise SystemExit(main())
