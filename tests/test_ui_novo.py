"""
Spec novo-visual: a interface nova (app/novo.html), num Edge headless real.

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
    pg.goto(base + "/novo.html" + query)
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
    for sel in ("#btnMenu", ".topbar .shield", "#btnSearch"):
        assert pagina.is_visible(sel), sel
    assert pagina.inner_text("#pageTitle").strip().lower() == TELAS[tela].lower()


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
    pg.goto(servidor.url + "/novo.html", wait_until="commit")
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
        const meta = await (await fetch('/api/meta')).json();
        const t = (a) => meta.teams[a];
        return [m.coresDosLados({ offense: 'SEA', defense: 'NE' }, t), m.coresDosLados({ offense: 'TB', defense: 'DAL' }, t),
                m.coresDosLados({}, t), m.fundoClaro('#FFB612'), m.fundoClaro('#002244')];
    }""")
    meta = api(servidor.url, "/api/meta")["teams"]
    assert r[0] == {"offense": meta["SEA"]["primary"], "defense": meta["NE"]["secondary"]}
    assert r[1] == {"offense": meta["TB"]["primary"], "defense": meta["DAL"]["primary"]}
    assert r[2] == {} and r[3] is True and r[4] is False
