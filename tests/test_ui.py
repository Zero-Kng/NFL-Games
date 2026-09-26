"""
Spec otimizacao-desempenho, tarefa 8: comportamento do navegador (3.x, 4.1, 4.5,
5.x) num Edge headless real. Desde a spec novo-visual (tarefa 9), roda sobre a
interface nova: os links antigos (?screen=coach|scout) abrem a pagina Jogo e a
tela Jogadores.

Latencia e falha sao simuladas embrulhando o fetch da pagina (window.__atraso e
window.__falharUmaVez), o que deixa cada cenario deterministico. Os tempos sao
medidos dentro da propria pagina (performance.now), sem o overhead do Playwright.
"""

import json
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")

SEMANA = 1


def jogo(base):
    """O 1o jogo da semana 1 da temporada padrao: o que a tela abre com ?week=1.
    (O seletor de temporada, e o ?season= no link, entram na tarefa 7 da spec dados-externos.)"""
    with urllib.request.urlopen(f"{base}/api/games?week={SEMANA}") as r:
        return json.load(r)[0]["gameId"]

# Injetado antes de qualquer script da pagina.
EMBRULHO_FETCH = """
window.__atraso = {};          // {trecho_da_url: ms}
window.__falharUmaVez = [];    // [trecho_da_url]  -> falha so na 1a vez
const _fetch = window.fetch.bind(window);
window.fetch = async (url, opts) => {
  const u = String(url);
  const i = window.__falharUmaVez.findIndex((t) => u.includes(t));
  if (i >= 0) { window.__falharUmaVez.splice(i, 1); throw new TypeError('falha simulada: ' + u); }
  const r = await _fetch(url, opts);
  for (const t in window.__atraso) {
    if (u.includes(t)) await new Promise((ok) => setTimeout(ok, window.__atraso[t]));
  }
  return r;
};
"""

