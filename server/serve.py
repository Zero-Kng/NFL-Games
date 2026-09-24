"""
Servidor local do app NFL Games.

Serve a UI estatica de app/ e a API JSON /api/* sobre os dados do Big Data Bowl.
So depende da stdlib + pandas (nenhum framework a instalar).

Uso:
    python server/serve.py                 # http://127.0.0.1:8000
    python server/serve.py --port 9000
    python server/serve.py --host 0.0.0.0  # expoe na rede local (ver aviso abaixo)

Seguranca: a API e somente leitura e, por padrao, escuta apenas em 127.0.0.1.
Nao ha autenticacao, entao use --host 0.0.0.0 apenas em rede confiavel.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))

from build_metrics import ensure_cache  # noqa: E402
from data_layer import NFLData  # noqa: E402
from response_cache import CacheDeRespostas, Resposta  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
CACHE_DIR = ROOT / "cache"

GZIP_MIN_BYTES = 2048
DATA: NFLData | None = None
# Respostas prontas da API: os dados nao mudam com o servidor de pe.
CACHE = CacheDeRespostas()

# Requisicoes /api em processamento ao mesmo tempo. Acima disso: 503 imediato,
# em vez de enfileirar sem limite (protege memoria e CPU numa rajada).
MAX_PENDENTES = 64
_vagas = threading.BoundedSemaphore(MAX_PENDENTES)

# So para testes: atraso artificial em cada requisicao /api, para segurar uma
# vaga e provar o 503 de forma deterministica. Nunca definido em uso normal.
_ATRASO_TESTE_S = float(os.environ.get("NFL_ATRASO_API_MS", "0")) / 1000


class Server(ThreadingHTTPServer):
    # O padrao do socketserver e 5: acima de 5 conexoes esperando accept(), o
    # sistema operacional recusa. 128 cobre rajadas bem acima da carga-alvo.
    request_queue_size = 128
    daemon_threads = True


# --------------------------------------------------------------------------- #
# roteador minimo
# --------------------------------------------------------------------------- #
class Router:
    """
    Cada rota declara os parametros de query que entende. So eles entram na
    chave do cache de respostas, em ordem fixa: parametros desconhecidos nao
    geram variacoes e nao conseguem encher o cache.
    """

    def __init__(self):
        self.routes: list[tuple[re.Pattern, callable, tuple[str, ...]]] = []

    def get(self, pattern: str, params: tuple[str, ...] = ()):
        def deco(fn):
            self.routes.append((re.compile(f"^{pattern}$"), fn, tuple(sorted(params))))
            return fn

        return deco

    def match(self, path: str):
        for pattern, fn, params in self.routes:
            m = pattern.match(path)
            if m:
                return fn, m.groupdict(), params
        return None, None, ()


router = Router()


def chave_cache(path: str, query: dict, conhecidos: tuple[str, ...]) -> str:
    """Caminho + parametros conhecidos (1o valor, nao vazios), em ordem alfabetica."""
    pares = [(k, query[k][0]) for k in conhecidos if query.get(k) and query[k][0] != ""]
    return path + ("?" + urlencode(pares) if pares else "")


class ApiError(Exception):
    def __init__(self, status: int, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers or {}


def _int_param(query: dict, name: str, default=None):
    raw = query.get(name, [None])[0]
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        raise ApiError(400, f"parametro '{name}' deve ser inteiro (recebido: {raw!r})")


def _str_param(query: dict, name: str, default=None):
    raw = query.get(name, [None])[0]
    return default if raw in (None, "") else unquote(raw)


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
@router.get(r"/api/meta")
def api_meta(_q, _p):
    return DATA.meta()


@router.get(r"/api/games", params=("week", "date"))
def api_games(q, _p):
    return DATA.games_list(week=_int_param(q, "week"), date=_str_param(q, "date"))


@router.get(r"/api/games/(?P<game_id>\d+)")
def api_game(_q, p):
    game = DATA.game(int(p["game_id"]))
    if game is None:
        raise ApiError(404, f"jogo {p['game_id']} nao encontrado")
    return game


@router.get(r"/api/games/(?P<game_id>\d+)/plays", params=("quarter", "team"))
def api_plays(q, p):
    return DATA.game_plays(
        int(p["game_id"]), quarter=_int_param(q, "quarter"), team=_str_param(q, "team")
    )


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)")
def api_play(_q, p):
    play = DATA.play(int(p["game_id"]), int(p["play_id"]))
    if play is None:
        raise ApiError(404, "jogada nao encontrada")
    return play


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)/tracking")
def api_tracking(_q, p):
    tr = DATA.play_tracking(int(p["game_id"]), int(p["play_id"]))
    if tr is None:
        raise ApiError(404, "tracking indisponivel para esta jogada")
    return tr


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)/formation")
def api_formation(_q, p):
    f = DATA.snap_formation(int(p["game_id"]), int(p["play_id"]))
    if f is None:
        raise ApiError(404, "formacao indisponivel para esta jogada")
    return f


@router.get(r"/api/games/(?P<game_id>\d+)/broadcast")
def api_broadcast(_q, p):
    bc = DATA.broadcast(int(p["game_id"]))
    if bc is None:
        raise ApiError(404, "jogo nao encontrado")
    return bc


@router.get(r"/api/players", params=("q", "position", "role", "team", "rated", "limit"))
def api_players(q, _p):
    return DATA.players_list(
        q=_str_param(q, "q"),
        position=_str_param(q, "position"),
        role=_str_param(q, "role"),
        team=_str_param(q, "team"),
        rated_only=_str_param(q, "rated", "1") not in ("0", "false"),
        limit=min(_int_param(q, "limit", 40), 300),
    )


@router.get(r"/api/players/(?P<nfl_id>\d+)")
def api_player(_q, p):
    prof = DATA.player(int(p["nfl_id"]))
    if prof is None:
        raise ApiError(404, "jogador sem dados suficientes no periodo")
    return prof


@router.get(r"/api/compare", params=("a", "b"))
def api_compare(q, _p):
    a, b = _int_param(q, "a"), _int_param(q, "b")
    if a is None or b is None:
        raise ApiError(400, "informe os parametros 'a' e 'b' com os nflId")
    cmp = DATA.compare(a, b)
    if cmp is None:
        raise ApiError(404, "um dos jogadores nao tem dados suficientes")
    return cmp


@router.get(r"/api/leaders", params=("metric", "role", "limit"))
def api_leaders(q, _p):
    metric = _str_param(q, "metric")
    if not metric:
        raise ApiError(400, "informe o parametro 'metric'")
    return DATA.leaders(metric, role=_str_param(q, "role"), limit=min(_int_param(q, "limit", 10), 100))


# --------------------------------------------------------------------------- #
# arquivos estaticos
# --------------------------------------------------------------------------- #
APP_ROOT = APP_DIR.resolve()
_static_cache: dict[Path, tuple[int, bytes, str]] = {}
_static_lock = threading.Lock()


def _static_file(target: Path) -> tuple[bytes, str]:
    """(conteudo, ETag), relendo o arquivo so quando o mtime muda."""
    mtime = target.stat().st_mtime_ns
    with _static_lock:
        hit = _static_cache.get(target)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    body = target.read_bytes()
    etag = '"' + hashlib.sha1(body).hexdigest() + '"'
    with _static_lock:
        _static_cache[target] = (mtime, body, etag)
    return body, etag


def _etags(header: str) -> set[str]:
    """Valores de If-None-Match (aceita lista e o prefixo W/ de ETag fraca)."""
    return {t.strip().removeprefix("W/") for t in header.split(",") if t.strip()}


# --------------------------------------------------------------------------- #
# handler HTTP
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "NFLGames/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path.startswith("/api/"):
                self._handle_api(path, parse_qs(parsed.query))
            else:
                self._handle_static(path)
        except ApiError as e:
            self._send_json({"error": e.message}, status=e.status, extra_headers=e.headers)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # o cliente desistiu; nada a responder
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "erro interno no servidor"}, status=500)

    def _handle_api(self, path: str, query: dict):
        fn, params, conhecidos = router.match(path)
        if fn is None:
            raise ApiError(404, f"rota desconhecida: {path}")
        if not _vagas.acquire(blocking=False):
            raise ApiError(503, "servidor ocupado, tente novamente", {"Retry-After": "2"})
        try:
            if _ATRASO_TESTE_S:
                time.sleep(_ATRASO_TESTE_S)
            t0 = time.perf_counter()
            # Parametro invalido ou recurso inexistente viram ApiError dentro de
            # fn: atravessam o cache sem ser guardados.
            resp, hit = CACHE.get_or_build(chave_cache(path, query, conhecidos), lambda: fn(query, params))
            ms = (time.perf_counter() - t0) * 1000
        finally:
            _vagas.release()
        self._send_resposta(resp, {"X-Query-Time": f"{ms:.0f}ms", "X-Cache": "HIT" if hit else "MISS"})

    def _send_resposta(self, resp: Resposta, extra_headers: dict):
        """Envia uma resposta do cache: o gzip pronto, ou descomprimido se o cliente nao aceita."""
        headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", **extra_headers}
        if resp.raw_size >= GZIP_MIN_BYTES and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = resp.gz
            headers["Content-Encoding"] = "gzip"
        else:
            body = resp.corpo()
        self.send_response(200)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (APP_DIR / rel).resolve()
        # Impede escapar da pasta app/ via ../ -- comparar strings com startswith
        # deixaria passar uma pasta vizinha como "app2/".
        if not target.is_relative_to(APP_ROOT):
            self._send_bytes(b"forbidden", "text/plain", HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send_bytes(b"nao encontrado", "text/plain", HTTPStatus.NOT_FOUND)
            return
        body, etag = _static_file(target)
        # no-cache = o navegador pode guardar, mas revalida a cada visita (ETag).
        cache = {"Cache-Control": "no-cache", "ETag": etag, "Vary": "Accept-Encoding"}
        if etag in _etags(self.headers.get("If-None-Match", "")):
            self.send_response(HTTPStatus.NOT_MODIFIED)
            for k, v in cache.items():
                self.send_header(k, v)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send_bytes(body, ctype, extra_headers=cache)

    def _send_json(self, payload, status: int = 200, extra_headers: dict | None = None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status, extra_headers)

    def _send_bytes(self, body: bytes, ctype: str, status: int = 200, extra_headers: dict | None = None):
        headers = {"Content-Type": ctype, "Cache-Control": "no-store"}
        if extra_headers:
            headers.update(extra_headers)
        if len(body) >= GZIP_MIN_BYTES and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = gzip.compress(body, 6)
            headers["Content-Encoding"] = "gzip"
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} · {fmt % args}\n")


# --------------------------------------------------------------------------- #
def tarefas_de_aquecimento():
    """
    (chave, construtor) das respostas que todo usuario acaba pedindo, na ordem
    em que a tela as pede: meta, partidas de cada semana e, jogo a jogo (semana 1
    primeiro, que e a tela padrao), detalhe, jogadas e comentarista. O tracking
    fica de fora: 8.557 jogadas sao caras de pre-montar e a pre-carga do
    navegador cobre a navegacao.
    """
    urls = ["/api/meta", "/api/players?limit=60"]
    jogos = DATA.games.sort_values(["week", "gameId"])
    urls += [f"/api/games?week={int(w)}" for w in jogos["week"].unique()]
    for g in jogos["gameId"]:
        urls += [f"/api/games/{g}", f"/api/games/{g}/plays", f"/api/games/{g}/broadcast"]
    for url in urls:
        u = urlparse(url)
        query = parse_qs(u.query)
        fn, params, conhecidos = router.match(u.path)
        yield chave_cache(u.path, query, conhecidos), (lambda fn=fn, q=query, p=params: fn(q, p))


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-pendentes", type=int, default=MAX_PENDENTES,
                    help="requisicoes /api simultaneas antes de responder 503 (padrao: %(default)s)")
    return ap


def main() -> int:
    args = parser().parse_args()

    global DATA, _vagas
    _vagas = threading.BoundedSemaphore(args.max_pendentes)
    # Prepara so o que falta (1a execucao, jogo novo ou alterado). Com o cache
    # completo, e so uma conferencia de tamanhos/datas.
    try:
        ensure_cache(DATA_DIR, CACHE_DIR, progress=lambda m: print(m, flush=True))
    except FileNotFoundError as e:
        print(f"[erro] {e}")
        return 1
    print("carregando dataset NFL Big Data Bowl 2023...")
    t0 = time.perf_counter()
    DATA = NFLData(DATA_DIR, CACHE_DIR)
    c = DATA.meta()["counts"]
    print(
        f"  pronto em {time.perf_counter() - t0:.1f}s — "
        f"{c['games']} jogos, {c['plays']} jogadas, {c['players']} jogadores"
    )

    if not (APP_DIR / "index.html").is_file():
        print(f"[aviso] {APP_DIR / 'index.html'} nao existe; a API funciona, a UI nao.")

    httpd = Server((args.host, args.port), Handler)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"\nservindo em {url}")
    if args.host == "0.0.0.0":
        print("[aviso] escutando em todas as interfaces, sem autenticacao. Use so em rede confiavel.")
    print("ctrl+c para parar\n")
    # O socket ja esta escutando: o app atende enquanto o cache aquece.
    CACHE.aquecer(tarefas_de_aquecimento(), log=lambda m: print(m, flush=True))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando...")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
