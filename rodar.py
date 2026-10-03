"""
NFL GAMES - inicia o app (dados do nflverse, 2021 em diante) em Windows,
Linux e macOS.

    python rodar.py                  # sobe o servidor e abre o navegador
    python rodar.py --port 9000      # outra porta
    python rodar.py --offline        # so a copia local em dados/, sem internet
    python rodar.py --sem-navegador  # nao abre o navegador (so mostra o endereco)

As demais opcoes (--host, --max-pendentes) vao direto para o server/serve.py.
Do codigo: python rodar.py (ou ./rodar.sh no Linux e no macOS). Empacotado:
NFL-Games.exe (Windows) e nfl-games (Linux), gerados por tools/empacotar.py;
eles aceitam as mesmas opcoes.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PYTHON_MINIMO = (3, 10)
PORTA_PADRAO = int(os.environ.get("NFL_PORTA_PADRAO") or 8000)   # a variavel e so para testes
ESPERA_COPIA_S = 60                                     # a 2a copia espera a 1a responder por ate 60 s
ESPERA_COPIA_INTERVALO_S = 0.5
PORTAS_A_TENTAR = 20                                    # 8000 ocupada: tenta 8001, 8002... ate 8019
BIBLIOTECAS = ("pandas", "numpy")
PYTHON = "python" if os.name == "nt" else "python3"     # o nome que a pessoa digita no terminal
CONGELADO = bool(getattr(sys, "frozen", False))          # rodando como executavel (PyInstaller)
# Spec sem-terminal: o NFL-Games.exe do Windows roda sem console. As mensagens vao para
# dados/nfl-games.log, os erros que impedem o app de abrir viram uma janela de aviso, abrir
# de novo reaproveita a copia que ja esta rodando, e o app se encerra sozinho sem abas.
def modo_janela_atual(executavel: str, congelado: bool, sistema: str) -> bool:
    """Sem console no Windows: o .exe do PyInstaller ou o pythonw.exe (o atalho NFL Games.lnk,
    que roda o codigo atual pelo Python instalado, assinado e confiavel para o Windows)."""
    if sistema != "nt":
        return False
    return congelado or Path(executavel).name.lower() == "pythonw.exe"


MODO_JANELA = modo_janela_atual(sys.executable, CONGELADO, os.name)
NOME_LOG = "nfl-games.log"
_log = None                                             # o arquivo aberto por preparar_saida


def _utf8() -> None:
    """Acentos certos em qualquer terminal (no Windows, sem precisar do PYTHONIOENCODING)."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def checar_python(versao=sys.version_info) -> bool:
    if tuple(versao[:2]) >= PYTHON_MINIMO:
        return True
    print(f"[ERRO] O app precisa do Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} ou mais novo "
          f"(este e o {versao[0]}.{versao[1]}). Instale em https://www.python.org/downloads/", flush=True)
    return False


def faltando() -> list[str]:
    return [b for b in BIBLIOTECAS if importlib.util.find_spec(b) is None]


def pastas(congelado: bool = CONGELADO, interno: Path | None = None,
           executavel: Path | None = None) -> tuple[Path, Path]:
    """
    (interface, dados). A partir do codigo: as pastas do repositorio. No
    executavel: a interface vem de dentro dele (so leitura) e os dados ficam
    numa pasta dados/ ao lado do .exe, baixados na primeira execucao.
    """
    if not congelado:
        return RAIZ / "app", RAIZ / "dados"
    interno = Path(interno or getattr(sys, "_MEIPASS", RAIZ))
    executavel = Path(executavel or sys.executable)
    return interno / "app", executavel.resolve().parent / "dados"


def ler_opcoes(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None,
                    help=f"porta (padrao: {PORTA_PADRAO}, ou a proxima livre se ela estiver ocupada)")
    ap.add_argument("--offline", action="store_true", help="usa so a copia local em dados/, sem internet")
    ap.add_argument("--sem-navegador", action="store_true", help="nao abre o navegador")
    return ap.parse_known_args(argv)


def porta_disponivel(host: str, porta: int) -> bool:
    """Se da para o servidor se ligar a porta agora (a mesma exigencia de exclusividade dele)."""
    with socket.socket() as s:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((host, porta))
        except OSError:
            return False
    return True


def escolher_porta(host: str, pedida: int | None, inicial: int | None = None) -> tuple[int, bool]:
    """
    (porta, trocou). Porta pedida (--port) fica como esta: ocupada, o servidor
    explica o erro. Sem pedido, a padrao ou, se outro programa estiver nela, a
    proxima livre, para o duplo clique funcionar com outro projeto aberto.
    """
    if pedida is not None:
        return pedida, False
    inicial = PORTA_PADRAO if inicial is None else inicial
    for porta in range(inicial, inicial + PORTAS_A_TENTAR):
        if porta_disponivel(host, porta):
            return porta, porta != inicial
    return inicial, False


