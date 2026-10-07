# prvky_starwars.py - prvky a hotove obrazovky pro Alphacool s tematikou Star Wars
# Nacte ho prvky_scifi.py na konci (stejne API prvku: draw(img, d, p, data, now)).
#
#   zamerovac     zamerovaci pocitac X-wingu: dratovy prikop leti k divakovi (rychlost podle hodnoty),
#                 uprostred zamerovaci krize; od 85 % rozsahu blika ramecek "zamereno"
#   mec           svetelny mec: rukojet a cepel dlouha podle hodnoty, nad nim popisek a hodnoty
#   hvezda_smrti  Hvezda smrti s talirem superlaseru a prikopem, kolem prstenec "nabiti" podle hodnoty
#   hyperprostor  hvezdy se pri vyssi hodnote natahuji do car a leti rychleji
#   yavin         takticky displej bitvy o Yavin: Hvezda smrti obiha planetu k mesici podle hodnoty
#   stitek        radek se stitkem: popisek inverzne v plnem obdelniku, za nim text ze sablony
#   rohy          rohovy ramecek (jen rohy, jako zamerovaci displej)
#
# Vsechno se kresli jen cary a body (1 bit, 240x128) - zadna loga ani pisma z filmu.

import math
import random

from PIL import Image, ImageDraw

from prvky import _num, frac, get_font, value
from prvky_scifi import (C_FREE, C_T, C_USED, CORES, CPU_L, CPU_T, CPU_W, D_FREE, D_T, DOWN, GC, GG, GPU_L, GPU_T,
                         GPU_W, RAM, RAMG, SMALL, TERM, UP, VRAMG, WIFI_S, S, _el, _header, _row, _term,
                         _xor_text, fill_template)

LINK = "@síť rychlost připojení"


def _fr(p, data):
    return frac(value(data, p.get("senzor"), p.get("delitel", 1)), _num(p, "min", 0), _num(p, "max", 100))


def _t(now):
    return now.timestamp()


def _layer(w, h):
    """Pomocna vrstva velikosti prvku - co z ni vycuhuje, se pri vlozeni orizne."""
    lay = Image.new("1", (max(1, w), max(1, h)), 0)
    return lay, ImageDraw.Draw(lay)


def _dotted_line(d, p0, p1, step=3, fill=1):
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / step))
    for i in range(n + 1):
        d.point((p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n), fill=fill)


def _dotted_circle(d, cx, cy, rx, ry, step_deg=6, a0=0, a1=360, fill=1):
    a = a0
    while a <= a1:
        t = math.radians(a)
        d.point((cx + rx * math.cos(t), cy + ry * math.sin(t)), fill=fill)
        a += step_deg


# ------------------------------------------------------------ zamerovaci pocitac (X-wing)
def draw_trench(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    if w < 20 or h < 20:
        return
    fr = _fr(p, data)
    lay, ld = _layer(w, h)
    vx, vy = w / 2, h * 0.40                                   # uberny bod
    near = [(3, h * 0.10), (3, h - 4), (w - 4, h - 4), (w - 4, h * 0.10)]   # prurez prikopem: stena-dno-stena

    def at(pt, k):                                            # bod prurezu v hloubce k (1 = u divaka)
        return vx + (pt[0] - vx) * k, vy + (pt[1] - vy) * k

    for pt in near:                                           # podelne hrany prikopu
        ld.line((at(pt, 1.0), at(pt, 0.07)), fill=1)
    phase = (_t(now) * (0.4 + 2.6 * fr)) % 1.0                # pricky leti k divakovi, rychleji pri zatezi
    for i in range(6):                                        # u uberneho bodu jen hrany, at je videt kriz
        z = (i + 1 - phase) * 0.8
        k = 1 / (1 + z)
        if k > 0.98 or k < 0.2:
            continue
        ld.line([at(pt, k) for pt in near], fill=1)
    for sx in (-1, 1):                                        # zamerovaci kriz: vodorovne rysky s mezerou
        ld.line((vx + sx * 6, vy, vx + sx * 16, vy), fill=1)
        ld.line((vx + sx * 16, vy - 2, vx + sx * 16, vy + 2), fill=1)
    ld.line((vx, vy - 6, vx, vy - 10), fill=1)
    if fr >= 0.85 and now.microsecond < 500000:               # "zamereno"
        ld.rectangle((vx - 5, vy - 4, vx + 5, vy + 4), outline=1)
    img.paste(1, (x, y), lay)
    d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)


