"""
Spec site-publico, tarefa 3: a fonte estática (app/js/fonte-estatica.js), que a
interface usa no site publicado, contra o servidor.

O site exportado é servido no subcaminho /NFL-Games/, como no GitHub Pages. Cada teste
chama a API da própria página (o mesmo objeto `api` que as telas usam) e compara com
o servidor real (mesma cópia dos dados) ou, quando o relógio importa, com a NFLData
criada na mesma data que o relógio do Playwright.
"""

import json
import sys
import urllib.parse
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from conftest import ROOT, http_json

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl"), str(ROOT / "tools")]
DADOS = ROOT / "dados"
pytestmark = pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")
playwright = pytest.importorskip("playwright.sync_api")

import data_layer  # noqa: E402

NY = ZoneInfo("America/New_York")
MSG_GZ = "Este navegador não consegue abrir os dados do jogo. Atualize o navegador (no iPhone, iOS 16.4 ou mais novo)."
MSG_ABERTURA = "Não foi possível carregar os dados. Verifique a conexão e tente de novo."
CHAMAR = """async (expr) => {
  const m = await import(new URL('js/api.js', document.baseURI).href);
  try { return { ok: await (new Function('api', 'return ' + expr))(m.api) }; }
  catch (e) { return { erro: e.message, status: e.status ?? null }; }
}"""


@pytest.fixture(scope="module")
def nfl():
    return data_layer.NFLData(DADOS)


@pytest.fixture(scope="module")
def navegador():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Edge indisponivel para o Playwright: {e}")
        yield b
        b.close()


def nova_pagina(navegador, base, hoje=None, fuso=None, init=None):
    ctx = navegador.new_context(viewport={"width": 430, "height": 860}, timezone_id=fuso)
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    pg = ctx.new_page()
    if hoje is not None:
        pg.clock.set_fixed_time(hoje)
    if init:
        pg.add_init_script(init)
    pg.goto(base + "/")
    pg.wait_for_function("document.querySelector('.screen.active')")
    return pg


@pytest.fixture
def pagina(navegador, site):
    pg = nova_pagina(navegador, site)
    yield pg
    pg.context.close()


def chamar(pg, expr):
    return pg.evaluate(CHAMAR, expr)


def norm(x):
    return json.loads(json.dumps(x))


def servidor_diz(servidor, rota):
    status, corpo = http_json(servidor.url + rota)
    return {"ok": corpo} if status == 200 else {"erro": corpo["error"], "status": status}


def em_ny(dia: str, hora: time) -> datetime:
    return datetime.combine(datetime.fromisoformat(dia).date(), hora, tzinfo=NY).astimezone(timezone.utc)


def semanas(nfl, ano):
    return next(t for t in nfl.meta()["seasons"] if t["season"] == ano)["weeks"]


def com_hoje(nfl, hoje):
    nfl._hoje = hoje
    return nfl


# ----------------------------------------------------------- relógio (2.4, 2.5)
def test_meta_semana_atual(navegador, site, nfl):
    ws = semanas(nfl, 2026)
    quinta = ws[2]["dates"][0]
    momentos = [em_ny(ws[0]["dates"][0], time(12)) - timedelta(days=30),      # antes do 1º jogo
                em_ny(quinta, time(21)),                                        # quinta de rodada, 21h em NY
                em_ny(quinta, time(12)) - timedelta(days=2)]                    # a terça antes
    for h in momentos:
        pg = nova_pagina(navegador, site, hoje=h)
        m = chamar(pg, "api.meta()")["ok"]
        pg.context.close()
        ref = com_hoje(nfl, h).meta()
        assert m["currentWeek"] == ref["currentWeek"], h
        assert [t["currentWeek"] for t in m["seasons"]] == [t["currentWeek"] for t in ref["seasons"]], h


def _jogo_sem_placar(nfl):
    com_hoje(nfl, None)
    for w in semanas(nfl, 2026):
        for g in nfl.games_list(season=2026, week=w["week"]):
            if g["status"] == "agendado" and g["kickoffUtc"]:
                return w["week"], g
    pytest.skip("nenhum jogo a jogar em 2026 nesta cópia dos dados")


def test_status_antes_durante_depois(navegador, site, nfl):
    semana, g = _jogo_sem_placar(nfl)
    inicio = datetime.fromisoformat(g["kickoffUtc"].replace("Z", "+00:00"))
    for h in (inicio - timedelta(hours=1), inicio + timedelta(hours=1)):
        pg = nova_pagina(navegador, site, hoje=h)
        lista = chamar(pg, f"api.games(2026, {semana})")["ok"]
        jogo = chamar(pg, f"api.game({g['gameId']})")["ok"]
        pg.context.close()
        ref = com_hoje(nfl, h)
        assert [x["status"] for x in lista] == [x["status"] for x in ref.games_list(season=2026, week=semana)], h
        assert jogo["status"] == ref.game(g["gameId"])["status"], h
    com_hoje(nfl, None)


