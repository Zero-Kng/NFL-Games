"""
Spec novo-visual: a interface (app/index.html), num Edge headless real.

Tarefa 2 (casca): identidade do rascunho, cabeçalho, moldura, movimento
reduzido, fontes externas, barra inferior, menu lateral, links antigos,
filtros de temporada e semana e configurações corrompidas.

Tarefa 3 (Início): carrossel de notícias, os dois cartões, os jogos da semana
com os estados e o placar ao vivo (os testes de cartão e ao vivo da
test_ui_dados.py, adaptados), filtro por time e erro na semana. A ESPN e a
lista de jogos são simuladas com page.route(); o relógio é o do Playwright.
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

playwright = pytest.importorskip("playwright.sync_api")

TELAS = {"inicio": "Início", "jogo": "Jogo", "jogadores": "Jogadores", "noticias": "Notícias",
         "config": "Configurações", "sobre": "Sobre os dados"}
ESPERAR = """async ([cond, limite]) => {
  const f = new Function('return (' + cond + ')');
  const t0 = performance.now();
  while (!f()) {
    if (performance.now() - t0 > limite) return -1;
    await new Promise((ok) => setTimeout(ok, 10));
  }
  return performance.now() - t0;
}"""


@pytest.fixture(scope="module")
def navegador():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Edge indisponivel para o Playwright: {e}")
        yield b
        b.close()


@pytest.fixture
def contexto(navegador):
    ctx = navegador.new_context(viewport={"width": 430, "height": 860})
    # a interface nova não depende da ESPN para a casca; qualquer chamada externa é barrada
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    yield ctx
    ctx.close()


@pytest.fixture
def pagina(contexto):
    pg = contexto.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    yield pg
    assert erros == [], f"erros de JavaScript na pagina: {erros}"


def esperar(pg, cond: str, limite_ms: int = 10000):
    ms = pg.evaluate(ESPERAR, [cond, limite_ms])
    assert ms >= 0, f"condicao nao aconteceu em {limite_ms} ms: {cond}"


def api(base, caminho):
    with urllib.request.urlopen(base + caminho) as r:
        return json.load(r)


def abrir(pg, base, query=""):
    pg.goto(base + "/" + query)
    esperar(pg, "document.querySelector('.screen.active') && document.querySelectorAll('#seasonChips .chip').length > 0"
                " || document.querySelector('.screen.active .state')")


def ir_para(pg, tela):
    if tela in ("config", "sobre"):
        if not pg.eval_on_selector("#sidebar", "e => e.classList.contains('open')"):
            pg.click("#btnMenu")
        esperar(pg, "document.getElementById('sidebar').classList.contains('open')")
        pg.click(f".side-item[data-go={tela}]")
    else:
        pg.click(f".nav-item[data-go={tela}]")
    esperar(pg, f"document.getElementById('{tela}').classList.contains('active')")


def rgb(pg, seletor, prop):
    return pg.eval_on_selector(seletor, f"e => getComputedStyle(e).{prop}")


def esperar_cor(pg, seletor, prop, valor):
    """Espera a cor final (as trocas de estado têm transição de 0,2 s)."""
    esperar(pg, f"getComputedStyle(document.querySelector({json.dumps(seletor)})).{prop} === {json.dumps(valor)}", 3000)


# ================================================================ Requisito 1
def test_ui_tokens_do_rascunho(servidor, pagina):
    """1.1: fundo, superfície e destaque vêm dos tokens do rascunho."""
    abrir(pagina, servidor.url)
    assert rgb(pagina, "body", "backgroundColor") == "rgb(3, 6, 12)"
    assert "rgb(6, 11, 20)" in rgb(pagina, ".app", "backgroundImage") + rgb(pagina, ".app", "backgroundColor")
    assert rgb(pagina, ".icon-btn", "backgroundColor") == "rgb(14, 23, 38)"                   # --surface
    esperar_cor(pagina, ".nav-item[aria-current=page]", "backgroundColor", "rgb(229, 32, 46)")  # --red
    assert "Barlow Condensed" in rgb(pagina, "#pageTitle", "fontFamily")


@pytest.mark.parametrize("tela", list(TELAS))
def test_ui_cabecalho_em_todas_as_telas(servidor, pagina, tela):
    """1.2: menu, escudo com o título da tela e busca em todas as telas."""
    abrir(pagina, servidor.url)
    ir_para(pagina, tela)
    for sel in ("#btnMenu", ".topbar .logo", "#btnSearch"):
        assert pagina.is_visible(sel), sel
    assert pagina.inner_text("#pageTitle").strip().lower() == TELAS[tela].lower()


def test_ui_logo_no_cabecalho_e_no_menu(servidor, pagina):
    """A logo da equipe (app/img/logo.png) no lugar do escudo "NFL": carregada, decorativa e com 32 px de altura."""
    abrir(pagina, servidor.url)
    pagina.click("#btnMenu")
    esperar(pagina, "document.getElementById('sidebar').classList.contains('open')")
    logos = pagina.eval_on_selector_all(".topbar .logo, .sidebar-head .logo", """ls => ls.map(l => ({
        src: l.getAttribute('src'), alt: l.getAttribute('alt'), ok: l.complete && l.naturalWidth > 0,
        altura: Math.round(l.getBoundingClientRect().height), largura: Math.round(l.getBoundingClientRect().width) }))""")
    assert len(logos) == 2
    for l in logos:
        assert l["src"] == "img/logo.png" and l["alt"] == "" and l["ok"], l
        assert l["altura"] == 32 and 45 <= l["largura"] <= 52, l
    assert pagina.query_selector(".shield") is None


def test_ui_icone_da_aba(servidor, pagina):
    abrir(pagina, servidor.url)
    href = pagina.eval_on_selector("link[rel=icon]", "l => l.getAttribute('href')")
    assert href == "img/icone.png"
    with urllib.request.urlopen(servidor.url + "/" + href) as r:
        assert r.headers["Content-Type"] == "image/png" and r.read()[:4] == bytes([0x89]) + b"PNG"


def test_ui_moldura_centralizada_em_tela_larga(servidor, navegador):
    """1.3."""
    ctx = navegador.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    abrir(pg, servidor.url)
    caixa = pg.eval_on_selector(".app", "e => e.getBoundingClientRect().toJSON()")
    assert caixa["width"] == 430
    assert abs(caixa["x"] - (1280 - 430) / 2) <= 1
    ctx.close()


def test_ui_sem_transicoes_com_movimento_reduzido(servidor, navegador):
    """1.4: com o pedido do sistema, as telas entram sem animação e o menu abre sem transição."""
    ctx = navegador.new_context(viewport={"width": 430, "height": 860}, reduced_motion="reduce")
    pg = ctx.new_page()
    abrir(pg, servidor.url)
    assert pg.evaluate("document.documentElement.dataset.movimento") == "reduzido"
    assert rgb(pg, ".screen.active", "animationName") == "none"
    pg.click("#btnMenu")
    assert rgb(pg, "#sidebar", "transitionDuration") in ("0s", "0s, 0s")
    ctx.close()


def test_ui_sem_fontes_externas_renderiza(servidor, contexto):
    """1.5: sem o Google Fonts, a página desenha com a fonte do sistema, sem esperar."""
    contexto.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
    pg = contexto.new_page()
    pg.goto(servidor.url + "/", wait_until="commit")
    esperar(pg, "document.querySelectorAll('#seasonChips .chip').length > 0", 5000)


# ================================================================ Requisito 2
def test_ui_barra_inferior_com_4_destinos(servidor, pagina):
    """2.1."""
    abrir(pagina, servidor.url)
    textos = pagina.eval_on_selector_all(".bottom-nav .nav-item", "bs => bs.map(b => b.innerText.trim())")
    assert textos == ["Início", "Jogo", "Jogadores", "Notícias"]


def test_ui_destino_ativo_destacado(servidor, pagina):
    """2.2: o destino tocado abre a tela e fica destacado (e só ele)."""
    abrir(pagina, servidor.url)
    ir_para(pagina, "jogadores")
    ativos = pagina.eval_on_selector_all(".nav-item[aria-current=page]", "bs => bs.map(b => b.dataset.go)")
    assert ativos == ["jogadores"]
    esperar_cor(pagina, ".nav-item[data-go=jogadores]", "backgroundColor", "rgb(229, 32, 46)")
    esperar_cor(pagina, ".nav-item[data-go=inicio]", "backgroundColor", "rgba(0, 0, 0, 0)")


def test_ui_menu_lateral_itens(servidor, pagina):
    """2.3: os 4 destinos, Sobre os dados e Configurações."""
    abrir(pagina, servidor.url)
    pagina.click("#btnMenu")
    itens = pagina.eval_on_selector_all("#sidebar .side-item", "bs => bs.map(b => b.innerText.trim())")
    assert itens == ["Início", "Jogo", "Jogadores", "Notícias", "Sobre os dados", "Configurações"]
    ir_para(pagina, "config")
    assert not pagina.eval_on_selector("#sidebar", "e => e.classList.contains('open')")


def test_ui_menu_fecha_com_esc_e_toque_fora(servidor, pagina):
    """2.5."""
    abrir(pagina, servidor.url)
    pagina.click("#btnMenu")
    esperar(pagina, "document.getElementById('sidebar').classList.contains('open')")
    assert pagina.evaluate("document.activeElement.closest('#sidebar') !== null")    # foco vai para o menu
    pagina.keyboard.press("Escape")
    esperar(pagina, "!document.getElementById('sidebar').classList.contains('open')")
    assert pagina.evaluate("document.activeElement.id") == "btnMenu"                  # e volta ao botão
    pagina.click("#btnMenu")
    esperar(pagina, "document.getElementById('sidebar').classList.contains('open')")
    pagina.mouse.click(420, 400)                                                    # no escurecido, fora do menu
    esperar(pagina, "!document.getElementById('sidebar').classList.contains('open')")


@pytest.mark.parametrize("antiga,tela,aba", [("coach", "jogo", None), ("commentator", "jogo", "replay"),
                                             ("scout", "jogadores", None)])
def test_ui_links_antigos_abrem_tela_nova(servidor, pagina, antiga, tela, aba):
    """2.6: com o mesmo jogo e a mesma semana."""
    abrir(pagina, servidor.url, f"?season=2021&week=1&game=2021090900&screen={antiga}")
    esperar(pagina, f"document.getElementById('{tela}').classList.contains('active')")
    q = dict(p.split("=") for p in pagina.url.split("?")[1].split("&"))
    assert q["screen"] == tela and q["season"] == "2021" and q["week"] == "1" and q["game"] == "2021090900"
    assert q.get("aba") == aba


# ================================================================ Requisito 3
def test_ui_temporadas_so_com_dados(servidor, pagina):
    """3.1."""
    abrir(pagina, servidor.url)
    meta = api(servidor.url, "/api/meta")
    chips = pagina.eval_on_selector_all("#seasonChips .chip", "bs => bs.map(b => Number(b.dataset.season))")
    assert chips == [t["season"] for t in meta["seasons"]]


def test_ui_semanas_so_com_dados(servidor, pagina):
    """3.2: as semanas da temporada escolhida, com o nome da rodada nos playoffs."""
    abrir(pagina, servidor.url)
    pagina.click("#seasonChips [data-season='2024']")
    esperar(pagina, "document.querySelector('#seasonChips [aria-pressed=true]').dataset.season === '2024'")
    meta = api(servidor.url, "/api/meta")
    semanas = next(t for t in meta["seasons"] if t["season"] == 2024)["weeks"]
    chips = pagina.eval_on_selector_all("#weekChips .chip", "bs => bs.map(b => [Number(b.dataset.week), b.innerText])")
    assert [w for w, _ in chips] == [w["week"] for w in semanas]
    assert [t for _, t in chips][-4:] == ["Wild Card", "Divisional", "Final de Conferência", "Super Bowl"]
    assert chips[0][1] == "Sem 1"


def test_ui_abre_na_semana_mais_recente(servidor, pagina):
    """3.5: sem semana escolhida, a mais recente já começada da temporada atual."""
    abrir(pagina, servidor.url)
    meta = api(servidor.url, "/api/meta")
    ativo = pagina.eval_on_selector("#weekChips [aria-pressed=true]", "b => Number(b.dataset.week)")
    assert ativo == meta["currentWeek"]
    assert pagina.eval_on_selector("#seasonChips [aria-pressed=true]", "b => Number(b.dataset.season)") == meta["season"]


def test_ui_filtros_so_nas_telas_que_usam(servidor, pagina):
    abrir(pagina, servidor.url)
    ir_para(pagina, "jogadores")
    assert pagina.is_visible("#seasonRow") and not pagina.is_visible("#weekRow")
    ir_para(pagina, "jogo")
    assert not pagina.is_visible("#filters")


# ================================================================ Requisito 11
@pytest.mark.parametrize("salvo", ["{quebrado", json.dumps({"avancoNoticias": "sim", "velocidadeReplay": 7}), None])
def test_ui_configuracao_corrompida_usa_padrao(servidor, contexto, salvo):
    """11.5: JSON quebrado, valores desconhecidos ou localStorage que lança: vale o padrão."""
    if salvo is None:
        contexto.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqueado'); } });")
    else:
        contexto.add_init_script(f"localStorage.setItem('nfl.config.v2', {json.dumps(salvo)});")
    pg = contexto.new_page()
    abrir(pg, servidor.url)
    cfg = pg.evaluate("import('/js/config.js').then((m) => m.ler())")
    assert cfg == {"avancoNoticias": True, "velocidadeReplay": 1}


# ================================================================ Tarefa 3: Início
AGORA = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
SEMANA_2021 = "?season=2021&week=1"
TRACK = "document.getElementById('heroTrack')"


def abrir_inicio(pg, base, query=SEMANA_2021):
    pg.clock.install(time=AGORA)
    abrir(pg, base, query)
    esperar(pg, "document.querySelector('#jogosLista .match, #jogosLista .state:not(.loading)')")


def ponto_ativo(pg):
    return pg.evaluate("[...document.querySelectorAll('#heroDots button')]"
                       ".findIndex(b => b.getAttribute('aria-current') === 'true')")


def esperar_slide(pg, i):
    esperar(pg, f"Math.abs({TRACK}.scrollLeft - {i} * {TRACK}.clientWidth) < 2", 3000)


def simular_noticias(pg, corpo):
    pg.route("**/api/news?*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(corpo)))


def evento(espn_id, state, home, away, period=2, clock="5:21", name=None):
    return {"id": espn_id, "competitions": [{
        "status": {"period": period, "displayClock": clock,
                   "type": {"state": state, "name": name or {"in": "STATUS_IN_PROGRESS", "post": "STATUS_FINAL",
                                                              "pre": "STATUS_SCHEDULED"}[state]}},
        "competitors": [{"homeAway": "home", "score": str(home)}, {"homeAway": "away", "score": str(away)}]}]}


def simular_espn(pg, placares):
    """`placares`: uma resposta do scoreboard por consulta (a última se repete);
    cada uma é uma lista de eventos ou o número de um status HTTP de erro."""
    pg.espn = []

    def rota(route):
        if "/scoreboard" not in route.request.url:
            return route.fulfill(status=404, body="")
        r = placares[min(len(pg.espn), len(placares) - 1)]
        pg.espn.append(route.request.url)
        if isinstance(r, int):
            return route.fulfill(status=r, body="erro simulado")
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"events": r}))

    pg.route("https://site.api.espn.com/**", rota)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def simular_semana(pg, base, jogos_de):
    """Troca /api/games por jogos reais (2025, semana 1) com status e horários dados."""
    reais = api(base, "/api/games?season=2025&week=1")
    lista = []
    for real, extra in zip(reais, jogos_de):
        g = json.loads(json.dumps(real))
        placar = extra.pop("placar", None)
        g["home"]["score"], g["away"]["score"] = placar if placar else (None, None)
        g.update(extra)
        lista.append(g)
    pg.route("**/api/games?*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(lista)))
    return lista


def test_ui_inicio_ordem_das_secoes(servidor, pagina):
    """4.1: carrossel, os dois cartões e a lista de jogos, nesta ordem."""
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('heroBlock').hidden")
    ids = pagina.eval_on_selector_all("#inicio > section", "ss => ss.map(s => s.id)")
    assert ids == ["heroBlock", "resumoBlock", "jogosBlock"]


def test_ui_cartao_partidas_da_semana(servidor, pagina):
    """4.2: a quantidade real de jogos da semana escolhida."""
    abrir_inicio(pagina, servidor.url)
    jogos = api(servidor.url, "/api/games?season=2021&week=1")
    esperar(pagina, f"document.getElementById('tilePartidas').textContent === '{len(jogos)}'")
    ids = pagina.eval_on_selector_all("#jogosLista .match", "ms => ms.map(m => Number(m.dataset.game))")
    assert ids == [g["gameId"] for g in jogos]


def test_ui_cartao_jogadores_avaliados(servidor, pagina):
    """4.3: summary.ratedPlayers da temporada escolhida; o cartão leva a Jogadores."""
    abrir_inicio(pagina, servidor.url)
    n = api(servidor.url, "/api/summary?season=2021")["ratedPlayers"]
    esperado = f"{n:,}".replace(",", ".")
    esperar(pagina, f"document.getElementById('tileAvaliados').textContent === {json.dumps(esperado)}")
    pagina.click("#resumoBlock [data-go=jogadores]")
    esperar(pagina, "document.getElementById('jogadores').classList.contains('active')")


def test_ui_partida_abre_pagina_jogo(servidor, pagina):
    """4.4."""
    abrir_inicio(pagina, servidor.url)
    pagina.click("#jogosLista .match:nth-child(2)")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active')")
    jogos = api(servidor.url, "/api/games?season=2021&week=1")
    assert f"game={jogos[1]['gameId']}" in pagina.url


def test_ui_carrossel_4_primeiras(servidor, pagina):
    """7.4 e 7.2: as 4 primeiras notícias da semana, cada uma com o jogo a que se refere."""
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelectorAll('#heroTrack .slide').length > 0")
    news = api(servidor.url, "/api/news?season=2021&week=1")[:4]
    slides = pagina.eval_on_selector_all("#heroTrack .slide", "ss => ss.map(s => [s.dataset.noticia, s.innerText])")
    assert [i for i, _ in slides] == [n["id"] for n in news]
    for (_, t), n in zip(slides, news):
        assert n["titulo"].upper() in t.upper() and n["texto"] in t
        assert all(time in t for time in n["times"])                   # o jogo, no rodapé
    assert pagina.eval_on_selector_all("#heroDots button", "bs => bs.length") == 4
    assert ponto_ativo(pagina) == 0


def test_ui_noticia_abre_pagina_jogo(servidor, pagina):
    """7.5."""
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelector('#heroTrack .slide')")
    jogo = pagina.eval_on_selector("#heroTrack .slide", "s => s.dataset.game")
    pagina.click("#heroTrack .slide")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active')")
    assert f"game={jogo}" in pagina.url


def test_ui_carrossel_avanca_a_cada_5s(servidor, pagina):
    """4.5: avança a cada 5 s e pausa com o mouse em cima; os pontos levam à notícia."""
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelectorAll('#heroDots button').length === 4")
    pagina.clock.fast_forward(4000)
    assert ponto_ativo(pagina) == 0
    pagina.clock.fast_forward(1200)
    assert ponto_ativo(pagina) == 1
    pagina.clock.fast_forward(5000)
    assert ponto_ativo(pagina) == 2
    esperar_slide(pagina, 2)
    assert ponto_ativo(pagina) == 2
    pagina.hover("#hero")
    pagina.clock.fast_forward(15000)
    assert ponto_ativo(pagina) == 2                                  # parado com o mouse em cima
    pagina.mouse.move(5, 5)
    pagina.clock.fast_forward(5000)
    assert ponto_ativo(pagina) == 3
    pagina.clock.fast_forward(5000)
    assert ponto_ativo(pagina) == 0                                  # volta ao começo
    esperar_slide(pagina, 0)
    pagina.click("#heroDots button[data-slide='2']")
    assert ponto_ativo(pagina) == 2
    esperar_slide(pagina, 2)


def test_ui_carrossel_para_ao_sair_do_inicio(servidor, pagina):
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelectorAll('#heroDots button').length === 4")
    ir_para(pagina, "noticias")
    pagina.clock.fast_forward(12000)
    ir_para(pagina, "inicio")
    esperar(pagina, "document.querySelectorAll('#heroDots button').length === 4")
    assert ponto_ativo(pagina) == 0


@pytest.mark.parametrize("motivo", ["movimento_reduzido", "avanco_desligado"])
def test_ui_carrossel_parado_com_movimento_reduzido(servidor, navegador, motivo):
    """4.6, e o avanço desligado nas Configurações (religado, volta sem recarregar)."""
    ctx = navegador.new_context(viewport={"width": 430, "height": 860},
                                reduced_motion="reduce" if motivo == "movimento_reduzido" else "no-preference")
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    if motivo == "avanco_desligado":
        ctx.add_init_script("localStorage.setItem('nfl.config.v2', JSON.stringify({avancoNoticias: false}));")
    pg = ctx.new_page()
    abrir_inicio(pg, servidor.url)
    esperar(pg, "document.querySelectorAll('#heroDots button').length === 4")
    pg.clock.fast_forward(16000)
    assert ponto_ativo(pg) == 0
    if motivo == "avanco_desligado":
        pg.evaluate("import('/js/config.js').then((m) => m.gravar({ avancoNoticias: true }))")
        pg.clock.fast_forward(5200)
        assert ponto_ativo(pg) == 1
    ctx.close()


def test_ui_semana_sem_noticias_oculta_carrossel(servidor, pagina):
    """4.7: sem notícias, o carrossel some e o resto do Início fica."""
    simular_noticias(pagina, [])
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelector('#jogosLista .match')")
    pagina.wait_for_timeout(200)
    assert pagina.eval_on_selector("#heroBlock", "e => e.hidden") is True
    assert pagina.is_visible("#resumoBlock") and pagina.is_visible("#jogosBlock")


def test_ui_noticia_nao_vira_html(servidor, pagina):
    """S.1 nas notícias do carrossel."""
    real = api(servidor.url, "/api/news?season=2021&week=1")[0]
    simular_noticias(pagina, [{**real, "titulo": '<img src=x onerror="window.__xss=1">Manchete',
                               "texto": "<b>negrito</b>", "destaque": "<i>9</i>", "tag": "<u>t</u>"}])
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelector('#heroTrack .slide')")
    assert pagina.query_selector("#heroTrack img, #heroTrack b, #heroTrack i, #heroTrack u") is None
    assert "<img src=x" in pagina.text_content("#heroTrack") and pagina.evaluate("window.__xss") is None


def test_ui_trocar_semana_atualiza_inicio(servidor, pagina):
    """3.3: a lista, o cartão de partidas e as notícias passam a ser da semana escolhida."""
    abrir_inicio(pagina, servidor.url)
    esperar(pagina, "document.querySelector('#heroTrack .slide')")
    pagina.click("#weekChips [data-week='2']")
    jogos = api(servidor.url, "/api/games?season=2021&week=2")
    news = api(servidor.url, "/api/news?season=2021&week=2")[:4]
    esperar(pagina, "document.querySelector('#jogosLista .match') && "
                    f"document.querySelector('#jogosLista .match').dataset.game === '{jogos[0]['gameId']}'")
    esperar(pagina, "document.querySelector('#heroTrack .slide') && "
                    f"document.querySelector('#heroTrack .slide').dataset.noticia === {json.dumps(news[0]['id'])}")
    assert pagina.inner_text("#tilePartidas") == str(len(jogos))
    assert "Semana 2" in pagina.inner_text("#jogosConta")
    assert ponto_ativo(pagina) == 0


def test_ui_erro_na_semana_mantem_filtros(servidor, pagina):
    """3.4: a falha aparece na lista, e os filtros continuam funcionando."""
    pagina.route("**/api/games?*week=2*", lambda r: r.fulfill(status=500, content_type="application/json",
                                                              body=json.dumps({"error": "falha simulada"})))
    abrir_inicio(pagina, servidor.url)
    pagina.click("#weekChips [data-week='2']")
    esperar(pagina, "document.querySelector('#jogosLista .state.error')")
    assert "falha simulada" in pagina.inner_text("#jogosLista")
    pagina.click("#weekChips [data-week='3']")
    jogos = api(servidor.url, "/api/games?season=2021&week=3")
    esperar(pagina, "document.querySelector('#jogosLista .match') && "
                    f"document.querySelector('#jogosLista .match').dataset.game === '{jogos[0]['gameId']}'")
    pagina.click("#seasonChips [data-season='2022']")
    esperar(pagina, "document.querySelector('#seasonChips [aria-pressed=true]').dataset.season === '2022'")


def test_ui_filtro_por_time_com_chip(servidor, pagina):
    """3.3 (tarefa): o filtro por time mostra só os jogos dele, e o chip "TIME ×" remove."""
    abrir_inicio(pagina, servidor.url)
    pagina.evaluate("import('/js/telas/inicio.js').then((m) => m.filtrarPorTime('TB'))")
    esperar(pagina, "document.querySelectorAll('#jogosLista .match').length === 1")
    assert "Buccaneers" in pagina.inner_text("#jogosLista")
    assert pagina.inner_text("#filtroTime .chip").strip() == "TB"
    pagina.click("#weekChips [data-week='2']")                       # o filtro vale nas outras semanas
    esperar(pagina, "document.getElementById('jogosConta').textContent.includes('Semana 2') && "
                    "document.querySelectorAll('#jogosLista .match').length === 1 && "
                    "document.querySelector('#jogosLista .match').innerText.includes('Buccaneers')")
    pagina.click("#filtroTime .chip")
    esperar(pagina, "document.querySelectorAll('#jogosLista .match').length > 1")
    assert pagina.inner_text("#filtroTime") == ""


# ------------------------------------------ 4.8: estados do cartão e placar ao vivo
def test_ui_cartao_a_jogar_e_sem_resultado(servidor, pagina):
    simular_espn(pagina, [[]])
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=3))},
        {"espnId": "900002", "status": "sem_resultado", "kickoffUtc": iso(AGORA - timedelta(days=1))},
    ])
    abrir_inicio(pagina, servidor.url, "")
    cards = pagina.eval_on_selector_all(".match", "ms => ms.map(m => [m.dataset.estado, m.innerText])")
    assert cards[0][0] == "agendado" and "A JOGAR" in cards[0][1] and "–" not in cards[0][1]
    assert cards[1][0] == "sem_resultado" and "resultado ainda não disponível" in cards[1][1]


def test_ui_cartao_encerrado_com_prorrogacao(servidor, pagina):
    simular_espn(pagina, [[]])
    lista = simular_semana(pagina, servidor.url, [
        {"espnId": "900003", "status": "encerrado", "placar": (27, 24), "overtime": True,
         "kickoffUtc": iso(AGORA - timedelta(days=3))},
    ])
    abrir_inicio(pagina, servidor.url, "")
    t = pagina.inner_text(".match")
    assert "FINAL" in t and "PRORROG." in t and "27" in t and "24" in t
    assert pagina.eval_on_selector(".match .team.win .name", "e => e.textContent") == lista[0]["home"]["nick"]


def _semana_ao_vivo(pg, base):
    return simular_semana(pg, base, [
        {"espnId": "900001", "status": "sem_resultado", "kickoffUtc": iso(AGORA - timedelta(hours=1))},
        {"espnId": "900002", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=5))},
        {"espnId": "900003", "status": "encerrado", "placar": (24, 20), "kickoffUtc": iso(AGORA - timedelta(days=3))},
    ])


def test_ui_ao_vivo_placar_quarto_relogio(servidor, pagina):
    simular_espn(pagina, [[evento("900001", "in", 3, 7, period=2, clock="5:21")]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_inicio(pagina, servidor.url, "")
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    t = pagina.inner_text(".match")
    assert "AO VIVO" in t and "Q2 · 5:21" in t and "7" in t and "3" in t


def test_ui_ao_vivo_atualiza_a_cada_30s_e_para_ao_encerrar(servidor, pagina):
    simular_espn(pagina, [
        [evento("900001", "in", 3, 7, period=2, clock="5:21")],
        [evento("900001", "in", 10, 14, period=3, clock="10:00")],
        [evento("900001", "post", 17, 21, period=4, clock="0:00")],
    ])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_inicio(pagina, servidor.url, "")
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q2 · 5:21')")
    assert len(pagina.espn) == 1
    pagina.clock.fast_forward(29000)
    pagina.wait_for_timeout(300)
    assert len(pagina.espn) == 1                                     # ainda não deu 30 s
    pagina.clock.fast_forward(1500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q3 · 10:00')")
    pagina.clock.fast_forward(30000)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'final-espn'")
    assert "FINAL" in pagina.inner_text(".match") and "21" in pagina.inner_text(".match")
    pagina.clock.fast_forward(120000)                                # encerrado: parou de consultar
    pagina.wait_for_timeout(300)
    assert len(pagina.espn) == 3


def test_ui_ao_vivo_para_fora_do_inicio(servidor, pagina):
    simular_espn(pagina, [[evento("900001", "in", 3, 7)]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_inicio(pagina, servidor.url, "")
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    ir_para(pagina, "noticias")
    n = len(pagina.espn)
    pagina.clock.fast_forward(95000)
    pagina.wait_for_timeout(300)
    assert len(pagina.espn) == n


def test_ui_sem_jogo_em_andamento_nao_consulta(servidor, pagina):
    simular_espn(pagina, [[]])
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=5))},
        {"espnId": "900003", "status": "encerrado", "placar": (24, 20), "kickoffUtc": iso(AGORA - timedelta(days=3))},
    ])
    abrir_inicio(pagina, servidor.url, "")
    pagina.clock.fast_forward(90000)
    pagina.wait_for_timeout(300)
    assert pagina.espn == []


def test_ui_ao_vivo_comeca_quando_o_jogo_comeca(servidor, pagina):
    simular_espn(pagina, [[evento("900001", "in", 0, 7, period=1, clock="9:00")]])
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(minutes=10))},
    ])
    abrir_inicio(pagina, servidor.url, "")
    assert pagina.espn == []
    pagina.clock.fast_forward(11 * 60 * 1000)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")


def test_ui_ao_vivo_falha_mantem_ultimo_placar(servidor, pagina):
    simular_espn(pagina, [[evento("900001", "in", 3, 7)], 503,
                          [evento("900001", "in", 3, 14, period=3, clock="12:00")]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_inicio(pagina, servidor.url, "")
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    pagina.clock.fast_forward(30500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('atualização ao vivo indisponível')")
    t = pagina.inner_text(".match")
    assert "AO VIVO" in t and "Q2 · 5:21" in t                       # o último placar conhecido
    pagina.clock.fast_forward(30500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q3 · 12:00')")
    assert "indisponível" not in pagina.inner_text(".match")


def test_ui_encerrado_prevalece_nflverse(servidor, pagina):
    simular_espn(pagina, [[evento("900001", "in", 3, 7), evento("900003", "in", 10, 3)]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_inicio(pagina, servidor.url, "")
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    terceiro = pagina.eval_on_selector_all(".match", "ms => [ms[2].dataset.estado, ms[2].innerText]")
    assert terceiro[0] == "final" and "24" in terceiro[1] and "20" in terceiro[1] and "AO VIVO" not in terceiro[1]


# ================================================================ Tarefa 4: página Jogo
JOGO = "?season=2021&week=1&game=2021090900&screen=jogo"          # DAL 29 x 31 TB
MATERIA = {"headline": "Brady lança 4 TDs e Bucs vencem", "description": "Tom Brady não piscou.",
           "published": "2021-09-10T06:32:45Z", "source": "AP",
           "links": {"web": {"href": "http://www.espn.com/nfl/recap?gameId=401326322"}}}


def abrir_jogo(pg, base, query=JOGO):
    abrir(pg, base, query)
    esperar(pg, "document.getElementById('jogo').classList.contains('active') && document.querySelector('#jogoCab .jogo-cab')")


def esperar_prancheta(pg):
    esperar(pg, "document.querySelectorAll('#field .player-dot:not(.ball)').length > 0 || "
                "document.querySelector('#fieldWrap .formacao-indisponivel')")


def aba(pg, nome):
    pg.click(f"#jogoAbas [data-aba={nome}]")
    esperar(pg, f"document.querySelector('#jogoAbas [aria-selected=true]').dataset.aba === '{nome}'")


def simular_materia(pg, materia=None, status=200):
    pg.summary = []

    def rota(route):
        if "/summary" not in route.request.url:
            return route.fulfill(status=404, body="")
        pg.summary.append(route.request.url)
        if status != 200:
            return route.fulfill(status=status, body="erro simulado")
        corpo = {"header": {"competitions": [{"status": {"type": {"state": "post"}}, "competitors": []}]}}
        if materia:
            corpo["article"] = materia
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(corpo))

    pg.route("https://site.api.espn.com/**", rota)


def test_ui_jogo_cabecalho_da_partida(servidor, pagina):
    """5.1: placar, os dois times e a semana; nos playoffs, o nome da rodada."""
    abrir_jogo(pagina, servidor.url)
    t = pagina.inner_text("#jogoCab")
    assert "Cowboys" in t and "Buccaneers" in t and "29" in t and "31" in t and "Semana 1" in t and "FINAL" in t
    assert pagina.eval_on_selector("#jogoCab .team.win .name", "e => e.textContent") == "Buccaneers"
    sb = api(servidor.url, "/api/games?season=2021&week=22")[0]["gameId"]
    abrir_jogo(pagina, servidor.url, f"?season=2021&week=22&game={sb}&screen=jogo")
    assert "Super Bowl" in pagina.inner_text("#jogoCab")


def test_ui_jogo_5_abas(servidor, pagina):
    """5.2."""
    abrir_jogo(pagina, servidor.url)
    abas = pagina.eval_on_selector_all("#jogoAbas [role=tab]", "bs => bs.map(b => b.innerText.trim())")
    assert abas == ["Prancheta", "Jogadas", "Replay", "Estatísticas", "Playbook"]
    assert pagina.eval_on_selector("#jogoAbas [aria-selected=true]", "b => b.dataset.aba") == "prancheta"
    pagina.focus("#aba-prancheta")                                     # setas do teclado entre as abas
    pagina.keyboard.press("ArrowRight")
    esperar(pagina, "document.activeElement.id === 'aba-jogadas' && "
                    "document.querySelector('#jogoAbas [aria-selected=true]').dataset.aba === 'jogadas'")


def test_ui_abas_do_antigo_treinador(servidor, pagina):
    """5.3: prancheta com os 22 jogadores, jogadas por quarto, estatísticas e playbook."""
    abrir_jogo(pagina, servidor.url)
    esperar_prancheta(pagina)
    assert pagina.eval_on_selector_all("#field .player-dot:not(.ball)", "ds => ds.length") == 22
    assert "Esquema ilustrativo" in pagina.inner_text("#avisoField")
    pagina.eval_on_selector("#field .player-dot:not(.ball)", "d => d.click()")   # tocar num jogador mostra quem é
    esperar(pagina, "document.querySelector('#dotInfo .row-card')")
    pagina.click("#nextPlay")
    esperar(pagina, "new URLSearchParams(location.search).get('play') !== '55'")
    aba(pagina, "jogadas")
    plays = api(servidor.url, "/api/games/2021090900/plays")
    esperar(pagina, "document.querySelectorAll('#jogoCorpo .play-row').length > 0")
    assert pagina.eval_on_selector_all("#jogoCorpo .play-row", "rs => rs.length") == len(plays)
    quartos = pagina.eval_on_selector_all("#jogoCorpo .sec-head h3", "hs => hs.map(h => h.textContent)")
    assert quartos[:4] == ["1º quarto", "2º quarto", "3º quarto", "4º quarto"]
    aba(pagina, "estatisticas")
    esperar(pagina, "document.getElementById('jogoCorpo').innerText.includes('Jardas totais')")
    assert "Pressão e proteção".upper() in pagina.inner_text("#jogoCorpo").upper()
    aba(pagina, "playbook")
    esperar(pagina, "document.getElementById('jogoCorpo').innerText.toUpperCase().includes('FORMAÇÕES · TB')")


def test_ui_replay_narrado_placar_e_acumulado(servidor, pagina):
    """5.4: narração cronológica, placar do momento e painel acumulado; uma jogada a cada 1,4 s."""
    pagina.clock.install(time=AGORA)
    abrir_jogo(pagina, servidor.url, JOGO + "&aba=replay")
    esperar(pagina, "document.querySelectorAll('#bcFeed .tl-item').length === 1")
    bc = api(servidor.url, "/api/games/2021090900/broadcast")
    assert pagina.inner_text("#bcPos") == f"1/{len(bc['feed'])}"
    pagina.click("#bcPlay")
    pagina.clock.fast_forward(1400 * 3 + 100)
    esperar(pagina, "document.getElementById('bcPos').textContent.startsWith('4/')")
    assert pagina.eval_on_selector_all("#bcFeed .tl-item", "is => is.length") == 4
    assert bc["feed"][3]["narration"]["headline"] in pagina.inner_text("#bcFeed .tl-item[aria-current=true]")
    assert "Jardas" in pagina.inner_text("#bcPanel")
    pagina.click("#bcPlay")                                            # pausa
    pagina.clock.fast_forward(5000)
    assert pagina.inner_text("#bcPos").startswith("4/")
    pagina.eval_on_selector("#bcRange", "r => { r.value = String(r.max); r.dispatchEvent(new Event('input', { bubbles: true })); }")
    esperar(pagina, f"document.getElementById('bcPos').textContent === '{len(bc['feed'])}/{len(bc['feed'])}'")
    fim = bc["feed"][-1]["score"]
    placar = pagina.eval_on_selector_all("#bcScore .big", "bs => bs.map(b => Number(b.textContent))")
    assert placar == [fim["away"], fim["home"]] == [29, 31]


def test_ui_replay_na_velocidade_das_configuracoes(servidor, contexto):
    """11.2 (parte do Replay): 2× avança uma jogada a cada 0,7 s."""
    contexto.add_init_script("localStorage.setItem('nfl.config.v2', JSON.stringify({velocidadeReplay: 2}));")
    pg = contexto.new_page()
    pg.clock.install(time=AGORA)
    abrir_jogo(pg, servidor.url, JOGO + "&aba=replay")
    esperar(pg, "document.getElementById('bcPlay')")
    pg.click("#bcPlay")
    pg.clock.fast_forward(700 * 4 + 100)
    esperar(pg, "document.getElementById('bcPos').textContent.startsWith('5/')")


def test_ui_jogada_em_jogadas_ou_replay_abre_prancheta(servidor, pagina):
    """5.5."""
    abrir_jogo(pagina, servidor.url, JOGO + "&aba=jogadas")
    esperar(pagina, "document.querySelectorAll('#jogoCorpo .play-row').length > 20")
    alvo = pagina.eval_on_selector_all("#jogoCorpo .play-row", "rs => rs[20].dataset.play")
    pagina.click(f"#jogoCorpo .play-row[data-play='{alvo}']")
    esperar(pagina, "document.querySelector('#jogoAbas [aria-selected=true]').dataset.aba === 'prancheta'")
    esperar_prancheta(pagina)
    assert pagina.eval_on_selector("#playPick", "s => s.value") == alvo
    aba(pagina, "replay")
    esperar(pagina, "document.querySelector('#bcFeed .tl-item')")
    alvo = pagina.eval_on_selector("#bcFeed .tl-item", "i => i.dataset.play")
    pagina.click("#bcFeed .tl-item")
    esperar(pagina, "document.querySelector('#jogoAbas [aria-selected=true]').dataset.aba === 'prancheta'")
    esperar(pagina, f"document.getElementById('playPick') && document.getElementById('playPick').value === '{alvo}'")


def test_ui_trocar_aba_mantem_jogo_e_jogada(servidor, pagina):
    """5.6."""
    abrir_jogo(pagina, servidor.url, JOGO + "&play=253")
    esperar_prancheta(pagina)
    assert pagina.eval_on_selector("#playPick", "s => s.value") == "253"
    for nome in ("jogadas", "replay", "estatisticas", "playbook", "prancheta"):
        aba(pagina, nome)
    esperar_prancheta(pagina)
    assert pagina.eval_on_selector("#playPick", "s => s.value") == "253"
    assert "Cowboys" in pagina.inner_text("#jogoCab")
    ir_para(pagina, "inicio")                                          # ida e volta pela barra
    ir_para(pagina, "jogo")
    esperar_prancheta(pagina)
    assert pagina.eval_on_selector("#playPick", "s => s.value") == "253"


def test_ui_jogo_sem_partida_abre_primeira_da_semana(servidor, pagina):
    """5.7."""
    abrir(pagina, servidor.url, "?season=2021&week=2")
    ir_para(pagina, "jogo")
    primeiro = api(servidor.url, "/api/games?season=2021&week=2")[0]
    esperar(pagina, "document.querySelector('#jogoCab .jogo-cab')")
    assert primeiro["home"]["nick"] in pagina.inner_text("#jogoCab")
    assert f"game={primeiro['gameId']}" in pagina.url


def test_ui_jogada_sem_formacao_mostra_aviso(servidor, pagina):
    """5.8: os dados da jogada e a mensagem no lugar da prancheta."""
    abrir_jogo(pagina, servidor.url)
    esperar(pagina, "document.getElementById('playPick') && document.getElementById('playPick').options.length > 100")
    pagina.evaluate("""() => {
        const s = document.getElementById('playPick');
        s.value = [...s.options].find((o) => o.text.includes('sem formação')).value;
        s.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    esperar(pagina, "document.getElementById('fieldWrap') && "
                    "document.getElementById('fieldWrap').innerText.includes('Formação indisponível para esta jogada')")
    assert pagina.inner_text("#playMeta").strip() != ""
    assert pagina.query_selector("#field .player-dot") is None
    aba(pagina, "jogadas")
    esperar(pagina, "document.querySelector('.play-row')")
    assert "SEM DADOS DE FORMAÇÃO" in pagina.inner_text("#jogoCorpo")


# ------------------------------------------ 5.9: matéria da ESPN (os testes da test_ui_dados.py, adaptados)
def test_ui_materia_no_topo_da_pagina_jogo(servidor, pagina):
    simular_materia(pagina, MATERIA)
    abrir_jogo(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    ordem = pagina.eval_on_selector_all("#jogo > section", "ss => ss.map(s => s.id || s.firstElementChild.id)")
    assert ordem[:3] == ["jogoCabBlock", "materia", "jogoAbas"]
    t = pagina.inner_text("#materia")
    assert "BRADY LANÇA 4 TDS" in t.upper() and "Tom Brady não piscou." in t
    assert "10/09/2021" in t and "AP · ESPN" in t
    assert pagina.eval_on_selector("#materia a", "a => a.href") == "https://www.espn.com/nfl/recap?gameId=401326322"
    assert "event=401326322" in pagina.summary[0]


@pytest.mark.parametrize("caso", ["erro", "sem_materia"])
def test_ui_materia_indisponivel_some(servidor, pagina, caso):
    simular_materia(pagina, None, status=500 if caso == "erro" else 200)
    abrir_jogo(pagina, servidor.url)
    esperar_prancheta(pagina)                                          # o resto da página segue
    pagina.wait_for_timeout(300)
    assert len(pagina.summary) == 1
    assert pagina.eval_on_selector("#materia", "m => m.hidden") is True


@pytest.mark.parametrize("href", ["https://evil.example.com/nfl/recap", "javascript:alert(1)",
                                  "https://espn.com.evil.io/x"])
def test_ui_link_fora_da_espn_nao_exibido(servidor, pagina, href):
    simular_materia(pagina, {**MATERIA, "links": {"web": {"href": href}}})
    abrir_jogo(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    assert pagina.query_selector("#materia a") is None and "Brady" in pagina.inner_text("#materia")


def test_ui_materia_texto_externo_nao_vira_html(servidor, pagina):
    simular_materia(pagina, {**MATERIA, "headline": '<img src=x onerror="window.__xss=1">Manchete',
                             "description": "<b>negrito</b>"})
    abrir_jogo(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    assert pagina.query_selector("#materia img") is None and pagina.query_selector("#materia b") is None
    assert "<img src=x" in pagina.text_content("#materia") and pagina.evaluate("window.__xss") is None


def test_ui_materia_nao_consulta_jogo_a_jogar(servidor, pagina):
    simular_materia(pagina, MATERIA)
    agendado = next(g for g in api(servidor.url, "/api/games?season=2026&week=18") if g["status"] == "agendado")
    abrir_jogo(pagina, servidor.url, f"?season=2026&week=18&game={agendado['gameId']}&screen=jogo")
    assert "A JOGAR" in pagina.inner_text("#jogoCab")
    pagina.wait_for_timeout(300)
    assert pagina.summary == [] and pagina.eval_on_selector("#materia", "m => m.hidden") is True


# ================================================================ Tarefa 5: prancheta
GENERICA = "?season=2026&week=1&game=2026090900&screen=jogo&play=64"   # SEA x NE, posições genéricas


def cores_dos_pontos(pg):
    return pg.eval_on_selector_all("#field .player-dot:not(.ball)", """ds => {
        const c = { offense: new Set(), defense: new Set() };
        ds.forEach((d) => c[d.classList.contains('def') ? 'defense' : 'offense'].add(getComputedStyle(d).backgroundColor));
        return { offense: [...c.offense], defense: [...c.defense], def: ds.filter((d) => d.classList.contains('def')).length };
    }""")


def test_ui_prancheta_esquema_ilustrativo_sem_animacao(servidor, pagina):
    """5.3: um quadro só, com o aviso de esquema ilustrativo e sem controles de animação."""
    abrir_jogo(pagina, servidor.url, JOGO + "&play=55")
    esperar_prancheta(pagina)
    assert "Esquema ilustrativo" in pagina.inner_text("#avisoField")
    assert pagina.query_selector("#jogoCorpo input[type=range], #btnPlay, #frameRange, #speedPick") is None
    c = cores_dos_pontos(pagina)
    assert c["def"] == 11 and len(c["offense"]) == 1 and len(c["defense"]) == 1
    legenda = pagina.inner_text("#fieldLegend")
    assert "TB · ataque" in legenda and "DAL · defesa" in legenda


def test_ui_prancheta_jogador_tocado_fica_destacado(servidor, pagina):
    """Tocar num jogador destaca só ele (no app antigo a comparação de ids nunca batia); de novo, desfaz."""
    abrir_jogo(pagina, servidor.url, JOGO + "&play=55")
    esperar_prancheta(pagina)
    pagina.eval_on_selector_all("#field .player-dot:not(.ball)", "ds => ds[8].click()")
    assert pagina.eval_on_selector_all("#field .player-dot.selected", "ds => ds.length") == 1
    assert pagina.eval_on_selector_all("#field .player-dot.dim", "ds => ds.length") == 21
    assert "Chris Godwin" in pagina.inner_text("#dotInfo")
    pagina.eval_on_selector_all("#field .player-dot:not(.ball)", "ds => ds[8].click()")
    assert pagina.query_selector("#field .player-dot.selected, #field .player-dot.dim") is None
    assert pagina.inner_text("#dotInfo") == ""


def test_ui_prancheta_posicoes_genericas(servidor, pagina):
    """Jogada sem os nomes na fonte: posições genéricas com o aviso, e os lados com cores diferentes
    mesmo quando os times têm a mesma cor (SEA e NE: #002244)."""
    abrir_jogo(pagina, servidor.url, GENERICA)
    esperar_prancheta(pagina)
    assert "posições genéricas, sem nomes" in pagina.inner_text("#avisoField")
    assert pagina.eval_on_selector_all("#field .player-dot:not(.ball)", "ds => ds.length") == 22
    c = cores_dos_pontos(pagina)
    assert c["offense"] == ["rgb(0, 34, 68)"] and len(c["defense"]) == 1 and c["defense"] != c["offense"]
    assert "SEA · ataque" in pagina.inner_text("#fieldLegend") and "NE · defesa" in pagina.inner_text("#fieldLegend")
    pagina.eval_on_selector("#field .player-dot:not(.ball)", "d => d.click()")
    assert "Posição genérica" in pagina.inner_text("#dotInfo")
    assert pagina.query_selector("#dotInfo [data-player]") is None       # sem nome, não leva a um perfil


def test_ui_prancheta_cores_dos_lados(servidor, pagina):
    abrir(pagina, servidor.url)
    r = pagina.evaluate("""async () => {
        const m = await import('/js/prancheta.js');
        const ui = await import('/js/ui.js');
        const meta = await (await fetch('/api/meta')).json();
        const t = (a) => meta.teams[a];
        return [m.coresDosLados({ offense: 'SEA', defense: 'NE' }, t), m.coresDosLados({ offense: 'TB', defense: 'DAL' }, t),
                m.coresDosLados({}, t), ui.corDoTexto('#FFB612'), ui.corDoTexto('#002244'), ui.corDoTexto('#FB4F14')];
    }""")
    meta = api(servidor.url, "/api/meta")["teams"]
    assert r[0] == {"offense": meta["SEA"]["primary"], "defense": meta["NE"]["secondary"]}
    assert r[1] == {"offense": meta["TB"]["primary"], "defense": meta["DAL"]["primary"]}
    assert r[2] == {} and r[3] == "#0b1322" and r[4] == "#ffffff" and r[5] == "#0b1322"   # CIN: 3,0:1 com branco


# ================================================================ Tarefa 6: Jogadores
JOGADORES = "?season=2021&week=1&game=2021090900&screen=jogadores"


def abrir_jogadores(pg, base, query=JOGADORES):
    abrir(pg, base, query)
    esperar(pg, "document.getElementById('jogadores').classList.contains('active') && "
                "document.querySelector('#scoutBody .row-card, #scoutBody .state:not(.loading), #radarSlot')")


def nomes_da_lista(pg):
    return pg.eval_on_selector_all("#scoutBody .row-card b", "bs => bs.map(b => b.textContent)")


def test_ui_jogadores_busca_filtro_perfil_comparacao(servidor, pagina):
    """6.1: lista por rating, filtro por posição, busca, perfil com radar e jogo a jogo, e comparação."""
    abrir_jogadores(pagina, servidor.url)
    lista = api(servidor.url, "/api/players?season=2021&limit=60")
    assert nomes_da_lista(pagina) == [p["name"] for p in lista]
    pagina.click("#scoutFilters [data-pos=QB]")
    qbs = api(servidor.url, "/api/players?season=2021&position=QB&limit=60")
    esperar(pagina, f"document.querySelector('#scoutBody .row-card b') && "
                    f"document.querySelector('#scoutBody .row-card b').textContent === {json.dumps(qbs[0]['name'])}")
    assert nomes_da_lista(pagina) == [p["name"] for p in qbs]
    pagina.fill("#scoutSearch", "brady")
    esperar(pagina, "document.querySelectorAll('#scoutBody .row-card').length === 1")
    assert nomes_da_lista(pagina) == ["Tom Brady"]
    pagina.click("#scoutBody .row-card")
    esperar(pagina, "document.querySelector('#radarSlot svg.radar')")
    assert "jogador=00-0019596" in pagina.url
    perfil = pagina.inner_text("#scoutBody")
    assert "TOM BRADY" in perfil.upper() and "JOGO A JOGO" in perfil.upper() and "Michigan" in perfil
    assert pagina.is_hidden("#scoutControles")
    pagina.select_option("#cmpPick", index=1)
    esperar(pagina, "document.querySelectorAll('#cmpSlot .cmp').length > 3")
    assert "Tom Brady" in pagina.inner_text("#cmpSlot .cmp-nomes")
    pagina.click("#backList")                                          # volta com o filtro e a busca mantidos
    esperar(pagina, "document.querySelectorAll('#scoutBody .row-card').length === 1")
    assert pagina.input_value("#scoutSearch") == "brady"
    assert pagina.eval_on_selector("#scoutFilters [aria-pressed=true]", "b => b.dataset.pos") == "QB"
    assert "jogador=" not in pagina.url


def test_ui_jogadores_na_temporada_escolhida(servidor, pagina):
    abrir_jogadores(pagina, servidor.url)
    pagina.click("#seasonChips [data-season='2024']")
    lista = api(servidor.url, "/api/players?season=2024&limit=60")
    esperar(pagina, "document.querySelector('#scoutBody .row-card b') && "
                    f"document.querySelector('#scoutBody .row-card b').textContent === {json.dumps(lista[0]['name'])}")
    assert "Temporada 2024" in pagina.inner_text("#jogadoresBlock .block-head")


def test_ui_jogadores_a_observar_da_partida(servidor, pagina):
    """6.2: os destaques da partida selecionada; o link leva à partida."""
    abrir_jogadores(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('observarBlock').hidden")
    watch = api(servidor.url, "/api/games/2021090900")["watch"]
    ids = pagina.eval_on_selector_all("#observarLista .watch-card", "cs => cs.map(c => c.dataset.player)")
    assert ids == [p["nflId"] for p in watch]
    assert pagina.inner_text("#observarJogo") == "DAL @ TB"
    pagina.click("#observarLista .watch-card:nth-child(2)")
    esperar(pagina, "document.querySelector('#radarSlot')")
    assert f"jogador={watch[1]['nflId']}" in pagina.url
    pagina.click("#observarJogo")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active')")
    assert "game=2021090900" in pagina.url


def test_ui_a_observar_atualiza_ao_trocar_partida(servidor, pagina):
    """6.3."""
    abrir_jogadores(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('observarBlock').hidden")
    outro = api(servidor.url, "/api/games?season=2021&week=1")[3]
    ir_para(pagina, "inicio")
    pagina.click(f"#jogosLista .match[data-game='{outro['gameId']}']")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active')")
    ir_para(pagina, "jogadores")
    watch = api(servidor.url, f"/api/games/{outro['gameId']}")["watch"]
    esperar(pagina, f"document.querySelector('#observarLista .watch-card') && "
                    f"document.querySelector('#observarLista .watch-card').dataset.player === {json.dumps(watch[0]['nflId'])}")
    assert pagina.inner_text("#observarJogo") == f"{outro['away']['abbr']} @ {outro['home']['abbr']}"


def test_ui_a_observar_sem_partida_usa_a_primeira_da_semana(servidor, pagina):
    abrir_jogadores(pagina, servidor.url, "?season=2021&week=2&screen=jogadores")
    primeiro = api(servidor.url, "/api/games?season=2021&week=2")[0]
    esperar(pagina, "!document.getElementById('observarBlock').hidden")
    assert pagina.inner_text("#observarJogo") == f"{primeiro['away']['abbr']} @ {primeiro['home']['abbr']}"


def test_ui_a_observar_oculto_sem_avaliados(servidor, pagina):
    """6.4: resposta simulada sem ninguém com amostra suficiente."""
    real = api(servidor.url, "/api/games/2021090900")
    pagina.route("**/api/games/2021090900", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({**real, "watch": []})))
    abrir_jogadores(pagina, servidor.url)
    pagina.wait_for_timeout(300)
    assert pagina.eval_on_selector("#observarBlock", "e => e.hidden") is True
    assert len(nomes_da_lista(pagina)) == 60                           # a lista segue


def test_ui_jogador_da_prancheta_abre_o_perfil(servidor, pagina):
    abrir_jogo(pagina, servidor.url, JOGO + "&play=55")
    esperar_prancheta(pagina)
    pagina.eval_on_selector_all("#field .player-dot:not(.ball)", "ds => ds[8].click()")
    pagina.click("#dotInfo [data-player]")
    esperar(pagina, "document.getElementById('jogadores').classList.contains('active') && document.querySelector('#radarSlot')")
    assert "CHRIS GODWIN" in pagina.inner_text("#scoutBody").upper()


def test_ui_perfil_por_link(servidor, pagina):
    abrir_jogadores(pagina, servidor.url, "?season=2021&screen=jogadores&jogador=00-0019596")
    esperar(pagina, "document.querySelector('#radarSlot')")
    assert "TOM BRADY" in pagina.inner_text("#scoutBody").upper()


# ================================================================ Tarefa 7: Notícias e busca
NOTICIAS = "?season=2021&week=1&screen=noticias"
EMBRULHO_FETCH = """
window.__atraso = {};          // {trecho_da_url: ms}
const _fetch = window.fetch.bind(window);
window.fetch = async (url, opts) => {
  const r = await _fetch(url, opts);
  for (const t in window.__atraso) {
    if (String(url).includes(t)) await new Promise((ok) => setTimeout(ok, window.__atraso[t]));
  }
  return r;
};
"""


def abrir_noticias(pg, base, query=NOTICIAS):
    abrir(pg, base, query)
    esperar(pg, "document.getElementById('noticias').classList.contains('active') && "
                "document.querySelector('#noticiasLista .news-item, #noticiasLista .state:not(.loading)')")


def buscar(pg, termo):
    if pg.is_hidden("#searchbar"):
        pg.click("#btnSearch")
    pg.fill("#searchInput", termo)


def grupos_da_busca(pg):
    return pg.eval_on_selector_all("#searchResults .sr-group", "gs => gs.map(g => g.textContent)")


def esperar_busca_completa(pg):
    esperar(pg, "!document.querySelector('#searchResults .sr-carregando') && "
                "document.querySelector('#searchResults .sr-item, #searchResults .sr-empty')")


def test_ui_noticias_da_semana(servidor, pagina):
    """7.1 e 7.2: as notícias da semana, na ordem da API, cada uma com o jogo a que se refere."""
    abrir_noticias(pagina, servidor.url)
    news = api(servidor.url, "/api/news?season=2021&week=1")
    ids = pagina.eval_on_selector_all("#noticiasLista .news-item", "ns => ns.map(n => n.dataset.noticia)")
    assert ids == [n["id"] for n in news]
    assert pagina.inner_text("#noticiasConta") == f"{len(news)} notícias · Semana 1"
    itens = pagina.eval_on_selector_all("#noticiasLista .news-item", "ns => ns.map(n => n.innerText)")
    for t, n in zip(itens, news):
        assert all(time in t for time in n["times"]) and n["tag"] in t and n["texto"] in t


def test_ui_noticia_da_lista_abre_pagina_jogo(servidor, pagina):
    """7.5."""
    abrir_noticias(pagina, servidor.url)
    jogo = pagina.eval_on_selector_all("#noticiasLista .news-item", "ns => ns[2].dataset.game")
    pagina.click("#noticiasLista .news-item:nth-child(3)")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active') && document.querySelector('#jogoCab .jogo-cab')")
    assert f"game={jogo}" in pagina.url


def test_ui_noticias_semana_vazia(servidor, pagina):
    """7.6: semana ainda sem jogos disputados."""
    abrir_noticias(pagina, servidor.url, "?season=2026&week=18&screen=noticias")
    assert "Sem notícias para esta semana." in pagina.inner_text("#noticiasLista")


def test_ui_noticias_trocar_semana(servidor, pagina):
    abrir_noticias(pagina, servidor.url)
    pagina.click("#weekChips [data-week='2']")
    news = api(servidor.url, "/api/news?season=2021&week=2")
    esperar(pagina, "document.querySelector('#noticiasLista .news-item') && "
                    f"document.querySelector('#noticiasLista .news-item').dataset.noticia === {json.dumps(news[0]['id'])}")


def test_ui_lupa_abre_busca_com_foco(servidor, pagina):
    """8.1."""
    abrir(pagina, servidor.url)
    pagina.click("#btnSearch")
    assert pagina.is_visible("#searchbar")
    assert pagina.evaluate("document.activeElement.id") == "searchInput"


def test_ui_busca_agrupa_times_jogadores_noticias(servidor, pagina):
    """8.2: nesta ordem; as notícias também pelo nome do time (a manchete usa a sigla)."""
    abrir(pagina, servidor.url, "?season=2021&week=1")
    buscar(pagina, "buc")
    esperar_busca_completa(pagina)
    assert grupos_da_busca(pagina) == ["Times", "Jogadores", "Notícias"]
    assert "Tampa Bay Buccaneers" in pagina.inner_text("#searchResults")
    jogadores = api(servidor.url, "/api/players?season=2021&q=buc&limit=8")
    ids = pagina.eval_on_selector_all("[data-busca-jogador]", "bs => bs.map(b => b.dataset.buscaJogador)")
    assert ids == [p["nflId"] for p in jogadores]
    noticias = pagina.eval_on_selector_all("#searchResults [data-game]", "bs => bs.length")
    assert 1 <= noticias <= 6


def test_ui_resultado_da_busca_leva_ao_destino(servidor, pagina):
    """8.3: o time (seus jogos na semana), o perfil do jogador e a página do jogo da notícia."""
    abrir(pagina, servidor.url, "?season=2021&week=1&screen=noticias")
    buscar(pagina, "tampa")
    esperar_busca_completa(pagina)
    pagina.click("[data-busca-time=TB]")
    esperar(pagina, "document.getElementById('inicio').classList.contains('active') && "
                    "document.querySelectorAll('#jogosLista .match').length === 1")
    assert pagina.inner_text("#filtroTime .chip").strip() == "TB" and pagina.is_hidden("#searchbar")
    buscar(pagina, "mahomes")
    esperar(pagina, "document.querySelector('[data-busca-jogador]')")
    pagina.click("[data-busca-jogador]")
    esperar(pagina, "document.getElementById('jogadores').classList.contains('active') && document.querySelector('#radarSlot')")
    assert "PATRICK MAHOMES" in pagina.inner_text("#scoutBody").upper()
    buscar(pagina, "chandler jones")
    esperar(pagina, "document.querySelector('#searchResults [data-game]')")
    jogo = pagina.eval_on_selector("#searchResults [data-game]", "b => b.dataset.game")
    pagina.click("#searchResults [data-game]")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active') && document.querySelector('#jogoCab .jogo-cab')")
    assert f"game={jogo}" in pagina.url and pagina.is_hidden("#searchResults")


def test_ui_busca_nada_encontrado(servidor, pagina):
    """8.4, com o termo escapado (S.1)."""
    abrir(pagina, servidor.url)
    buscar(pagina, "<img src=x onerror=window.__xss=1>")
    esperar(pagina, "document.querySelector('#searchResults .sr-empty')")
    assert pagina.inner_text("#searchResults .sr-empty") == "Nada encontrado para “<img src=x onerror=window.__xss=1>”."
    assert pagina.query_selector("#searchResults img") is None and pagina.evaluate("window.__xss") is None


def test_ui_busca_resposta_antiga_descartada(servidor, contexto):
    """8.5: a busca por "ma" demora; a por "mahomes" chega antes e é a que fica."""
    contexto.add_init_script(EMBRULHO_FETCH)
    pg = contexto.new_page()
    abrir(pg, servidor.url, "?season=2021&week=1")
    pg.evaluate("window.__atraso['q=ma&'] = 900")
    pg.click("#btnSearch")
    pg.type("#searchInput", "ma")
    pg.wait_for_timeout(350)                                           # passa a espera de 200 ms: "ma" sai
    pg.type("#searchInput", "homes")
    esperar(pg, "[...document.querySelectorAll('[data-busca-jogador] b')].some((b) => /mahomes/i.test(b.textContent))")
    pg.wait_for_timeout(1000)                                          # a resposta velha de "ma" já chegou
    nomes = pg.eval_on_selector_all("[data-busca-jogador] b", "bs => bs.map(b => b.textContent)")
    assert nomes == ["Patrick Mahomes"]


def test_ui_busca_cancelar_e_esc_limpam(servidor, pagina):
    """8.6."""
    abrir(pagina, servidor.url)
    buscar(pagina, "chiefs")
    esperar(pagina, "!document.getElementById('searchResults').hidden")
    pagina.click("#btnSearchClose")
    assert pagina.is_hidden("#searchbar") and pagina.is_hidden("#searchResults")
    assert pagina.input_value("#searchInput") == ""
    buscar(pagina, "chiefs")
    esperar(pagina, "!document.getElementById('searchResults').hidden")
    pagina.keyboard.press("Escape")
    assert pagina.is_hidden("#searchbar") and pagina.input_value("#searchInput") == ""
    assert pagina.evaluate("document.activeElement.id") == "btnSearch"
    pagina.click("#btnSearch")                                         # reabre vazia
    assert pagina.input_value("#searchInput") == "" and pagina.is_hidden("#searchResults")


def test_ui_busca_corta_em_100_caracteres(servidor, pagina):
    """S.2: só os 100 primeiros caracteres (o campo também tem maxlength)."""
    pedidos = []
    pagina.on("request", lambda r: pedidos.append(r.url) if "/api/players?" in r.url else None)
    abrir(pagina, servidor.url)
    pagina.click("#btnSearch")
    assert pagina.get_attribute("#searchInput", "maxlength") == "100"
    pagina.evaluate("""() => { const i = document.getElementById('searchInput');
        i.value = 'a'.repeat(150); i.dispatchEvent(new Event('input', { bubbles: true })); }""")
    esperar(pagina, "document.querySelector('#searchResults .sr-empty, #searchResults [data-busca-jogador]')")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(pedidos[-1]).query)["q"][0]
    assert q == "a" * 100


# ================================================================ Tarefa 8: Configurações e Sobre
def abrir_config(pg, base):
    abrir(pg, base)
    ir_para(pg, "config")
    esperar(pg, "document.getElementById('cfgAvanco')")


def config_salva(pg):
    return pg.evaluate("JSON.parse(localStorage.getItem('nfl.config.v2') || 'null')")


def test_ui_menu_abre_configuracoes(servidor, pagina):
    """11.1."""
    abrir_config(pagina, servidor.url)
    assert pagina.inner_text("#pageTitle").strip().lower() == "configurações"
    assert "config" in pagina.url


def test_ui_configuracoes_dois_controles(servidor, pagina):
    """11.2: avanço automático das notícias e velocidade do Replay (0,5×, 1× ou 2×), com os padrões."""
    abrir_config(pagina, servidor.url)
    assert pagina.get_attribute("#cfgAvanco", "role") == "switch"
    assert pagina.get_attribute("#cfgAvanco", "aria-checked") == "true"
    vels = pagina.eval_on_selector_all("[data-vel]", "rs => rs.map(r => [r.innerText, r.getAttribute('aria-checked')])")
    assert vels == [["0,5×", "false"], ["1×", "true"], ["2×", "false"]]
    pagina.click("[data-vel='0.5']")
    assert config_salva(pagina) == {"avancoNoticias": True, "velocidadeReplay": 0.5}
    pagina.focus("[data-vel='0.5']")                                    # setas no grupo
    pagina.keyboard.press("ArrowRight")
    pagina.keyboard.press("ArrowRight")
    assert config_salva(pagina)["velocidadeReplay"] == 2
    assert pagina.evaluate("document.activeElement.dataset.vel") == "2"
    pagina.click("#cfgAvanco")
    assert pagina.get_attribute("#cfgAvanco", "aria-checked") == "false"
    assert config_salva(pagina) == {"avancoNoticias": False, "velocidadeReplay": 2}


def test_ui_configuracao_aplica_sem_recarregar(servidor, pagina):
    """11.3: o Replay passa a 0,5× (2,8 s por jogada) e o carrossel para, sem recarregar."""
    pagina.clock.install(time=AGORA)
    abrir_jogo(pagina, servidor.url, JOGO + "&aba=replay")
    esperar(pagina, "document.getElementById('bcPlay')")
    pagina.click("#bcPlay")
    pagina.clock.fast_forward(1500)
    esperar(pagina, "document.getElementById('bcPos').textContent.startsWith('2/')")
    pagina.evaluate("import('/js/config.js').then((m) => m.gravar({ velocidadeReplay: 0.5 }))")   # com o Replay andando
    pagina.clock.fast_forward(2000)
    assert pagina.inner_text("#bcPos").startswith("2/")
    pagina.clock.fast_forward(1000)
    esperar(pagina, "document.getElementById('bcPos').textContent.startsWith('3/')")
    pagina.click("#bcPlay")
    ir_para(pagina, "config")
    pagina.click("#cfgAvanco")                                         # desliga o avanço
    ir_para(pagina, "inicio")
    esperar(pagina, "document.querySelectorAll('#heroDots button').length > 1")
    pagina.clock.fast_forward(12000)
    assert ponto_ativo(pagina) == 0
    ir_para(pagina, "config")
    pagina.click("#cfgAvanco")                                         # liga de novo
    ir_para(pagina, "inicio")
    esperar(pagina, "document.querySelectorAll('#heroDots button').length > 1")
    pagina.clock.fast_forward(5200)
    assert ponto_ativo(pagina) == 1


def test_ui_configuracao_persiste_ao_recarregar(servidor, pagina):
    """11.4."""
    abrir_config(pagina, servidor.url)
    pagina.click("[data-vel='2']")
    pagina.click("#cfgAvanco")
    pagina.reload()
    esperar(pagina, "document.getElementById('cfgAvanco')")
    assert pagina.get_attribute("#cfgAvanco", "aria-checked") == "false"
    assert pagina.get_attribute("[data-vel='2']", "aria-checked") == "true"


def test_ui_configuracao_avisa_movimento_reduzido(servidor, navegador):
    ctx = navegador.new_context(viewport={"width": 430, "height": 860}, reduced_motion="reduce")
    pg = ctx.new_page()
    abrir(pg, servidor.url, "?screen=config")
    esperar(pg, "document.getElementById('cfgAvanco')")
    assert pg.is_visible("#cfgMovimento")
    ctx.close()


def test_ui_sobre_mostra_fontes_e_ultima_atualizacao(servidor, pagina):
    """2.3 e o "Sobre" da dados-externos, adaptado."""
    abrir(pagina, servidor.url)
    ir_para(pagina, "sobre")
    t = pagina.inner_text("#sobreDados")
    assert "nflverse" in t and "CC-BY-4.0" in t and "ESPN" in t and "FTN Data" in t
    assert "Última atualização:" in t and "sem registro" not in t
    meta = api(servidor.url, "/api/meta")
    assert pagina.eval_on_selector_all("#sobreDados .fonte", "fs => fs.length") == len(meta["fontes"])
    anos = [s["season"] for s in meta["seasons"]]
    assert f"Temporadas {min(anos)} a {max(anos)}" in t


# ================================================================ Tarefa 9: troca, nomes antigos e acessibilidade
PERCURSO = [
    # (nome, query, preparo em JS depois de abrir, condição de pronto)
    ("inicio", "?season=2021&week=1", None, "document.querySelector('#jogosLista .match') && document.querySelector('#heroTrack .slide')"),
    ("prancheta", "?season=2021&week=1&game=2021090900&screen=jogo&play=55", None,
     "document.querySelectorAll('#field .player-dot').length > 20"),
    ("jogadas", "?season=2021&week=1&game=2021090900&screen=jogo&aba=jogadas", None, "document.querySelector('.play-row')"),
    ("replay", "?season=2021&week=1&game=2021090900&screen=jogo&aba=replay", None, "document.querySelector('.tl-item')"),
    ("estatisticas", "?season=2021&week=1&game=2021090900&screen=jogo&aba=estatisticas", None, "document.querySelector('#jogoCorpo .cmp')"),
    ("playbook", "?season=2021&week=1&game=2021090900&screen=jogo&aba=playbook", None, "document.querySelector('#jogoCorpo .tend')"),
    ("jogadores", "?season=2021&week=1&game=2021090900&screen=jogadores", None,
     "document.querySelector('#scoutBody .row-card') && document.querySelector('.watch-card')"),
    ("perfil", "?season=2021&week=1&screen=jogadores&jogador=00-0019596", None, "document.querySelector('#radarSlot svg')"),
    ("noticias", "?season=2021&week=1&screen=noticias", None, "document.querySelector('.news-item')"),
    ("config", "?screen=config", None, "document.getElementById('cfgAvanco')"),
    ("sobre", "?screen=sobre", None, "document.querySelector('#sobreDados .fonte')"),
    ("menu", "?season=2021&week=1", "document.getElementById('btnMenu').click()",
     "document.getElementById('sidebar').classList.contains('open')"),
    ("busca", "?season=2021&week=1", """(() => { document.getElementById('btnSearch').click();
        const i = document.getElementById('searchInput'); i.value = 'buc';
        i.dispatchEvent(new Event('input', { bubbles: true })); })()""",
     "document.querySelector('[data-busca-jogador]') && document.querySelector('#searchResults [data-game]')"),
]


def percorrer(pg, base, nome):
    _, q, preparo, pronto = next(p for p in PERCURSO if p[0] == nome)
    abrir(pg, base, q)
    if preparo:
        pg.evaluate(preparo)
    esperar(pg, pronto)
    pg.wait_for_timeout(350)                                           # fim das transições


ALVOS_PEQUENOS = """() => {
  const sel = 'button, a[href], input, select, [role=button], [tabindex="0"]';
  return [...document.querySelectorAll(sel)].filter((e) => {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('[hidden], [inert]');
  }).map((e) => {
    const r = e.getBoundingClientRect();
    let w = r.width, h = r.height;
    if (e.classList.contains('player-dot')) {          // o ponto de 26 px tem a área de toque no ::after
      const a = getComputedStyle(e, '::after');
      w = Math.max(w, parseFloat(a.width) || 0); h = Math.max(h, parseFloat(a.height) || 0);
    }
    return { w: Math.round(w), h: Math.round(h), e: e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' +
      String(e.className).replace(/ /g, '.') + ' "' + (e.textContent || '').trim().slice(0, 24) + '"' };
  }).filter((x) => x.w < 44 || x.h < 44);
}"""

CONTRASTE_BAIXO = """(minimo) => {
  const cor = (c) => { const m = /rgba?\\(([^)]+)\\)/.exec(c || ''); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const mistura = (a, b) => [0, 1, 2].map((i) => a[i] * a[3] + b[i] * (1 - a[3])).concat(1);
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const razao = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // Fundo efetivo: as camadas de cima para baixo até uma opaca. De um gradiente vale a 1ª cor
  // (a mais clara nos do app: o pior caso para texto claro).
  const fundo = (el) => {
    const camadas = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage.includes('gradient')) { const m = /rgba?\\([^)]+\\)/.exec(cs.backgroundImage); if (m) camadas.push(cor(m[0])); }
      const bc = cor(cs.backgroundColor);
      if (bc && bc[3] > 0) camadas.push(bc);
      if (camadas.length && camadas[camadas.length - 1][3] >= 1) break;
    }
    let base = [3, 6, 12, 1];
    for (let i = camadas.length - 1; i >= 0; i--) base = mistura(camadas[i], base);
    return base;
  };
  const ruins = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (el.closest('svg, [hidden], [inert], [aria-hidden="true"], script, style')) return;
    const temTexto = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!temTexto) return;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden') return;
    let op = 1;
    for (let e = el; e; e = e.parentElement) op *= Number(getComputedStyle(e).opacity);
    const c = cor(cs.color); c[3] *= op;
    const bg = fundo(el);
    const k = razao(mistura(c, bg), bg);
    if (k < minimo) ruins.push(el.tagName.toLowerCase() + '.' + String(el.className).replace(/ /g, '.') + ' "' +
      el.textContent.trim().slice(0, 24) + '" ' + k.toFixed(2));
  });
  return ruins;
}"""


@pytest.mark.parametrize("tela", ["inicio", "jogo", "jogadores", "noticias", "config", "sobre"])
def test_ui_nomes_antigos_ausentes(servidor, pagina, tela):
    """2.4 e 9.2: nenhuma tela (nem o menu) mostra Treinador, Olheiro ou Comentarista."""
    abrir(pagina, servidor.url, f"?season=2021&week=1&game=2021090900&screen={tela}")
    esperar(pagina, "!document.querySelector('.screen.active .state.loading')")
    pagina.click("#btnMenu")
    esperar(pagina, "document.getElementById('sidebar').classList.contains('open')")
    corpo = pagina.inner_text("body")
    for antigo in ("Treinador", "Olheiro", "Comentarista", "TREINADOR", "OLHEIRO", "COMENTARISTA"):
        assert antigo not in corpo, antigo


def test_ui_sem_sugestoes_de_tatica(servidor, pagina):
    """9.1: nem o título, nem o conteúdo (o campo insights segue na API, ignorado)."""
    for nome in ("inicio", "prancheta", "jogadores"):
        percorrer(pagina, servidor.url, nome)
        assert "Sugestões de tática".upper() not in pagina.inner_text("body").upper()
        assert pagina.query_selector("#insightsSec, .tip-card") is None


def test_ui_sem_bastidores(servidor, pagina):
    """9.2."""
    for nome in ("inicio", "prancheta", "noticias"):
        percorrer(pagina, servidor.url, nome)
        assert "Bastidores".upper() not in pagina.inner_text("body").upper()
        assert pagina.query_selector("#notesSec, .news-card") is None


@pytest.mark.parametrize("nome", [p[0] for p in PERCURSO])
def test_ui_alvos_de_toque_44px(servidor, pagina, nome):
    """NFR 3."""
    percorrer(pagina, servidor.url, nome)
    assert pagina.evaluate(ALVOS_PEQUENOS) == []


@pytest.mark.parametrize("nome", [p[0] for p in PERCURSO])
def test_ui_contraste_minimo(servidor, pagina, nome):
    """NFR 4: todo texto com pelo menos 4,5:1 sobre o fundo efetivo."""
    percorrer(pagina, servidor.url, nome)
    assert pagina.evaluate(CONTRASTE_BAIXO, 4.5) == []


def test_ui_contraste_dos_escudos_de_todos_os_times(servidor, pagina):
    """NFR 4 nos escudos: o texto (branco ou escuro) contrasta 4,5:1 com a cor de cada um dos 32 times."""
    abrir(pagina, servidor.url)
    ruins = pagina.evaluate("""async () => {
        const ui = await import('/js/ui.js');
        const meta = await (await fetch('/api/meta')).json();
        return Object.values(meta.teams).filter((t) => { const c = ui.corLegivel(t.primary); return ui.contraste(c.fundo, c.texto) < 4.5; })
            .map((t) => t.abbr + ' ' + t.primary);
    }""")
    assert ruins == []


FOCO = """() => { const e = document.activeElement, cs = getComputedStyle(e);
  return { id: e.id, cls: String(e.className), texto: (e.textContent || '').trim().slice(0, 20),
           visivel: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2 }; }"""


def test_ui_navegacao_por_teclado(servidor, pagina):
    """NFR 5: da barra ao destino só com o teclado, e o foco sempre visível."""
    abrir(pagina, servidor.url, "?season=2021&week=1")
    esperar(pagina, "document.querySelector('#jogosLista .match')")
    vistos = []
    for _ in range(60):                                                # o começo da página, pelo Tab
        pagina.keyboard.press("Tab")
        f = pagina.evaluate(FOCO)
        vistos.append(f)
        assert f["visivel"], f"foco sem contorno visível em {f}"
    assert any("match" in f["cls"] for f in vistos), [f["cls"] for f in vistos]
    # uma partida pelo teclado abre a página Jogo; as abas vão pelas setas
    pagina.focus("#jogosLista .match")
    pagina.keyboard.press("Enter")
    esperar(pagina, "document.getElementById('jogo').classList.contains('active') && document.getElementById('aba-prancheta')")
    pagina.focus("#aba-prancheta")
    pagina.keyboard.press("ArrowRight")
    esperar(pagina, "document.activeElement.id === 'aba-jogadas'")
    assert pagina.evaluate(FOCO)["visivel"]
    # um jogador da prancheta pelo teclado
    pagina.keyboard.press("ArrowLeft")
    esperar(pagina, "document.querySelectorAll('#field .player-dot:not(.ball)').length > 20")
    pagina.focus("#field .player-dot:not(.ball)")
    assert pagina.evaluate(FOCO)["visivel"]
    pagina.keyboard.press("Enter")
    esperar(pagina, "document.querySelector('#dotInfo .row-card')")
    # menu lateral e Configurações pelo teclado
    pagina.focus("#btnMenu")
    pagina.keyboard.press("Enter")
    esperar(pagina, "document.activeElement.closest('#sidebar')")
    for _ in range(8):
        if pagina.evaluate("document.activeElement.dataset.go") == "config":
            break
        pagina.keyboard.press("Tab")
    pagina.keyboard.press("Enter")
    esperar(pagina, "document.getElementById('cfgAvanco')")
    pagina.focus("#cfgAvanco")
    pagina.keyboard.press("Space")
    assert pagina.get_attribute("#cfgAvanco", "aria-checked") == "false"
    assert pagina.evaluate(FOCO)["visivel"]


XSS = '<img src=x onerror="window.__xss=1">'


def test_ui_texto_do_dado_nao_vira_html(servidor, pagina):
    """S.1: nomes, manchetes e descrições com marcação aparecem como texto em todas as telas."""
    jogos = api(servidor.url, "/api/games?season=2021&week=1")
    jogos[0]["home"]["nick"] = XSS + "Bucs"
    news = api(servidor.url, "/api/news?season=2021&week=1")
    news[0]["titulo"] = XSS + "Manchete"
    news[0]["texto"] = "<b>texto</b>"
    jogadores = api(servidor.url, "/api/players?season=2021&limit=60")
    jogadores[0]["name"] = XSS + "Jogador"
    plays = api(servidor.url, "/api/games/2021090900/plays")
    for p in plays:
        p["description"] = XSS + p["description"]
    jogo = api(servidor.url, "/api/games/2021090900")
    jogo["stadium"] = XSS + "Estádio"
    jogo["watch"][0]["name"] = XSS + "Destaque"

    def responder(corpo):
        return lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(corpo))

    pagina.route("**/api/games?season=2021&week=1", responder(jogos))
    pagina.route("**/api/news?season=2021&week=1", responder(news))
    pagina.route("**/api/players?season=2021&limit=60", responder(jogadores))
    pagina.route("**/api/games/2021090900/plays", responder(plays))
    pagina.route("**/api/games/2021090900", responder(jogo))
    abrir(pagina, servidor.url, "?season=2021&week=1&game=2021090900")
    esperar(pagina, "document.querySelector('#jogosLista .match') && document.querySelector('#heroTrack .slide')")
    ir_para(pagina, "noticias")
    esperar(pagina, "document.querySelector('.news-item')")
    ir_para(pagina, "jogo")
    pagina.click("#jogoAbas [data-aba=jogadas]")
    esperar(pagina, "document.querySelector('.play-row') && document.querySelector('#jogoCab .jogo-cab')")
    ir_para(pagina, "jogadores")
    esperar(pagina, "document.querySelector('#scoutBody .row-card') && document.querySelector('.watch-card')")
    corpo = pagina.text_content("body")                                # as telas visitadas guardam o HTML
    for marca in ("Bucs", "Manchete", "Jogador", "Destaque", "Estádio"):
        assert XSS + marca in corpo, marca
    assert "<b>texto</b>" in corpo
    assert pagina.query_selector(".screen img") is None
    assert pagina.eval_on_selector_all(".screen b", "bs => bs.filter(b => b.textContent === 'texto').length") == 0
    assert pagina.evaluate("window.__xss") is None
