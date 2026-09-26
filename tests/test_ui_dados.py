"""
Tarefa 7 (dados-externos): as telas atuais com os dados novos, num Edge headless real.

A ESPN (placar ao vivo e matéria) é simulada com page.route(); nos testes do
placar ao vivo, a lista de jogos também, a partir de jogos reais com o status e
o horário controlados. O relógio da página é o do Playwright (page.clock): corre
normalmente e é adiantado de 30 em 30 s com fast_forward.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

playwright = pytest.importorskip("playwright.sync_api")

AGORA = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
ESPN = "https://site.api.espn.com/**"
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
    ctx = navegador.new_context()
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.espn = {"scoreboard": [], "summary": []}      # chamadas feitas à ESPN
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


# ------------------------------------------------------------------ ESPN simulada
def evento(espn_id, state, home, away, period=2, clock="5:21", name=None):
    return {"id": espn_id, "competitions": [{
        "status": {"period": period, "displayClock": clock,
                   "type": {"state": state, "name": name or {"in": "STATUS_IN_PROGRESS", "post": "STATUS_FINAL",
                                                              "pre": "STATUS_SCHEDULED"}[state]}},
        "competitors": [{"homeAway": "home", "score": str(home)}, {"homeAway": "away", "score": str(away)}]}]}


def simular_espn(pg, placares=None, materia=None, status_summary=200):
    """`placares`: lista de respostas do scoreboard, uma por consulta (a última se repete);
    cada uma é uma lista de eventos ou o número de um status HTTP de erro."""
    placares = placares or [[]]

    def rota(route):
        url = route.request.url
        if "/scoreboard" in url:
            n = len(pg.espn["scoreboard"])
            pg.espn["scoreboard"].append(url)
            r = placares[min(n, len(placares) - 1)]
            if isinstance(r, int):
                return route.fulfill(status=r, body="erro simulado")
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"events": r}))
        if "/summary" in url:
            pg.espn["summary"].append(url)
            if status_summary != 200:
                return route.fulfill(status=status_summary, body="erro simulado")
            corpo = {"header": {"competitions": [{"status": {"type": {"state": "post"}}, "competitors": []}]}}
            if materia:
                corpo["article"] = materia
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(corpo))
        return route.fulfill(status=404, body="")

    pg.route(ESPN, rota)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def simular_semana(pg, base, jogos_de):
    """Troca /api/games por jogos reais (2025, semana 1) com status e horários dados.
    `jogos_de`: lista de dicts com os campos a sobrescrever (espnId, status, kickoffUtc, placar)."""
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


def abrir_home(pg, base, url="/"):
    pg.clock.install(time=AGORA)
    pg.goto(base + url)
    esperar(pg, "document.querySelector('.match')")


# ============================================================ 1.2, 8.2 temporada
def test_ui_seletor_de_temporada(servidor, pagina):
    simular_espn(pagina)
    abrir_home(pagina, servidor.url)
    meta = api(servidor.url, "/api/meta")
    opcoes = pagina.eval_on_selector_all("#seasonPick option", "os => os.map(o => Number(o.value))")
    assert opcoes == [t["season"] for t in meta["seasons"]] and len(opcoes) == 6
    pagina.select_option("#seasonPick", "2021")
    esperar(pagina, "document.getElementById('hdrSub').textContent.includes('Temporada 2021')")
    # a semana padrão de uma temporada encerrada é a mais recente: o Super Bowl (disputado em 2022)
    sb = [str(g["gameId"]) for g in api(servidor.url, "/api/games?season=2021&week=22")]
    esperar(pagina, f"document.querySelector('.match') && document.querySelector('.match').dataset.game === '{sb[0]}'")
    assert "Super Bowl" in texto(pagina, "#gamesCount") and "Super Bowl" in texto(pagina, ".week-chip.active")


def test_ui_chips_de_playoff(servidor, pagina):
    simular_espn(pagina)
    abrir_home(pagina, servidor.url, "/?season=2024&week=22")
    chips = pagina.eval_on_selector_all(".week-chip", "cs => cs.map(c => c.firstChild.textContent)")
    assert chips[0] == "SEM 1" and chips[-4:] == ["Wild Card", "Divisional", "Final de Conferência", "Super Bowl"]
    assert "Super Bowl" in texto(pagina, "#gamesCount")


# ============================================================ 1.4, 1.5 cartões
def test_ui_cartao_a_jogar_e_sem_resultado(servidor, pagina):
    simular_espn(pagina, placares=[[]])          # a ESPN ainda não tem nada desses jogos
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=3))},
        {"espnId": "900002", "status": "sem_resultado", "kickoffUtc": iso(AGORA - timedelta(days=1))},
    ])
    abrir_home(pagina, servidor.url)
    cards = pagina.eval_on_selector_all(".match", "ms => ms.map(m => [m.dataset.estado, m.innerText])")
    assert cards[0][0] == "agendado" and "A JOGAR" in cards[0][1] and "–" not in cards[0][1]
    assert cards[1][0] == "sem_resultado" and "resultado ainda não disponível" in cards[1][1]


# ============================================================ 10.x placar ao vivo
def _semana_ao_vivo(pg, base, encerrado_nflverse=None):
    return simular_semana(pg, base, [
        {"espnId": "900001", "status": "sem_resultado", "kickoffUtc": iso(AGORA - timedelta(hours=1))},
        {"espnId": "900002", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=5))},
        encerrado_nflverse or {"espnId": "900003", "status": "encerrado", "placar": (24, 20),
                               "kickoffUtc": iso(AGORA - timedelta(days=3))},
    ])


def test_ui_ao_vivo_placar_quarto_relogio(servidor, pagina):
    simular_espn(pagina, placares=[[evento("900001", "in", 3, 7, period=2, clock="5:21")]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_home(pagina, servidor.url)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    t = texto(pagina, ".match")
    assert "AO VIVO" in t and "Q2 · 5:21" in t and "7" in t and "3" in t


def test_ui_ao_vivo_atualiza_a_cada_30s_e_para_ao_encerrar(servidor, pagina):
    """10.2 e 10.3 com relógio controlado."""
    simular_espn(pagina, placares=[
        [evento("900001", "in", 3, 7, period=2, clock="5:21")],
        [evento("900001", "in", 10, 14, period=3, clock="10:00")],
        [evento("900001", "post", 17, 21, period=4, clock="0:00")],
    ])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_home(pagina, servidor.url)
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q2 · 5:21')")
    assert len(pagina.espn["scoreboard"]) == 1
    pagina.clock.fast_forward(29000)
    pagina.wait_for_timeout(300)
    assert len(pagina.espn["scoreboard"]) == 1                  # ainda não deu 30 s
    pagina.clock.fast_forward(1500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q3 · 10:00')")
    assert len(pagina.espn["scoreboard"]) == 2
    pagina.clock.fast_forward(30000)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'final-espn'")
    assert "FINAL" in texto(pagina, ".match") and "21" in texto(pagina, ".match")
    n = len(pagina.espn["scoreboard"])
    pagina.clock.fast_forward(120000)                          # encerrado: parou de consultar
    pagina.wait_for_timeout(300)
    assert len(pagina.espn["scoreboard"]) == n == 3


def test_ui_sem_jogo_em_andamento_nao_consulta(servidor, pagina):
    """10.4: só jogos a jogar (futuros) e encerrados: nenhuma consulta ao placar ao vivo."""
    simular_espn(pagina)
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(hours=5))},
        {"espnId": "900003", "status": "encerrado", "placar": (24, 20), "kickoffUtc": iso(AGORA - timedelta(days=3))},
    ])
    abrir_home(pagina, servidor.url)
    pagina.clock.fast_forward(90000)
    pagina.wait_for_timeout(300)
    assert pagina.espn["scoreboard"] == []


def test_ui_ao_vivo_comeca_quando_o_jogo_comeca(servidor, pagina):
    """Um jogo a jogar passa a ser consultado quando chega a hora do início."""
    simular_espn(pagina, placares=[[evento("900001", "in", 0, 7, period=1, clock="9:00")]])
    simular_semana(pagina, servidor.url, [
        {"espnId": "900001", "status": "agendado", "kickoffUtc": iso(AGORA + timedelta(minutes=10))},
    ])
    abrir_home(pagina, servidor.url)
    assert pagina.espn["scoreboard"] == []
    pagina.clock.fast_forward(11 * 60 * 1000)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")


def test_ui_ao_vivo_falha_mantem_ultimo_placar(servidor, pagina):
    """10.5: a falha mostra o último placar com o aviso e tenta de novo em 30 s."""
    simular_espn(pagina, placares=[
        [evento("900001", "in", 3, 7)],
        503,
        [evento("900001", "in", 3, 14, period=3, clock="12:00")],
    ])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_home(pagina, servidor.url)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    pagina.clock.fast_forward(30500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('atualização ao vivo indisponível')")
    t = texto(pagina, ".match")
    assert "AO VIVO" in t and "Q2 · 5:21" in t                  # o último placar conhecido
    pagina.clock.fast_forward(30500)
    esperar(pagina, "document.querySelector('.match').innerText.includes('Q3 · 12:00')")
    assert "indisponível" not in texto(pagina, ".match")


def test_ui_encerrado_prevalece_nflverse(servidor, pagina):
    """10.6: com o placar oficial do nflverse, a ESPN não muda o cartão."""
    simular_espn(pagina, placares=[[evento("900001", "in", 3, 7), evento("900003", "in", 10, 3)]])
    _semana_ao_vivo(pagina, servidor.url)
    abrir_home(pagina, servidor.url)
    esperar(pagina, "document.querySelector('.match').dataset.estado === 'aovivo'")
    terceiro = pagina.eval_on_selector_all(".match", "ms => [ms[2].dataset.estado, ms[2].innerText]")
    assert terceiro[0] == "final" and "24" in terceiro[1] and "20" in terceiro[1] and "AO VIVO" not in terceiro[1]


# ============================================================ 6.x, S.1, S.4 matéria
MATERIA = {"headline": "Brady lança 4 TDs e Bucs vencem", "description": "Tom Brady não piscou.",
           "published": "2021-09-10T06:32:45Z", "source": "AP",
           "links": {"web": {"href": "http://www.espn.com/nfl/recap?gameId=401326322"}}}


def abrir_jogo_2021(pg, base):
    abrir_home(pg, base, "/?season=2021&week=1&game=2021090900")


def test_ui_materia_titulo_resumo_data_fonte_e_link(servidor, pagina):
    simular_espn(pagina, materia=MATERIA)
    abrir_jogo_2021(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    t = texto(pagina, "#materia")
    assert "Brady lança 4 TDs e Bucs vencem" in t and "Tom Brady não piscou." in t
    assert "10/09/2021" in t and "AP · ESPN" in t
    href = pagina.eval_on_selector("#materia a", "a => a.href")
    assert href == "https://www.espn.com/nfl/recap?gameId=401326322"          # http -> https
    assert "event=401326322" in pagina.espn["summary"][0]


@pytest.mark.parametrize("caso", ["erro", "sem_materia"])
def test_ui_materia_indisponivel_some(servidor, pagina, caso):
    simular_espn(pagina, materia=None, status_summary=500 if caso == "erro" else 200)
    abrir_jogo_2021(pagina, servidor.url)
    esperar(pagina, "document.getElementById('personaLead').innerText.includes('DAL @ TB')")
    pagina.wait_for_timeout(300)
    assert pagina.eval_on_selector("#materia", "m => m.hidden") is True
    assert "Partidas".upper() in texto(pagina, "#home").upper()                  # o resto da página segue


@pytest.mark.parametrize("href", ["https://evil.example.com/nfl/recap", "javascript:alert(1)",
                                  "https://espn.com.evil.io/x"])
def test_ui_link_fora_da_espn_nao_exibido(servidor, pagina, href):
    simular_espn(pagina, materia={**MATERIA, "links": {"web": {"href": href}}})
    abrir_jogo_2021(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    assert pagina.query_selector("#materia a") is None and "Brady" in texto(pagina, "#materia")


def test_ui_texto_externo_nao_vira_html(servidor, pagina):
    simular_espn(pagina, materia={**MATERIA, "headline": '<img src=x onerror="window.__xss=1">Manchete',
                                  "description": "<b>negrito</b>"})
    abrir_jogo_2021(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('materia').hidden")
    assert pagina.query_selector("#materia img") is None and pagina.query_selector("#materia b") is None
    assert "<img src=x" in texto(pagina, "#materia") and pagina.evaluate("window.__xss") is None


# ============================================================ 4.3, 4.5, 3.4 prancheta
def test_ui_prancheta_aviso_ilustrativo_sem_animacao(servidor, pagina):
    simular_espn(pagina)
    pagina.goto(servidor.url + "/?season=2021&week=1&game=2021090900&screen=coach")
    esperar(pagina, "document.querySelectorAll('#field .player-dot').length > 20")
    assert "Esquema ilustrativo" in texto(pagina, "#avisoField")
    assert pagina.eval_on_selector("#animCtrl", "e => e.hidden") is True


def test_ui_formacao_indisponivel_e_jogada_sem_formacao(servidor, pagina):
    simular_espn(pagina)
    pagina.goto(servidor.url + "/?season=2021&week=1&game=2021090900&screen=coach")
    esperar(pagina, "document.getElementById('playPick') && document.getElementById('playPick').options.length > 100")
    pagina.evaluate("""() => {
        const s = document.getElementById('playPick');
        s.value = [...s.options].find((o) => o.text.includes('sem formação')).value;
        s.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    esperar(pagina, "document.getElementById('fieldWrap') && document.getElementById('fieldWrap').innerText.includes('Formação indisponível para esta jogada')")
    pagina.click("#coachTabs [data-tab=plays]")
    esperar(pagina, "document.querySelector('.play-row')")
    assert "SEM DADOS DE FORMAÇÃO" in texto(pagina, "#coachBody")


# ============================================================ 8.x, 3.3, 9.1, 7.4
def test_ui_quatro_telas_funcionam_com_dados_novos(servidor, pagina):
    simular_espn(pagina)
    abrir_jogo_2021(pagina, servidor.url)
    pagina.click(".nav-item[data-go=coach]")
    esperar(pagina, "document.querySelectorAll('#field .player-dot').length > 20")
    pagina.click(".nav-item[data-go=scout]")
    esperar(pagina, "document.querySelectorAll('#scoutBody .p-row').length > 10")
    pagina.click("#scoutBody .p-row")
    esperar(pagina, "document.getElementById('radarSlot')")
    assert "Temporada 2021".lower() in texto(pagina, "#scout").lower()
    pagina.click(".nav-item[data-go=commentator]")
    esperar(pagina, "document.querySelectorAll('#bcFeed .tl-item').length > 0")
    assert "DAL @ TB" in texto(pagina, "#bcSub")


def test_ui_blocos_sem_dado_ocultos(servidor, pagina):
    simular_espn(pagina)
    abrir_jogo_2021(pagina, servidor.url)
    esperar(pagina, "!document.getElementById('watchSec').hidden")
    assert pagina.eval_on_selector("#insightsSec", "e => e.hidden") is True
    assert pagina.eval_on_selector("#notesSec", "e => e.hidden") is True
    pagina.click(".watch-card")
    esperar(pagina, "document.getElementById('radarSlot')")
    perfil = texto(pagina, "#scoutBody")
    assert "mph" not in perfil and "Pico" not in perfil and "undefined" not in perfil and "NaN" not in perfil


def test_ui_sem_avisos_do_dataset_antigo(servidor, pagina):
    simular_espn(pagina)
    abrir_home(pagina, servidor.url)
    corpo = pagina.inner_text("body")
    for antigo in ("Big Data Bowl", "semanas 1–8", "somente jogadas de passe", "aproximado", "PFF", "tracking"):
        assert antigo not in corpo, antigo


def test_ui_sobre_mostra_fontes_e_ultima_atualizacao(servidor, pagina):
    simular_espn(pagina)
    abrir_home(pagina, servidor.url)
    t = texto(pagina, "#sobreDados")
    assert "nflverse" in t and "CC-BY-4.0" in t and "ESPN" in t and "FTN Data" in t
    assert "Última atualização:" in t and "sem registro" not in t
