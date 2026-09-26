# led_efekty.py - softwarove efekty LED pro vsechny ventilatory
#
# Aplikace sama pocita barvu kazde LED (~30x za sekundu) a posila ji ventilatorum v primem
# rezimu (F140 pres NZXT "super-fixed", ventilatory na desce pres ARGB hlavicku D_LED1).
# Diky tomu je jas pod kontrolou a efekty jsou stejne a synchronni na vsech ventilatorech.
# Ciste vypocty bez hardwaru - pouziva je vlakno LED (led.py) i zivy nahled v nastaveni.
#
# Ventilator ("cil") = (klic, pocet LED, skupina): F140 maji 8 LED, 3 ventilatory na desce
# jsou paralelne na jedne hlavicce a sviti stejne (16 LED).

import colorsys
import math
import random

FPS = 30

# typ -> (cesky nazev, pocet barev, rychlost, smer)
EFFECTS = {
    "barva": ("jedna barva", 1, False, False),
    "vlastni": ("vlastní barvy LED", 0, False, False),
    "duha_toceni": ("duha – točení", 0, True, True),
    "duha_prelevani": ("duha – přelévání", 0, True, False),
    "dychani": ("dýchání", 3, True, False),
    "kometa": ("kometa", 2, True, True),
    "prechod": ("přechod 2 barev", 2, True, True),
    "trpyt": ("třpyt", 2, True, False),
    "ohen": ("oheň / svíčka", 0, True, False),
    "blikani": ("blikání", 1, True, False),
    "paleta": ("paleta – točení", 3, True, True),
    "vysece": ("výseče – točení", 3, True, True),
    "dvojita_kometa": ("dvojitá kometa", 2, True, True),
    "stirani": ("stírání barev", 3, True, True),
    "polarni_zare": ("polární záře", 3, True, False),
    "plazma": ("plazma (duha)", 0, True, False),
    "duhovy_trpyt": ("duhový třpyt", 0, True, False),
    "tep": ("tep srdce", 1, True, False),
    "stroboskop": ("stroboskop", 1, True, False),
    "policie": ("policie", 2, True, False),
    "teplota": ("podle teploty", 3, False, False),
    "vypnuto": ("vypnuto", 0, False, False),
}
ANIMATED = {k for k, v in EFFECTS.items() if v[2]} | {"teplota"}

DEFAULT_EFFECT = {"typ": "duha_toceni", "barvy": ["#ff0000", "#0060ff", "#00ff40"], "rychlost": 4,
                  "opacny_smer": False, "senzor": "CPU (Tctl/Tdie)", "min": 40, "max": 90}


def hex_rgb(h):
    h = str(h).lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _scale(c, k):
    return tuple(v * k for v in c)


def _hsv(h, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, v)
    return (r * 255, g * 255, b * 255)


def _gradient(colors, t):
    """Plynuly prechod pres seznam barev, t = 0..1."""
    if len(colors) == 1:
        return colors[0]
    t = max(0.0, min(1.0, t)) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    return _mix(colors[i], colors[i + 1], t - i)


def _cyclic(colors, p, hard=False):
    """Barva na pozici p (0..1) v kruhu barev: za posledni barvou zase prvni."""
    k = len(colors)
    x = (p % 1.0) * k
    a = int(x) % k
    if hard:
        return colors[a]
    f = x - int(x)
    return _mix(colors[a], colors[(a + 1) % k], f * f * (3 - 2 * f))


def _comet(head, n, tail, color, direction):
    """Jas jedne komety pro kazdou LED (hlava na pozici head, ocas za ni)."""
    out = []
    for i in range(n):
        d = (head - i) % n if direction > 0 else (i - head) % n     # vzdalenost za hlavou
        out.append(_scale(color, max(0.0, 1 - d / tail) ** 2))
    return out


