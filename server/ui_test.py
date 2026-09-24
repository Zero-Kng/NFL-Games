"""
Teste de fumaca da UI: renderiza a pagina num Edge/Chrome headless (executando
o JavaScript de verdade) e confere se os dados do dataset chegaram ao DOM.

Uso:  python server/ui_test.py [url]
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> str | None:
    return next((b for b in BROWSERS if Path(b).is_file()), None)


def dump_dom(url: str, browser: str, budget_ms: int = 12000) -> str:
    profile = Path(tempfile.gettempdir()) / "nfl_ui_test_profile"
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--disable-dev-shm-usage", f"--virtual-time-budget={budget_ms}",
        f"--user-data-dir={profile}", "--dump-dom", url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    return res.stdout or ""


def count(dom: str, needle: str) -> int:
    return len(re.findall(re.escape(needle), dom))


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
    browser = find_browser()
    if not browser:
        print("[erro] nenhum Edge/Chrome encontrado para o teste headless")
        return 1
    print(f"navegador: {Path(browser).name}\nurl: {url}\n")

    dom = dump_dom(url, browser)
    if not dom.strip():
        print("[erro] o navegador nao devolveu DOM")
        return 1
    print(f"DOM renderizado: {len(dom):,} bytes\n")

    # (rotulo, trecho esperado, minimo)
    checks = [
        ("chips de semana", 'class="week-chip', 8),
        ("cartoes de partida", 'class="match', 10),
        ("badges de time", 'class="tbadge', 20),
        ("sugestoes taticas", "tip-card", 3),
        ("jogadores a observar", "watch-card", 3),
        ("bastidores", "news-card", 2),
        ("nota do dataset", "Big Data Bowl", 1),
    ]
    bad = [("estado de erro", "state error"), ("API indisponivel", "API indispon"), ("undefined no DOM", ">undefined<")]

    ok = True
    for label, needle, minimum in checks:
        n = count(dom, needle)
        good = n >= minimum
        ok &= good
        print(f"  {'OK ' if good else 'FALHA'} {label:<24} {n:>3} (min {minimum})")
    print()
    for label, needle in bad:
        n = count(dom, needle)
        if n:
            ok = False
        print(f"  {'OK ' if not n else 'FALHA'} sem {label:<21} {n:>3}")

    # Amostra de conteudo real extraido do DOM
    print("\n--- amostras do DOM ---")
    for pat, label in [
        (r'class="tbadge[^"]*"[^>]*>([A-Z]{2,3})<', "times"),
        (r'class="tip-title">.*?</span>([^<]{10,90})<', "titulos taticos"),
        (r'class="watch-name">([^<]+)<', "jogadores"),
        (r'class="news-title">([^<]+)<', "bastidores"),
        (r'class="meta-line">([^<]+)<', "linhas de jogo"),
    ]:
        found = re.findall(pat, dom, re.S)[:5]
        print(f"  {label}: {found}")

    print("\n" + ("TUDO OK" if ok else "HOUVE FALHAS"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
