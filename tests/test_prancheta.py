"""Tarefa 5 (dados-externos): esquema ilustrativo da formação de cada jogada (Requisito 4)."""

import sys

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

sys.path[:0] = [str(ROOT / "server")]
import prancheta  # noqa: E402
import tabela_npz  # noqa: E402

DADOS = ROOT / "dados"

ATAQUE = ("C;G;G;QB;RB;T;T;TE;WR;WR;WR", "56;73;52;4;33;78;60;89;88;9;3",
          "Cooper Beebe;Tyler Smith;Tyler Booker;Dak Prescott;Javonte Williams;Terence Steele;Tyler Guyton;"
          "Brevyn Spann-Ford;CeeDee Lamb;KaVontae Turpin;George Pickens")
DEFESA = "CB;CB;CB;DT;DT;FS;ILB;ILB;OLB;OLB;SS"


def _jogada(**extra):
    j = {"gameId": 2025090400, "play_id": 55, "posteam": "DAL", "defteam": "PHI", "yardline_100": 36.0,
         "ydstogo": 4, "play_type": "run", "formacao": "UNDER CENTER", "qb_local": "U", "hash": "R",
         "backfield": 1.0, "box": 7.0, "rushers": 4.0, "pessoal_of": "1 RB, 1 TE, 3 WR",
         "pessoal_def": "3 CB, 2 DT, 1 FS, 2 ILB, 2 OLB, 1 SS",
         "of_posicoes": ATAQUE[0], "of_numeros": ATAQUE[1], "of_nomes": ATAQUE[2],
         "of_ids": ";".join(f"00-00{i:05d}" for i in range(11)),
         "def_posicoes": DEFESA, "def_numeros": "24;2;27;91;95;32;0;42;13;96;21",
         "def_nomes": ";".join(f"Defensor {i}" for i in range(11)),
         "def_ids": ";".join(f"00-01{i:05d}" for i in range(11))}
    j.update(extra)
    return j


def _no_box(e):
    los, yb = e["lineOfScrimmage"], e["ball"][0][1]
    return sum(1 for p in e["players"] if p["side"] == "defense"
               and 0 < p["t"][0][0] - los <= prancheta.BOX_PROF and abs(p["t"][0][1] - yb) <= prancheta.BOX_LARG)


def _dentro_do_campo(e):
    return all(0 <= p["t"][0][0] <= 120 and 0 <= p["t"][0][1] <= prancheta.LARGURA for p in e["players"])


def test_formato_do_tracking_com_um_quadro():
    e = prancheta.esquema(_jogada())
    assert e["frameCount"] == 1 and e["ilustrativo"] is True and e["generico"] is False
    assert e["playDirection"] == "right" and e["lineOfScrimmage"] == 110 - 36 and e["yardsToGo"] == 4
    assert len(e["ball"]) == 1 and e["ball"][0][0] == e["lineOfScrimmage"]
    assert e["formacao"] == {"nome": "UNDER CENTER", "pessoalAtaque": "1 RB, 1 TE, 3 WR",
                             "pessoalDefesa": "3 CB, 2 DT, 1 FS, 2 ILB, 2 OLB, 1 SS", "box": 7, "rushers": 4}
    dak = next(p for p in e["players"] if p["name"] == "Dak Prescott")
    assert dak == {**dak, "nflId": "00-0000003", "jersey": 4, "position": "QB", "side": "offense", "team": "DAL"}
    assert len(dak["t"]) == 1 and len(dak["t"][0]) == 5


def test_onze_contra_onze_dentro_do_campo_ataque_para_x_positivo():
    e = prancheta.esquema(_jogada())
    ataque = [p for p in e["players"] if p["side"] == "offense"]
    defesa = [p for p in e["players"] if p["side"] == "defense"]
    assert len(ataque) == len(defesa) == 11
    assert len({p["nflId"] for p in e["players"]}) == 22          # o Field indexa os pontos pelo nflId
    assert _dentro_do_campo(e)
    los = e["lineOfScrimmage"]
    assert all(p["t"][0][0] < los for p in ataque) and all(p["t"][0][0] > los for p in defesa)


def test_linha_ofensiva_t_g_c_g_t_e_bola_no_hash():
    e = prancheta.esquema(_jogada(hash="L"))
    yb = e["ball"][0][1]
    assert yb == pytest.approx(prancheta.HASH["L"])
    ol = sorted((p["t"][0][1] - yb, p["position"]) for p in e["players"] if p["position"] in ("C", "G", "T"))
    assert [pos for _, pos in ol] == ["T", "G", "C", "G", "T"]
    assert [round(dy, 1) for dy, _ in ol] == [-2.4, -1.2, 0.0, 1.2, 2.4]


@pytest.mark.parametrize("fundo,raso", [({"qb_local": "S", "formacao": "SHOTGUN"}, {"qb_local": "U"}),
                                        ({"qb_local": None, "formacao": "SHOTGUN"}, {"qb_local": None, "formacao": "I_FORM"}),
                                        ({"qb_local": "P", "formacao": "PISTOL"}, {"qb_local": "U"})])
