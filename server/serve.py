"""
Servidor local do app NFL Games.

Serve a UI estatica de app/ e a API JSON /api/* sobre os dados do nflverse
(temporadas de 2021 em diante), baixados e montados em dados/ por etl/fontes.py,
etl/montar.py e etl/ratings.py. So depende da stdlib + pandas/numpy.

Na subida, busca os dados novos (so o que mudou); com copia local, sobe na hora
e atualiza em segundo plano. Uma vez por dia, atualiza de novo e troca os dados
sem reiniciar. Sem internet, segue com a ultima copia.

Uso:
    python server/serve.py                 # http://127.0.0.1:8000
    python server/serve.py --port 9000
    python server/serve.py --offline       # usa so a copia local (testes, medicoes)
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

import fontes  # noqa: E402
import montar  # noqa: E402
from data_layer import NFLData  # noqa: E402
from response_cache import CacheDeRespostas, Resposta, serializar  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# NFL_APP e NFL_DADOS: outras pastas para a interface e os dados. O executável
# (rodar.py empacotado) usa a interface de dentro dele e os dados ao lado do
# .exe; os testes da subida sem dados usam uma pasta vazia.
APP_DIR = Path(os.environ.get("NFL_APP") or ROOT / "app")
DADOS_DIR = Path(os.environ.get("NFL_DADOS") or fontes.DADOS)

GZIP_MIN_BYTES = 2048
# Os modulos ES (app/js/*.js) so carregam com tipo JavaScript. No Windows o
# mimetypes le o registro, que em algumas maquinas mapeia .js para text/plain.
mimetypes.add_type("text/javascript", ".js")
# Os dados em uso. A atualizacao diaria troca a referencia inteira de uma vez;
# cada requisicao pega a sua no inicio e termina com ela.
DATA: NFLData | None = None
# Respostas prontas da API; limpas quando os dados sao trocados.
CACHE = CacheDeRespostas()
INTERVALO_ATUALIZACAO_S = 24 * 3600

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
    geram variacoes e nao conseguem encher o cache. `cache=False` para as
    respostas que dependem do relogio (o status "a jogar" dos jogos).
    """

    def __init__(self):
        self.routes: list[tuple[re.Pattern, callable, tuple[str, ...], bool]] = []

    def get(self, pattern: str, params: tuple[str, ...] = (), cache: bool = True):
        def deco(fn):
            self.routes.append((re.compile(f"^{pattern}$"), fn, tuple(sorted(params)), cache))
            return fn

        return deco

    def match(self, path: str):
        for pattern, fn, params, cache in self.routes:
            m = pattern.match(path)
            if m:
                return fn, m.groupdict(), params, cache
        return None, None, (), True


router = Router()


def chave_cache(path: str, query: dict, conhecidos: tuple[str, ...]) -> str:
    """Caminho + parametros conhecidos (1o valor, nao vazios), em ordem alfabetica."""
    pares = [(k, query[k][0]) for k in conhecidos if query.get(k) and query[k][0] != ""]
    return path + ("?" + urlencode(pares) if pares else "")


def _chave(dados: NFLData, path: str, query: dict, conhecidos: tuple[str, ...]) -> str:
    """Chave no cache: a versao dos dados + a chave da URL. Uma requisicao que pegou
    os dados antigos pouco antes da troca nunca grava nem le a resposta dos novos."""
    return f"v{dados.versao} {chave_cache(path, query, conhecidos)}"


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
# endpoints: cada um recebe os dados da requisicao (d), a query e o caminho
# --------------------------------------------------------------------------- #
ID_JOGADOR = r"(?P<pid>[0-9A-Za-z-]{1,20})"


def _temporada(d: NFLData, q: dict) -> int | None:
    ano = _int_param(q, "season")
    if ano is not None and ano not in d.temporadas:
        raise ApiError(404, f"temporada {ano} indisponivel (ha {min(d.temporadas)} a {max(d.temporadas)})")
    return ano


@router.get(r"/api/meta")
def api_meta(d, _q, _p):
    return d.meta()


@router.get(r"/api/games", params=("season", "week", "date"), cache=False)
def api_games(d, q, _p):
    return d.games_list(season=_temporada(d, q), week=_int_param(q, "week"), date=_str_param(q, "date"))


@router.get(r"/api/games/(?P<game_id>\d+)")
def api_game(d, _q, p):
    game = d.game(int(p["game_id"]))
    if game is None:
        raise ApiError(404, f"jogo {p['game_id']} nao encontrado")
    return game


@router.get(r"/api/games/(?P<game_id>\d+)/plays", params=("quarter", "team"))
def api_plays(d, q, p):
    return d.game_plays(int(p["game_id"]), quarter=_int_param(q, "quarter"), team=_str_param(q, "team"))


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)")
def api_play(d, _q, p):
    play = d.play(int(p["game_id"]), int(p["play_id"]))
    if play is None:
        raise ApiError(404, "jogada nao encontrada")
    return play


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)/tracking")
def api_tracking(d, _q, p):
    tr = d.play_tracking(int(p["game_id"]), int(p["play_id"]))
    if tr is None:
        raise ApiError(404, "formacao indisponivel para esta jogada")
    return tr


