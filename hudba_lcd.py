# hudba_lcd.py - obrazovka "Prave hraje" na LCD Krakenu (240x240, kresli se 3x)
#
# Rozvrzeni "obal": obal alba uprostred nahore (se zari z jeho barev), pod nim nazev skladby a interpret,
# kolem okraje prstenec prubehu skladby. "cely": obal pres cely displej, text pres ztmaveny spodek.
# Vse se vejde do kruhu (displej muze byt kulaty). Plasticky vzhled: obal jako vystouply panel
# s leskem a stinem, prstenec jako trubka v drazce (screens.arc3d).
# Pismo Montserrat; znaky, ktere nema (azbuka, japonstina, korejstina...), z pisem Windows.

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import screens

BASE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(BASE, "fonts")
WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
S = 3
SIZE = 240
W = SIZE * S

_fonts = {}
_cache = {}


def _font_file(text, bold):
    """Montserrat pro latinku; jinak pismo Windows, ktere dane znaky umi."""
    cps = [ord(c) for c in text]
    if any(0xAC00 <= c <= 0xD7AF or 0x1100 <= c <= 0x11FF or 0x3130 <= c <= 0x318F for c in cps):
        return os.path.join(WIN_FONTS, "malgunbd.ttf" if bold else "malgun.ttf")          # korejstina
    if any(0x2E80 <= c <= 0x9FFF or 0xF900 <= c <= 0xFAFF or 0xFF00 <= c <= 0xFFEF for c in cps):
        return os.path.join(WIN_FONTS, "YuGothB.ttc" if bold else "YuGothM.ttc")          # CJK
    if any(c > 0x024F and not (0x2000 <= c <= 0x206F) for c in cps):
        return os.path.join(WIN_FONTS, "seguisb.ttf" if bold else "segoeui.ttf")          # azbuka, recka...
    return os.path.join(FONTS, "Montserrat-Bold.ttf" if bold else "Montserrat-SemiBold.ttf")


def _font(path, px):
    k = (path, px)
    if k not in _fonts:
        try:
            _fonts[k] = ImageFont.truetype(path, px)
        except OSError:
            try:
                _fonts[k] = ImageFont.truetype(os.path.join(FONTS, "Montserrat-SemiBold.ttf"), px)
            except OSError:
                _fonts[k] = ImageFont.load_default()
    return _fonts[k]


def _ellipsis(d, text, f, max_w):
    if d.textlength(text, font=f) <= max_w:
        return text
    while len(text) > 1 and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _lines(d, text, bold, widths, sizes, two_lines=True):
    """Rozlozit text: jeden radek v nejvetsi velikosti, ktera se vejde; jinak dva radky (zalomeni
    mezi slovy), druhy pripadne zkraceny "…". Vrati (pismo, [radky])."""
    path = _font_file(text, bold)
    for px in sizes:
        f = _font(path, px * S)
        if d.textlength(text, font=f) <= widths[0] * S:
            return f, [text]
    f = _font(path, sizes[-1] * S)
    if two_lines and len(widths) > 1:
        words = text.split()
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            if d.textlength(a, font=f) <= widths[0] * S:
                best = (a, b)
        if best is None:                                  # jedno dlouhe slovo: rozdelit po znacich
            a = _ellipsis(d, text, f, widths[0] * S)[:-1]
            best = (a, text[len(a):].lstrip())
        return f, [best[0], _ellipsis(d, best[1], f, widths[1] * S)]
    return f, [_ellipsis(d, text, f, widths[0] * S)]


def _rgb(h):
    h = str(h).lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (200, 200, 200)


def _lighter(c, k):
    return tuple(int(v + (255 - v) * k) for v in c)


def _rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
    return m


def _square(img):
    w, h = img.size
    s = min(w, h)
    return img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))