def test_qb_mais_fundo_no_shotgun_que_sob_o_center(fundo, raso):
    def prof(extra):
        e = prancheta.esquema(_jogada(**extra))
        return e["lineOfScrimmage"] - next(p for p in e["players"] if p["position"] == "QB")["t"][0][0]
    assert prof(fundo) > prof(raso)


@pytest.mark.parametrize("box", [5, 6, 7, 8, 9])
def test_defensores_no_box_conferem(box):
    e = prancheta.esquema(_jogada(box=float(box)))
    assert _no_box(e) == box


def test_posicoes_agrupadas_de_2021():
    e = prancheta.esquema(_jogada(formacao="SINGLEBACK", qb_local=None, hash=None, backfield=None,
                                  of_posicoes="QB;OL;OL;WR;OL;WR;OL;TE;RB;TE;OL",
                                  def_posicoes="DL;DB;DL;LB;DB;DL;DB;LB;LB;LB;DL", box=8.0))
    assert _dentro_do_campo(e) and _no_box(e) == 8
    assert e["ball"][0][1] == pytest.approx(prancheta.LARGURA / 2)       # sem hash: no meio


def test_esquema_generico_sem_nomes():
    e = prancheta.esquema(_jogada(formacao=None, qb_local="S", backfield=1.0, box=6.0, pessoal_of=None,
                                  pessoal_def=None, **{k: None for k in ("of_posicoes", "of_numeros", "of_nomes",
                                                                         "of_ids", "def_posicoes", "def_numeros",
                                                                         "def_nomes", "def_ids")}))
    assert e["generico"] is True and e["formacao"]["nome"] == "SHOTGUN"
    assert all(p["name"] is None and p["jersey"] is None for p in e["players"])
    pos = [p["position"] for p in e["players"] if p["side"] == "offense"]
    assert sorted(pos) == sorted(["OL"] * 5 + ["QB", "RB"] + ["WR"] * 4)
    assert len({p["nflId"] for p in e["players"]}) == 22 and _no_box(e) == 6 and _dentro_do_campo(e)


@pytest.mark.parametrize("extra", [{"formacao": None, "qb_local": "0"}, {"formacao": None, "qb_local": None},
                                   {"yardline_100": None}])
def test_esquema_sem_formacao_none(extra):
    assert prancheta.esquema(_jogada(**extra)) is None


def test_posicoes_fora_do_lugar_e_mais_de_onze():
    # jumbo: DL como bloqueador no ataque; 12 na defesa (erro da fonte) com um WR
    e = prancheta.esquema(_jogada(of_posicoes="C;G;G;QB;RB;T;T;TE;DT;TE;FB", def_posicoes=DEFESA + ";WR",
                                  def_numeros=None, def_nomes=None, def_ids=None))
    assert sum(p["side"] == "defense" for p in e["players"]) == 12
    assert len({p["nflId"] for p in e["players"]}) == 23 and _dentro_do_campo(e)


def test_perto_da_linha_de_gol_continua_no_campo():
    for jarda in (1.0, 99.0):
        assert _dentro_do_campo(prancheta.esquema(_jogada(yardline_100=jarda)))


# ------------------------------------------------------------------ dados reais
def _jogadas(ano):
    p = tabela_npz.carregar(DADOS / "temporadas" / str(ano) / "jogadas.npz")
    p = p.astype({c: object for c in p if isinstance(p[c].dtype, pd.CategoricalDtype)})
    p = p[p["play_type"].isin(["pass", "run"])]
    return [{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
            for r in p.sample(400, random_state=1).to_dict("records")]


@pytest.mark.skipif(not (DADOS / "jogos.npz").exists(), reason="dados ainda não montados")
@pytest.mark.parametrize("ano", [2021, 2023, 2025, 2026])
def test_esquema_em_jogadas_reais(ano):
    """Inclui 2021 (4.6): mesmo os jogos que tinham tracking usam a prancheta sem movimento."""
    feitos = 0
    for j in _jogadas(ano):
        e = prancheta.esquema(j)
        if e is None:
            continue
        feitos += 1
        assert _dentro_do_campo(e)
        assert len({p["nflId"] for p in e["players"]}) == len(e["players"])
        xy = np.array([p["t"][0][:2] for p in e["players"]])
        perto = (np.abs(xy[:, None, :] - xy[None, :, :]) < 1).all(axis=2)
        assert perto.sum() == len(xy), "dois jogadores no mesmo ponto"           # só a diagonal
        n_def = sum(p["side"] == "defense" for p in e["players"])
        if j.get("box") is not None:
            assert _no_box(e) == min(int(j["box"]), n_def), (j["gameId"], j["play_id"])
        assert e["generico"] == (ano == 2026)
    assert feitos > 350
