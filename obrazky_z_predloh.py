# obrazky_z_predloh.py - loga pro Alphacool LCD z barevnych predloh (obrazky/predlohy/)
# Spusteni: py obrazky_z_predloh.py   -> obrazky/<nazev>.png a obrazky/<nazev>_<vyska>.png
#
# <nazev>.png         vetsi verze ve stupnich sedi - pro prvek s velikosti "prizpusobit"
#                     (prvek ji zmensi a prevede na 1 bit podle prahu)
# <nazev>_<vyska>.png hotove 1bitove verze v dane vysce pro velikost "puvodni"
# Bily bod = rozsviceny, cerny = pozadi (obrazek se na displej kresli jako maska).
#
# Barevne obrazky pro Kraken (obrazky/kraken/<nazev>.png, RGBA s pruhlednym pozadim):
#   odznak   = barevne casti a bily text zustanou, sede pozadi a stribrny ramecek zmizi
#   vyrez    = bile pozadi kolem predmetu (vyplnene od rohu) je pruhledne, predmet zustane cely

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "obrazky", "predlohy")
OUT = os.path.join(BASE, "obrazky")

# nazev: (co ma svitit, vysky 1bitovych verzi)
#   tmave  = tmave casti na svetlem pozadi
#   svetle = svetle casti (predloha na tmavem pozadi, nebo tmavy panel s bilym logem)
#   nebile = vse krome bile (barevne i cerne casti, bila = otvor)
#   odznak = svetly text a barevny odznak, bily znak v odznaku = otvor (RYZEN [7])
LOGA = {
    "amd": ("tmave", (12, 16, 24)),
    "amd_ctverec": ("svetle", (48, 64)),
    "ryzen": ("tmave", (10, 14)),
    "ryzen7": ("odznak", (11, 16)),
    "nvidia": ("tmave", (12, 16)),
    "nvidia_nad_sebou": ("nebile", (32, 48)),
    "geforce_rtx_ramecek": ("tmave", (32, 40)),
    "geforce_rtx_nad_sebou": ("tmave", (40, 64)),
    "geforce_rtx_zelene": ("svetle", (20, 32)),
}


# nazev: (predloha, uprava)
KRAKEN = {
    "ryzen7_odznak": ("ryzen7_odznak.png", "odznak"),
    "ryzen_9700x_samolepka": ("ryzen_9700x_samolepka.png", "vyrez"),
    "ryzen_9700x_procesor": ("ryzen_9700x_procesor.png", "vyrez"),
}
KRAKEN_OUT = os.path.join(OUT, "kraken")
KRAKEN_MAX = 720                                      # Kraken kresli ve 3x rozliseni (720x720)


def _stretch(gray, lo, hi):
    """Hodnoty pod lo -> 0, nad hi -> 255, mezi plynule (mekke okraje pro zmensovani)."""
    return gray.point(lambda v: 0 if v <= lo else 255 if v >= hi else round((v - lo) * 255 / (hi - lo)))


def lit_mask(src, mode):
    rgb = src.convert("RGB")
    # orez na obsah: body, ktere se lisi od barvy pozadi v rohu
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > 40 else 0)
    if diff.getbbox():
        rgb = rgb.crop(diff.getbbox())
    r, g, b = rgb.split()
    if mode == "tmave":
        mask = _stretch(ImageChops.invert(rgb.convert("L")), 255 - 170, 255 - 90)
    elif mode == "svetle":                            # nejsilnejsi kanal: bila i syte barvy sviti
        mask = _stretch(ImageChops.lighter(ImageChops.lighter(r, g), b), 90, 170)
    elif mode == "odznak":
        hi = ImageChops.lighter(ImageChops.lighter(r, g), b)
        lo = ImageChops.darker(ImageChops.darker(r, g), b)
        colored = _stretch(ImageChops.subtract(hi, lo), 60, 120)      # syta barva odznaku
        white = _stretch(lo, 90, 170)
        box = colored.point(lambda v: 255 if v >= 128 else 0).getbbox()
        if box:                                       # bila jen vlevo od odznaku (text), v nem je to otvor
            white.paste(0, (box[0], 0, white.width, white.height))
        mask = ImageChops.lighter(colored, white)
    else:                                             # nebile: nejslabsi kanal nizky = neni bila
        mask = _stretch(ImageChops.invert(ImageChops.darker(ImageChops.darker(r, g), b)), 60, 140)
    box = mask.point(lambda v: 255 if v >= 128 else 0).getbbox()
    return mask.crop(box) if box else mask


