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
