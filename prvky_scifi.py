# prvky_scifi.py - sci-fi prvky a hotove obrazovky pro Alphacool (Blade Runner, Vetrelci)
# Navrhy z Claude Design (platno, stranka "Alphacool – hotove obrazovky").
#
# Prvky (API jako prvky.py: draw(img, d, p, data, now[, history])):
#   seg      segmentove cislo (7 segmentu) nebo cas, jednotka a popisek drobne vpravo
#   radek    radek textu ze sablony s hodnotami senzoru
#   term     terminal: radky "POPISEK = sablona", mezi popiskem a hodnotou tecky
#   pasek    tenky pasek (Blade Runner): popisek vlevo, hodnoty vpravo, pod nimi 3px bar s ryskami
#   duhovka  duhovka (Voight-Kampff): zornicka roste s hodnotou
#   esper    mrizka s grafem v case a zamerovacim krizem, v rohu hodnota
#   teren    dratovy teren z historie hodnoty (pristani na LV-426)
#   blok     svisly blokovy sloupec s hodnotou nahore a popiskem dole
#   radar    detektor pohybu: pulkruh, otacejici se paprsek, body z historie
#
# Sablona textu: {senzor|delitel|desetinna mista}, delitel a mista jsou volitelne (1, 0),
# jednotky se pisou primo do textu: "CPU {Celkové vytížení CPU}% {Takt jader|1000|1}GHz".

import copy
import math
import re

from PIL import Image, ImageChops, ImageDraw

import prvky
from prvky import _f, _hist_cols, _num, frac, get_font, value

TERM = _f(12, True)
SMALL = _f(11, fam="Micro 5")
_PLACEHOLDER = re.compile(r"\{([^{}|]+)(?:\|([^{}|]*))?(?:\|([^{}|]*))?\}")


def fill_template(text, data):
    """Sablona -> text s aktualnimi hodnotami (chybejici senzor = pomlcka)."""
    def rep(m):
        sensor = m.group(1).strip()
        try:
            div = float((m.group(2) or "1").replace(",", ".")) or 1
        except ValueError:
            div = 1
        try:
            dec = int(m.group(3) or 0)
        except ValueError:
            dec = 0
        return prvky.fmt(value(data, sensor, div), dec)
    return _PLACEHOLDER.sub(rep, str(text or ""))


def template_sensors(text):
    return [m.group(1).strip() for m in _PLACEHOLDER.finditer(str(text or ""))]


def _xor_text(img, xy, text, font, anchor="mm"):
    """Text, ktery se na vyplni invertuje."""
    m = Image.new("1", img.size, 0)
    ImageDraw.Draw(m).text(xy, text, font=font, fill=1, anchor=anchor)
    img.paste(ImageChops.logical_xor(img, m))


def _hist(p, history, key="senzor"):
    div = _num(p, "delitel", 1) or 1
    return [v / div for v in (history or {}).get(p.get(key), [])]


# ------------------------------------------------------------ segmentove cislice
SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
       "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", "–": "g", " ": ""}


