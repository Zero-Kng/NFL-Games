"""
Porta ocupada por outro programa (ex.: um `manage.py runserver 8000` de outro
projeto). No Windows, com SO_REUSEADDR (o padrao do HTTPServer do Python), dois
programas conseguiam se ligar a mesma porta sem erro: o NFL Games dizia
"servindo em :8000", mas as conexoes iam para o outro programa, e o navegador
abria a pagina dele. Agora o servidor exige a porta so para si e, se ela estiver
ocupada, sai explicando; o rodar.py (e o executavel) usa a proxima porta livre
quando ninguem pediu uma porta especifica.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import rodar  # noqa: E402
from servidor_local import porta_livre  # noqa: E402


def ocupar(porta: int) -> socket.socket:
    """Um servidor de outro projeto na porta, do jeito do Django/HTTPServer (SO_REUSEADDR)."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", porta))
    s.listen()
    return s


@pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados/ ainda nao montado")
def test_servidor_nao_divide_a_porta_com_outro_programa():
    porta = porta_livre()
    outro = ocupar(porta)
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NFL_ESPERA_ERRO_S": "0"}
        r = subprocess.run([sys.executable, str(ROOT / "server" / "serve.py"), "--offline", "--port", str(porta)],
                           cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    finally:
        outro.close()
    saida = r.stdout + r.stderr
    assert r.returncode == 1, saida
    assert f"a porta {porta} esta ocupada por outro programa" in saida and "--port" in saida
    assert "Traceback" not in saida and "servindo em" not in saida


def test_porta_disponivel_ve_a_ocupada_por_outro_programa():
    porta = porta_livre()
    assert rodar.porta_disponivel("127.0.0.1", porta) is True
    outro = ocupar(porta)
    try:
        assert rodar.porta_disponivel("127.0.0.1", porta) is False
    finally:
        outro.close()


def test_sem_porta_pedida_usa_a_proxima_livre():
    porta = porta_livre()
    outro = ocupar(porta)
    try:
        escolhida, trocou = rodar.escolher_porta("127.0.0.1", None, inicial=porta)
    finally:
        outro.close()
    assert trocou is True and escolhida > porta


def test_sem_porta_pedida_e_a_padrao_livre_fica_com_ela():
    porta = porta_livre()
    assert rodar.escolher_porta("127.0.0.1", None, inicial=porta) == (porta, False)


def test_porta_pedida_nao_e_trocada():
    """Quem pediu --port quer aquela porta: se estiver ocupada, o servidor explica o erro."""
    porta = porta_livre()
    outro = ocupar(porta)
    try:
        assert rodar.escolher_porta("127.0.0.1", porta, inicial=8000) == (porta, False)
    finally:
        outro.close()


def test_main_avisa_e_usa_outra_porta(monkeypatch, capsys):
    porta = porta_livre()
    outro = ocupar(porta)
    recebido = {}
    monkeypatch.setattr(rodar, "PORTA_PADRAO", porta)
    monkeypatch.setattr(rodar, "faltando", lambda: [])
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: recebido.setdefault("opcoes", opcoes) and 0)
    try:
        assert rodar.main(["--sem-navegador"]) == 0
    finally:
        outro.close()
    saida = capsys.readouterr().out
    nova = int(recebido["opcoes"][recebido["opcoes"].index("--port") + 1])
    assert nova != porta
    assert f"a porta {porta} esta ocupada por outro programa; usando a {nova}" in saida
    assert f"http://127.0.0.1:{nova}" in saida
