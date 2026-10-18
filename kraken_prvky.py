# kraken_prvky.py - volne rozvrzeni obrazovky Krakenu (typ obrazovky "volne")
#
# Obrazovka = seznam prvku v scr["prvky"]; kazdy ma typ, polohu x, y a velikost w, h v bodech
# displeje 240x240. Kresli se ve 3x rozliseni (screens.S) v poradi seznamu (pozdejsi navrchu).
# Prvky vychazeji z existujicich obrazovek (screens.py):
#   panel        podklad dlazdice (zaobleny obdelnik)
#   text         pevny text (pismo Montserrat, prechod barev)
#   hodnota      hodnota senzoru s jednotkou nahore vpravo (barva i podle hodnoty)
#   bar          vodorovny / svisly bar s prechodem
#   segmenty     segmentovy bar
#   oblouk       oblouk s prechodem (uhly: 0 = nahore, po smeru hodin), i plneni od konce
#   prstenec     segmentovy prstenec
#   budik        stupnice s ruckickou
#   graf         prubeh hodnoty v case (plocha, cara, tecka)
#   graf_dokola  paprsky historie dokola
#   hladina      kruhova nadoba s hladinou
#   hodiny       cas / datum jako text
#   rucicky      rucickove hodiny
#   obrazek      obrazek ze slozky obrazky/
# Pseudo senzory casu (napr. pro sekundovy prstenec): @sekundy, @minuty, @hodiny.

import copy
import math
import os
import re
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFont

import screens as SC

S = SC.S
WEIGHTS = ["Light", "SemiBold", "Bold", "ExtraBold", "Black"]
ALIGN = ["vlevo", "stred", "vpravo"]
CLOCK_FORMATS = ["HH:MM", "HH:MM:SS", "HH", "MM", "SS", "den", "datum", "den datum", "den D. M.", "DEN D. M.",
                 "D. M.", "D. M. RRRR"]
TIME_SENSORS = ["@sekundy", "@minuty", "@hodiny"]
UNITS = ["auto", "auto°", "°", "°C", "%", "GHz", "MHz", "W", "RPM", "GB", "MB/s", ""]   # auto° = °C jako °
TRACK = "#1c1f24"
HISTORY_TYPES = ("graf", "graf_dokola", "statistika", "trend")
UNIT_BY_DIV = {**SC.UNIT_BY_DIV, ("MB", 1024): "GB", ("KB/s", 1024): "MB/s"}


# ------------------------------------------------------------------ pomucky
def _num(p, key, default):
    try:
        return float(p.get(key, default))
    except (TypeError, ValueError):
        return default


def _rgb(p, key, default):
    return SC.hex_rgb(p.get(key) or default, SC.hex_rgb(default))


def _cols(p, d1="#ffffff", d2=None):
    c1 = _rgb(p, "barva_od", d1)
    return c1, _rgb(p, "barva_do", p.get("barva_od") or d2 or d1)


def _box(p):
    x, y = int(_num(p, "x", 0)), int(_num(p, "y", 0))
    w, h = max(1, int(_num(p, "w", 10))), max(1, int(_num(p, "h", 10)))
    return x * S, y * S, (x + w) * S, (y + h) * S


def _circle(p):
    x0, y0, x1, y1 = _box(p)
    return (x0 + x1) / 2, (y0 + y1) / 2, min(x1 - x0, y1 - y0) / 2


def _font(p, weight="ExtraBold", px=24):
    wt = p.get("pismo", weight)
    return SC._raw_font(wt if wt in WEIGHTS else weight, max(6, _num(p, "velikost", px)))


def _fit(d, text, font, max_w):
    """Zmensi pismo, aby se text vesel do sirky (body platna)."""
    tw = d.textlength(text, font=font)
    if tw <= max_w or tw <= 0:
        return font
    return ImageFont.truetype(font.path, max(6 * S, int(font.size * max_w / tw)))


def _sensor(p, data):
    """-> (hodnota, text, jednotka, podil 0..1)"""
    sensor = p.get("senzor")
    div = _num(p, "delitel", 1) or 1
    v = SC.value_for(sensor, data, div)
    txt = SC._fmt(v, int(_num(p, "desetinna_mista", 0)))
    u = p.get("jednotka", "auto")
    if u in ("auto", "auto°"):
        short = u == "auto°"                              # teplota jen jako stupen (°C -> °)
        u = (data.get(sensor) or {}).get("unit", "")
        u = UNIT_BY_DIV.get((u, int(div)), u if div == 1 else "")
        if short and u in SC.DEGREE_UNITS:
            u = "°"
    return v, txt, u, SC._frac(v, _num(p, "min", 0), _num(p, "max", 100))


def _anchor_x(p):
    al = p.get("zarovnani", "vlevo")
    x0, _y0, x1, _y1 = _box(p)
    return {"vlevo": x0, "stred": (x0 + x1) / 2, "vpravo": x1}.get(al, x0), {"vlevo": "l", "stred": "m",
                                                                           "vpravo": "r"}.get(al, "l")


def _line_text(img, d, p, text, weight="ExtraBold", px=16, cols=None):
    f = _fit(d, text, _font(p, weight, px), (_box(p)[2] - _box(p)[0]))
    ax, a = _anchor_x(p)
    y0, y1 = _box(p)[1], _box(p)[3]
    SC._text(img, (ax, (y0 + y1) / 2), text, f, cols or _cols(p), a + "m")


def _arc(img, cx, cy, r, thick, start, span, fr, cols, track=None, dim=None, caps=True, reverse=False):
    """Oblouk s prechodem podel oblouku; uhly: 0 = nahore, po smeru hodin.
    reverse = plni se od konce oblouku (napr. pravy oblouk rostouci zdola nahoru)."""
    if SC.PLASTIC:
        return SC.arc3d(img, cx, cy, r, thick, start - 90, span, fr, cols, dim=dim, caps=caps, reverse=reverse,
                        track=track is not None)
    d = ImageDraw.Draw(img)
    box = (cx - r, cy - r, cx + r, cy + r)
    rr = r - thick / 2
    a0 = start - 90
    width = max(1, int(thick))

    def cap(ang, col):
        if caps:
            a = math.radians(ang)
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
            d.ellipse((px - thick / 2, py - thick / 2, px + thick / 2, py + thick / 2), fill=col)

    if dim is not None:                                   # cela stupnice ztlumene v barvach prechodu
        for i in range(int(span)):
            t = i / span
            d.arc(box, a0 + i, a0 + i + 2, fill=SC._dim(SC.mix(*cols, 1 - t if reverse else t), dim), width=width)
        cap(a0, SC._dim(cols[1] if reverse else cols[0], dim))
        cap(a0 + span, SC._dim(cols[0] if reverse else cols[1], dim))
    elif track is not None:
        d.arc(box, a0, a0 + span, fill=track, width=width)
        cap(a0, track)
        cap(a0 + span, track)
    steps = int(span * fr)
    if steps <= 0:
        return
    for i in range(steps):
        if reverse:
            ang = a0 + span - i - 2
        else:
            ang = a0 + i
        d.arc(box, ang, ang + 2, fill=SC.mix(*cols, i / span), width=width)
    if reverse:
        cap(a0 + span, cols[0])
        cap(a0 + span - steps, SC.mix(*cols, steps / span))
    else:
        cap(a0, cols[0])
        cap(a0 + steps, SC.mix(*cols, steps / span))


def _hist(p, history):
    div = _num(p, "delitel", 1) or 1
    return [v / div for v in (history or {}).get(p.get("senzor"), [])]


# ------------------------------------------------------------------ prvky
def draw_panel(img, d, p, data, now, history):
    x0, y0, x1, y1 = _box(p)
    r = min(_num(p, "zaobleni", 11) * S, (x1 - x0) / 2, (y1 - y0) / 2)
    outline = _rgb(p, "barva_obrysu", "#2c323b") if p.get("obrys") else None
    if SC.PLASTIC:
        if p.get("zapusteny"):                            # zapustene okenko (napr. pod hodnotou budiku)
            SC._groove_rect(img, (x0, y0, x1, y1), r, SC._lerp(_rgb(p, "barva", "#0e1013"), SC.WHITE, 0.06))
        else:
            SC._raised(img, (x0, y0, x1, y1), r, _rgb(p, "barva", "#0e1013"))
        if outline:
            d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, outline=outline, width=S)
        return
    d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, fill=_rgb(p, "barva", "#0e1013"), outline=outline,
                        width=S if outline else 0)


def draw_text(img, d, p, data, now, history):
    _line_text(img, d, p, str(p.get("text", "")))


def draw_value(img, d, p, data, now, history):
    v, txt, u, fr = _sensor(p, data)
    x0, y0, x1, y1 = _box(p)
    f = _font(p, "ExtraBold", 40)
    fu = SC._raw_font("Bold", max(6, f.size / S * _num(p, "jednotka_pomer", 0.33)))
    gap = 2 * S if u else 0
    tw = d.textlength(txt, font=f)
    uw = d.textlength(u, font=fu) if u else 0
    if tw + gap + uw > x1 - x0 > 0:                        # zmensit, at se vejde do sirky
        k = (x1 - x0) / (tw + gap + uw)
        f = ImageFont.truetype(f.path, max(6 * S, int(f.size * k)))
        fu = ImageFont.truetype(fu.path, max(6 * S, int(fu.size * k)))
        tw, uw = d.textlength(txt, font=f), (d.textlength(u, font=fu) if u else 0)
    cols = _cols(p)
    if p.get("podle_hodnoty"):
        c = SC.mix(*cols, fr)
        cols = (c, c)
    total = tw + gap + uw
    ax, a = _anchor_x(p)
    xl = ax if a == "l" else ax - total / 2 if a == "m" else ax - total
    bb = d.textbbox((0, 0), "0", font=f, anchor="ls")
    base = (y0 + y1) / 2 - bb[1] / 2                       # vyska cislic na stred prvku
    SC._text(img, (xl, base), txt, f, cols, "ls")
    if u:
        ub = d.textbbox((0, 0), u, font=fu, anchor="ls")
        SC._text(img, (xl + tw + gap, base + bb[1] - ub[1]), u, fu, cols, "ls")


def draw_bar(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    x0, y0, x1, y1 = _box(p)
    w, h = x1 - x0, y1 - y0
    r = min(w, h) // 2 if p.get("zaobleni", True) else 0
    if SC.PLASTIC:                                        # drazka kolem baru, vypln v puvodni velikosti
        g = SC._bar_rim(min(w, h))
        return SC._bar3d(img, (x0 - g, y0 - g, x1 + g, y1 + g), r + g if r else 0, fr,
                         _cols(p, "#3cff3c", "#ff3b3b"), p.get("smer") == "svisle", base=_rgb(p, "podklad", TRACK),
                         inset=g)
    d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, fill=_rgb(p, "podklad", TRACK))
    if fr <= 0:
        return
    cols = _cols(p, "#3cff3c", "#ff3b3b")
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    if p.get("smer") == "svisle":
        fh = max(2 * r or 1, int(h * fr))
        md.rounded_rectangle((x0, y1 - fh, x1 - 1, y1 - 1), r, fill=255)
        SC._paint(img, mask, SC._vgrad(w, h, cols[0], cols[1]), (x0, y0))
    else:
        fw = max(2 * r or 1, int(w * fr))
        md.rounded_rectangle((x0, y0, x0 + fw - 1, y1 - 1), r, fill=255)
        SC._paint(img, mask, SC._hgrad(w, h, *cols), (x0, y0))


def draw_segments(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    x0, y0, x1, y1 = _box(p)
    n = max(1, int(_num(p, "pocet", 20)))
    gap = _num(p, "mezera", 2) * S
    vertical = p.get("smer") == "svisle"
    if p.get("vanicka"):                                  # zapustena vanicka, segmenty uvnitr
        pad = max(S, round(min(x1 - x0, y1 - y0) * 0.16))
        tray = (x0, y0, x1, y1)
        if SC.PLASTIC:
            SC._groove_rect(img, tray, min(_num(p, "zaobleni", 1) * S + pad, (y1 - y0) / 2, (x1 - x0) / 2))
        else:
            d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), pad, fill=(10, 12, 15))
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    length = (y1 - y0) if vertical else (x1 - x0)
    sl = max(1.0, (length - gap * (n - 1)) / n)
    lit = round(fr * n)
    cols = _cols(p, "#22d3ee", "#ff9f1c")
    off = _rgb(p, "podklad", "#1a1d22")
    rad = min(_num(p, "zaobleni", 1) * S, sl / 2)
    if SC.PLASTIC:
        boxes = []
        for i in range(n):
            a = i * (sl + gap)
            b = (x0, y1 - a - sl, x1 - 1, y1 - a - 1) if vertical else (x0 + a, y0, x0 + a + sl - 1, y1 - 1)
            boxes.append(b + (SC.mix(*cols, i / max(1, n - 1)) if i < lit else None,))
        return SC._segments3d(img, boxes, cols, rad, off=off, vertical=vertical, bar_box=(x0, y0, x1, y1))
    for i in range(n):
        col = SC.mix(*cols, i / max(1, n - 1)) if i < lit else off
        a = i * (sl + gap)
        box = (x0, y1 - a - sl, x1 - 1, y1 - a - 1) if vertical else (x0 + a, y0, x0 + a + sl - 1, y1 - 1)
        d.rounded_rectangle(box, rad, fill=col)