@router.get(r"/api/games/(?P<game_id>\d+)/plays/(?P<play_id>\d+)/formation")
def api_formation(d, _q, p):
    f = d.snap_formation(int(p["game_id"]), int(p["play_id"]))
    if f is None:
        raise ApiError(404, "formacao indisponivel para esta jogada")
    return f


@router.get(r"/api/games/(?P<game_id>\d+)/broadcast")
def api_broadcast(d, _q, p):
    bc = d.broadcast(int(p["game_id"]))
    if bc is None:
        raise ApiError(404, "jogo nao encontrado ou ainda sem jogadas")
    return bc


@router.get(r"/api/players", params=("season", "q", "position", "role", "team", "rated", "limit"))
def api_players(d, q, _p):
    return d.players_list(
        season=_temporada(d, q),
        q=_str_param(q, "q"),
        position=_str_param(q, "position"),
        role=_str_param(q, "role"),
        team=_str_param(q, "team"),
        rated_only=_str_param(q, "rated", "1") not in ("0", "false"),
        limit=min(_int_param(q, "limit", 40), 300),
    )


@router.get(r"/api/players/" + ID_JOGADOR, params=("season",))
def api_player(d, q, p):
    prof = d.player(p["pid"], season=_temporada(d, q))
    if prof is None:
        raise ApiError(404, "jogador sem dados na temporada")
    return prof


@router.get(r"/api/compare", params=("season", "a", "b"))
def api_compare(d, q, _p):
    a, b = _str_param(q, "a"), _str_param(q, "b")
    if not a or not b:
        raise ApiError(400, "informe os parametros 'a' e 'b' com os ids dos jogadores")
    cmp = d.compare(a, b, season=_temporada(d, q))
    if cmp is None:
        raise ApiError(404, "um dos jogadores nao tem dados na temporada")
    return cmp


@router.get(r"/api/leaders", params=("season", "metric", "role", "limit"))
def api_leaders(d, q, _p):
    metric = _str_param(q, "metric")
    if not metric:
        raise ApiError(400, "informe o parametro 'metric'")
    return d.leaders(metric, role=_str_param(q, "role"), limit=min(_int_param(q, "limit", 10), 100),
                     season=_temporada(d, q))


@router.get(r"/api/news", params=("season", "week"))
def api_news(d, q, _p):
    return d.news(season=_temporada(d, q), week=_int_param(q, "week"))


@router.get(r"/api/summary", params=("season",))
def api_summary(d, q, _p):
    return d.summary(season=_temporada(d, q))


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
        fn, params, conhecidos, cacheavel = router.match(path)
        if fn is None:
            raise ApiError(404, f"rota desconhecida: {path}")
        if not _vagas.acquire(blocking=False):
            raise ApiError(503, "servidor ocupado, tente novamente", {"Retry-After": "2"})
        try:
            if _ATRASO_TESTE_S:
                time.sleep(_ATRASO_TESTE_S)
            dados = DATA        # a referencia desta requisicao, mesmo que troquem no meio
            t0 = time.perf_counter()
            # Parametro invalido ou recurso inexistente viram ApiError dentro de
            # fn: atravessam o cache sem ser guardados.
            if cacheavel:
                resp, hit = CACHE.get_or_build(_chave(dados, path, query, conhecidos),
                                               lambda: fn(dados, query, params))
            else:
                resp, hit = serializar(fn(dados, query, params)), False
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
def tarefas_de_aquecimento(dados: NFLData):
    """
    (chave, construtor) das respostas que todo usuario acaba pedindo, na ordem
    em que a tela as pede: meta, jogadores e, jogo a jogo (a semana atual
    primeiro, depois da mais recente para a mais antiga), detalhe, jogadas e
    comentarista dos jogos ja disputados da temporada atual. As outras
    temporadas: sob demanda. A lista de jogos nao entra: ela nao e guardada.
    """
    semana = dados.meta()["currentWeek"]
    urls = ["/api/meta", "/api/players?limit=60", "/api/summary", f"/api/news?week={semana}", "/api/news"]
    j = dados.jogos[(dados.jogos["season"] == dados.atual) & dados.jogos["home_score"].notna()]
    j = j.assign(_outra=(j["week"] != semana)).sort_values(["_outra", "week", "gameId"],
                                                          ascending=[True, False, True])
    for g in j["gameId"]:
        urls += [f"/api/games/{g}", f"/api/games/{g}/plays", f"/api/games/{g}/broadcast"]
    for url in urls:
        u = urlparse(url)
        query = parse_qs(u.query)
        fn, params, conhecidos, _c = router.match(u.path)
        yield _chave(dados, u.path, query, conhecidos), (lambda fn=fn, q=query, p=params: fn(dados, q, p))


def _log(m: str) -> None:
    print(m, flush=True)


def trocar_dados(novo: NFLData, log=_log) -> None:
    """Troca os dados em uso, limpa as respostas antigas e reaquece (7.3)."""
    global DATA
    DATA = novo
    CACHE.limpar()
    CACHE.aquecer(tarefas_de_aquecimento(novo), log=log)


