# screens.py - vykresleni obrazovek pro displej NZXT Kraken 2023 (240x240)
# Kresli se ve 3x vetsim rozliseni, obsah se orizne a roztahne na displej.
#
# Typy obrazovek (config.json -> "obrazovky"):
#   "dva_bary"  - dve hodnoty s vodorovnymi bary (napr. teplota CPU a GPU)
#   "oblouk"    - jedna hodnota s barevnym obloukem
#   "budik"     - jedna hodnota jako rucickovy budik (tachometr)
#   "dva_kruhy" - dve hodnoty jako soustredne kruhy
#   "graf"      - prubeh jedne hodnoty v case
#   "hodiny"    - hodiny ve 24h formatu
#   "dva_oblouky"   - dve hodnoty jako oblouky vlevo a vpravo, cisla uprostred
#   "segmenty"      - jedna hodnota jako prstenec ze segmentu
#   "ctyri_hodnoty" - ctyri hodnoty v ctvrtinach kruhu, kazda se svym obloukem
#   "chlazeni"      - kapalina, pumpa a ventilatory Krakenu
#   "graf_dva"      - prubeh dvou hodnot v case
#   "hodiny_analog" - rucickove hodiny (datum volitelne)
#   "hodiny_datum"  - digitalni hodiny se sekundovym prstencem, cas na radku (datum volitelne)
#   "hodiny_pod_sebou" - totez, hodiny nad minutami
#   "obrazek"       - obrazek / logo ze slozky obrazky/
# Ctvercove (navrhy z Claude Design, vyuzivaji cely displej):
#   "dlazdice" (ctyri dlazdice), "cpu_detail", "chlazeni_radky", "hodiny_stav", "graf_plny",
#   "sit_disky", "gpu_sloupce", "velke_cislo", "hladina" (kruhova), "graf_dokola" (kruhovy)
# Volne rozvrzeni: "volne" - prvky s polohou a velikosti v scr["prvky"] (kraken_prvky.py, editor_kraken.py)
#
# Barvy: kazda barevna cast ma dve barvy <cast>_od a <cast>_do (prechod).
# Stejne barvy = jednobarevne. Prechod se pocita pres odstin (HSV),
# takze zelena -> cervena jde pres zlutou, ne pres hnedou.

import colorsys
import json
import math
import os
from datetime import datetime
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

SIZE = 240
S = 3                      # supersampling
W = SIZE * S
BASE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(BASE, "fonts")
IMAGES = os.path.join(BASE, "obrazky")

WHITE = (255, 255, 255)
GREY = (150, 150, 150)
DARK = (95, 95, 95)
BLACK = (0, 0, 0)
DEGREE_UNITS = ("°", "°C", "°F")

TYPES = {"dva_bary": "Dva bary", "oblouk": "Oblouk (1 hodnota)", "budik": "Budík (1 hodnota)",
         "dva_kruhy": "Dva kruhy", "graf": "Graf v čase", "hodiny": "Hodiny",
         "dva_oblouky": "Dva oblouky (vlevo a vpravo)", "segmenty": "Segmentový prstenec (1 hodnota)",
         "ctyri_hodnoty": "Čtyři hodnoty", "chlazeni": "Chlazení (kapalina, pumpa, ventilátory)",
         "graf_dva": "Graf dvou hodnot", "hodiny_analog": "Ručičkové hodiny",
         "hodiny_datum": "Digitální hodiny s prstencem", "hodiny_pod_sebou": "Digitální hodiny s prstencem – pod sebou",
         "obrazek": "Obrázek / logo",
         "dlazdice": "Čtyři dlaždice", "cpu_detail": "CPU detail (hodnota, 3 údaje, graf)",
         "chlazeni_radky": "Chlazení – řádky", "hodiny_stav": "Hodiny a stav",
         "graf_plny": "Graf přes celou plochu", "sit_disky": "Síť a disky", "gpu_sloupce": "GPU sloupce",
         "velke_cislo": "Jedno velké číslo", "hladina": "Hladina (kruhová)", "graf_dokola": "Graf dokola (kruhový)",
         "volne": "Volné rozvržení (editor)"}

# barevne casti kazdeho typu: (klic, popisek, vychozi_od, vychozi_do)
_TEXT = ("text", "Text (čísla a popisky)", "#ffffff", "#ffffff")
COLORS = {
    "dva_bary": [("bar1", "Horní bar", "#3cff3c", "#3cff3c"),
                 ("bar2", "Dolní bar", "#3264ff", "#3264ff"), _TEXT],
    "oblouk": [("oblouk", "Oblouk", "#3cdc28", "#ff1414"), _TEXT],
    "budik": [("oblouk", "Stupnice", "#3cdc28", "#ff1414"),
              ("rucicka", "Ručička", "#ffffff", "#ffffff"), _TEXT],
    "dva_kruhy": [("kruh1", "Vnější kruh", "#3cff3c", "#b4f014"),
                  ("kruh2", "Vnitřní kruh", "#3264ff", "#28c8ff"), _TEXT],
    "graf": [("graf", "Graf", "#3cdc28", "#ff1414"), _TEXT],
    "hodiny": [("hodiny", "Hodiny", "#3ce628", "#f0f014"),
               ("minuty", "Minuty", "#ffa014", "#ff1e14")],
    "dva_oblouky": [("oblouk1", "Levý oblouk", "#3cff3c", "#b4f014"),
                    ("oblouk2", "Pravý oblouk", "#3264ff", "#28c8ff"), _TEXT],
    "segmenty": [("segmenty", "Segmenty", "#28c8ff", "#ff28c8"), _TEXT],
    "ctyri_hodnoty": [("oblouky", "Oblouky", "#3cdc28", "#ff1414"), _TEXT],
    "chlazeni": [("kapalina", "Teplota kapaliny", "#28c8ff", "#28c8ff"),
                 ("pumpa", "Oblouk pumpy (vlevo)", "#3264ff", "#28c8ff"),
                 ("ventilatory", "Oblouk ventilátorů (vpravo)", "#3cff3c", "#b4f014"), _TEXT],
    "graf_dva": [("graf1", "Graf 1", "#3cff3c", "#3cff3c"), ("graf2", "Graf 2", "#3c8cff", "#3c8cff"), _TEXT],
    "hodiny_analog": [("cifernik", "Ciferník", "#ffffff", "#ffffff"), ("rucicky", "Ručičky", "#ffffff", "#ffffff"),
                      ("sekundy", "Sekundová ručička", "#ff3c28", "#ff3c28"), ("datum", "Datum", "#28c8ff", "#28c8ff")],
    "hodiny_datum": [("hodiny", "Čas", "#ffffff", "#ffffff"), ("sekundy", "Sekundový prstenec", "#28c8ff", "#ff28c8"),
                     ("datum", "Datum", "#b4b4b4", "#b4b4b4")],
    "hodiny_pod_sebou": [("hodiny", "Hodiny", "#ffffff", "#ffffff"), ("minuty", "Minuty", "#28c8ff", "#28c8ff"),
                         ("sekundy", "Sekundový prstenec", "#28c8ff", "#ff28c8"), ("datum", "Datum", "#b4b4b4", "#b4b4b4")],
    "obrazek": [("tvar", "Barva tvaru (úprava „jen tvar“)", "#ffffff", "#ffffff")],
    "dlazdice": [("dlazdice1", "Dlaždice 1 (popisek a bar)", "#3cff3c", "#ff3b3b"),
                 ("dlazdice2", "Dlaždice 2", "#3b82f6", "#a855f7"),
                 ("dlazdice3", "Dlaždice 3", "#a855f7", "#ec4899"),
                 ("dlazdice4", "Dlaždice 4", "#22d3ee", "#3b82f6"), _TEXT],
    "cpu_detail": [("akcent", "Nadpis a graf", "#ffb020", "#ff3b3b"), _TEXT],
    "chlazeni_radky": [("kapalina", "Kapalina (stupnice)", "#22d3ee", "#ff9f1c"),
                       ("pumpa", "Pumpa", "#22d3ee", "#3b82f6"),
                       ("ventilatory", "Ventilátory", "#ffb020", "#ff6b35"), _TEXT],
    "hodiny_stav": [("hodiny", "Čas a sekundový pruh", "#3cff3c", "#22d3ee"),
                    ("stav1", "Údaj 1 (popisek)", "#ffb020", "#ffb020"),
                    ("stav2", "Údaj 2 (popisek)", "#7aa8ff", "#7aa8ff"),
                    ("stav3", "Údaj 3 (popisek)", "#22d3ee", "#22d3ee"), _TEXT],
    "graf_plny": [("graf", "Graf (dole → nahoře)", "#3cff3c", "#ffb020"), _TEXT],
    "sit_disky": [("sit", "Síť (stahování → odesílání)", "#3cff3c", "#22d3ee"),
                  ("disky", "Disky", "#a855f7", "#ec4899"), _TEXT],
    "gpu_sloupce": [("nadpis", "Nadpis", "#7aa8ff", "#7aa8ff"), ("sloupce", "Sloupce (dole → nahoře)", "#3b82f6", "#a855f7"),
                    _TEXT],
    "velke_cislo": [("segmenty", "Nadpis a segmenty", "#3cff3c", "#ff3b3b"), _TEXT],
    "hladina": [("voda", "Hladina (nahoře → dole)", "#22d3ee", "#1d4ed8"), _TEXT],
    "graf_dokola": [("paprsky", "Paprsky (nízká → vysoká)", "#a855f7", "#ff3b8a"), _TEXT],
}
DAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]
MONTHS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
          "října", "listopadu", "prosince"]
IMAGE_MODES = ["beze změny", "odstranit pozadí", "jen tvar", "odstranit pozadí, černou na bílou"]

_font_cache = {}
_TS = 1.0                  # meritko textu dane obrazovky
_TCHAR = None              # cislice pro sablonu orezu (None = nejsirsi)


# ------------------------------------------------------------------ pisma

def _font(weight, px):
    px = max(6, round(px * _TS))
    k = (weight, px)
    if k not in _font_cache:
        path = os.path.join(FONTS, f"Montserrat-{weight}.ttf")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Chybi pismo {path}")
        _font_cache[k] = ImageFont.truetype(path, px * S)
    return _font_cache[k]


def _raw_font(weight, px):
    """Pismo bez meritka textu (pro hodiny)."""
    global _TS
    old, _TS = _TS, 1.0
    try:
        return _font(weight, px)
    finally:
        _TS = old


def _fit_font(d, text, weight, px, max_w):
    while px > 8 and d.textlength(text, font=_font(weight, px)) > max_w:
        px -= 1
    return _font(weight, px)


def _canvas():
    return Image.new("RGB", (W, W), BLACK)


# ------------------------------------------------------------------ barvy

def hex_rgb(value, default=(255, 255, 255)):
    try:
        v = str(value).lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return default


def mix(c1, c2, t):
    """Prechod dvou barev pres odstin (HSV)."""
    t = max(0.0, min(1.0, t))
    if c1 == c2:
        return c1
    h1, s1, v1 = colorsys.rgb_to_hsv(*(x / 255 for x in c1))
    h2, s2, v2 = colorsys.rgb_to_hsv(*(x / 255 for x in c2))
    if s1 < 0.05:                      # seda/bila nema odstin -> prevzit
        h1 = h2
    if s2 < 0.05:
        h2 = h1
    dh = h2 - h1
    if dh > 0.5:
        dh -= 1
    elif dh < -0.5:
        dh += 1
    h = (h1 + dh * t) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s1 + (s2 - s1) * t, v1 + (v2 - v1) * t)
    return (round(r * 255), round(g * 255), round(b * 255))


def colors(scr, part):
    """(barva_od, barva_do) dane casti obrazovky."""
    for k, _l, d_od, d_do in COLORS.get(scr.get("typ"), []):
        if k == part:
            return hex_rgb(scr.get(f"{k}_od", d_od)), hex_rgb(scr.get(f"{k}_do", d_do))
    return WHITE, WHITE


def _dim(c, k):
    return tuple(int(v * k) for v in c)


def _hgrad(w, h, c1, c2):
    """Vodorovny prechod jako obrazek."""
    img = Image.new("RGB", (max(1, w), max(1, h)))
    d = ImageDraw.Draw(img)
    for x in range(max(1, w)):
        d.line((x, 0, x, h), fill=mix(c1, c2, x / max(1, w - 1)))
    return img


def _vgrad(w, h, c_bottom, c_top):
    img = Image.new("RGB", (max(1, w), max(1, h)))
    d = ImageDraw.Draw(img)
    for y in range(max(1, h)):
        d.line((0, y, w, y), fill=mix(c_bottom, c_top, 1 - y / max(1, h - 1)))
    return img


def _paint(img, mask, fill_img, xy=(0, 0)):
    layer = Image.new("RGB", img.size, BLACK)
    layer.paste(fill_img, xy)
    img.paste(layer, (0, 0), mask)


def _text(img, xy, text, font, cols, anchor="la"):
    """Text jednobarevny nebo s diagonalnim prechodem."""
    c1, c2 = cols
    if text == MISSING:
        c1 = c2 = GREY
    d = ImageDraw.Draw(img)
    if PLASTIC and text:
        _extrude(d, xy, text, font, c1, anchor)
    if c1 == c2:
        d.text(xy, text, font=font, fill=c1, anchor=anchor)
        return
    x0, y0, x1, y1 = (int(v) for v in d.textbbox(xy, text, font=font, anchor=anchor))
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=font, fill=255, anchor=anchor)
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for i in range(w + h):
        gd.line((i, 0, i - h, h), fill=mix(c1, c2, i / (w + h)))
    _paint(img, mask, grad, (x0, y0))


def _textlen(img, text, font):
    return ImageDraw.Draw(img).textlength(text, font=font)


# ------------------------------------------------------------------ hodnoty

def _frac(value, lo, hi):
    if value is None or hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


MISSING = "–"                # chybejici hodnota (senzor nedostupny)


def _fmt(value, decimals):
    return MISSING if value is None else f"{value:.{int(decimals)}f}"


def value_for(sensor, data, divisor=1):
    item = data.get(sensor) if sensor else None
    if item is None:
        return None
    try:
        return item["value"] / (float(divisor) or 1)
    except (TypeError, ZeroDivisionError):
        return None


def unit_for(scr, sensor, data):
    u = scr.get("jednotka", "auto")
    if u == "auto":
        u = (data.get(sensor) or {}).get("unit", "")
    return u


def widest_digit(font):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    return max("0123456789", key=lambda ch: d.textlength(ch, font=font))


def template_text(lo, hi, decimals, font):
    """Text pro vypocet orezu: nejdelsi mozne cislo z cislic _TCHAR (nebo nejsirsich)."""
    digits = len(str(int(max(abs(lo), abs(hi))))) or 1
    ch = _TCHAR or widest_digit(font)
    txt = ch * digits
    if int(decimals) > 0:
        txt += "." + ch * int(decimals)
    return txt


def _value_text(scr, n, data, font, template):
    """Hodnota n-teho senzoru ("" / "1" / "2") -> (text, podil 0..1, cislo)."""
    lo, hi = float(scr.get("min" + n, 0)), float(scr.get("max" + n, 100))
    if template:
        return template_text(lo, hi, scr.get("desetinna_mista", 0), font), 1.0, hi
    v = value_for(scr.get("senzor" + n), data, scr.get("delitel", 1))
    return _fmt(v, scr.get("desetinna_mista", 0)), _frac(v, lo, hi), v