def opcoes_servidor(args: argparse.Namespace, extras: list[str]) -> list[str]:
    opcoes = ["--host", args.host, "--port", str(args.port)]
    if args.offline:
        opcoes.append("--offline")
    return opcoes + list(extras)


def _host_local(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "") else host


def endereco(host: str, porta: int) -> str:
    return f"http://{_host_local(host)}:{porta}"


def preparar_saida(dados: Path) -> Path | None:
    """Modo janela: stdout e stderr passam para dados/nfl-games.log, recomecado a cada abertura.
    Sem permissao de escrita, segue sem log (devolve None)."""
    global _log
    log = Path(dados) / NOME_LOG
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        novo = open(log, "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        # Sem console (sys.stdout/stderr None) e sem log, quem escreve neles quebraria (o servidor
        # registra cada pedido no stderr): sem log, as mensagens vao para o nada.
        nada = None
        for nome in ("stdout", "stderr"):
            if getattr(sys, nome) is None:
                nada = nada or open(os.devnull, "w", encoding="utf-8")
                setattr(sys, nome, nada)
        return None
    if _log is not None:
        try:
            _log.close()
        except OSError:
            pass
    _log = novo
    sys.stdout = sys.stderr = novo
    return log


def avisar(mensagem: str, mostrar=None, icone: int = 0x10) -> None:
    """Janela de aviso do Windows (icone: 0x10 erro, 0x40 informacao). Com NFL_SEM_AVISO=1
    (testes, GitHub Actions), so o log: uma janela travaria o teste esperando um clique."""
    if os.environ.get("NFL_SEM_AVISO") == "1":
        print(f"[aviso] {mensagem}", flush=True)
        return
    if mostrar is None:
        import ctypes  # noqa: PLC0415 - so no Windows
        mostrar = ctypes.windll.user32.MessageBoxW
    # icone | MB_SETFOREGROUND | MB_TOPMOST: na frente do navegador, que abriu antes
    mostrar(None, mensagem, "NFL Games", icone | 0x10000 | 0x40000)


_travas = []                                            # os mutex ficam abertos enquanto o processo vive


def trava_unica(nome: str = "Local\\NFL-Games") -> bool:
    """Mutex com nome do Windows: so a 1a copia aberta pega. Dois duplos cliques seguidos nao sobem
    duas copias na mesma dados/ (a 2a espera a 1a responder). Fora do Windows, sempre pega."""
    if os.name != "nt":
        return True
    import ctypes  # noqa: PLC0415
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    alca = k32.CreateMutexW(None, False, nome)
    ja_existia = k32.GetLastError() == 183          # ERROR_ALREADY_EXISTS
    if alca:
        _travas.append(alca)
    return not ja_existia


_abertura = {"fechar": None, "pronta": None, "thread": None, "erro": None}


def abrir_abertura(imagem: Path) -> None:
    """A logo de abertura sem o PyInstaller (pelo atalho/pythonw): uma janela sem borda do Tkinter,
    centralizada e na frente, ate fechar_abertura(). O magenta e a cor-chave do transparente
    (a imagem so tem pontos opacos ou transparentes: sem linha roxa nos cantos)."""
    fechar, pronta = threading.Event(), threading.Event()

    def janela():
        try:
            import tkinter as tk  # noqa: PLC0415
            raiz = tk.Tk()
            raiz.overrideredirect(True)
            raiz.attributes("-topmost", True)
            chave = "#ff00ff"
            raiz.configure(bg=chave)
            raiz.attributes("-transparentcolor", chave)
            foto = tk.PhotoImage(master=raiz, file=str(imagem))
            rotulo = tk.Label(raiz, image=foto, bg=chave, bd=0, highlightthickness=0)
            rotulo.pack()
            largura, altura = foto.width(), foto.height()
            raiz.geometry(f"{largura}x{altura}+{(raiz.winfo_screenwidth() - largura) // 2}"
                          f"+{(raiz.winfo_screenheight() - altura) // 2}")

            def vigiar():
                if fechar.is_set():
                    raiz.destroy()
                else:
                    raiz.after(100, vigiar)

            raiz.after(100, vigiar)
            pronta.set()
            raiz.mainloop()
            # O Tcl tem de ser liberado na thread que o criou (senao vaza; gh-83274)
            del rotulo, foto, raiz
            import gc  # noqa: PLC0415
            gc.collect()
        except Exception as e:  # noqa: BLE001 - sem a logo, o app abre do mesmo jeito
            _abertura["erro"] = repr(e)
            pronta.set()

    t = threading.Thread(target=janela, name="abertura", daemon=True)
    _abertura.update(fechar=fechar, pronta=pronta, thread=t, erro=None)
    t.start()


def fechar_abertura() -> None:
    """Fecha a logo da abertura (--splash do PyInstaller ou a janela do Tkinter); sem ela, nao faz nada."""
    if _abertura["fechar"] is not None:
        _abertura["fechar"].set()
    try:
        import pyi_splash  # noqa: PLC0415 - so existe no executavel com --splash
        pyi_splash.close()
    except Exception:  # noqa: BLE001 - sem a logo (codigo, Linux) ou ja fechada
        pass


def procurar_copia(host: str, portas: range, perguntar=None) -> int | None:
    """A 1a porta em que ja roda um NFL Games (pela resposta do /api/estado, nao so pela
    porta ocupada), inclusive ainda carregando os dados."""
    import json  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    def _perguntar(url):
        with urllib.request.urlopen(url, timeout=2) as r:   # so portas ocupadas: uma copia montando dados demora
            return json.load(r)

    perguntar = perguntar or _perguntar
    for porta in portas:
        # Porta livre: ninguem nela, pula sem conectar (no Windows, conectar numa porta local
        # fechada leva ~2 s; com 20 portas, a abertura ficava ~10 s mais lenta).
        if porta_disponivel(host, porta):
            continue
        try:
            estado = perguntar(f"http://{_host_local(host)}:{porta}/api/estado")
        except Exception:  # noqa: BLE001 - porta fechada, outro programa, resposta que nao e JSON
            continue
        if isinstance(estado, dict) and estado.get("app") == "NFL Games":
            return porta
    return None


def _texto_do_aviso(motivo: str, log: Path | None) -> str:
    return (f"O NFL Games não conseguiu abrir.\n\n{motivo}\n\n"
            f"Detalhes em: {log if log else 'sem arquivo de log'}")


def vigiar_e_abrir(host: str, porta: int, processo, abrir=webbrowser.open, intervalo_s: float = 0.5,
                   ao_falhar=None) -> bool:
    """
    Espera o servidor aceitar conexoes e abre o navegador. Na primeira subida
    isso leva alguns minutos (download dos dados), entao espera enquanto o
    servidor estiver no ar (processo.poll() None). Sem navegador (maquina sem
    tela), mostra o endereco.
    """
    url = endereco(host, porta)
    while processo.poll() is None:
        try:
            with socket.create_connection((_host_local(host), porta), timeout=1):
                pass
        except OSError:
            time.sleep(intervalo_s)
            continue
        try:
            abriu = abrir(url)
        except Exception:  # noqa: BLE001 - qualquer falha do navegador vira "abra voce"
            abriu = False
        fechar_abertura()                           # o navegador assume daqui (sem-terminal)
        if abriu is False:
            print(f"\nAbra no navegador: {url}\n", flush=True)
            if ao_falhar:                           # no .exe nao ha terminal para ler o endereco
                ao_falhar(url)
        return True
    return False


class _Servindo:
    """O servidor roda neste processo; poll() diz se ele ja terminou (como um subprocesso)."""

    def __init__(self):
        self.codigo = None

    def poll(self):
        return self.codigo


def rodar_servidor(opcoes: list[str]) -> int:
    """Roda o server/serve.py neste processo (no executavel nao ha outro Python para chamar)."""
    for pasta in (RAIZ / "server", RAIZ / "etl"):
        if str(pasta) not in sys.path:
            sys.path.insert(0, str(pasta))
    import serve  # noqa: PLC0415 - depende das pastas acima e do NFL_APP/NFL_DADOS ja definidos
    sys.argv = ["serve.py", *opcoes]
    return serve.main()


def _esperar_enter() -> None:
    """Executavel aberto com duplo clique: a janela fecharia antes de a pessoa ler o erro."""
    if CONGELADO and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPressione Enter para fechar...")
        except (EOFError, KeyboardInterrupt):
            pass


def main(argv: list[str] | None = None, modo_janela: bool | None = None) -> int:
    janela = MODO_JANELA if modo_janela is None else modo_janela
    if janela and not CONGELADO:              # pelo atalho (pythonw): a logo vem do Tkinter, ja de cara
        abrir_abertura(RAIZ / "tools" / "abertura.png")
    saida = {"log": None}                     # o log so e recomecado quando o app vai subir de fato
    try:
        return _main(argv, janela, saida)
    except Exception as e:  # noqa: BLE001 - sem terminal, a pessoa so ve a janela de aviso
        if not janela:
            raise
        import traceback  # noqa: PLC0415
        traceback.print_exc()
        fechar_abertura()
        avisar(_texto_do_aviso(f"Erro inesperado: {e!r}", saida["log"]))
        return 1


def _main(argv: list[str] | None, janela: bool, saida: dict) -> int:
    _utf8()
    if not checar_python():
        return 1
    falta = [] if CONGELADO else faltando()          # o executavel ja traz as bibliotecas
    if falta:
        print(f"[ERRO] Faltam bibliotecas do Python: {', '.join(falta)}.\n"
              f"       Instale com:  {PYTHON} -m pip install pandas numpy", flush=True)
        if janela:                                    # pelo atalho nao ha terminal para ler isso
            fechar_abertura()
            avisar(f"Faltam bibliotecas do Python: {', '.join(falta)}.\n\n"
                   f"Instale num terminal com:\n{PYTHON} -m pip install pandas numpy")
        return 1

    args, extras = ler_opcoes(argv)
    if janela and args.port is None:
        # Ja ha um NFL Games rodando (o .exe aberto de novo): so abre o navegador nele. Se a trava
        # ja estava pega, outra copia acabou de abrir (dois duplos cliques seguidos): espera ela
        # responder em vez de subir uma segunda copia na mesma dados/.
        portas = range(PORTA_PADRAO, PORTA_PADRAO + PORTAS_A_TENTAR)
        aberta = procurar_copia(args.host, portas)
        if aberta is None and not trava_unica():
            limite = time.monotonic() + ESPERA_COPIA_S
            while aberta is None and time.monotonic() < limite:
                time.sleep(ESPERA_COPIA_INTERVALO_S)
                aberta = procurar_copia(args.host, portas)
        if aberta is not None:
            url = endereco(args.host, aberta)
            print(f"o NFL Games ja esta aberto em {url}; abrindo o navegador nele.", flush=True)
            if not args.sem_navegador:
                webbrowser.open(url)
            fechar_abertura()
            return 0
    if janela:
        saida["log"] = preparar_saida(pastas()[1])  # so agora: reaproveitar nao apaga o log da copia aberta
    padrao = PORTA_PADRAO
    args.port, trocou = escolher_porta(args.host, args.port)
    if trocou:
        print(f"[aviso] a porta {padrao} esta ocupada por outro programa; usando a {args.port}.", flush=True)
    app, dados = pastas()
    os.environ.setdefault("NFL_APP", str(app))
    os.environ.setdefault("NFL_DADOS", str(dados))
    url = endereco(args.host, args.port)
    print("\n=== NFL GAMES ===\n\n"
          "Na primeira execucao o servidor baixa e monta os dados do nflverse\n"
          f"(~330 MB, alguns minutos; o progresso aparece abaixo) em {os.environ['NFL_DADOS']}.\n"
          "Precisa de internet. Nas proximas, sobe direto com a copia local e busca so o que mudou.\n"
          f"O app fica em {url}" + ("" if args.sem_navegador else " (o navegador abre sozinho)") + "\n"
          + ("Para fechar: \"Encerrar o app\" no menu, ou feche as abas do app (ele se encerra sozinho).\n"
             if janela else "Ctrl+C (ou fechar esta janela) para parar.\n"), flush=True)

    servindo = _Servindo()
    if args.sem_navegador:
        # Sem navegador, a logo da abertura fecha quando a porta abre (senao ficaria ate o fim).
        abrir, ao_falhar = (lambda url: None), None
    else:
        abrir = webbrowser.open
        ao_falhar = (lambda url: avisar(f"O navegador não abriu sozinho. Abra o NFL Games em: {url}", icone=0x40)
                     ) if janela else None
    threading.Thread(target=vigiar_e_abrir, args=(args.host, args.port, servindo),
                     kwargs={"abrir": abrir, "ao_falhar": ao_falhar}, daemon=True).start()
    opcoes = opcoes_servidor(args, extras) + (["--encerrar-sozinho"] if janela else [])
    try:
        codigo = rodar_servidor(opcoes)
    except KeyboardInterrupt:                       # Ctrl+C antes de o servidor ficar no ar
        print("\nencerrado.", flush=True)
        return 0
    finally:
        servindo.codigo = -1

    if codigo:
        print("\n[ERRO] O servidor nao subiu. Veja a mensagem acima.\n"
              "       Se for a primeira execucao, confira a conexao com a internet.", flush=True)
        if janela:
            fechar_abertura()
            avisar(_texto_do_aviso("O servidor não subiu. Se for a primeira execução, "
                                   "confira a conexão com a internet.", saida["log"]))
            return codigo
        if not CONGELADO:
            print(f"       Se faltar biblioteca, instale:  {PYTHON} -m pip install pandas numpy", flush=True)
        _esperar_enter()
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