def draw_arc(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    cx, cy, r = _circle(p)
    thick = min(r, max(1, _num(p, "tloustka", 14)) * S)
    dimmed = bool(p.get("ztlumene_pozadi"))
    _arc(img, cx, cy, r, thick, _num(p, "start", -135), _num(p, "rozsah", 270), fr, _cols(p, "#3cdc28", "#ff1414"),
         track=None if dimmed else _rgb(p, "podklad", "#3a3a3a"), dim=0.28 if dimmed else None,
         caps=p.get("zaoblene_konce", True), reverse=bool(p.get("opacne")))


def draw_ring(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    cx, cy, r = _circle(p)
    n = max(2, int(_num(p, "pocet", 30)))
    start, span = _num(p, "start", -150), _num(p, "rozsah", 300)
    thick = int(min(r, max(1, _num(p, "tloustka", 12)) * S))
    cols = _cols(p, "#28c8ff", "#ff28c8")
    step = span / n
    lit = round(fr * n)
    gapd = min(2.4, step / 3)
    box = (cx - r, cy - r, cx + r, cy + r)
    if SC.PLASTIC:
        return SC.seg_ring3d(img, cx, cy, r, thick, [
            (start - 90 + i * step + gapd / 2, start - 90 + (i + 1) * step - gapd / 2, SC.mix(*cols, i / (n - 1)), i < lit)
            for i in range(n)])
    for i in range(n):
        a0 = start - 90 + i * step + gapd / 2
        col = SC.mix(*cols, i / (n - 1))
        d.arc(box, a0, a0 + step - gapd, fill=col if i < lit else SC._dim(col, 0.18), width=thick)


def draw_gauge(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    cx, cy, r = _circle(p)
    start, span = _num(p, "start", -120), _num(p, "rozsah", 240)
    if p.get("luneta"):                                   # kovova luneta a zapusteny ciferník uvnitr prvku
        bw = max(2 * S, r * 0.05)
        SC._metal_ring(img, cx, cy, r, bw)
        d.ellipse((cx - r + bw, cy - r + bw, cx + r - bw, cy + r - bw), fill=(2, 2, 3))
        SC._disc(img, cx, cy, r - bw * 1.2, (27, 31, 37), (3, 4, 5))
        r = r - bw * 1.6
    thick = min(r / 2, max(1, _num(p, "tloustka", 9)) * S)
    _arc(img, cx, cy, r, thick, start, span, fr, _cols(p, "#3cdc28", "#ff1414"), dim=0.28)
    k = r / (96 * S)
    for i in range(11):
        a = math.radians(start - 90 + span * i / 10)
        big = i % 5 == 0
        r1 = r - thick - 6 * S * k
        r2 = r1 - (8 if big else 4) * S * k
        d.line((cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)),
               fill=SC.GREY, width=max(1, int((3 if big else 2) * S * k)))
    a = math.radians(start - 90 + span * fr)
    nc = _rgb(p, "barva_rucicky", "#ffffff")
    ln = r - thick - 8 * S * k
    perp = a + math.pi / 2
    base = max(2 * S, 7 * S * k)
    if SC.PLASTIC:                                        # rucicka ze dvou pulek a vypoukla cepicka
        SC._needle(img, cx, cy, start - 90 + span * fr, ln, base, base * 1.8, nc)
        SC._dome(img, cx, cy, max(3 * S, 12 * S * k), SC._lerp(nc, (120, 128, 138), 0.3))
        return
    d.polygon([(cx + base * math.cos(perp), cy + base * math.sin(perp)), (cx + ln * math.cos(a), cy + ln * math.sin(a)),
               (cx - base * math.cos(perp), cy - base * math.sin(perp))], fill=nc)
    hub = max(3 * S, 12 * S * k)
    d.ellipse((cx - hub, cy - hub, cx + hub, cy + hub), fill=nc)
    d.ellipse((cx - hub * 0.4, cy - hub * 0.4, cx + hub * 0.4, cy + hub * 0.4), fill=SC.BLACK)


def draw_graph(img, d, p, data, now, history):
    x0, y0, x1, y1 = _box(p)
    cols = _cols(p, "#3cdc28", "#ff1414")
    if p.get("ramecek"):
        if SC.PLASTIC:                                    # zapustena obrazovka grafu
            SC._groove_rect(img, (x0, y0, x1, y1), 6 * S, base=(22, 25, 30))
        else:
            d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), 6 * S, outline=SC.DARK, width=S)
    if p.get("mrizka"):                                   # vodorovne linky po ctvrtinach
        for i in (1, 2, 3):
            y = y0 + (y1 - y0) * i / 4
            if SC.PLASTIC:
                SC._engraved(d, x0 + 2 * S, y, x1 - 2 * S, S)
            else:
                d.line((x0 + 2 * S, y, x1 - 2 * S, y), fill=(35, 38, 44), width=S)
    vals = _hist(p, history)
    if len(vals) < 2:
        return
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    if p.get("auto_max"):                                 # meritko podle nejvyssi hodnoty v historii (sit)
        hi = max(max(vals), lo + 0.1)
    style = p.get("styl", "čára")
    if style == "pásek 3D" and SC.PLASTIC:
        SC.ribbon3d(img, x0, y0, x1 - x0, y1 - y0, vals, lo, hi, cols, None,
                    max(2 * S, _num(p, "hloubka", 7) * S))
        return
    if style == "sloupce":
        return _graph_columns(img, d, p, vals, lo, hi, cols, (x0, y0, x1, y1))
    lw = max(1, _num(p, "cara", 3)) * S
    dot = p.get("tecka", True)
    pad = lw
    right = x1 - pad - (lw * 1.4 if dot else 0)
    n = len(vals)
    pts = [(x0 + pad + (right - x0 - pad) * i / (n - 1), y1 - pad - (y1 - y0 - 2 * pad) * SC._frac(v, lo, hi))
           for i, v in enumerate(vals)]
    w, h = x1 - x0, y1 - y0
    if p.get("plocha", True):
        area = Image.new("L", img.size, 0)
        ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], y1 - pad), (pts[0][0], y1 - pad)], fill=150)
        SC._paint(img, area, SC._vgrad(w, h + 1, *cols), (x0, y0))
    light = SC._vgrad(w, h + 1, *[SC.mix(c, SC.WHITE, 0.35) for c in cols])
    if SC.PLASTIC:                                        # cara s tmavym bokem a odleskem
        full = Image.new("RGB", img.size, SC.BLACK)
        full.paste(light, (x0, y0))
        SC._line3d(img, pts, lw, full, side=SC._dim(cols[1], 0.4))
        if dot:
            ex, ey = pts[-1]
            SC._dome(img, ex, ey, lw * 1.4, SC.mix(cols[1], SC.WHITE, 0.4))
        return
    line = Image.new("L", img.size, 0)
    ImageDraw.Draw(line).line(pts, fill=255, width=int(lw), joint="curve")
    SC._paint(img, line, light, (x0, y0))
    if dot:
        ex, ey = pts[-1]
        rr = lw * 1.3
        d.ellipse((ex - rr, ey - rr, ex + rr, ey + rr), fill=SC.WHITE)


def _graph_columns(img, d, p, vals, lo, hi, cols, box):
    """Graf ze sloupcu: hodnoty prevzorkovane na pocet sloupcu, barva podle vysky."""
    x0, y0, x1, y1 = box
    n = max(2, int(_num(p, "pocet", 24)))
    step = len(vals) / n
    vals = [vals[min(len(vals) - 1, int(i * step))] for i in range(n)] if len(vals) >= n else vals
    n = len(vals)
    gap = max(1, _num(p, "mezera", 1.5) * S)
    cw = max(S, (x1 - x0 - gap * (n - 1)) / n)
    rad = min(cw / 2, _num(p, "zaobleni", 1.5) * S)
    for i, v in enumerate(vals):
        fr = max(0.02, SC._frac(v, lo, hi))
        bx0 = x0 + i * (cw + gap)
        top = y1 - (y1 - y0) * fr
        col = SC.mix(*cols, fr)
        if SC.PLASTIC:
            layer = Image.new("RGB", img.size, SC.BLACK)
            ImageDraw.Draw(layer).rounded_rectangle((bx0, top, bx0 + cw, y1 - 1), rad,
                                                    fill=col)
            mask = SC._rect_mask(img, (bx0, top, bx0 + cw, y1 - 1), rad)
            SC._shape(img, layer, mask, (bx0, top, bx0 + cw, y1), across=True, shade=SC.CYLINDER)
        else:
            d.rounded_rectangle((bx0, top, bx0 + cw, y1 - 1), rad, fill=col)


def draw_radial(img, d, p, data, now, history):
    cx, cy, r = _circle(p)
    cols = _cols(p, "#a855f7", "#ff3b8a")
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    vals = _hist(p, history)
    n = 60
    if vals:                                              # nejnovejsi hodnota tesne vlevo od 12 hodin
        step = max(1, len(vals) / n)
        vals = [vals[min(len(vals) - 1, int(i * step))] for i in range(min(n, len(vals)))]
        vals = [None] * (n - len(vals)) + vals
    else:
        vals = [None] * n
    r1, ln = r * 0.58, r * 0.4
    w = max(S, r * 0.045)
    rays = []
    for i, v in enumerate(vals):
        fr = 0.06 if v is None else max(0.06, SC._frac(v, lo, hi))
        a = math.radians(i * 6 - 90)
        r2 = r1 + ln * fr
        xa, ya, xb, yb = cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)
        rays.append(((xa, ya, xb, yb), SC.OFF if v is None else SC.WHITE if i == n - 1 else SC.mix(*cols, fr)))
    if SC.PLASTIC:
        SC._rays3d(img, rays, w)
    else:
        _rays_flat(d, rays, w)
    if p.get("kotouc"):                                   # kotouc uprostred (pod hodnotu)
        rd = r1 - w * 1.2
        if SC.PLASTIC:
            SC._tint(img, SC._disc_mask(img, cx + rd * 0.03, cy + rd * 0.05, rd), SC.BLACK, 0.8)
            SC._metal_ring(img, cx, cy, rd, max(S, rd * 0.06))
            SC._disc(img, cx, cy, rd * 0.94, (42, 48, 56), (6, 7, 8), dy=-0.2)
        else:
            d.ellipse((cx - rd, cy - rd, cx + rd, cy + rd), fill=(18, 20, 24))


def _rays_flat(d, rays, w):
    for (xa, ya, xb, yb), col in rays:
        d.line((xa, ya, xb, yb), fill=col, width=int(w))
        for x, y in ((xa, ya), (xb, yb)):
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)


def draw_level(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    cx, cy, r = _circle(p)
    cols = _cols(p, "#22d3ee", "#1d4ed8")
    R = r * 0.94
    if SC.PLASTIC:                                        # kovova obruc a tmave dno koule
        SC._metal_ring(img, cx, cy, r, r * 0.07)
        SC._disc(img, cx, cy, r * 0.93, (13, 20, 24), (1, 1, 1))
        R = r * 0.9
    else:
        d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(7, 11, 14))
    level = cy + R - 2 * R * fr
    vessel = Image.new("L", img.size, 0)
    ImageDraw.Draw(vessel).ellipse((cx - R, cy - R, cx + R, cy + R), fill=255)
    xa, xb = int(cx - R), int(cx + R)
    for amp, ph, alpha, grad in ((R * 0.06, 1.8, 90, False), (R * 0.045, 0.0, 255, True)):
        pts = [(x, level + amp * math.sin((x - xa) / (R * 0.37) + ph)) for x in range(xa, xb + 1, 3 * S)]
        wave = Image.new("L", img.size, 0)
        ImageDraw.Draw(wave).polygon(pts + [(xb, cy + R + S), (xa, cy + R + S)], fill=alpha)
        fill = SC._vgrad(img.width, img.height, cols[1], cols[0]) if grad else Image.new("RGB", img.size, cols[0])
        SC._paint(img, ImageChops.multiply(wave, vessel), fill)
    if SC.PLASTIC:
        _glass(img, vessel, cx, cy, R, [(x, level + R * 0.045 * math.sin((x - xa) / (R * 0.37)))
                                        for x in range(xa, xb + 1, 3 * S)])
        return
    rw = max(S, r * 0.055)
    d.ellipse((cx - r + rw / 2, cy - r + rw / 2, cx + r - rw / 2, cy + r - rw / 2),
              outline=_rgb(p, "barva_okraje", "#16252d"), width=int(rw))


