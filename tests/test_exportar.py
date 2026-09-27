"""
Spec site-publico, tarefa 2: o exportador (tools/exportar.py) grava em arquivos as
respostas que a interface pede, iguais às da camada de dados do servidor.

Exporta a temporada 2021 (e, num teste, a 2026) para uma pasta temporária e compara
cada arquivo com a NFLData criada com a mesma data ("hoje") usada na exportação.
"""

import gzip
import json
import re
import sys
from datetime import datetime, timezone

import pytest

from conftest import ROOT

sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "server"), str(ROOT / "etl")]
DADOS = ROOT / "dados"
pytestmark = pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")

import data_layer  # noqa: E402
import exportar  # noqa: E402

AGORA = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
ANO = 2021


@pytest.fixture(scope="module")
def nfl():
    return data_layer.NFLData(DADOS, hoje=AGORA)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    saida = tmp_path_factory.mktemp("site")
    versao = exportar.exportar(DADOS, saida, temporadas={ANO}, processos=4, agora=AGORA)
    return saida, versao


def api(site):
    saida, versao = site
    return saida / "api" / versao


def ler(caminho):
    if caminho.suffix == ".gz":
        return json.loads(gzip.decompress(caminho.read_bytes()).decode("utf-8"))
    return json.loads(caminho.read_text(encoding="utf-8"))


def ids_da_temporada(nfl, ano):
    t = next(x for x in nfl.meta()["seasons"] if x["season"] == ano)
    return [g["gameId"] for w in t["weeks"] for g in nfl.games_list(season=ano, week=w["week"])]


def test_versao_e_marca(site):
    saida, versao = site
    assert re.fullmatch(r"\d{8}T\d{4}", versao)
    assert ler(saida / "api" / "versao.json") == {"versao": versao}
    assert '<meta name="nfl-dados" content="estatico">' in (saida / "index.html").read_text(encoding="utf-8")
    assert (saida / "css" / "app.css").exists() and (saida / "js" / "api.js").exists()


def test_meta_igual_ao_servidor(site, nfl):
    # ultimaAtualizacao vem do dados/manifest.json lido na hora: um app aberto que sincronize
    # durante o teste a muda. O resto do meta tem de ser igual.
    exportado, servidor = ler(api(site) / "meta.json"), nfl.meta()
    assert isinstance(exportado.pop("ultimaAtualizacao"), str)
    servidor.pop("ultimaAtualizacao")
    assert exportado == servidor


def test_semanas_iguais_ao_servidor(site, nfl):
    t = next(x for x in nfl.meta()["seasons"] if x["season"] == ANO)
    for w in t["weeks"]:
        assert ler(api(site) / str(ANO) / "semanas" / f"{w['week']}.json") == nfl.games_list(season=ANO, week=w["week"])


def test_jogos_iguais_ao_servidor(site, nfl):
    ids = ids_da_temporada(nfl, ANO)
    assert len(list((api(site) / "jogos").glob("*.pranchetas.json.gz"))) == len(ids)
    for gid in ids[::len(ids) // 20][:20]:
        b = ler(api(site) / "jogos" / f"{gid}.json.gz")
        assert b == {"game": nfl.game(gid), "plays": nfl.game_plays(gid), "broadcast": nfl.broadcast(gid)}
        pr = ler(api(site) / "jogos" / f"{gid}.pranchetas.json.gz")
        for p in b["plays"]:
            tr = nfl.play_tracking(gid, p["playId"])
            assert pr.get(str(p["playId"])) == tr


def test_jogadores_e_perfis(site, nfl):
    base = api(site) / str(ANO)
    assert ler(base / "jogadores.json") == nfl.players_list(season=ANO, rated_only=False, limit=10**6)
    ids = list(nfl.temporadas[ANO].jogadores.index)
    assert len(list((base / "jogadores").glob("*.json"))) == len(ids)
    for pid in ids[::len(ids) // 50][:50]:
        assert ler(base / "jogadores" / f"{pid}.json") == nfl.player(pid, ANO)


def test_noticias_e_resumo(site, nfl):
    base = api(site) / str(ANO)
    assert ler(base / "noticias.json") == nfl.news(season=ANO)
    t = next(x for x in nfl.meta()["seasons"] if x["season"] == ANO)
    for w in t["weeks"]:
        assert ler(base / "noticias" / f"{w['week']}.json") == nfl.news(season=ANO, week=w["week"])
    assert ler(base / "resumo.json") == nfl.summary(season=ANO)


def test_jogo_futuro_exportado(tmp_path, nfl):
    """Foco de revisão 5: jogo que ainda não aconteceu também tem os dois arquivos."""
    exportar.exportar(DADOS, tmp_path, temporadas={2026}, processos=4, agora=AGORA)
    versao = ler(tmp_path / "api" / "versao.json")["versao"]
    futuro = next(g for g in nfl.games_list(season=2026, week=18) if g["status"] == "agendado")
    base = tmp_path / "api" / versao / "jogos"
    b = ler(base / f"{futuro['gameId']}.json.gz")
    assert b["plays"] == [] and b["broadcast"] is None and b["game"] == nfl.game(futuro["gameId"])
    assert ler(base / f"{futuro['gameId']}.pranchetas.json.gz") == {}


def test_verificar_acusa_problemas(site, tmp_path):
    import shutil
    saida, versao = site
    assert exportar.verificar(saida) == []
    copia = tmp_path / "copia"
    shutil.copytree(saida, copia)
    (copia / "api" / versao / "meta.json").unlink()
    assert len(exportar.verificar(copia, limite_bytes=1)) == 2


def test_gravacao_atomica(site):
    saida, _ = site
    assert list(saida.rglob("*.tmp")) == []


def test_cli_sai_com_erro_se_a_verificacao_falhar(tmp_path, monkeypatch):
    monkeypatch.setattr(exportar, "verificar", lambda saida, limite_bytes=0: ["simulado"])
    monkeypatch.setattr(exportar, "exportar", lambda *a, **k: "20260927T1500")
    assert exportar.main(["--saida", str(tmp_path), "--temporadas", "2021"]) == 1
