"""Tarefa 2 (dados-externos): sincronização das fontes, com um 'GitHub' falso local."""

import gzip
import json
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "etl"))
import fontes  # noqa: E402

CATALOGO_TESTE = [
    fontes.Fonte("jogos", "schedules", r"games\.csv\.gz", frozenset({"game_id", "season"}), por_ano=False),
    fontes.Fonte("jogadas", "pbp", r"play_by_play_(?P<ano>\d{4})\.csv(\.gz)?",
                 frozenset({"game_id", "play_id"})),
]
ANOS = range(2024, 2026)


class GitHubFalso:
    """Serve /api/releases/tags/{tag} e /download/{tag}/{arquivo}."""

    def __init__(self):
        self.arquivos: dict[str, dict[str, dict]] = {}   # tag -> nome -> {conteudo, updated_at}
        self.limite_estourado = False
        self.pedidos: list[str] = []
        pai = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                pai.pedidos.append(self.path)
                if self.path.startswith("/api/releases/tags/"):
                    if pai.limite_estourado:
                        self.send_response(403)
                        self.send_header("X-RateLimit-Remaining", "0")
                        self.end_headers()
                        return
                    tag = self.path.rsplit("/", 1)[1]
                    assets = [{"name": n, "size": len(a["conteudo"]), "updated_at": a["updated_at"]}
                              for n, a in pai.arquivos.get(tag, {}).items()]
                    corpo = json.dumps({"assets": assets}).encode()
                elif self.path.startswith("/download/"):
                    _, _, tag, nome = self.path.split("/", 3)
                    corpo = pai.arquivos[tag][nome]["conteudo"]
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.rede = fontes.Rede(api=base + "/api/releases/tags/", download=base + "/download/", timeout=5)

    def publicar(self, tag, nome, texto, updated_at="2026-09-01T00:00:00Z"):
        conteudo = gzip.compress(texto.encode()) if nome.endswith(".gz") else texto.encode()
        self.arquivos.setdefault(tag, {})[nome] = {"conteudo": conteudo, "updated_at": updated_at}

    def downloads(self):
        return [p for p in self.pedidos if p.startswith("/download/")]


@pytest.fixture
def gh(monkeypatch):
    monkeypatch.setattr(fontes, "CATALOGO", CATALOGO_TESTE)
    g = GitHubFalso()
    g.publicar("schedules", "games.csv.gz", "game_id,season\n2025_01_DAL_PHI,2025\n")
    g.publicar("pbp", "play_by_play_2024.csv.gz", "game_id,play_id\nA,1\n")
    g.publicar("pbp", "play_by_play_2025.csv.gz", "game_id,play_id\nB,1\n")
    g.publicar("pbp", "play_by_play_2025.csv", "game_id,play_id\nB,1\n")      # versão sem gz: ignorada
    g.publicar("pbp", "play_by_play_2019.csv.gz", "game_id,play_id\nZ,1\n")   # fora do intervalo
    yield g
    g.srv.shutdown()


def sinc(gh, tmp_path, **kw):
    return fontes.sincronizar(tmp_path, anos=ANOS, rede=kw.pop("rede", gh.rede), progresso=lambda m: None, **kw)


def test_primeira_sincronizacao_baixa_so_o_necessario(gh, tmp_path):
    r = sinc(gh, tmp_path)
    assert sorted(r.baixados) == ["pbp/play_by_play_2024.csv.gz", "pbp/play_by_play_2025.csv.gz",
                                  "schedules/games.csv.gz"]
    assert r.anos_alterados == {2024, 2025} and r.globais_alterados == {"jogos"}
    assert (tmp_path / "brutos" / "pbp" / "play_by_play_2025.csv.gz").exists()
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert "ultimaSincronizacao" in m and len(m["arquivos"]) == 3


def test_sincroniza_so_o_que_mudou(gh, tmp_path):
    sinc(gh, tmp_path)
    gh.pedidos.clear()
    r = sinc(gh, tmp_path)
    assert r.baixados == [] and gh.downloads() == []
    gh.publicar("pbp", "play_by_play_2025.csv.gz", "game_id,play_id\nB,1\nB,2\n", updated_at="2026-09-25T10:00:00Z")
    r = sinc(gh, tmp_path)
    assert r.baixados == ["pbp/play_by_play_2025.csv.gz"] and r.anos_alterados == {2025}


def test_arquivo_sem_coluna_rejeitado_mantem_copia(gh, tmp_path):
    sinc(gh, tmp_path)
    local = tmp_path / "brutos" / "pbp" / "play_by_play_2025.csv.gz"
    bom = local.read_bytes()
    gh.publicar("pbp", "play_by_play_2025.csv.gz", "game_id,outra\nB,1\n", updated_at="2026-09-25T10:00:00Z")
    r = sinc(gh, tmp_path)
    assert r.baixados == [] and any("play_id" in f for f in r.falhas)
    assert local.read_bytes() == bom
    assert not list(local.parent.glob("*.tmp"))