def test_fuso_do_aparelho_nao_muda_semana_nem_status(navegador, site, nfl):
    """Foco de revisão 2: celular em Brasília, 23h30 de uma quinta de rodada (22h30 em NY)."""
    ws = semanas(nfl, 2026)
    quinta = ws[2]["dates"][0]
    h = datetime.combine(datetime.fromisoformat(quinta).date(), time(23, 30),
                         tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(timezone.utc)
    pg = nova_pagina(navegador, site, hoje=h, fuso="America/Sao_Paulo")
    m = chamar(pg, "api.meta()")["ok"]
    lista = chamar(pg, f"api.games(2026, {ws[2]['week']})")["ok"]
    pg.context.close()
    ref = com_hoje(nfl, h)
    assert m["currentWeek"] == ref.meta()["currentWeek"]
    assert [x["status"] for x in lista] == [x["status"] for x in ref.games_list(season=2026, week=ws[2]["week"])]
    com_hoje(nfl, None)


# -------------------------------------------------------------- jogadores (2.2)
BUSCAS = [{"q": "ma", "limit": 8}, {"q": "ja'marr"}, {"q": "JOSÉ"}, {"q": "é"}, {"q": "smith "},
          {"position": "QB", "limit": 60}, {"position": "WR,TE", "q": "a", "limit": 60},
          {"role": "EDGE", "limit": 60}, {"team": "kc"}, {"rated": 0, "limit": 300}, {"limit": 500}]


@pytest.mark.parametrize("ano", [2021, 2025])
def test_busca_igual_ao_servidor(pagina, servidor, ano):
    """Foco de revisão 3: acento, apóstrofo, maiúsculas e espaço no fim."""
    for f in BUSCAS:
        estatico = chamar(pagina, f"api.players({ano}, {json.dumps(f)})")["ok"]
        ref = servidor_diz(servidor, "/api/players?" + urllib.parse.urlencode({"season": ano, **f}))["ok"]
        assert [p["nflId"] for p in estatico] == [p["nflId"] for p in ref], f
        assert estatico == ref, f


def test_comparacao_igual_ao_servidor(pagina, servidor):
    qbs = servidor_diz(servidor, "/api/players?season=2021&role=QB&limit=2")["ok"]
    wr = servidor_diz(servidor, "/api/players?season=2021&role=WRTE&limit=1")["ok"][0]
    casos = [(qbs[0]["nflId"], qbs[1]["nflId"]), (qbs[0]["nflId"], wr["nflId"]), (qbs[0]["nflId"], "00-0000000")]
    for a, b in casos:
        assert chamar(pagina, f"api.compare('{a}', '{b}', 2021)") == \
            servidor_diz(servidor, f"/api/compare?season=2021&a={a}&b={b}"), (a, b)
    assert chamar(pagina, f"api.compare('{qbs[0]['nflId']}', '', 2021)") == \
        servidor_diz(servidor, f"/api/compare?season=2021&a={qbs[0]['nflId']}")


# ------------------------------------------------------------ erros (2.6, 4.x)
def test_404_iguais_ao_servidor(pagina, servidor, nfl):
    """Foco de revisão 4: jogo, lance, jogador e temporada que não existem."""
    _, futuro = _jogo_sem_placar(nfl)
    jogo = nfl.games_list(season=2021, week=1)[0]["gameId"]
    casos = [("api.game(123)", "/api/games/123"),
             (f"api.tracking({jogo}, 999999)", f"/api/games/{jogo}/plays/999999/tracking"),
             ("api.player('00-0000000', 2021)", "/api/players/00-0000000?season=2021"),
             ("api.games(2019, 1)", "/api/games?season=2019&week=1"),
             ("api.players(2019, {})", "/api/players?season=2019"),
             (f"api.broadcast({futuro['gameId']})", f"/api/games/{futuro['gameId']}/broadcast"),
             ("api.plays(123)", "/api/games/123/plays")]
    for expr, rota in casos:
        assert chamar(pagina, expr) == servidor_diz(servidor, rota), expr


def test_jogo_futuro_igual_ao_servidor(pagina, servidor, nfl):
    """Foco de revisão 5."""
    _, futuro = _jogo_sem_placar(nfl)
    gid = futuro["gameId"]
    for expr, rota in ((f"api.game({gid})", f"/api/games/{gid}"), (f"api.plays({gid})", f"/api/games/{gid}/plays"),
                       (f"api.broadcast({gid})", f"/api/games/{gid}/broadcast")):
        assert chamar(pagina, expr) == servidor_diz(servidor, rota), expr


# ----------------------------------------------------------------- jogos (2.1)
def test_jogo_e_pranchetas_iguais(pagina, servidor, nfl):
    pedidos = []
    pagina.on("request", lambda r: pedidos.append(r.url))
    for g in nfl.games_list(season=2025, week=1)[:3]:
        gid = g["gameId"]
        for expr, rota in ((f"api.game({gid})", f"/api/games/{gid}"), (f"api.plays({gid})", f"/api/games/{gid}/plays"),
                           (f"api.broadcast({gid})", f"/api/games/{gid}/broadcast")):
            assert chamar(pagina, expr) == servidor_diz(servidor, rota), expr
        lances = [p["playId"] for p in nfl.game_plays(gid)][:5]
        for pid in lances:
            assert chamar(pagina, f"api.tracking({gid}, {pid})") == \
                servidor_diz(servidor, f"/api/games/{gid}/plays/{pid}/tracking"), (gid, pid)
        assert sum(f"/jogos/{gid}.pranchetas.json.gz" in u for u in pedidos) == 1, gid


def test_noticias_resumo_e_perfil(pagina, servidor):
    for expr, rota in (("api.news(2021, 1)", "/api/news?season=2021&week=1"), ("api.news(2021)", "/api/news?season=2021"),
                       ("api.summary(2025)", "/api/summary?season=2025"), ("api.news(2021, 99)", "/api/news?season=2021&week=99"),
                       ("api.games(2021, 99)", "/api/games?season=2021&week=99")):
        assert chamar(pagina, expr) == servidor_diz(servidor, rota), expr
    pid = servidor_diz(servidor, "/api/players?season=2021&limit=1")["ok"][0]["nflId"]
    assert chamar(pagina, f"api.player('{pid}', 2021)") == servidor_diz(servidor, f"/api/players/{pid}?season=2021")


def test_gz_com_content_encoding(navegador, site_exportado, servidor, nfl):
    """Foco de revisão 1: servidor que entrega o .gz com Content-Encoding: gzip."""
    from servidor_estatico import site_local
    gid = nfl.games_list(season=2025, week=1)[0]["gameId"]
    with site_local(site_exportado, gz_como_encoding=True) as url:
        pg = nova_pagina(navegador, url)
        assert chamar(pg, f"api.plays({gid})") == servidor_diz(servidor, f"/api/games/{gid}/plays")
        pg.context.close()


def test_sem_decompressionstream(navegador, site, servidor, nfl):
    """4.2: sem DecompressionStream, o jogo avisa; o resto funciona."""
    gid = nfl.games_list(season=2025, week=1)[0]["gameId"]
    pg = nova_pagina(navegador, site, init="delete window.DecompressionStream;")
    assert chamar(pg, f"api.plays({gid})")["erro"] == MSG_GZ
    assert chamar(pg, "api.meta()")["ok"]["season"] == servidor_diz(servidor, "/api/meta")["ok"]["season"]
    assert len(chamar(pg, "api.players(2025, {limit: 5})")["ok"]) == 5
    pg.context.close()


# ------------------------------------------------------------- site (4.3, seg. 4)
def test_caminhos_relativos(navegador, site, nfl):
    """Nada fora do subcaminho /NFL-Games/, exceto as fontes do Google e a ESPN."""
    gid = nfl.games_list(season=2025, week=1)[0]["gameId"]
    ctx = navegador.new_context(viewport={"width": 430, "height": 860})
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    pg = ctx.new_page()
    pedidos = []
    pg.on("request", lambda r: pedidos.append(r.url))
    pg.goto(site + "/")
    pg.wait_for_function("document.querySelector('#jogosLista .match')")
    pg.goto(site + f"/?screen=jogo&season=2025&week=1&game={gid}")
    pg.wait_for_function("document.querySelector('#jogoCab .jogo-cab')")
    ctx.close()
    fora = [u for u in pedidos if not u.startswith(site + "/")
            and not u.startswith(("https://fonts.googleapis.com/", "https://fonts.gstatic.com/", "https://site.api.espn.com/"))]
    assert fora == []


def test_mensagem_de_abertura(navegador, site):
    ctx = navegador.new_context(viewport={"width": 430, "height": 860})
    pg = ctx.new_page()
    pg.route("**/api/versao.json", lambda r: r.fulfill(status=404, body=""))
    pg.goto(site + "/")
    pg.wait_for_function("document.querySelector('#inicio .state')")
    texto = pg.inner_text("#inicio")
    ctx.close()
    assert MSG_ABERTURA in texto
    assert "rodar.py" not in texto and "NFL-Games" not in texto


# ------------------------------------------------ tarefa 4: troca de versão (4.4)
def test_versao_nova_recarrega_no_mesmo_lugar(navegador, site_exportado, tmp_path):
    """Publicação nova no meio do uso: a sessão aberta recarrega na versão nova, sem misturar dias."""
    import os
    import shutil
    import exportar
    from servidor_estatico import site_local
    copia = tmp_path / "NFL-Games"
    shutil.copytree(site_exportado, copia, copy_function=os.link)      # links: rápido, e não mexe no original
    v1 = json.loads((copia / "api" / "versao.json").read_text(encoding="utf-8"))["versao"]
    v2 = "29990101T0000"
    with site_local(copia) as url:
        pg = nova_pagina(navegador, url)
        pg.goto(url + "/?season=2025&week=1")
        pg.wait_for_function("document.querySelector('#jogosLista .match')")
        for tentativa in range(50):                                     # o Pages troca o site inteiro
            try:                                                        # (no Windows, um arquivo recém-servido
                (copia / "api" / v1).rename(copia / "api" / v2)         # pode ficar aberto por um instante)
                break
            except PermissionError:
                if tentativa == 49:
                    raise
                pg.wait_for_timeout(100)
        exportar.gravar_json(copia / "api" / "versao.json", {"versao": v2})
        pedidos = []
        with pg.expect_event("load", timeout=10000):                    # recarga de verdade (não pushState)
            pg.click(".nav-item[data-go=jogadores]")                    # pede jogadores.json da versão antiga: 404
            pg.on("request", lambda r: pedidos.append(r.url))
        pg.wait_for_function("document.querySelector('#scoutBody .row-card')")
        assert "screen=jogadores" in pg.url and "season=2025" in pg.url
        dados = [u for u in pedidos if "/api/" in u and not u.endswith("versao.json")]
        assert dados and all(f"/api/{v2}/" in u for u in dados), dados
        pg.context.close()


def test_404_de_verdade_nao_recarrega(pagina):
    r = pagina.evaluate("""async () => {
        const f = await import(new URL('js/fonte-estatica.js', document.baseURI).href);
        const a = await import(new URL('js/api.js', document.baseURI).href);
        const fonte = f.fonteEstatica({ get: a.get, recarregar: () => { window.__recarregou = true; } });
        try { await fonte.player('00-0000000', 2021); return 'resolveu'; }
        catch (e) { return [e.status, e.message, window.__recarregou || false]; }
    }""")
    assert r == [404, "jogador sem dados na temporada", False]


# ------------------------------------------------------ revisão final (2.5)
FORMATO_US = """(() => {
  Object.defineProperty(Intl.DateTimeFormat.prototype, 'format', { get() { return (d) => {
    const p = this.formatToParts(d); const v = (t) => p.find((x) => x.type === t).value;
    return v('month') + '/' + v('day') + '/' + v('year'); }; } }); })();"""


def test_semana_atual_nao_depende_do_formato_de_data(navegador, site, nfl):
    """O en-CA já mudou de AAAA-MM-DD para M/D/AAAA numa versão do Chrome: a semana não pode mudar junto.
    Relógio real: o relógio falso do Playwright troca o Intl.DateTimeFormat por um objeto dele."""
    pg = nova_pagina(navegador, site, init=FORMATO_US)
    assert pg.evaluate("new Intl.DateTimeFormat('en-CA').format(0).includes('/')"), "o formato não foi trocado"
    m = chamar(pg, "api.meta()")["ok"]
    pg.context.close()
    ref = com_hoje(nfl, None).meta()
    assert m["currentWeek"] == ref["currentWeek"]
    assert [t["currentWeek"] for t in m["seasons"]] == [t["currentWeek"] for t in ref["seasons"]]


def test_versao_instavel_nao_recarrega_em_laco(navegador, site):
    """Logo depois de um deploy, nós do CDN podem responder versões diferentes: a página
    recarrega uma vez, e não em laço (a 2ª vez seguida mostra o erro normal da tela)."""
    ctx = navegador.new_context(viewport={"width": 430, "height": 860})
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    pg = ctx.new_page()
    chamadas = {"n": 0}

    def versao(route):
        chamadas["n"] += 1
        if chamadas["n"] % 2 == 0:                      # um nó do CDN já com a versão nova (que ainda não existe)
            return route.fulfill(status=200, content_type="application/json", body='{"versao": "29990101T0000"}')
        return route.continue_()

    pg.route("**/api/versao.json", versao)
    cargas = []
    pg.on("load", lambda: cargas.append(1))
    pg.goto(site + "/?screen=jogadores&season=2021&jogador=00-0000000")    # o perfil dá 404
    pg.wait_for_timeout(4000)
    ctx.close()
    assert len(cargas) <= 2, f"{len(cargas)} cargas da página: laço de recarga"
