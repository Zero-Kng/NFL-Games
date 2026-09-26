"""
Tarefa 6 (dados-externos): servidor sobre as tabelas das 6 temporadas.

Rotas nas 6 temporadas, status dos jogos, troca de dados sem reiniciar (sem erro
e com o cache limpo), atualização diária agendada, /api/meta com as fontes e a
última atualização, e a subida sem dados saindo com código 1.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

import pytest

from conftest import ROOT, http_json

sys.path[:0] = [str(ROOT / "server"), str(ROOT / "etl")]
DADOS = ROOT / "dados"
pytestmark = pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")

import data_layer  # noqa: E402

ANOS = range(2021, 2027)


@pytest.fixture(scope="module")
def nfl():
    return data_layer.NFLData(DADOS)


def _um_jogo_disputado(base, ano):
    for w in (1, 2):
        s, jogos = http_json(f"{base}/api/games?season={ano}&week={w}")
        feitos = [g for g in jogos if g["status"] == "encerrado" and g["plays"]]
        if feitos:
            return feitos[0]
    raise AssertionError(f"nenhum jogo disputado em {ano}")


# ------------------------------------------------------------- rotas (6.1)
@pytest.mark.parametrize("ano", list(ANOS))
def test_cada_rota_responde_nas_6_temporadas(servidor, ano):
    base = servidor.url
    g = _um_jogo_disputado(base, ano)
    gid = g["gameId"]
    for url in (f"/api/games/{gid}", f"/api/games/{gid}/plays", f"/api/games/{gid}/broadcast",
                f"/api/players?season={ano}&limit=5"):
        assert http_json(base + url)[0] == 200, url
    _s, jogadas = http_json(f"{base}/api/games/{gid}/plays")
    com = next(p for p in jogadas if p["hasFormation"])
    for sufixo in ("", "/tracking", "/formation"):
        assert http_json(f"{base}/api/games/{gid}/plays/{com['playId']}{sufixo}")[0] == 200, sufixo
    _s, jogadores = http_json(f"{base}/api/players?season={ano}&limit=2")
    a, b = jogadores[0]["nflId"], jogadores[1]["nflId"]
    s, perfil = http_json(f"{base}/api/players/{a}?season={ano}")
    assert s == 200 and perfil["season"] == ano and a.startswith("00-")       # id gsis
    assert http_json(f"{base}/api/compare?season={ano}&a={a}&b={b}")[0] == 200
    s, lideres = http_json(f"{base}/api/leaders?season={ano}&metric=epa_dropback&role=QB&limit=3")
    assert s == 200 and len(lideres) == 3


def test_sem_season_vale_a_temporada_atual(servidor):
    _s, meta = http_json(servidor.url + "/api/meta")
    _s, jogos = http_json(servidor.url + "/api/games?week=1")
    assert {g["season"] for g in jogos} == {meta["season"]}


def test_temporada_inexistente_404(servidor):
    s, corpo = http_json(servidor.url + "/api/games?season=2019")
    assert s == 404 and "2019" in corpo["error"]


def test_jogo_tem_placar_oficial_rodada_e_espn(nfl):
    sb = nfl.games_list(2025, 22)[0]
    assert sb["rodada"] == "Super Bowl" and sb["gameType"] == "SB" and sb["espnId"]
    tb = next(g for g in nfl.games_list(2021, 1) if g["gameId"] == 2021090900)
    assert (tb["away"]["abbr"], tb["away"]["score"], tb["home"]["abbr"], tb["home"]["score"]) == ("DAL", 29, "TB", 31)


def test_placar_da_ultima_jogada_e_o_oficial(nfl):
    """2.3: o placar a cada jogada termina no oficial (inclui corridas e chutes)."""
    for ano in (2021, 2025):
        for g in nfl.games_list(ano, 1):
            ultima = nfl.game_plays(g["gameId"])[-1]["score"]
            assert (ultima["home"], ultima["away"]) == (g["home"]["score"], g["away"]["score"]), g["gameId"]


def test_status_dos_jogos_pelo_relogio():
    """1.4 e 1.5: 'agendado' antes do início; 'sem_resultado' depois, enquanto a fonte não traz o placar."""
    antes = data_layer.NFLData(DADOS, hoje=datetime(2026, 9, 1, tzinfo=timezone.utc))
    depois = data_layer.NFLData(DADOS, hoje=datetime(2027, 3, 1, tzinfo=timezone.utc))
    jogo = next(g for g in antes.games_list(2026, 18))
    assert jogo["status"] == "agendado" and jogo["home"]["score"] is None and jogo["kickoffUtc"].endswith("Z")
    assert next(g for g in depois.games_list(2026, 18) if g["gameId"] == jogo["gameId"])["status"] == "sem_resultado"
    assert all(g["status"] == "encerrado" for g in antes.games_list(2025, 1))


def test_campos_sem_fonte_fora_das_respostas(nfl):
    """8.3: nada de velocidade, tempo até a pressão por tracking ou dados da PFF."""
    g = nfl.games_list(2025, 1)[0]["gameId"]
    jogadas = nfl.game_plays(g)
    proibidos = {"maxSpeed", "topSpeed", "timeToPressure", "pff", "scoreIsPartial", "timeToQb"}
    assert not proibidos & set().union(*(p.keys() for p in jogadas))
    pid = nfl.players_list(2025, limit=1)[0]["nflId"]
    perfil = nfl.player(pid, 2025)
    assert not proibidos & set(perfil) and perfil["positionsLinedUp"] == []
    detalhe = nfl.game(g)
    assert detalhe["insights"] == [] and detalhe["notes"] == []
    assert all(v is not None for lado in detalhe["teams"].values() for v in lado["offense"].values())


def test_jogada_sem_formacao_marcada(nfl):
    """3.4: chutes (sem formação) aparecem na lista com a marca, e o esquema dá 404."""
    g = nfl.games_list(2025, 1)[0]["gameId"]
    kick = next(p for p in nfl.game_plays(g) if p["playType"] == "kickoff")
    assert kick["semFormacao"] and not kick["hasFormation"]
    assert nfl.play_tracking(g, kick["playId"]) is None


def test_compara_so_mesmo_grupo_e_temporada(nfl):
    """5.6: grupos diferentes -> sem linhas de comparação."""
    qb = nfl.players_list(2025, role="QB", limit=1)[0]["nflId"]
    cb = nfl.players_list(2025, role="DB", limit=1)[0]["nflId"]
    c = nfl.compare(qb, cb, 2025)
    assert c["sameRole"] is False and c["rows"] == [] and c["season"] == 2025
    outro = nfl.players_list(2025, role="QB", limit=2)[1]["nflId"]
    assert nfl.compare(qb, outro, 2025)["rows"]


def test_radar_valor_bruto_percentil_e_ol_base_reduzida(nfl):
    """5.2 e 5.7."""
    qb = nfl.player(nfl.players_list(2025, role="QB", limit=1)[0]["nflId"], 2025)
    radar = qb["roles"][0]["radar"]
    assert len(radar) == 6 and all(a["value"] is not None and a["percentile"] is not None for a in radar)
    ol = nfl.player(nfl.players_list(2025, role="OL", limit=1)[0]["nflId"], 2025)
    assert ol["baseReduzida"] and ol["roles"][0]["baseReduzida"]


def test_perfil_tem_temporada_e_jogo_a_jogo(nfl):
    """5.3."""
    dak = nfl.player("00-0033077", 2021)
    assert dak["season"] == 2021 and 2021 in dak["seasons"] and len(dak["seasons"]) >= 5
    assert len(dak["gameLog"]) >= 15 and all(j["opponent"] for j in dak["gameLog"])
    assert any(s["label"] == "Jardas de passe" for s in dak["roles"][0]["stats"])


# ------------------------------------------------------------- meta (6.2)
def test_meta_fontes_creditos_ultima_atualizacao_e_rodadas(servidor):
    """9.1, 7.4 e 1.2."""
    _s, meta = http_json(servidor.url + "/api/meta")
    assert {f["nome"] for f in meta["fontes"]} >= {"nflverse", "ESPN"}
    assert all(f["credito"] for f in meta["fontes"])
    assert "CC-BY-4.0" in next(f for f in meta["fontes"] if f["nome"] == "nflverse")["credito"]
    assert meta["ultimaAtualizacao"]
    assert [t["season"] for t in meta["seasons"]] == sorted(ANOS, reverse=True)
    rodadas = {w["rodada"] for w in next(t for t in meta["seasons"] if t["season"] == 2024)["weeks"]}
    assert {"Wild Card", "Divisional", "Final de Conferência", "Super Bowl"} <= rodadas
    assert meta["dataset"]["caveats"] == []                     # 3.3: sem os avisos do dataset antigo


def test_subida_com_copia_local_ate_10s(servidor):
    """NFR 2 (a fixture mede até /api/meta responder)."""
    assert servidor.startup_s <= 10.0, f"subida levou {servidor.startup_s:.1f}s"


# ------------------------------------------------ troca de dados (6.2, 7.3)
@pytest.fixture
def servidor_em_processo(nfl):
    """O Handler real num servidor HTTP deste processo, para trocar os dados por dentro."""
    import serve
    serve.DATA = nfl
    serve.CACHE.limpar()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield serve, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_troca_de_dados_durante_requisicoes_sem_erro(servidor_em_processo, nfl):
    serve, base = servidor_em_processo
    g = nfl.games_list(2025, 1)[0]["gameId"]
    urls = ["/api/meta", f"/api/games/{g}", f"/api/games/{g}/plays", "/api/players?season=2025&limit=60",
            f"/api/games/{g}/broadcast", "/api/games?season=2025&week=1", f"/api/players?season=2024&limit=60"]
    novo = data_layer.NFLData(DADOS)            # carregado antes: a troca em si é só trocar a referência
    trocas, status = [], []
    fim = threading.Event()

    def trocar():
        for i in range(5):
            time.sleep(0.15)
            serve.trocar_dados(novo if i % 2 == 0 else nfl, log=lambda _m: None)
            trocas.append(i)
        fim.set()

    def usuario(k):
        i = k
        while not fim.is_set():
            with urllib.request.urlopen(base + urls[i % len(urls)], timeout=60) as r:
                r.read()
                status.append(r.status)
            i += 1

    t = threading.Thread(target=trocar)
    t.start()
    with ThreadPoolExecutor(10) as ex:
        list(ex.map(usuario, range(10)))
    t.join(30)
    assert len(trocas) == 5 and len(status) >= 10 and set(status) == {200}


def test_cache_limpo_depois_da_troca(servidor_em_processo, nfl):
    serve, base = servidor_em_processo
    urllib.request.urlopen(base + "/api/meta").read()
    assert serve.CACHE.stats()["itens"] >= 1

    class Novo(data_layer.NFLData):
        def meta(self):
            return {**super().meta(), "marca": "dados novos"}

    serve.trocar_dados(Novo(DADOS), log=lambda _m: None)
    _s, meta = http_json(base + "/api/meta")
    assert meta.get("marca") == "dados novos"               # a resposta antiga não voltou do cache


def test_atualizacao_diaria_agendada():
    """7.2 com relógio controlado: roda depois da 1ª espera e a cada intervalo, e para no Event."""
    import serve
    chamadas = []
    parar = threading.Event()
    serve.ciclo_de_atualizacao(parar, intervalo_s=0.05, primeira_espera_s=0.01,
                               passo=lambda: chamadas.append(time.perf_counter()))
    time.sleep(0.4)
    parar.set()
    n = len(chamadas)
    time.sleep(0.15)
    assert n >= 4 and len(chamadas) == n                     # parou de chamar depois do Event


def test_atualizacao_sem_rede_segue_com_os_dados(monkeypatch, nfl):
    """7.5: a atualização falha sem internet e o servidor continua com o que tem."""
    import serve
    serve.DATA = nfl
    mensagens = []
    assert serve.atualizar(offline=True, log=mensagens.append) is False
    assert serve.DATA is nfl and any("sem acesso" in m for m in mensagens)


# ------------------------------------------------------ subida sem dados (7.6)
def test_subida_sem_internet_e_sem_copia_sai_com_codigo_1(tmp_path):
    env = {**os.environ, "NFL_DADOS": str(tmp_path / "dados"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "server" / "serve.py"), "--offline", "--port", "0"],
                       env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    saida = r.stdout + r.stderr
    assert r.returncode == 1, saida
    assert "primeira carga" in saida and "[erro] Sem dados para subir o app" in saida
    assert "internet" in saida


def test_rodar_bat_explica_a_primeira_carga():
    """O RODAR.bat avisa que a primeira carga baixa os dados (o progresso sai do servidor, testado acima)."""
    bat = (ROOT / "RODAR.bat").read_text(encoding="utf-8", errors="replace")
    assert "nflverse" in bat and "primeira" in bat.lower()
    assert "Big Data Bowl" not in bat and "tracking" not in bat