# ------------------------------------------------------------------ prvky

def _bar(img, x, y, w, h, frac, cols):
    if PLASTIC:                                      # drazka kolem baru, vypln v puvodni velikosti
        g = _bar_rim(h)
        return _bar3d(img, (x - g, y - g, x + w + g, y + h + g), h // 2 + g, frac, cols, inset=g)
    d = ImageDraw.Draw(img)
    r = h // 2
    d.rounded_rectangle((x, y, x + w, y + h), r, fill=GREY)
    if frac > 0:
        fw = max(h, int(w * frac))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((x, y, x + fw, y + h), r, fill=255)
        _paint(img, mask, _hgrad(w, h + 1, *cols), (x, y))   # prechod pres celou delku baru


def _arc(img, c, r, thick, start, span, frac, cols, track=DARK, dim_rest=None):
    """Oblouk: podklad + barevna cast s prechodem podel oblouku. Podklad i barevna cast
    maji zakulacene konce."""
    if PLASTIC:
        return arc3d(img, c, c, r, thick, start, span, frac, cols, dim=dim_rest)
    d = ImageDraw.Draw(img)
    box = (c - r, c - r, c + r, c + r)
    rr = r - thick / 2

    def cap(ang, col):
        a = math.radians(ang)
        cx, cy = c + rr * math.cos(a), c + rr * math.sin(a)
        d.ellipse((cx - thick / 2, cy - thick / 2, cx + thick / 2, cy + thick / 2), fill=col)

    if dim_rest is None:
        d.arc(box, start, start + span, fill=track, width=thick)
        cap(start, track)
        cap(start + span, track)
    else:                                   # cela stupnice ztlumene v barvach prechodu
        for i in range(int(span)):
            d.arc(box, start + i, start + i + 2, fill=_dim(mix(*cols, i / span), dim_rest), width=thick)
        cap(start, _dim(cols[0], dim_rest))
        cap(start + span, _dim(cols[1], dim_rest))
    steps = int(span * frac)
    if steps <= 0:
        return
    for i in range(steps):
        d.arc(box, start + i, start + i + 2, fill=mix(*cols, i / span), width=thick)
    cap(start, cols[0])
    cap(start + steps, mix(*cols, steps / span))


def _unit_after(img, x_left, y_top, txt, font, unit, tcols, deg_px=26, unit_px=18, deg_dy=2):
    """Jednotka za cislem vykreslenym s anchor lt na (x_left, y_top)."""
    d = ImageDraw.Draw(img)
    tw = d.textlength(txt, font=font)
    if unit in DEGREE_UNITS:
        _text(img, (x_left + tw + 3 * S, y_top + deg_dy * S), "°", _font("ExtraBold", deg_px), tcols, "lt")
    elif unit:
        bottom = d.textbbox((x_left, y_top), txt, font=font, anchor="lt")[3]
        _text(img, (x_left + tw + 3 * S, bottom), unit, _font("ExtraBold", unit_px), tcols, "ld")


# ------------------------------------------------------- plasticky (3D) vzhled
# Navrh: Claude Design, stranka "Kraken – plastické (3D)". Svetlo shora zleva:
#   podklady baru a oblouku = zapustene drazky (tmave nahore, svetly spodni okraj),
#   vypln baru a segmentu = lesk nahore, stin dole, mekka zare v barve,
#   oblouky a prstence = trubky (stin na vnejsi strane, lesk a odlesk na vnitrni),
#   panely = vystouple (svetla horni hrana, tmava spodni), velka cisla = vytlacena do hloubky.
# Stinovani se pocita pres masky tvaru (Pillow), takze plati pro libovolny tvar a barvu.
PLASTIC = True              # render() prepina podle config["plasticky_vzhled"]
GLOW = False                # zare kolem barevnych tvaru (config["plasticka_zare"]); na LCD je obrys
                            # tvaru rozmazany a obrazce pusobi mensi, proto vychozi vypnuto
GROOVE = (10, 12, 15)       # dno drazky oblouku
_c3d = {}


def _cached(key, make):
    if key not in _c3d:
        if len(_c3d) > 96:
            _c3d.clear()
        _c3d[key] = make()
    return _c3d[key]


def _lerp(c1, c2, t):
    """Linearni prechod RGB (pro odstiny jedne barvy, bez otaceni odstinu)."""
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def _interp(stops, t):
    """Hodnota v bode t podle [(t, hodnota)] (hodnota cislo nebo barva)."""
    for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
        if t <= t1:
            k = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            if isinstance(a0, tuple):
                return _lerp(a0, a1, k)
            return a0 + (a1 - a0) * max(0.0, k)
    return stops[-1][1]


def _strip(n, stops, vertical, alpha):
    """Pruh 1 x n (svisle) nebo n x 1: alfa 0..255 (alpha=True) nebo barvy podle stops."""
    n = max(1, int(n))
    key = ("strip", n, tuple(stops), vertical, alpha)

    def make():
        vals = [_interp(stops, i / max(1, n - 1)) for i in range(n)]
        im = Image.new("L" if alpha else "RGB", (1, n) if vertical else (n, 1))
        im.putdata([int(255 * v) for v in vals] if alpha else vals)
        return im
    return _cached(key, make)


def _grad(w, h, stops, vertical=True):
    """Obrazek w x h s prechodem barev podle [(t, barva)] (shora dolu / zleva doprava)."""
    w, h = max(1, int(w)), max(1, int(h))
    return _strip(h if vertical else w, stops, vertical, False).resize((w, h), Image.BILINEAR)


def _moved(mask, dx, dy):
    out = Image.new("L", mask.size, 0)
    out.paste(mask, (int(round(dx)), int(round(dy))))
    return out


def _tint(img, mask, color, alpha=1.0):
    """Primichat barvu pres masku se silou alpha (0..1)."""
    if alpha <= 0:
        return
    bb = mask.getbbox()                                  # jen v oblasti tvaru (rychlejsi)
    if not bb:
        return
    mask = mask.crop(bb)
    if alpha < 1:
        mask = mask.point(lambda v, a=alpha: int(v * a))
    img.paste(color, bb, mask)


def _edges(img, mask, k, top=0.14, bottom=0.8):
    """Vystouply tvar: svetla horni hrana a tmava spodni (k = sila hrany v bodech platna)."""
    if top:
        _tint(img, ImageChops.subtract(mask, _moved(mask, 0, k)), WHITE, top)
    if bottom:
        _tint(img, ImageChops.subtract(mask, _moved(mask, 0, -k)), BLACK, bottom)


# stinovani pres vysku tvaru (bar) a pres sirku (valec): (lesk, stin) jako [(t, sila)]
GLOSS = ([(0, 0.6), (0.32, 0.16), (0.52, 0), (1, 0)], [(0, 0), (0.52, 0), (1, 0.5)])
CYLINDER = ([(0, 0), (0.2, 0), (0.34, 0.42), (0.46, 0.08), (0.62, 0), (1, 0)],
            [(0, 0.55), (0.2, 0), (0.7, 0), (1, 0.6)])
# trubka a drazka pres tloustku oblouku: t = 0 vnejsi okraj .. 1 vnitrni okraj
TUBE = ([(0, 0), (0.5, 0), (0.64, 0.38), (0.72, 0.75), (0.8, 0.32), (0.92, 0), (1, 0)],
        [(0, 0.42), (0.22, 0), (1, 0)])               # stin jen u samotneho okraje, at trubka nevypada uzsi
GROOVE_SHADE = ([(0, 0), (0.86, 0), (0.92, 0.11), (1, 0.11)], [(0, 0.6), (0.14, 0.3), (0.22, 0), (1, 0)])


def _gloss(img, mask, box, across=False, shade=GLOSS):
    """Plasticke stinovani tvaru v masce v ramci box: svisle (bar), across=True vodorovne (valec)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    m = mask.crop((x0, y0, x0 + w, y0 + h))
    for stops, col in zip(shade, (WHITE, BLACK)):
        r = _strip(w if across else h, stops, not across, True).resize((w, h))
        img.paste(col, (x0, y0, x0 + w, y0 + h), ImageChops.multiply(m, r))


def _ring_shade(img, mask, cx, cy, r, thick, shade=TUBE):
    """Stinovani mezikruzi r - thick .. r (trubka nebo drazka) v masce oblouku."""
    for n, (stops, col) in enumerate(zip(shade, (WHITE, BLACK))):
        key = ("ring", img.size, round(cx), round(cy), round(r), round(thick), tuple(stops))

        def make(stops=stops):
            im = Image.new("L", img.size, 0)
            d = ImageDraw.Draw(im)
            steps = max(2, int(thick))
            for i in range(steps + 1):
                rr = r - thick * i / steps
                v = int(255 * _interp(stops, i / steps))
                if v > 0:
                    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=v, width=max(2, int(thick / steps) + 2))
            return im
        _tint(img, ImageChops.multiply(mask, _cached(key, make)), col)


def _glow(img, layer, mask, radius, alpha=0.45, force=False):
    """Mekka zare barevneho tvaru (layer = tvar na cernem, mask = tvar); kreslit pred tvarem.
    force = i pri vypnute zari (rozsvicena kontrolka)."""
    if not (GLOW or force):
        return
    bb = mask.getbbox()
    if not bb or radius <= 0 or alpha <= 0:
        return
    pad = int(radius * 2.5)
    box = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))
    w, h = box[2] - box[0], box[3] - box[1]
    src = Image.composite(layer.crop(box), Image.new("RGB", (w, h), BLACK), mask.crop(box))
    k = 4                                                  # rozmazani ve ctvrtinovem rozliseni (rychle)
    small = src.resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
    big = small.filter(ImageFilter.GaussianBlur(radius / k)).resize((w, h), Image.BILINEAR)
    big = big.point(lambda v, a=alpha: int(v * a))
    img.paste(ImageChops.screen(img.crop(box), big), box[:2])


def _shape(img, layer, mask, box=None, glow=True, shade=GLOSS, across=False, glow_r=None):
    """Barevny tvar (layer pres mask) se zari a plastickym stinovanim."""
    bb = box or mask.getbbox()
    if not bb:
        return
    if glow:
        _glow(img, layer, mask, glow_r or max(3 * S, min(bb[2] - bb[0], bb[3] - bb[1]) * 0.45))
    img.paste(layer, (0, 0), mask)
    if shade:
        _gloss(img, mask, bb, across, shade)


def _groove_rect(img, box, r, base=None):
    """Zapustena drazka (podklad baru): tmave nahore, svetly spodni okraj, vnitrni stin."""
    x0, y0, x1, y1 = (int(v) for v in box)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, fill=255)
    b = base or (28, 32, 38)
    _paint(img, mask, _grad(x1 - x0, y1 - y0, [(0, _dim(b, 0.08)), (0.6, _dim(b, 0.38)), (1, b)]), (x0, y0))
    k = max(S, (y1 - y0) * 0.12)
    _tint(img, ImageChops.subtract(mask, _moved(mask, 0, k)), BLACK, 0.85)
    _tint(img, ImageChops.subtract(mask, _moved(mask, 0, 2 * k)), BLACK, 0.4)
    _tint(img, ImageChops.subtract(mask, _moved(mask, 0, -max(S, k * 0.6))), WHITE, 0.09)
    return mask


def _bar3d(img, box, r, frac, cols, vertical=False, base=None, inset=True):
    """Bar: zapustena drazka a v ni vypoukla vypln s prechodem (souradnice platna)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    _groove_rect(img, box, r, base)
    if frac <= 0:
        return
    if inset is True:
        ins = max(S, round(min(x1 - x0, y1 - y0) * 0.1))
    else:
        ins = int(inset or 0)                       # cislo = presna sirka okraje drazky
    fx0, fy0, fx1, fy1 = x0 + ins, y0 + ins, x1 - ins, y1 - ins
    rr = max(0, r - ins)
    if vertical:
        fy0 = fy1 - max(2 * rr or 1, int((fy1 - fy0) * frac))
        fill = _vgrad(x1 - x0, y1 - y0, cols[0], cols[1])
    else:
        fx1 = fx0 + max(2 * rr or 1, int((fx1 - fx0) * frac))
        fill = _hgrad(x1 - x0, y1 - y0, *cols)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((fx0, fy0, fx1 - 1, fy1 - 1), rr, fill=255)
    layer = Image.new("RGB", img.size, BLACK)
    layer.paste(fill, (x0, y0))
    _shape(img, layer, mask, (fx0, fy0, fx1, fy1), across=vertical, shade=CYLINDER if vertical else GLOSS)


def _bar_rim(h):
    """Sirka okraje drazky kolem baru vysokeho h (body platna)."""
    return max(S, round(h * 0.18))


def _raised(img, box, r, base=(14, 16, 19)):
    """Vystouply panel: prechod svetlejsi nahore -> tmavsi dole, svetla horni a tmava spodni hrana."""
    x0, y0, x1, y1 = (int(v) for v in box)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, fill=255)
    stops = [(0, _lerp(base, WHITE, 0.08)), (0.48, base), (1, _dim(base, 0.5))]
    _paint(img, mask, _grad(x1 - x0, y1 - y0, stops), (x0, y0))
    _edges(img, mask, max(S, 1.5 * S), top=0.14, bottom=0.85)


def _segments3d(img, boxes, cols_lit, radius, off=(13, 15, 18), vertical=False, bar_box=None):
    """Segmenty jako kosticky: rozsvicene vystupuji (lesk, zare), zhasnute jsou zapustene.
    boxes = [(x0, y0, x1, y1, barva nebo None = zhasnuty)]."""
    lit_m, off_m = Image.new("L", img.size, 0), Image.new("L", img.size, 0)
    layer = Image.new("RGB", img.size, BLACK)
    ld, lm, om = ImageDraw.Draw(layer), ImageDraw.Draw(lit_m), ImageDraw.Draw(off_m)
    for x0, y0, x1, y1, col in boxes:
        if col is None:
            om.rounded_rectangle((x0, y0, x1, y1), radius, fill=255)
        else:
            lm.rounded_rectangle((x0, y0, x1, y1), radius, fill=255)
            ld.rounded_rectangle((x0, y0, x1, y1), radius, fill=col)
    if off_m.getbbox():
        _tint(img, off_m, off)
        k = max(S, min(b[3] - b[1] for b in boxes) * 0.1)
        _tint(img, ImageChops.subtract(off_m, _moved(off_m, 0, k)), BLACK, 0.85)
        _tint(img, ImageChops.subtract(off_m, _moved(off_m, 0, -max(1, k * 0.5))), WHITE, 0.06)
    if lit_m.getbbox():
        bb = bar_box or lit_m.getbbox()
        _shape(img, layer, lit_m, bb, across=vertical,
               shade=([(0, 0.62), (0.22, 0.2), (0.5, 0), (1, 0)], [(0, 0), (0.5, 0), (1, 0.55)]),
               glow_r=max(2 * S, min(bb[2] - bb[0], bb[3] - bb[1]) * 0.35))


