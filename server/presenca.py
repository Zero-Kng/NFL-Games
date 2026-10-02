"""
Presença das abas do app (spec sem-terminal): decide quando o servidor do
NFL-Games.exe se encerra sozinho, depois que a última aba fecha.

Cada aba dá sinal a cada 30 s (POST /api/presenca) e avisa ao fechar. A vigia do
servidor chama verificar() a cada 5 s e, com um motivo, encerra o app.

Regras do verificar(), nesta ordem:
  1. relógio saltou (o PC dormiu): recomeça a contagem;
  2. nenhuma aba deu sinal desde a abertura: segue rodando (1ª carga, navegador fechado);
  3. não sobrou aba e a saída tem saida_s: encerra;
  4. todas as abas sem sinal há limite_s: encerra.
"""

from __future__ import annotations

import threading
import time

MAX_ABAS = 100        # uma página não consegue encher a memória do servidor
MAX_ID = 64

ULTIMA_ABA = "a última aba do app foi fechada"
SEM_SINAL = "nenhuma aba do app deu sinal em 3 min"


class Presenca:
    def __init__(self, agora=time.monotonic, limite_s: float = 180.0, saida_s: float = 15.0,
                 salto_s: float = 60.0):
        self.agora, self.limite_s, self.saida_s, self.salto_s = agora, limite_s, saida_s, salto_s
        self.abas: dict[str, float] = {}           # aba -> instante do último sinal
        self.alguma_vez = False
        self.saida_em: float | None = None          # instante em que a última aba saiu
        self.ultima_verificacao = agora()
        self._lock = threading.Lock()

    def sinal(self, aba: str) -> None:
        with self._lock:
            self.abas[str(aba)[:MAX_ID]] = self.agora()
            self.alguma_vez = True
            self.saida_em = None
            while len(self.abas) > MAX_ABAS:
                del self.abas[min(self.abas, key=self.abas.get)]

    def saiu(self, aba: str) -> None:
        with self._lock:
            self.abas.pop(str(aba)[:MAX_ID], None)
            if self.alguma_vez and not self.abas:
                self.saida_em = self.agora()

    def verificar(self) -> str | None:
        with self._lock:
            agora = self.agora()
            pulo = agora - self.ultima_verificacao
            self.ultima_verificacao = agora
            if pulo > self.salto_s:                  # o PC dormiu: recomeça a contagem
                self.abas = {a: agora for a in self.abas}
                if self.saida_em is not None:
                    self.saida_em = agora
                return None
            if not self.alguma_vez:
                return None
            if not self.abas:
                if self.saida_em is not None and agora - self.saida_em >= self.saida_s:
                    return ULTIMA_ABA
                return None
            if all(agora - t >= self.limite_s for t in self.abas.values()):
                return SEM_SINAL
            return None
