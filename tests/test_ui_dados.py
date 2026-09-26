"""
Spec dados-externos, tarefa 7: as telas com os dados do nflverse, num Edge headless real.

Desde a spec novo-visual (tarefa 9), roda sobre a interface nova. Os testes de
cartão de jogo, placar ao vivo, matéria da ESPN, prancheta ilustrativa,
"formação indisponível" e "Sobre os dados" foram adaptados e ficam em
test_ui_novo.py (tarefas 3, 4, 5 e 8), ao lado do que eles cobrem na tela nova.
Aqui ficam os que atravessam telas: temporadas e rodadas de playoff, as quatro
áreas funcionando com os dados novos e nenhum resto do dataset antigo.
"""

import json
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")

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
def pagina(navegador):
    ctx = navegador.new_context(viewport={"width": 430, "height": 860})
    ctx.route("https://site.api.espn.com/**", lambda r: r.fulfill(status=404, body=""))
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    yield pg
    ctx.close()
    assert erros == [], f"erros de JavaScript na pagina: {erros}"


def esperar(pg, cond: str, limite_ms: int = 10000):
    ms = pg.evaluate(ESPERAR, [cond, limite_ms])
    assert ms >= 0, f"condicao nao aconteceu em {limite_ms} ms: {cond}"


def texto(pg, sel: str) -> str:
    return pg.eval_on_selector(sel, "e => e.innerText")


def api(base, caminho):
    with urllib.request.urlopen(base + caminho) as r:
        return json.load(r)


def abrir(pg, base, query=""):
    pg.goto(base + "/" + query)
    esperar(pg, "document.querySelector('.screen.active') && document.querySelectorAll('#seasonChips .chip').length > 0")


def ir_para(pg, tela):
    pg.click(f".nav-item[data-go={tela}]")
    esperar(pg, f"document.getElementById('{tela}').classList.contains('active')")


# ============================================================ 1.2, 8.2 temporada
def test_ui_seletor_de_temporada(servidor, pagina):
    abrir(pagina, servidor.url)
    meta = api(servidor.url, "/api/meta")
    chips = pagina.eval_on_selector_all("#seasonChips .chip", "cs => cs.map(c => Number(c.dataset.season))")
    assert chips == [t["season"] for t in meta["seasons"]] and len(chips) == 6
    pagina.click("#seasonChips [data-season='2021']")
    # a semana padrão de uma temporada encerrada é a mais recente: o Super Bowl (disputado em 2022)
    sb = [str(g["gameId"]) for g in api(servidor.url, "/api/games?season=2021&week=22")]
    esperar(pagina, f"document.querySelector('#jogosLista .match') && document.querySelector('#jogosLista .match').dataset.game === '{sb[0]}'")
    assert "Super Bowl" in texto(pagina, "#jogosConta") and "Super Bowl" in texto(pagina, "#weekChips [aria-pressed=true]")
    assert "Temporada 2021 · Super Bowl" in pagina.text_content("#sidebarSub")


def test_ui_chips_de_playoff(servidor, pagina):
    abrir(pagina, servidor.url, "?season=2024&week=22")
    esperar(pagina, "document.querySelector('#jogosLista .match')")
    chips = pagina.eval_on_selector_all("#weekChips .chip", "cs => cs.map(c => c.textContent)")
    assert chips[0] == "Sem 1" and chips[-4:] == ["Wild Card", "Divisional", "Final de Conferência", "Super Bowl"]
    assert "Super Bowl" in texto(pagina, "#jogosConta")


# ============================================================ 8.x, 3.3, 9.1, 7.4
def test_ui_quatro_areas_funcionam_com_dados_novos(servidor, pagina):
    """O que eram Treinador, Olheiro e Comentarista, agora na página Jogo e em Jogadores."""
    abrir(pagina, servidor.url, "?season=2021&week=1&game=2021090900")
    esperar(pagina, "document.querySelector('#jogosLista .match')")
    ir_para(pagina, "jogo")
    esperar(pagina, "document.querySelectorAll('#field .player-dot').length > 20")
    pagina.click("#jogoAbas [data-aba=replay]")
    esperar(pagina, "document.querySelectorAll('#bcFeed .tl-item').length > 0")
    assert "Cowboys" in texto(pagina, "#bcScore") and "Buccaneers" in texto(pagina, "#bcScore")
    ir_para(pagina, "jogadores")
    esperar(pagina, "document.querySelectorAll('#scoutBody .row-card').length > 10")
    assert "Temporada 2021" in texto(pagina, "#jogadoresBlock")
    pagina.click("#scoutBody .row-card")
    esperar(pagina, "document.getElementById('radarSlot')")


def test_ui_perfil_sem_campos_do_dataset_antigo(servidor, pagina):
    abrir(pagina, servidor.url, "?season=2021&week=1&game=2021090900&screen=jogadores")
    esperar(pagina, "document.querySelector('#observarLista .watch-card')")
    pagina.click("#observarLista .watch-card")
    esperar(pagina, "document.getElementById('radarSlot')")
    perfil = texto(pagina, "#scoutBody")
    assert "mph" not in perfil and "Pico" not in perfil and "undefined" not in perfil and "NaN" not in perfil


@pytest.mark.parametrize("tela", ["inicio", "jogo", "jogadores", "noticias"])
def test_ui_sem_avisos_do_dataset_antigo(servidor, pagina, tela):
    abrir(pagina, servidor.url, "?season=2021&week=1&game=2021090900")
    if tela != "inicio":
        ir_para(pagina, tela)
    esperar(pagina, "!document.querySelector('.screen.active .state.loading')")
    pagina.wait_for_timeout(200)
    corpo = pagina.inner_text("body")
    for antigo in ("Big Data Bowl", "semanas 1–8", "somente jogadas de passe", "aproximado", "PFF", "tracking",
                   "undefined", "NaN"):
        assert antigo not in corpo, antigo
