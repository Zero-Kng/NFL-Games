"""
Teste de fumaca das 4 telas: abre cada persona num navegador headless (rodando
o JavaScript de verdade) e confere se os dados reais chegaram ao DOM.

Uso:  python server/ui_test_all.py
"""

from __future__ import annotations

import re
import sys

from ui_test import count, dump_dom, find_browser

BASE = "http://127.0.0.1:8000/"
GAME = "2021092300"  # CAR @ HOU, semana 3

# tela -> (url, [(rotulo, trecho, minimo)], [amostras (regex, rotulo)])
SCREENS = {
    "HOME": (
        f"?week=3&game={GAME}",
        [("cartoes de partida", 'class="match', 10), ("taticas", "tip-card", 3),
         ("bastidores", "news-card", 2)],
        [(r'class="tip-title">.*?</span>([^<]{10,80})<', "leitura tatica")],
    ),
    "TREINADOR": (
        f"?week=3&game={GAME}&screen=coach",
        [("campo", 'id="field"', 1), ("jogadores no campo", "player-dot", 22),
         ("marcacoes do campo", "<line", 8), ("controles", 'id="frameRange"', 1),
         ("seletor de jogada", 'id="playPick"', 1)],
        [(r'<option value="\d+"[^>]*>([^<]+)</option>', "jogadas"),
         (r'class="num">(\d+)</span>', "camisas")],
    ),
    "OLHEIRO": (
        "?screen=scout",
        [("lista de jogadores", 'class="p-row"', 20), ("ratings", 'class="rate', 20),
         ("filtros", 'data-pos=', 9)],
        [(r'class="nm"><b>([^<]+)</b><span>([^<]{5,60})<', "jogadores")],
    ),
    "COMENTARISTA": (
        f"?week=3&game={GAME}&screen=commentator",
        # O replay comeca na 1a jogada, entao ha 1 narracao no primeiro render.
        [("placar", "live-score", 1), ("narracao", "tl-item", 1),
         ("controle de replay", 'id="bcRange"', 1), ("painel", 'id="bcPanel"', 1),
         ("barras do painel", 'class="cmp"', 5)],
        [(r'class="ev"><b>([^<]+)</b>', "narracoes")],
    ),
}

BAD = [("estado de erro", "state error"), ("API indisponivel", "API indispon"),
       ("undefined", ">undefined<"), ("NaN", ">NaN<")]


def main() -> int:
    browser = find_browser()
    if not browser:
        print("[erro] Edge/Chrome nao encontrado")
        return 1

    all_ok = True
    for name, (query, checks, samples) in SCREENS.items():
        dom = dump_dom(BASE + query, browser)
        print(f"\n{'=' * 58}\n{name}  ({query})\n{'=' * 58}")
        if not dom.strip():
            print("  FALHA: sem DOM")
            all_ok = False
            continue
        print(f"  DOM: {len(dom):,} bytes")
        for label, needle, minimum in checks:
            n = count(dom, needle)
            good = n >= minimum
            all_ok &= good
            print(f"  {'OK   ' if good else 'FALHA'} {label:<22} {n:>4} (min {minimum})")
        for label, needle in BAD:
            n = count(dom, needle)
            if n:
                all_ok = False
                print(f"  FALHA apareceu {label}: {n}x")
        for pat, label in samples:
            found = re.findall(pat, dom, re.S)[:4]
            print(f"    {label}: {found}")

    print("\n" + ("=" * 58) + "\n" + ("TODAS AS TELAS OK" if all_ok else "HOUVE FALHAS"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
