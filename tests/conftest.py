import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from servidor_local import servidor as _servidor  # noqa: E402


@pytest.fixture(scope="session")
def servidor_real():
    """Servidor real numa porta livre, compartilhado pela sessao de testes."""
    with _servidor() as srv:
        yield srv


@pytest.fixture(scope="session")
def servidor(servidor_real):
    # Apelido. Os testes de interface redefinem `servidor` parametrizado (PC e site) sobre
    # o servidor_real: se dependessem de uma fixture de mesmo nome, o pytest recriaria o
    # servidor a cada troca de parâmetro (~20 s cada).
    return servidor_real


def http_get(url: str, headers: dict | None = None):
    """(status, cabecalhos, corpo) sem lancar em 4xx/5xx."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def http_json(url: str):
    status, _h, body = http_get(url)
    return status, json.loads(body)


# ------------------------------------------------------------ site-publico
# O site exportado (tools/exportar.py) para os testes da fonte estática e da bateria
# de interface na fonte "estatico". Exportar tudo leva alguns minutos; o resultado fica
# em build/site-testes/ e é reaproveitado enquanto os dados e o código não mudarem.
SITE_TESTES = ROOT / "build" / "site-testes"


def _chave_do_site() -> str:
    import hashlib
    h = hashlib.sha256()
    arquivos = [ROOT / "dados" / "manifest.json", ROOT / "tools" / "exportar.py", ROOT / "etl" / "ratings.py"]
    arquivos += sorted((ROOT / "server").glob("*.py"))       # app/ fica de fora: é copiado de novo a cada sessão
    for p in arquivos:
        h.update(str(p.relative_to(ROOT)).encode())
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()


@pytest.fixture(scope="session")
def site_exportado() -> Path:
    import shutil
    import exportar
    pasta, chave_arq = SITE_TESTES / "NFL-Games", SITE_TESTES / "chave.txt"
    chave = _chave_do_site()
    if not (chave_arq.exists() and chave_arq.read_text() == chave and (pasta / "api" / "versao.json").exists()):
        if pasta.exists():
            shutil.rmtree(pasta)
        exportar.exportar(ROOT / "dados", pasta, processos=4)
        chave_arq.write_text(chave)
    else:
        exportar.copiar_interface(pasta)                     # a interface atual sobre os dados já exportados
    return pasta


@pytest.fixture(scope="session")
def site(site_exportado):
    """URL do site exportado, servido no subcaminho /NFL-Games/ (como no GitHub Pages)."""
    from servidor_estatico import site_local
    with site_local(site_exportado) as url:
        yield url


# ------------------------------------ site-publico, tarefa 5: UI nas duas fontes
# Nos testes de interface, a fixture `servidor` vira um Alvo parametrizado: a página
# abre no servidor (PC) ou no site exportado (Pages); `api` é sempre o servidor real,
# a referência dos dados. Testes marcados so_servidor(motivo) pulam no site.
import re  # noqa: E402
from typing import NamedTuple  # noqa: E402

FONTES = ["servidor", "estatico"]


class Alvo(NamedTuple):
    url: str          # base da página
    api: str          # servidor real, para os dados de referência
    fonte: str        # "servidor" ou "estatico"


def alvo_de(request, servidor_real) -> Alvo:
    if request.param == "estatico":
        marca = request.node.get_closest_marker("so_servidor")
        if marca:
            pytest.skip("só no app do PC: " + (marca.args[0] if marca.args else ""))
        return Alvo(request.getfixturevalue("site"), servidor_real.url, "estatico")
    return Alvo(servidor_real.url, servidor_real.url, "servidor")


def _corpo(resposta):
    return resposta if isinstance(resposta, tuple) else (200, resposta)


def _responder(resposta):
    status, corpo = _corpo(resposta)
    return lambda r: r.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))


def _no_site(padrao: str):
    """Rota da API (glob como nos route() de hoje) -> (regex do arquivo no site, id do jogo, chave no bundle)."""
    caminho, _, query = padrao.lstrip("*").partition("?")
    ano = (re.search(r"season=(\d+)", query) or [None, r"\d+"])[1]
    semana = (re.search(r"week=(\d+)", query) or [None, None])[1]
    m = re.fullmatch(r"/api/games/(\d+)(/plays)?", caminho)
    if m:
        return re.compile(rf"/api/[^/]+/jogos/{m[1]}\.json\.gz$"), m[1], "plays" if m[2] else "game"
    if caminho == "/api/games":
        return re.compile(rf"/api/[^/]+/{ano}/semanas/{semana or r'[0-9]+'}\.json$"), None, None
    if caminho == "/api/news":
        fim = rf"/noticias/{semana}\.json$" if semana else r"/noticias(/[0-9]+)?\.json$"
        return re.compile(rf"/api/[^/]+/{ano}{fim}"), None, None
    if caminho == "/api/players":
        return re.compile(rf"/api/[^/]+/{ano}/jogadores\.json$"), None, None
    raise ValueError(f"rota sem arquivo equivalente no site: {padrao}")


def simular_api(pg, alvo: Alvo, rotas: dict) -> None:
    """Simula respostas da API como a interface as pede. Valor: o corpo JSON (200) ou (status, corpo).
    No site, a rota vira o arquivo equivalente; nos jogos, as sobrescritas de game/plays entram
    no bundle real (gzip), que é baixado do próprio site."""
    import gzip
    if alvo.fonte == "servidor":
        for padrao, resposta in rotas.items():
            pg.route(padrao, _responder(resposta))
        return
    bundles: dict[str, dict] = {}
    for padrao, resposta in rotas.items():
        regex, jogo, chave = _no_site(padrao)
        if jogo is None:
            pg.route(regex, _responder(resposta))
        else:
            bundles.setdefault(jogo, {"regex": regex, "trocas": {}})["trocas"][chave] = resposta

    def trocar(trocas):
        def handler(route):
            erros = [r for r in trocas.values() if _corpo(r)[0] != 200]
            if erros:
                return _responder(erros[0])(route)
            b = json.loads(gzip.decompress(route.fetch().body()))
            b.update({k: _corpo(v)[1] for k, v in trocas.items()})
            route.fulfill(status=200, content_type="application/gzip",
                          body=gzip.compress(json.dumps(b).encode("utf-8")))
        return handler

    for jogo in bundles.values():
        pg.route(jogo["regex"], trocar(jogo["trocas"]))