class Engine:
    """Pocita snimky. Stav (trpyt, ohen, vyhlazena teplota) drzi pro kazdy cil zvlast."""

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.state = {}

    def frame(self, eff, t, key, n, fan_idx=0, fan_count=1, wave=False, custom=None, data=None, dt=1 / FPS):
        """Barvy (r, g, b) 0-255 jako float pro n LED jednoho ventilatoru v case t."""
        typ = eff.get("typ", "vypnuto")
        cols = [hex_rgb(c) for c in eff.get("barvy", [])] or [(255, 255, 255)]
        speed = max(1, min(10, int(eff.get("rychlost", 4))))
        rate = 0.08 * speed                       # otacky za sekundu (1 -> 0,08, 10 -> 0,8)
        direction = -1 if eff.get("opacny_smer") else 1
        offset = fan_idx / max(1, fan_count) if wave else 0.0
        black = (0.0, 0.0, 0.0)

        if typ == "barva":
            return [cols[0]] * n
        if typ == "vlastni":
            src = [hex_rgb(c) for c in (custom or [])] or [(255, 255, 255)]
            return [src[i % len(src)] for i in range(n)]
        if typ == "duha_toceni":
            ph = t * rate * direction + offset
            return [_hsv(i / n + ph) for i in range(n)]
        if typ == "duha_prelevani":
            c = _hsv(t * rate * 0.5 + offset)
            return [c] * n
        if typ == "dychani":
            period = 6.0 / speed * 2              # jeden nadech (s)
            x = t / period + offset
            cycle = int(x)
            k = (1 - math.cos((x - cycle) * 2 * math.pi)) / 2
            return [_scale(cols[cycle % len(cols)], k)] * n
        if typ == "kometa":
            head = ((t * rate * direction + offset) % 1.0) * n
            tail = max(2.0, n * 0.6)
            bg = _scale(cols[1], 0.08) if len(cols) > 1 else black
            out = []
            for i in range(n):
                d = (head - i) % n if direction > 0 else (i - head) % n     # vzdalenost za hlavou
                k = max(0.0, 1 - d / tail) ** 2
                out.append(tuple(max(bg[j], cols[0][j] * k) for j in range(3)))
            return out
        if typ == "prechod":
            c2 = cols[1] if len(cols) > 1 else black
            ph = t * rate * direction + offset
            return [_mix(cols[0], c2, (1 + math.cos(2 * math.pi * (i / n + ph))) / 2) for i in range(n)]
        if typ == "trpyt":
            st = self.state.setdefault(("trpyt", key), [0.0] * n)
            if len(st) != n:
                st[:] = [0.0] * n
            base = _scale(cols[1], 0.12) if len(cols) > 1 else black
            decay = 0.6 ** (dt * speed * 2)
            for i in range(n):
                st[i] *= decay
                if self.rng.random() < dt * speed * 0.25:
                    st[i] = 1.0
            return [tuple(max(base[j], cols[0][j] * st[i]) for j in range(3)) for i in range(n)]
        if typ == "ohen":
            st = self.state.setdefault(("ohen", key), [0.6] * n)
            if len(st) != n:
                st[:] = [0.6] * n
            a = min(1.0, dt * speed * 1.5)
            out = []
            for i in range(n):
                st[i] += (self.rng.uniform(0.25, 1.0) - st[i]) * a
                v = st[i]
                out.append(_mix((255, 40, 0), (255, 170, 20), v * v) if v > 0.3 else _scale((255, 40, 0), v / 0.3))
            return [_scale(c, 0.35 + 0.65 * st[i]) for i, c in enumerate(out)]
        if typ == "blikani":
            on = ((t * speed * 0.8 + offset) % 1.0) < 0.5
            return [cols[0] if on else black] * n
        if typ in ("paleta", "vysece"):
            ph = t * rate * direction + offset
            return [_cyclic(cols, i / n + ph, hard=typ == "vysece") for i in range(n)]
        if typ == "dvojita_kometa":
            head = ((t * rate * direction + offset) % 1.0) * n
            c2 = cols[1] if len(cols) > 1 else cols[0]
            a = _comet(head, n, max(2.0, n * 0.4), cols[0], direction)
            b = _comet((head + n / 2) % n, n, max(2.0, n * 0.4), c2, direction)
            return [tuple(max(a[i][j], b[i][j]) for j in range(3)) for i in range(n)]
        if typ == "stirani":
            x = t * rate * 1.5 + offset
            step = int(x)
            edge = (x - step) * n
            prev, cur = cols[step % len(cols)], cols[(step + 1) % len(cols)]
            out = []
            for i in range(n):
                j = i if direction > 0 else n - 1 - i
                out.append(_mix(prev, cur, edge - j))            # mekka hrana jedne LED
            return out
        if typ == "polarni_zare":
            ph = t * rate * 0.35
            out = []
            for i in range(n):
                u = i / n + offset
                x = 0.5 + 0.3 * math.sin(2 * math.pi * (u + ph)) + 0.2 * math.sin(2 * math.pi * (2 * u - ph * 1.7) + 1.3)
                k = 0.55 + 0.45 * math.sin(2 * math.pi * (u * 3 + ph * 0.8) + 0.5)
                out.append(_scale(_gradient(cols, x), k))
            return out
        if typ == "plazma":
            ph = t * rate
            out = []
            for i in range(n):
                u = i / n + offset
                v = math.sin(2 * math.pi * (2 * u + ph)) + math.sin(2 * math.pi * (u - ph * 0.7) + 1.1)
                out.append(_hsv(v / 4 + ph * 0.25))
            return out
        if typ == "duhovy_trpyt":
            st = self.state.setdefault(("duhovy_trpyt", key), [[0.0, 0.0] for _ in range(n)])
            if len(st) != n:
                st[:] = [[0.0, 0.0] for _ in range(n)]
            decay = 0.6 ** (dt * speed * 2)
            for s_ in st:
                s_[0] *= decay
                if self.rng.random() < dt * speed * 0.3:
                    s_[:] = [1.0, self.rng.random()]
            return [_hsv(h, v) for v, h in st]
        if typ == "tep":
            period = 60.0 / (40 + 10 * speed)                  # 50-140 uderu za minutu
            p = ((t / period + offset) % 1.0) * period
            k = math.exp(-p / 0.09)
            if p >= 0.25:
                k = max(k, 0.65 * math.exp(-(p - 0.25) / 0.09))
            return [_scale(cols[0], max(0.03, k))] * n
        if typ == "stroboskop":
            freq = 0.4 * speed                                 # zablesky za sekundu
            on = ((t * freq + offset) % 1.0) < max(0.06 * freq, 0.02)
            return [cols[0] if on else black] * n
        if typ == "policie":
            c2 = cols[1] if len(cols) > 1 else cols[0]
            p = (t * speed * 0.3 + offset) % 1.0
            side = 0 if p < 0.5 else 1
            on = int((p % 0.5) * 12) % 2 == 0                  # 3 zablesky na kazde strane
            out = []
            for i in range(n):
                mine = (i < n / 2) == (side == 0)
                out.append((cols[0] if side == 0 else c2) if on and mine else black)
            return out
        if typ == "teplota":
            v = None
            item = (data or {}).get(eff.get("senzor", ""))
            if item is not None:
                v = item.get("value")
            smooth = self.state.get(("teplota", key))
            if v is not None:                     # vyhlazeni ~2 s, aby barva neskakala
                smooth = v if smooth is None else smooth + (v - smooth) * min(1.0, dt / 2.0)
                self.state[("teplota", key)] = smooth
            if smooth is None:
                return [(40.0, 40.0, 40.0)] * n
            lo, hi = float(eff.get("min", 40)), float(eff.get("max", 90))
            fr = 0.0 if hi == lo else (smooth - lo) / (hi - lo)
            return [_gradient(cols, fr)] * n
        return [black] * n


def apply_brightness(colors, percent):
    """Jas 0-100 % -> vnimany jas (kvadraticky), vystup cela cisla 0-255."""
    k = max(0.0, min(1.0, percent / 100.0)) ** 2
    return [[int(round(max(0, min(255, c[j] * k)))) for j in range(3)] for c in colors]
