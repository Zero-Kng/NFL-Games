"""
rodar.py: o inicializador do app em Windows, Linux e macOS, a partir do código
(python rodar.py, ./rodar.sh) ou empacotado (NFL-Games.exe, nfl-games). Confere
o Python e as bibliotecas, roda o server/serve.py no mesmo processo, espera a
porta responder e abre o navegador.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rodar  # noqa: E402
from servidor_local import porta_livre  # noqa: E402


class ProcessoFalso:
    """Um servidor que está no ar (poll() None) ou que já saiu com um código."""

    def __init__(self, codigo=None):
        self.codigo = codigo

    def poll(self):
        return self.codigo


# ------------------------------------------------------------ Python e bibliotecas
def test_python_antigo_recusado(capsys):
    assert rodar.checar_python((3, 9, 18)) is False
    assert "3.10" in capsys.readouterr().out
    assert rodar.checar_python((3, 10, 0)) is True


def test_bibliotecas_faltando_mostra_o_comando(monkeypatch, capsys):
    monkeypatch.setattr(rodar, "faltando", lambda: ["pandas"])
    assert rodar.main(["--sem-navegador"]) == 1
    saida = capsys.readouterr().out
    assert "pandas" in saida and "-m pip install pandas numpy" in saida


def test_faltando_ve_o_que_nao_esta_instalado(monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome: None if nome == "numpy" else real(nome))
    assert rodar.faltando() == ["numpy"]


# ------------------------------------------------------------ opções e pastas
def test_repassa_as_opcoes_ao_servidor():
    args, extras = rodar.ler_opcoes(["--port", "9000", "--offline", "--max-pendentes", "8", "--sem-navegador"])
    assert rodar.opcoes_servidor(args, extras) == ["--host", "127.0.0.1", "--port", "9000", "--offline",
                                                   "--max-pendentes", "8"]
    assert args.sem_navegador is True


def test_pastas_a_partir_do_codigo():
    app, dados = rodar.pastas(congelado=False)
    assert app == ROOT / "app" and dados == ROOT / "dados"


def test_pastas_no_executavel(tmp_path):
    """No executável, a interface vem de dentro dele e os dados ficam ao lado do .exe."""
    exe = tmp_path / "NFL-Games.exe"
    app, dados = rodar.pastas(congelado=True, interno=tmp_path / "_MEI123", executavel=exe)
    assert app == tmp_path / "_MEI123" / "app" and dados == tmp_path / "dados"


@pytest.mark.parametrize("host,esperado", [("127.0.0.1", "http://127.0.0.1:8000"),
                                           ("0.0.0.0", "http://127.0.0.1:8000"),
                                           ("localhost", "http://localhost:8000")])
def test_endereco_do_app(host, esperado):
    assert rodar.endereco(host, 8000) == esperado


# ------------------------------------------------------------ navegador
def _escutando():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s


def test_abre_o_navegador_quando_a_porta_responde():
    s = _escutando()
    porta = s.getsockname()[1]
    abertos = []
    try:
        ok = rodar.vigiar_e_abrir("127.0.0.1", porta, ProcessoFalso(), abrir=abertos.append, intervalo_s=0.05)
    finally:
        s.close()
    assert ok is True and abertos == [f"http://127.0.0.1:{porta}"]


def test_espera_a_porta_abrir():
    porta = porta_livre()
    abertos = []
    t = threading.Thread(target=lambda: abertos.append(
        rodar.vigiar_e_abrir("127.0.0.1", porta, ProcessoFalso(), abrir=lambda u: None, intervalo_s=0.05)))
    t.start()
    time.sleep(0.3)                     # a porta ainda está fechada: segue esperando
    assert t.is_alive()
    s = socket.socket()
    s.bind(("127.0.0.1", porta))
    s.listen()
    t.join(5)
    s.close()
    assert abertos == [True]


def test_nao_abre_se_o_servidor_saiu():
    abertos = []
    ok = rodar.vigiar_e_abrir("127.0.0.1", porta_livre(), ProcessoFalso(codigo=1), abrir=abertos.append,
                              intervalo_s=0.05)
    assert ok is False and abertos == []


def test_sem_tela_mostra_o_endereco(capsys):
    s = _escutando()
    porta = s.getsockname()[1]
    try:
        rodar.vigiar_e_abrir("127.0.0.1", porta, ProcessoFalso(), abrir=lambda u: False, intervalo_s=0.05)
    finally:
        s.close()
    assert f"http://127.0.0.1:{porta}" in capsys.readouterr().out


def test_sem_navegador_nao_abre(monkeypatch):
    chamados = []
    monkeypatch.setattr(rodar, "faltando", lambda: [])
    monkeypatch.setattr(rodar, "vigiar_e_abrir", lambda *a, **k: chamados.append(a))
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: 0)
    assert rodar.main(["--sem-navegador"]) == 0
    assert chamados == []


def test_servidor_recebe_as_opcoes_e_as_pastas(monkeypatch):
    recebido = {}
    monkeypatch.setattr(rodar, "faltando", lambda: [])
    monkeypatch.delenv("NFL_APP", raising=False)
    monkeypatch.delenv("NFL_DADOS", raising=False)

    def servidor(opcoes):
        recebido["opcoes"] = opcoes
        recebido["app"], recebido["dados"] = os.environ["NFL_APP"], os.environ["NFL_DADOS"]
        return 0

    monkeypatch.setattr(rodar, "rodar_servidor", servidor)
    assert rodar.main(["--sem-navegador", "--offline", "--port", "9100"]) == 0
    assert recebido == {"opcoes": ["--host", "127.0.0.1", "--port", "9100", "--offline"],
                        "app": str(ROOT / "app"), "dados": str(ROOT / "dados")}


def test_codigo_de_erro_do_servidor_e_repassado(monkeypatch, capsys):
    monkeypatch.setattr(rodar, "faltando", lambda: [])
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: 1)
    assert rodar.main(["--sem-navegador"]) == 1
    assert "O servidor nao subiu" in capsys.readouterr().out


def test_ctrl_c_na_carga_encerra_sem_erro(monkeypatch, capsys):
    monkeypatch.setattr(rodar, "faltando", lambda: [])

    def interrompido(opcoes):
        raise KeyboardInterrupt

    monkeypatch.setattr(rodar, "rodar_servidor", interrompido)
    assert rodar.main(["--sem-navegador"]) == 0
    assert "encerrado" in capsys.readouterr().out


@pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados/ ainda nao montado")
def test_servidor_serve_a_pasta_do_app_indicada(tmp_path):
    """NFL_APP: no executável, a interface vem da pasta interna dele, não do repositório."""
    from servidor_local import servidor
    (tmp_path / "index.html").write_text("<title>app do executavel</title>", encoding="utf-8")
    with servidor(esperar_aquecimento=False, env={"NFL_APP": str(tmp_path)}) as srv:
        with urllib.request.urlopen(srv.url + "/") as r:
            assert b"app do executavel" in r.read()


# ------------------------------------------------------------ empacotamento
def test_executavel_leva_a_interface_e_o_icone_da_logo():
    import empacotar
    args = empacotar.argumentos(Path("dist"), Path("build"))
    assert any(a.endswith(f"app{os.pathsep}app") for a in args)
    if os.name == "nt":                                # o PyInstaller so usa o icone no Windows (e no macOS)
        i = args.index("--icon")
        assert args[i + 1] == str(ROOT / "app" / "img" / "icone.ico") and Path(args[i + 1]).is_file()
    else:
        assert "--icon" not in args


# ------------------------------------------------------------ atalho
def test_rodar_sh_chama_o_rodar_py():
    assert not (ROOT / "RODAR.bat").exists()             # substituído pelo executável e pelo rodar.py
    sh = (ROOT / "rodar.sh").read_text(encoding="utf-8")
    assert "rodar.py" in sh
    assert sh.startswith("#!/usr/bin/env sh")
    assert "\r\n" not in sh                               # sh não aceita CRLF
    modo = subprocess.run(["git", "ls-files", "-s", "rodar.sh"], cwd=ROOT, capture_output=True, text=True).stdout
    assert modo.startswith("100755"), modo                # executável no Git


# ------------------------------------------------------------ de ponta a ponta
def _matar_arvore(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(10)


@pytest.mark.skipif(not (ROOT / "dados" / "jogos.npz").exists(), reason="dados/ ainda nao montado")
def test_sobe_o_app_de_ponta_a_ponta():
    porta = porta_livre()
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, str(ROOT / "rodar.py"), "--offline", "--sem-navegador", "--port", str(porta)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", **extra)
    try:
        t0 = time.time()
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2) as r:
                    assert r.status == 200 and b"NFL Games" in r.read()
                    break
            except OSError:
                assert proc.poll() is None, "o rodar.py saiu antes de o app responder"
                assert time.time() - t0 < 90, "o app nao respondeu em 90 s"
                time.sleep(0.3)
    finally:
        _matar_arvore(proc)
    saida = proc.stdout.read()
    assert "NFL GAMES" in saida and f"http://127.0.0.1:{porta}" in saida


# ================================================ sem-terminal, tarefa 4 (modo janela)
import json  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402


def _servidor_de_teste(corpo: bytes, tipo="application/json"):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    porta = porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, porta


def test_procurar_copia_acha_o_app():
    srv, porta = _servidor_de_teste(json.dumps({"app": "NFL Games", "pronto": True}).encode())
    try:
        assert rodar.procurar_copia("127.0.0.1", range(porta, porta + 1)) == porta
    finally:
        srv.shutdown()


def test_procurar_copia_acha_copia_ainda_carregando():
    """Foco de revisão 2: a 1ª cópia ainda baixando os dados também conta."""
    srv, porta = _servidor_de_teste(json.dumps({"app": "NFL Games", "pronto": False, "fase": "preparando"}).encode())
    try:
        assert rodar.procurar_copia("127.0.0.1", range(porta, porta + 1)) == porta
    finally:
        srv.shutdown()


def test_procurar_copia_ignora_outro_programa():
    srv, porta = _servidor_de_teste(b"<html>outro programa</html>", "text/html")
    try:
        assert rodar.procurar_copia("127.0.0.1", range(porta, porta + 2)) is None
    finally:
        srv.shutdown()


@pytest.fixture
def janela(monkeypatch, tmp_path):
    """main() no modo janela, com dublês: nada de log de verdade, janela de aviso ou navegador."""
    reg = {"avisos": [], "fechou": 0, "abriu": [], "opcoes": None, "enter": 0}
    monkeypatch.setattr(rodar, "faltando", lambda: [])
    monkeypatch.setattr(rodar, "preparar_saida", lambda dados: tmp_path / "nfl-games.log")
    monkeypatch.setattr(rodar, "avisar", lambda msg, mostrar=None: reg["avisos"].append(msg))
    monkeypatch.setattr(rodar, "fechar_abertura", lambda: reg.__setitem__("fechou", reg["fechou"] + 1))
    monkeypatch.setattr(rodar.webbrowser, "open", lambda url: reg["abriu"].append(url) or True)
    monkeypatch.setattr(rodar, "_esperar_enter", lambda: reg.__setitem__("enter", reg["enter"] + 1))
    monkeypatch.setattr(rodar, "procurar_copia", lambda host, portas: None)
    return reg


def test_modo_janela_reaproveita_a_copia(janela, monkeypatch):
    monkeypatch.setattr(rodar, "procurar_copia", lambda host, portas: 8000)
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: pytest.fail("não podia subir outro servidor"))
    assert rodar.main([], modo_janela=True) == 0
    assert janela["abriu"] == ["http://127.0.0.1:8000"] and janela["fechou"] >= 1


def test_modo_janela_com_porta_dada_nao_procura(janela, monkeypatch):
    monkeypatch.setattr(rodar, "procurar_copia", lambda host, portas: pytest.fail("não devia procurar"))
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: 0)
    assert rodar.main(["--port", "9000", "--sem-navegador"], modo_janela=True) == 0


def test_modo_janela_passa_encerrar_sozinho(janela, monkeypatch):
    recebidas = []
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: recebidas.append(opcoes) or 0)
    rodar.main(["--sem-navegador", "--port", "9101"], modo_janela=True)
    rodar.main(["--sem-navegador", "--port", "9101"], modo_janela=False)
    assert "--encerrar-sozinho" in recebidas[0] and "--encerrar-sozinho" not in recebidas[1]


def test_modo_janela_erro_avisa_com_o_log(janela, monkeypatch, tmp_path):
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: 1)
    assert rodar.main(["--sem-navegador"], modo_janela=True) == 1
    aviso = janela["avisos"][0]
    assert aviso.startswith("O NFL Games não conseguiu abrir.") and str(tmp_path / "nfl-games.log") in aviso
    assert janela["enter"] == 0 and janela["fechou"] >= 1


def test_modo_janela_excecao_inesperada(janela, monkeypatch, capsys):
    def quebra(opcoes):
        raise RuntimeError("x")

    monkeypatch.setattr(rodar, "rodar_servidor", quebra)
    assert rodar.main(["--sem-navegador"], modo_janela=True) == 1
    assert "RuntimeError" in capsys.readouterr().err
    assert janela["avisos"] and "RuntimeError" in janela["avisos"][0]


def test_preparar_saida_grava_e_recomeca(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    log = rodar.preparar_saida(tmp_path / "dados")
    print("a")
    assert rodar.preparar_saida(tmp_path / "dados") == log == tmp_path / "dados" / "nfl-games.log"
    print("b")
    sys.stdout.flush()
    conteudo = log.read_text(encoding="utf-8")
    sys.stdout.close()
    assert conteudo == "b\n"


def test_preparar_saida_sem_permissao(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    (tmp_path / "dados").write_text("um arquivo, não uma pasta")
    assert rodar.preparar_saida(tmp_path / "dados") is None


def test_avisar_sem_aviso_nos_testes(monkeypatch, capsys):
    monkeypatch.setenv("NFL_SEM_AVISO", "1")
    mostrou = []
    rodar.avisar("teste", mostrar=lambda *a: mostrou.append(a))
    assert mostrou == [] and "[aviso] teste" in capsys.readouterr().out


def test_modo_janela_reaproveitar_nao_apaga_o_log_da_copia(janela, monkeypatch, tmp_path):
    """Abrir o .exe de novo não pode recomeçar o log da cópia que já está rodando."""
    chamadas = []
    monkeypatch.setattr(rodar, "preparar_saida", lambda dados: chamadas.append(dados) or tmp_path / "x.log")
    monkeypatch.setattr(rodar, "procurar_copia", lambda host, portas: 8000)
    monkeypatch.setattr(rodar, "rodar_servidor", lambda opcoes: pytest.fail("não podia subir outro servidor"))
    assert rodar.main([], modo_janela=True) == 0
    assert chamadas == []
