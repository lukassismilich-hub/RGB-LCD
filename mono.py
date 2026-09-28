# mono.py - vykresleni pro monochromaticky Alphacool USB display (240x128, 1 bit)
# Rozvrzeni je seznam volne umistenych prvku (prvky.py). Tady jen vstup pro vlakno
# displeje a nahled pro okno nastaveni.

from PIL import Image

import prvky

WIDTH, HEIGHT = prvky.WIDTH, prvky.HEIGHT


def render(acfg, data, history=None, now=None):
    """Obrazek v rezimu "1" (1 = rozsviceny bod) tak, jak ho vidi uzivatel (i na vysku)."""
    return prvky.render(acfg, data, history, now)


def to_panel(img, acfg):
    """Otoceni podle montaze displeje -> 240x128 pro odeslani."""
    return prvky.to_panel(img, acfg)


def graph_sensors(acfg):
    """{senzor: delka_s} pro vsechny grafy na displeji (hlavni smycka pro ne drzi historii)."""
    out = {}
    for p in prvky.items(acfg):
        if (p.get("typ") == "graf" or p.get("typ") in prvky.HISTORY_TYPES) and p.get("senzor"):
            out[p["senzor"]] = max(out.get(p["senzor"], 0), float(p.get("delka_s", 120)))
    return out


def preview(img, scale=2, on=(235, 242, 255), off=(24, 52, 190)):
    """Nahled pro okno nastaveni: barvy jako modry STN displej, zvetseny."""
    rgb = Image.new("RGB", img.size, off)
    rgb.paste(on, (0, 0), img.convert("L"))
    return rgb.resize((img.width * scale, img.height * scale), Image.NEAREST)