def _glass(img, vessel, cx, cy, R, surface):
    """Sklenena koule: lesk hladiny, tmavnuti k okraji, mekky odlesk vlevo nahore."""
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).line(surface, fill=255, width=max(S, int(R * 0.03)))
    SC._tint(img, ImageChops.multiply(m, vessel), SC.WHITE, 0.55)
    sh = Image.new("L", img.size, 0)
    sd = ImageDraw.Draw(sh)
    ox, oy = cx - R * 0.16, cy - R * 0.24
    for i in range(30, -1, -1):
        t = i / 30
        rr = R * 1.25 * t
        sd.ellipse((ox - rr, oy - rr, ox + rr, oy + rr), fill=int(255 * SC._interp([(0, 0), (0.62, 0.12), (1, 0.8)], t)))
    SC._tint(img, ImageChops.multiply(sh, vessel), SC.BLACK)
    hl = Image.new("L", img.size, 0)
    hd = ImageDraw.Draw(hl)
    hx, hy, rx, ry = cx - R * 0.34, cy - R * 0.58, R * 0.42, R * 0.22
    for i in range(16):
        t = i / 15
        hd.ellipse((hx - rx * (1 - t), hy - ry * (1 - t), hx + rx * (1 - t), hy + ry * (1 - t)), fill=int(150 * t ** 1.5))
    SC._tint(img, ImageChops.multiply(hl, vessel), SC.WHITE)
    ImageDraw.Draw(img).ellipse((cx - R, cy - R, cx + R, cy + R), outline=SC.BLACK, width=max(S, int(R * 0.015)))


def clock_text(fmt, now):
    days, months = SC.DAYS, SC.MONTHS
    short = days[now.weekday()][:2].upper()
    return {"HH:MM": f"{now.hour:02d}:{now.minute:02d}", "HH:MM:SS": f"{now:%H:%M:%S}",
            "HH": f"{now.hour:02d}", "MM": f"{now.minute:02d}", "SS": f"{now.second:02d}",
            "den": days[now.weekday()], "datum": f"{now.day}. {months[now.month - 1]}",
            "den datum": f"{days[now.weekday()]} {now.day}. {months[now.month - 1]}",
            "den D. M.": f"{days[now.weekday()]} {now.day}. {now.month}.",
            "DEN D. M.": f"{short} {now.day}. {now.month}.", "D. M.": f"{now.day}. {now.month}.",
            "D. M. RRRR": f"{now.day}. {now.month}. {now.year}"}.get(fmt, f"{now.hour:02d}:{now.minute:02d}")


def draw_clock(img, d, p, data, now, history):
    _line_text(img, d, p, clock_text(p.get("format", "HH:MM"), now))


def _hand(d, cx, cy, ang, length, width, col, back=0):
    a = math.radians(ang - 90)
    x0, y0 = cx - back * math.cos(a), cy - back * math.sin(a)
    x1, y1 = cx + length * math.cos(a), cy + length * math.sin(a)
    d.line((x0, y0, x1, y1), fill=col, width=max(1, int(width)))
    for x, y in ((x0, y0), (x1, y1)):
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=col)


def draw_analog(img, d, p, data, now, history):
    cx, cy, r = _circle(p)
    dial, hc, sc = _rgb(p, "barva_od", "#ffffff"), _rgb(p, "barva_do", "#ffffff"), _rgb(p, "barva_sekund", "#ff3c28")
    k = r / (114 * S)                                     # meritko vuci puvodnim rucickovym hodinam
    if SC.PLASTIC:                                        # kovova luneta, zapusteny ciferník, plasticke rucicky
        SC._metal_ring(img, cx, cy, r, 6 * S * k)
        SC._disc(img, cx, cy, r - 6 * S * k, (27, 31, 37), (3, 4, 5))
        for i in range(60):
            a = math.radians(i * 6 - 90)
            big = i % 5 == 0
            r1, r2 = r - 11 * S * k, r - (26 if i % 15 == 0 else 20 if big else 14) * S * k
            seg = (cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a))
            wt = max(1, int((5 if i % 15 == 0 else 4 if big else 2) * S * k))
            d.line([v + (S * k if j % 2 == 0 else 1.5 * S * k) for j, v in enumerate(seg)], fill=SC.BLACK, width=wt)
            d.line(seg, fill=dial if big else SC._dim(dial, 0.5), width=wt)
        _dial_extras(img, p, cx, cy, r, k, dial, now)
        SC._needle(img, cx, cy, (now.hour % 12 + now.minute / 60) * 30 - 90, 60 * S * k, 6.5 * S * k, 11 * S * k, hc)
        SC._needle(img, cx, cy, (now.minute + now.second / 60) * 6 - 90, 90 * S * k, 4.5 * S * k, 13 * S * k, hc)
        if p.get("sekundy", True):
            SC._needle(img, cx, cy, now.second * 6 - 90, 97 * S * k, max(S, 1.8 * S * k), 22 * S * k, sc)
        SC._dome(img, cx, cy, 9 * S * k, sc if p.get("sekundy", True) else hc)
        return
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=SC._dim(dial, 0.55), width=max(1, int(3 * S * k)))
    for i in range(60):
        a = math.radians(i * 6 - 90)
        big = i % 5 == 0
        r1, r2 = r - 8 * S * k, r - (24 if i % 15 == 0 else 18 if big else 12) * S * k
        d.line((cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)),
               fill=dial if big else SC._dim(dial, 0.5), width=max(1, int((5 if i % 15 == 0 else 4 if big else 2) * S * k)))
    _dial_extras(img, p, cx, cy, r, k, dial, now)
    _hand(d, cx, cy, (now.hour % 12 + now.minute / 60) * 30, 58 * S * k, 11 * S * k, hc, 10 * S * k)
    _hand(d, cx, cy, (now.minute + now.second / 60) * 6, 88 * S * k, 7 * S * k, hc, 12 * S * k)
    if p.get("sekundy", True):
        _hand(d, cx, cy, now.second * 6, 96 * S * k, max(1, 3 * S * k), sc, 22 * S * k)
        d.ellipse((cx - 9 * S * k, cy - 9 * S * k, cx + 9 * S * k, cy + 9 * S * k), fill=sc)
        d.ellipse((cx - 3 * S * k, cy - 3 * S * k, cx + 3 * S * k, cy + 3 * S * k), fill=SC.BLACK)


def _dial_extras(img, p, cx, cy, r, k, dial, now):
    """Cisla 12 / 3 / 6 / 9 a datum na ciferníku (jako obrazovka Rucickove hodiny)."""
    if p.get("cisla"):
        f = SC._raw_font("ExtraBold", max(6, 22 * k))
        for num, ang in ((12, 0), (3, 90), (6, 180), (9, 270)):
            a = math.radians(ang - 90)
            SC._text(img, (cx + (r - 42 * S * k) * math.cos(a), cy + (r - 42 * S * k) * math.sin(a)), str(num), f,
                     (dial, dial), "mm")
    if p.get("datum"):
        c = _rgb(p, "barva_datum", "#28c8ff")
        SC._text(img, (cx, cy + 44 * S * k), clock_text("DEN D. M.", now), SC._raw_font("ExtraBold", max(6, 17 * k)),
                 (c, c), "mm")


_img_cache = {}


def _picture(p):
    """Obrazek jako RGBA (pruhlednost z alfa kanalu, u uprav z jasu)."""
    name, mode = p.get("soubor", ""), p.get("uprava", SC.IMAGE_MODES[0])
    path = os.path.join(SC.IMAGES, *name.split("/"))
    key = (path, os.path.getmtime(path), mode, tuple(_cols(p)))
    if key not in _img_cache:
        if mode == SC.IMAGE_MODES[0]:
            src = Image.open(path).convert("RGBA")
            bb = src.getchannel("A").getbbox()
            src = src.crop(bb) if bb else src
        else:
            rgb = SC._load_image(name, mode, _cols(p))
            src = rgb.convert("RGBA")
            src.putalpha(rgb.convert("L").point(lambda v: 255 if v > 12 else 0))
        if len(_img_cache) > 16:
            _img_cache.clear()
        _img_cache[key] = src
    return _img_cache[key]


def draw_image(img, d, p, data, now, history):
    x0, y0, x1, y1 = _box(p)
    try:
        src = _picture(p)
    except (OSError, ValueError):
        d.rectangle((x0, y0, x1 - 1, y1 - 1), outline=SC.DARK, width=S)
        d.line((x0, y0, x1 - 1, y1 - 1), fill=SC.DARK, width=S)
        return
    k = min((x1 - x0) / src.width, (y1 - y0) / src.height)
    pic = src.resize((max(1, round(src.width * k)), max(1, round(src.height * k))), Image.LANCZOS)
    img.paste(pic.convert("RGB"), (int(x0 + (x1 - x0 - pic.width) / 2), int(y0 + (y1 - y0 - pic.height) / 2)),
              pic.getchannel("A"))


# ------------------------------------------------------------ text se sablonou
_PLACEHOLDER = re.compile(r"\{([^{}|]+)(?:\|([^{}|]*))?(?:\|([^{}|]*))?\}")


_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")


def fill_template(text, data):
    """Sablona {senzor|delitel|desetinna mista} -> text s hodnotami (chybejici senzor = pomlcka).
    Delitel a mista jsou volitelne (1, 0), jednotky se pisou primo do textu. Cast v [hranatych
    zavorkach] se vynecha, kdyz v ni nektery senzor chybi: "{@disk C: volno} GB[ · {Teplota disku (C:)} °C]"."""
    def optional(m):
        part = m.group(1)
        if any(SC.value_for(s, data) is None for s in template_sensors(part)):
            return ""
        return part
    text = _OPTIONAL.sub(optional, str(text or ""))

    def rep(m):
        try:
            div = float((m.group(2) or "1").replace(",", ".")) or 1
        except ValueError:
            div = 1
        try:
            dec = int(m.group(3) or 0)
        except ValueError:
            dec = 0
        return SC._fmt(SC.value_for(m.group(1).strip(), data, div), dec)
    return _PLACEHOLDER.sub(rep, text)


def template_sensors(text):
    return [m.group(1).strip() for m in _PLACEHOLDER.finditer(str(text or ""))]


def item_sensors(p):
    """Vsechny senzory prvku (senzor + senzory v sablone textu)."""
    out = [p["senzor"]] if p.get("senzor") else []
    if p.get("typ") == "sablona":
        out += template_sensors(p.get("text"))
    return out


def draw_template(img, d, p, data, now, history):
    _line_text(img, d, p, fill_template(p.get("text", ""), data))


