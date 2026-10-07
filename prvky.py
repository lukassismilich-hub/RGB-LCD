# prvky.py - graficke prvky pro monochromaticky displej Alphacool 240x128 (1 bit)
#
# Rozvrzeni = seznam prvku v config["alphacool"]["prvky"], kresli se v tom poradi
# (na vysku - otoceni 90/270 - ma vlastni rozvrzeni 128x240 v "prvky_na_vysku")
# (pozdejsi prvek je navrchu). Kazdy prvek ma typ, polohu x, y a velikost w, h
# v bodech displeje. Kresli se bez vyhlazovani, "sede" plochy jsou rastr.
#
# Typy (a jejich styly):
#   text      popisek a/nebo hodnota senzoru, zarovnani, pismo
#   cislo     velke cislo s jednotkou a popiskem
#   hodiny    cas / datum v ruznych formatech
#   bar       styl plny | segmenty | rysky (s ryskami a maximem) | rastr; 2. senzor = rozdeleny bar
#   sloupce   svisle sloupce pro vic senzoru (napr. jadra CPU)
#   graf      styl plocha | sloupce | mrizka
#   budik     pulkruh s ryskami a rucickou
#   prstenec  kruh ze segmentu
#   oblouk    tlusty oblouk, podklad rastr
#   ikona     pixelova ikona 11x11 (meritko 1-3)
#   obrazek   PNG/BMP/JPG ze slozky obrazky/ -> 1 bit (prah nebo rastr), pruhlednost z alfa kanalu
#   cara      vodorovna / svisla
#   obdelnik  ramecek, plny nebo rastr (napr. pruh pod hodiny)
# Sci-fi prvky (segmentove cislo, terminal, LCARS, radar, ...) a hotove obrazovky: prvky_scifi.py

import glob
import math
import os
import time
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFont

WIDTH, HEIGHT = 240, 128
# otoceni = jak je displej namontovany: 90 = otoceny doprava (po smeru hodin), 270 = doleva
ROTATIONS = {0: "0° (na šířku)", 90: "90° – na výšku, otočený doprava", 180: "180° (vzhůru nohama)",
             270: "270° – na výšku, otočený doleva"}


def rotation(acfg):
    try:
        r = int(acfg.get("otoceni", 0)) % 360
    except (TypeError, ValueError):
        return 0
    return r if r in ROTATIONS else 0


def portrait(acfg):
    return rotation(acfg) in (90, 270)


def layout_key(acfg):
    return "prvky_na_vysku" if portrait(acfg) else "prvky"


def items(acfg):
    """Prvky rozvrzeni pro aktualni otoceni."""
    return acfg.get(layout_key(acfg), [])


def canvas_size(acfg):
    """Velikost kresleni tak, jak displej vidi uzivatel (na vysku 128x240)."""
    return (HEIGHT, WIDTH) if portrait(acfg) else (WIDTH, HEIGHT)


def to_panel(img, acfg):
    """Nakresleny obrazek -> obrazek 240x128 v orientaci panelu."""
    r = rotation(acfg)
    return img.rotate(r, expand=True) if r else img
BASE = os.path.dirname(os.path.abspath(__file__))
MISSING = "–"
DAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]

# ---------------------------------------------------------------- pisma

_index = None
_font_cache = {}
DEFAULT_FAMILY = "Terminus (TTF)"                  # ostre ve 12, 14, 16, ... 32 px, i tucne, cestina
SMALL_FAMILY = "Micro 5"                           # drobne popisky, ostre v 11 px
FALLBACK = (DEFAULT_FAMILY, "Departure Mono", "Pixel Operator")


def _font_dirs():
    """Jen pisma aplikace (fonts/) - pisma Windows se na 1 bitu kresli nerovne."""
    return [os.path.join(BASE, "fonts")]


def font_index():
    """{rodina: {"regular": cesta, "bold": cesta}} ze slozky fonts/."""
    global _index
    if _index is not None:
        return _index
    idx = {}
    seen = set()
    for d in _font_dirs():
        for ext in ("ttf", "otf", "ttc", "otb"):
            for path in glob.glob(os.path.join(d, f"*.{ext}")):
                key = os.path.normcase(path)
                if key in seen:
                    continue
                seen.add(key)
                fam = None
                for size in (10, 8, 12, 16):          # bitmapova pisma (.otb) maji jen svou velikost
                    try:
                        fam, style = ImageFont.truetype(path, size).getname()
                        break
                    except Exception:
                        continue
                if fam is None:
                    continue
                s = (style or "").lower()
                slot = idx.setdefault(fam, {})
                if s in ("regular", "normal", "book", "roman", "medium") and "regular" not in slot:
                    slot["regular"] = path
                elif s == "bold":
                    slot["bold"] = path
                else:
                    slot.setdefault("jine", path)
    for fam, slot in list(idx.items()):
        slot.setdefault("regular", slot.get("jine") or slot.get("bold"))
        if not slot["regular"]:
            del idx[fam]
    _index = idx
    return idx


