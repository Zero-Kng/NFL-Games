"""
Spec novo-visual: a interface nova (app/novo.html), num Edge headless real.

Tarefa 2 (casca): identidade do rascunho, cabeçalho, moldura, movimento
reduzido, fontes externas, barra inferior, menu lateral, links antigos,
filtros de temporada e semana e configurações corrompidas.
"""

import json
import re
import urllib.request

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
