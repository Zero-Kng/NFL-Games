"""Garante que a infraestrutura de teste (tarefa 1.1) funciona."""

from conftest import http_json


def test_fixture_servidor_responde_meta(servidor):
    status, meta = http_json(servidor.url + "/api/meta")
    assert status == 200
    assert meta["season"] >= 2026 and len(meta["seasons"]) >= 6


# ------------------------------------------------ site-publico, tarefa 6
def test_workflow_pages():
    """Publicação diária no GitHub Pages: gatilhos, permissões mínimas e passos (design, componente 6)."""
    import yaml
    from conftest import ROOT
    texto = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(texto)
    gatilhos = wf.get("on", wf.get(True))                  # o YAML 1.1 lê a chave "on" como True
    assert gatilhos["schedule"] == [{"cron": "0 10 * * *"}]
    assert gatilhos["push"]["branches"] == ["main"]
    assert set(gatilhos["push"]["paths"]) == {"app/**", "server/**", "etl/**", "tools/exportar.py",
                                              ".github/workflows/pages.yml"}
    assert "workflow_dispatch" in gatilhos
    assert wf["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    assert wf["concurrency"]["group"] == "pages"
    passos = [p for job in wf["jobs"].values() for p in job["steps"]]
    ordem = [next((i for i, p in enumerate(passos) if alvo in (p.get("run", "") + p.get("uses", ""))), None)
             for alvo in ("etl/montar.py", "tools/exportar.py", "actions/upload-pages-artifact", "actions/deploy-pages")]
    assert None not in ordem and ordem == sorted(ordem), ordem
    upload = next(p for p in passos if "upload-pages-artifact" in p.get("uses", ""))
    assert upload["with"]["path"] == "site"
    assert "git push" not in texto and "contents: write" not in texto


def test_workflow_pages_autentica_a_api_do_github():
    """Revisão final: sem token, a API do GitHub limita a 60 chamadas/hora por IP, e o --estrito
    faria a publicação diária falhar por isso."""
    import yaml
    from conftest import ROOT
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8"))
    montar = next(p for job in wf["jobs"].values() for p in job["steps"] if "etl/montar.py" in p.get("run", ""))
    assert montar["env"]["GITHUB_TOKEN"] == "${{ github.token }}"


# ------------------------------------------------ sem-terminal, tarefa 5
def _empacotar():
    import sys
    from conftest import ROOT
    sys.path.insert(0, str(ROOT / "tools"))
    import empacotar
    return empacotar, ROOT


def test_empacotar_windows_sem_console_com_logo(tmp_path):
    empacotar, ROOT = _empacotar()
    args = empacotar.argumentos(tmp_path / "dist", tmp_path / "build", windows=True)
    assert "--windowed" in args and "--console" not in args
    assert args[args.index("--splash") + 1] == str(ROOT / "tools" / "abertura.png")


def test_empacotar_linux_com_console(tmp_path):
    empacotar, _ = _empacotar()
    args = empacotar.argumentos(tmp_path / "dist", tmp_path / "build", windows=False)
    assert "--console" in args and "--windowed" not in args and "--splash" not in args


def test_abertura_png():
    from PIL import Image
    _, ROOT = _empacotar()
    img = Image.open(ROOT / "tools" / "abertura.png")
    assert img.size == (360, 240) and img.mode == "RGBA"
    # A tela de abertura do PyInstaller não desenha transparência parcial: usa uma cor-chave
    # (magenta), e os pixels semitransparentes dos cantos viravam uma linha roxa na borda.
    assert set(img.getchannel("A").tobytes()) <= {0, 255}