def color_cutout(src, mode):
    """Barevny obrazek s pruhlednym pozadim (RGBA), oriznuty na obsah."""
    rgb = src.convert("RGB")
    if mode == "odznak":
        # vnitrni sede pole: body blizko barvy pozadi uprostred leveho okraje -> orez uvnitr ramecku
        bg = rgb.getpixel((rgb.width // 25, rgb.height // 4))
        near = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L").point(
            lambda v: 255 if v < 12 else 0)
        box = near.getbbox()
        if box:
            rgb = rgb.crop((box[0] + 4, box[1] + 4, box[2] - 4, box[3] - 4))
        r, g, b = rgb.split()
        hi = ImageChops.lighter(ImageChops.lighter(r, g), b)
        lo = ImageChops.darker(ImageChops.darker(r, g), b)
        colored = _stretch(ImageChops.subtract(hi, lo), 50, 110)        # syta oranzova/cervena
        white = _stretch(lo, 150, 210)                                  # bily text
        alpha = ImageChops.lighter(colored, white)
    else:
        # vyplnit bile pozadi od vsech rohu, predmet (i svetly uvnitr) zustane
        work = rgb.copy()
        key = (255, 0, 255)
        for xy in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1)):
            if work.getpixel(xy) != key:
                ImageDraw.floodfill(work, xy, key, thresh=40)
        r, g, b = work.split()
        bgmask = ImageChops.logical_and(
            ImageChops.logical_and(r.point(lambda v: 255 if v == 255 else 0).convert("1"),
                                   g.point(lambda v: 255 if v == 0 else 0).convert("1")),
            b.point(lambda v: 255 if v == 255 else 0).convert("1"))
        alpha = ImageChops.invert(bgmask.convert("L")).filter(ImageFilter.MinFilter(3))   # bez bileho lemu
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v >= 40 else 0).getbbox()
    if box:
        out = out.crop(box)
    k = min(1.0, KRAKEN_MAX / max(out.size))
    if k < 1.0:
        out = out.resize((round(out.width * k), round(out.height * k)), Image.LANCZOS)
    return out


def fit(mask, height):
    w = max(1, round(mask.width * height / mask.height))
    return mask.resize((w, height), Image.LANCZOS)


def main():
    for name, (mode, heights) in LOGA.items():
        path = os.path.join(SRC, name + ".png")
        if not os.path.exists(path):
            print(f"chybi predloha {path}")
            continue
        mask = lit_mask(Image.open(path), mode)
        big = mask if mask.height <= 128 and mask.width <= 240 else \
            mask.resize((round(mask.width * min(240 / mask.width, 128 / mask.height)),
                         round(mask.height * min(240 / mask.width, 128 / mask.height))), Image.LANCZOS)
        big.save(os.path.join(OUT, name + ".png"))
        for h in heights:
            small = fit(mask, h).point(lambda v: 255 if v >= 128 else 0).convert("1")
            small.save(os.path.join(OUT, f"{name}_{h}.png"))
        print(f"{name}: {big.width}x{big.height}, 1 bit: " +
              ", ".join(f"{round(mask.width * h / mask.height)}x{h}" for h in heights))
    os.makedirs(KRAKEN_OUT, exist_ok=True)
    for name, (src, mode) in KRAKEN.items():
        path = os.path.join(SRC, src)
        if not os.path.exists(path):
            print(f"chybi predloha {path}")
            continue
        out = color_cutout(Image.open(path), mode)
        out.save(os.path.join(KRAKEN_OUT, name + ".png"))
        print(f"kraken/{name}: {out.width}x{out.height}")


if __name__ == "__main__":
    main()
