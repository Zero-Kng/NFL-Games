"""
Formato binario do tracking de um jogo: cache/tracking/<gameId>.npz.

Gravado pelo ETL (etl/build_metrics.py) e lido pelo servidor (data_layer.py).
Guarda as mesmas colunas que o servidor lia do CSV original. Numeros ficam em
float64/int64 (valores identicos bit a bit). Texto (team, playDirection,
event) tem pouquissimos valores distintos, entao vira categoria: codigos
inteiros em "<coluna>" (-1 = ausente) + os valores em "<coluna>__cats". Ler
assim e ~5x mais rapido que recriar 200 mil strings por jogo, e cada celula
devolve o mesmo texto (ou NaN) que o CSV.
E lido com allow_pickle=False: um arquivo adulterado nao executa codigo.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

# Colunas que o servidor usa para montar a prancheta (play_tracking).
COLUNAS = ["playId", "nflId", "frameId", "jerseyNumber", "team", "playDirection",
           "x", "y", "s", "a", "o", "dir", "event"]
_CATS = "__cats"


def salvar(df: pd.DataFrame, destino: Path) -> None:
    """Grava de forma atomica: escreve num .tmp e renomeia no fim."""
    arrays = {}
    for c in COLUNAS:
        s = df[c]
        if s.dtype.kind in "fiub":
            arrays[c] = s.to_numpy()
        else:
            cat = pd.Categorical(s)
            arrays[c] = cat.codes.astype(np.int16)
            arrays[c + _CATS] = np.asarray(cat.categories, dtype="U")
    tmp = destino.with_name(destino.name + ".tmp")
    with open(tmp, "wb") as f:
        np.savez_compressed(f, **arrays)
    os.replace(tmp, destino)


def carregar(origem: Path) -> pd.DataFrame:
    """
    Mesmas colunas e valores do pd.read_csv(usecols=COLUNAS) do CSV original;
    as colunas de texto vem como categoria (mesmo texto por celula, NaN igual).
    """
    with np.load(origem, allow_pickle=False) as z:
        dados = {}
        for c in COLUNAS:
            if c + _CATS in z.files:
                dados[c] = pd.Categorical.from_codes(z[c], categories=z[c + _CATS].tolist())
            else:
                dados[c] = z[c]
    return pd.DataFrame(dados)
