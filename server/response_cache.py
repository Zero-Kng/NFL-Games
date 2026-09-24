"""
Cache de respostas prontas da API (JSON ja serializado e comprimido).

Os dados nao mudam enquanto o servidor esta de pe, entao cada resposta so
precisa ser calculada uma vez. O cache garante isso mesmo sob concorrencia:
se 10 pessoas pedem o mesmo jogo no mesmo instante, uma calcula e as outras
esperam o resultado dela ("single-flight").
"""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Resposta:
    gz: bytes        # corpo JSON comprimido
    raw_size: int    # tamanho do JSON sem compressao
    etag: str        # sha1 do JSON, entre aspas
    build_ms: float  # quanto custou construir

    def corpo(self) -> bytes:
        return gzip.decompress(self.gz)


def serializar(payload, build_ms: float = 0.0) -> Resposta:
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return Resposta(
        gz=gzip.compress(raw, 6),
        raw_size=len(raw),
        etag='"' + hashlib.sha1(raw).hexdigest() + '"',
        build_ms=build_ms,
    )


class _EmConstrucao:
    """Marcador de uma chave sendo construida; quem chega depois espera nele."""

    __slots__ = ("pronto", "resposta", "erro")

    def __init__(self):
        self.pronto = threading.Event()
        self.resposta: Resposta | None = None
        self.erro: BaseException | None = None


class CacheDeRespostas:
    def __init__(self, max_bytes: int = 128 * 2**20):
        self.max_bytes = max_bytes
        self._itens: OrderedDict[str, Resposta] = OrderedDict()
        self._em_construcao: dict[str, _EmConstrucao] = {}
        self._bytes = 0
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get_or_build(self, key: str, build: Callable[[], object]) -> tuple[Resposta, bool]:
        """
        (resposta, hit). Se outra thread ja esta construindo a mesma chave,
        espera por ela. Se build() lanca, a excecao chega a todos os que
        esperavam e nada e guardado: a proxima chamada tenta de novo.
        """
        with self._lock:
            pronta = self._itens.get(key)
            if pronta is not None:
                self._itens.move_to_end(key)
                self._hits += 1
                return pronta, True
            marca = self._em_construcao.get(key)
            dono = marca is None
            if dono:
                marca = self._em_construcao[key] = _EmConstrucao()

        if not dono:
            marca.pronto.wait()
            if marca.erro is not None:
                raise marca.erro
            with self._lock:
                self._hits += 1
            return marca.resposta, True

        try:
            t0 = time.perf_counter()
            payload = build()
            marca.resposta = serializar(payload, (time.perf_counter() - t0) * 1000)
        except BaseException as e:
            marca.erro = e
            raise
        finally:
            with self._lock:
                del self._em_construcao[key]
                if marca.resposta is not None:
                    self._guardar(key, marca.resposta)
                    self._misses += 1
            marca.pronto.set()
        return marca.resposta, False

    def _guardar(self, key: str, resp: Resposta) -> None:
        # chamado com self._lock
        self._itens[key] = resp
        self._bytes += len(resp.gz)
        while self._bytes > self.max_bytes and len(self._itens) > 1:
            _k, velho = self._itens.popitem(last=False)
            self._bytes -= len(velho.gz)

    def aquecer(self, tarefas: Iterable[tuple[str, Callable[[], object]]],
                log: Callable[[str], None] = print, pausa_s: float = 0.002) -> threading.Thread:
        """
        Constroi as chaves em segundo plano, na ordem dada. Uma tarefa que
        falha e registrada e pulada. Entre tarefas, cede CPU as requisicoes.
        """
        def rodar():
            t0 = time.perf_counter()
            n = falhas = 0
            log("aquecimento: inicio")
            for key, build in tarefas:
                try:
                    self.get_or_build(key, build)
                    n += 1
                except Exception as e:  # noqa: BLE001 -- aquecer nunca derruba o servidor
                    falhas += 1
                    log(f"aquecimento: falhou {key}: {e!r}")
                time.sleep(pausa_s)
            s = self.stats()
            log(f"aquecimento: concluido em {time.perf_counter() - t0:.1f}s "
                f"({n} respostas, {falhas} falhas, {s['bytes'] / 2**20:.1f} MB)")

        t = threading.Thread(target=rodar, name="aquecimento", daemon=True)
        t.start()
        return t

    def stats(self) -> dict:
        with self._lock:
            return {"itens": len(self._itens), "bytes": self._bytes,
                    "hits": self._hits, "misses": self._misses}
