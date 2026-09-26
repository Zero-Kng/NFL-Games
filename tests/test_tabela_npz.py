"""Tarefa 1 (dados-externos): formato binário genérico das tabelas."""

import sys

import numpy as np
import pandas as pd
import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "server"))
import tabela_npz  # noqa: E402


def _texto_como_no_original(orig: pd.DataFrame, lido: pd.DataFrame) -> pd.DataFrame:
    """As colunas de texto voltam como categoria; compara o conteúdo célula a célula."""
    out = lido.copy()
    for c in orig.columns:
        if isinstance(lido[c].dtype, pd.CategoricalDtype):
            out[c] = lido[c].astype(object).where(lido[c].notna(), None)
    return out


def test_ida_e_volta_identica(tmp_path):
    df = pd.DataFrame({
        "gameId": np.array([2021090900, 2021090900, 2025090400], dtype="int64"),
        "epa": [0.1234567890123, np.nan, -2.5],
        "td": [True, False, True],
        "desc": ["(15:00) D.Prescott pass", None, "Chiefs <b>TD</b>"],
        "time": ["DAL", "DAL", "KC"],
        "coluna com espaço/barra": [1.0, 2.0, 3.0],
    })
    arq = tmp_path / "t.npz"
    tabela_npz.salvar(df, arq)
    lido = tabela_npz.carregar(arq)
    assert list(lido.columns) == list(df.columns)
    # numeros: bit a bit, mesmo tipo
    for c in ("gameId", "epa", "td", "coluna com espaço/barra"):
        assert lido[c].dtype == df[c].dtype
        np.testing.assert_array_equal(lido[c].to_numpy(), df[c].to_numpy())
    # texto: mesmo conteudo, ausente continua ausente, HTML guardado literal
    t = _texto_como_no_original(df, lido)
    assert t["desc"].tolist() == ["(15:00) D.Prescott pass", None, "Chiefs <b>TD</b>"]
    assert t["time"].tolist() == ["DAL", "DAL", "KC"]


def test_nullable_vira_float_com_nan(tmp_path):
    df = pd.DataFrame({"down": pd.array([1, None, 3], dtype="Int64"),
                       "flag": pd.array([True, None, False], dtype="boolean")})
    arq = tmp_path / "n.npz"
    tabela_npz.salvar(df, arq)
    lido = tabela_npz.carregar(arq)
    np.testing.assert_array_equal(lido["down"].to_numpy(), [1.0, np.nan, 3.0])
    np.testing.assert_array_equal(lido["flag"].to_numpy(), [1.0, np.nan, 0.0])


def test_tabela_vazia_e_coluna_toda_ausente(tmp_path):
    vazia = pd.DataFrame({"a": pd.Series([], dtype="float64"), "b": pd.Series([], dtype="object")})
    tabela_npz.salvar(vazia, tmp_path / "v.npz")
    lida = tabela_npz.carregar(tmp_path / "v.npz")
    assert list(lida.columns) == ["a", "b"] and len(lida) == 0

    ausente = pd.DataFrame({"x": [None, None]})
    tabela_npz.salvar(ausente, tmp_path / "a.npz")
    assert tabela_npz.carregar(tmp_path / "a.npz")["x"].isna().all()


def test_muitos_valores_de_texto_distintos(tmp_path):
    # O play-by-play tem ~50 mil descrições distintas por temporada: não cabe em int16.
    df = pd.DataFrame({"desc": [f"jogada {i}" for i in range(70_000)]})
    tabela_npz.salvar(df, tmp_path / "m.npz")
    lido = tabela_npz.carregar(tmp_path / "m.npz")
    assert lido["desc"].iloc[-1] == "jogada 69999"


def test_gravacao_atomica_nao_deixa_tmp(tmp_path):
    tabela_npz.salvar(pd.DataFrame({"a": [1]}), tmp_path / "x.npz")
    assert not list(tmp_path.glob("*.tmp"))


def test_arquivo_corrompido_lanca_erro(tmp_path):
    ruim = tmp_path / "ruim.npz"
    ruim.write_bytes(b"isto nao e um zip")
    with pytest.raises(Exception):
        tabela_npz.carregar(ruim)
