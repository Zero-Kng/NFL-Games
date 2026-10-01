"""
Spec sem-terminal, tarefa 1: a regra que decide quando o app do .exe se encerra
sozinho (server/presenca.py), com um relógio falso.
"""

import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "server"))
from presenca import MAX_ABAS, MAX_ID, Presenca  # noqa: E402

TRES_MIN = "nenhuma aba do app deu sinal em 3 min"
ULTIMA = "a última aba do app foi fechada"


class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def nova():
    r = Relogio()
    return r, Presenca(agora=r)


def ate(r, p, fim, passo=5.0):
    """Avança o relógio até `fim` verificando a cada `passo` (como a vigia); devolve o último motivo."""
    motivo = None
    while r.t < fim:
        r.t = min(r.t + passo, fim)
        motivo = p.verificar()
        if motivo:
            return motivo
    return motivo


def test_nao_encerra_antes_da_primeira_aba():
    r, p = nova()
    assert ate(r, p, 3600) is None


def test_encerra_sem_sinal_em_3_min():
    r, p = nova()
    p.sinal("a")
    assert ate(r, p, 179, passo=1) is None
    r.t = 180
    assert p.verificar() == TRES_MIN


def test_encerra_15_s_depois_da_ultima_saida():
    r, p = nova()
    p.sinal("a")
    r.t = 10
    p.saiu("a")
    assert ate(r, p, 24, passo=1) is None
    r.t = 25
    assert p.verificar() == ULTIMA


def test_recarregar_nao_encerra():
    r, p = nova()
    p.sinal("a")
    r.t = 10
    p.saiu("a")
    r.t = 12
    p.sinal("b")
    assert ate(r, p, 40, passo=1) is None


def test_fechar_uma_de_duas_abas_nao_encerra():
    r, p = nova()
    p.sinal("a")
    p.sinal("b")
    p.saiu("a")
    while r.t < 600:
        assert ate(r, p, r.t + 30) is None
        p.sinal("b")


def test_salto_de_relogio_recomeca():
    r, p = nova()
    p.sinal("a")
    r.t = 5
    assert p.verificar() is None
    r.t = 7205                                   # o PC dormiu 2 h
    assert p.verificar() is None
    assert ate(r, p, 7205 + 175) is None
    assert ate(r, p, 7205 + 180) == TRES_MIN


def test_limite_de_abas_e_id_cortado():
    r, p = nova()
    for i in range(150):
        r.t += 0.01
        p.sinal(f"aba{i}")
    assert len(p.abas) <= MAX_ABAS
    assert "aba149" in p.abas and "aba0" not in p.abas      # as mais antigas saem
    p.sinal("x" * 1000)
    assert "x" * MAX_ID in p.abas and "x" * 1000 not in p.abas
