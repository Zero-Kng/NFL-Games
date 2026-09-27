"""
Exporta o app para um site estático (spec site-publico): a interface de app/ e, em
api/{versao}/, as respostas da API que ela usa, gravadas pela mesma camada de dados
do servidor (NFLData). É o que o GitHub Actions publica no GitHub Pages.

    python tools/exportar.py                          # tudo, em site/
    python tools/exportar.py --saida site --processos 4
    python tools/exportar.py --temporadas 2021,2026   # só essas (o meta.json sai completo)

Estrutura (design, Data Model):
    index.html, css/, js/, img/            cópia de app/ + <meta name="nfl-dados" content="estatico">
    api/versao.json                        {"versao": "AAAAMMDDTHHMM"}  (UTC)
    api/{versao}/meta.json
    api/{versao}/jogos/{id}.json.gz        {"game", "plays", "broadcast"}
    api/{versao}/jogos/{id}.pranchetas.json.gz   {"<playId>": tracking}
    api/{versao}/{ano}/semanas/{semana}.json, jogadores.json, jogadores/{nflId}.json,
                       noticias.json, noticias/{semana}.json, resumo.json

Sai com código 1 se a verificação final (verificar) achar problema.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "server", ROOT / "etl"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

MARCA = '<meta name="nfl-dados" content="estatico">'
LIMITE_PAGES = 1_000_000_000   # 1 GB por site (RNF 1)


# ------------------------------------------------------------------ gravação
def gravar_json(caminho: Path, obj, gz: bool = False) -> None:
    """Grava de forma atômica: um .tmp ao lado e depois os.replace."""
    corpo = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if gz:
        corpo = gzip.compress(corpo, compresslevel=9, mtime=0)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(corpo)
    os.replace(tmp, caminho)


# ------------------------------------------------- trabalho dos processos
_nfl = None


def _iniciar(dados: str, agora_iso: str | None) -> None:
    global _nfl
    import data_layer
    _nfl = data_layer.NFLData(Path(dados), hoje=datetime.fromisoformat(agora_iso) if agora_iso else None)


def _exportar_jogos(destino: str, ids: list[int]) -> int:
    base = Path(destino) / "jogos"
    for gid in ids:
        plays = _nfl.game_plays(gid)
        gravar_json(base / f"{gid}.json.gz",
                    {"game": _nfl.game(gid), "plays": plays, "broadcast": _nfl.broadcast(gid)}, gz=True)
        pranchetas = {}
        for p in plays:
            tr = _nfl.play_tracking(gid, p["playId"])
            if tr is not None:
                pranchetas[str(p["playId"])] = tr
        gravar_json(base / f"{gid}.pranchetas.json.gz", pranchetas, gz=True)
    return len(ids)


def _exportar_perfis(destino: str, ano: int, ids: list[str]) -> int:
    base = Path(destino) / str(ano) / "jogadores"
    for pid in ids:
        gravar_json(base / f"{pid}.json", _nfl.player(pid, ano))
    return len(ids)


def _fatias(itens: list, n: int) -> list[list]:
    return [itens[i::n] for i in range(n) if itens[i::n]]


# --------------------------------------------------------------- exportar
def exportar(dados: Path, saida: Path, temporadas: set[int] | None = None, processos: int = 4,
             agora: datetime | None = None) -> str:
    """Exporta para `saida` e devolve a versão (AAAAMMDDTHHMM, UTC)."""
    import data_layer

    agora = agora or datetime.now(timezone.utc)
    agora_iso = agora.isoformat()
    versao = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)

    # interface: cópia de app/ com a marca que troca a fonte de dados (api.js)
    shutil.copytree(ROOT / "app", saida, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    index = saida / "index.html"
    html = index.read_text(encoding="utf-8")
    if MARCA not in html:
        index.write_text(html.replace("</head>", MARCA + "\n</head>", 1), encoding="utf-8")

    if (saida / "api").exists():
        shutil.rmtree(saida / "api")        # versões antigas não vão junto
    destino = saida / "api" / versao

    _iniciar(str(dados), agora_iso)
    nfl = _nfl
    meta = nfl.meta()
    anos = [t["season"] for t in meta["seasons"] if temporadas is None or t["season"] in temporadas]
    gravar_json(destino / "meta.json", meta)

    jogos, perfis = [], []
    for t in meta["seasons"]:
        ano = t["season"]
        if ano not in anos:
            continue
        base = destino / str(ano)
        for w in t["weeks"]:
            lista = nfl.games_list(season=ano, week=w["week"])
            gravar_json(base / "semanas" / f"{w['week']}.json", lista)
            gravar_json(base / "noticias" / f"{w['week']}.json", nfl.news(season=ano, week=w["week"]))
            jogos += [g["gameId"] for g in lista]
        gravar_json(base / "noticias.json", nfl.news(season=ano))
        gravar_json(base / "resumo.json", nfl.summary(season=ano))
        gravar_json(base / "jogadores.json", nfl.players_list(season=ano, rated_only=False, limit=10**6))
        perfis += [(ano, str(pid)) for pid in nfl.temporadas[ano].jogadores.index]

    print(f"exportar: {len(anos)} temporadas, {len(jogos)} jogos, {len(perfis)} perfis, {processos} processos",
          flush=True)
    if processos <= 1:
        _exportar_jogos(str(destino), jogos)
        for ano in anos:
            _exportar_perfis(str(destino), ano, [p for a, p in perfis if a == ano])
    else:
        with ProcessPoolExecutor(max_workers=processos, initializer=_iniciar,
                                 initargs=(str(dados), agora_iso)) as pool:
            tarefas = [pool.submit(_exportar_jogos, str(destino), f) for f in _fatias(jogos, processos * 4)]
            for ano in anos:
                ids = [p for a, p in perfis if a == ano]
                tarefas += [pool.submit(_exportar_perfis, str(destino), ano, f) for f in _fatias(ids, processos)]
            for t in tarefas:
                t.result()                      # propaga qualquer erro de um processo

    gravar_json(saida / "api" / "versao.json", {"versao": versao})   # por último: só aponta para o que está completo
    return versao


# -------------------------------------------------------------- verificar
def _tamanho(pasta: Path) -> int:
    return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file())


def verificar(saida: Path, limite_bytes: int = LIMITE_PAGES) -> list[str]:
    """Problemas que impedem publicar; lista vazia quando está tudo certo."""
    saida = Path(saida)
    problemas = []
    try:
        versao = json.loads((saida / "api" / "versao.json").read_text(encoding="utf-8"))["versao"]
    except (OSError, ValueError, KeyError):
        return ["api/versao.json ausente ou ilegível"]
    destino = saida / "api" / versao
    try:
        meta = json.loads((destino / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = None
        problemas.append(f"api/{versao}/meta.json ausente ou ilegível")
    if meta is not None:
        for t in meta["seasons"]:
            if not (destino / str(t["season"])).exists():
                continue                        # temporada fora desta exportação (--temporadas)
            gid = next(iter(json.loads((destino / str(t["season"]) / "semanas" /
                                        f"{t['weeks'][0]['week']}.json").read_text(encoding="utf-8"))), {}).get("gameId")
            try:
                b = json.loads(gzip.decompress((destino / "jogos" / f"{gid}.json.gz").read_bytes()))
                assert {"game", "plays", "broadcast"} <= set(b)
            except (OSError, ValueError, AssertionError, EOFError):
                problemas.append(f"jogo {gid} ({t['season']}) ausente ou ilegível")
    try:
        if MARCA not in (saida / "index.html").read_text(encoding="utf-8"):
            problemas.append("index.html sem a marca da fonte estática")
    except OSError:
        problemas.append("index.html ausente")
    total = _tamanho(saida)
    if total > limite_bytes:
        problemas.append(f"site com {total / 1e6:.0f} MB, acima do limite de {limite_bytes / 1e6:.0f} MB")
    return problemas


# ------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exporta o app para um site estático (GitHub Pages).")
    ap.add_argument("--saida", default=str(ROOT / "site"))
    ap.add_argument("--dados", default=str(ROOT / "dados"))
    ap.add_argument("--processos", type=int, default=4)
    ap.add_argument("--temporadas", default=None, help="ex.: 2021,2026 (padrão: todas)")
    args = ap.parse_args(argv)
    temporadas = {int(a) for a in args.temporadas.split(",")} if args.temporadas else None

    t0 = time.perf_counter()
    versao = exportar(Path(args.dados), Path(args.saida), temporadas=temporadas, processos=args.processos)
    problemas = verificar(Path(args.saida))
    print(f"exportar: versao {versao} em {time.perf_counter() - t0:.0f} s, "
          f"{_tamanho(Path(args.saida)) / 1e6:.0f} MB" if Path(args.saida).exists() else f"exportar: versao {versao}",
          flush=True)
    for p in problemas:
        print("PROBLEMA:", p, file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
