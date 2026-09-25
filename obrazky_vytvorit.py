# obrazky_vytvorit.py - pripravene 1bitove obrazky pro Alphacool LCD (slozka obrazky/)
# Spusteni: py obrazky_vytvorit.py
#
#   amd_logo.png, amd_logo_velke.png  napis AMD + sipka (vlastni kresba, ne stazene logo)
#   amd_sipka.png                     samotna sipka
#   ryzen7.png                        RYZEN 7 (Arial Black, zkosene)
#   9700x.png, 9700x_blok.png          9700X, blok = tmave pismo ve svetlem zkosenem pruhu
#
# Kresli se primo v cilove velikosti bez vyhlazovani, aby obrazky byly na displeji ostre.
# Bily bod = rozsviceny, pruhledne = cerne pozadi (PNG s alfa kanalem).

import os

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "obrazky")
WINFONTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts")

# sipka AMD v souradnicich 0-100: velky lomeny uhel + mensi ctverec se seriznutym rohem
ARROW = [[(0, 0), (100, 0), (100, 100), (72, 72), (72, 28), (28, 28)],
         [(0, 100), (0, 42), (28, 42), (58, 72), (58, 100)]]
# pismena AMD (vyska 100): tucne geometricke tvary; vnitrni otvory se kresli cerne
LETTERS = {
    "A": (100, [(0, 100), (36, 0), (64, 0), (100, 100), (72, 100), (65, 80), (35, 80), (28, 100)],
          [(42, 58), (58, 58), (50, 34)]),
    "M": (104, [(0, 100), (0, 0), (27, 0), (52, 38), (77, 0), (104, 0), (104, 100), (78, 100), (78, 46),
                (58, 76), (46, 76), (26, 46), (26, 100)], None),
    "D": (94, [(0, 0), (60, 0), (94, 28), (94, 72), (60, 100), (0, 100)],
          [(26, 24), (52, 24), (68, 38), (68, 62), (52, 76), (26, 76)]),
}


def _poly(d, pts, ox, oy, k, fill):
    d.polygon([(round(ox + x * k), round(oy + y * k)) for x, y in pts], fill=fill)


def amd_logo(height, gap_arrow=None, arrow=True):
    k = (height - 1) / 100
    widths = [LETTERS[c][0] for c in "AMD"]
    sp = 16
    text_w = round((sum(widths) + sp * 2) * k) + 1
    gap = gap_arrow if gap_arrow is not None else max(3, round(height * 0.35))
    w = text_w + (gap + height if arrow else 0)
    img = Image.new("1", (w, height), 0)
    d = ImageDraw.Draw(img)
    x = 0.0
    for c in "AMD":
        lw, outer, inner = LETTERS[c]
        _poly(d, outer, x, 0, k, 1)
        if inner:
            _poly(d, inner, x, 0, k, 0)
        x += (lw + sp) * k
    if arrow:
        for poly in ARROW:
            _poly(d, poly, text_w + gap, 0, k, 1)
    return img


def arrow_only(size):
    img = Image.new("1", (size, size), 0)
    d = ImageDraw.Draw(img)
    for poly in ARROW:
        _poly(d, poly, 0, 0, (size - 1) / 100, 1)
    return img


def shear(img, k=0.22):
    """zkoseni doprava (jako italika), zustane ostre"""
    w, h = img.size
    extra = int(h * k) + 1
    return img.transform((w + extra, h), Image.AFFINE, (1, k, -extra, 0, 1, 0), Image.NEAREST, fillcolor=0)


def text_img(text, px, font="ariblk.ttf"):
    f = ImageFont.truetype(os.path.join(WINFONTS, font), px)
    bb = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), text, font=f, anchor="lt")
    img = Image.new("1", (bb[2] - bb[0], bb[3] - bb[1]), 0)
    ImageDraw.Draw(img).text((-bb[0], -bb[1]), text, font=f, fill=1, anchor="lt")
    return shear(img)


def block(img, pad=3):
    """tmave pismo ve svetlem zkosenem pruhu (negativ)"""
    w, h = img.size
    sk = int((h + 2 * pad) * 0.22) + 1
    out = Image.new("1", (w + 2 * pad + sk, h + 2 * pad), 0)
    d = ImageDraw.Draw(out)
    H = h + 2 * pad - 1
    d.polygon([(sk, 0), (out.width - 1, 0), (out.width - 1 - sk, H), (0, H)], fill=1)
    out.paste(0, (pad + sk // 2, pad), img)
    return out


def save(img, name):
    """1 bit -> PNG s pruhlednosti (zhasnute body pruhledne)"""
    rgba = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rgba.paste((255, 255, 255, 255), (0, 0), img.convert("L"))
    rgba.save(os.path.join(OUT, name))
    print(f"{name:22s} {img.width}x{img.height}")


def main():
    os.makedirs(OUT, exist_ok=True)
    save(amd_logo(16), "amd_logo.png")
    save(amd_logo(24), "amd_logo_velke.png")
    save(arrow_only(16), "amd_sipka.png")
    save(text_img("RYZEN 7", 20), "ryzen7.png")
    nine = text_img("9700X", 16)
    save(nine, "9700x.png")
    save(block(nine), "9700x_blok.png")


if __name__ == "__main__":
    main()
