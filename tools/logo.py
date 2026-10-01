"""
Gera as imagens da logo a partir de rascunho/logo-original.png (a arte enviada
pela equipe: a logo clara sobre fundo azul-marinho texturizado).

    python -m pip install -r requirements-dev.txt   # traz o Pillow (uma vez)
    python tools/logo.py

Saidas:
    app/img/logo.png     a logo sem fundo, recolorida na paleta do app (cabecalho e menu lateral)
    app/img/icone.png    icone quadrado, 64 px (aba do navegador)
    app/img/icone.ico    o mesmo em 16 a 256 px (icone do NFL-Games.exe)
    tools/abertura.png   a logo num cartao de 360 x 240 (a tela de abertura do NFL-Games.exe)

A logo original vai do azul (linhas de velocidade) ao branco (a bola); aqui o
que era azul vira o --blue-soft (#7aa7f2) e o que era branco vira o --text
(#eef2f8) do app/css/app.css, pela saturacao de cada ponto. O fundo sai: o que
e mais escuro que ele vira transparente, o resto ganha opacidade pelo brilho
(as linhas de velocidade, mais apagadas, ficam semitransparentes).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("[erro] precisa do Pillow e do numpy: python -m pip install -r requirements-dev.txt")

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "rascunho" / "logo-original.png"
DESTINO = RAIZ / "app" / "img"

# Paleta do app (app/css/app.css)
AZUL_CLARO = np.array([0x7A, 0xA7, 0xF2])   # --blue-soft
TEXTO = np.array([0xEE, 0xF2, 0xF8])        # --text
SUPERFICIE = (0x0E, 0x17, 0x26, 255)        # --surface: fundo do icone quadrado

# Brilho (maior canal) do fundo texturizado: ate ~90; a logo comeca em ~120.
FUNDO_ATE = 88
OPACO_A_PARTIR = 190
SATURACAO_AZUL = 0.45                         # daqui para cima o ponto e "azul"; perto de 0, "branco"
RECORTE = (33, 168, 425, 430)                 # a logo inteira (bola, linhas, campo e trave), com folga
ALTURA_LOGO = 96                              # 3x os 32 px do cabecalho: nitida em telas densas


def logo_sem_fundo(img: Image.Image) -> Image.Image:
    rgb = np.asarray(img.convert("RGB").crop(RECORTE)).astype(float)
    brilho = rgb.max(axis=2)
    alfa = np.clip((brilho - FUNDO_ATE) / (OPACO_A_PARTIR - FUNDO_ATE), 0, 1)
    saturacao = (brilho - rgb.min(axis=2)) / np.maximum(brilho, 1)
    tom = (1 - np.clip(saturacao / SATURACAO_AZUL, 0, 1))[..., None]     # 0 = azul, 1 = branco
    cor = AZUL_CLARO * (1 - tom) + TEXTO * tom
    rgba = np.dstack([cor, alfa * 255]).round().astype(np.uint8)
    saida = Image.fromarray(rgba, "RGBA")
    return saida.crop(saida.getbbox())        # justa: sem margem transparente


def icone(logo: Image.Image, lado: int) -> Image.Image:
    """A logo centrada num quadrado arredondado da cor de superficie do app."""
    grande = lado * 4                          # desenha grande e reduz: bordas suaves
    fundo = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    ImageDraw.Draw(fundo).rounded_rectangle((0, 0, grande - 1, grande - 1), radius=grande // 5, fill=SUPERFICIE)
    margem = grande * 0.12
    escala = min((grande - 2 * margem) / logo.width, (grande - 2 * margem) / logo.height)
    peca = logo.resize((round(logo.width * escala), round(logo.height * escala)), Image.LANCZOS)
    fundo.alpha_composite(peca, ((grande - peca.width) // 2, (grande - peca.height) // 2))
    return fundo.resize((lado, lado), Image.LANCZOS)


def abertura(logo: Image.Image) -> Image.Image:
    """A tela de abertura do .exe (spec sem-terminal): a logo num cartao da cor de superficie do app."""
    largura, altura, escala = 360, 240, 4      # desenha grande e reduz: bordas suaves
    fundo = Image.new("RGBA", (largura * escala, altura * escala), (0, 0, 0, 0))
    ImageDraw.Draw(fundo).rounded_rectangle((0, 0, largura * escala - 1, altura * escala - 1),
                                            radius=24 * escala, fill=SUPERFICIE)
    alto = 120 * escala
    peca = logo.resize((round(logo.width * alto / logo.height), alto), Image.LANCZOS)
    fundo.alpha_composite(peca, ((fundo.width - peca.width) // 2, (fundo.height - peca.height) // 2))
    return fundo.resize((largura, altura), Image.LANCZOS)


def main() -> int:
    if not ORIGEM.is_file():
        print(f"[erro] nao achei {ORIGEM}")
        return 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    logo = logo_sem_fundo(Image.open(ORIGEM))
    largura = round(logo.width * ALTURA_LOGO / logo.height)
    logo.resize((largura, ALTURA_LOGO), Image.LANCZOS).save(DESTINO / "logo.png", optimize=True)
    icone(logo, 64).save(DESTINO / "icone.png", optimize=True)
    icone(logo, 256).save(DESTINO / "icone.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    abertura(logo).save(RAIZ / "tools" / "abertura.png", optimize=True)
    for arq in [DESTINO / n for n in ("logo.png", "icone.png", "icone.ico")] + [RAIZ / "tools" / "abertura.png"]:
        print(f"{arq.relative_to(RAIZ)}  {Image.open(arq).size}  {arq.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