def atualizar(offline: bool = False, log=_log) -> bool:
    """
    Um ciclo de atualizacao: sincroniza, monta e, se algo mudou, carrega os
    dados novos e troca. Nunca derruba o servidor: sem internet ou com erro,
    loga e segue com a copia em uso (7.5). Devolve True se trocou os dados.
    """
    try:
        sinc, mont = montar.sincronizar_e_montar(DADOS_DIR, progresso=log,
                                                 rede=fontes.SemAcesso() if offline else None)
    except Exception as e:  # noqa: BLE001
        log(f"[aviso] atualizacao falhou ({e!r}); seguindo com os dados em uso")
        return False
    if not (sinc.mudou or mont.temporadas or mont.globais):
        if not sinc.sem_rede:
            # nada novo, mas a data da ultima atualizacao (/api/meta) mudou
            CACHE.limpar()
            CACHE.aquecer(tarefas_de_aquecimento(DATA), log=log)
        return False
    log(f"atualizacao: {len(sinc.baixados)} arquivos novos, temporadas {mont.temporadas}; recarregando...")
    try:
        novo = NFLData(DADOS_DIR)
    except Exception as e:  # noqa: BLE001
        log(f"[aviso] dados novos ilegiveis ({e!r}); seguindo com os dados em uso")
        return False
    trocar_dados(novo, log=log)
    log("atualizacao: dados novos em uso")
    return True


def ciclo_de_atualizacao(parar: threading.Event, intervalo_s: float, primeira_espera_s: float,
                         offline: bool = False, log=_log, passo=None) -> threading.Thread:
    """
    Atualiza depois de `primeira_espera_s` e, a partir dai, a cada `intervalo_s`
    (7.2). `passo` substitui atualizar() nos testes.
    """
    passo = passo or (lambda: atualizar(offline=offline, log=log))

    def rodar():
        espera = primeira_espera_s
        while not parar.wait(espera):
            passo()
            espera = intervalo_s

    t = threading.Thread(target=rodar, name="atualizacao", daemon=True)
    t.start()
    return t


def _tem_copia_montada() -> bool:
    return (DADOS_DIR / "jogos.npz").exists() and any((DADOS_DIR / "temporadas").glob("*/jogadores.npz"))


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-pendentes", type=int, default=MAX_PENDENTES,
                    help="requisicoes /api simultaneas antes de responder 503 (padrao: %(default)s)")
    ap.add_argument("--offline", action="store_true",
                    help="nao acessa a internet: usa so a copia local (testes e medicoes)")
    return ap


def main() -> int:
    args = parser().parse_args()

    global DATA, _vagas
    _vagas = threading.BoundedSemaphore(args.max_pendentes)
    intervalo = float(os.environ.get("NFL_INTERVALO_ATUALIZACAO_S") or INTERVALO_ATUALIZACAO_S)
    rede = fontes.SemAcesso() if args.offline else None

    ja_atualizou = False
    if not _tem_copia_montada():
        # Primeira subida: baixa e monta tudo antes de servir, mostrando o progresso.
        print("primeira carga: baixando e montando os dados do nflverse (2021 em diante)...", flush=True)
        try:
            montar.sincronizar_e_montar(DADOS_DIR, progresso=_log, rede=rede)
        except fontes.SemDados as e:
            print(f"\n[erro] Sem dados para subir o app: {e}\n"
                  "       Conecte-se a internet e rode de novo: a primeira carga baixa os dados "
                  "do nflverse (~330 MB, alguns minutos).", flush=True)
            return 1
        ja_atualizou = True

    print("carregando os dados...", flush=True)
    t0 = time.perf_counter()
    try:
        DATA = NFLData(DADOS_DIR)
    except (FileNotFoundError, OSError, ValueError, KeyError) as e:
        print(f"[erro] dados locais ilegiveis ({e!r}). Apague a pasta {DADOS_DIR} e rode de novo.", flush=True)
        return 1
    c = DATA.meta()["counts"]
    print(f"  pronto em {time.perf_counter() - t0:.1f}s: temporadas {min(DATA.temporadas)}-{DATA.atual}, "
          f"{c['played']} jogos disputados e {c['plays']} jogadas em {DATA.atual}", flush=True)

    if not (APP_DIR / "index.html").is_file():
        print(f"[aviso] {APP_DIR / 'index.html'} nao existe; a API funciona, a UI nao.")

    httpd = Server((args.host, args.port), Handler)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"\nservindo em {url}")
    if args.host == "0.0.0.0":
        print("[aviso] escutando em todas as interfaces, sem autenticacao. Use so em rede confiavel.")
    print("ctrl+c para parar\n", flush=True)
    # O socket ja esta escutando: o app atende enquanto o cache aquece.
    CACHE.aquecer(tarefas_de_aquecimento(DATA), log=_log)
    # Com copia local, a busca por dados novos (7.1) roda em 2o plano logo apos a subida.
    parar = threading.Event()
    ciclo_de_atualizacao(parar, intervalo, primeira_espera_s=intervalo if ja_atualizou else 1.0,
                         offline=args.offline)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando...")
        parar.set()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
