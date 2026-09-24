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
import json
import mimetypes
import re
import sys
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).parent))

from data_layer import NFLData  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "nfl-big-data-bowl-regional-event-data-main" / "data"
CACHE_DIR = ROOT / "cache"

GZIP_MIN_BYTES = 2048
DATA: NFLData | None = None


# --------------------------------------------------------------------------- #
# roteador minimo
# --------------------------------------------------------------------------- #
class Router:
    def __init__(self):
        self.routes: list[tuple[re.Pattern, callable]] = []

    def get(self, pattern: str):
        def deco(fn):
            self.routes.append((re.compile(f"^{pattern}$"), fn))
            return fn

        return deco

    def match(self, path: str):
        for pattern, fn in self.routes:
            m = pattern.match(path)
            if m:
                return fn, m.groupdict()
        return None, None


router = Router()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


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


@router.get(r"/api/games")
def api_games(q, _p):
    return DATA.games_list(week=_int_param(q, "week"), date=_str_param(q, "date"))


@router.get(r"/api/games/(?P<game_id>\d+)")
def api_game(_q, p):
    game = DATA.game(int(p["game_id"]))
    if game is None:
        raise ApiError(404, f"jogo {p['game_id']} nao encontrado")
    return game


@router.get(r"/api/games/(?P<game_id>\d+)/plays")
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


@router.get(r"/api/players")
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


@router.get(r"/api/compare")
def api_compare(q, _p):
    a, b = _int_param(q, "a"), _int_param(q, "b")
    if a is None or b is None:
        raise ApiError(400, "informe os parametros 'a' e 'b' com os nflId")
    cmp = DATA.compare(a, b)
    if cmp is None:
        raise ApiError(404, "um dos jogadores nao tem dados suficientes")
    return cmp


@router.get(r"/api/leaders")
def api_leaders(q, _p):
    metric = _str_param(q, "metric")
    if not metric:
        raise ApiError(400, "informe o parametro 'metric'")
    return DATA.leaders(metric, role=_str_param(q, "role"), limit=min(_int_param(q, "limit", 10), 100))


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
            self._send_json({"error": e.message}, status=e.status)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "erro interno no servidor"}, status=500)

    def _handle_api(self, path: str, query: dict):
        fn, params = router.match(path)
        if fn is None:
            raise ApiError(404, f"rota desconhecida: {path}")
        t0 = time.perf_counter()
        payload = fn(query, params)
        ms = (time.perf_counter() - t0) * 1000
        self._send_json(payload, extra_headers={"X-Query-Time": f"{ms:.0f}ms"})

    def _handle_static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (APP_DIR / rel).resolve()
        # Impede escapar da pasta app/ via ../
        if not str(target).startswith(str(APP_DIR.resolve())):
            self._send_bytes(b"forbidden", "text/plain", HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send_bytes(b"nao encontrado", "text/plain", HTTPStatus.NOT_FOUND)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send_bytes(target.read_bytes(), ctype)

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
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    global DATA
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

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"\nservindo em {url}")
    if args.host == "0.0.0.0":
        print("[aviso] escutando em todas as interfaces, sem autenticacao. Use so em rede confiavel.")
    print("ctrl+c para parar\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando...")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
