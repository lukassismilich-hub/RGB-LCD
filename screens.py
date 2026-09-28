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
#
# Barvy: kazda barevna cast ma dve barvy <cast>_od a <cast>_do (prechod).
# Stejne barvy = jednobarevne. Prechod se pocita pres odstin (HSV),
# takze zelena -> cervena jde pres zlutou, ne pres hnedou.

import colorsys
import json
import math
import os
from datetime import datetime
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

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
         "velke_cislo": "Jedno velké číslo", "hladina": "Hladina (kruhová)", "graf_dokola": "Graf dokola (kruhový)"}

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
    _arc(img, c, r, 18 * S, start, span, frac, cols, dim_rest=0.28)

    # rysky
    for i in range(11):
        a = math.radians(start + span * i / 10)
        r1, r2 = r - 26 * S, r - (34 if i % 5 == 0 else 30) * S
        d.line((c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)),
               fill=GREY, width=3 * S if i % 5 == 0 else 2 * S)
    # rucicka
    a = math.radians(start + span * frac)
    ncols = colors(scr, "rucicka")
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
    d.rounded_rectangle((gx0, gy0, gx1, gy1), 8 * S, outline=DARK, width=2 * S)
    for i in (1, 2, 3):
        y = gy0 + (gy1 - gy0) * i / 4
        d.line((gx0 + 4 * S, y, gx1 - 4 * S, y), fill=(45, 45, 45), width=S)

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
        ImageDraw.Draw(img).line(pts, fill=BLACK, width=11 * S, joint="curve")
        line = Image.new("L", img.size, 0)
        ImageDraw.Draw(line).line(pts, fill=255, width=8 * S, joint="curve")
        _paint(img, line, lgrad, (gx0, gy0))
        ex, ey = pts[-1]
        col = mix(*light, 1 - (ey - gy0) / (gy1 - gy0))
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
    for i in range(n):
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
    d.rounded_rectangle((gx0, gy0, gx1, gy1), 8 * S, outline=DARK, width=2 * S)
    for i in (1, 2, 3):
        y = gy0 + (gy1 - gy0) * i / 4
        d.line((gx0 + 4 * S, y, gx1 - 4 * S, y), fill=(45, 45, 45), width=S)
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
            d.line(pts, fill=BLACK, width=10 * S, joint="curve")
            line = Image.new("L", img.size, 0)
            ImageDraw.Draw(line).line(pts, fill=255, width=6 * S, joint="curve")
            _paint(img, line, _vgrad(gx1 - gx0, gy1 - gy0, *cols), (gx0, gy0))
            ex, ey = pts[-1]
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
    d.ellipse((c - r, c - r, c + r, c + r), outline=_dim(dial, 0.55), width=3 * S)
    for i in range(60):
        a = math.radians(i * 6 - 90)
        big = i % 5 == 0
        r1, r2 = r - 8 * S, r - (24 if i % 15 == 0 else 18 if big else 12) * S
        d.line((c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)),
               fill=dial if big else _dim(dial, 0.5), width=(5 if i % 15 == 0 else 4 if big else 2) * S)
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
    _hand(d, c, h, 58 * S, 11 * S, hc, back=10 * S)
    _hand(d, c, m, 88 * S, 7 * S, hc, back=12 * S)
    _hand(d, c, now.second * 6, 96 * S, 3 * S, sc, back=22 * S)
    d.ellipse((c - 9 * S, c - 9 * S, c + 9 * S, c + 9 * S), fill=sc)
    d.ellipse((c - 3 * S, c - 3 * S, c + 3 * S, c + 3 * S), fill=BLACK)
    return img


def _seconds_ring(d, c, cols, second, template):
    """Prstenec ze 60 segmentu, rozsvicene do aktualni sekundy."""
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
    _seconds_ring(d, c, colors(scr, "sekundy"), now.second, template)
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
    for i in range(n):
        x0 = x + i * (sw + gap)
        col = mix(*cols, i / max(1, n - 1)) if i < lit else OFF
        d.rounded_rectangle((_u(x0), _u(y), _u(x0 + sw), _u(y + h)), _u(radius), fill=col)


def _panel(img, x, y, w, h, r):
    ImageDraw.Draw(img).rounded_rectangle((_u(x), _u(y), _u(x + w), _u(y + h)), _u(r), fill=PANEL)


def _hist(scr, key, data_hist, div_key="delitel"):
    div = float(scr.get(div_key, 1) or 1)
    return [v / div for v in (data_hist or {}).get(scr.get(key), [])]