def test_sem_rede_segue_com_copia_local(gh, tmp_path):
    sinc(gh, tmp_path)
    fora = fontes.Rede(api="http://127.0.0.1:9/api/releases/tags/", download="http://127.0.0.1:9/download/",
                       timeout=2)
    r = sinc(gh, tmp_path, rede=fora)
    assert r.sem_rede and r.baixados == []


def test_sem_rede_e_sem_copia_levanta_semdados(gh, tmp_path):
    fora = fontes.Rede(api="http://127.0.0.1:9/api/releases/tags/", download="http://127.0.0.1:9/download/",
                       timeout=2)
    with pytest.raises(fontes.SemDados):
        sinc(gh, tmp_path, rede=fora)


def test_limite_da_api_tratado_como_sem_rede(gh, tmp_path):
    sinc(gh, tmp_path)
    gh.limite_estourado = True
    r = sinc(gh, tmp_path)
    assert r.sem_rede and any("limite" in f for f in r.falhas)


def test_descartado_nao_e_baixado_de_novo(gh, tmp_path):
    sinc(gh, tmp_path)
    liberado = fontes.descartar(tmp_path, {2024})
    assert liberado > 0
    assert not (tmp_path / "brutos" / "pbp" / "play_by_play_2024.csv.gz").exists()
    gh.pedidos.clear()
    r = sinc(gh, tmp_path)                       # sem mudança na fonte: nada é baixado
    assert r.baixados == [] and gh.downloads() == []


def test_descartado_republicado_e_baixado(gh, tmp_path):
    sinc(gh, tmp_path)
    fontes.descartar(tmp_path, {2024})
    gh.publicar("pbp", "play_by_play_2024.csv.gz", "game_id,play_id\nA,1\nA,2\n", updated_at="2026-09-26T00:00:00Z")
    r = sinc(gh, tmp_path)                       # correção publicada: baixa de novo
    assert r.baixados == ["pbp/play_by_play_2024.csv.gz"] and r.anos_alterados == {2024}
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert not m["arquivos"]["pbp/play_by_play_2024.csv.gz"].get("descartado")


def test_descartado_forcado_e_baixado(gh, tmp_path):
    sinc(gh, tmp_path)
    fontes.descartar(tmp_path, {2024})
    r = sinc(gh, tmp_path, forcar={2024})        # remontar a temporada exige os brutos
    assert r.baixados == ["pbp/play_by_play_2024.csv.gz"]


def test_so_descartados_nao_e_semdados(gh, tmp_path):
    sinc(gh, tmp_path)
    fontes.descartar(tmp_path, {2024, 2025})
    fora = fontes.Rede(api="http://127.0.0.1:9/api/releases/tags/", download="http://127.0.0.1:9/download/",
                       timeout=2)
    r = sinc(gh, tmp_path, rede=fora)            # sem rede, mas as tabelas já estão montadas
    assert r.sem_rede


def test_url_fora_da_lista_recusada():
    with pytest.raises(PermissionError):
        fontes.Rede()._abrir("https://exemplo.com/arquivo.csv")


def test_temporada_atual_vira_em_setembro():
    assert fontes.temporada_atual(datetime(2026, 8, 31)) == 2025
    assert fontes.temporada_atual(datetime(2026, 9, 1)) == 2026


def test_catalogo_real_tem_as_9_releases():
    import importlib
    real = importlib.reload(fontes)
    assert {f.release for f in real.CATALOGO} == {
        "schedules", "players", "rosters", "pbp", "pbp_participation", "ftn_charting",
        "stats_player", "pfr_advstats", "snap_counts"}


# ------------------------------------------- site-publico, revisão final (3.1)
@pytest.mark.parametrize("token", ["abc123", None])
def test_token_do_github_so_na_api(monkeypatch, token):
    """No Actions (GITHUB_TOKEN), a API do GitHub vai autenticada: sem isso o limite é de 60
    chamadas/hora por IP compartilhado. Os downloads e o PC (sem a variável) seguem sem token."""
    pedidos = []
    monkeypatch.setattr(fontes.urllib.request, "urlopen", lambda req, timeout: pedidos.append(req))
    if token:
        monkeypatch.setenv("GITHUB_TOKEN", token)
    else:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rede = fontes.Rede()
    rede._abrir(rede.api + "pbp")
    rede._abrir(rede.download + "pbp/play_by_play_2026.csv.gz")
    api, download = pedidos
    assert api.get_header("Authorization") == (f"Bearer {token}" if token else None)
    assert download.get_header("Authorization") is None