def _dims(h):
    return (max(6, int(h * 0.55)) if h < 24 else int(h * 0.52)), max(2, h // 9)


def seg_width(text, h):
    dw, gap = _dims(h)
    w = 0
    for ch in text:
        w += max(2, round(h / 9)) + gap if ch in ".:" else dw + gap
    return max(0, w - gap)


def seg7(d, x, y, h, text, fill=1):
    """Text ze segmentovych cislic (0-9 - . :); pod 24 px obdelnikove segmenty (ostre na 1 bitu)."""
    dw, gap = _dims(h)
    t = max(2, round(h / 9))
    k = t / 2
    cx = x
    for ch in text:
        if ch in ".:":
            s = t
            if ch == ".":
                d.rectangle((cx, y + h - s, cx + s - 1, y + h - 1), fill=fill)
            else:
                for yy in (y + h // 3 - s // 2, y + 2 * h // 3 - s // 2):
                    d.rectangle((cx, yy, cx + s - 1, yy + s - 1), fill=fill)
            cx += s + gap
            continue
        if h < 24:
            tt = 2 if h < 18 else 3
            gy = y + (h - tt) // 2
            boxes = {"a": (cx, y, cx + dw - 1, y + tt - 1), "g": (cx, gy, cx + dw - 1, gy + tt - 1),
                     "d": (cx, y + h - tt, cx + dw - 1, y + h - 1),
                     "f": (cx, y, cx + tt - 1, gy + tt - 1), "b": (cx + dw - tt, y, cx + dw - 1, gy + tt - 1),
                     "e": (cx, gy, cx + tt - 1, y + h - 1), "c": (cx + dw - tt, gy, cx + dw - 1, y + h - 1)}
            for name in SEG.get(ch, ""):
                d.rectangle(boxes[name], fill=fill)
        else:
            hm = y + h // 2
            segs = {"a": ("h", cx, cx + dw - 1, y + k), "g": ("h", cx, cx + dw - 1, hm),
                    "d": ("h", cx, cx + dw - 1, y + h - 1 - k),
                    "f": ("v", y, hm, cx + k), "b": ("v", y, hm, cx + dw - 1 - k),
                    "e": ("v", hm, y + h - 1, cx + k), "c": ("v", hm, y + h - 1, cx + dw - 1 - k)}
            for name in SEG.get(ch, ""):
                o, a0, a1, c = segs[name]
                a0, a1 = a0 + 1.5, a1 - 1.5
                if o == "h":
                    pts = [(a0, c), (a0 + k, c - k), (a1 - k, c - k), (a1, c), (a1 - k, c + k), (a0 + k, c + k)]
                else:
                    pts = [(c, a0), (c + k, a0 + k), (c + k, a1 - k), (c, a1), (c - k, a1 - k), (c - k, a0 + k)]
                d.polygon(pts, fill=fill)
        cx += dw + gap
    return cx - gap - x


# ------------------------------------------------------------------ prvky
def draw_seg(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    if p.get("cas"):
        txt = now.strftime(p.get("format_casu", "%H:%M"))
    else:
        v = value(data, p.get("senzor"), p.get("delitel", 1))
        txt = "--" if v is None else f"{v:.{int(_num(p, 'desetinna_mista', 0))}f}"
    fs = get_font(SMALL)
    u, lbl = p.get("jednotka", ""), p.get("popisek", "")
    side = max(d.textlength(u, font=fs), d.textlength(lbl, font=fs)) + 3 if (u or lbl) else 0
    sw = seg_width(txt, h)
    al = p.get("zarovnani", "vlevo")
    x0 = x if al == "vlevo" else x + (w - sw - side) // 2 if al == "stred" else x + w - sw - side
    fill = int(p.get("barva", 1))
    seg7(d, x0, y, h, txt, fill=fill)
    if u:
        d.text((x0 + sw + 3, y), u, font=fs, fill=fill, anchor="lt")
    if lbl:
        d.text((x0 + sw + 3, y + h), lbl, font=fs, fill=fill, anchor="lb")


def draw_row(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo", TERM))
    txt = fill_template(p.get("sablona", ""), data)
    al = p.get("zarovnani", "vlevo")
    ax = {"vlevo": x, "stred": x + w / 2, "vpravo": x + w - 1}.get(al, x)
    anchor = {"vlevo": "lm", "stred": "mm", "vpravo": "rm"}.get(al, "lm")
    if int(p.get("barva", 1)) == 0:
        _xor_text(img, (ax, y + h / 2), txt, f, anchor)
    else:
        d.text((ax, y + h / 2), txt, font=f, fill=1, anchor=anchor)


def term_rows(p):
    """Radky terminalu: [(popisek, sablona)] z textu "POPISEK = sablona" (radek na radek)."""
    out = []
    for line in str(p.get("radky", "")).splitlines():
        if not line.strip():
            continue
        lbl, _, tmpl = line.partition("=")
        out.append((lbl.strip(), tmpl.strip()))
    return out


def draw_term(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo", TERM))
    lh = int(_num(p, "radek_px", 13))
    cw = d.textlength("0", font=f)
    yy = y
    for lbl, tmpl in term_rows(p):
        if yy + lh - 2 > y + h:
            break
        val = fill_template(tmpl, data)
        d.text((x, yy), lbl, font=f, fill=1, anchor="lt")
        vw = d.textlength(val, font=f)
        d.text((x + w - 1, yy), val, font=f, fill=1, anchor="rt")
        xx, end = x + d.textlength(lbl, font=f) + cw * 0.6, x + w - vw - cw * 0.6
        while xx < end:                                          # tecky mezi popiskem a hodnotou
            d.point((xx, yy + lh - 5), fill=1)
            xx += 3
        yy += lh
    if p.get("kurzor") and yy + lh - 2 <= y + h:                  # vyzva s blikajicim kurzorem
        d.text((x, yy), ">", font=f, fill=1, anchor="lt")
        if now.second % 2 == 0:
            d.rectangle((x + cw + 2, yy + 1, x + 2 * cw + 1, yy + lh - 4), fill=1)


def draw_strip(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo", TERM))
    d.text((x, y), p.get("popisek", ""), font=f, fill=1, anchor="lt")
    d.text((x + w - 1, y), fill_template(p.get("sablona", ""), data), font=f, fill=1, anchor="rt")
    by = y + h - 4
    fr = frac(value(data, p.get("senzor"), p.get("delitel", 1)), _num(p, "min", 0), _num(p, "max", 100))
    for i in range(11):
        tx = x + round((w - 1) * i / 10)
        d.line((tx, by, tx, by + 3), fill=1)
    d.line((x, by + 3, x + w - 1, by + 3), fill=1)
    if fr > 0:
        d.rectangle((x, by, x + round((w - 1) * fr), by + 2), fill=1)


def draw_iris(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    r = min(w, h) // 2 - 1
    cx, cy = x + w // 2, y + h // 2
    fr = frac(value(data, p.get("senzor"), p.get("delitel", 1)), _num(p, "min", 0), _num(p, "max", 100))
    pr = round(r * (0.18 + 0.5 * fr))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=1)
    for a in range(0, 360, 4):
        t = math.radians(a)
        d.point((cx + (r + 3) * math.cos(t), cy + (r + 3) * math.sin(t)), fill=1)
    for i in range(48):
        t = math.radians(i * 7.5 + (i % 3) * 2)
        r1, r2 = pr + 2, r - 3 - (i % 4)
        d.line((cx + r1 * math.cos(t), cy + r1 * math.sin(t), cx + r2 * math.cos(t), cy + r2 * math.sin(t)), fill=1)
    d.ellipse((cx - pr, cy - pr, cx + pr, cy + pr), fill=1)
    hl = max(1, pr // 3)
    d.ellipse((cx - pr // 2 - hl, cy - pr // 2 - hl, cx - pr // 2 + hl, cy - pr // 2 + hl), fill=0)
    for sx in (-1, 1):
        d.line((cx + sx * (r + 6), cy, cx + sx * (r + 12), cy), fill=1)
    d.line((cx, cy - r - 6, cx, cy - r - 10), fill=1)


def draw_esper(img, d, p, data, now, history=None):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)
    for gx in range(x + 8, x + w - 1, 8):
        for gy in range(y + 8, y + h - 1, 8):
            d.point((gx, gy), fill=1)
    vals = _hist(p, history)
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    if len(vals) >= 2 and w > 8 and h > 24:
        cols = _hist_cols(vals, w - 6)
        pts = [(x + 3 + i, y + h - 4 - round((h - 20) * frac(v, lo, hi))) for i, v in enumerate(cols)]
        d.line(pts, fill=1, width=1)
        ex, ey = pts[-13] if len(pts) > 13 else pts[-1]
        for xx in range(x + 1, x + w - 1, 3):
            d.point((xx, ey), fill=1)
        for yy in range(y + 1, y + h - 1, 3):
            d.point((ex, yy), fill=1)
        d.rectangle((ex - 5, ey - 5, ex + 5, ey + 5), outline=1)
        d.rectangle((ex - 1, ey - 1, ex + 1, ey + 1), fill=1)
    f = get_font(TERM)
    tag = fill_template(p.get("sablona", ""), data)
    if tag:
        tw = d.textlength(tag, font=f)
        d.rectangle((x + 1, y + 1, x + tw + 5, y + 13), fill=1)
        _xor_text(img, (x + 3, y + 7), tag, f, "lm")
    if p.get("roh"):
        d.text((x + w - 3, y + 3), p["roh"], font=get_font(SMALL), fill=1, anchor="rt")


def draw_terrain(img, d, p, data, now, history=None):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    vals = _hist(p, history)
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    n_rows, n_pts = 9, 25
    prof = _hist_cols(vals, n_pts) if len(vals) >= n_pts else [lo] * n_pts
    rows = []
    for r in range(n_rows):                                       # r = 0 daleko, n-1 blizko
        z = (r + 1) / n_rows
        base = y + h * 0.25 + (h * 0.75 - 1) * z ** 1.6
        spread = 0.35 + 0.65 * z
        amp = h * 0.55 * z
        shift = n_rows - 1 - r                                     # starsi hodnoty dal
        pts = []
        for i in range(n_pts):
            u = i / (n_pts - 1)
            v = prof[max(0, min(n_pts - 1, i - shift))]
            bump = frac(v, lo, hi) * (0.4 + 0.6 * math.sin(math.pi * u) ** 2)
            pts.append((x + w / 2 + (u - 0.5) * w * spread * 1.4, base - amp * bump))
        rows.append(pts)
    clip = Image.new("1", img.size, 0)
    ImageDraw.Draw(clip).rectangle((x, y, x + w - 1, y + h - 1), fill=1)
    layer = Image.new("1", img.size, 0)
    ld = ImageDraw.Draw(layer)
    for r, pts in enumerate(rows):                                 # zezadu dopredu (prekryvani)
        ld.polygon(pts + [(pts[-1][0], y + h + 40), (pts[0][0], y + h + 40)], fill=0)
        ld.line(pts, fill=1)
        if r > 0:
            for i in range(0, n_pts, 3):
                ld.line((rows[r - 1][i], pts[i]), fill=1)
    img.paste(1, (0, 0), ImageChops.logical_and(layer, clip))


def draw_block(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    v = value(data, p.get("senzor"), p.get("delitel", 1))
    d.text((x + w / 2, y), prvky.fmt(v, p.get("desetinna_mista", 0), p.get("jednotka", "")), font=get_font(TERM),
           fill=1, anchor="mt")
    d.text((x + w / 2, y + h - 1), p.get("popisek", ""), font=get_font(SMALL), fill=1, anchor="mb")
    top, bot = y + 14, y + h - 9
    if bot - top < 6:
        return
    d.rectangle((x + 3, top, x + w - 4, bot), outline=1)
    on = round(((bot - top - 2) // 4) * frac(v, _num(p, "min", 0), _num(p, "max", 100)))
    for i in range(on):
        yy = bot - 2 - i * 4
        d.rectangle((x + 5, yy - 2, x + w - 6, yy), fill=1)


def draw_radar(img, d, p, data, now, history=None):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    r = min(w // 2, h) - 1
    if r < 6:
        return
    cx, cy = x + w // 2, y + h - 1
    d.arc((cx - r, cy - r, cx + r, cy + r), 180, 360, fill=1)
    for k in (0.33, 0.66):
        rr = round(r * k)
        for a in range(180, 361, 6):
            t = math.radians(a)
            d.point((cx + rr * math.cos(t), cy + rr * math.sin(t)), fill=1)
    for a in range(180, 361, 30):
        t = math.radians(a)
        d.line((cx + (r - 4) * math.cos(t), cy + (r - 4) * math.sin(t), cx + r * math.cos(t), cy + r * math.sin(t)),
               fill=1)
    sweep = 180 + ((now.second % 4) + now.microsecond / 1e6) / 4 * 180
    t = math.radians(sweep)
    d.line((cx, cy, cx + r * math.cos(t), cy + r * math.sin(t)), fill=1)
    for dt in (3, 6, 9):                                           # dozvuk za paprskem
        t2 = math.radians(sweep - dt)
        for rr in range(4, r, 4):
            d.point((cx + rr * math.cos(t2), cy + rr * math.sin(t2)), fill=1)
    vals = _hist(p, history)
    lo, hi = _num(p, "min", 0), _num(p, "max", 100)
    if vals:
        n = 9
        for i in range(n):                                         # body: novejsi = blize stredu
            v = vals[int((len(vals) - 1) * i / (n - 1))]
            ang = math.radians(195 + 150 * ((i * 37) % n) / n)
            rr = r * (0.25 + 0.7 * (1 - i / n)) * (0.6 + 0.4 * frac(v, lo, hi))
            bx, by = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            s = 2 if i == n - 1 else 1
            d.rectangle((bx - s, by - s, bx + s, by + s), fill=1)
    d.rectangle((cx - 2, cy - 2, cx + 2, cy), fill=1)


DRAW = {"seg": draw_seg, "radek": draw_row, "term": draw_term, "pasek": draw_strip, "duhovka": draw_iris,
        "esper": draw_esper, "teren": draw_terrain, "blok": draw_block, "radar": draw_radar}
HISTORY_TYPES = ("esper", "teren", "radar")
TYPES = {"seg": "Segmentové číslo / čas", "radek": "Řádek hodnot (šablona)", "term": "Terminál (řádky s tečkami)",
         "pasek": "Tenký pásek (Blade Runner)", "duhovka": "Duhovka (Voight-Kampff)", "esper": "Esper – graf s křížem",
         "teren": "Drátový terén (historie)", "blok": "Blokový sloupec", "radar": "Detektor pohybu (radar)"}
NEW = {
    "seg": dict(x=4, y=4, w=80, h=20, senzor="CPU (Tctl/Tdie)", delitel=1, desetinna_mista=0, jednotka="°C",
                popisek="CPU", zarovnani="vlevo", cas=False, format_casu="%H:%M", barva=1),
    "radek": dict(x=2, y=2, w=236, h=12, sablona="CPU {Celkové vytížení CPU}% {Celková spotřeba CPU}W",
                  zarovnani="vlevo", pismo=TERM, barva=1),
    "term": dict(x=2, y=2, w=114, h=66, radky="CPU = {CPU (Tctl/Tdie)}°C\nZÁTĚŽ = {Celkové vytížení CPU}%",
                 radek_px=13, kurzor=False, pismo=TERM),
    "pasek": dict(x=2, y=2, w=144, h=16, popisek="CPU", sablona="{CPU (Tctl/Tdie)}°C", senzor="CPU (Tctl/Tdie)",
                  min=0, max=100, delitel=1, pismo=TERM),
    "duhovka": dict(x=2, y=2, w=84, h=84, senzor="Celkové vytížení CPU", min=0, max=100, delitel=1),
    "esper": dict(x=0, y=0, w=156, h=104, senzor="CPU (Tctl/Tdie)", min=30, max=95, delitel=1, delka_s=120,
                  sablona="CPU {CPU (Tctl/Tdie)}°C", roh="T-2MIN"),
    "teren": dict(x=0, y=66, w=240, h=62, senzor="CPU (Tctl/Tdie)", min=30, max=95, delitel=1, delka_s=120),
    "blok": dict(x=2, y=14, w=38, h=86, senzor="CPU (Tctl/Tdie)", min=0, max=100, delitel=1, desetinna_mista=0,
                 jednotka="°", popisek="CPU °C"),
    "radar": dict(x=2, y=2, w=130, h=70, senzor="@síť stahování", min=0, max=20, delitel=1, delka_s=120),
}


# ------------------------------------------------------------ Star Trek (LCARS, warp jadro)
def _pill(d, box, fill=1):
    d.rounded_rectangle(box, (box[3] - box[1]) // 2, fill=fill)


def draw_lcars_frame(img, d, p, data, now):
    """Rohovy "loket": svisly pas vlevo, vodorovny nahore, zaobleny vnejsi i vnitrni roh,
    v levem pasu bloky s kody, v hornim pasu popisek v mezere."""
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    vb, hb = int(_num(p, "pas", 26)), int(_num(p, "pas_nahore", 9))
    ro, ri = 12, 7
    mask = Image.new("1", img.size, 0)
    m = ImageDraw.Draw(mask)
    m.rounded_rectangle((x, y, x + vb + ro * 2, y + hb + ro * 2), ro, fill=1)
    m.rectangle((x, y + ro, x + vb - 1, y + h - 1), fill=1)
    m.rectangle((x + ro, y, x + w - hb // 2 - 1, y + hb - 1), fill=1)
    m.ellipse((x + w - hb, y, x + w - 1, y + hb - 1), fill=1)
    m.rectangle((x + vb, y + hb, x + vb + ro * 2, y + hb + ro * 2), fill=0)
    m.rectangle((x + vb, y + hb, x + vb + ri, y + hb + ri), fill=1)
    m.pieslice((x + vb, y + hb, x + vb + 2 * ri, y + hb + 2 * ri), 180, 270, fill=0)
    label = p.get("popisek", "")
    f = get_font(SMALL)
    if label:
        lw = d.textlength(label, font=f)
        lx = x + w - hb - 10 - lw
        m.rectangle((lx - 4, y, lx + lw + 3, y + hb - 1), fill=0)
    codes = [c for c in str(p.get("kody", "")).split() if c]
    y0, n = y + hb + ro * 2 + 4, max(1, len(codes))
    bh = (y + h - y0 - 2 * (n - 1)) // n
    for i in range(1, n):
        yy = y0 + i * (bh + 2) - 2
        m.rectangle((x, yy, x + vb - 1, yy + 1), fill=0)
    m.rectangle((x, y0 - 2, x + vb - 1, y0 - 1), fill=0)
    img.paste(1, (0, 0), mask)
    for i, c in enumerate(codes):
        _xor_text(img, (x + vb - 3, y0 + i * (bh + 2) + bh - 2), c, f, "rb")
    if label:
        d.text((lx, y + hb // 2), label, font=f, fill=1, anchor="lm")


def draw_lcars_value(img, d, p, data, now):
    """Obly stitek s inverznim popiskem, za nim segmentova hodnota a jednotka;
    od vysky 24 px pod hodnotou rada bloku podle hodnoty."""
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    ph = min(13, h)
    pw = int(_num(p, "sirka_stitku", 44))
    _pill(d, (x, y, x + pw, y + ph - 1))
    d.rectangle((x + pw - ph // 2, y, x + pw, y + ph - 1), fill=1)
    _xor_text(img, (x + pw - 4, y + ph // 2), p.get("popisek", ""), get_font(TERM), "rm")
    v = value(data, p.get("senzor"), p.get("delitel", 1))
    txt = "--" if v is None else f"{v:.{int(_num(p, 'desetinna_mista', 0))}f}"
    vh = ph if h < 24 else h - 9
    sw = seg7(d, x + pw + 5, y, vh, txt)
    if p.get("jednotka"):
        d.text((x + pw + 5 + sw + 2, y), p["jednotka"], font=get_font(SMALL), fill=1, anchor="lt")
    if h >= 24:
        by = y + h - 6
        n = max(1, int(_num(p, "bloky", 12)))
        bw = (w - pw - 5 - 2 * (n - 1)) / n
        on = round(n * frac(v, _num(p, "min", 0), _num(p, "max", 100)))
        for i in range(n):
            bx = x + pw + 5 + i * (bw + 2)
            box = (round(bx), by, round(bx + bw) - 1, y + h - 1)
            if i < on:
                d.rectangle(box, fill=1)
            else:
                d.line((box[0], box[3], box[2], box[3]), fill=1)
        _pill(d, (x, by, x + pw, y + h - 1))


def draw_warp(img, d, p, data, now):
    """Warp jadro: svisly sloup oblych clanku rozsvicenych odspodu podle hodnoty, ze stredu
    nahoru i dolu bezi puls (rychlejsi pri vyssi hodnote); nahore a dole sirsi hlavice."""
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    fr = frac(value(data, p.get("senzor"), p.get("delitel", 1)), _num(p, "min", 0), _num(p, "max", 100))
    cap = max(6, h // 12)
    _pill(d, (x, y, x + w - 1, y + cap - 1))
    _pill(d, (x, y + h - cap, x + w - 1, y + h - 1))
    top, bot = y + cap + 3, y + h - cap - 3
    seg_h = 5
    n = max(2, (bot - top + 2) // (seg_h + 2))
    inset = max(3, w // 6)
    on = round(n * fr)
    t = now.second + now.microsecond / 1e6
    mid = n // 2
    pulse = int(t * (1 + 3 * fr) * 3) % (mid + 1)
    for i in range(n):
        yy = bot - i * (seg_h + 2) - seg_h + 1
        box = (x + inset, yy, x + w - 1 - inset, yy + seg_h - 1)
        if i < on:
            _pill(d, box)
        else:
            d.rounded_rectangle(box, seg_h // 2, outline=1)
        if abs(i - mid) == pulse:                         # puls ze stredu nahoru i dolu
            d.rectangle((x + 1, yy + 1, x + inset - 2, yy + seg_h - 2), fill=1)
            d.rectangle((x + w - inset + 1, yy + 1, x + w - 2, yy + seg_h - 2), fill=1)


DRAW.update({"lcars_ram": draw_lcars_frame, "lcars_hodnota": draw_lcars_value, "warp": draw_warp})
TYPES.update({"lcars_ram": "LCARS rám (Star Trek)", "lcars_hodnota": "LCARS štítek s hodnotou",
              "warp": "Warp jádro (Star Trek)"})
NEW.update({
    "lcars_ram": dict(x=0, y=0, w=240, h=128, pas=30, pas_nahore=9, popisek="SYSTÉM", kody="01 02 03 04"),
    "lcars_hodnota": dict(x=36, y=20, w=96, h=13, popisek="CPU", sirka_stitku=44, senzor="CPU (Tctl/Tdie)",
                          delitel=1, desetinna_mista=0, jednotka="°C", min=0, max=100, bloky=12),
    "warp": dict(x=100, y=0, w=40, h=128, senzor="Celkové vytížení CPU", min=0, max=100, delitel=1),
})


# ------------------------------------------------------------ hotove obrazovky
def S(sensor, div=1, dec=0):
    """Zastupny symbol hodnoty pro sablonu."""
    if div == 1 and dec == 0:
        return "{%s}" % sensor
    return "{%s|%s|%s}" % (sensor, div, dec)


CPU_T, CPU_L, CPU_W = "CPU (Tctl/Tdie)", "Celkové vytížení CPU", "Celková spotřeba CPU"
CPU_F, CORES = "Takt jader", "Průměrný počet aktivních jader"
GPU_T, GPU_L, GPU_W = "Teplota GPU", "Zatížení jádra GPU", "GPU Spotřeba energie"
GPU_F, VRAM, RAM = "Takt GPU (naměřený)", "Přidělená paměť GPU", "Použitá fyzická paměť"
DOWN, UP, WIFI_S = "@síť stahování", "@síť odesílání", "@wifi signál"
C_FREE, C_T, C_USED = "@disk C: volno", "Teplota disku (C:)", "@disk C: obsazeno"
D_FREE, D_T, D_USED = "@disk D: volno", "Teplota disku (D:)", "@disk D: obsazeno"
GC, GG, RAMG, VRAMG = S(CPU_F, 1000, 1), S(GPU_F, 1000, 1), S(RAM, 1024, 1), S(VRAM, 1000, 1)


def _el(typ, **kw):
    base = copy.deepcopy(prvky.NEW[typ]) if typ in prvky.NEW else copy.deepcopy(NEW[typ])
    base.update(typ=typ, **kw)
    return base


def _terms(rows):
    return "\n".join(f"{l} = {t}" for l, t in rows)


def _header(title):
    return [_el("obdelnik", x=0, y=0, w=240, h=12, vypln="plna"),
            _el("radek", x=2, y=0, w=156, h=12, barva=0, sablona=title),
            _el("hodiny", x=160, y=0, w=78, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM, barva=0)]


def _row(x, y, w, tmpl, h=12, al="vlevo", font=TERM, **kw):
    return _el("radek", x=x, y=y, w=w, h=h, sablona=tmpl, zarovnani=al, pismo=font, **kw)


def _term(x, y, w, h, rows, **kw):
    return _el("term", x=x, y=y, w=w, h=h, radky=_terms(rows), **kw)


def templates():
    """{nazev: [prvky]} - hotove obrazovky 240x128 (na sirku)."""
    return {
        "Nostromo – stav systému (Vetřelec)": _header("NOSTROMO · STAV SYSTÉMU") + [
            _term(2, 15, 114, 66, [("CPU", S(CPU_T) + "°C"), ("ZÁTĚŽ", S(CPU_L) + "%"), ("PŘÍKON", S(CPU_W) + "W"),
                                   ("TAKT", GC + "GHz"), ("JÁDRA", S(CORES, 1, 1))]),
            _term(124, 15, 114, 66, [("GPU", S(GPU_T) + "°C"), ("ZÁTĚŽ", S(GPU_L) + "%"), ("PŘÍKON", S(GPU_W) + "W"),
                                     ("TAKT", GG + "GHz"), ("VRAM", VRAMG + "GB")]),
            _el("cara", x=2, y=82, w=236, h=1, smer="vodorovna", tloustka=1),
            _term(2, 86, 114, 40, [("RAM", RAMG + "GB"), ("C:", S(C_FREE) + "G " + S(C_T) + "°"),
                                   ("D:", S(D_FREE) + "G " + S(D_T) + "°")]),
            _term(124, 86, 114, 40, [("↓ SÍŤ", S(DOWN, 1, 1) + "MB/s"), ("↑ SÍŤ", S(UP, 1, 1) + "MB/s"),
                                     ("WIFI", S(WIFI_S) + "dB")])],
        "LV-426 – sestup (Vetřelec)": [
            _el("obdelnik", x=0, y=0, w=240, h=12, vypln="plna"),
            _el("hodiny", x=2, y=0, w=100, h=12, format="HH:MM:SS", pismo=TERM, barva=0),
            _el("hodiny", x=118, y=0, w=120, h=12, format="den datum", zarovnani="vpravo", pismo=TERM, barva=0),
            _el("seg", x=4, y=16, w=76, h=20, senzor=CPU_T, jednotka="°C", popisek="CPU"),
            _el("seg", x=84, y=16, w=76, h=20, senzor=GPU_T, jednotka="°C", popisek="GPU"),
            _el("seg", x=164, y=16, w=74, h=20, senzor=RAM, delitel=1024, desetinna_mista=1, jednotka="GB",
                popisek="RAM"),
            _row(2, 40, 118, f"CPU {S(CPU_L)}% {S(CPU_W)}W {GC}G"),
            _row(122, 40, 116, f"GPU {S(GPU_L)}% {S(GPU_W)}W {GG}G", al="vpravo"),
            _row(2, 53, 118, f"C: {S(C_FREE)}G D: {S(D_FREE)}G"),
            _row(122, 53, 116, f"↓ {S(DOWN, 1, 1)} ↑ {S(UP, 1, 1)} MB/s", al="vpravo"),
            _el("teren", x=0, y=66, w=240, h=62, senzor=CPU_T, min=30, max=95)],
        "Detektor pohybu – síť (Vetřelci)": [
            _el("radar", x=2, y=2, w=130, h=70, senzor=DOWN, min=0, max=20),
            _el("seg", x=2, y=78, w=130, h=26, senzor=DOWN, desetinna_mista=1, jednotka="MB/S", popisek="STAH.",
                zarovnani="stred"),
            _row(2, 112, 130, f"↑ {S(UP, 1, 1)}MB/s  WIFI {S(WIFI_S)}dB", h=14, al="stred"),
            _el("obdelnik", x=138, y=0, w=102, h=12, vypln="plna"),
            _el("hodiny", x=140, y=0, w=98, h=12, format="HH:MM:SS", zarovnani="stred", pismo=TERM, barva=0),
            _term(140, 15, 98, 112, [("CPU", f"{S(CPU_T)}° {S(CPU_L)}%"), ("GPU", f"{S(GPU_T)}° {S(GPU_L)}%"),
                                     ("W", f"{S(CPU_W)} / {S(GPU_W)}W"), ("GHZ", f"{GC} / {GG}"),
                                     ("RAM", RAMG + "G"), ("VRAM", VRAMG + "G"),
                                     ("C:", f"{S(C_FREE)}G {S(C_T)}°"), ("D:", f"{S(D_FREE)}G {S(D_T)}°")])],
        "Taktický panel (Vetřelci – APC)": _header("TAKTICKÝ PANEL · SYSTÉM") + [
            _el("blok", x=2 + i * 40, y=15, w=38, h=86, popisek=lbl, senzor=s, min=0, max=mx, delitel=dv,
                desetinna_mista=dc, jednotka=u)
            for i, (lbl, s, mx, dv, dc, u) in enumerate((("CPU °C", CPU_T, 100, 1, 0, "°"),
                                                         ("GPU °C", GPU_T, 100, 1, 0, "°"),
                                                         ("CPU %", CPU_L, 100, 1, 0, "%"),
                                                         ("GPU %", GPU_L, 100, 1, 0, "%"),
                                                         ("RAM GB", RAM, 32, 1024, 1, ""),
                                                         ("DISK C:", C_USED, 100, 1, 0, "%")))
        ] + [
            _row(2, 103, 236, f"C: {S(C_FREE)}G  D: {S(D_FREE)}G   ↓ {S(DOWN, 1, 1)} ↑ {S(UP, 1, 1)} MB/s"),
            _row(2, 115, 236, f"PŘÍKON {S(CPU_W)}W {S(GPU_W)}W   TAKT {GC} / {GG}GHz")],
        "Voight-Kampff (Blade Runner)": [
            _row(2, 0, 150, "VOIGHT-KAMPFF · SUBJEKT CPU", h=11, font=SMALL),
            _el("hodiny", x=160, y=0, w=78, h=11, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM),
            _el("cara", x=0, y=12, w=240, h=1, smer="vodorovna", tloustka=1),
            _el("duhovka", x=2, y=17, w=84, h=82, senzor=CPU_L, min=0, max=100),
            _row(0, 102, 90, f"ZÁTĚŽ {S(CPU_L)}%", al="stred"),
            _row(0, 115, 90, f"GPU {S(GPU_L)}%", al="stred"),
            _el("pasek", x=94, y=15, w=144, h=16, popisek="CPU", sablona=f"{S(CPU_T)}°C {GC}GHz", senzor=CPU_T),
            _el("pasek", x=94, y=31, w=144, h=16, popisek="GPU", sablona=f"{S(GPU_T)}°C {GG}GHz", senzor=GPU_T),
            _el("pasek", x=94, y=47, w=144, h=16, popisek="PŘÍKON", sablona=f"{S(CPU_W)}W / {S(GPU_W)}W",
                senzor=CPU_W, min=0, max=150),
            _el("pasek", x=94, y=63, w=144, h=16, popisek="RAM", sablona=RAMG + "GB", senzor=RAM, delitel=1024,
                min=0, max=32),
            _el("pasek", x=94, y=79, w=144, h=16, popisek="DISK C:", sablona=f"{S(C_FREE)}G {S(C_T)}°",
                senzor=C_USED),
            _el("pasek", x=94, y=95, w=144, h=16, popisek="DISK D:", sablona=f"{S(D_FREE)}G {S(D_T)}°",
                senzor=D_USED),
            _el("pasek", x=94, y=111, w=144, h=16, popisek="SÍŤ", sablona=f"↓ {S(DOWN, 1, 1)} ↑ {S(UP, 1, 1)}",
                senzor=DOWN, min=0, max=20)],
        "Esper – analýza (Blade Runner)": [
            _el("esper", x=0, y=0, w=156, h=104, senzor=CPU_T, min=30, max=95, sablona=f"CPU {S(CPU_T)}°C",
                roh="T-2MIN"),
            _row(0, 105, 156, f"GPU {S(GPU_T)}° {S(GPU_L)}% {S(GPU_W)}W"),
            _row(0, 117, 156, f"↓ {S(DOWN, 1, 1)} ↑ {S(UP, 1, 1)} MB/s {S(WIFI_S)}dB"),
            _el("hodiny", x=160, y=0, w=78, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM),
            _term(160, 15, 78, 112, [("ZÁT", S(CPU_L) + "%"), ("W", S(CPU_W) + "W"), ("GHZ", GC),
                                     ("JÁD", S(CORES, 1, 1)), ("RAM", RAMG + "G"), ("VRAM", VRAMG + "G"),
                                     ("C:", S(C_FREE) + "G"), ("D:", S(D_FREE) + "G")])],
        "Spinner 2049 (Blade Runner 2049)": [
            _el("seg", x=0, y=2, w=240, h=24, cas=True, zarovnani="stred", jednotka="", popisek=""),
            _el("hodiny", x=0, y=28, w=240, h=10, format="den datum", zarovnani="stred", pismo=SMALL),
            _el("cara", x=0, y=40, w=240, h=1, smer="vodorovna", tloustka=1),
            _el("seg", x=4, y=45, w=76, h=20, senzor=CPU_T, jednotka="°C", popisek="CPU"),
            _row(4, 69, 76, f"{S(CPU_L)}% {S(CPU_W)}W"),
            _row(4, 81, 76, GC + "GHz"),
            _el("seg", x=84, y=45, w=72, h=20, senzor=RAM, delitel=1024, desetinna_mista=1, jednotka="GB",
                popisek="RAM", zarovnani="stred"),
            _row(84, 69, 72, f"↓ {S(DOWN, 1, 1)}", al="stred"),
            _row(84, 81, 72, f"↑ {S(UP, 1, 1)}", al="stred"),
            _el("seg", x=160, y=45, w=78, h=20, senzor=GPU_T, jednotka="°C", popisek="GPU", zarovnani="vpravo"),
            _row(160, 69, 78, f"{S(GPU_L)}% {S(GPU_W)}W", al="vpravo"),
            _row(160, 81, 78, GG + "GHz", al="vpravo"),
            _el("pasek", x=4, y=96, w=232, h=15, popisek="DISK C:", sablona=f"{S(C_FREE)}GB volno {S(C_T)}°C",
                senzor=C_USED),
            _el("pasek", x=4, y=112, w=232, h=15, popisek="DISK D:", sablona=f"{S(D_FREE)}GB volno {S(D_T)}°C",
                senzor=D_USED)],
        "LCARS – hlavní obrazovka (Star Trek)": [
            _el("lcars_ram", x=0, y=0, w=240, h=128, pas=30, pas_nahore=9, popisek="LCARS 47", kody="01 02 03 04"),
            _row(36, 12, 110, f"C:{S(C_FREE)}G D:{S(D_FREE)}G"),
            _el("hodiny", x=150, y=12, w=88, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM),
            _el("lcars_hodnota", x=36, y=27, w=92, h=24, popisek="CPU", senzor=CPU_T, jednotka="°C", bloky=8),
            _row(130, 27, 108, f"{S(CPU_L)}% {S(CPU_W)}W", al="vpravo"),
            _row(130, 39, 108, GC + "GHz", al="vpravo"),
            _el("lcars_hodnota", x=36, y=52, w=92, h=24, popisek="GPU", senzor=GPU_T, jednotka="°C", bloky=8),
            _row(130, 52, 108, f"{S(GPU_L)}% {S(GPU_W)}W", al="vpravo"),
            _row(130, 64, 108, f"{GG}GHz {VRAMG}G", al="vpravo"),
            _el("lcars_hodnota", x=36, y=77, w=92, h=24, popisek="RAM", senzor=RAM, delitel=1024, desetinna_mista=1,
                jednotka="GB", min=0, max=32, bloky=8),
            _row(130, 77, 108, f"C:{S(C_T)}° D:{S(D_T)}°", al="vpravo"),
            _el("lcars_hodnota", x=36, y=102, w=92, h=24, popisek="SÍŤ", senzor=DOWN, desetinna_mista=1,
                jednotka="MB/S", min=0, max=20, bloky=8),
            _row(130, 102, 108, f"↑ {S(UP, 1, 1)}MB/s", al="vpravo"),
            _row(130, 114, 108, f"WIFI {S(WIFI_S)}dB", al="vpravo")],
        "Strojovna – warp jádro (Star Trek)": [
            _el("warp", x=100, y=0, w=40, h=128, senzor=CPU_L, min=0, max=100),
            _el("hodiny", x=0, y=0, w=96, h=12, format="HH:MM:SS", pismo=TERM),
            _el("hodiny", x=144, y=0, w=96, h=12, format="datum", zarovnani="vpravo", pismo=TERM),
        ] + [
            _el("lcars_hodnota", x=0, y=15 + i * 14, w=96, h=13, popisek=l, sirka_stitku=38, senzor=s, delitel=dv,
                desetinna_mista=dc, jednotka=u)
            for i, (l, s, dv, dc, u) in enumerate((("CPU", CPU_T, 1, 0, "°C"), ("ZÁT", CPU_L, 1, 0, "%"),
                                                    ("W", CPU_W, 1, 0, "W"), ("GHZ", CPU_F, 1000, 1, ""),
                                                    ("RAM", RAM, 1024, 1, "GB"), ("C:", C_FREE, 1, 0, "GB"),
                                                    ("↓", DOWN, 1, 1, "MB/S"), ("WIFI", WIFI_S, 1, 0, "DB")))
        ] + [
            _el("lcars_hodnota", x=144, y=15 + i * 14, w=96, h=13, popisek=l, sirka_stitku=38, senzor=s, delitel=dv,
                desetinna_mista=dc, jednotka=u)
            for i, (l, s, dv, dc, u) in enumerate((("GPU", GPU_T, 1, 0, "°C"), ("ZÁT", GPU_L, 1, 0, "%"),
                                                    ("W", GPU_W, 1, 0, "W"), ("GHZ", GPU_F, 1000, 1, ""),
                                                    ("VRAM", VRAM, 1000, 1, "GB"), ("D:", D_FREE, 1, 0, "GB"),
                                                    ("↑", UP, 1, 1, "MB/S"), ("DISK", C_T, 1, 0, "°C")))
        ],
    }


def label(p):
    t = TYPES.get(p.get("typ"), p.get("typ", "?"))
    if p.get("typ") == "term":
        rows = term_rows(p)
        extra = ", ".join(l for l, _t in rows[:3]) + ("…" if len(rows) > 3 else "")
    elif p.get("typ") == "seg" and p.get("cas"):
        extra = "čas"
    else:
        extra = p.get("popisek") or p.get("sablona") or p.get("senzor") or ""
    return f"{t}: {extra}".rstrip(": ")