ESPERAR = """async ([cond, limite]) => {
  const f = new Function('return (' + cond + ')');
  const t0 = performance.now();
  while (!f()) {
    if (performance.now() - t0 > limite) return -1;
    await new Promise((ok) => setTimeout(ok, 2));
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
    ctx = navegador.new_context()
    ctx.add_init_script(EMBRULHO_FETCH)
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    yield pg
    ctx.close()
    assert erros == [], f"erros de JavaScript na pagina: {erros}"


def esperar(pg, cond: str, limite_ms: int = 10000) -> float:
    ms = pg.evaluate(ESPERAR, [cond, limite_ms])
    assert ms >= 0, f"condicao nao aconteceu em {limite_ms} ms: {cond}"
    return ms


def jogadas_com_tracking(base):
    with urllib.request.urlopen(f"{base}/api/games/{jogo(base)}/plays") as r:
        return [p["playId"] for p in json.load(r) if p["hasFormation"]]


def abrir_prancheta(pg, base):
    pg.goto(f"{base}/?week={SEMANA}&game={jogo(base)}&screen=coach")
    esperar(pg, "document.querySelectorAll('#field .player-dot').length > 10")


def escolher_jogada(pg, play_id):
    pg.evaluate("""(id) => {
        const s = document.getElementById('playPick');
        s.value = String(id);
        s.dispatchEvent(new Event('change', { bubbles: true }));
    }""", play_id)


DESCRICAO = "document.querySelector('.play-desc') && document.querySelector('.play-desc').textContent"


# ------------------------------------------------------------------ 4.1 ----
MARCAR_PRONTA = """
// Registra o instante (desde o inicio da navegacao) em que a home fica pronta.
new MutationObserver((_m, obs) => {
  // Pronta = partidas, notícias do carrossel e os dois cartões preenchidos.
  if (document.querySelector('#jogosLista .match') && document.querySelector('#heroTrack .slide') &&
      /[0-9]/.test((document.getElementById('tileAvaliados') || {}).textContent || '')) {
    window.__prontaEm = performance.now();
    obs.disconnect();
  }
}).observe(document, { childList: true, subtree: true });
"""


def test_ui_home_pronta_ate_200ms(servidor, navegador):
    # Contexto novo, sem nada em cache do navegador. A 1a visita aquece a
    # conexao; mede-se a 2a (as fontes externas nao entram: nao bloqueiam mais).
    ctx = navegador.new_context()
    ctx.add_init_script(MARCAR_PRONTA)
    pg = ctx.new_page()
    try:
        tempos, redes = [], []
        for _ in range(3):
            pg.goto(servidor.url + "/?week=1", wait_until="commit")
            esperar(pg, "window.__prontaEm !== undefined")
            tempos.append(pg.evaluate("window.__prontaEm"))
            # Linha do tempo de cada pedido: se o teste falhar, mostra onde travou.
            redes.append(pg.evaluate("""() => performance.getEntriesByType('resource').map((e) =>
                e.name.replace(location.origin, '').slice(0, 45) + ' ' +
                Math.round(e.startTime) + '-' + Math.round(e.responseEnd) + 'ms')"""))
        mediana = sorted(tempos)[1]
        assert mediana <= 200, f"home pronta em {[round(t) for t in tempos]} ms; pedidos: {redes}"
    finally:
        ctx.close()


# ------------------------------------------------------------------ 4.5 ----
def test_ui_sem_fontes_externas_renderiza(servidor, pagina):
    # O servidor de fontes "trava": o pedido nunca e respondido.
    pagina.route("**/fonts.googleapis.com/**", lambda route: None)
    pagina.route("**/fonts.gstatic.com/**", lambda route: None)
    pagina.goto(servidor.url + "/?week=1", wait_until="commit")
    esperar(pagina, "document.querySelectorAll('#jogosLista .match').length > 0", 3000)
    pronta = pagina.evaluate("performance.now()")
    assert pronta <= 1000, f"com a fonte travada a home levou {pronta:.0f} ms"


# ------------------------------------------------------------------ 3.1 ----
def test_ui_proxima_jogada_ate_50ms(servidor, pagina):
    abrir_prancheta(pagina, servidor.url)
    pagina.wait_for_timeout(500)  # tempo da pre-carga das vizinhas
    tempos = []
    for _ in range(3):
        antes = pagina.evaluate(DESCRICAO)
        pagina.click("#nextPlay")
        tempos.append(esperar(pagina, f"({DESCRICAO}) && ({DESCRICAO}) !== {json.dumps(antes)} && "
                                      "document.querySelectorAll('#field .player-dot').length > 10"))
        pagina.wait_for_timeout(300)
    # O clique do Playwright tambem entra na medida, entao ela e conservadora.
    assert sorted(tempos)[1] <= 50, f"proxima jogada: {tempos} ms"


# ------------------------------------------------------------------ 3.2 ----
def test_ui_troca_rapida_mostra_so_a_ultima_jogada(servidor, pagina):
    ids = jogadas_com_tracking(servidor.url)
    b, c = ids[10], ids[20]  # longe da 1a jogada: nao estao pre-carregadas
    abrir_prancheta(pagina, servidor.url)
    escolher_jogada(pagina, c)
    esperar(pagina, f"document.getElementById('playPick').value === '{c}' && ({DESCRICAO})")
    pagina.wait_for_timeout(100)
    descricao_c = pagina.evaluate(DESCRICAO)
    escolher_jogada(pagina, ids[0])
    esperar(pagina, f"({DESCRICAO}) !== {json.dumps(descricao_c)}")

    # B demora 800 ms; o usuario desiste e escolhe C (que ja esta em cache).
    pagina.evaluate(f"window.__atraso['/plays/{b}/tracking'] = 800")
    escolher_jogada(pagina, b)
    pagina.wait_for_timeout(50)
    escolher_jogada(pagina, c)
    pagina.wait_for_timeout(1200)  # B ja chegou
    assert pagina.evaluate(DESCRICAO) == descricao_c
    assert pagina.evaluate("document.getElementById('playPick').value") == str(c)


# ------------------------------------------------------------------ 3.3 ----
def test_ui_prefetch_falho_carrega_normal(servidor, pagina):
    ids = jogadas_com_tracking(servidor.url)
    # Roda depois do embrulho do fetch: a pre-carga da jogada seguinte vai falhar.
    pagina.add_init_script(f"window.__falharUmaVez = ['/plays/{ids[1]}/tracking'];")
    abrir_prancheta(pagina, servidor.url)
    pagina.wait_for_timeout(500)  # a pre-carga de ids[1] falhou em silencio
    assert pagina.evaluate("window.__falharUmaVez.length") == 0, "a pre-carga nao chegou a ser tentada"
    assert pagina.locator(".state.error").count() == 0
    pagina.click("#nextPlay")
    esperar(pagina, f"document.getElementById('playPick') && document.getElementById('playPick').value === '{ids[1]}' "
                    "&& document.querySelectorAll('#field .player-dot').length > 10")
    assert pagina.locator(".state.error").count() == 0


# ------------------------------------------------------------------ 3.4 ----
def test_ui_prefetch_so_depois_da_jogada_escolhida(servidor, pagina):
    ids = jogadas_com_tracking(servidor.url)
    abrir_prancheta(pagina, servidor.url)
    pagina.wait_for_timeout(500)
    rede = pagina.evaluate("""() => performance.getEntriesByType('resource')
        .filter((e) => e.name.includes('/tracking'))
        .map((e) => ({ url: e.name, inicio: e.startTime, fim: e.responseEnd }))""")
    escolhida = next(r for r in rede if f"/plays/{ids[0]}/tracking" in r["url"])
    vizinhas = [r for r in rede if f"/plays/{ids[1]}/tracking" in r["url"]]
    assert vizinhas, "a jogada seguinte nao foi pre-carregada"
    assert all(v["inicio"] >= escolhida["fim"] for v in vizinhas)


# ------------------------------------------------------------ 5.1 / 5.2 ----
def _abrir_olheiro(pg, base):
    pg.goto(base + "/?screen=scout")
    esperar(pg, "document.querySelectorAll('#scoutBody .row-card').length > 0")


def _nomes(pg):
    return pg.evaluate("[...document.querySelectorAll('#scoutBody .row-card b')].map((b) => b.textContent)")


def test_ui_busca_mostra_texto_final(servidor, pagina):
    _abrir_olheiro(pagina, servidor.url)
    pagina.type("#scoutSearch", "mahomes", delay=30)
    esperar(pagina, "[...document.querySelectorAll('#scoutBody .row-card b')].some((b) => /mahomes/i.test(b.textContent))")
    assert all("mahomes" in n.lower() for n in _nomes(pagina))


def test_ui_busca_resposta_antiga_descartada(servidor, pagina):
    _abrir_olheiro(pagina, servidor.url)
    # A busca por "ma" demora; a por "mahomes" chega antes dela.
    pagina.evaluate("window.__atraso['q=ma&'] = 900")
    pagina.type("#scoutSearch", "ma")
    pagina.wait_for_timeout(400)   # passa o debounce de 280 ms: "ma" sai
    pagina.type("#scoutSearch", "homes")
    esperar(pagina, "[...document.querySelectorAll('#scoutBody .row-card b')].some((b) => /mahomes/i.test(b.textContent))")
    pagina.wait_for_timeout(1000)  # a resposta velha de "ma" ja chegou
    nomes = _nomes(pagina)
    assert nomes and all("mahomes" in n.lower() for n in nomes), nomes