# ------------------------------------------------------------ svetelny mec
def draw_saber(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    fr = _fr(p, data)
    f = get_font(p.get("pismo", TERM))
    if h >= 20:                                               # radek s popiskem a hodnotami nad mecem
        d.text((x, y), p.get("popisek", ""), font=f, fill=1, anchor="lt")
        d.text((x + w - 1, y), fill_template(p.get("sablona", ""), data), font=f, fill=1, anchor="rt")
        top = y + 14
    else:
        top = y
    bot = y + h - 1
    bh = bot - top + 1
    if bh < 5:
        return
    hl = max(24, int(bh * 2.6))                               # delka rukojeti
    g0, g1 = x + 3, x + int(hl * 0.62)
    d.rectangle((x, top + 1, x + 2, bot - 1), fill=1)         # hlavice
    d.rectangle((g0, top + 2, g1, bot - 2), outline=1)        # rukojet s rybovanim
    for xx in range(g0 + 2, g1 - 1, 2):
        d.line((xx, top + 2, xx, bot - 2), fill=1)
    d.rectangle((g1 + 1, top + 1, x + hl - 1, bot - 1), fill=1)   # aktivacni cast a emitor
    d.rectangle((x + hl - 4, top, x + hl - 1, bot), fill=1)
    if bh >= 9:
        d.rectangle((g1 + 3, top + 3, g1 + 5, top + 4), fill=0)   # tlacitko
    b0, b_end = x + hl + 1, x + w - 1
    b1 = b0 + round((b_end - b0) * fr)
    cy = (top + bot) // 2
    for xx in range(b1 + 3, b_end, 3):                         # zbytek rozsahu jen tecky
        d.point((xx, cy), fill=1)
    d.line((b_end, cy - 2, b_end, cy + 2), fill=1)
    if b1 - b0 >= 3:
        r = max(1, (bh - 2) // 2)
        d.rounded_rectangle((b0, top + 1, b1, bot - 1), r, outline=1)     # zare
        if bh >= 7:
            d.rounded_rectangle((b0, top + 3, b1 - 2, bot - 3), max(1, r - 2), fill=1)   # jadro


# ------------------------------------------------------------ Hvezda smrti
def draw_deathstar(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    fr = _fr(p, data)
    R = min(w, h) // 2 - 1
    if R < 16:
        return
    cx, cy = x + w // 2, y + h // 2
    ring = p.get("prstenec", True)
    r = R - 9 if ring else R
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=1)
    # povrch: rovnobezky a poledniky teckovane, prikop na rovniku
    lay, ld = _layer(2 * r + 1, 2 * r + 1)
    ox = oy = r
    for k in (-0.62, -0.3, 0.32, 0.62):
        yy = oy + r * k
        hw = math.sqrt(max(0, r * r - (yy - oy) ** 2))
        for xx in range(int(ox - hw) + 2, int(ox + hw) - 1, 3):
            ld.point((xx, yy), fill=1)
    for k in (0.45, 0.85):
        _dotted_circle(ld, ox, oy, r * k, r, step_deg=7, a0=20, a1=160)
    ty = oy + r * 0.06
    hw = math.sqrt(max(0, r * r - (ty - oy) ** 2))
    ld.rectangle((ox - hw + 1, ty - 1, ox + hw - 1, ty + 1), fill=0)
    ld.line((ox - hw + 1, ty - 1, ox + hw - 1, ty - 1), fill=1)
    ld.line((ox - hw + 1, ty + 1, ox + hw - 1, ty + 1), fill=1)
    rng = random.Random(4)                                    # svetla mesta (vzdy stejna)
    for _ in range(int(r * 1.4)):
        a, rr = rng.uniform(0, math.tau), r * math.sqrt(rng.random()) * 0.92
        ld.point((ox + rr * math.cos(a), oy + rr * math.sin(a)), fill=1)
    dx, dy, dr = ox - r * 0.38, oy - r * 0.36, r * 0.27      # talir superlaseru
    ld.ellipse((dx - dr - 1, dy - dr - 1, dx + dr + 1, dy + dr + 1), fill=0)
    ld.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), outline=1)
    ld.ellipse((dx - dr * 0.4, dy - dr * 0.4, dx + dr * 0.4, dy + dr * 0.4), outline=1)
    for a in (210, 330, 90):
        t = math.radians(a)
        _dotted_line(ld, (dx + dr * math.cos(t), dy + dr * math.sin(t)), (dx, dy), step=2)
    ld.point((dx, dy), fill=1)
    mask = Image.new("1", lay.size, 0)
    ImageDraw.Draw(mask).ellipse((1, 1, 2 * r - 1, 2 * r - 1), fill=1)
    img.paste(lay, (cx - r, cy - r), mask)
    if fr >= 0.95 and now.microsecond < 600000:              # plne nabito: paprsek
        bx, by = cx - r * 0.38, cy - r * 0.36
        d.line((bx, by, x, by - r * 0.3), fill=1, width=2)
    if ring:                                                  # prstenec nabiti
        n = 36
        on = round(n * fr)
        for i in range(n):
            a0 = -90 + i * 360 / n + 1.5
            a1 = a0 + 360 / n - 3
            if i < on:
                d.arc((cx - R, cy - R, cx + R, cy + R), a0, a1, fill=1, width=4)
            else:
                t = math.radians((a0 + a1) / 2)
                d.point((cx + (R - 2) * math.cos(t), cy + (R - 2) * math.sin(t)), fill=1)


