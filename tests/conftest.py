import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from servidor_local import servidor as _servidor  # noqa: E402


@pytest.fixture(scope="session")
def servidor():
    """Servidor real numa porta livre, compartilhado pela sessao de testes."""
    with _servidor() as srv:
        yield srv


def http_get(url: str, headers: dict | None = None):
    """(status, cabecalhos, corpo) sem lancar em 4xx/5xx."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def http_json(url: str):
    status, _h, body = http_get(url)
    return status, json.loads(body)


# ------------------------------------------------------------ site-publico
# O site exportado (tools/exportar.py) para os testes da fonte estática e da bateria
# de interface na fonte "estatico". Exportar tudo leva alguns minutos; o resultado fica
# em build/site-testes/ e é reaproveitado enquanto os dados e o código não mudarem.
SITE_TESTES = ROOT / "build" / "site-testes"


def _chave_do_site() -> str:
    import hashlib
    h = hashlib.sha256()
    arquivos = [ROOT / "dados" / "manifest.json", ROOT / "tools" / "exportar.py", ROOT / "etl" / "ratings.py"]
    arquivos += sorted((ROOT / "server").glob("*.py"))       # app/ fica de fora: é copiado de novo a cada sessão
    for p in arquivos:
        h.update(str(p.relative_to(ROOT)).encode())
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()


@pytest.fixture(scope="session")
def site_exportado() -> Path:
    import shutil
    import exportar
    pasta, chave_arq = SITE_TESTES / "NFL-Games", SITE_TESTES / "chave.txt"
    chave = _chave_do_site()
    if not (chave_arq.exists() and chave_arq.read_text() == chave and (pasta / "api" / "versao.json").exists()):
        if pasta.exists():
            shutil.rmtree(pasta)
        exportar.exportar(ROOT / "dados", pasta, processos=4)
        chave_arq.write_text(chave)
    else:
        exportar.copiar_interface(pasta)                     # a interface atual sobre os dados já exportados
    return pasta


@pytest.fixture(scope="session")
def site(site_exportado):
    """URL do site exportado, servido no subcaminho /NFL-Games/ (como no GitHub Pages)."""
    from servidor_estatico import site_local
    with site_local(site_exportado) as url:
        yield url
