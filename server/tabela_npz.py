"""
Formato binário das tabelas locais (dados/temporadas/{ano}/*.npz).

Generaliza o tracking_npz.py da spec anterior para qualquer DataFrame:

- números (int, float, bool) ficam como estão, bit a bit;
- colunas pandas "nullable" (Int64, boolean, Float64) viram float64 com NaN
  no lugar do ausente, porque o numpy não tem inteiro com ausente;
- texto vira categoria: códigos int32 (-1 = ausente) + a lista de valores.
  É compacto (o play-by-play repete os mesmos times, formações e tipos de
  jogada) e rápido de ler, sem recriar uma string por célula.

A ordem e os nomes das colunas ficam guardados à parte ("__colunas"), então
qualquer nome de coluna funciona. A leitura usa allow_pickle=False: um arquivo
adulterado não executa código.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

_COLUNAS = "__colunas"
_CATS = "__cats"


def _eh_numero(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)


def salvar(df: pd.DataFrame, destino: Path) -> None:
    """Grava de forma atômica: escreve num .tmp e renomeia no fim."""
    destino = Path(destino)
    arrays = {_COLUNAS: np.asarray(list(map(str, df.columns)), dtype="U")}
    for i, nome in enumerate(df.columns):
        s = df[nome]
        chave = f"c{i}"
        if _eh_numero(s) and not isinstance(s.dtype, pd.CategoricalDtype):
            if isinstance(s.dtype, pd.api.extensions.ExtensionDtype):
                arrays[chave] = s.to_numpy(dtype="float64", na_value=np.nan)
            else:
                arrays[chave] = s.to_numpy()
        else:
            cat = pd.Categorical(s.astype("string"))
            arrays[chave] = cat.codes.astype(np.int32)
            arrays[chave + _CATS] = np.asarray([str(c) for c in cat.categories], dtype="U")
    tmp = destino.with_name(destino.name + ".tmp")
    with open(tmp, "wb") as f:
        np.savez_compressed(f, **arrays)
    os.replace(tmp, destino)


def carregar(origem: Path) -> pd.DataFrame:
    """Mesmas colunas, na mesma ordem; texto como categoria (NaN no ausente)."""
    with np.load(origem, allow_pickle=False) as z:
        nomes = z[_COLUNAS].tolist()
        dados = {}
        for i, nome in enumerate(nomes):
            chave = f"c{i}"
            if chave + _CATS in z.files:
                dados[nome] = pd.Categorical.from_codes(z[chave], categories=z[chave + _CATS].tolist())
            else:
                dados[nome] = z[chave]
    return pd.DataFrame(dados, columns=nomes)