# ------------------------------------------------------------------ ikony
# tvary v mrizce 24 x 24: ("l", body) cara, ("p", body) plny mnohouhelnik, ("c", x, y, r, plny) kruh,
# ("o", x0, y0, x1, y1, plny) elipsa, ("r", x0, y0, x1, y1, polomer, plny) obdelnik,
# ("a", x0, y0, x1, y1, od, do) oblouk elipsy (uhly Pillow: 0 = vpravo, po smeru hodin)
def _blade(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    mx, my = 12 + 5.4 * c, 12 + 5.4 * s
    return [(mx + 5.0 * math.cos(t) * c - 2.3 * math.sin(t) * s, my + 5.0 * math.cos(t) * s + 2.3 * math.sin(t) * c)
            for t in (i * math.pi / 8 for i in range(16))]


ICON_SHAPES = {
    "šipka dolů": [("l", [(12, 4), (12, 20)]), ("l", [(5, 13), (12, 20), (19, 13)])],
    "šipka nahoru": [("l", [(12, 20), (12, 4)]), ("l", [(5, 11), (12, 4), (19, 11)])],
    "šipka vpravo": [("l", [(4, 12), (20, 12)]), ("l", [(13, 5), (20, 12), (13, 19)])],
    "teploměr": [("r", 9.5, 2.5, 14.5, 15.5, 2.5, False), ("c", 12, 18, 4.2, True), ("l", [(12, 8), (12, 16)])],
    "ventilátor": [("c", 12, 12, 10.5, False), ("c", 12, 12, 2.2, True)] + [("p", _blade(a)) for a in (20, 110, 200, 290)],
    "kapka": [("p", [(12, 2.5)] + [(12 + 6.2 * math.cos(math.radians(t)), 15 + 6.2 * math.sin(math.radians(t)))
                                   for t in range(-55, 240, 10)])],
    "blesk": [("p", [(13.5, 2), (5, 13.5), (11, 13.5), (9.5, 22), (19, 9.5), (13, 9.5)])],
    "CPU": [("r", 6, 6, 18, 18, 1.5, False), ("r", 9.5, 9.5, 14.5, 14.5, 0, True)]
           + [("l", q) for v in (9, 12, 15) for q in ([(v, 2), (v, 6)], [(v, 18), (v, 22)], [(2, v), (6, v)],
                                                       [(18, v), (22, v)])],
    "GPU": [("r", 2, 6, 22, 18, 1.5, False), ("c", 8.5, 12, 3.4, False), ("c", 15.5, 12, 3.4, False),
            ("l", [(6, 18), (6, 21), (14, 21), (14, 18)])],
    "RAM": [("r", 2, 6, 22, 16, 1, False), ("r", 5, 8.5, 8, 13, 0, True), ("r", 10.5, 8.5, 13.5, 13, 0, True),
            ("r", 16, 8.5, 19, 13, 0, True)] + [("l", [(x, 16), (x, 19)]) for x in (4.5, 7.5, 10.5, 13.5, 16.5, 19.5)],
    "disk": [("o", 5, 3, 19, 8, False), ("l", [(5, 5.5), (5, 18.5)]), ("l", [(19, 5.5), (19, 18.5)]),
             ("a", 5, 16, 19, 21, 0, 180), ("a", 5, 9.5, 19, 14.5, 0, 180)],
    "síť": [("a", 12 - r, 19 - r, 12 + r, 19 + r, 225, 315) for r in (5, 10, 15)] + [("c", 12, 19, 1.8, True)],
    "hodiny": [("c", 12, 12, 9.5, False), ("l", [(12, 12), (12, 6.5)]), ("l", [(12, 12), (16, 14.5)])],
    "výstraha": [("l", [(12, 3), (22, 20.5), (2, 20.5), (12, 3)]), ("l", [(12, 9), (12, 14.5)]),
                 ("c", 12, 17.6, 1.3, True)],
}
ICONS = list(ICON_SHAPES)


def _icon_mask(img, name, box, stroke):
    """Maska ikony vepsane do box (body platna); stroke = tloustka cary v jednotkach mrizky 24."""
    x0, y0, x1, y1 = box
    k = min(x1 - x0, y1 - y0) / 24
    ox, oy = x0 + (x1 - x0 - 24 * k) / 2, y0 + (y1 - y0 - 24 * k) / 2
    P = lambda x, y: (ox + x * k, oy + y * k)
    m = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(m)
    sw = max(1.0, stroke * k)
    h = sw / 2

    def dot(x, y):
        md.ellipse((x - h, y - h, x + h, y + h), fill=255)
    for s in ICON_SHAPES.get(name, []):
        kind = s[0]
        if kind == "l":
            pts = [P(*q) for q in s[1]]
            md.line(pts, fill=255, width=int(round(sw)), joint="curve")
            dot(*pts[0])
            dot(*pts[-1])
        elif kind == "p":
            md.polygon([P(*q) for q in s[1]], fill=255)
        elif kind in ("c", "o"):
            if kind == "c":
                _k, cx, cy, r, full = s
                (X, Y), R = P(cx, cy), r * k
                bb, ry = [X - R, Y - R, X + R, Y + R], R
            else:
                _k, ax, ay, bx, by, full = s
                bb = [*P(ax, ay), *P(bx, by)]
            if full:
                md.ellipse(bb, fill=255)
            else:                                         # obrys na strede cary (Pillow kresli dovnitr)
                md.ellipse([bb[0] - h, bb[1] - h, bb[2] + h, bb[3] + h], outline=255, width=int(round(sw)))
        elif kind == "r":
            _k, ax, ay, bx, by, rad, full = s
            bb = [*P(ax, ay), *P(bx, by)]
            if full:
                md.rounded_rectangle(bb, rad * k, fill=255)
            else:
                md.rounded_rectangle([bb[0] - h, bb[1] - h, bb[2] + h, bb[3] + h], rad * k + h, outline=255,
                                     width=int(round(sw)))
        elif kind == "a":
            _k, ax, ay, bx, by, a0, a1 = s
            bb = [*P(ax, ay), *P(bx, by)]
            md.arc([bb[0] - h, bb[1] - h, bb[2] + h, bb[3] + h], a0, a1, fill=255, width=int(round(sw)))
            cx, cy, rx, ry = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2, (bb[2] - bb[0]) / 2, (bb[3] - bb[1]) / 2
            for a in (a0, a1):
                dot(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
    return m


def _paint_icon(img, name, box, cols, stroke):
    """Ikona v prechodu barev (shora od -> dolu do); ve 3D vzhledu se stinem a leskem."""
    x0, y0, x1, y1 = (int(v) for v in box)
    m = _icon_mask(img, name, (x0, y0, x1, y1), stroke)
    k = min(x1 - x0, y1 - y0) / 24
    if SC.PLASTIC:
        SC._tint(img, SC._moved(m, k * 0.5, k * 0.8), SC.BLACK, 0.75)
    SC._paint(img, m, SC._vgrad(max(1, x1 - x0), max(1, y1 - y0), cols[1], cols[0]), (x0, y0))
    if SC.PLASTIC:
        SC._gloss(img, m, (x0, y0, x1, y1))


def draw_icon(img, d, p, data, now, history):
    cols = _cols(p, "#22d3ee", "#3b82f6")
    name = p.get("ikona", ICONS[0])
    stroke = max(0.5, _num(p, "tloustka", 2))
    if p.get("odznak"):                                   # ikona na kulatem vypouklem odznaku
        cx, cy, R = _circle(p)
        if SC.PLASTIC:
            SC._dome(img, cx, cy, R, cols[0], light=0.5, dark=0.5)
        else:
            d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=cols[0])
        s = R * 0.62
        SC._tint(img, _icon_mask(img, name, (cx - s, cy - s, cx + s, cy + s), stroke * 1.1), SC._dim(cols[0], 0.12))
        return
    _paint_icon(img, name, _box(p), cols, stroke)


# ------------------------------------------------------- teplomer a valec
def draw_thermometer(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    x0, y0, x1, y1 = _box(p)
    w, h = x1 - x0, y1 - y0
    cols = _cols(p, "#22d3ee", "#ff3b3b")
    ticks = p.get("rysky", True)
    R = min(w * (0.3 if ticks else 0.5), h * 0.2)              # banka
    cx = x0 + (R * 1.15 if ticks else w / 2)
    tw = R * 0.52                                              # polovina sirky trubice
    by = y1 - R
    base = _rgb(p, "podklad", TRACK)
    ins = max(S, tw * 0.3)
    ftw = tw - ins
    lo_y, hi_y = by - R * 0.55, y0 + ins + ftw                 # rozsah hladiny v trubici
    top = lo_y - (lo_y - hi_y) * fr
    if SC.PLASTIC:
        SC._groove_rect(img, (cx - tw, y0, cx + tw, by), int(tw), base)
        SC._disc(img, cx, by, R, SC._lerp(base, SC.WHITE, 0.05), (2, 2, 3), dy=0.15)
    else:
        d.rounded_rectangle((cx - tw, y0, cx + tw, by), tw, fill=base)
        d.ellipse((cx - R, by - R, cx + R, by + R), fill=base)
    if fr > 0:
        mask = SC._rect_mask(img, (cx - ftw, top - ftw, cx + ftw, by), int(ftw))
        layer = Image.new("RGB", img.size, SC.BLACK)
        layer.paste(SC._vgrad(max(1, int(2 * R)), max(1, int(by - hi_y + ftw)), cols[0], cols[1]),
                    (int(cx - R), int(hi_y - ftw)))
        if SC.PLASTIC:
            SC._shape(img, layer, mask, (cx - ftw, top - ftw, cx + ftw, by), across=True, shade=SC.CYLINDER)
        else:
            img.paste(layer, (0, 0), mask)
    rb = R - ins
    if SC.PLASTIC:
        SC._dome(img, cx, by, rb, cols[0])
    else:
        d.ellipse((cx - rb, by - rb, cx + rb, by + rb), fill=cols[0])
    if ticks:                                                  # rysky vpravo od trubice
        xa = cx + tw + max(S, tw * 0.4)
        room = x1 - xa
        for i in range(11):
            y = lo_y - (lo_y - hi_y) * i / 10
            ln = room * (0.9 if i % 5 == 0 else 0.5)
            if ln > S:
                d.line((xa, y, xa + ln, y), fill=SC.GREY if i % 5 == 0 else SC.DARK, width=max(1, int(S * 0.8)))


def draw_cylinder(img, d, p, data, now, history):
    _v, _t, _u, fr = _sensor(p, data)
    x0, y0, x1, y1 = _box(p)
    cols = _cols(p, "#3b82f6", "#a855f7")
    w = x1 - x0
    if SC.PLASTIC:
        ry = max(S, w * 0.13)
        SC.cylinder3d(img, x0, y0 + ry, x1, y1 - ry, ry, fr, cols)
        return
    r = int(w * 0.17)
    d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, fill=(18, 20, 24))
    if fr > 0:
        fh = max(2 * r, int((y1 - y0) * fr))
        mask = SC._rect_mask(img, (x0, y1 - fh, x1 - 1, y1 - 1), r)
        SC._paint(img, mask, SC._vgrad(w, y1 - y0, cols[0], cols[1]), (x0, y0))


# --------------------------------------------------- statistika, trend, kontrolka
STATS = ["max", "min", "průměr", "změna"]


def _stat(p, history):
    vals = _hist(p, history)
    if not vals:
        return None
    f = p.get("funkce", "max")
    if f == "min":
        return min(vals)
    if f == "průměr":
        return sum(vals) / len(vals)
    if f == "změna":
        return vals[-1] - vals[0]
    return max(vals)


def draw_stat(img, d, p, data, now, history):
    v = _stat(p, history)
    _v, _t, u, _fr = _sensor(p, data)
    txt = SC._fmt(v, int(_num(p, "desetinna_mista", 0)))
    if p.get("funkce") == "změna" and v is not None and v > 0:
        txt = "+" + txt
    txt += "°" if u in SC.DEGREE_UNITS else (" " + u if u else "")
    label = str(p.get("popisek", ""))
    x0, y0, x1, y1 = _box(p)
    f = _font(p, "Bold", 22)
    fl = ImageFont.truetype(SC._raw_font("SemiBold", 10).path, f.size)
    lw = d.textlength(label + " ", font=fl) if label else 0
    tw = d.textlength(txt, font=f)
    if lw + tw > x1 - x0 > 0:                                  # zmensit, at se vejde do sirky
        k = (x1 - x0) / (lw + tw)
        f = ImageFont.truetype(f.path, max(6 * S, int(f.size * k)))
        fl = ImageFont.truetype(fl.path, max(6 * S, int(fl.size * k)))
        lw = d.textlength(label + " ", font=fl) if label else 0
        tw = d.textlength(txt, font=f)
    ax, a = _anchor_x(p)
    xl = ax if a == "l" else ax - (lw + tw) / 2 if a == "m" else ax - lw - tw
    bb = d.textbbox((0, 0), "0", font=f, anchor="ls")
    base = (y0 + y1) / 2 - bb[1] / 2
    if label:
        c = _rgb(p, "barva_popisku", "#8a929c")
        SC._text(img, (xl, base), label, fl, (c, c), "ls")
    SC._text(img, (xl + lw, base), txt, f, _cols(p), "ls")


def draw_trend(img, d, p, data, now, history):
    vals = _hist(p, history)
    diff = 0.0
    if len(vals) >= 2:
        first = vals[:max(1, len(vals) // 5)]
        diff = vals[-1] - sum(first) / len(first)
    thr = abs(_num(p, "prah", 1))
    if diff > thr:
        name, key, dflt = "šipka nahoru", "barva_roste", "#ff3b3b"
    elif diff < -thr:
        name, key, dflt = "šipka dolů", "barva_klesa", "#3cff3c"
    else:
        name, key, dflt = "šipka vpravo", "barva_stoji", "#8a929c"
    c = _rgb(p, key, dflt)
    _paint_icon(img, name, _box(p), (c, c), max(0.5, _num(p, "tloustka", 3)))


def draw_lamp(img, d, p, data, now, history):
    v, _t, _u, _fr = _sensor(p, data)
    thr = _num(p, "prah", 80)
    on = v is not None and (v < thr if p.get("pod") else v >= thr)
    if on and p.get("blikat") and now.second % 2:
        on = False
    col = _rgb(p, "barva_od", "#ff3b3b") if on else _rgb(p, "barva_zhasnuta", "#2a1416")
    x0, y0, x1, y1 = _box(p)
    round_shape = p.get("tvar", "kruh") == "kruh"
    if round_shape:
        cx, cy, R = _circle(p)
        mask = SC._disc_mask(img, cx, cy, R)
    else:
        rad = int(min(x1 - x0, y1 - y0) * 0.22)
        mask = SC._rect_mask(img, (x0, y0, x1 - 1, y1 - 1), rad)
    if on and p.get("zare", True):                             # zare jen u rozsvicene kontrolky
        SC._glow(img, Image.new("RGB", img.size, col), mask, min(x1 - x0, y1 - y0) * 0.35, 0.6, force=True)
    if round_shape and SC.PLASTIC:
        SC._dome(img, cx, cy, R, col, light=0.55 if on else 0.3, dark=0.5)
    elif SC.PLASTIC:
        SC._shape(img, Image.new("RGB", img.size, col), mask, (x0, y0, x1, y1), glow=False)
        SC._edges(img, mask, max(S, 1.5 * S), top=0.2, bottom=0.6)
    else:
        img.paste(col, None, mask)
    if p.get("text"):
        tc = SC._dim(col, 0.15) if on else SC._lerp(col, SC.WHITE, 0.25)
        _line_text(img, d, dict(p, zarovnani="stred"), str(p["text"]), cols=(tc, tc))


# ------------------------------------------------------------------ tvary
LINE_STYLES = ["vyrytá", "plná", "čárkovaná"]
CIRCLE_STYLES = ["plný", "kotouč", "kopule", "zapuštěný", "obrys"]


def draw_line(img, d, p, data, now, history):
    x0, y0, x1, y1 = _box(p)
    t = max(0.5, _num(p, "tloustka", 2)) * S
    col = _rgb(p, "barva", "#1e2228")
    style = p.get("styl", LINE_STYLES[0])
    vert = p.get("smer") == "svisle"
    c = (x0 + x1) / 2 if vert else (y0 + y1) / 2
    seg = (lambda a, b, o=0.0: (c + o, a, c + o, b)) if vert else (lambda a, b, o=0.0: (a, c + o, b, c + o))
    a0, a1 = (y0, y1) if vert else (x0, x1)
    if style == "vyrytá":                                      # tmava drazka a svetly okraj pod ni / vpravo
        d.line(seg(a0, a1, -t * 0.3), fill=(3, 4, 5), width=max(1, int(t)))
        d.line(seg(a0, a1, t * 0.65), fill=col, width=max(1, int(t / 2)))
    elif style == "čárkovaná":
        pos = a0
        while pos < a1:
            d.line(seg(pos, min(a1, pos + 3 * t)), fill=col, width=max(1, int(t)))
            pos += 5 * t
    else:
        d.line(seg(a0, a1), fill=col, width=max(1, int(t)))


def draw_circle(img, d, p, data, now, history):
    cx, cy, R = _circle(p)
    col = _rgb(p, "barva", "#1b1f25")
    style = p.get("styl", CIRCLE_STYLES[0])
    if style == "kotouč":
        SC._disc(img, cx, cy, R, SC._lerp(col, SC.WHITE, 0.12), SC._dim(col, 0.25), dy=-0.15)
    elif style == "kopule":
        SC._dome(img, cx, cy, R, col)
    elif style == "zapuštěný":
        SC._disc(img, cx, cy, R, col, (2, 2, 3), dy=0.2)
        SC._tint(img, ImageChops.subtract(SC._disc_mask(img, cx, cy, R), SC._disc_mask(img, cx, cy - S, R)),
                 SC.WHITE, 0.1)
    elif style == "obrys":
        t = max(1, _num(p, "tloustka", 2) * S)
        d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=col, width=int(t))
    else:
        d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=col)


def draw_bezel(img, d, p, data, now, history):
    cx, cy, R = _circle(p)
    SC._metal_ring(img, cx, cy, R, min(R, max(1, _num(p, "tloustka", 6)) * S))


DRAW = {"panel": draw_panel, "text": draw_text, "hodnota": draw_value, "bar": draw_bar, "segmenty": draw_segments,
        "oblouk": draw_arc, "prstenec": draw_ring, "budik": draw_gauge, "graf": draw_graph,
        "graf_dokola": draw_radial, "hladina": draw_level, "hodiny": draw_clock, "rucicky": draw_analog,
        "obrazek": draw_image, "sablona": draw_template, "ikona": draw_icon, "teplomer": draw_thermometer,
        "valec": draw_cylinder, "statistika": draw_stat, "trend": draw_trend, "kontrolka": draw_lamp,
        "cara": draw_line, "kruh": draw_circle, "luneta": draw_bezel}
TYPES = {"panel": "Panel (podklad)", "text": "Text", "hodnota": "Hodnota senzoru", "bar": "Bar",
         "segmenty": "Segmentový bar", "oblouk": "Oblouk", "prstenec": "Segmentový prstenec",
         "budik": "Budík s ručičkou", "graf": "Graf v čase", "graf_dokola": "Graf dokola", "hladina": "Hladina",
         "hodiny": "Hodiny / datum", "rucicky": "Ručičkové hodiny", "obrazek": "Obrázek / logo",
         "sablona": "Text se šablonou (více hodnot)", "ikona": "Ikona", "teplomer": "Teploměr",
         "valec": "Skleněný válec", "statistika": "Min / max / průměr", "trend": "Šipka trendu",
         "kontrolka": "Kontrolka (výstraha)", "cara": "Čára / oddělovač", "kruh": "Kruh / kotouč",
         "luneta": "Kovová luneta"}
# skupiny v nabidce "+ Pridat" editoru
GROUPS = [("Text a hodnoty", ["text", "sablona", "hodnota", "statistika", "hodiny", "ikona", "obrazek"]),
          ("Ukazatele", ["bar", "segmenty", "oblouk", "prstenec", "budik", "teplomer", "valec", "hladina",
                         "kontrolka", "trend"]),
          ("Grafy a hodiny", ["graf", "graf_dokola", "rucicky"]),
          ("Tvary a podklady", ["panel", "cara", "kruh", "luneta"])]


def render(items, data, history=None, now=None):
    """Prvky -> obrazek 720x720 (3x). Chybny prvek nesmi shodit celou obrazovku."""
    now = now or datetime.now()
    data = dict(data)
    data.update({"@sekundy": {"value": now.second, "unit": ""}, "@minuty": {"value": now.minute, "unit": ""},
                 "@hodiny": {"value": now.hour, "unit": ""}})
    img = SC._canvas()
    d = ImageDraw.Draw(img)
    for p in items:
        if p.get("skryty") or p.get("typ") not in DRAW:
            continue
        try:
            DRAW[p["typ"]](img, d, p, data, now, history)
        except Exception:
            x0, y0, _x1, _y1 = _box(p)
            d.rectangle((x0, y0, x0 + 4 * S, y0 + 4 * S), fill=(255, 0, 0))
    return img


# ------------------------------------------------------ pole editoru a vychozi hodnoty
_SENS = [("senzor", "Senzor", "sensor", None), ("min", "Minimum", "num", None), ("max", "Maximum", "num", None),
         ("delitel", "Dělitel (1000 = MHz→GHz)", "num", None)]
_COLS = [("barva_od", "Barva od", "color", None), ("barva_do", "Barva do", "color", None)]
_FONT = [("pismo", "Písmo", "choice", WEIGHTS), ("velikost", "Velikost písma (px)", "num", None),
         ("zarovnani", "Zarovnání", "choice", ALIGN)]
_ARC = [("start", "Začátek (°, 0 = nahoře)", "num", None), ("rozsah", "Rozsah (°)", "num", None),
        ("tloustka", "Tloušťka (px)", "num", None)]
_VAL = [("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel (1000 = MHz→GHz)", "num", None),
        ("desetinna_mista", "Desetinná místa", "int", None), ("jednotka", "Jednotka", "unit", None)]
GRAPH_STYLES = ["čára", "pásek 3D", "sloupce"]
FIELDS = {
    "panel": [("barva", "Barva", "color", None), ("zaobleni", "Zaoblení rohů (px)", "num", None),
              ("zapusteny", "Zapuštěný (okénko, 3D vzhled)", "bool", None),
              ("obrys", "Obrys", "bool", None), ("barva_obrysu", "Barva obrysu", "color", None)],
    "text": [("text", "Text", "text", None)] + _FONT + _COLS,
    "hodnota": [("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel (1000 = MHz→GHz)", "num", None),
                ("desetinna_mista", "Desetinná místa", "int", None), ("jednotka", "Jednotka", "unit", None),
                ("jednotka_pomer", "Velikost jednotky (0.2–1)", "num", None)] + _FONT + _COLS
               + [("podle_hodnoty", "Barva podle hodnoty (od → do)", "bool", None),
                  ("min", "Minimum (pro barvu)", "num", None), ("max", "Maximum (pro barvu)", "num", None)],
    "bar": _SENS + [("smer", "Směr", "choice", ["vodorovne", "svisle"]), ("zaobleni", "Zaoblené konce", "bool", None)]
           + _COLS + [("podklad", "Podklad", "color", None)],
    "segmenty": _SENS + [("pocet", "Počet segmentů", "int", None), ("mezera", "Mezera (px)", "num", None),
                         ("zaobleni", "Zaoblení (px)", "num", None), ("smer", "Směr", "choice", ["vodorovne", "svisle"]),
                         ("vanicka", "Vanička (zapuštěný podklad)", "bool", None)]
                + _COLS + [("podklad", "Zhasnutý segment", "color", None)],
    "oblouk": _SENS + _ARC + [("opacne", "Plnit od konce", "bool", None),
                              ("zaoblene_konce", "Zaoblené konce", "bool", None),
                              ("ztlumene_pozadi", "Podklad ztlumeně v barvách", "bool", None)]
              + _COLS + [("podklad", "Podklad", "color", None)],
    "prstenec": _SENS + [("pocet", "Počet segmentů", "int", None)] + _ARC + _COLS,
    "budik": _SENS + _ARC + [("luneta", "Kovová luneta a ciferník", "bool", None)] + _COLS
             + [("barva_rucicky", "Ručička", "color", None)],
    "graf": _SENS + [("delka_s", "Délka (s)", "int", None), ("styl", "Styl", "choice", GRAPH_STYLES),
                     ("cara", "Tloušťka čáry (px)", "num", None), ("plocha", "Plocha pod čarou", "bool", None),
                     ("tecka", "Tečka na konci", "bool", None), ("hloubka", "Hloubka pásku 3D (px)", "num", None),
                     ("pocet", "Počet sloupců", "int", None), ("auto_max", "Maximum podle historie", "bool", None),
                     ("ramecek", "Rámeček", "bool", None),
                     ("mrizka", "Linky po čtvrtinách", "bool", None)] + _COLS,
    "graf_dokola": _SENS + [("delka_s", "Délka (s)", "int", None), ("kotouc", "Kotouč uprostřed", "bool", None)]
                   + _COLS,
    "hladina": _SENS + _COLS + [("barva_okraje", "Okraj", "color", None)],
    "hodiny": [("format", "Formát", "choice", CLOCK_FORMATS)] + _FONT + _COLS,
    "rucicky": [("barva_od", "Ciferník", "color", None), ("barva_do", "Ručičky", "color", None),
                ("sekundy", "Sekundová ručička", "bool", None), ("barva_sekund", "Sekundová ručička", "color", None),
                ("cisla", "Čísla 12 · 3 · 6 · 9", "bool", None), ("datum", "Datum (SO 17. 10.)", "bool", None),
                ("barva_datum", "Barva data", "color", None)],
    "obrazek": [("soubor", "Obrázek", "image", None), ("uprava", "Úprava", "mode", None),
                ("barva_od", "Barva tvaru (jen tvar)", "color", None), ("barva_do", "Barva tvaru – do", "color", None)],
    "sablona": [("text", "Šablona {senzor|dělitel|místa}", "template", None)] + _FONT + _COLS,
    "ikona": [("ikona", "Ikona", "choice", ICONS), ("tloustka", "Tloušťka čáry (z 24)", "num", None),
              ("odznak", "Na kulatém odznaku", "bool", None)] + _COLS,
    "teplomer": _SENS + [("rysky", "Rysky", "bool", None)] + _COLS + [("podklad", "Podklad", "color", None)],
    "valec": _SENS + _COLS,
    "statistika": _VAL + [("funkce", "Hodnota z historie", "choice", STATS), ("delka_s", "Za posledních (s)", "int", None),
                          ("popisek", "Popisek před hodnotou", "text", None)] + _FONT + _COLS
                  + [("barva_popisku", "Barva popisku", "color", None)],
    "trend": [("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel (1000 = MHz→GHz)", "num", None),
              ("delka_s", "Porovnat s průměrem za (s)", "int", None),
              ("prah", "Menší změna = beze změny", "num", None), ("tloustka", "Tloušťka šipky (z 24)", "num", None),
              ("barva_roste", "Roste", "color", None), ("barva_klesa", "Klesá", "color", None),
              ("barva_stoji", "Beze změny", "color", None)],
    "kontrolka": [("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel (1000 = MHz→GHz)", "num", None),
                  ("prah", "Rozsvítit od hodnoty", "num", None), ("pod", "Rozsvítit naopak pod hodnotou", "bool", None),
                  ("blikat", "Blikat", "bool", None), ("tvar", "Tvar", "choice", ["kruh", "obdélník"]),
                  ("zare", "Záře, když svítí", "bool", None), ("barva_od", "Rozsvícená", "color", None),
                  ("barva_zhasnuta", "Zhasnutá", "color", None), ("text", "Nápis", "text", None),
                  ("velikost", "Velikost nápisu (px)", "num", None)],
    "cara": [("smer", "Směr", "choice", ["vodorovne", "svisle"]), ("styl", "Styl", "choice", LINE_STYLES),
             ("tloustka", "Tloušťka (px)", "num", None), ("barva", "Barva", "color", None)],
    "kruh": [("styl", "Styl", "choice", CIRCLE_STYLES), ("barva", "Barva", "color", None),
             ("tloustka", "Tloušťka obrysu (px)", "num", None)],
    "luneta": [("tloustka", "Šířka (px)", "num", None)],
}
_S = {"senzor": "CPU (Tctl/Tdie)", "min": 0, "max": 100, "delitel": 1}
NEW = {
    "panel": dict(x=10, y=10, w=110, h=110, barva="#0e1013", zaobleni=11, obrys=False, barva_obrysu="#2c323b"),
    "text": dict(x=20, y=20, w=100, h=16, text="CPU", pismo="ExtraBold", velikost=12, zarovnani="vlevo",
                 barva_od="#ffffff", barva_do="#ffffff"),
    "hodnota": dict(x=20, y=40, w=120, h=50, senzor="CPU (Tctl/Tdie)", delitel=1, desetinna_mista=0, jednotka="auto",
                    jednotka_pomer=0.33, pismo="ExtraBold", velikost=48, zarovnani="vlevo", barva_od="#ffffff",
                    barva_do="#ffffff", podle_hodnoty=False, min=0, max=100),
    "bar": dict(x=20, y=100, w=200, h=8, smer="vodorovne", zaobleni=True, barva_od="#3cff3c", barva_do="#ff3b3b",
                podklad=TRACK, **_S),
    "segmenty": dict(x=20, y=100, w=200, h=10, pocet=20, mezera=2, zaobleni=1, smer="vodorovne", barva_od="#22d3ee",
                     barva_do="#ff9f1c", podklad="#1a1d22", **_S),
    "oblouk": dict(x=10, y=10, w=220, h=220, start=-135, rozsah=270, tloustka=14, opacne=False, zaoblene_konce=True,
                   ztlumene_pozadi=False, barva_od="#3cdc28", barva_do="#ff1414", podklad="#3a3a3a", **_S),
    "prstenec": dict(x=10, y=10, w=220, h=220, pocet=30, start=-150, rozsah=300, tloustka=12, barva_od="#28c8ff",
                     barva_do="#ff28c8", **_S),
    "budik": dict(x=20, y=20, w=200, h=200, start=-120, rozsah=240, tloustka=9, barva_od="#3cdc28",
                  barva_do="#ff1414", barva_rucicky="#ffffff", **_S),
    "graf": dict(x=0, y=120, w=240, h=120, delka_s=120, styl="čára", cara=3, plocha=True, tecka=True, hloubka=7,
                 pocet=24, ramecek=False, mrizka=False, barva_od="#3cff3c", barva_do="#ffb020",
                 senzor="CPU (Tctl/Tdie)", min=30, max=95, delitel=1),
    "graf_dokola": dict(x=20, y=20, w=200, h=200, delka_s=60, kotouc=False, barva_od="#a855f7", barva_do="#ff3b8a",
                        senzor="Celkové vytížení CPU", min=0, max=100, delitel=1),
    "hladina": dict(x=10, y=10, w=220, h=220, barva_od="#22d3ee", barva_do="#1d4ed8", barva_okraje="#16252d",
                    senzor="@kapalina", min=20, max=60, delitel=1),
    "hodiny": dict(x=0, y=80, w=240, h=70, format="HH:MM", pismo="ExtraBold", velikost=80, zarovnani="stred",
                   barva_od="#ffffff", barva_do="#ffffff"),
    "rucicky": dict(x=10, y=10, w=220, h=220, barva_od="#ffffff", barva_do="#ffffff", sekundy=True,
                    barva_sekund="#ff3c28", cisla=False, datum=False, barva_datum="#28c8ff"),
    "obrazek": dict(x=20, y=20, w=200, h=200, soubor="kraken/ryzen7_odznak.png", uprava="beze změny",
                    barva_od="#ffffff", barva_do="#ffffff"),
    "sablona": dict(x=14, y=150, w=212, h=20, text="pumpa {@pumpa_vykon} % · {@pumpa} ot/min", pismo="Bold",
                    velikost=13, zarovnani="stred", barva_od="#e6fbff", barva_do="#e6fbff"),
    "ikona": dict(x=20, y=20, w=32, h=32, ikona="teploměr", tloustka=2, odznak=False, barva_od="#22d3ee",
                  barva_do="#3b82f6"),
    "teplomer": dict(x=20, y=20, w=44, h=200, rysky=True, barva_od="#22d3ee", barva_do="#ff3b3b", podklad=TRACK,
                     **_S),
    "valec": dict(x=20, y=30, w=48, h=150, barva_od="#3b82f6", barva_do="#a855f7", **_S),
    "statistika": dict(x=130, y=14, w=96, h=16, senzor="CPU (Tctl/Tdie)", delitel=1, desetinna_mista=0,
                       jednotka="auto", funkce="max", delka_s=120, popisek="max", pismo="Bold", velikost=11,
                       zarovnani="vpravo", barva_od="#ffffff", barva_do="#ffffff", barva_popisku="#8a929c"),
    "trend": dict(x=200, y=20, w=24, h=24, senzor="CPU (Tctl/Tdie)", delitel=1, delka_s=30, prah=1, tloustka=3,
                  barva_roste="#ff3b3b", barva_klesa="#3cff3c", barva_stoji="#8a929c"),
    "kontrolka": dict(x=200, y=20, w=20, h=20, senzor="CPU (Tctl/Tdie)", delitel=1, prah=85, pod=False, blikat=True,
                      tvar="kruh", zare=True, barva_od="#ff3b3b", barva_zhasnuta="#2a1416", text="", velikost=9),
    "cara": dict(x=14, y=110, w=212, h=4, smer="vodorovne", styl="vyrytá", tloustka=1, barva="#1e2228"),
    "kruh": dict(x=60, y=60, w=120, h=120, styl="kotouč", barva="#1b1f25", tloustka=2),
    "luneta": dict(x=4, y=4, w=232, h=232, tloustka=5),
}
NEW["panel"]["zapusteny"] = False
NEW["segmenty"]["vanicka"] = False
NEW["budik"]["luneta"] = False


def new(typ):
    p = copy.deepcopy(NEW[typ])
    p["typ"] = typ
    return p


def label(p):
    """Popis prvku pro seznam v editoru."""
    t = TYPES.get(p.get("typ"), p.get("typ", "?"))
    extra = p.get("text") or (p.get("format") if p.get("typ") == "hodiny" else "") or p.get("ikona") \
        or p.get("senzor") or os.path.splitext(os.path.basename(p.get("soubor", "")))[0] \
        or (p.get("styl", "") if p.get("typ") in ("cara", "kruh") else "")
    return f"{t}: {extra}".rstrip(": ")


def history_sensors(items):
    """{senzor: delka_s} prvku, ktere kresli historii."""
    out = {}
    for p in items:
        if p.get("typ") in HISTORY_TYPES and p.get("senzor"):
            out[p["senzor"]] = max(out.get(p["senzor"], 0), _num(p, "delka_s", 120))
    return out


# ---------------------------------------------- prevod hotove obrazovky na prvky
# from_screen(scr) rozlozi nastavenou obrazovku (senzory, nadpisy, barvy, rozsahy) na prvky volneho
# rozvrzeni v bodech displeje 240 x 240. Ctvercove obrazovky maji navrh 480 x 480 -> souradnice / 2,
# ostatni jsou rozvrzene podle toho, jak vypadaji po orezu a zvetseni na displej.
def _el(typ, **kw):
    p = new(typ)
    p.update(kw)
    return p


CPU, GPU, RAM, LIQ = "CPU (Tctl/Tdie)", "Teplota GPU", "Použitá fyzická paměť", "@kapalina"
MUTED = "#8a929c"


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def _pc(scr, part, i=None):
    """Barvy casti obrazovky jako barva_od / barva_do (i = 0/1: obe barvy z jedne)."""
    a, b = (_hex(c) for c in SC.colors(scr, part))
    if i is not None:
        a = b = (a, b)[i]
    return {"barva_od": a, "barva_do": b}


def _one(col):
    return {"barva_od": col, "barva_do": col}


def _oslot(scr, n=""):
    """Senzor puvodnich obrazovek (delitel spolecny pro obrazovku)."""
    return {"senzor": scr.get("senzor" + n) or "", "min": scr.get("min" + n, 0), "max": scr.get("max" + n, 100),
            "delitel": scr.get("delitel", 1) or 1}


def _oval(scr, unit=None):
    return {"desetinna_mista": scr.get("desetinna_mista", 0), "jednotka": unit or scr.get("jednotka", "auto")}


def _slot(scr, n=""):
    """Senzor ctvercovych obrazovek (delitelN, desetinnaN)."""
    return {"senzor": scr.get("senzor" + n) or "", "min": scr.get("min" + n, 0), "max": scr.get("max" + n, 100),
            "delitel": scr.get("delitel" + n, 1) or 1}


def _sval(scr, n="", unit="auto"):
    return {"desetinna_mista": scr.get("desetinna" + n, 0), "jednotka": scr.get("jednotka" + n, unit)}


def _txt(x, y, w, h, text, size, col, weight="ExtraBold", align="vlevo"):
    return _el("text", x=x, y=y, w=w, h=h, text=str(text or ""), velikost=size, pismo=weight, zarovnani=align,
               **_one(col))


def _val(x, y, w, h, slot, val, size, cols, align="vlevo", ratio=0.33, weight="ExtraBold"):
    return _el("hodnota", x=x, y=y, w=w, h=h, velikost=size, zarovnani=align, jednotka_pomer=ratio, pismo=weight,
               **slot, **val, **cols)


def _span(scr):
    secs = int(scr.get("delka_s", 120))
    return f"{secs // 60} min" if secs >= 60 else f"{secs} s"


def _pair(scr, c1, c2, top=56, size=50, w=140):
    """Dve hodnoty nad sebou uprostred s popisky v barvach ukazatelu (dva kruhy, dva oblouky)."""
    x = 120 - w // 2
    tc = _pc(scr, "text")
    h = round(size * 0.92)
    return [_txt(x + 10, top, w - 20, 16, scr.get("nadpis1", ""), 13, c1, align="stred"),
            _val(x, top + 18, w, h, _oslot(scr, "1"), _oval(scr, "auto°"), size, tc, "stred", 0.45),
            _val(x, top + 24 + h, w, h, _oslot(scr, "2"), _oval(scr, "auto°"), size, tc, "stred", 0.45),
            _txt(x + 10, top + 26 + 2 * h, w - 20, 16, scr.get("nadpis2", ""), 13, c2, align="stred")]


def _tile(x, y, label, color, slot, val, c1, c2, tcols):
    dec = int(val.get("desetinna_mista", 0) or 0)
    return [_el("panel", x=x, y=y, w=114, h=114),
            _txt(x + 11, y + 9, 92, 16, label, 11, color),
            _val(x + 11, y + 34, 92, 48, slot, val, 48 if dec == 0 else 36, tcols),
            _el("bar", x=x + 11, y=y + 96, w=92, h=6, barva_od=c1, barva_do=c2, **slot)]


def _arc_screen(scr, slot, cols, start, span, thick, box=(6, 6, 228, 228), **kw):
    x, y, w, h = box
    return _el("oblouk", x=x, y=y, w=w, h=h, start=start, rozsah=span, tloustka=thick, **slot, **cols, **kw)


def from_screen(scr):
    """Hotova obrazovka -> seznam prvku (co nejvic podobny puvodni obrazovce)."""
    t = scr.get("typ")
    tc = _pc(scr, "text")
    white = tc["barva_od"]
    E = []
    if t == "dva_bary":
        c1, c2 = _pc(scr, "bar1"), _pc(scr, "bar2")
        E += [_txt(14, 88, 90, 22, scr.get("nadpis1", ""), 19, white),
              _val(92, 32, 136, 72, _oslot(scr, "1"), _oval(scr, "auto°"), 82, tc, "vpravo", 0.36, "Black"),
              _el("bar", x=14, y=114, w=212, h=17, **_oslot(scr, "1"), **c1),
              _el("bar", x=14, y=137, w=212, h=17, **_oslot(scr, "2"), **c2),
              _txt(14, 160, 90, 22, scr.get("nadpis2", ""), 19, white),
              _val(92, 164, 136, 72, _oslot(scr, "2"), _oval(scr, "auto°"), 82, tc, "vpravo", 0.36, "Black")]
    elif t == "oblouk":
        E += [_arc_screen(scr, _oslot(scr), _pc(scr, "oblouk"), -90, 315, 24),
              _txt(50, 82, 150, 24, scr.get("nadpis") or scr.get("senzor", ""), 22, white),
              _val(46, 106, 166, 70, _oslot(scr), _oval(scr, "auto°"), 80, tc, "vlevo", 0.4, "Black")]
    elif t == "budik":
        E += [_el("budik", x=6, y=6, w=228, h=228, start=-120, rozsah=240, tloustka=20, luneta=True,
                  barva_rucicky=_pc(scr, "rucicka")["barva_od"], **_oslot(scr), **_pc(scr, "oblouk")),
              _val(56, 144, 128, 54, _oslot(scr), _oval(scr, "auto°"), 60, tc, "stred", 0.4, "Black"),
              _txt(56, 202, 128, 20, scr.get("nadpis") or scr.get("senzor", ""), 18, white, align="stred")]
    elif t == "dva_kruhy":
        k1, k2 = _pc(scr, "kruh1"), _pc(scr, "kruh2")
        E += [_arc_screen(scr, _oslot(scr, "1"), k1, -90, 300, 18, (4, 4, 232, 232)),
              _arc_screen(scr, _oslot(scr, "2"), k2, -90, 300, 18, (28, 28, 184, 184))]
        E += _pair(scr, k1["barva_od"], k2["barva_od"], top=62, size=42, w=120)
    elif t in ("dva_oblouky", "chlazeni"):
        if t == "chlazeni":
            kp, kv = _pc(scr, "pumpa"), _pc(scr, "ventilatory")
            E += [_arc_screen(scr, {"senzor": "@pumpa_vykon", "min": 0, "max": 100}, kp, 195, 150, 22),
                  _arc_screen(scr, {"senzor": "@ventilatory_vykon", "min": 0, "max": 100}, kv, 15, 150, 22,
                              opacne=True),
                  _txt(50, 62, 140, 16, "KAPALINA", 13, white, align="stred"),
                  _val(40, 80, 160, 52, {"senzor": LIQ, "min": 20, "max": 60, "delitel": 1},
                       {"desetinna_mista": 1, "jednotka": "°"}, 58, _pc(scr, "kapalina"), "stred", 0.45, "Black")]
            for y, lbl, key, cols in ((142, "PUMPA", "pumpa", kp), (162, "VENTILÁTORY", "ventilatory", kv)):
                E.append(_el("sablona", x=36, y=y, w=168, h=16, velikost=12, pismo="ExtraBold", zarovnani="stred",
                             text=f"{lbl} {{@{key}_vykon}} % · {{@{key}}}", **_one(cols["barva_do"])))
        else:
            k1, k2 = _pc(scr, "oblouk1"), _pc(scr, "oblouk2")
            E += [_arc_screen(scr, _oslot(scr, "1"), k1, 195, 150, 22),
                  _arc_screen(scr, _oslot(scr, "2"), k2, 15, 150, 22, opacne=True)]
            E += _pair(scr, k1["barva_od"], k2["barva_od"])
    elif t == "graf":
        E += [_txt(14, 24, 130, 18, scr.get("nadpis") or scr.get("senzor", ""), 17, white),
              _txt(150, 24, 76, 16, _span(scr), 12, MUTED, align="vpravo"),
              _val(12, 38, 200, 52, _oslot(scr), _oval(scr, "auto°"), 58, tc, "vlevo", 0.4, "Black"),
              _el("graf", x=10, y=104, w=220, h=124, ramecek=True, mrizka=True, cara=4,
                  delka_s=scr.get("delka_s", 120), **_oslot(scr), **_pc(scr, "graf"))]
    elif t == "graf_dva":
        g1, g2 = _pc(scr, "graf1"), _pc(scr, "graf2")
        E += [_el("graf", x=10, y=104, w=220, h=124, ramecek=True, mrizka=True, plocha=False, cara=3,
                  delka_s=scr.get("delka_s", 120), **_oslot(scr, "2"), **g2),
              _el("graf", x=10, y=104, w=220, h=124, plocha=True, cara=3, delka_s=scr.get("delka_s", 120),
                  **_oslot(scr, "1"), **g1),
              _txt(14, 30, 96, 14, scr.get("nadpis1") or scr.get("senzor1", ""), 12, white, align="vpravo"),
              _txt(130, 30, 96, 14, scr.get("nadpis2") or scr.get("senzor2", ""), 12, white),
              _val(10, 46, 100, 48, _oslot(scr, "1"), _oval(scr, "auto°"), 50, _one(g1["barva_od"]), "vpravo", 0.4,
                   "Black"),
              _val(130, 46, 100, 48, _oslot(scr, "2"), _oval(scr, "auto°"), 50, _one(g2["barva_od"]), "vlevo", 0.4,
                   "Black"),
              _txt(80, 230, 80, 10, _span(scr), 9, MUTED, align="stred")]
    elif t == "hodiny":
        E += [_el("hodiny", x=0, y=6, w=240, h=112, format="HH", velikost=136, pismo="Black", zarovnani="stred",
                  **_pc(scr, "hodiny")),
              _el("hodiny", x=0, y=124, w=240, h=112, format="MM", velikost=136, pismo="Bold", zarovnani="stred",
                  **_pc(scr, "minuty"))]
    elif t == "segmenty":
        E += [_el("prstenec", x=6, y=6, w=228, h=228, pocet=30, start=-150, rozsah=300, tloustka=27, **_oslot(scr),
                  **_pc(scr, "segmenty")),
              _txt(60, 78, 120, 20, scr.get("nadpis") or scr.get("senzor", ""), 18, white, align="stred"),
              _val(46, 100, 148, 64, _oslot(scr), _oval(scr, "auto°"), 68, tc, "stred", 0.4, "Black")]
    elif t == "ctyri_hodnoty":
        oc = _pc(scr, "oblouky")
        E += [_el("cara", x=118, y=28, w=4, h=184, smer="svisle"), _el("cara", x=28, y=118, w=184, h=4)]
        for n, start, rev, cx, cy in (("1", 275, False, 72, 79), ("2", 5, True, 168, 79),
                                      ("3", 185, True, 72, 161), ("4", 95, False, 168, 161)):
            E += [_arc_screen(scr, _oslot(scr, n), oc, start, 80, 15, opacne=rev),
                  _val(cx - 38, cy - 17, 76, 34, _oslot(scr, n), _oval(scr, "auto°"), 36, tc, "stred", 0.45, "Black"),
                  _txt(cx - 38, cy - 35 if cy < 120 else cy + 21, 76, 14, scr.get("nadpis" + n, ""), 12, MUTED,
                       align="stred")]
    elif t == "hodiny_analog":
        E.append(_el("rucicky", x=6, y=6, w=228, h=228, cisla=True, datum=bool(scr.get("datum")),
                     barva_od=_pc(scr, "cifernik")["barva_od"], barva_do=_pc(scr, "rucicky")["barva_od"],
                     barva_sekund=_pc(scr, "sekundy")["barva_od"], barva_datum=_pc(scr, "datum")["barva_od"]))
    elif t in ("hodiny_datum", "hodiny_pod_sebou"):
        E.append(_el("prstenec", x=4, y=4, w=232, h=232, senzor="@sekundy", min=0, max=59, pocet=60, start=0,
                     rozsah=360, tloustka=10, delitel=1, **_pc(scr, "sekundy")))
        date = bool(scr.get("datum"))
        if t == "hodiny_datum":
            y = 86 if date else 92
            E.append(_el("hodiny", x=22, y=y, w=196, h=56, format="HH:MM", velikost=60, pismo="Black",
                         zarovnani="stred", **_pc(scr, "hodiny")))
            if date:
                E.append(_el("hodiny", x=30, y=150, w=180, h=20, format="den D. M.", velikost=16, pismo="ExtraBold",
                             zarovnani="stred", **_pc(scr, "datum")))
        else:
            y = 40 if date else 48
            E += [_el("hodiny", x=40, y=y, w=160, h=70, format="HH", velikost=78, pismo="Black", zarovnani="stred",
                      **_pc(scr, "hodiny")),
                  _el("hodiny", x=40, y=y + 76, w=160, h=70, format="MM", velikost=78, pismo="Black",
                      zarovnani="stred", **_pc(scr, "minuty"))]
            if date:
                E.append(_el("hodiny", x=40, y=194, w=160, h=18, format="D. M.", velikost=15, pismo="ExtraBold",
                             zarovnani="stred", **_pc(scr, "datum")))
    elif t == "obrazek":
        E.append(_el("obrazek", x=0, y=0, w=240, h=240, soubor=scr.get("soubor", ""),
                     uprava=scr.get("uprava", SC.IMAGE_MODES[0]), **_pc(scr, "tvar")))
    elif t == "dlazdice":
        for n, (x, y) in zip("1234", ((4, 4), (122, 4), (4, 122), (122, 122))):
            c = _pc(scr, "dlazdice" + n)
            E += _tile(x, y, scr.get("nadpis" + n, ""), c["barva_od"], _slot(scr, n), _sval(scr, n),
                       c["barva_od"], c["barva_do"], tc)
    elif t == "cpu_detail":
        ak = _pc(scr, "akcent")
        E += [_el("graf", x=0, y=150, w=240, h=90, styl="pásek 3D", mrizka=True, tecka=True, cara=3,
                  delka_s=scr.get("delka_s", 120), **_slot(scr), **ak),
              _txt(14, 12, 145, 18, scr.get("nadpis", ""), 15, ak["barva_od"]),
              _txt(14, 32, 145, 12, scr.get("podnadpis", ""), 9, MUTED, "SemiBold"),
              _val(9, 46, 150, 76, _slot(scr), _sval(scr, "", "auto°"), 100, tc, "vlevo", 0.28)]
        for i, n in enumerate("123"):
            if scr.get("senzor" + n) or scr.get("popisek" + n):
                E += [_val(165, 21 + i * 39, 70, 20, _slot(scr, n), _sval(scr, n, ""), 20, tc),
                      _txt(165, 42 + i * 39, 70, 11, scr.get("popisek" + n, ""), 8, MUTED, "SemiBold")]
        E.append(_txt(176, 228, 50, 10, _span(scr), 8, MUTED, "Bold", "vpravo"))
    elif t == "chlazeni_radky":
        kc, kp, kv = _pc(scr, "kapalina"), _pc(scr, "pumpa"), _pc(scr, "ventilatory")
        lo, hi = scr.get("min", 20), scr.get("max", 60)
        liq = {"senzor": LIQ, "min": lo, "max": hi, "delitel": 1}
        E += [_txt(14, 12, 150, 16, "KAPALINA", 12, kc["barva_od"]),
              _val(11, 30, 218, 60, liq, {"desetinna_mista": 1, "jednotka": "°C"}, 75, tc, "vlevo", 0.3),
              _el("segmenty", x=12, y=108, w=216, h=13, pocet=20, vanicka=True, **liq, **kc),
              _txt(14, 125, 80, 10, f"{lo:g} °C", 7.5, MUTED, "SemiBold"),
              _txt(130, 125, 96, 10, "59 °C = 100 %", 7.5, "#ff6b6b", "Bold", "vpravo")]
        for y, lbl, key, cols in ((146, "PUMPA", "pumpa", kp), (192, "VENTILÁTORY", "ventilatory", kv)):
            E += [_txt(14, y, 110, 16, lbl, 11, cols["barva_od"]),
                  _el("sablona", x=150, y=y - 6, w=76, h=26, text=f"{{@{key}_vykon}} %", velikost=22,
                      pismo="ExtraBold", zarovnani="vpravo", **tc),
                  _el("sablona", x=96, y=y + 1, w=54, h=14, text=f"[{{@{key}}} ot/min]", velikost=9, pismo="SemiBold",
                      zarovnani="vpravo", **_one(MUTED)),
                  _el("bar", x=14, y=y + 26, w=212, h=7, senzor=f"@{key}_vykon", min=0, max=100, **cols)]
    elif t == "hodiny_stav":
        hc = _pc(scr, "hodiny")
        E += [_el("hodiny", x=0, y=14, w=240, h=76, format="HH:MM", velikost=85, zarovnani="stred", **hc),
              _el("bar", x=14, y=114, w=212, h=4, senzor="@sekundy", min=0, max=59, delitel=1, **hc)]
        if scr.get("datum", True):
            E.append(_el("hodiny", x=0, y=134, w=240, h=24, format="den datum", pismo="SemiBold", velikost=15,
                         zarovnani="stred", **_one("#cfd6de")))
        for n, x in zip("123", (14, 86, 158)):
            E += [_el("panel", x=x, y=170, w=68, h=56, zaobleni=9),
                  _txt(x + 8, 175, 52, 12, scr.get("nadpis" + n, ""), 8, _pc(scr, "stav" + n)["barva_od"]),
                  _val(x + 8, 192, 52, 28, _slot(scr, n), _sval(scr, n, "auto°"), 25, tc, "vlevo", 0.4)]
    elif t == "graf_plny":
        gc = _pc(scr, "graf")
        st = dict(_slot(scr), desetinna_mista=scr.get("desetinna", 0), jednotka="auto°",
                  delka_s=scr.get("delka_s", 120), velikost=11, pismo="Bold", zarovnani="vpravo", **tc)
        E += [_el("graf", x=0, y=80, w=240, h=160, styl="pásek 3D", hloubka=7, mrizka=True,
                  delka_s=scr.get("delka_s", 120), **_slot(scr), **gc),
              _txt(14, 13, 130, 16, scr.get("nadpis", ""), 13, gc["barva_od"]),
              _val(11, 30, 135, 52, _slot(scr), _sval(scr), 60, tc, "vlevo", 0.33),
              _el("statistika", x=130, y=13, w=96, h=14, funkce="max", popisek="max", **st),
              _el("statistika", x=130, y=29, w=96, h=14, funkce="min", popisek="min", **st),
              _txt(110, 46, 116, 10, "posledních " + _span(scr), 8, MUTED, "Bold", "vpravo")]
    elif t == "sit_disky":
        sc, dc = _pc(scr, "sit"), _pc(scr, "disky")
        E.append(_txt(14, 11, 60, 14, "SÍŤ", 11, sc["barva_od"]))
        for key, y, icon, col in (("senzor_dolu", 31, "šipka dolů", sc["barva_od"]),
                                  ("senzor_nahoru", 70, "šipka nahoru", sc["barva_do"])):
            s = {"senzor": scr.get(key) or "", "min": 0, "max": 10, "delitel": 1}
            E += [_el("ikona", x=8, y=y, w=26, h=26, ikona=icon, odznak=True, tloustka=3, **_one(col)),
                  _val(40, y - 1, 116, 30, s, {"desetinna_mista": scr.get("desetinna", 1), "jednotka": "MB/s"}, 30,
                       tc, "vlevo", 0.34),
                  _el("graf", x=159, y=y - 1, w=67, h=28, plocha=False, tecka=False, cara=2, auto_max=True,
                      delka_s=60, **s, **_one(col))]
        E += [_el("cara", x=14, y=110, w=212, h=4), _txt(14, 124, 80, 14, "DISKY", 11, dc["barva_od"])]
        for n, top in (("1", 145), ("2", 189)):
            letter = (scr.get("disk" + n) or "").strip()
            if not letter:
                continue
            E += [_txt(14, top + 2, 34, 22, letter, 20, white),
                  _el("bar", x=51, y=top + 2, w=175, h=7, senzor=f"@disk {letter} obsazeno", min=0, max=100,
                      delitel=1, **dc),
                  _el("sablona", x=51, y=top + 14, w=175, h=12, velikost=9, pismo="SemiBold", zarovnani="vlevo",
                      text=f"{{@disk {letter} volno}} GB volno[ · {{Teplota disku ({letter})}} °C]", **_one(MUTED))]
    elif t == "gpu_sloupce":
        cols = _pc(scr, "sloupce")
        E += [_txt(14, 12, 45, 18, scr.get("nadpis", "GPU"), 15, _pc(scr, "nadpis")["barva_od"]),
              _txt(60, 15, 166, 12, scr.get("podnadpis", ""), 9, MUTED, "SemiBold")]
        for i, n in enumerate("1234"):
            x = 14 + i * 55
            E += [_el("valec", x=x, y=42, w=47, h=135, **_slot(scr, n), **cols),
                  _val(x, 184, 47, 16, _slot(scr, n), _sval(scr, n, "auto°"), 15, tc, "stred", 0.6),
                  _txt(x - 2, 204, 51, 10, scr.get("nadpis" + n, ""), 7.5, MUTED, "Bold", "stred")]
    elif t == "velke_cislo":
        cols = _pc(scr, "segmenty")
        E += [_txt(16, 14, 130, 18, scr.get("nadpis", ""), 17, cols["barva_od"]),
              _txt(150, 17, 74, 12, scr.get("popisek", ""), 10, MUTED, "Bold", "vpravo"),
              _val(7, 40, 226, 112, _slot(scr), _sval(scr), 150, tc, "vlevo", 0.2),
              _el("segmenty", x=14, y=194, w=212, h=28, pocet=24, mezera=2, zaobleni=2, vanicka=True,
                  **_slot(scr), **cols),
              _txt(16, 226, 40, 10, f"{float(scr.get('min', 0)):g}", 7.5, MUTED, "Bold"),
              _txt(184, 226, 40, 10, f"{float(scr.get('max', 100)):g}", 7.5, MUTED, "Bold", "vpravo")]
    elif t == "hladina":
        E += [_el("hladina", x=3, y=3, w=234, h=234, **_slot(scr), **_pc(scr, "voda")),
              _txt(40, 52, 160, 16, scr.get("nadpis", ""), 12, "#bfefff", align="stred"),
              _val(30, 72, 180, 60, _slot(scr), {"desetinna_mista": scr.get("desetinna", 0), "jednotka": "auto°"},
                   65, tc, "stred", 0.3)]
        if scr.get("senzor") == LIQ:
            E.append(_el("sablona", x=40, y=160, w=160, h=16, text="[pumpa {@pumpa_vykon} %][ · {@pumpa} ot/min]",
                         velikost=11, pismo="Bold", zarovnani="stred", **_one("#e6fbff")))
    elif t == "graf_dokola":
        cols = _pc(scr, "paprsky")
        E += [_el("graf_dokola", x=10, y=10, w=220, h=220, kotouc=True, delka_s=scr.get("delka_s", 60),
                  **_slot(scr), **cols),
              _txt(70, 80, 100, 12, scr.get("nadpis", ""), 9, cols["barva_od"], align="stred"),
              _val(70, 94, 100, 44, _slot(scr), {"desetinna_mista": scr.get("desetinna", 0), "jednotka": "auto°"},
                   48, tc, "stred", 0.35),
              _txt(66, 142, 108, 10, "posledních " + _span(scr) + " dokola", 7.5, MUTED, "SemiBold", "stred")]
    elif t == "volne":
        E = copy.deepcopy(scr.get("prvky", []))
    return E


# ukazkove obrazovky pro sablony (vychozi senzory a rozsahy jako v okne nastaveni)
_TWO = {"nadpis1": "CPU", "senzor1": CPU, "min1": 0, "max1": 100, "nadpis2": "GPU", "senzor2": GPU, "min2": 0,
        "max2": 100}
_ONE = {"nadpis": "CPU", "senzor": CPU, "min": 0, "max": 100}
SAMPLES = {
    "dva_bary": _TWO, "oblouk": _ONE, "budik": _ONE, "dva_kruhy": _TWO, "graf": dict(_ONE, min=30, max=95),
    "hodiny": {}, "dva_oblouky": _TWO, "segmenty": _ONE,
    "ctyri_hodnoty": dict(_TWO, nadpis3="H₂O", senzor3=LIQ, min3=20, max3=60, nadpis4="ZÁTĚŽ",
                          senzor4="Celkové vytížení CPU", min4=0, max4=100),
    "chlazeni": {}, "graf_dva": dict(_TWO, min1=30, max1=95, min2=30, max2=90), "hodiny_analog": {"datum": True},
    "hodiny_datum": {"datum": True}, "hodiny_pod_sebou": {"datum": True},
    "obrazek": {"soubor": "kraken/ryzen7_odznak.png", "uprava": "beze změny"},
    "dlazdice": {"nadpis1": "CPU", "senzor1": CPU, "nadpis2": "GPU", "senzor2": GPU, "nadpis3": "RAM", "senzor3": RAM,
                 "max3": 32, "delitel3": 1024, "desetinna3": 1, "nadpis4": "KAPALINA", "senzor4": LIQ, "min4": 20,
                 "max4": 60},
    "cpu_detail": {"nadpis": "CPU", "podnadpis": "Tctl/Tdie", "senzor": CPU, "min": 30, "max": 95,
                   "senzor1": "Takt jader", "delitel1": 1000, "desetinna1": 1, "popisek1": "GHz takt",
                   "senzor2": "Celková spotřeba CPU", "popisek2": "W spotřeba",
                   "senzor3": "Celkové vytížení CPU", "popisek3": "% zátěž"},
    "chlazeni_radky": {"min": 20, "max": 60},
    "hodiny_stav": {"datum": True, "nadpis1": "CPU", "senzor1": CPU, "nadpis2": "GPU", "senzor2": GPU,
                    "nadpis3": "H₂O", "senzor3": LIQ},
    "graf_plny": {"nadpis": "CPU", "senzor": CPU, "min": 30, "max": 95},
    "sit_disky": {"senzor_dolu": "@síť stahování", "senzor_nahoru": "@síť odesílání", "desetinna": 1,
                  "disk1": "C:", "disk2": "D:"},
    "gpu_sloupce": {"nadpis": "GPU", "nadpis1": "TEPLOTA", "senzor1": GPU, "nadpis2": "ZÁTĚŽ",
                    "senzor2": "Zatížení jádra GPU", "nadpis3": "TAKT GHz", "senzor3": "Takt GPU", "max3": 3.2,
                    "delitel3": 1000, "desetinna3": 1, "nadpis4": "VRAM GB", "senzor4": "Přidělená paměť GPU",
                    "max4": 12, "delitel4": 1000, "desetinna4": 1},
    "velke_cislo": {"nadpis": "CPU", "popisek": "TEPLOTA", "senzor": CPU},
    "hladina": {"nadpis": "KAPALINA", "senzor": LIQ, "min": 20, "max": 60, "desetinna": 1},
    "graf_dokola": {"nadpis": "ZÁTĚŽ CPU", "senzor": "Celkové vytížení CPU", "delka_s": 60},
}


def templates():
    """{nazev: [prvky]} - vychozi rozvrzeni pro kazdy typ hotove obrazovky (z_obrazovky na ukazkovych
    senzorech) + prazdne."""
    out = {SC.TYPES[t]: from_screen(dict(s, typ=t)) for t, s in SAMPLES.items()}
    out["Prázdné"] = []
    return out