def _area_chart(img, x, y, w, h, vals, lo, hi, cols, line_w=5, line_col=None, dot=None):
    """Plocha grafu pres oblast (souradnice navrhu): plocha od barvy 'do' nahore k 'od' dole
    (sila 140 -> 12), cara v prechodu od -> do (nebo line_col)."""
    if len(vals) < 2:
        return None
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
        _arrow(d, 42, cy, down, col)
        end = _num(img, 72, cy + 21, _fmt(v, dec), _f("ExtraBold", 60), tcols, max_w=230)
        _text(img, (end + _u(10), _u(cy + 21)), "MB/s", _f("Bold", 20), (MUTED, MUTED), "ls")
        vals = (history or {}).get(scr.get(key), [])[-60:]
        if len(vals) >= 2:
            top = max(max(vals), 0.1)
            x0, y0, w, h = _u(318), _u(cy - 28), _u(134), _u(56)
            pts = [(x0 + w * i / (len(vals) - 1), y0 + h - h * min(1.0, v2 / top)) for i, v2 in enumerate(vals)]
            d.line(pts, fill=col, width=_u(4), joint="curve")
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
        d.rounded_rectangle((X0, Y0, X1, Y1), _u(16), fill=(18, 20, 24))
        t, frac, unit, _v = _slot(scr, n, data)
        if frac > 0:
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


# 11 ----------------------------------------------------------- kapalina jako hladina
def draw_level(scr, data, template=False, history=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    cols = colors(scr, "voda")
    c = W // 2
    R = _u(206)
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
        _paint(img, ImageChops.multiply(wave, vessel), fill)
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
    for i, v in enumerate(vals):
        fr = 0.06 if v is None else max(0.06, _frac(v, lo, hi))
        a = math.radians(i * 6 - 90)
        r1, r2 = _u(140), _u(140 + 80 * fr)
        x1, y1, x2, y2 = c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)
        col = OFF if v is None else WHITE if i == n - 1 else mix(*cols, fr)
        d.line((x1, y1, x2, y2), fill=col, width=w)
        for x, y in ((x1, y1), (x2, y2)):
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)
    _label(img, 240, 175, scr.get("nadpis", ""), "ExtraBold", 18, cols[0], "ms", max_w=200)
    txt, _fr, unit, _v = _slot(scr, "", data)
    _num(img, 240, 262, txt, _f("ExtraBold", 96), colors(scr, "text"), _short_unit(unit), _f("Bold", 34),
         anchor="m", max_w=220, gap=2)
    _label(img, 240, 290, "posledních " + _span_text(scr) + " dokola", "SemiBold", 15, MUTED, "ms", max_w=220)
    return img


DRAW = {"dva_bary": draw_two_bars, "oblouk": draw_arc, "budik": draw_gauge,
        "dva_kruhy": draw_rings, "graf": draw_graph, "hodiny": draw_time,
        "dva_oblouky": draw_two_arcs, "segmenty": draw_segments, "ctyri_hodnoty": draw_four,
        "chlazeni": draw_cooling, "graf_dva": draw_graph_two, "hodiny_analog": draw_analog,
        "hodiny_datum": draw_clock_date, "hodiny_pod_sebou": draw_clock_date, "obrazek": draw_image,
        "dlazdice": draw_tiles, "cpu_detail": draw_cpu_detail, "chlazeni_radky": draw_cooling_rows,
        "hodiny_stav": draw_clock_status, "graf_plny": draw_graph_full, "sit_disky": draw_net_disks,
        "gpu_sloupce": draw_gpu_columns, "velke_cislo": draw_big_number, "hladina": draw_level,
        "graf_dokola": draw_radial}


# ------------------------------------------------------- orez a zvetseni

_boxes = {}
_TEMPLATE_CHARS = (None, "0", "3", "6", "8", "9")   # None = nejsirsi cislice
FULL_FRAME = ("obrazek", "dlazdice", "cpu_detail", "chlazeni_radky", "hodiny_stav", "graf_plny",
              "sit_disky", "gpu_sloupce", "velke_cislo", "hladina", "graf_dokola")   # bez orezu na obsah


def _content_box(scr, data):
    """Vyrez = sjednoceni obsahu pro nejsirsi i nejvyssi (oble) cislice."""
    global _TCHAR
    if scr.get("typ") in FULL_FRAME:                  # obsah uz je rozvrzeny na cely displej
        return (0, 0, W, W)
    key = json.dumps(scr, sort_keys=True, ensure_ascii=False) + f"|{_TS}"
    if key not in _boxes:
        box = None
        for ch in _TEMPLATE_CHARS:
            _TCHAR = ch
            try:
                big = DRAW[scr.get("typ", "hodiny")](scr, data, template=True)
            finally:
                _TCHAR = None
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
    crop = big.crop(box)
    cw, ch = crop.size
    k = (SIZE * fill) / max(cw, ch)
    small = crop.resize((max(1, round(cw * k)), max(1, round(ch * k))), Image.LANCZOS)
    out = Image.new("RGB", (SIZE, SIZE), BLACK)
    out.paste(small, ((SIZE - small.width) // 2, (SIZE - small.height) // 2))
    return out


def render(scr, data, fill=0.92, gamma=0.65, text_scale=1.0, history=None):
    """scr = popis obrazovky, data = {senzor: {"value", "unit"}}, history = {senzor: [hodnoty]}"""
    global _TS
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