def font_families():
    return sorted(font_index(), key=str.lower)


def get_font(spec):
    """spec = {"rodina", "velikost", "tucne"} -> ImageFont (s nahradnim pismem)."""
    spec = spec or {}
    fam = spec.get("rodina", DEFAULT_FAMILY)
    px = max(5, int(spec.get("velikost", 11)))
    bold = bool(spec.get("tucne"))
    k = (fam, px, bold)
    if k not in _font_cache:
        idx = font_index()
        slot = idx.get(fam) or next((idx[f] for f in FALLBACK if f in idx), None)
        if slot is None:
            _font_cache[k] = ImageFont.load_default()
        else:
            path = slot.get("bold") if bold and slot.get("bold") else slot["regular"]
            try:
                _font_cache[k] = ImageFont.truetype(path, px)
            except OSError:                        # bitmapove pismo (.otb) jen ve sve velikosti
                for size in (8, 12, 16, 24, 32):
                    try:
                        _font_cache[k] = ImageFont.truetype(path, size)
                        break
                    except OSError:
                        continue
                else:
                    _font_cache[k] = ImageFont.load_default()
    return _font_cache[k]


# ----------------------------------------------------------- hodnoty

def value(data, sensor, divisor=1):
    item = data.get(sensor) if sensor else None
    if item is None:
        return None
    try:
        return item["value"] / (float(divisor) or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def unit(data, sensor, u):
    if u == "auto":
        return (data.get(sensor) or {}).get("unit", "")
    return u or ""


def fmt(v, decimals, u=""):
    return MISSING if v is None else f"{v:.{int(decimals)}f}{u}"


def frac(v, lo, hi):
    if v is None or hi == lo:
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _num(p, key, default):
    try:
        return float(p.get(key, default))
    except (TypeError, ValueError):
        return default


def _val(p, data, key="senzor"):
    return value(data, p.get(key), p.get("delitel", 1))


def _frac(p, data, key="senzor"):
    return frac(_val(p, data, key), _num(p, "min", 0), _num(p, "max", 100))


def _text_value(p, data):
    v = _val(p, data)
    return fmt(v, p.get("desetinna_mista", 0), unit(data, p.get("senzor"), p.get("jednotka", "auto")))


# ------------------------------------------------------------ pomucky

def _checker(img, box, mask=None):
    """rastr (sachovnice) v obdelniku; s maskou jen tam, kde je maska."""
    x0, y0, x1, y1 = (int(v) for v in box)
    pat = Image.new("1", img.size, 0)
    pd = pat.load()
    for y in range(max(0, y0), min(img.height - 1, y1) + 1):
        for x in range(max(0, x0), min(img.width - 1, x1) + 1):
            if (x + y) % 2 == 0:
                pd[x, y] = 1
    if mask is not None:
        pat = ImageChops.logical_and(pat, mask)
    img.paste(1, (0, 0), pat)


def _hist_cols(vals, n):
    out = []
    if not vals or n <= 0:
        return out
    for x in range(n):
        a = int(x * len(vals) / n)
        b = max(a + 1, int((x + 1) * len(vals) / n))
        chunk = vals[a:b]
        out.append(sum(chunk) / len(chunk))
    return out


def _center_text(d, cx, cy, text, font, fill):
    d.text((cx, cy), text, font=font, fill=fill, anchor="mm")


_peaks = {}           # senzor -> (maximum, cas) pro bar s ryskami
PEAK_HOLD_S = 10


def _peak(sensor, v):
    now = time.monotonic()
    old = _peaks.get(sensor)
    if v is None:
        return old[0] if old else None
    if old is None or v >= old[0] or now - old[1] > PEAK_HOLD_S:
        _peaks[sensor] = (v, now)
        return v
    return old[0]


# ------------------------------------------------------------- prvky

def draw_text(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo"))
    parts = []
    if p.get("popisek"):
        parts.append(p["popisek"])
    if p.get("senzor"):
        parts.append(_text_value(p, data))
    text = " ".join(parts)
    al = p.get("zarovnani", "vlevo")
    ax = {"vlevo": x, "stred": x + w / 2, "vpravo": x + w}[al]
    anchor = {"vlevo": "lm", "stred": "mm", "vpravo": "rm"}[al]
    d.text((ax, y + h / 2), text, font=f, fill=int(p.get("barva", 1)), anchor=anchor)


def draw_number(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    fill = int(p.get("barva", 1))
    v = _val(p, data)
    txt = fmt(v, p.get("desetinna_mista", 0))
    fb = get_font(p.get("pismo", _f(36, True)))
    fs = get_font(p.get("pismo_male", _f(11)))
    d.text((x, y), txt, font=fb, fill=fill, anchor="lt")
    right = x + d.textlength(txt, font=fb) + 2
    u = unit(data, p.get("senzor"), p.get("jednotka", "auto"))
    top = d.textbbox((x, y), txt, font=fb, anchor="lt")
    if u:
        d.text((right, top[1]), u, font=fs, fill=fill, anchor="lt")
    if p.get("popisek"):
        d.text((right, top[3]), p["popisek"], font=fs, fill=fill, anchor="lb")


def draw_clock(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo"))
    fmt_ = p.get("format", "HH:MM:SS")
    texts = {"HH:MM:SS": now.strftime("%H:%M:%S"), "HH:MM": now.strftime("%H:%M"),
             "datum": now.strftime("%d.%m.%Y"), "den datum": f"{DAYS[now.weekday()]} {now:%d.%m.%Y}",
             "den": DAYS[now.weekday()], "HH:MM datum": now.strftime("%H:%M  %d.%m.")}
    text = texts.get(fmt_, texts["HH:MM:SS"])
    al = p.get("zarovnani", "vlevo")
    ax = {"vlevo": x, "stred": x + w / 2, "vpravo": x + w}[al]
    anchor = {"vlevo": "lm", "stred": "mm", "vpravo": "rm"}[al]
    d.text((ax, y + h / 2), text, font=f, fill=int(p.get("barva", 1)), anchor=anchor)


def _bar(img, d, box, fr, style, peak_fr=None):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if style == "segmenty":
        seg, gap = max(2, int(p_seg(h))), 1
        n = max(1, (w + gap) // (seg + gap))
        on = round(n * fr)
        for i in range(n):
            sx = x0 + i * (seg + gap)
            if i < on:
                d.rectangle((sx, y0, sx + seg - 1, y1), fill=1)
            else:
                d.rectangle((sx, y1 - 1 if h > 3 else y1, sx + seg - 1, y1), fill=1)
    elif style == "rysky":
        bh = max(1, h - 5)
        d.rectangle((x0, y0 + 2, x0 + round(w * fr), y0 + 2 + bh - 1), fill=1) if fr > 0 else None
        base = y1 - 2
        d.line((x0, base, x1, base), fill=1)
        for i in range(11):
            tx = x0 + round(w * i / 10)
            d.line((tx, base, tx, base + (2 if i % 5 == 0 else 1)), fill=1)
        if peak_fr is not None:
            px = x0 + round(w * peak_fr)
            d.line((px, y0, px, y0 + 2 + bh - 1), fill=1)
            d.line((px - 1, y0, px + 1, y0), fill=1)
    elif style == "rastr":
        _checker(img, box)
        if fr > 0:
            d.rectangle((x0, y0, x0 + round(w * fr), y1), fill=1)
    else:                                              # plny s rameckem
        d.rectangle(box, outline=1)
        if fr > 0 and w > 4 and h > 3:
            d.rectangle((x0 + 2, y0 + 2, x0 + 2 + round((w - 4) * fr), y1 - 2), fill=1)


def p_seg(h):
    return 3 if h < 6 else 4


def draw_bar(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    style = p.get("styl", "plny")
    boxes = [(x, y, x + w - 1, y + h - 1)]
    keys = ["senzor"]
    if p.get("senzor2"):                               # rozdeleny bar: dve hodnoty pod sebou
        hh = (h - 2) // 2
        boxes = [(x, y, x + w - 1, y + hh - 1), (x, y + hh + 2, x + w - 1, y + 2 * hh + 1)]
        keys = ["senzor", "senzor2"]
    for box, key in zip(boxes, keys):
        v = _val(p, data, key)
        fr = frac(v, _num(p, "min", 0), _num(p, "max", 100))
        pk = None
        if style == "rysky":
            pv = _peak(p.get(key), v)
            pk = frac(pv, _num(p, "min", 0), _num(p, "max", 100)) if pv is not None else None
        _bar(img, d, box, fr, style, pk)


def draw_columns(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    sensors = [s for s in p.get("senzory", []) if s]
    if not sensors:
        d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)
        return
    n = len(sensors)
    gap = 2 if w >= n * 5 else 1
    bw = max(1, (w - (n - 1) * gap) // n)
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    for i, s in enumerate(sensors):
        bx = x + i * (bw + gap)
        fr = frac(value(data, s, p.get("delitel", 1)), lo, hi)
        top = y + h - 1 - round((h - 1) * fr)
        if p.get("ramecek", True):
            d.rectangle((bx, y, bx + bw - 1, y + h - 1), outline=1)
        if fr > 0:
            d.rectangle((bx, top, bx + bw - 1, y + h - 1), fill=1)


def draw_graph(img, d, p, data, now, history):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    style = p.get("styl", "plocha")
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    div = _num(p, "delitel", 1) or 1
    vals = [v / div for v in (history or {}).get(p.get("senzor"), [])]
    frame = p.get("ramecek", True)
    x0, y0, x1, y1 = x, y, x + w - 1, y + h - 1
    if frame:
        d.rectangle((x0, y0, x1, y1), outline=1)
        x0, y0, x1, y1 = x0 + 2, y0 + 2, x1 - 2, y1 - 2
    iw, ih = x1 - x0 + 1, y1 - y0
    if style == "mrizka":
        for gy in range(5):
            yy = y0 + round(ih * gy / 4)
            for xx in range(x0, x1 + 1, 3):
                img.putpixel((xx, yy), 1)
        for gx in range(1, 6):
            xx = x0 + round((iw - 1) * gx / 6)
            for yy in range(y0, y1 + 1, 3):
                img.putpixel((xx, yy), 1)
    if len(vals) < 2 or iw < 2 or ih < 2:
        return
    if style == "sloupce":
        step = 3 if iw >= 30 else 2
        cols = _hist_cols(vals, iw // step)
        if not frame:
            d.line((x0, y1, x1, y1), fill=1)
        for i, v in enumerate(cols):
            bx = x0 + i * step
            top = y1 - round(ih * frac(v, lo, hi))
            d.rectangle((bx, top, bx + step - 2, y1), fill=1)
        return
    cols = _hist_cols(vals, iw)
    pts = [(x0 + i, y1 - round(ih * frac(v, lo, hi))) for i, v in enumerate(cols)]
    if style == "plocha":
        area = Image.new("1", img.size, 0)
        ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], y1), (pts[0][0], y1)], fill=1)
        _checker(img, (x0, y0, x1, y1), area)
        d.line(pts, fill=1, width=2)
    else:
        d.line(pts, fill=1, width=1)


def _value_center(d, p, data, cx, cy):
    if not p.get("hodnota", True):
        return
    f = get_font(p.get("pismo", _f(16, True)))
    _center_text(d, cx, cy, _text_value(p, data), f, 1)
    if p.get("popisek"):
        fs = get_font(p.get("pismo_male", _f(9)))
        bb = d.textbbox((cx, cy), "0", font=f, anchor="mm")
        d.text((cx, bb[3] + 2), p["popisek"], font=fs, fill=1, anchor="mt")


def draw_gauge(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo", _f(12, True)))
    txt_h = (6 + d.textbbox((0, 0), "0°", font=f, anchor="lt")[3]) if p.get("hodnota", True) else 2
    r = max(6, min(w / 2 - 1, h - txt_h - 1))
    cx, cy = x + w / 2, y + r + 1
    d.arc((cx - r, cy - r, cx + r, cy + r), 180, 360, fill=1, width=2)
    for i in range(11):
        a = math.radians(180 + 18 * i)
        big = i % 5 == 0
        r1, r2 = r - 3, r - (min(9, r / 3) if big else min(6, r / 4))
        d.line((cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)),
               fill=1, width=2 if big else 1)
    a = math.radians(180 + 180 * _frac(p, data))
    rn = r - min(11, r / 3 + 2)
    d.line((cx, cy, cx + rn * math.cos(a), cy + rn * math.sin(a)), fill=1, width=2)
    d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=1)
    if p.get("hodnota", True):
        txt = (p.get("popisek", "") + " " if p.get("popisek") else "") + _text_value(p, data)
        d.text((cx, cy + 5), txt, font=f, fill=1, anchor="mt")


def draw_ring(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    r = max(4, min(w, h) / 2 - 1)
    cx, cy = x + w / 2, y + h / 2
    n = max(4, int(_num(p, "segmenty", 20)))
    span = _num(p, "uhel", 270)
    start = 90 + (360 - span) / 2
    thick = max(2, int(_num(p, "tloustka", 6)))
    on = round(n * _frac(p, data))
    step = span / n
    gapdeg = min(3.0, step / 3)
    box = (cx - r, cy - r, cx + r, cy + r)
    for i in range(n):
        a0, a1 = start + i * step + gapdeg / 2, start + (i + 1) * step - gapdeg / 2
        d.arc(box, a0, a1, fill=1, width=thick if i < on else 1)
    _value_center(d, p, data, cx, cy)


def draw_arc(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    r = max(4, min(w, h) / 2 - 1)
    cx, cy = x + w / 2, y + h / 2
    span = _num(p, "uhel", 240)
    start = 90 + (360 - span) / 2
    thick = max(2, int(_num(p, "tloustka", 8)))
    box = (cx - r, cy - r, cx + r, cy + r)
    mask = Image.new("1", img.size, 0)
    ImageDraw.Draw(mask).arc(box, start, start + span, fill=1, width=thick)
    _checker(img, (cx - r, cy - r, cx + r, cy + r), mask)
    fr = _frac(p, data)
    if fr > 0:
        d.arc(box, start, start + span * fr, fill=1, width=thick)
    _value_center(d, p, data, cx, cy)


# pixelove ikony 11x11 ("#" = bod)
ICONS = {
    "teplomer": ["....###....", "...#...#...", "...#.#.#...", "...#.#.#...", "...#.#.#...",
                 "...#.#.#...", "..#.###.#..", ".#.#####.#.", ".#.#####.#.", "..#.###.#..", "...#####..."],
    "cpu": [".#.#.#.#.#.", "###########", ".#.......#.", "##.#####.##", ".#.#...#.#.", "##.#...#.##",
            ".#.#...#.#.", "##.#####.##", ".#.......#.", "###########", ".#.#.#.#.#."],
    "gpu": ["...........", "##########.", "#........##", "#.###.##..#", "#.#.#.##..#", "#.###.....#",
            "#........##", "##########.", ".#.#.#.#...", "...........", "..........."],
    "ram": ["...........", "...........", "###########", "#.#.#.#.#.#", "#.#.#.#.#.#", "#.#.#.#.#.#",
            "###########", ".#.#.#.#.#.", "...........", "...........", "..........."],
    "disk": ["###########", "#.........#", "#..#####..#", "#.#.....#.#", "#.#..#..#.#", "#.#.....#.#",
             "#..#####..#", "#.........#", "#.......#.#", "#.........#", "###########"],
    "sit": ["....#......", "...###.....", "..#.#.#....", "....#......", "....#...#..", "....#...#..",
            "....#...#..", "......#.#.#", ".......###.", "........#..", "..........."],
    "ventilator": ["...#####...", "..#.....#..", ".#.##....#.", "#..###...##", "#...##..#.#", "#....#....#",
                   "#.#..##...#", "##...###..#", ".#....##.#.", "..#.....#..", "...#####..."],
    "kapka": [".....#.....", ".....#.....", "....###....", "....###....", "...#####...", "..#######..",
              "..#.#####..", "..#.#####..", "..##.####..", "...#####...", "....###...."],
    "blesk": ["......##...", ".....##....", "....##.....", "...##......", "..#######..", ".....##....",
              "....##.....", "...##......", "..##.......", ".##........", "..........."],
}


def draw_icon(img, d, p, data, now):
    rows = ICONS.get(p.get("nazev", "cpu"), ICONS["cpu"])
    k = max(1, int(_num(p, "meritko", 1)))
    fill = int(p.get("barva", 1))
    for j, row in enumerate(rows):
        for i, c in enumerate(row):
            if c == "#":
                d.rectangle((p["x"] + i * k, p["y"] + j * k, p["x"] + i * k + k - 1, p["y"] + j * k + k - 1),
                            fill=fill)


def draw_line(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    t = max(1, int(_num(p, "tloustka", 1)))
    fill = int(p.get("barva", 1))
    if p.get("smer", "vodorovna") == "svisla":
        d.rectangle((x, y, x + t - 1, y + h - 1), fill=fill)
    else:
        d.rectangle((x, y, x + w - 1, y + t - 1), fill=fill)


def draw_rect(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    box = (x, y, x + w - 1, y + h - 1)
    fill = p.get("vypln", "zadna")
    col = int(p.get("barva", 1))
    if fill == "plna":
        d.rectangle(box, fill=col)
    elif fill == "rastr":
        _checker(img, box)
    else:
        d.rectangle(box, outline=col)
        if p.get("dvojity"):
            d.rectangle((x + 2, y + 2, x + w - 3, y + h - 3), outline=col)


IMAGES_DIR = os.path.join(BASE, "obrazky")
_img_cache = {}


def image_path(name):
    """Cesta k obrazku: relativni = ze slozky obrazky/."""
    if not name:
        return ""
    return name if os.path.isabs(name) else os.path.join(IMAGES_DIR, name)


def load_mask(p):
    """Obrazek prvku jako maska "1" (1 = rozsvitit) ve velikosti, v jake se nakresli."""
    path = image_path(p.get("soubor", ""))
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    fit = p.get("velikost", "puvodni")
    key = (path, mtime, fit, p["w"], p["h"], int(_num(p, "prah", 128)), bool(p.get("rastr")),
           bool(p.get("negativ")))
    if key in _img_cache:
        return _img_cache[key]
    src = Image.open(path)
    alpha = src.getchannel("A") if "A" in src.getbands() else None
    gray = src.convert("L")
    if fit == "prizpusobit":                          # vejit do ramecku, zachovat pomer stran
        k = min(p["w"] / src.width, p["h"] / src.height)
        size = (max(1, round(src.width * k)), max(1, round(src.height * k)))
        gray = gray.resize(size, Image.LANCZOS)
        alpha = alpha.resize(size, Image.LANCZOS) if alpha is not None else None
    if p.get("negativ"):
        gray = gray.point(lambda v: 255 - v)
    if p.get("rastr"):                                # fotografie: Floyd-Steinberg
        mask = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        t = int(_num(p, "prah", 128))
        mask = gray.point(lambda v: 255 if v >= t else 0).convert("1")
    if alpha is not None:
        mask = ImageChops.logical_and(mask, alpha.point(lambda v: 255 if v >= 128 else 0).convert("1"))
    if len(_img_cache) > 64:
        _img_cache.clear()
    _img_cache[key] = mask
    return mask


def image_size(name):
    try:
        with Image.open(image_path(name)) as im:
            return im.size
    except OSError:
        return None


def draw_image(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    mask = load_mask(p)
    if mask is None:                                  # chybi soubor: preskrtnuty ramecek
        d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)
        d.line((x, y, x + w - 1, y + h - 1), fill=1)
        return
    crop = mask.crop((0, 0, min(w, mask.width), min(h, mask.height)))
    if p.get("pozadi"):                               # neprusvitny: pod obrazkem zhasnout
        d.rectangle((x, y, x + crop.width - 1, y + crop.height - 1), fill=0)
    img.paste(int(p.get("barva", 1)), (x, y), crop)


DRAW = {"obrazek": draw_image, "text": draw_text, "cislo": draw_number, "hodiny": draw_clock, "bar": draw_bar,
        "sloupce": draw_columns, "budik": draw_gauge, "prstenec": draw_ring, "oblouk": draw_arc,
        "ikona": draw_icon, "cara": draw_line, "obdelnik": draw_rect}


def render(acfg, data, history=None, now=None):
    """acfg = config["alphacool"] -> obrazek v rezimu "1" (1 = rozsviceny bod) tak, jak ho vidi
    uzivatel: 240x128, na vysku 128x240 (pro displej ho otoci to_panel)."""
    img = Image.new("1", canvas_size(acfg), 0)
    d = ImageDraw.Draw(img)
    now = now or datetime.now()
    # seznam prvku pro prvky, ktere se jinym vyhybaji (hvezdy v prvky_starwars)
    img.info["prvky"] = [p for p in items(acfg) if not p.get("skryty")]
    for p in items(acfg):
        if p.get("skryty"):
            continue
        try:
            if p.get("typ") == "graf":
                draw_graph(img, d, p, data, now, history)
            elif p.get("typ") in HISTORY_TYPES:
                DRAW[p["typ"]](img, d, p, data, now, history)
            else:
                DRAW.get(p.get("typ"), draw_rect)(img, d, p, data, now)
        except Exception:
            # chybny prvek (napr. nesmyslne rozmery) nesmi shodit cely displej
            d.rectangle((p.get("x", 0), p.get("y", 0), p.get("x", 0) + 3, p.get("y", 0) + 3), fill=1)
    if acfg.get("inverze"):
        img = img.convert("L").point(lambda v: 255 - v).convert("1")
    return img


# ------------------------------------------------ nove prvky (vychozi hodnoty)

def _f(size, bold=False, fam=None):
    """Vychozi pismo prvku; velikost se zaokrouhli na ostrou velikost pixeloveho pisma."""
    if fam:
        return {"rodina": fam, "velikost": size, "tucne": bold}
    if size <= 10:
        return {"rodina": SMALL_FAMILY, "velikost": 11, "tucne": False}
    sharp = min((12, 14, 16, 18, 20, 22, 24, 28, 32), key=lambda v: abs(v - size))
    return {"rodina": DEFAULT_FAMILY, "velikost": sharp, "tucne": bold}


_SENS = {"senzor": "CPU (Tctl/Tdie)", "min": 0, "max": 100, "delitel": 1}
NEW = {
    "text": dict(x=4, y=4, w=100, h=14, popisek="CPU", senzor="CPU (Tctl/Tdie)", jednotka="°C",
                 delitel=1, desetinna_mista=0, zarovnani="vlevo", pismo=_f(11), barva=1),
    "cislo": dict(x=4, y=4, w=90, h=44, senzor="CPU (Tctl/Tdie)", jednotka="°C", delitel=1,
                  desetinna_mista=0, popisek="CPU", pismo=_f(36, True), pismo_male=_f(11), barva=1),
    "hodiny": dict(x=4, y=4, w=90, h=14, format="HH:MM:SS", zarovnani="vlevo", pismo=_f(11, True), barva=1),
    "bar": dict(x=4, y=4, w=100, h=9, styl="plny", senzor2="", **_SENS),
    "sloupce": dict(x=4, y=4, w=80, h=30, senzory=[], min=0, max=100, delitel=1, ramecek=True),
    "graf": dict(x=0, y=80, w=240, h=48, styl="plocha", senzor="CPU (Tctl/Tdie)", min=30, max=95,
                 delitel=1, delka_s=120, ramecek=True),
    "budik": dict(x=4, y=4, w=100, h=64, jednotka="°C", desetinna_mista=0, popisek="", hodnota=True,
                  pismo=_f(12, True), **_SENS),
    "prstenec": dict(x=4, y=4, w=64, h=64, jednotka="", desetinna_mista=0, popisek="CPU", hodnota=True,
                     segmenty=20, uhel=270, tloustka=6, pismo=_f(16, True), pismo_male=_f(9), **_SENS),
    "oblouk": dict(x=4, y=4, w=64, h=64, jednotka="", desetinna_mista=0, popisek="CPU", hodnota=True,
                   uhel=240, tloustka=8, pismo=_f(16, True), pismo_male=_f(9), **_SENS),
    "ikona": dict(x=4, y=4, w=11, h=11, nazev="cpu", meritko=1, barva=1),
    "obrazek": dict(x=4, y=4, w=73, h=16, soubor="amd_logo.png", velikost="puvodni", prah=128, rastr=False,
                    negativ=False, pozadi=False, barva=1),
    "cara": dict(x=0, y=20, w=240, h=1, smer="vodorovna", tloustka=1, barva=1),
    "obdelnik": dict(x=0, y=0, w=240, h=14, vypln="plna", dvojity=False, barva=1),
}
TYPES = {"text": "Text / hodnota", "cislo": "Velké číslo", "hodiny": "Hodiny / datum",
         "bar": "Bar", "sloupce": "Sloupce (více senzorů)", "graf": "Graf v čase",
         "budik": "Budík s ručičkou", "prstenec": "Prstenec ze segmentů", "oblouk": "Tlustý oblouk",
         "ikona": "Ikona", "obrazek": "Obrázek (PNG, BMP, JPG)", "cara": "Čára",
         "obdelnik": "Obdélník / pruh"}


def new(typ):
    import copy
    p = copy.deepcopy(NEW[typ])
    p["typ"] = typ
    if typ == "ikona":
        p["w"] = p["h"] = 11 * p["meritko"]
    return p


OLD_ROWS = [
    {"popisek": "CPU", "senzor": "CPU (Tctl/Tdie)", "min": 0, "max": 100, "jednotka": "°C", "delitel": 1,
     "desetinna_mista": 0, "senzor2": "Takt jader", "jednotka2": "GHz", "delitel2": 1000,
     "desetinna_mista2": 2},
    {"popisek": "GPU", "senzor": "Teplota GPU", "min": 0, "max": 100, "jednotka": "°C", "delitel": 1,
     "desetinna_mista": 0, "senzor2": "Takt GPU", "jednotka2": "GHz", "delitel2": 1000,
     "desetinna_mista2": 2},
    {"popisek": "RAM", "senzor": "Použitá fyzická paměť", "min": 0, "max": 32, "jednotka": "G",
     "delitel": 1024, "desetinna_mista": 1, "senzor2": ""},
]
OLD_GRAPH = {"popisek": "CPU", "senzor": "CPU (Tctl/Tdie)", "min": 30, "max": 95, "jednotka": "°",
             "delitel": 1, "desetinna_mista": 0, "delka_s": 120}


def default_portrait_layout():
    """Vychozi rozvrzeni na vysku (128x240): hodiny, CPU a GPU velkym cislem s barem, RAM, graf."""
    out = [
        dict(new("obdelnik"), x=0, y=0, w=128, h=15, vypln="plna"),
        dict(new("hodiny"), x=0, y=0, w=128, h=15, format="HH:MM:SS", zarovnani="stred",
             pismo=_f(12, True), barva=0),
    ]
    for i, (lbl, sensor) in enumerate((("CPU", "CPU (Tctl/Tdie)"), ("GPU", "Teplota GPU"))):
        y = 20 + i * 62
        out.append(dict(new("cislo"), x=2, y=y, w=124, h=44, senzor=sensor, popisek=lbl))
        out.append(dict(new("bar"), x=4, y=y + 47, w=120, h=9, styl="segmenty", senzor=sensor))
    out += [
        dict(new("text"), x=2, y=146, w=124, h=14, popisek="RAM", senzor="Použitá fyzická paměť",
             jednotka="G", delitel=1024, desetinna_mista=1, pismo=_f(12, True)),
        dict(new("bar"), x=4, y=162, w=120, h=9, styl="plny", senzor="Použitá fyzická paměť", min=0, max=32,
             delitel=1024),
        dict(new("graf"), x=0, y=180, w=128, h=60, senzor="CPU (Tctl/Tdie)", min=30, max=95),
    ]
    return out


def default_layout(rows=None, graph=None):
    """Prvky odpovidajici puvodnimu pevnemu prehledu (zahlavi, 3 radky s barem, graf).
    Pouziva se jako vychozi rozvrzeni a pro prevod stareho nastaveni."""
    rows = rows if rows is not None else OLD_ROWS
    g = dict(OLD_GRAPH, **(graph or {}))
    out = [
        dict(new("obdelnik"), x=0, y=0, w=240, h=15, vypln="plna"),
        dict(new("hodiny"), x=3, y=0, w=110, h=15, format="HH:MM:SS", pismo=_f(12, True), barva=0),
        dict(new("hodiny"), x=117, y=0, w=120, h=15, format="den datum", zarovnani="vpravo",
             pismo=_f(12, True), barva=0),
    ]
    for i, r in enumerate(rows[:3]):
        yc = 26 + i * 19
        has2 = bool(r.get("senzor2"))
        out.append(dict(new("text"), x=2, y=yc - 7, w=36, h=14, popisek=r.get("popisek", ""), senzor="",
                        pismo=_f(12, True)))
        out.append(dict(new("text"), x=36, y=yc - 7, w=50, h=14, popisek="", senzor=r.get("senzor", ""),
                        jednotka=r.get("jednotka", "auto"), delitel=r.get("delitel", 1),
                        desetinna_mista=r.get("desetinna_mista", 0), zarovnani="vpravo", pismo=_f(12, True)))
        out.append(dict(new("bar"), x=90, y=yc - 5, w=(88 if has2 else 148), h=11, styl="plny",
                        senzor=r.get("senzor", ""), min=r.get("min", 0), max=r.get("max", 100),
                        delitel=r.get("delitel", 1)))
        if has2:
            out.append(dict(new("text"), x=180, y=yc - 7, w=58, h=14, popisek="", senzor=r["senzor2"],
                            jednotka=r.get("jednotka2", "auto"), delitel=r.get("delitel2", 1),
                            desetinna_mista=r.get("desetinna_mista2", 0), zarovnani="vpravo",
                            pismo=_f(12, True)))
    secs = int(g.get("delka_s", 120))
    out += [
        dict(new("text"), x=2, y=83, w=42, h=14, popisek=g.get("popisek", ""), senzor="", pismo=_f(12, True)),
        dict(new("text"), x=2, y=98, w=42, h=14, popisek="", senzor=g.get("senzor", ""),
             jednotka=g.get("jednotka", "auto"), delitel=g.get("delitel", 1),
             desetinna_mista=g.get("desetinna_mista", 0), pismo=_f(12, True)),
        dict(new("text"), x=2, y=113, w=42, h=14, popisek=f"{secs // 60} min" if secs >= 60 else f"{secs} s",
             senzor="", pismo=_f(10)),
        dict(new("graf"), x=46, y=81, w=194, h=47, styl="plocha", senzor=g.get("senzor", ""),
             min=g.get("min", 30), max=g.get("max", 95), delitel=g.get("delitel", 1), delka_s=secs),
    ]
    return out


def label(p):
    """Popis prvku pro seznam v editoru."""
    if p.get("typ") in _scifi.DRAW:
        return _scifi.label(p)
    t = TYPES.get(p.get("typ"), p.get("typ", "?"))
    extra = (p.get("popisek") or p.get("senzor") or p.get("format") or p.get("nazev") or p.get("soubor")
             or p.get("styl") or "")
    if p.get("typ") == "bar":
        extra = f"{p.get('styl', 'plny')}: {p.get('senzor', '')}"
    return f"{t}: {extra}".rstrip(": ")


# ------------------------------------------------ sci-fi prvky a hotove obrazovky (prvky_scifi.py)
# Import az na konci: prvky_scifi pouziva funkce tohoto modulu.
import prvky_scifi as _scifi  # noqa: E402

DRAW.update(_scifi.DRAW)
NEW.update(_scifi.NEW)
TYPES.update(_scifi.TYPES)
HISTORY_TYPES = _scifi.HISTORY_TYPES                 # prvky, ktere kresli historii hodnoty (krome grafu)
