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
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFont

import screens as SC

S = SC.S
WEIGHTS = ["Light", "SemiBold", "Bold", "ExtraBold", "Black"]
ALIGN = ["vlevo", "stred", "vpravo"]
CLOCK_FORMATS = ["HH:MM", "HH:MM:SS", "den", "datum", "den datum", "D. M. RRRR"]
TIME_SENSORS = ["@sekundy", "@minuty", "@hodiny"]
UNITS = ["auto", "°", "°C", "%", "GHz", "MHz", "W", "RPM", "GB", "MB/s", ""]
TRACK = "#1c1f24"
HISTORY_TYPES = ("graf", "graf_dokola")
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
    if u == "auto":
        u = (data.get(sensor) or {}).get("unit", "")
        u = UNIT_BY_DIV.get((u, int(div)), u if div == 1 else "")
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
        d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), 6 * S, outline=SC.DARK, width=S)
    vals = _hist(p, history)
    if len(vals) < 2:
        return
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
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
        return SC._rays3d(img, rays, w)
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
    return {"HH:MM": f"{now.hour:02d}:{now.minute:02d}", "HH:MM:SS": f"{now:%H:%M:%S}",
            "den": days[now.weekday()], "datum": f"{now.day}. {months[now.month - 1]}",
            "den datum": f"{days[now.weekday()]} {now.day}. {months[now.month - 1]}",
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
    _hand(d, cx, cy, (now.hour % 12 + now.minute / 60) * 30, 58 * S * k, 11 * S * k, hc, 10 * S * k)
    _hand(d, cx, cy, (now.minute + now.second / 60) * 6, 88 * S * k, 7 * S * k, hc, 12 * S * k)
    if p.get("sekundy", True):
        _hand(d, cx, cy, now.second * 6, 96 * S * k, max(1, 3 * S * k), sc, 22 * S * k)
        d.ellipse((cx - 9 * S * k, cy - 9 * S * k, cx + 9 * S * k, cy + 9 * S * k), fill=sc)
        d.ellipse((cx - 3 * S * k, cy - 3 * S * k, cx + 3 * S * k, cy + 3 * S * k), fill=SC.BLACK)


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


DRAW = {"panel": draw_panel, "text": draw_text, "hodnota": draw_value, "bar": draw_bar, "segmenty": draw_segments,
        "oblouk": draw_arc, "prstenec": draw_ring, "budik": draw_gauge, "graf": draw_graph,
        "graf_dokola": draw_radial, "hladina": draw_level, "hodiny": draw_clock, "rucicky": draw_analog,
        "obrazek": draw_image}
TYPES = {"panel": "Panel (podklad)", "text": "Text", "hodnota": "Hodnota senzoru", "bar": "Bar",
         "segmenty": "Segmentový bar", "oblouk": "Oblouk", "prstenec": "Segmentový prstenec",
         "budik": "Budík s ručičkou", "graf": "Graf v čase", "graf_dokola": "Graf dokola", "hladina": "Hladina",
         "hodiny": "Hodiny / datum", "rucicky": "Ručičkové hodiny", "obrazek": "Obrázek / logo"}


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
FIELDS = {
    "panel": [("barva", "Barva", "color", None), ("zaobleni", "Zaoblení rohů (px)", "num", None),
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
                         ("zaobleni", "Zaoblení (px)", "num", None), ("smer", "Směr", "choice", ["vodorovne", "svisle"])]
                + _COLS + [("podklad", "Zhasnutý segment", "color", None)],
    "oblouk": _SENS + _ARC + [("opacne", "Plnit od konce", "bool", None),
                              ("zaoblene_konce", "Zaoblené konce", "bool", None),
                              ("ztlumene_pozadi", "Podklad ztlumeně v barvách", "bool", None)]
              + _COLS + [("podklad", "Podklad", "color", None)],
    "prstenec": _SENS + [("pocet", "Počet segmentů", "int", None)] + _ARC + _COLS,
    "budik": _SENS + _ARC + _COLS + [("barva_rucicky", "Ručička", "color", None)],
    "graf": _SENS + [("delka_s", "Délka (s)", "int", None), ("cara", "Tloušťka čáry (px)", "num", None),
                     ("plocha", "Plocha pod čarou", "bool", None), ("tecka", "Tečka na konci", "bool", None),
                     ("ramecek", "Rámeček", "bool", None)] + _COLS,
    "graf_dokola": _SENS + [("delka_s", "Délka (s)", "int", None)] + _COLS,
    "hladina": _SENS + _COLS + [("barva_okraje", "Okraj", "color", None)],
    "hodiny": [("format", "Formát", "choice", CLOCK_FORMATS)] + _FONT + _COLS,
    "rucicky": [("barva_od", "Ciferník", "color", None), ("barva_do", "Ručičky", "color", None),
                ("sekundy", "Sekundová ručička", "bool", None), ("barva_sekund", "Sekundová ručička", "color", None)],
    "obrazek": [("soubor", "Obrázek", "image", None), ("uprava", "Úprava", "mode", None),
                ("barva_od", "Barva tvaru (jen tvar)", "color", None), ("barva_do", "Barva tvaru – do", "color", None)],
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
    "graf": dict(x=0, y=120, w=240, h=120, delka_s=120, cara=3, plocha=True, tecka=True, ramecek=False,
                 barva_od="#3cff3c", barva_do="#ffb020", senzor="CPU (Tctl/Tdie)", min=30, max=95, delitel=1),
    "graf_dokola": dict(x=20, y=20, w=200, h=200, delka_s=60, barva_od="#a855f7", barva_do="#ff3b8a",
                        senzor="Celkové vytížení CPU", min=0, max=100, delitel=1),
    "hladina": dict(x=10, y=10, w=220, h=220, barva_od="#22d3ee", barva_do="#1d4ed8", barva_okraje="#16252d",
                    senzor="@kapalina", min=20, max=60, delitel=1),
    "hodiny": dict(x=0, y=80, w=240, h=70, format="HH:MM", pismo="ExtraBold", velikost=80, zarovnani="stred",
                   barva_od="#ffffff", barva_do="#ffffff"),
    "rucicky": dict(x=10, y=10, w=220, h=220, barva_od="#ffffff", barva_do="#ffffff", sekundy=True,
                    barva_sekund="#ff3c28"),
    "obrazek": dict(x=20, y=20, w=200, h=200, soubor="kraken/ryzen7_odznak.png", uprava="beze změny",
                    barva_od="#ffffff", barva_do="#ffffff"),
}


def new(typ):
    p = copy.deepcopy(NEW[typ])
    p["typ"] = typ
    return p


def label(p):
    """Popis prvku pro seznam v editoru."""
    t = TYPES.get(p.get("typ"), p.get("typ", "?"))
    extra = p.get("text") or (p.get("format") if p.get("typ") == "hodiny" else "") or p.get("senzor") \
        or os.path.splitext(os.path.basename(p.get("soubor", "")))[0]
    return f"{t}: {extra}".rstrip(": ")


def history_sensors(items):
    """{senzor: delka_s} prvku, ktere kresli historii."""
    out = {}
    for p in items:
        if p.get("typ") in HISTORY_TYPES and p.get("senzor"):
            out[p["senzor"]] = max(out.get(p["senzor"], 0), _num(p, "delka_s", 120))
    return out


# ------------------------------------------------------------ sablony
def _el(typ, **kw):
    p = new(typ)
    p.update(kw)
    return p


CPU, GPU, RAM, LIQ = "CPU (Tctl/Tdie)", "Teplota GPU", "Použitá fyzická paměť", "@kapalina"


def _tile(x, y, label, color, sensor, lo, hi, c1, c2, div=1, dec=0):
    return [_el("panel", x=x, y=y, w=114, h=114),
            _el("text", x=x + 11, y=y + 9, w=92, h=16, text=label, velikost=11, barva_od=color, barva_do=color),
            _el("hodnota", x=x + 11, y=y + 34, w=92, h=48, senzor=sensor, delitel=div, desetinna_mista=dec,
                velikost=48 if dec == 0 else 36, min=lo, max=hi),
            _el("bar", x=x + 11, y=y + 96, w=92, h=6, senzor=sensor, delitel=div, min=lo, max=hi, barva_od=c1,
                barva_do=c2)]


def templates():
    """{nazev: [prvky]} - vychozi rozvrzeni slozena z prvku podle existujicich obrazovek."""
    chips = []
    for x, (lbl, col, sensor) in zip((14, 86, 158), (("CPU", "#ffb020", CPU), ("GPU", "#7aa8ff", GPU),
                                                    ("H₂O", "#22d3ee", LIQ))):
        chips += [_el("panel", x=x, y=170, w=68, h=56, zaobleni=9),
                  _el("text", x=x + 8, y=175, w=52, h=12, text=lbl, velikost=8, barva_od=col, barva_do=col),
                  _el("hodnota", x=x + 8, y=192, w=52, h=28, senzor=sensor, jednotka="°", velikost=25)]
    return {
        "Čtyři dlaždice": (_tile(4, 4, "CPU", "#3cff3c", CPU, 0, 100, "#3cff3c", "#ff3b3b")
                          + _tile(122, 4, "GPU", "#7aa8ff", GPU, 0, 100, "#3b82f6", "#a855f7")
                          + _tile(4, 122, "RAM", "#c084fc", RAM, 0, 32, "#a855f7", "#ec4899", div=1024, dec=1)
                          + _tile(122, 122, "KAPALINA", "#22d3ee", LIQ, 20, 60, "#22d3ee", "#3b82f6")),
        "Hodiny a stav": [
            _el("hodiny", x=0, y=14, w=240, h=76, format="HH:MM", velikost=85, zarovnani="stred",
                barva_od="#3cff3c", barva_do="#22d3ee"),
            _el("bar", x=14, y=112, w=212, h=4, senzor="@sekundy", min=0, max=59, barva_od="#3cff3c",
                barva_do="#22d3ee"),
            _el("hodiny", x=0, y=124, w=240, h=24, format="den datum", pismo="SemiBold", velikost=15,
                zarovnani="stred", barva_od="#cfd6de", barva_do="#cfd6de")] + chips,
        "Dva oblouky": [
            _el("oblouk", x=6, y=6, w=228, h=228, start=195, rozsah=150, tloustka=18, senzor=CPU,
                barva_od="#3cff3c", barva_do="#ff3b3b", podklad="#2a2d33"),
            _el("oblouk", x=6, y=6, w=228, h=228, start=15, rozsah=150, tloustka=18, opacne=True, senzor=GPU,
                barva_od="#3b82f6", barva_do="#a855f7", podklad="#2a2d33"),
            _el("text", x=50, y=52, w=140, h=16, text="CPU", velikost=14, zarovnani="stred", barva_od="#3cff3c",
                barva_do="#3cff3c"),
            _el("hodnota", x=50, y=68, w=140, h=48, senzor=CPU, jednotka="°", velikost=54, zarovnani="stred"),
            _el("hodnota", x=50, y=126, w=140, h=48, senzor=GPU, jednotka="°", velikost=54, zarovnani="stred"),
            _el("text", x=50, y=174, w=140, h=16, text="GPU", velikost=14, zarovnani="stred", barva_od="#7aa8ff",
                barva_do="#7aa8ff")],
        "Chlazení": [
            _el("text", x=14, y=12, w=150, h=16, text="KAPALINA", velikost=12, barva_od="#22d3ee", barva_do="#22d3ee"),
            _el("hodnota", x=11, y=30, w=218, h=60, senzor=LIQ, desetinna_mista=1, jednotka="°C", velikost=75),
            _el("segmenty", x=14, y=110, w=212, h=9, senzor=LIQ, min=20, max=60),
            _el("text", x=14, y=144, w=110, h=16, text="PUMPA", velikost=11, barva_od="#22d3ee", barva_do="#22d3ee"),
            _el("hodnota", x=140, y=138, w=86, h=26, senzor="@pumpa_vykon", jednotka="%", velikost=22,
                zarovnani="vpravo"),
            _el("bar", x=14, y=170, w=212, h=7, senzor="@pumpa_vykon", barva_od="#22d3ee", barva_do="#3b82f6"),
            _el("text", x=14, y=190, w=130, h=16, text="VENTILÁTORY", velikost=11, barva_od="#ff9f43",
                barva_do="#ff9f43"),
            _el("hodnota", x=140, y=184, w=86, h=26, senzor="@ventilatory_vykon", jednotka="%", velikost=22,
                zarovnani="vpravo"),
            _el("bar", x=14, y=216, w=212, h=7, senzor="@ventilatory_vykon", barva_od="#ffb020", barva_do="#ff6b35")],
        "Budík": [
            _el("budik", x=20, y=14, w=200, h=200, senzor=CPU),
            _el("hodnota", x=60, y=136, w=120, h=44, senzor=CPU, jednotka="°", velikost=40, zarovnani="stred"),
            _el("text", x=60, y=186, w=120, h=18, text="CPU", velikost=15, zarovnani="stred")],
        "Hodnota a graf": [
            _el("text", x=14, y=12, w=150, h=18, text="CPU", velikost=14, barva_od="#3cff3c", barva_do="#3cff3c"),
            _el("hodnota", x=11, y=30, w=180, h=56, senzor=CPU, jednotka="°C", velikost=62),
            _el("graf", x=0, y=96, w=240, h=144, senzor=CPU, min=30, max=95)],
        "Hladina": [
            _el("hladina", x=6, y=6, w=228, h=228),
            _el("text", x=40, y=50, w=160, h=16, text="KAPALINA", velikost=12, zarovnani="stred", barva_od="#bfefff",
                barva_do="#bfefff"),
            _el("hodnota", x=30, y=74, w=180, h=60, senzor=LIQ, desetinna_mista=1, jednotka="°", velikost=62,
                zarovnani="stred")],
        "Sekundový prstenec": [
            _el("prstenec", x=4, y=4, w=232, h=232, senzor="@sekundy", min=0, max=59, pocet=60, start=0, rozsah=360,
                tloustka=5, barva_od="#28c8ff", barva_do="#ff28c8"),
            _el("hodiny", x=30, y=88, w=180, h=54, format="HH:MM", velikost=58, zarovnani="stred"),
            _el("hodiny", x=30, y=146, w=180, h=20, format="den datum", pismo="SemiBold", velikost=13,
                zarovnani="stred", barva_od="#b4b4b4", barva_do="#b4b4b4")],
        "Prázdné": [],
    }