def arc3d(img, cx, cy, r, thick, a0, span, frac, cols, dim=None, caps=True, reverse=False, track=True):
    """Oblouk jako trubka v drazce. a0 = zacatek v uhlech Pillow (0 = vpravo, po smeru hodin),
    oblouk zabira mezikruzi r - thick .. r; reverse = plni se od konce."""
    box = (cx - r, cy - r, cx + r, cy + r)
    rr = r - thick / 2
    width = max(1, int(thick))

    def cap(dd, ang, col):
        if caps:
            a = math.radians(ang)
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
            dd.ellipse((px - thick / 2, py - thick / 2, px + thick / 2, py + thick / 2), fill=col)

    grad = _conic(img.size, cx, cy, a0, span, cols, reverse)        # barva podle uhlu
    if track or dim is not None:                             # drazka (nebo ztlumena stupnice)
        m = Image.new("L", img.size, 0)
        md = ImageDraw.Draw(m)
        md.arc(box, a0, a0 + span, fill=255, width=width)
        cap(md, a0, 255)
        cap(md, a0 + span, 255)
        if dim is not None:
            img.paste(grad.point(lambda v, k=dim: int(v * k)), (0, 0), m)
        else:
            _tint(img, m, GROOVE)
        _ring_shade(img, m, cx, cy, r, thick, GROOVE_SHADE)
    steps = int(span * frac)
    if steps <= 0:
        return
    layer = grad
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    lo_ang = a0 + span - steps if reverse else a0
    md.arc(box, lo_ang, lo_ang + steps, fill=255, width=width)
    cap(md, lo_ang, 255)
    cap(md, lo_ang + steps, 255)
    _glow(img, layer, mask, thick * 0.4)
    img.paste(layer, (0, 0), mask)
    _ring_shade(img, mask, cx, cy, r, thick, TUBE)


_conics = {}


def _conic(size, cx, cy, a0, span, cols, reverse=False):
    """Obrazek s barvou podle uhlu kolem (cx, cy): prechod cols od a0 po a0 + span (uhly Pillow);
    mimo rozsah barva blizsiho konce. Pocita se ve 1/3 rozliseni a uklada (zalezi jen na nastaveni)."""
    key = (size, round(cx), round(cy), round(a0, 1), round(span, 1), cols, reverse)
    if key not in _conics:
        k = 3
        w, h = max(1, size[0] // k), max(1, size[1] // k)
        pal = [mix(*cols, i / 255) for i in range(256)]
        px = []
        for y in range(h):
            dy = y * k + k / 2 - cy
            for x in range(w):
                delta = (math.degrees(math.atan2(dy, x * k + k / 2 - cx)) - a0) % 360
                if delta > span:
                    delta = span if delta - span < 360 - delta else 0
                t = delta / span if span else 0
                px.append(pal[int(255 * (1 - t if reverse else t))])
        im = Image.new("RGB", (w, h))
        im.putdata(px)
        if len(_conics) > 24:
            _conics.clear()
        _conics[key] = im.resize(size, Image.BILINEAR)
    return _conics[key]


def seg_ring3d(img, cx, cy, r, thick, segs):
    """Prstenec ze segmentu: segs = [(uhel_od, uhel_do, barva, rozsviceny)], uhly Pillow."""
    box = (cx - r, cy - r, cx + r, cy + r)
    width = max(1, int(thick))
    lay = Image.new("RGB", img.size, BLACK)
    lit, off = Image.new("L", img.size, 0), Image.new("L", img.size, 0)
    ld, lm, om = ImageDraw.Draw(lay), ImageDraw.Draw(lit), ImageDraw.Draw(off)
    for a0, a1, col, on in segs:
        if on:
            ld.arc(box, a0, a1, fill=col, width=width)
            lm.arc(box, a0, a1, fill=255, width=width)
        else:
            om.arc(box, a0, a1, fill=255, width=width)
    if off.getbbox():
        _tint(img, off, (13, 15, 18))
        _ring_shade(img, off, cx, cy, r, thick, GROOVE_SHADE)
    if lit.getbbox():
        _glow(img, lay, lit, thick * 0.45)
        img.paste(lay, (0, 0), lit)
        _ring_shade(img, lit, cx, cy, r, thick, TUBE)


def _dome(img, cx, cy, r, color, light=0.6, dark=0.55):
    """Vypoukla kulicka / cepicka: soustredne kruhy posunute ke svetlu (vlevo nahore)."""
    d = ImageDraw.Draw(img)
    n = max(8, min(40, int(r / S)))
    lo, hi = _dim(color, 1 - dark), _lerp(color, WHITE, light)
    for i in range(n):
        t = i / (n - 1)
        rr = r * (1 - 0.85 * t)
        ox, oy = -r * 0.3 * t, -r * 0.35 * t
        d.ellipse((cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr), fill=_interp([(0, lo), (0.55, color), (1, hi)], t))


METAL = [(0, (139, 148, 159)), (0.25, (58, 64, 72)), (0.55, (20, 23, 27)), (0.8, (44, 50, 56)), (1, (93, 102, 112))]


def _metal_ring(img, cx, cy, r_out, width):
    """Kovova luneta: mezikruzi s diagonalnim prechodem (odlesk vlevo nahore a vpravo dole)."""
    size = max(2, int(2 * r_out))

    def make():
        n = 64
        im = Image.new("RGB", (n, n))
        im.putdata([_interp(METAL, (x + y) / (2 * (n - 1))) for y in range(n) for x in range(n)])
        return im.resize((size, size), Image.BILINEAR)
    grad = _cached(("metal", size), make)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), fill=255)
    ri = r_out - width
    md.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=0)
    _paint(img, mask, grad, (int(cx - r_out), int(cy - r_out)))


def _disc(img, cx, cy, r, inner, outer, dy=-0.08):
    """Kotouc s kruhovym prechodem (ciferník, dno nadoby), svetlejsi stred mirne nahore."""
    d = ImageDraw.Draw(img)
    n = 40
    for i in range(n):
        t = i / (n - 1)
        rr = r * (1 - t * 0.98)
        oy = r * dy * t
        d.ellipse((cx - rr, cy + oy - rr, cx + rr, cy + oy + rr), fill=_interp([(0, outer), (0.3, _lerp(outer, inner, 0.6)), (1, inner)], t))


def _needle(img, cx, cy, ang, length, half_w, back, col):
    """Rucicka ze dvou pulek (svetla a tmava hrana) se stinem; ang = uhel Pillow ve stupnich."""
    a = math.radians(ang)
    p = lambda rr, da=0.0: (cx + rr * math.cos(a + da), cy + rr * math.sin(a + da))
    tip, tail = p(length), p(-back)
    bl, br = p(half_w, -math.pi / 2), p(half_w, math.pi / 2)
    sh = Image.new("L", img.size, 0)
    k = max(S, half_w * 0.6)
    ImageDraw.Draw(sh).polygon([(x + k, y + 1.5 * k) for x, y in (tip, bl, tail, br)], fill=255)
    _tint(img, sh, BLACK, 0.7)
    d = ImageDraw.Draw(img)
    d.polygon([tip, bl, tail], fill=_lerp(col, WHITE, 0.25))
    d.polygon([tip, br, tail], fill=_dim(col, 0.6))


def _line3d(img, pts, width, fill, side=None):
    """Cara grafu s hloubkou: tmavy bok pod carou, cara (barva nebo obrazek pres celou plochu),
    tenky odlesk nahore."""
    d = ImageDraw.Draw(img)
    w = max(1, int(width))
    if side:
        d.line([(x, y + w * 0.7) for x, y in pts], fill=side, width=w, joint="curve")
    if isinstance(fill, tuple):
        d.line(pts, fill=fill, width=w, joint="curve")
    else:
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).line(pts, fill=255, width=w, joint="curve")
        img.paste(fill, (0, 0), m)
    hm = Image.new("L", img.size, 0)
    ImageDraw.Draw(hm).line([(x, y - w * 0.22) for x, y in pts], fill=255, width=max(1, int(w * 0.28)), joint="curve")
    _tint(img, hm, WHITE, 0.55)


def _engraved(d, x0, y, x1, w):
    """Vyryta vodorovna linka: tmava drazka a svetly okraj pod ni."""
    d.line((x0, y, x1, y), fill=(3, 4, 5), width=max(1, int(w * 1.5)))
    d.line((x0, y + w * 1.25, x1, y + w * 1.25), fill=(29, 33, 39), width=max(1, int(w * 0.75)))


def _extrude(d, xy, text, font, c1, anchor):
    """Vytlaceni textu: vetsi pismo vrstvy do hloubky (svetle -> tmave), mensi jen tmavy stin."""
    px = font.size
    x, y = xy
    if px >= 20 * S:
        depth = int(min(9, max(3, round(px * 0.035))))
        top = _dim(c1, 0.77) if min(c1) > 200 else _dim(c1, 0.6)
        for i in range(depth, 0, -1):
            d.text((x, y + i), text, font=font, fill=_lerp(top, (20, 23, 27), (i - 1) / max(1, depth - 1)),
                   anchor=anchor)
    elif px >= 9 * S:
        d.text((x, y + max(2, round(px * 0.06))), text, font=font, fill=_dim(c1, 0.3), anchor=anchor)


# ---------------------------------------------------------------- obrazovky

def draw_two_bars(scr, data, template=False, history=None):
    img = _canvas()
    tcols = colors(scr, "text")
    unit = unit_for(scr, scr.get("senzor1"), data)
    is_deg = unit in DEGREE_UNITS
    big_px = 62 if is_deg or not unit else 54
    f_big = _font("Black", big_px)
    v1, fr1, _ = _value_text(scr, "1", data, f_big, template)
    v2, fr2, _ = _value_text(scr, "2", data, f_big, template)

    x0, x1 = 38 * S, 202 * S
    bar_h = 16 * S
    y_bar1 = 102 * S
    y_bar2 = y_bar1 + bar_h + 6 * S
    num_right = (180 if (is_deg or not unit) else 196) * S
    if _TS > 1.0:
        num_right = min(x1, num_right + int((_TS - 1.0) * 40) * S)

    _bar(img, x0, y_bar1, x1 - x0, bar_h, fr1, colors(scr, "bar1"))
    _bar(img, x0, y_bar2, x1 - x0, bar_h, fr2, colors(scr, "bar2"))

    lbl_w = int(70 * _TS) * S
    free1 = num_right - _textlen(img, v1, f_big) - x0 - 6 * S
    free2 = num_right - _textlen(img, v2, f_big) - x0 - 6 * S
    d = ImageDraw.Draw(img)
    f_l1 = _fit_font(d, scr.get("nadpis1", ""), "ExtraBold", 17, max(20 * S, min(lbl_w, free1)))
    f_l2 = _fit_font(d, scr.get("nadpis2", ""), "ExtraBold", 17, max(20 * S, min(lbl_w, free2)))
    _text(img, (x0, y_bar1 - 5 * S), scr.get("nadpis1", ""), f_l1, tcols, "ls")
    _text(img, (x0, y_bar2 + bar_h + 5 * S), scr.get("nadpis2", ""), f_l2, tcols, "lt")

    top_base = y_bar1 - 6 * S
    bot_top = y_bar2 + bar_h + 6 * S
    _text(img, (num_right, top_base), v1, f_big, tcols, "rs")
    _text(img, (num_right, bot_top), v2, f_big, tcols, "rt")

    if is_deg:
        f_deg = _font("ExtraBold", 24)
        cap = int(44 * _TS) * S
        _text(img, (num_right + 3 * S, top_base - cap), "°", f_deg, tcols, "lt")
        _text(img, (num_right + 3 * S, bot_top), "°", f_deg, tcols, "lt")
    elif unit:
        f_unit = _font("ExtraBold", 14)
        cap = int(big_px * 0.71 * _TS) * S
        _text(img, (num_right, top_base - cap - 5 * S), unit, f_unit, tcols, "rs")
        _text(img, (num_right, bot_top + cap + 9 * S), unit, f_unit, tcols, "rt")
    return img