def _cover_panel(img, cover, box, radius, glow, plastic):
    """Obal alba do box (souradnice 3x): zare z barev obalu, stin, lesk (plasticky vzhled)."""
    x0, y0, x1, y1 = box
    size = (x1 - x0, y1 - y0)
    if glow:                                              # "ambilight": rozmazany zvetseny obal za nim
        g = int(size[0] * 1.45)
        amb = cover.resize((max(1, g // 4), max(1, g // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5))
        amb = amb.resize((g, g), Image.BILINEAR)
        m = Image.new("L", (g, g), 0)
        pad = (g - size[0]) // 2
        ImageDraw.Draw(m).rounded_rectangle((pad, pad, g - pad, g - pad), radius, fill=185)
        m = m.filter(ImageFilter.GaussianBlur(14 * S))
        img.paste(amb, (x0 - pad, y0 - pad), m)
    if plastic:                                           # stin pod panelem
        sh = Image.new("L", img.size, 0)
        ImageDraw.Draw(sh).rounded_rectangle((x0 + 2 * S, y0 + 5 * S, x1 + 2 * S, y1 + 5 * S), radius, fill=200)
        sh = sh.filter(ImageFilter.GaussianBlur(5 * S))
        img.paste((0, 0, 0), (0, 0), sh)
    c = _square(cover).resize(size, Image.LANCZOS)
    mask = _rounded_mask(size, radius)
    img.paste(c, (x0, y0), mask)
    if plastic:                                           # lesk shora, tmavsi spodni hrana, svetla horni
        h = size[1]
        grad = Image.linear_gradient("L").resize((1, 256)).transpose(Image.FLIP_TOP_BOTTOM)
        shine = grad.point(lambda v: int(max(0, v - 150) * 0.55)).resize(size)       # horni ~40 %
        img.paste((255, 255, 255), (x0, y0), ImageChops.multiply(mask, shine))
        edge = ImageChops.subtract(mask, ImageChops.offset(mask, 0, 2 * S))
        img.paste((255, 255, 255), (x0, y0), edge.point(lambda v: v * 70 // 255))
        low = ImageChops.subtract(mask, ImageChops.offset(mask, 0, -3 * S))
        img.paste((0, 0, 0), (x0, y0), low.point(lambda v: v * 140 // 255))
    else:                                                 # jemny okraj, at obal nesplyne s pozadim
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius, outline=(60, 62, 68), width=S)


def _base(track, cfg, plastic):
    """Obrazek bez prstence prubehu (3x). Uklada se podle skladby a nastaveni."""
    pal = [_rgb(c) for c in (track.get("paleta") or [])] or [(255, 42, 109), (5, 217, 232)]
    main = pal[0]
    title, artist = track.get("nazev", ""), track.get("interpret", "")
    cover = track.get("obal")
    img = Image.new("RGB", (W, W), (0, 0, 0))
    d = ImageDraw.Draw(img)
    glow = bool(cfg.get("zare", True))
    if cfg.get("rozvrzeni") == "cely" and cover is not None:
        c = _square(cover).resize((W, W), Image.LANCZOS)
        img.paste(c, (0, 0))
        fade = Image.linear_gradient("L").resize((W, W))                            # 0 nahore -> 255 dole
        fade = fade.point(lambda v: 0 if v < 120 else min(235, int((v - 120) * 2.3)))
        img.paste((0, 0, 0), (0, 0), fade)
        f, lines = _lines(d, title, True, (190, 176), (21, 19, 17, 15))
        y = 172 if len(lines) == 1 else 162
        for i, ln in enumerate(lines):
            d.text((W // 2, (y + i * 19) * S), ln, font=f, fill=(245, 246, 248), anchor="mm")
        if artist:
            fa, la = _lines(d, artist, False, (150,), (15, 14, 13), two_lines=False)
            d.text((W // 2, (y + len(lines) * 19 + 5) * S), la[0], font=fa, fill=_lighter(main, 0.35), anchor="mm")
        return img
    box = (62 * S, 30 * S, 178 * S, 146 * S)
    if cover is not None:
        _cover_panel(img, cover, box, 10 * S, glow, plastic)
    else:                                                 # bez obalu: nota v hlavni barve
        d.rounded_rectangle(box, 10 * S, fill=(18, 20, 24), outline=main, width=2 * S)
        f = _font(os.path.join(WIN_FONTS, "seguisym.ttf"), 70 * S)
        d.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), "♪", font=f, fill=main, anchor="mm")
    f, lines = _lines(d, title, True, (190, 176), (21, 19, 17, 16))
    y = 168 if len(lines) == 1 else 162
    tcol = _lighter(main, 0.3)
    for i, ln in enumerate(lines):
        if plastic:                                       # vytlaceni do hloubky jako u ostatnich obrazovek
            d.text((W // 2 + S, (y + i * 18) * S + 2 * S), ln, font=f, fill=tuple(v // 4 for v in tcol), anchor="mm")
        d.text((W // 2, (y + i * 18) * S), ln, font=f, fill=tcol, anchor="mm")
    if artist:
        ya = y + len(lines) * 18 + 6
        fa, la = _lines(d, artist, False, (164 if len(lines) == 1 else 140,), (15, 14, 13), two_lines=False)
        d.text((W // 2, ya * S), la[0], font=fa, fill=(205, 208, 214), anchor="mm")
    return img


def render(track, cfg, progress=None, gamma=0.65, plastic=True):
    """Obrazek 240x240 pro LCD. progress = (pozice s, delka s) nebo None."""
    key = (id(track), track.get("obal_id"), tuple(track.get("paleta") or []), cfg.get("rozvrzeni"),
           bool(cfg.get("zare", True)), bool(plastic))
    if _cache.get("key") != key:
        _cache.clear()
        _cache["key"] = key
        _cache["base"] = _base(track, cfg, plastic)
    frac = None
    if cfg.get("prubeh", True) and progress and progress[1] > 0:
        frac = max(0.0, min(1.0, progress[0] / progress[1]))
    step = None if frac is None else int(frac * 360)
    if _cache.get("step") == step and "out" in _cache:
        return _cache["out"]
    img = _cache["base"].copy()
    if step is not None:
        pal = [_rgb(c) for c in (track.get("paleta") or [])] or [(255, 42, 109), (5, 217, 232)]
        c1, c2 = (pal[1] if len(pal) > 1 else pal[0]), pal[0]
        r, thick = 118 * S, 5 * S
        if plastic:
            old = screens.PLASTIC
            screens.PLASTIC = True
            try:
                screens.arc3d(img, W // 2, W // 2, r, thick, -90, 360, step / 360, (c1, c2), caps=False)
            finally:
                screens.PLASTIC = old
        else:
            d = ImageDraw.Draw(img)
            box = (W // 2 - r, W // 2 - r, W // 2 + r, W // 2 + r)
            d.arc(box, 0, 360, fill=(32, 34, 40), width=thick)
            if step:
                d.arc(box, -90, -90 + step, fill=c2, width=thick)
    out = img.resize((SIZE, SIZE), Image.LANCZOS)
    if gamma and gamma != 1.0:
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        out = out.point(lut * 3)
    _cache["step"], _cache["out"] = step, out
    return out