# ------------------------------------------------------------ hyperprostor
def draw_hyperspace(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    if w < 10 or h < 10:
        return
    fr = _fr(p, data)
    lay, ld = _layer(w, h)
    cx, cy = w / 2, h / 2
    maxr = math.hypot(cx, cy)
    t = _t(now)
    rng = random.Random(7)
    speed = 0.12 + 0.9 * fr                                   # podil cesty od stredu k okraji za sekundu
    for _ in range(int(_num(p, "hvezdy", 70))):
        a = rng.uniform(0, math.tau)
        s = rng.uniform(0.6, 1.4)
        ph = (rng.random() + t * speed * s) % 1.0
        r0 = maxr * ph * ph                                    # zrychluje smerem k okraji
        ln = 1 + fr * r0 * 0.9                                 # pri zatezi dlouhe cary
        ca, sa = math.cos(a), math.sin(a)
        ld.line((cx + r0 * ca, cy + r0 * sa, cx + (r0 + ln) * ca, cy + (r0 + ln) * sa), fill=1)
    img.paste(1, (x, y), lay)
    if p.get("ramecek", True):
        d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)


# ------------------------------------------------------------ bitva o Yavin
def draw_yavin(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    if w < 40 or h < 40:
        return
    fr = _fr(p, data)
    lay, ld = _layer(w, h)
    pr = h * 0.55                                             # planeta, z vetsi casti mimo displej vlevo
    px, py = -pr * 0.35, h * 0.5
    ld.ellipse((px - pr, py - pr, px + pr, py + pr), outline=1)
    ld.ellipse((px - pr + 1, py - pr + 1, px + pr - 1, py + pr - 1), outline=1)
    for k in (0.82, 0.62):                                    # pasy plynneho obra
        _dotted_circle(ld, px, py, pr * k, pr * k, step_deg=4, a0=-80, a1=80)
    ox, oy = w - 12 - px, h / 2 - 10                          # draha Hvezdy smrti a mesice: elipsa (sikmy pohled)
    a_start, a_moon = -60.0, 55.0
    _dotted_circle(ld, px, py, ox, oy, step_deg=2, a0=a_start - 12, a1=a_moon + 12)
    tm = math.radians(a_moon)
    mx, my = px + ox * math.cos(tm), py + oy * math.sin(tm)
    ld.ellipse((mx - 4, my - 4, mx + 4, my + 4), fill=1)      # mesic Yavin 4
    for sx in (-1, 1):                                        # zamerovaci zavorky kolem mesice
        ld.line((mx + sx * 7, my - 7, mx + sx * 9, my - 7), fill=1)
        ld.line((mx + sx * 9, my - 7, mx + sx * 9, my + 7), fill=1)
        ld.line((mx + sx * 7, my + 7, mx + sx * 9, my + 7), fill=1)
    ta = math.radians(a_start + (a_moon - 22 - a_start) * fr)   # Hvezda smrti se blizi k dosahu
    sx_, sy_ = px + ox * math.cos(ta), py + oy * math.sin(ta)
    ld.ellipse((sx_ - 6, sy_ - 6, sx_ + 6, sy_ + 6), fill=0, outline=1)
    ld.line((sx_ - 6, sy_ + 1, sx_ + 6, sy_ + 1), fill=1)
    ld.ellipse((sx_ - 4, sy_ - 4, sx_ - 1, sy_ - 1), outline=1)
    if fr >= 0.99:                                            # v dosahu: carkovana cara k mesici, blika
        if now.microsecond < 600000:
            _dotted_line(ld, (sx_, sy_), (mx, my), step=2)
    img.paste(1, (x, y), lay)


# ------------------------------------------------------------ obecne: radek se stitkem, rohovy ramecek
def draw_tag_row(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    f = get_font(p.get("pismo", TERM))
    lbl = p.get("popisek", "")
    tw = int(_num(p, "sirka_stitku", 0)) or int(d.textlength(lbl, font=f)) + 6
    tw = min(tw, w)
    d.rectangle((x, y, x + tw - 1, y + h - 1), fill=1)
    _xor_text(img, (x + tw / 2, y + h / 2), lbl, f, "mm")
    txt = fill_template(p.get("sablona", ""), data)
    if txt:
        if p.get("zarovnani") == "vpravo":
            d.text((x + w - 1, y + h / 2), txt, font=f, fill=1, anchor="rm")
        else:
            d.text((x + tw + 3, y + h / 2), txt, font=f, fill=1, anchor="lm")


def draw_corners(img, d, p, data, now):
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    k = max(2, int(_num(p, "delka", 6)))
    x1, y1 = x + w - 1, y + h - 1
    for cx, cy, sx, sy in ((x, y, 1, 1), (x1, y, -1, 1), (x, y1, 1, -1), (x1, y1, -1, -1)):
        d.line((cx, cy, cx + sx * k, cy), fill=1)
        d.line((cx, cy, cx, cy + sy * k), fill=1)


DRAW = {"zamerovac": draw_trench, "mec": draw_saber, "hvezda_smrti": draw_deathstar, "hyperprostor": draw_hyperspace,
        "yavin": draw_yavin, "stitek": draw_tag_row, "rohy": draw_corners}
TYPES = {"zamerovac": "Zaměřovač X-wingu (Star Wars)", "mec": "Světelný meč (Star Wars)",
         "hvezda_smrti": "Hvězda smrti (Star Wars)", "hyperprostor": "Hyperprostor (Star Wars)",
         "yavin": "Bitva o Yavin (Star Wars)", "stitek": "Řádek se štítkem", "rohy": "Rohový rámeček"}
NEW = {
    "zamerovac": dict(x=0, y=0, w=140, h=100, senzor=CPU_L, min=0, max=100, delitel=1),
    "mec": dict(x=2, y=2, w=236, h=27, popisek="CPU", sablona=S(CPU_T) + "°C", senzor=CPU_T, min=30, max=95,
                delitel=1, pismo=TERM),
    "hvezda_smrti": dict(x=0, y=0, w=128, h=128, senzor=CPU_L, min=0, max=100, delitel=1, prstenec=True),
    "hyperprostor": dict(x=0, y=14, w=240, h=58, senzor=CPU_L, min=0, max=100, delitel=1, hvezdy=70, ramecek=True),
    "yavin": dict(x=0, y=0, w=150, h=128, senzor=CPU_T, min=40, max=95, delitel=1),
    "stitek": dict(x=2, y=2, w=120, h=11, popisek="CPU", sablona=S(CPU_T) + "°", sirka_stitku=24,
                   zarovnani="vlevo", pismo=TERM),
    "rohy": dict(x=2, y=2, w=100, h=60, delka=6),
}


def templates():
    """Hotove obrazovky 240x128 s tematikou Star Wars."""
    return {
        "Zaměřovací počítač (Star Wars – X-wing)": [
            _el("zamerovac", x=0, y=0, w=140, h=100, senzor=CPU_L, min=0, max=100),
            _el("seg", x=2, y=104, w=136, h=22, senzor=CPU_T, jednotka="°C", popisek="CPU", zarovnani="stred"),
            _el("obdelnik", x=144, y=0, w=96, h=12, vypln="plna"),
            _el("hodiny", x=144, y=0, w=96, h=12, format="HH:MM:SS", zarovnani="stred", pismo=TERM, barva=0),
            _term(146, 15, 92, 112, [("ZÁTĚŽ", S(CPU_L) + "%"), ("PŘÍKON", S(CPU_W) + "W"), ("TAKT", GC + "G"),
                                     ("GPU", f"{S(GPU_T)}° {S(GPU_L)}%"), ("GPU W", S(GPU_W) + "W"),
                                     ("RAM", RAMG + "G"), ("↓", S(DOWN, 1, 1) + "MB"), ("↑", S(UP, 1, 1) + "MB")])],
        "Světelné meče (Star Wars)": _header("SVĚTELNÉ MEČE") + [
            _el("mec", x=2, y=15, w=236, h=27, popisek="CPU", sablona=f"{S(CPU_T)}°C  {S(CPU_L)}%  {S(CPU_W)}W",
                senzor=CPU_T, min=30, max=95),
            _el("mec", x=2, y=43, w=236, h=27, popisek="GPU", sablona=f"{S(GPU_T)}°C  {S(GPU_L)}%  {S(GPU_W)}W",
                senzor=GPU_T, min=30, max=90),
            _el("mec", x=2, y=71, w=236, h=27, popisek="RAM", sablona=f"{RAMG} GB  VRAM {VRAMG} GB",
                senzor=RAM, delitel=1024, min=0, max=32),
            _el("mec", x=2, y=99, w=236, h=27, popisek="DISK C:", sablona=f"{S(C_FREE)} GB volno  {S(C_T)}°C",
                senzor=C_USED, min=0, max=100)],
        "Hvězda smrti – superlaser (Star Wars)": [
            _el("hvezda_smrti", x=0, y=0, w=128, h=128, senzor=CPU_L, min=0, max=100),
            _row(132, 0, 106, "SUPERLASER"),
            _el("seg", x=132, y=15, w=106, h=24, senzor=CPU_L, jednotka="%", popisek="NABITÍ"),
            _el("cara", x=132, y=43, w=106, h=1, smer="vodorovna", tloustka=1),
            _term(132, 47, 106, 66, [("CPU", S(CPU_T) + "°C"), ("GPU", f"{S(GPU_T)}° {S(GPU_L)}%"),
                                     ("PŘÍKON", f"{S(CPU_W)}+{S(GPU_W)}W"), ("RAM", RAMG + "GB"),
                                     ("↓ SÍŤ", S(DOWN, 1, 1) + "MB/s")]),
            _el("hodiny", x=132, y=115, w=106, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM)],
        "Hyperprostor (Star Wars – Millennium Falcon)": [
            _el("obdelnik", x=0, y=0, w=240, h=12, vypln="plna"),
            _row(2, 0, 156, f"HYPERPROSTOR {S(CPU_L)}%", barva=0),
            _el("hodiny", x=160, y=0, w=78, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM, barva=0),
            _el("hyperprostor", x=0, y=14, w=240, h=58, senzor=CPU_L, min=0, max=100),
            _el("seg", x=4, y=76, w=76, h=20, senzor=CPU_T, jednotka="°C", popisek="CPU"),
            _el("seg", x=84, y=76, w=76, h=20, senzor=GPU_T, jednotka="°C", popisek="GPU"),
            _el("seg", x=164, y=76, w=74, h=20, senzor=RAM, delitel=1024, desetinna_mista=1, jednotka="GB",
                popisek="RAM"),
            _row(2, 100, 118, f"CPU {S(CPU_W)}W {GC}G"),
            _row(122, 100, 116, f"GPU {S(GPU_L)}% {S(GPU_W)}W", al="vpravo"),
            _row(2, 113, 118, f"C: {S(C_FREE)}G D: {S(D_FREE)}G"),
            _row(122, 113, 116, f"↓ {S(DOWN, 1, 1)} ↑ {S(UP, 1, 1)} MB/s", al="vpravo")],
        # pres cely displej; hodnoty mimo drahu Hvezdy smrti (od -60 do 33 stupnu, polomer 6 px)
        "Bitva o Yavin – taktický displej (Star Wars)": [
            _el("yavin", x=0, y=0, w=240, h=128, senzor=CPU_T, min=40, max=95),
            _row(24, 0, 130, "TAKTICKÝ DISPLEJ · YAVIN 4", h=10, font=SMALL),
            # v planete na cernem podkladu: zatez CPU a GPU
            _el("obdelnik", x=0, y=31, w=38, h=66, vypln="plna", barva=0),
            _el("stitek", x=1, y=33, w=36, h=11, popisek="CPU", sablona="", sirka_stitku=36),
            _el("seg", x=1, y=47, w=36, h=17, senzor=CPU_L, jednotka="%", popisek="", zarovnani="stred"),
            _el("stitek", x=1, y=67, w=36, h=11, popisek="GPU", sablona="", sirka_stitku=36),
            _el("seg", x=1, y=80, w=36, h=17, senzor=GPU_L, jednotka="%", popisek="", zarovnani="stred"),
            # uvnitr drahy: blok hodnot v rohovem ramecku, radky se stitky
            _el("rohy", x=44, y=36, w=121, h=64, delka=6),
            _el("stitek", x=48, y=39, w=120, h=11, popisek="CPU", sablona=f"{S(CPU_T)}° {S(CPU_W)}W {GC}GHz",
                sirka_stitku=22),
            _el("stitek", x=48, y=51, w=120, h=11, popisek="GPU", sablona=f"{S(GPU_T)}° {S(GPU_W)}W {GG}GHz",
                sirka_stitku=22),
            _el("stitek", x=48, y=63, w=120, h=11, popisek="RAM", sablona=f"{RAMG}G VRAM {VRAMG}G",
                sirka_stitku=22),
            _el("stitek", x=48, y=75, w=120, h=11, popisek="C:", sablona=f"{S(C_FREE)}G volno {S(C_T)}°",
                sirka_stitku=22),
            _el("stitek", x=48, y=87, w=120, h=11, popisek="D:", sablona=f"{S(D_FREE)}G volno {S(D_T)}°",
                sirka_stitku=22),
            # vlevo dole pod planetou
            _row(30, 117, 76, f"AKTIVNÍ JÁDRA {S(CORES, 1, 1)}", h=10, font=SMALL),
            # vpravo nahore nad drahou
            _el("hodiny", x=166, y=0, w=72, h=12, format="HH:MM:SS", zarovnani="vpravo", pismo=TERM),
            _el("hodiny", x=150, y=12, w=88, h=11, format="den datum", zarovnani="vpravo", pismo=SMALL),
            # vpravo dole pod drahou
            _row(160, 101, 78, f"{S(WIFI_S)}dB {S(LINK)}Mb", al="vpravo"),
            _row(134, 115, 104, f"↓{S(DOWN, 1, 1)} ↑{S(UP, 1, 1)} MB/s", al="vpravo")],
    }
