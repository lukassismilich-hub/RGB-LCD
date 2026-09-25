# mono.py - vykresleni prehledu pro monochromaticky Alphacool USB display (240x128, 1 bit)
#
# Jeden pevny prehled:
#   zahlavi   - hodiny a datum (inverzni pruh)
#   3 radky   - popisek, hodnota, bar, druha hodnota vpravo (napr. takt)
#   graf      - prubeh jedne hodnoty v case (cara + srafovana plocha)
#
# Kresli se primo v rezimu "1" (bez vyhlazovani - na monochromu sede odstiny nejsou).
# Bit 1 = rozsviceny bod (na modrem displeji bily).

import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 240, 128
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
MISSING = "–"

_fonts = {}


def _font(weight, px):
    k = (weight, px)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(os.path.join(FONTS, f"Montserrat-{weight}.ttf"), px)
    return _fonts[k]


def _value(data, sensor, divisor):
    item = data.get(sensor) if sensor else None
    if item is None:
        return None
    try:
        return item["value"] / (float(divisor) or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _unit(data, sensor, unit):
    if unit == "auto":
        return (data.get(sensor) or {}).get("unit", "")
    return unit or ""


def _fmt(v, decimals, unit):
    if v is None:
        return MISSING
    return f"{v:.{int(decimals)}f}{unit}"


def _frac(v, lo, hi):
    if v is None or hi == lo:
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _text_right(d, x_right, y_mid, text, font, fill=1):
    d.text((x_right, y_mid), text, font=font, fill=fill, anchor="rm")


def _header(d, now):
    d.rectangle((0, 0, WIDTH - 1, 14), fill=1)
    f = _font("Bold", 12)
    d.text((3, 7), now.strftime("%H:%M:%S"), font=f, fill=0, anchor="lm")
    _text_right(d, WIDTH - 3, 7, now.strftime("%d.%m.%Y"), f, fill=0)


def _row(d, y, row, data):
    """Radek: popisek | hodnota | bar | druha hodnota. y = svisly stred radku."""
    f_lbl = _font("ExtraBold", 12)
    f_val = _font("Bold", 12)
    d.text((2, y), row.get("popisek", ""), font=f_lbl, fill=1, anchor="lm")

    v1 = _value(data, row.get("senzor"), row.get("delitel", 1))
    u1 = _unit(data, row.get("senzor"), row.get("jednotka", "auto"))
    _text_right(d, 84, y, _fmt(v1, row.get("desetinna_mista", 0), u1), f_val)

    has2 = bool(row.get("senzor2"))
    x0, x1 = 88, (176 if has2 else WIDTH - 2)
    d.rectangle((x0, y - 5, x1, y + 5), outline=1)
    fr = _frac(v1, float(row.get("min", 0)), float(row.get("max", 100)))
    fill_to = x0 + 2 + round((x1 - x0 - 4) * fr)
    if fr > 0:
        d.rectangle((x0 + 2, y - 3, fill_to, y + 3), fill=1)

    if has2:
        v2 = _value(data, row.get("senzor2"), row.get("delitel2", 1))
        u2 = _unit(data, row.get("senzor2"), row.get("jednotka2", "auto"))
        _text_right(d, WIDTH - 2, y, _fmt(v2, row.get("desetinna_mista2", 0), u2), f_val)


def _graph(img, d, top, graf, data, history):
    bottom = HEIGHT - 1
    left_w = 44                                   # levy panel s popiskem
    gx0, gx1 = left_w, WIDTH - 1
    sensor = graf.get("senzor", "")
    lo, hi = float(graf.get("min", 0)), float(graf.get("max", 100))
    div = float(graf.get("delitel", 1)) or 1

    # levy panel: popisek, aktualni hodnota, delka
    mid = (top + bottom) // 2
    d.text((2, top + 8), graf.get("popisek", ""), font=_font("ExtraBold", 12), fill=1, anchor="lm")
    v = _value(data, sensor, div)
    u = _unit(data, sensor, graf.get("jednotka", "auto"))
    d.text((2, mid + 2), _fmt(v, graf.get("desetinna_mista", 0), u), font=_font("Bold", 12),
           fill=1, anchor="lm")
    secs = int(graf.get("delka_s", 120))
    span = f"{secs // 60} min" if secs >= 60 else f"{secs} s"
    d.text((2, bottom - 6), span, font=_font("SemiBold", 10), fill=1, anchor="lm")

    d.rectangle((gx0, top, gx1, bottom), outline=1)
    vals = [x / div for x in (history or {}).get(sensor, [])]
    if len(vals) < 2:
        return
    iw, ih = gx1 - gx0 - 3, bottom - top - 4      # vnitrek ramecku
    n = len(vals)
    # na kazdy sloupec pixelu jedna hodnota (prumer z te casti historie)
    cols = []
    for x in range(iw + 1):
        a = int(x * n / (iw + 1))
        b = max(a + 1, int((x + 1) * n / (iw + 1)))
        chunk = vals[a:b]
        cols.append(sum(chunk) / len(chunk))
    base = bottom - 2
    pts = []
    for x, cv in enumerate(cols):
        px = gx0 + 2 + x
        py = base - round(ih * _frac(cv, lo, hi))
        pts.append((px, py))
        # srafovana plocha pod carou (sachovnice = "polovicni jas")
        for yy in range(py + 2, base + 1):
            if (px + yy) % 2 == 0:
                img.putpixel((px, yy), 1)
    d.line(pts, fill=1, width=2)


def render(acfg, data, history=None, now=None):
    """acfg = config["alphacool"], data = {senzor: {"value", "unit"}}, history = {senzor: [hodnoty]}.
    Vrati obrazek 240x128 v rezimu "1"."""
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    _header(d, now or datetime.now())
    for i, row in enumerate(acfg.get("radky", [])[:3]):
        _row(d, 25 + i * 19, row, data)
    _graph(img, d, 81, acfg.get("graf", {}), data, history)
    if acfg.get("inverze"):
        img = img.convert("L").point(lambda p: 255 - p).convert("1")
    return img


def preview(img, scale=2, on=(235, 242, 255), off=(24, 52, 190)):
    """Nahled pro okno nastaveni: barvy jako modry STN displej, zvetseny."""
    rgb = Image.new("RGB", img.size, off)
    rgb.paste(on, (0, 0), img.convert("L"))
    return rgb.resize((img.width * scale, img.height * scale), Image.NEAREST)
