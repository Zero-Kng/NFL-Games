"""
Serve uma pasta de site estático (a saída do tools/exportar.py) num subcaminho, como
o GitHub Pages faz com https://zero-kng.github.io/NFL-Games/. Só para testes.

    with site_local(Path("site")) as url:
        url                      # http://127.0.0.1:<porta>/NFL-Games

Os .gz saem como arquivo comum (application/gzip), como o Pages os guarda; com
gz_como_encoding=True, saem com Content-Encoding: gzip, e o navegador os descompacta
sozinho (o outro jeito que um servidor pode entregá-los).
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from servidor_local import porta_livre


class _Handler(SimpleHTTPRequestHandler):
    prefixo = "/NFL-Games/"
    gz_como_encoding = False
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".json": "application/json", ".gz": "application/gzip"}

    def translate_path(self, path):
        caminho = urlsplit(path).path
        if not caminho.startswith(self.prefixo):
            return str(Path(self.directory) / "__fora_do_site__")      # 404 fora do subcaminho
        return super().translate_path("/" + caminho[len(self.prefixo):])

    def end_headers(self):
        if self.gz_como_encoding and urlsplit(self.path).path.endswith(".gz"):
            self.send_header("Content-Encoding", "gzip")
        super().end_headers()

    def guess_type(self, path):
        if self.gz_como_encoding and str(path).endswith(".gz"):
            return "application/json"
        return super().guess_type(path)

    def log_message(self, *args):
        pass


@contextmanager
def site_local(raiz: Path, prefixo: str = "/NFL-Games/", gz_como_encoding: bool = False) -> Iterator[str]:
    """Serve o conteúdo de `raiz` em http://127.0.0.1:<porta><prefixo>. Devolve a URL sem a barra final."""
    classe = type("Handler", (_Handler,), {"prefixo": prefixo, "gz_como_encoding": gz_como_encoding})
    porta = porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), partial(classe, directory=str(raiz)))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{porta}{prefixo.rstrip('/')}"
    finally:
        srv.shutdown()
        srv.server_close()