def draw_arc(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    sensor = scr.get("senzor")
    unit = unit_for(scr, sensor, data)
    txt, frac, _ = _value_text(scr, "", data, _font("Black", 66), template)

    c = W // 2
    _arc(img, c, 92 * S, 20 * S, 180, 315, frac, colors(scr, "oblouk"))

    lx = c - 56 * S
    title = scr.get("nadpis") or sensor or ""
    _text(img, (lx, c - 18 * S), title, _fit_font(d, title, "ExtraBold", 20, 120 * S), tcols, "ls")
    f_big = _fit_font(d, txt, "Black", 66, 120 * S)
    _text(img, (lx - 3 * S, c - 10 * S), txt, f_big, tcols, "lt")
    _unit_after(img, lx - 3 * S, c - 10 * S, txt, f_big, unit, tcols)
    return img


def draw_gauge(scr, data, template=False, history=None):
    """Budik: stupnice 240°, ruckicka, hodnota dole uprostred."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    sensor = scr.get("senzor")
    unit = unit_for(scr, sensor, data)
    txt, frac, _ = _value_text(scr, "", data, _font("Black", 54), template)
    c = W // 2
    r = 96 * S
    start, span = 150, 240
    cols = colors(scr, "oblouk")
    if PLASTIC:                                     # ciferník v kovove lunete (vejde se do okraje displeje)
        _metal_ring(img, c, c, r + 10 * S, 5 * S)
        d.ellipse((c - r - 5 * S, c - r - 5 * S, c + r + 5 * S, c + r + 5 * S), fill=(2, 2, 3))
        _disc(img, c, c, r + 4 * S, (27, 31, 37), (3, 4, 5))
    _arc(img, c, r, 18 * S, start, span, frac, cols, dim_rest=0.28)

    # rysky
    for i in range(11):
        a = math.radians(start + span * i / 10)
        r1, r2 = r - 26 * S, r - (34 if i % 5 == 0 else 30) * S
        d.line((c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)),
               fill=GREY, width=3 * S if i % 5 == 0 else 2 * S)
    # rucicka
    ncols = colors(scr, "rucicka")
    if PLASTIC:
        _needle(img, c, c, start + span * frac, r - 30 * S, 8 * S, 14 * S, ncols[0])
        _dome(img, c, c, 13 * S, _lerp(ncols[0], (120, 128, 138), 0.3))
        return _gauge_text(img, d, scr, txt, unit, tcols, sensor, c)
    a = math.radians(start + span * frac)
    tip = (c + (r - 30 * S) * math.cos(a), c + (r - 30 * S) * math.sin(a))
    perp = a + math.pi / 2
    base = 7 * S
    poly = [(c + base * math.cos(perp), c + base * math.sin(perp)), tip,
            (c - base * math.cos(perp), c - base * math.sin(perp))]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    _paint(img, mask, _hgrad(W, W, *ncols))
    d.ellipse((c - 12 * S, c - 12 * S, c + 12 * S, c + 12 * S), fill=ncols[0])
    d.ellipse((c - 5 * S, c - 5 * S, c + 5 * S, c + 5 * S), fill=BLACK)
    return _gauge_text(img, d, scr, txt, unit, tcols, sensor, c)


def _gauge_text(img, d, scr, txt, unit, tcols, sensor, c):
    f_big = _fit_font(d, txt, "Black", 54, 110 * S)
    tw = d.textlength(txt, font=f_big)
    x_left = c - tw / 2
    y_num = c + 22 * S
    _text(img, (x_left, y_num), txt, f_big, tcols, "lt")
    _unit_after(img, x_left, y_num, txt, f_big, unit, tcols, deg_px=22, unit_px=15)
    # popisek pod cislem - ruckicka se ho nikdy nedotkne
    title = scr.get("nadpis") or sensor or ""
    bottom = d.textbbox((0, y_num), "0", font=_font("Black", 54), anchor="lt")[3]   # pevna pozice
    _text(img, (c, bottom + 6 * S), title, _fit_font(d, title, "ExtraBold", 17, 120 * S), tcols, "mt")
    return img


def draw_rings(scr, data, template=False, history=None):
    """Dva soustredne kruhy (vnejsi = hodnota 1, vnitrni = hodnota 2), cisla uprostred."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    unit = unit_for(scr, scr.get("senzor1"), data)
    f_big = _font("Black", 40)
    v1, fr1, _ = _value_text(scr, "1", data, f_big, template)
    v2, fr2, _ = _value_text(scr, "2", data, f_big, template)
    c = W // 2
    start, span = 270, 360
    _arc(img, c, 104 * S, 16 * S, start - 90, 300, fr1, colors(scr, "kruh1"))
    _arc(img, c, 82 * S, 16 * S, start - 90, 300, fr2, colors(scr, "kruh2"))

    _center_pair(img, scr, v1, v2, colors(scr, "kruh1"), colors(scr, "kruh2"), unit, 40, 84 * S)
    return img


def _center_pair(img, scr, v1, v2, k1, k2, unit, px, max_w):
    """Dve hodnoty nad sebou uprostred, popisky v barvach svych ukazatelu."""
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    c = W // 2
    for n, (val, y, lbl, kc) in enumerate(((v1, c - 6 * S, scr.get("nadpis1", ""), k1),
                                           (v2, c + 6 * S, scr.get("nadpis2", ""), k2))):
        f = _fit_font(d, val, "Black", px, max_w)
        tw = d.textlength(val, font=f)
        x_left = c - tw / 2
        anchor_y = y
        if n == 0:
            bb = d.textbbox((x_left, 0), val, font=f, anchor="lt")
            top = y - (bb[3] - bb[1])
        else:
            top = y
        _text(img, (x_left, top), val, f, tcols, "lt")
        _unit_after(img, x_left, top, val, f, unit, tcols, deg_px=round(px * 0.45), unit_px=round(px * 0.3),
                    deg_dy=0)
        # popisek v barve sveho kruhu
        fl = _fit_font(d, lbl, "ExtraBold", round(px * 0.33), max_w)
        if n == 0:
            _text(img, (c, top - 4 * S), lbl, fl, (kc[0], kc[0]), "ms")
        else:
            h = d.textbbox((0, 0), val, font=f, anchor="lt")[3]
            _text(img, (c, top + h + 5 * S), lbl, fl, (kc[0], kc[0]), "mt")


def draw_graph(scr, data, template=False, history=None):
    """Prubeh hodnoty v case: plocha s prechodem podle vysky + aktualni hodnota."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    sensor = scr.get("senzor")
    unit = unit_for(scr, sensor, data)
    lo, hi = float(scr.get("min", 0)), float(scr.get("max", 100))
    f_big = _font("Black", 50)
    txt, _frac_v, _ = _value_text(scr, "", data, f_big, template)

    gx0, gx1 = 18 * S, 222 * S
    gy0, gy1 = 104 * S, 214 * S          # oblast grafu (nahore, dole)
    _graph_frame(img, d, gx0, gy0, gx1, gy1)

    div = float(scr.get("delitel", 1)) or 1
    vals = [1.0] * 40 if template else [v / div for v in (history or {}).get(sensor, [])]
    gcols = colors(scr, "graf")
    if len(vals) >= 2:
        n = len(vals)
        pad = 6 * S
        def pt(i, v):
            fr = 1.0 if template else _frac(v, lo, hi)
            return (gx0 + pad + (gx1 - gx0 - 2 * pad) * i / (n - 1),
                    gy1 - pad - (gy1 - gy0 - 2 * pad) * fr)
        pts = [pt(i, v) for i, v in enumerate(vals)]
        grad = _vgrad(gx1 - gx0, gy1 - gy0, *gcols)
        # plocha: syta, smerem dolu mirne slabne (krytí 200 -> 150 z 255)
        area = Image.new("L", img.size, 0)
        ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], gy1 - pad), (pts[0][0], gy1 - pad)], fill=255)
        fade = Image.new("L", img.size, 0)
        fd = ImageDraw.Draw(fade)
        for y in range(gy0, gy1 + 1):
            fd.line((gx0, y, gx1, y), fill=round(200 - 50 * (y - gy0) / (gy1 - gy0)))
        _paint(img, ImageChops.multiply(area, fade), grad, (gx0, gy0))
        # cara: silna, svetlejsi nez plocha, s tmavym lemem, aby se od plochy oddelila
        light = [mix(c, WHITE, 0.35) for c in gcols]
        lgrad = _vgrad(gx1 - gx0, gy1 - gy0, *light)
        ex, ey = pts[-1]
        col = mix(*light, 1 - (ey - gy0) / (gy1 - gy0))
        if PLASTIC:
            full = Image.new("RGB", img.size, BLACK)
            full.paste(lgrad, (gx0, gy0))
            _line3d(img, pts, 8 * S, full, side=_dim(gcols[1], 0.4))
            _dome(img, ex, ey, 10 * S, col)
        else:
            ImageDraw.Draw(img).line(pts, fill=BLACK, width=11 * S, joint="curve")
            line = Image.new("L", img.size, 0)
            ImageDraw.Draw(line).line(pts, fill=255, width=8 * S, joint="curve")
            _paint(img, line, lgrad, (gx0, gy0))
            d.ellipse((ex - 11 * S, ey - 11 * S, ex + 11 * S, ey + 11 * S), fill=BLACK)
            d.ellipse((ex - 9 * S, ey - 9 * S, ex + 9 * S, ey + 9 * S), fill=col)

    title = scr.get("nadpis") or sensor or ""
    _text(img, (gx0 + 2 * S, 34 * S), title, _fit_font(d, title, "ExtraBold", 17, 110 * S), tcols, "ls")
    f = _fit_font(d, txt, "Black", 50, 150 * S)
    _text(img, (gx0, 42 * S), txt, f, tcols, "lt")
    _unit_after(img, gx0, 42 * S, txt, f, unit, tcols, deg_px=22, unit_px=15)
    secs = int(scr.get("delka_s", 120))
    span_txt = f"{secs // 60} min" if secs >= 60 else f"{secs} s"
    _text(img, (gx1, 34 * S), span_txt, _font("ExtraBold", 12), (GREY, GREY), "rs")
    return img


def _graph_frame(img, d, gx0, gy0, gx1, gy1):
    """Ramecek grafu: ploche = obrys a linky, plasticke = zapustena obrazovka s vyrytymi linkami."""
    if PLASTIC:
        _groove_rect(img, (gx0, gy0, gx1, gy1), 8 * S, base=(22, 25, 30))
        for i in (1, 2, 3):
            _engraved(d, gx0 + 6 * S, gy0 + (gy1 - gy0) * i / 4, gx1 - 6 * S, S)
        return
    d.rounded_rectangle((gx0, gy0, gx1, gy1), 8 * S, outline=DARK, width=2 * S)
    for i in (1, 2, 3):
        y = gy0 + (gy1 - gy0) * i / 4
        d.line((gx0 + 4 * S, y, gx1 - 4 * S, y), fill=(45, 45, 45), width=S)


def draw_time(scr, data, template=False, history=None):
    now = datetime.now()
    img = _canvas()
    d = ImageDraw.Draw(img)
    c = W // 2
    f_h = _raw_font("Black", 88)
    f_m = _raw_font("Bold", 88)
    hh, mm = f"{now.hour:02d}", f"{now.minute:02d}"
    if template:
        ch_h = _TCHAR or widest_digit(f_h)
        ch_m = _TCHAR or widest_digit(f_m)
        hh, mm = ch_h * 2, ch_m * 2
    gap = 10 * S
    hb = d.textbbox((0, 0), "0", font=f_h)       # "0" = i s preteky oblych cislic
    mb = d.textbbox((0, 0), "0", font=f_m)
    y_h = c - gap // 2 - hb[3]
    y_m = c + gap // 2 - mb[1]
    for text, font, y, part in ((hh, f_h, y_h, "hodiny"), (mm, f_m, y_m, "minuty")):
        w = d.textlength(text, font=font)
        _text(img, (int(c - w / 2), int(y)), text, font, colors(scr, part))
    return img


# ------------------------------------------------------------ dalsi obrazovky

def _mirror_arc(img, c, r, thick, start, span, frac, cols, **kw):
    """Oblouk zrcadleny podle svisle osy (pravy oblouk roste zdola nahoru jako levy)."""
    layer = _canvas()
    _arc(layer, c, r, thick, start, span, frac, cols, **kw)
    img.paste(ImageChops.lighter(img, ImageOps.mirror(layer)))


def draw_two_arcs(scr, data, template=False, history=None):
    """Hodnota 1 = oblouk vlevo, hodnota 2 = oblouk vpravo, oba rostou zdola nahoru; cisla uprostred."""
    img = _canvas()
    unit = unit_for(scr, scr.get("senzor1"), data)
    f_big = _font("Black", 46)
    v1, fr1, _ = _value_text(scr, "1", data, f_big, template)
    v2, fr2, _ = _value_text(scr, "2", data, f_big, template)
    c = W // 2
    k1, k2 = colors(scr, "oblouk1"), colors(scr, "oblouk2")
    _arc(img, c, 108 * S, 20 * S, 105, 150, fr1, k1)
    _mirror_arc(img, c, 108 * S, 20 * S, 105, 150, fr2, k2)
    _center_pair(img, scr, v1, v2, k1, k2, unit, 46, 128 * S)
    return img


def draw_segments(scr, data, template=False, history=None):
    """Prstenec ze 30 segmentu (300°), rozsvicene segmenty v prechodu barev, cislo uprostred."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    sensor = scr.get("senzor")
    unit = unit_for(scr, sensor, data)
    txt, frac, _ = _value_text(scr, "", data, _font("Black", 60), template)
    c = W // 2
    cols = colors(scr, "segmenty")
    n, start, span = 30, 120, 300
    step = span / n
    lit = round(frac * n)
    box = (c - 110 * S, c - 110 * S, c + 110 * S, c + 110 * S)
    if PLASTIC:
        seg_ring3d(img, c, c, 110 * S, 24 * S, [(start + i * step + 1.2, start + (i + 1) * step - 1.2,
                                                  mix(*cols, i / (n - 1)), i < lit) for i in range(n)])
    for i in range(0 if PLASTIC else n):
        a0 = start + i * step + 1.2
        col = mix(*cols, i / (n - 1))
        d.arc(box, a0, a0 + step - 2.4, fill=col if i < lit else _dim(col, 0.18), width=24 * S)
    title = scr.get("nadpis") or sensor or ""
    _text(img, (c, c - 30 * S), title, _fit_font(d, title, "ExtraBold", 18, 120 * S), tcols, "ms")
    f_big = _fit_font(d, txt, "Black", 60, 130 * S)
    tw = d.textlength(txt, font=f_big)
    _text(img, (c - tw / 2, c - 22 * S), txt, f_big, tcols, "lt")
    _unit_after(img, c - tw / 2, c - 22 * S, txt, f_big, unit, tcols, deg_px=24, unit_px=16)
    return img


def draw_four(scr, data, template=False, history=None):
    """Ctyri hodnoty ve ctvrtinach kruhu, kazda s vlastnim obloukem na obvodu
    (1 vlevo nahore, 2 vpravo nahore, 3 vlevo dole, 4 vpravo dole)."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    cols = colors(scr, "oblouky")
    c = W // 2
    r = 112 * S
    if PLASTIC:                                         # vyryty kriz
        d.line((c - S, c - 88 * S, c - S, c + 88 * S), fill=(3, 4, 5), width=3 * S)
        d.line((c + 2 * S, c - 88 * S, c + 2 * S, c + 88 * S), fill=(29, 33, 39), width=S)
        _engraved(d, c - 88 * S, c - S, c + 88 * S, 2 * S)
    else:
        d.line((c, c - 88 * S, c, c + 88 * S), fill=(45, 45, 45), width=2 * S)
        d.line((c - 88 * S, c, c + 88 * S, c), fill=(45, 45, 45), width=2 * S)
    # oblouk vlevo nahore roste od vodorovne osy nahoru; ostatni ctvrtiny jsou jeho zrcadla,
    # takze vsechny rostou od vodorovne osy k svisle
    for n, sx, sy in (("1", -1, -1), ("2", 1, -1), ("3", -1, 1), ("4", 1, 1)):
        txt, frac, _ = _value_text(scr, n, data, _font("Black", 34), template)
        layer = _canvas()
        _arc(layer, c, r, 14 * S, 185, 80, frac, cols)
        if sx > 0:
            layer = ImageOps.mirror(layer)
        if sy > 0:
            layer = ImageOps.flip(layer)
        img.paste(ImageChops.lighter(img, layer))
        cx, cy = c + sx * 46 * S, c + sy * 40 * S
        f = _fit_font(d, txt, "Black", 34, 70 * S)
        unit = unit_for(scr, scr.get("senzor" + n), data)
        tw = d.textlength(txt, font=f)
        h = d.textbbox((0, 0), txt, font=f, anchor="lt")[3]
        top = cy - h / 2
        _text(img, (cx - tw / 2, top), txt, f, tcols, "lt")
        _unit_after(img, cx - tw / 2, top, txt, f, unit, tcols, deg_px=16, unit_px=11, deg_dy=0)
        lbl = scr.get("nadpis" + n, "")
        fl = _fit_font(d, lbl, "ExtraBold", 12, 70 * S)
        if sy < 0:
            _text(img, (cx, top - 4 * S), lbl, fl, (GREY, GREY), "ms")
        else:
            _text(img, (cx, top + h + 4 * S), lbl, fl, (GREY, GREY), "mt")
    return img


def draw_cooling(scr, data, template=False, history=None):
    """Kraken: teplota kapaliny uprostred, vykon pumpy (vlevo) a ventilatoru (vpravo) jako oblouky."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    c = W // 2
    kp, kv = colors(scr, "pumpa"), colors(scr, "ventilatory")

    def g(key):
        return None if template else value_for(key, data)
    pd, pr, fd, fr, lq = g("@pumpa_vykon"), g("@pumpa"), g("@ventilatory_vykon"), g("@ventilatory"), g("@kapalina")
    _arc(img, c, 108 * S, 20 * S, 105, 150, 1.0 if template else _frac(pd, 0, 100), kp)
    _mirror_arc(img, c, 108 * S, 20 * S, 105, 150, 1.0 if template else _frac(fd, 0, 100), kv)
    _text(img, (c, c - 40 * S), "KAPALINA", _font("ExtraBold", 15), tcols, "ms")
    if template:
        ch = _TCHAR or widest_digit(_font("Black", 58))
        txt = ch * 2 + "." + ch
    else:
        txt = _fmt(lq, 1)
    f_big = _fit_font(d, txt, "Black", 58, 120 * S)
    tw = d.textlength(txt, font=f_big)
    lc = colors(scr, "kapalina")
    _text(img, (c - tw / 2 - 6 * S, c - 34 * S), txt, f_big, lc, "lt")
    _unit_after(img, c - tw / 2 - 6 * S, c - 34 * S, txt, f_big, "°C", lc, deg_px=24)
    y = c + 34 * S
    for lbl, duty, rpm, kc in (("PUMPA", pd, pr, kp), ("VENTILÁTORY", fd, fr, kv)):
        if template:
            line = f"{lbl} 100 % · 8888"
        else:
            line = f"{lbl} {_fmt(duty, 0)} %" + ("" if rpm is None else f" · {_fmt(rpm, 0)}")
        _text(img, (c, y), line, _fit_font(d, line, "ExtraBold", 14, 130 * S), (kc[1], kc[1]), "mt")
        y += 20 * S
    return img


def draw_graph_two(scr, data, template=False, history=None):
    """Dve hodnoty v case v jednom grafu, kazda ve svem rozsahu min-max."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    gx0, gx1 = 18 * S, 222 * S
    gy0, gy1 = 104 * S, 214 * S
    _graph_frame(img, d, gx0, gy0, gx1, gy1)
    div = float(scr.get("delitel", 1)) or 1
    pad = 6 * S
    for n, left in (("2", False), ("1", True)):                     # 1 se kresli navrch
        cols = colors(scr, "graf" + n)
        sensor = scr.get("senzor" + n)
        lo, hi = float(scr.get("min" + n, 0)), float(scr.get("max" + n, 100))
        vals = [1.0] * 40 if template else [v / div for v in (history or {}).get(sensor, [])]
        if len(vals) >= 2:
            m = len(vals)
            pts = [(gx0 + pad + (gx1 - gx0 - 2 * pad) * i / (m - 1),
                    gy1 - pad - (gy1 - gy0 - 2 * pad) * (1.0 if template else _frac(v, lo, hi)))
                   for i, v in enumerate(vals)]
            if n == "1":                                   # plocha jen pod prvni hodnotou
                area = Image.new("L", img.size, 0)
                ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], gy1 - pad), (pts[0][0], gy1 - pad)], fill=90)
                _paint(img, area, _vgrad(gx1 - gx0, gy1 - gy0, *cols), (gx0, gy0))
            ex, ey = pts[-1]
            if PLASTIC:
                full = Image.new("RGB", img.size, BLACK)
                full.paste(_vgrad(gx1 - gx0, gy1 - gy0, *cols), (gx0, gy0))
                _line3d(img, pts, 6 * S, full, side=_dim(cols[1], 0.4))
                _dome(img, ex, ey, 8 * S, cols[1])
            else:
                d.line(pts, fill=BLACK, width=10 * S, joint="curve")
                line = Image.new("L", img.size, 0)
                ImageDraw.Draw(line).line(pts, fill=255, width=6 * S, joint="curve")
                _paint(img, line, _vgrad(gx1 - gx0, gy1 - gy0, *cols), (gx0, gy0))
                d.ellipse((ex - 8 * S, ey - 8 * S, ex + 8 * S, ey + 8 * S), fill=cols[1])
        txt, _fr, _v = _value_text(scr, n, data, _font("Black", 40), template)
        unit = unit_for(scr, sensor, data)
        f = _fit_font(d, txt, "Black", 40, 70 * S)
        tw = d.textlength(txt, font=f)
        extra = (14 if unit in DEGREE_UNITS else 30 if unit else 0) * S
        # hodnoty u stredu, at je kulaty okraj displeje neurizne
        xl = W // 2 - 10 * S - tw - extra if left else W // 2 + 10 * S
        vc = (cols[0], cols[0])
        _text(img, (xl, 50 * S), txt, f, vc, "lt")
        _unit_after(img, xl, 50 * S, txt, f, unit, vc, deg_px=18, unit_px=12)
        title = scr.get("nadpis" + n) or sensor or ""
        tx = W // 2 - 10 * S if left else W // 2 + 10 * S
        _text(img, (tx, 44 * S), title, _fit_font(d, title, "ExtraBold", 14, 90 * S), tcols, "rs" if left else "ls")
    secs = int(scr.get("delka_s", 120))
    span_txt = f"{secs // 60} min" if secs >= 60 else f"{secs} s"
    _text(img, (W // 2, gy1 + 8 * S), span_txt, _font("ExtraBold", 12), (GREY, GREY), "mt")
    return img


def _hand(d, c, angle, length, width, col, back=0):
    """Rucicka od stredu (s presahem dozadu) se zakulacenymi konci; uhel 0 = 12 hodin."""
    a = math.radians(angle - 90)
    x0, y0 = c - back * math.cos(a), c - back * math.sin(a)
    x1, y1 = c + length * math.cos(a), c + length * math.sin(a)
    d.line((x0, y0, x1, y1), fill=col, width=width)
    for x, y in ((x0, y0), (x1, y1)):
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=col)


def draw_analog(scr, data, template=False, history=None):
    """Rucickove hodiny: cifernik s ryskami, hodinova, minutova a sekundova rucicka, datum."""
    now = datetime.now()
    img = _canvas()
    d = ImageDraw.Draw(img)
    c = W // 2
    r = 114 * S
    dial = colors(scr, "cifernik")[0]
    if PLASTIC:                                         # kovova luneta a zapusteny ciferník
        _metal_ring(img, c, c, r + 4 * S, 7 * S)
        d.ellipse((c - r + 3 * S, c - r + 3 * S, c + r - 3 * S, c + r - 3 * S), fill=(2, 2, 3))
        _disc(img, c, c, r - 4 * S, (27, 31, 37), (3, 4, 5))
    else:
        d.ellipse((c - r, c - r, c + r, c + r), outline=_dim(dial, 0.55), width=3 * S)
    for i in range(60):
        a = math.radians(i * 6 - 90)
        big = i % 5 == 0
        r1, r2 = r - (12 if PLASTIC else 8) * S, r - (24 if i % 15 == 0 else 18 if big else 12) * S - (4 * S if PLASTIC else 0)
        seg = (c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a))
        wt = (5 if i % 15 == 0 else 4 if big else 2) * S
        if PLASTIC:                                     # rysky vystupuji: stin vpravo dole, lesk nahore
            d.line([v + (S if k % 2 == 0 else 1.5 * S) for k, v in enumerate(seg)], fill=BLACK, width=wt)
        d.line(seg, fill=dial if big else _dim(dial, 0.5), width=wt)
        if PLASTIC and big:
            d.line([v - (0.6 * S if k % 2 else 0.4 * S) for k, v in enumerate(seg)], fill=_lerp(dial, WHITE, 0.6),
                   width=max(1, int(wt * 0.3)))
    f_n = _raw_font("ExtraBold", 22)
    for num, ang in ((12, 0), (3, 90), (6, 180), (9, 270)):
        a = math.radians(ang - 90)
        _text(img, (c + (r - 42 * S) * math.cos(a), c + (r - 42 * S) * math.sin(a)), str(num), f_n,
              (dial, dial), "mm")
    if scr.get("datum"):
        date = f"{DAYS[now.weekday()][:2].upper()} {now.day}. {now.month}."
        _text(img, (c, c + 44 * S), date, _raw_font("ExtraBold", 17), colors(scr, "datum"), "mm")
    hc = colors(scr, "rucicky")[0]
    sc = colors(scr, "sekundy")[0]
    h = (now.hour % 12 + now.minute / 60) * 30
    m = (now.minute + now.second / 60) * 6
    if PLASTIC:
        _needle(img, c, c, h - 90, 60 * S, 6.5 * S, 11 * S, hc)
        _needle(img, c, c, m - 90, 90 * S, 4.5 * S, 13 * S, hc)
        _needle(img, c, c, now.second * 6 - 90, 97 * S, 1.8 * S, 22 * S, sc)
        _dome(img, c, c, 9 * S, sc)
        d.ellipse((c - 2.5 * S, c - 2.5 * S, c + 2.5 * S, c + 2.5 * S), fill=(10, 12, 15))
        return img
    _hand(d, c, h, 58 * S, 11 * S, hc, back=10 * S)
    _hand(d, c, m, 88 * S, 7 * S, hc, back=12 * S)
    _hand(d, c, now.second * 6, 96 * S, 3 * S, sc, back=22 * S)
    d.ellipse((c - 9 * S, c - 9 * S, c + 9 * S, c + 9 * S), fill=sc)
    d.ellipse((c - 3 * S, c - 3 * S, c + 3 * S, c + 3 * S), fill=BLACK)
    return img


def _seconds_ring(d, c, cols, second, template, img=None):
    """Prstenec ze 60 segmentu, rozsvicene do aktualni sekundy."""
    if PLASTIC and img is not None:
        seg_ring3d(img, c, c, 112 * S, 10 * S, [(-90 + i * 6 + 1, -90 + i * 6 + 5, mix(*cols, i / 59),
                                                  template or i <= second) for i in range(60)])
        return
    box = (c - 112 * S, c - 112 * S, c + 112 * S, c + 112 * S)
    for i in range(60):
        a0 = -90 + i * 6 + 1
        col = mix(*cols, i / 59)
        d.arc(box, a0, a0 + 4, fill=col if template or i <= second else _dim(col, 0.15), width=10 * S)


def draw_clock_date(scr, data, template=False, history=None):
    """Digitalni cas uprostred prstence ze 60 segmentu (sekundy); "hodiny_pod_sebou" = hodiny
    nad minutami. Velikost cislic ridi "Velikost textu", datum pod casem je volitelne."""
    now = datetime.now()
    img = _canvas()
    d = ImageDraw.Draw(img)
    c = W // 2
    _seconds_ring(d, c, colors(scr, "sekundy"), now.second, template, img)
    stacked = scr.get("typ") == "hodiny_pod_sebou"
    show_date = bool(scr.get("datum"))
    hh, mm = f"{now.hour:02d}", f"{now.minute:02d}"
    inner = 180 * S                                        # sirka uvnitr prstence
    if stacked:
        f = _font("Black", 64)
        ch = _TCHAR or widest_digit(f)
        if template:
            hh = mm = ch * 2
        # stejna vyska pro obe cisla (podle "0"), mezera 6 px; cely blok (i s datem) na stred
        def too_big(f):                                    # obe cisla se musi vejit do prstence
            b = d.textbbox((0, 0), "0", font=f, anchor="lt")
            return d.textlength(ch * 2, font=f) > inner * 0.8 or 2 * (b[3] - b[1]) + 6 * S > inner * 0.85
        while f.size > 20 * S and too_big(f):
            f = ImageFont.truetype(f.path, f.size - S)
        bb = d.textbbox((0, 0), "0", font=f, anchor="lt")
        h = bb[3] - bb[1]
        gap = 6 * S
        f_d = _font("ExtraBold", 16)
        date_h = (d.textbbox((0, 0), "0", font=f_d, anchor="lt")[3] + 8 * S) if show_date else 0
        top = c - (2 * h + gap + date_h) / 2 - bb[1]
        cm = colors(scr, "minuty")
        for text, y, cols in ((hh, top, colors(scr, "hodiny")), (mm, top + h + gap, cm)):
            w = d.textlength(text, font=f)
            _text(img, (int(c - w / 2), int(y)), text, f, cols, "lt")
        if show_date:
            _text(img, (c, top + bb[1] + 2 * h + gap + 8 * S), f"{now.day}. {now.month}.", f_d,
                  colors(scr, "datum"), "mt")
        return img
    txt = f"{hh}:{mm}"
    f = _font("Black", 50)
    if template:
        ch = _TCHAR or widest_digit(f)
        txt = f"{ch * 2}:{ch * 2}"
    while f.size > 20 * S and d.textlength(txt, font=f) > inner:
        f = ImageFont.truetype(f.path, f.size - S)
    bb = d.textbbox((0, 0), "0", font=f, anchor="lt")
    h = bb[3] - bb[1]
    f_d = _font("ExtraBold", 16)
    date_h = (d.textbbox((0, 0), "0", font=f_d, anchor="lt")[3] + 10 * S) if show_date else 0
    top = c - (h + date_h) / 2 - bb[1]
    w = d.textlength(txt, font=f)
    _text(img, (int(c - w / 2), int(top)), txt, f, colors(scr, "hodiny"), "lt")
    if show_date:
        _text(img, (c, top + bb[1] + h + 10 * S), f"{DAYS[now.weekday()]} {now.day}. {now.month}.", f_d,
              colors(scr, "datum"), "mt")
    return img


_image_cache = {}


def image_files():
    """Obrazky pro obrazovku "obrazek": obrazky/kraken/* (barevne, pruhledne pozadi), obrazky/*
    a obrazky/predlohy/* (relativni cesty)."""
    out = []
    for sub in ("kraken", "", "predlohy"):
        try:
            names = sorted(os.listdir(os.path.join(IMAGES, sub)))
        except OSError:
            continue
        out += [(sub + "/" if sub else "") + n for n in names
                if n.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"))]
    return out


def _load_image(name, mode, cols):
    path = os.path.join(IMAGES, *name.split("/"))
    key = (path, os.path.getmtime(path), mode, cols)
    if key in _image_cache:
        return _image_cache[key]
    src = Image.open(path).convert("RGBA")
    rgb = Image.new("RGB", src.size, BLACK)
    rgb.paste(src, (0, 0), src.getchannel("A"))
    if mode != IMAGE_MODES[0]:                         # pozadi = barva leveho horniho rohu
        bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        diff = ImageChops.difference(rgb, bg).convert("L")
        mask = diff.point(lambda v: 0 if v < 30 else 255 if v > 90 else round((v - 30) * 255 / 60))
        if mode == IMAGE_MODES[2]:                     # jen tvar, obarveny prechodem
            rgb = _hgrad(rgb.width, rgb.height, *cols)
        elif mode == IMAGE_MODES[3]:                   # cerne casti loga by na displeji nebyly videt
            r, g, b = rgb.split()
            dark = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
                lambda v: 255 if v < 60 else 0 if v > 120 else round((120 - v) * 255 / 60))
            rgb = Image.composite(Image.new("RGB", rgb.size, WHITE), rgb, dark)
        out = Image.new("RGB", rgb.size, BLACK)
        out.paste(rgb, (0, 0), mask)
        rgb = out
    bb = rgb.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
    if bb:
        rgb = rgb.crop(bb)
    if len(_image_cache) > 16:
        _image_cache.clear()
    _image_cache[key] = rgb
    return rgb


def draw_image(scr, data, template=False, history=None):
    """Obrazek / logo uprostred pres cely ctvercovy displej; velikost ridi "Velikost obsahu"."""
    img = _canvas()
    try:
        pic = _load_image(scr.get("soubor", ""), scr.get("uprava", IMAGE_MODES[0]), colors(scr, "tvar"))
    except (OSError, ValueError):
        d = ImageDraw.Draw(img)
        d.ellipse((W // 2 - 100 * S, W // 2 - 100 * S, W // 2 + 100 * S, W // 2 + 100 * S), outline=DARK,
                  width=3 * S)
        _text(img, (W // 2, W // 2), "chybí obrázek", _font("ExtraBold", 18), (GREY, GREY), "mm")
        return img
    k = W / max(pic.width, pic.height)                       # displej je ctvercovy -> delsi strana = sirka
    pic = pic.resize((max(1, round(pic.width * k)), max(1, round(pic.height * k))), Image.LANCZOS)
    img.paste(pic, ((W - pic.width) // 2, (W - pic.height) // 2))
    return img


# ------------------------------------------ ctvercove obrazovky (navrhy z Claude Design)
# Rozvrzeni je v souradnicich navrhu 480x480 (= 2x displej); _u() prevede na platno 720x720.
# Obrazovky vyuzivaji cely ctverec, proto se neorezavaji na obsah (FULL_FRAME) a nemaji
# posuvnik "Velikost textu" (pisma maji pevnou velikost podle navrhu).

PANEL = (14, 16, 19)          # podklad dlazdic
TRACK = (28, 31, 36)          # podklad baru
OFF = (26, 29, 34)            # zhasnuty segment
MUTED = (138, 146, 156)       # popisky
UNIT_BY_DIV = {("MB", 1000): "GB", ("MHz", 1000): "GHz", ("KB/s", 1000): "MB/s", ("MB/s", 1000): "GB/s"}


def _u(v):
    return round(v * 1.5)


def _f(weight, px):
    """Pismo podle navrhu (px v navrhu 480x480)."""
    return _raw_font(weight, px / 2)


def _slot(scr, n, data, dec_key=None):
    """Hodnota slotu n ("" / "1".."4") -> (text, podil 0..1, jednotka, cislo)."""
    sensor = scr.get("senzor" + n)
    div = float(scr.get("delitel" + n, 1) or 1)
    v = value_for(sensor, data, div)
    lo, hi = float(scr.get("min" + n, 0)), float(scr.get("max" + n, 100))
    txt = _fmt(v, scr.get(dec_key or ("desetinna" + n), 0))
    u = scr.get("jednotka" + n, "auto")
    if u == "auto":
        u = (data.get(sensor) or {}).get("unit", "")
        u = UNIT_BY_DIV.get((u, int(div)), u if div == 1 else "")
    return txt, _frac(v, lo, hi), u, v


def _short_unit(u):
    return "°" if u in DEGREE_UNITS else u


def _shrink(d, txt, f, max_w):
    while f.size > 8 * S and d.textlength(txt, font=f) > max_w:
        f = ImageFont.truetype(f.path, f.size - S)
    return f


def _num(img, x, base, txt, f, cols, unit="", f_unit=None, anchor="l", max_w=None, gap=4, ucols=None):
    """Cislo s jednotkou vpravo nahore (zarovnanou na horni okraj cislic). x = levy okraj,
    stred nebo pravy okraj celku podle anchor ("l"/"m"/"r"), base = uctari v navrhu."""
    d = ImageDraw.Draw(img)
    x, base = _u(x), _u(base)
    gap = _u(gap) if unit else 0
    if max_w:
        uw = d.textlength(unit, font=f_unit) + gap if unit else 0
        while f.size > 8 * S and d.textlength(txt, font=f) + uw > _u(max_w):
            f = ImageFont.truetype(f.path, f.size - S)
            if unit:
                f_unit = ImageFont.truetype(f_unit.path, max(6 * S, round(f_unit.size * 0.97)))
                uw = d.textlength(unit, font=f_unit) + gap
    tw = d.textlength(txt, font=f)
    total = tw + (d.textlength(unit, font=f_unit) + gap if unit else 0)
    x0 = x if anchor == "l" else x - total / 2 if anchor == "m" else x - total
    _text(img, (x0, base), txt, f, cols, "ls")
    if unit:
        top = d.textbbox((x0, base), "0", font=f, anchor="ls")[1]
        ub = d.textbbox((0, 0), unit, font=f_unit, anchor="ls")
        _text(img, (x0 + tw + gap, top - ub[1]), unit, f_unit, ucols or cols, "ls")
    return x0 + total


def _label(img, x, base, text, weight, px, col, anchor="ls", max_w=None):
    d = ImageDraw.Draw(img)
    f = _f(weight, px)
    if max_w:
        f = _shrink(d, text, f, _u(max_w))
    _text(img, (_u(x), _u(base)), text, f, (col, col), anchor)


def _rbar(img, x, y, w, h, frac, cols, track=TRACK):
    """Zakulaceny bar s prechodem (souradnice navrhu)."""
    x, y, w, h = _u(x), _u(y), _u(w), _u(h)
    if PLASTIC:                                      # drazka kolem baru, vypln v puvodni velikosti
        g = _bar_rim(h)
        return _bar3d(img, (x - g, y - g, x + w + g, y + h + g), h // 2 + g, frac, cols, base=track, inset=g)
    d = ImageDraw.Draw(img)
    r = h // 2
    d.rounded_rectangle((x, y, x + w, y + h), r, fill=track)
    if frac > 0:
        fw = max(h, int(w * frac))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((x, y, x + fw, y + h), r, fill=255)
        _paint(img, mask, _hgrad(w, h + 1, *cols), (x, y))


def _segbar(img, x, y, w, h, n, lit, cols, gap=4, radius=4):
    d = ImageDraw.Draw(img)
    sw = (w - gap * (n - 1)) / n
    if PLASTIC:                                      # kosticky v zapustene vanicce
        p = 4
        _groove_rect(img, (_u(x - p), _u(y - p), _u(x + w + p), _u(y + h + p)), _u(radius + 4))
        boxes = [(_u(x + i * (sw + gap)), _u(y), _u(x + i * (sw + gap) + sw), _u(y + h),
                  mix(*cols, i / max(1, n - 1)) if i < lit else None) for i in range(n)]
        _segments3d(img, boxes, cols, _u(radius), bar_box=(_u(x), _u(y), _u(x + w), _u(y + h)))
        return
    for i in range(n):
        x0 = x + i * (sw + gap)
        col = mix(*cols, i / max(1, n - 1)) if i < lit else OFF
        d.rounded_rectangle((_u(x0), _u(y), _u(x0 + sw), _u(y + h)), _u(radius), fill=col)


def _panel(img, x, y, w, h, r):
    if PLASTIC:
        return _raised(img, (_u(x), _u(y), _u(x + w), _u(y + h)), _u(r), PANEL)
    ImageDraw.Draw(img).rounded_rectangle((_u(x), _u(y), _u(x + w), _u(y + h)), _u(r), fill=PANEL)


def _hist(scr, key, data_hist, div_key="delitel"):
    div = float(scr.get(div_key, 1) or 1)
    return [v / div for v in (data_hist or {}).get(scr.get(key), [])]


def _area_chart(img, x, y, w, h, vals, lo, hi, cols, line_w=5, line_col=None, dot=None):
    """Plocha grafu pres oblast (souradnice navrhu): plocha od barvy 'do' nahore k 'od' dole
    (sila 140 -> 12), cara v prechodu od -> do (nebo line_col)."""
    if len(vals) < 2:
        return None
    if PLASTIC:
        return _ribbon_chart(img, x, y, w, h, vals, lo, hi, cols, line_col)
    X0, Y0, Wd, Hd = _u(x), _u(y), _u(w), _u(h)
    n = len(vals)
    pad = _u(line_w)
    right = Wd - (_u(dot) + _u(line_w) if dot else 0)          # tecka na konci se vejde na displej
    pts = [(X0 + right * i / (n - 1), Y0 + Hd - pad - (Hd - 2 * pad) * _frac(v, lo, hi)) for i, v in enumerate(vals)]
    area = Image.new("L", img.size, 0)
    ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], Y0 + Hd), (X0, Y0 + Hd)], fill=255)
    fade = Image.new("L", img.size, 0)
    fd = ImageDraw.Draw(fade)
    for yy in range(Y0, Y0 + Hd + 1):
        fd.line((X0, yy, X0 + Wd, yy), fill=round(140 - 128 * (yy - Y0) / max(1, Hd)))
    _paint(img, ImageChops.multiply(area, fade), _vgrad(Wd, Hd + 1, cols[0], cols[1]), (X0, Y0))
    line = Image.new("L", img.size, 0)
    ImageDraw.Draw(line).line(pts, fill=255, width=_u(line_w), joint="curve")
    fill = Image.new("RGB", (Wd + 1, Hd + 1), line_col) if line_col else _hgrad(Wd + 1, Hd + 1, *cols)
    _paint(img, line, fill, (X0, Y0))
    if dot:
        ex, ey = pts[-1]
        r = _u(dot)
        ImageDraw.Draw(img).ellipse((ex - r, ey - r, ex + r, ey + r), fill=WHITE)
    return pts


def _ribbon_chart(img, x, y, w, h, vals, lo, hi, cols, line_col=None, depth=14):
    """Plasticky graf v souradnicich navrhu 480 (viz ribbon3d)."""
    return ribbon3d(img, _u(x), _u(y), _u(w), _u(h), vals, lo, hi, cols, line_col, _u(depth))


def ribbon3d(img, X0, Y0, Wd, Hd, vals, lo, hi, cols, line_col=None, T=None):
    """Plasticky graf: pasek vytlaceny do hloubky T (zadni hrana vpravo nahore), horni plocha
    z ctyruhelniku se svetlosti podle sklonu, predni stena s prechodem, kulicka na konci.
    Souradnice platna (3x)."""
    if len(vals) < 2:
        return None
    T = T or max(3 * S, min(Wd, Hd) * 0.07)
    dx, dy = T * 0.9, -T * 0.65
    n = len(vals)
    m = max(S, T * 0.35)                                 # okraj pro caru a kulicku
    pad = m - dy
    right = Wd - dx - T * 0.6
    pts = [(X0 + right * i / (n - 1), Y0 + Hd - m - (Hd - pad - m) * _frac(v, lo, hi)) for i, v in enumerate(vals)]
    top_col = line_col or cols[1]
    lw = max(S, T * 0.2)
    # zare pod hranou
    gl = Image.new("RGB", img.size, BLACK)
    gm = Image.new("L", img.size, 0)
    ImageDraw.Draw(gl).line(pts, fill=top_col, width=int(lw * 3), joint="curve")
    ImageDraw.Draw(gm).line(pts, fill=255, width=int(lw * 3), joint="curve")
    _glow(img, gl, gm, lw * 2.5, 0.5)
    d = ImageDraw.Draw(img)
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):         # horni plocha pasku
        slope = (yb - ya) / max(1, xb - xa)
        t = max(0.0, min(1.0, 0.5 + slope * 0.9))
        base = mix(cols[0], top_col, 1 - ((ya + yb) / 2 - Y0) / max(1, Hd))
        c = _lerp(base, WHITE, (0.5 - t)) if t < 0.5 else _dim(base, 1 - 0.55 * (t - 0.5) * 2)
        quad = [(xa, ya), (xb, yb), (xb + dx, yb + dy), (xa + dx, ya + dy)]
        d.polygon(quad, fill=c, outline=c)
    face = Image.new("L", img.size, 0)
    ImageDraw.Draw(face).polygon(pts + [(pts[-1][0], Y0 + Hd), (pts[0][0], Y0 + Hd)], fill=255)
    stops = [(0, _dim(top_col, 0.75)), (0.5, _dim(cols[0], 0.3)), (1, (5, 6, 8))]
    _paint(img, face, _grad(Wd, Hd + 1, stops), (int(X0), int(Y0)))
    d.line(pts, fill=_lerp(top_col, WHITE, 0.55), width=int(lw), joint="curve")
    d.line([(px + dx, py + dy) for px, py in pts], fill=_lerp(top_col, WHITE, 0.25), width=int(lw * 0.67),
           joint="curve")
    ex, ey = pts[-1]
    _dome(img, ex + dx / 2, ey + dy / 2, T * 0.7, _lerp(top_col, WHITE, 0.2))
    return pts


# 1 ------------------------------------------------------------ ctyri dlazdice
def draw_tiles(scr, data, template=False, history=None):
    img = _canvas()
    tcols = colors(scr, "text")
    for n, (x, y) in zip("1234", ((8, 8), (244, 8), (8, 244), (244, 244))):
        _panel(img, x, y, 228, 228, 22)
        cols = colors(scr, "dlazdice" + n)
        _label(img, x + 22, y + 43, scr.get("nadpis" + n, ""), "ExtraBold", 22, cols[0], max_w=184)
        txt, frac, unit, _v = _slot(scr, n, data)
        _num(img, x + 22, y + 154, txt, _f("ExtraBold", 96 if len(txt) <= 3 else 72), tcols,
             unit, _f("Bold", 30), max_w=184, gap=2)
        _rbar(img, x + 22, y + 192, 184, 12, frac, cols)
    return img


# 2 ------------------------------------------------------------ CPU detail
def draw_cpu_detail(scr, data, template=False, history=None):
    img = _canvas()
    tcols = colors(scr, "text")
    ak = colors(scr, "akcent")
    _label(img, 28, 53, scr.get("nadpis", ""), "ExtraBold", 30, ak[0], max_w=290)
    _label(img, 28, 79, scr.get("podnadpis", ""), "SemiBold", 18, MUTED, max_w=290)
    txt, _fr, unit, _v = _slot(scr, "", data)
    _num(img, 18, 240, txt, _f("ExtraBold", 200), tcols, _short_unit(unit),
         _f("Bold", 56 if unit in DEGREE_UNITS else 36), max_w=300, gap=2)
    for i, n in enumerate("123"):
        if not scr.get("senzor" + n) and not scr.get("popisek" + n):
            continue
        t, _f2, _u2, _v2 = _slot(scr, n, data)
        base = 68 + i * 77.5
        _label(img, 330, base, t, "ExtraBold", 40, WHITE, max_w=130)
        _label(img, 330, base + 22, scr.get("popisek" + n, ""), "SemiBold", 16, MUTED, max_w=140)
    d = ImageDraw.Draw(img)
    for yy in (345, 390, 435):
        if PLASTIC:
            _engraved(d, 0, _u(yy), W, _u(2))
        else:
            d.line((0, _u(yy), W, _u(yy)), fill=TRACK, width=_u(2))
    vals = _hist(scr, "senzor", history)
    _area_chart(img, 0, 300, 480, 180, vals, float(scr.get("min", 0)), float(scr.get("max", 100)), ak)
    _label(img, 452, 462, _span_text(scr), "Bold", 16, MUTED, "rs")
    return img


def _span_text(scr):
    secs = int(scr.get("delka_s", 120))
    return f"{secs // 60} min" if secs >= 60 else f"{secs} s"


# 3 ------------------------------------------------------------ chlazeni v radcich
def draw_cooling_rows(scr, data, template=False, history=None):
    img = _canvas()
    tcols = colors(scr, "text")
    kc, kp, kv = colors(scr, "kapalina"), colors(scr, "pumpa"), colors(scr, "ventilatory")
    g = lambda k: value_for(k, data)
    lq, pd, pr, fd, fr = g("@kapalina"), g("@pumpa_vykon"), g("@pumpa"), g("@ventilatory_vykon"), g("@ventilatory")
    lo, hi = float(scr.get("min", 20)), float(scr.get("max", 60))
    _label(img, 28, 51, "KAPALINA", "ExtraBold", 24, kc[0])
    _num(img, 22, 179, _fmt(lq, 1), _f("ExtraBold", 150), tcols, "°C", _f("Bold", 44), max_w=430, gap=2)
    _segbar(img, 28, 222, 424, 18, 20, round(_frac(lq, lo, hi) * 20), kc)
    _label(img, 28, 263, f"{lo:g} °C", "SemiBold", 15, MUTED)
    _label(img, 452, 263, "59 °C = 100 %", "Bold", 15, (255, 107, 107), "rs")
    for top, lbl, duty, rpm, cols in ((292, "PUMPA", pd, pr, kp), (384, "VENTILÁTORY", fd, fr, kv)):
        base = top + 38
        _label(img, 28, base, lbl, "ExtraBold", 22, cols[0])
        _num(img, 452, base, f"{_fmt(duty, 0)} %", _f("ExtraBold", 44), tcols, anchor="r")
        d = ImageDraw.Draw(img)
        vw = d.textlength(f"{_fmt(duty, 0)} %", font=_f("ExtraBold", 44))
        if rpm is not None:
            _text(img, (_u(452) - vw - _u(12), _u(base)), f"{rpm:.0f} ot/min", _f("SemiBold", 18), (MUTED, MUTED), "rs")
        _rbar(img, 28, top + 54, 424, 14, _frac(duty, 0, 100), cols)
    return img


# 4 ------------------------------------------------------------ hodiny a stav
def draw_clock_status(scr, data, template=False, history=None):
    now = datetime.now()
    img = _canvas()
    d = ImageDraw.Draw(img)
    hc = colors(scr, "hodiny")
    txt = f"{now.hour:02d}:{now.minute:02d}"
    f = _shrink(d, txt, _f("ExtraBold", 170), _u(440))
    _text(img, (W // 2, _u(182)), txt, f, hc, "ms")
    _rbar(img, 28, 232, 424, 8, now.second / 59, hc)
    if scr.get("datum", True):
        _label(img, 240, 291, f"{DAYS[now.weekday()]} {now.day}. {MONTHS[now.month - 1]}", "SemiBold", 30,
               (207, 214, 222), "ms", max_w=440)
    tcols = colors(scr, "text")
    for n, x in zip("123", (28, 172, 316)):
        _panel(img, x, 340, 136, 112, 18)
        c = colors(scr, "stav" + n)[0]
        _label(img, x + 16, 371, scr.get("nadpis" + n, ""), "ExtraBold", 16, c, max_w=104)
        t, _fr, unit, _v = _slot(scr, n, data)
        su = _short_unit(unit)
        _num(img, x + 16, 429, t + (su if su == "°" else ""), _f("ExtraBold", 50), tcols,
             "" if su == "°" else su, _f("Bold", 20), max_w=104, gap=2)
    return img


# 5 ------------------------------------------------------------ graf pres celou plochu
def draw_graph_full(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    gc = colors(scr, "graf")
    lo, hi = float(scr.get("min", 0)), float(scr.get("max", 100))
    for yy in (224, 320, 416):                               # carkovane linky
        if PLASTIC:
            _engraved(d, 0, _u(yy), W, _u(2))
            continue
        for xx in range(0, 480, 14):
            d.line((_u(xx), _u(yy), _u(xx + 6), _u(yy)), fill=(35, 38, 44), width=_u(2))
    vals = _hist(scr, "senzor", history)
    _area_chart(img, 0, 160, 480, 320, vals, lo, hi, gc, line_col=gc[1], dot=9)
    _label(img, 28, 51, scr.get("nadpis", ""), "ExtraBold", 26, gc[0], max_w=260)
    txt, _fr, unit, _v = _slot(scr, "", data)
    _num(img, 22, 155, txt, _f("ExtraBold", 120), tcols, unit, _f("Bold", 40), max_w=270, gap=2)
    if len(vals) >= 2:
        su = _short_unit(unit)
        dec = scr.get("desetinna", 0)
        for base, word, v in ((51, "max ", max(vals)), (82, "min ", min(vals))):
            s = f"{_fmt(v, dec)}{su}"
            f = _f("Bold", 22)
            _text(img, (_u(452), _u(base)), s, f, tcols, "rs")
            _text(img, (_u(452) - d.textlength(s, font=f), _u(base)), word, _f("SemiBold", 22), (MUTED, MUTED), "rs")
    _label(img, 452, 107, "posledních " + _span_text(scr), "Bold", 16, MUTED, "rs")
    return img


# 6 ------------------------------------------------------------ sit a disky
def _arrow(d, cx, cy, down, col):
    k = 40 / 24                                             # ikona 24x24 zvetsena na 40
    def p(x, y):
        return (_u(cx - 20 + x * k), _u(cy - 20 + y * k))
    w = _u(3 * k)
    pts = [(12, 4), (12, 20)] if down else [(12, 20), (12, 4)]
    head = [(5, 13), (12, 20), (19, 13)] if down else [(5, 11), (12, 4), (19, 11)]
    d.line([p(*pts[0]), p(*pts[1])], fill=col, width=w)
    d.line([p(*q) for q in head], fill=col, width=w, joint="curve")
    for q in (pts[0], head[0], head[2]):
        x, y = p(*q)
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)


def draw_net_disks(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    sc, dc = colors(scr, "sit"), colors(scr, "disky")
    _label(img, 28, 43, "SÍŤ", "ExtraBold", 22, sc[0])
    dec = scr.get("desetinna", 1)
    for key, cy, down, col in (("senzor_dolu", 88, True, sc[0]), ("senzor_nahoru", 166, False, sc[1])):
        v = value_for(scr.get(key), data)
        if PLASTIC:                                         # sipka na vypouklem kulatem odznaku
            _dome(img, _u(42), _u(cy), _u(25), col, light=0.5, dark=0.5)
            _arrow(d, 42, cy, down, _dim(col, 0.12))
        else:
            _arrow(d, 42, cy, down, col)
        end = _num(img, 72, cy + 21, _fmt(v, dec), _f("ExtraBold", 60), tcols, max_w=230)
        _text(img, (end + _u(10), _u(cy + 21)), "MB/s", _f("Bold", 20), (MUTED, MUTED), "ls")
        vals = (history or {}).get(scr.get(key), [])[-60:]
        if len(vals) >= 2:
            top = max(max(vals), 0.1)
            x0, y0, w, h = _u(318), _u(cy - 28), _u(134), _u(56)
            pts = [(x0 + w * i / (len(vals) - 1), y0 + h - h * min(1.0, v2 / top)) for i, v2 in enumerate(vals)]
            if PLASTIC:
                _line3d(img, pts, _u(4), col, side=_dim(col, 0.4))
            else:
                d.line(pts, fill=col, width=_u(4), joint="curve")
    if PLASTIC:
        _engraved(d, _u(28), _u(224), _u(452), _u(2))
    else:
        d.line((_u(28), _u(225), _u(452), _u(225)), fill=TRACK, width=_u(2))
    _label(img, 28, 265, "DISKY", "ExtraBold", 22, dc[0])
    for n, top in (("1", 290), ("2", 378)):
        letter = (scr.get("disk" + n) or "").strip()
        if not letter:
            continue
        free = value_for(f"@disk {letter} volno", data)
        used = value_for(f"@disk {letter} obsazeno", data)
        temp = value_for(f"Teplota disku ({letter})", data)
        _label(img, 28, top + 39, letter, "ExtraBold", 40, WHITE)
        _rbar(img, 102, top + 2, 350, 14, _frac(used, 0, 100), dc)
        info = f"{_fmt(free, 0)} GB volno" + ("" if temp is None else f" · {temp:.0f} °C")
        _label(img, 102, top + 41, info, "SemiBold", 18, MUTED, max_w=350)
    return img


# 7 ------------------------------------------------------------ GPU sloupce
def _gpu_name(scr, data):
    import re
    if scr.get("podnadpis"):
        return scr["podnadpis"]
    dev = (data.get(scr.get("senzor1")) or {}).get("sensor", "")
    m = re.search(r"((?:GeForce\s+)?(?:RTX|GTX|RX|Arc)\s*[A-Z]?\d{3,4}\w*(?:\s+(?:Ti|Super|XT|XTX))?)", dev)
    return m.group(1) if m else ""


GLASS = [(0, (42, 48, 56)), (0.3, (20, 23, 28)), (0.75, (9, 10, 13)), (1, (26, 30, 36))]


def _cylinder(img, x, top, bottom, frac, cols, w=94, ry=12):
    """Sklenený valec s kapalinou (souradnice navrhu): hladina = elipsa, plast stinovany jako valec."""
    cylinder3d(img, _u(x), _u(top), _u(x + w), _u(bottom), _u(ry), frac, cols)


def cylinder3d(img, X0, T, X1, B, RY, frac, cols):
    """Skleneny valec s kapalinou (souradnice platna): T/B = stredy horni a dolni elipsy, RY = jeji
    polovysky; hladina = elipsa, plast stinovany jako valec, odlesk skla."""
    d = ImageDraw.Draw(img)
    X0, X1, T, B, RY = int(X0), int(X1), int(T), int(B), max(1, int(RY))
    w = X1 - X0
    _paint(img, _rect_mask(img, (X0, T, X1, B)), _grad(X1 - X0, B - T, GLASS, vertical=False), (X0, T))
    d.ellipse((X0, B - RY, X1, B + RY), fill=(14, 16, 20))                  # dno skla
    d.ellipse((X0, T - RY, X1, T + RY), fill=(5, 6, 7))                     # vnitrek horniho okraje
    if frac > 0:
        L = B - (B - T) * frac
        mask = _rect_mask(img, (X0, L, X1, B))
        ImageDraw.Draw(mask).ellipse((X0, B - RY, X1, B + RY), fill=255)
        layer = Image.new("RGB", img.size, BLACK)
        layer.paste(_vgrad(X1 - X0, B + RY - T + 1, cols[0], cols[1]), (X0, T))
        _shape(img, layer, mask, (X0, T, X1, B + RY), across=True, shade=CYLINDER, glow_r=w * 0.13)
        d.ellipse((X0, L - RY, X1, L + RY), fill=_lerp(cols[1], WHITE, 0.3), outline=_lerp(cols[1], WHITE, 0.65),
                  width=max(1, int(w * 0.021)))
    hl = _rect_mask(img, (X0 + w * 0.19, T + RY, X0 + w * 0.29, B - RY * 0.2), r=int(w * 0.048))
    _tint(img, hl, WHITE, 0.16)                                             # odlesk skla
    edge = max(1, int(w * 0.027))
    d.ellipse((X0, T - RY, X1, T + RY), outline=(86, 96, 107), width=edge)
    d.arc((X0, B - RY, X1, B + RY), 0, 180, fill=(58, 66, 76), width=edge)


def _rect_mask(img, box, r=0):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle(tuple(int(v) for v in box), r, fill=255)
    return m


def draw_gpu_columns(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    tcols = colors(scr, "text")
    cols = colors(scr, "sloupce")
    _label(img, 28, 53, scr.get("nadpis", "GPU"), "ExtraBold", 30, colors(scr, "nadpis")[0], max_w=90)
    _label(img, 120, 52, _gpu_name(scr, data), "SemiBold", 18, MUTED, max_w=332)
    for i, n in enumerate("1234"):
        x = 28 + i * 110
        X0, Y0, X1, Y1 = _u(x), _u(84), _u(x + 94), _u(354)
        t, frac, unit, _v = _slot(scr, n, data)
        if PLASTIC:
            _cylinder(img, x, 96, 342, frac, cols)
        else:
            d.rounded_rectangle((X0, Y0, X1, Y1), _u(16), fill=(18, 20, 24))
        if frac > 0 and not PLASTIC:
            fh = max(_u(32), int((Y1 - Y0) * frac))
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((X0, Y1 - fh, X1, Y1), _u(16), fill=255)
            _paint(img, mask, _vgrad(X1 - X0 + 1, Y1 - Y0 + 1, cols[0], cols[1]), (X0, Y0))
        su = _short_unit(unit)
        t = t + ("°" if su == "°" else " %" if su == "%" else "")
        _label(img, x + 47, 390, t, "ExtraBold", 30, tcols[0], "ms", max_w=104)
        _label(img, x + 47, 418, scr.get("nadpis" + n, ""), "Bold", 15, MUTED, "ms", max_w=104)
    return img


# 8 ------------------------------------------------------------ jedno velke cislo
def draw_big_number(scr, data, template=False, history=None):
    img = _canvas()
    tcols = colors(scr, "text")
    cols = colors(scr, "segmenty")
    _label(img, 32, 61, scr.get("nadpis", ""), "ExtraBold", 34, cols[0], max_w=260)
    _label(img, 448, 57, scr.get("popisek", ""), "Bold", 20, MUTED, "rs", max_w=180)
    txt, frac, unit, _v = _slot(scr, "", data)
    _num(img, 14, 310, txt, _f("ExtraBold", 300), tcols, unit, _f("Bold", 60), max_w=452, gap=10)
    _segbar(img, 32, 392, 416, 48, 24, round(frac * 24), cols)
    lo, hi = float(scr.get("min", 0)), float(scr.get("max", 100))
    _label(img, 32, 462, f"{lo:g}", "Bold", 15, MUTED)
    _label(img, 448, 462, f"{hi:g}", "Bold", 15, MUTED, "rs")
    return img


def _glass(img, vessel, c, R, level):
    """Skleněná koule nad hladinou: lesk hladiny, bublinky, stin k okraji, odlesky (navrh 480)."""
    d = ImageDraw.Draw(img)
    menisc = Image.new("L", img.size, 0)
    ImageDraw.Draw(menisc).line([(_u(x), _u(level + 9 * math.sin(x / 38))) for x in range(0, 481, 6)],
                                fill=255, width=_u(4))
    _tint(img, ImageChops.multiply(menisc, vessel), WHITE, 0.55)
    for bx, by, br in ((150, 360, 7), (176, 410, 4), (300, 330, 9), (322, 392, 5), (260, 430, 6), (210, 300, 3.5),
                       (356, 300, 4)):
        if by - br > level + 12:
            b = Image.new("L", img.size, 0)
            ImageDraw.Draw(b).ellipse((_u(bx - br), _u(by - br), _u(bx + br), _u(by + br)), outline=255,
                                      width=max(S, _u(1.5)))
            _tint(img, ImageChops.multiply(b, vessel), WHITE, 0.4)
            hx, hy, hr = _u(bx - br * 0.35), _u(by - br * 0.35), max(S, _u(br * 0.3))
            d.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=_lerp(img.getpixel((int(hx), int(hy))), WHITE, 0.8))

    def sphere():                                       # tmavnuti k okraji koule
        im = Image.new("L", img.size, 0)
        sd = ImageDraw.Draw(im)
        cx, cy = c - R * 0.16, c - R * 0.24
        for i in range(40, -1, -1):
            t = i / 40
            rr = R * 1.25 * t
            sd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=int(255 * _interp([(0, 0), (0.62, 0.12), (1, 0.8)], t)))
        return ImageChops.multiply(im, vessel)
    _tint(img, _cached(("sphere", c, R), sphere), BLACK)

    def spot(rx, ry, peak):                             # mekky odlesk natoceny o 32 stupnu
        im = Image.new("L", (int(2 * rx), int(2 * ry)), 0)
        sd = ImageDraw.Draw(im)
        for i in range(20):
            t = i / 19
            sd.ellipse((rx * t, ry * t, 2 * rx - rx * t, 2 * ry - ry * t), fill=int(255 * peak * t ** 1.5))
        return im.rotate(32, resample=Image.BICUBIC, expand=True)
    for (cx, cy, rx, ry, peak) in ((170, 120, 92, 52, 0.55), (146, 104, 22, 11, 0.8)):
        s = _cached(("spot", rx, ry, peak), lambda: spot(_u(rx), _u(ry), peak))
        full = Image.new("L", img.size, 0)
        full.paste(s, (int(_u(cx) - s.width / 2), int(_u(cy) - s.height / 2)))
        _tint(img, ImageChops.multiply(full, vessel), WHITE)
    caustic = Image.new("L", img.size, 0)
    ImageDraw.Draw(caustic).arc((_u(70), _u(70), _u(410), _u(410)), 40, 140, fill=255, width=_u(5))
    _tint(img, caustic, WHITE, 0.14)
    d.ellipse((c - R, c - R, c + R, c + R), outline=(0, 0, 0), width=_u(3))


# 11 ----------------------------------------------------------- kapalina jako hladina
def draw_level(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    cols = colors(scr, "voda")
    c = W // 2
    R = _u(208 if PLASTIC else 206)
    if PLASTIC:                                         # kovova obruc a dno skleněné koule
        _metal_ring(img, c, c, _u(230), _u(16))
        d.ellipse((c - _u(214), c - _u(214), c + _u(214), c + _u(214)), fill=(1, 1, 1))
        _disc(img, c, c, R, (13, 20, 24), (2, 3, 4))
    else:
        d.ellipse((c - R, c - R, c + R, c + R), fill=(7, 11, 14))
    txt, frac, unit, v = _slot(scr, "", data)
    level = 480 - (34 + 412 * frac)
    vessel = Image.new("L", img.size, 0)
    ImageDraw.Draw(vessel).ellipse((c - R, c - R, c + R, c + R), fill=255)
    for amp, ph, alpha, grad in ((12, 1.8, 90, False), (9, 0.0, 255, True)):
        pts = [(_u(x), _u(level + amp * math.sin(x / 38 + ph))) for x in range(0, 481, 6)]
        wave = Image.new("L", img.size, 0)
        ImageDraw.Draw(wave).polygon(pts + [(W, W), (0, W)], fill=alpha)
        fill = _vgrad(W, W, cols[1], cols[0]) if grad else Image.new("RGB", (W, W), cols[0])
        if PLASTIC and grad:
            fill = _grad(W, W, [(0, _lerp(cols[0], WHITE, 0.35)), (level / 480 + 0.05, cols[0]), (1, cols[1])])
        _paint(img, ImageChops.multiply(wave, vessel), fill)
    if PLASTIC:
        _glass(img, vessel, c, R, level)
    else:
        Ro = _u(220)
        d.ellipse((c - Ro, c - Ro, c + Ro, c + Ro), outline=(22, 37, 45), width=_u(12))
    _label(img, 240, 119, scr.get("nadpis", ""), "ExtraBold", 24, (191, 239, 255), "ms", max_w=300)
    _num(img, 240, 248, txt, _f("ExtraBold", 130), colors(scr, "text"), _short_unit(unit),
         _f("Bold", 40), anchor="m", max_w=380, gap=2)
    if scr.get("senzor") == "@kapalina":
        pd, pr = value_for("@pumpa_vykon", data), value_for("@pumpa", data)
        if pd is not None:
            line = f"pumpa {pd:.0f} %" + ("" if pr is None else f" · {pr:.0f} ot/min")
            _label(img, 240, 337, line, "Bold", 22, (230, 251, 255), "ms", max_w=340)
    return img


def _disc_mask(img, cx, cy, r):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return m


def _rays3d(img, rays, w):
    """Paprsky jako vypoukle tycinky: zare, stin vpravo dole, lesk vlevo nahore (pevny smer svetla)."""
    def stroke(dd, seg, col, width, dx=0.0, dy=0.0):
        x1, y1, x2, y2 = seg[0] + dx, seg[1] + dy, seg[2] + dx, seg[3] + dy
        dd.line((x1, y1, x2, y2), fill=col, width=max(1, int(width)))
        for x, y in ((x1, y1), (x2, y2)):
            dd.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=col)
    layer = Image.new("RGB", img.size, BLACK)
    mask = Image.new("L", img.size, 0)
    ld, md = ImageDraw.Draw(layer), ImageDraw.Draw(mask)
    for seg, col in rays:
        if col != OFF:
            stroke(ld, seg, col, w)
            stroke(md, seg, 255, w)
    _glow(img, layer, mask, w * 0.6, 0.5)
    d = ImageDraw.Draw(img)
    k = w / 10
    for seg, col in rays:
        stroke(d, seg, _dim(col, 0.4), w, 2.5 * k, 3.5 * k)
        stroke(d, seg, col, w * 0.92)
        if col != OFF:
            stroke(d, seg, _lerp(col, WHITE, 0.6), w * 0.27, -2 * k, -2.2 * k)


# 12 ----------------------------------------------------------- graf dokola
def draw_radial(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    cols = colors(scr, "paprsky")
    lo, hi = float(scr.get("min", 0)), float(scr.get("max", 100))
    c = W // 2
    r0 = _u(128)
    d.ellipse((c - r0, c - r0, c + r0, c + r0), outline=(21, 24, 28), width=_u(2))
    vals = _hist(scr, "senzor", history)
    n = 60
    if vals:                                                   # prevzorkovat na 60 paprsku (nejnovejsi nahore vlevo od 12)
        step = max(1, len(vals) / n)
        vals = [vals[min(len(vals) - 1, int(i * step))] for i in range(min(n, len(vals)))]
        if len(vals) < n:
            vals = [None] * (n - len(vals)) + vals
    else:
        vals = [None] * n
    w = _u(10)
    rays = []
    for i, v in enumerate(vals):
        fr = 0.06 if v is None else max(0.06, _frac(v, lo, hi))
        a = math.radians(i * 6 - 90)
        r1, r2 = _u(146 if PLASTIC else 140), _u((146 if PLASTIC else 140) + 80 * fr)
        x1, y1, x2, y2 = c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)
        rays.append(((x1, y1, x2, y2), OFF if v is None else WHITE if i == n - 1 else mix(*cols, fr)))
    if PLASTIC:
        _rays3d(img, rays, w)
        _tint(img, _disc_mask(img, c + _u(4), c + _u(6), _u(120)), BLACK, 0.8)   # stin pod kotoucem
        _metal_ring(img, c, c, _u(120), _u(7))
        _disc(img, c, c, _u(113), (42, 48, 56), (6, 7, 8), dy=-0.2)
    else:
        for (x1, y1, x2, y2), col in rays:
            d.line((x1, y1, x2, y2), fill=col, width=w)
            for x, y in ((x1, y1), (x2, y2)):
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)
    _label(img, 240, 175, scr.get("nadpis", ""), "ExtraBold", 18, cols[0], "ms", max_w=200)
    txt, _fr, unit, _v = _slot(scr, "", data)
    _num(img, 240, 262, txt, _f("ExtraBold", 96), colors(scr, "text"), _short_unit(unit), _f("Bold", 34),
         anchor="m", max_w=220, gap=2)
    _label(img, 240, 290, "posledních " + _span_text(scr) + " dokola", "SemiBold", 15, MUTED, "ms", max_w=220)
    return img


def draw_free(scr, data, template=False, history=None):
    """Volne rozvrzeni: prvky z kraken_prvky.py (import az tady - kraken_prvky pouziva tento modul)."""
    import kraken_prvky
    return kraken_prvky.render(scr.get("prvky", []), data, history)


DRAW = {"dva_bary": draw_two_bars, "oblouk": draw_arc, "budik": draw_gauge,
        "dva_kruhy": draw_rings, "graf": draw_graph, "hodiny": draw_time,
        "dva_oblouky": draw_two_arcs, "segmenty": draw_segments, "ctyri_hodnoty": draw_four,
        "chlazeni": draw_cooling, "graf_dva": draw_graph_two, "hodiny_analog": draw_analog,
        "hodiny_datum": draw_clock_date, "hodiny_pod_sebou": draw_clock_date, "obrazek": draw_image,
        "dlazdice": draw_tiles, "cpu_detail": draw_cpu_detail, "chlazeni_radky": draw_cooling_rows,
        "hodiny_stav": draw_clock_status, "graf_plny": draw_graph_full, "sit_disky": draw_net_disks,
        "gpu_sloupce": draw_gpu_columns, "velke_cislo": draw_big_number, "hladina": draw_level,
        "graf_dokola": draw_radial, "volne": draw_free}


# ------------------------------------------------------- orez a zvetseni

_boxes = {}
_TEMPLATE_CHARS = (None, "0", "3", "6", "8", "9")   # None = nejsirsi cislice
FULL_FRAME = ("obrazek", "dlazdice", "cpu_detail", "chlazeni_radky", "hodiny_stav", "graf_plny",
              "sit_disky", "gpu_sloupce", "velke_cislo", "hladina", "graf_dokola", "volne")   # bez orezu na obsah


def _content_box(scr, data):
    """Vyrez = sjednoceni obsahu pro nejsirsi i nejvyssi (oble) cislice."""
    global _TCHAR
    if scr.get("typ") in FULL_FRAME:                  # obsah uz je rozvrzeny na cely displej
        return (0, 0, W, W)
    key = json.dumps(scr, sort_keys=True, ensure_ascii=False) + f"|{_TS}"
    if key not in _boxes:
        global PLASTIC
        box = None
        plastic = PLASTIC
        for ch in _TEMPLATE_CHARS:
            _TCHAR = ch
            PLASTIC = False                           # orez podle ploche geometrie: zare a luneta plasticke
            try:                                      # verze ho nezvetsi (obrazce zustanou stejne velke)
                big = DRAW[scr.get("typ", "hodiny")](scr, data, template=True)
            finally:
                _TCHAR = None
                PLASTIC = plastic
            bb = big.convert("L").point(lambda v: 255 if v > 8 else 0).getbbox()
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                              max(box[2], bb[2]), max(box[3], bb[3]))
        x0, y0, x1, y1 = box or (0, 0, W, W)
        pad = 3 * S
        _boxes[key] = (max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(W, y1 + pad))
    return _boxes[key]


def clear_cache():
    _boxes.clear()


def _fit(big, box, fill):
    if PLASTIC and box != (0, 0, W, W):
        # stejne meritko jako ploche, ale vyrez pres cely displej: zare, luneta a hloubka cisel
        # se vejdou do okraje kolem obsahu, misto aby obsah zmensily
        x0, y0, x1, y1 = box
        k = (SIZE * fill) / max(x1 - x0, y1 - y0)
        half = SIZE / k / 2
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return big.crop((round(cx - half), round(cy - half), round(cx + half), round(cy + half))).resize(
            (SIZE, SIZE), Image.LANCZOS)
    crop = big.crop(box)
    cw, ch = crop.size
    k = (SIZE * fill) / max(cw, ch)
    small = crop.resize((max(1, round(cw * k)), max(1, round(ch * k))), Image.LANCZOS)
    out = Image.new("RGB", (SIZE, SIZE), BLACK)
    out.paste(small, ((SIZE - small.width) // 2, (SIZE - small.height) // 2))
    return out


def render(scr, data, fill=0.92, gamma=0.65, text_scale=1.0, history=None, plastic=None, glow=None):
    """scr = popis obrazovky, data = {senzor: {"value", "unit"}}, history = {senzor: [hodnoty]},
    plastic = plasticky (3D) vzhled, glow = zare kolem tvaru (None = ponechat PLASTIC / GLOW)"""
    global _TS, PLASTIC, GLOW
    if glow is not None:
        GLOW = bool(glow)
    if plastic is not None and bool(plastic) != PLASTIC:
        PLASTIC = bool(plastic)
        _boxes.clear()                                   # orez se pocita z vykresleni
    fill = float(scr.get("velikost_obsahu", fill))
    _TS = float(scr.get("velikost_textu", text_scale) or 1.0)
    draw = DRAW.get(scr.get("typ"), draw_time)
    big = draw(scr, data, history=history)
    img = _fit(big, _content_box(scr, data), fill)
    if gamma and gamma != 1.0:
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        img = img.point(lut * 3)
    return img


# ------------------------------------------------ automaticke obrazovky

AUTO_RANGES = {"°C": (0, 100), "%": (0, 100), "MHz": (0, 6000), "RPM": (0, 3000),
               "W": (0, 300), "V": (0, 2), "GB": (0, 64), "MB": (0, 16384)}


def auto_screen(name, item, seen_max=None):
    unit = item.get("unit", "")
    lo, hi = AUTO_RANGES.get(unit, (0, max(1.0, (seen_max or item["value"]) * 1.2)))
    dec = 0 if abs(hi) >= 100 else 1
    return {"typ": "oblouk", "nadpis": name, "senzor": name, "min": lo, "max": hi,
            "jednotka": "auto", "delitel": 1, "desetinna_mista": dec, "zapnuto": True, "_auto": True}


def used_sensors(screens):
    out = set()
    for s in screens:
        for k, v in s.items():
            if k.startswith("senzor") and isinstance(v, str) and v:
                out.add(v)
        if s.get("typ") == "volne":
            import kraken_prvky
            for p in s.get("prvky", []):
                out.update(kraken_prvky.item_sensors(p))
    return out


# klice senzoru, ke kterym obrazovka potrebuje historii (graf)
HISTORY_KEYS = {"graf": ("senzor",), "graf_dva": ("senzor1", "senzor2"), "cpu_detail": ("senzor",),
                "graf_plny": ("senzor",), "graf_dokola": ("senzor",), "sit_disky": ("senzor_dolu", "senzor_nahoru")}


def history_spans(screens):
    """{senzor: delka historie v s} pro obrazovky s grafem."""
    out = {}
    for s in screens:
        keys = HISTORY_KEYS.get(s.get("typ"), ())
        for k in keys:
            if s.get(k):
                out[s[k]] = max(out.get(s[k], 0), float(s.get("delka_s", 120)))
        if s.get("typ") == "volne":
            import kraken_prvky
            for name, span in kraken_prvky.history_sensors(s.get("prvky", [])).items():
                out[name] = max(out.get(name, 0), span)
    return out


def build_list(cfg, data, seen_max=None):
    configured = cfg.get("obrazovky", [])
    out = [s for s in configured if s.get("zapnuto", True)]
    if cfg.get("auto_obrazovky", True):
        used = used_sensors(configured) | set(cfg.get("skryte_senzory", []))
        for name, item in data.items():
            if name.startswith("@") or name in used:
                continue
            scr = auto_screen(name, item, (seen_max or {}).get(name))
            scr["velikost_obsahu"] = cfg.get("velikost_obsahu", 0.92)
            scr["velikost_textu"] = cfg.get("velikost_textu", 1.0)
            out.append(scr)
    return out or [{"typ": "hodiny"}]
