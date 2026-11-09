# klavesnice_efekty.py - plosne efekty pro klavesnici G815 (barva kazde klavesy zvlast)
#
# Ventilator je kruh, klavesnice plocha: efekty pocitaji s polohou klavesy (klavesnice_rozlozeni.KEYS,
# souradnice v "u" = sirka bezne klavesy). Bez hardwaru - vlakno LED i nahled v okne.
# Engine.frame(eff, dt, data, music) -> [(r, g, b)] v poradi KEYS (0-255, bez jasu).
#
# eff (config["led"]["efekt_klavesnice"]): "typ" + parametry podle PARAMS:
#   barvy (+ pocet_barev), duha (misto barev plna duha), rychlost 1-10, smer (uhel ve stupnich,
#   0 = doprava, 90 = dolu), sirka 1-10, opacne, pozadi, senzor / min / max, rada (ukazatel),
#   barvy_hudba "obal" / "vlastni", klavesy {zona: barva} + zaklad (vlastni barvy klaves),
#   reakce "" / "klavesa" / "vlnka" na stisk klaves, reakce_barva (hex nebo "duha"), reakce_doba (s).
# Stisky klaves (zona) dodava Engine.press() - ve vlakne LED z hooku Windows (klavesy_stisk.py),
# v nahledu simulovane.

import colorsys
import math
import random

import klavesnice_rozlozeni as R

FPS = 30
KEYS = R.KEYS
ZONES = [k[0] for k in KEYS]
CX = [k[2] + k[4] / 2 for k in KEYS]                    # stred klavesy (u)
CY = [k[3] + k[5] / 2 for k in KEYS]
X0, X1 = min(k[2] for k in KEYS), max(k[2] + k[4] for k in KEYS)
Y0, Y1 = min(k[3] for k in KEYS), max(k[3] + k[5] for k in KEYS)
MIDX, MIDY = (X0 + X1) / 2, (Y0 + Y1) / 2
INDEX = {z: i for i, z in enumerate(ZONES)}
SPACE = INDEX.get(41, 0)

DEFAULT_PALETTE = ["#ff0000", "#0060ff", "#00ff40", "#ffb000", "#b000ff", "#00e5ff", "#ff0080", "#ffffff"]

# typ: (nazev, skupina, parametry, (min, max) pocet barev, vychozi hodnoty)
EFFECTS = {
    "barva": ("jedna barva", "klidne", ("barvy",), (1, 1), {"barvy": ["#00a0ff"]}),
    "prechod": ("přechod přes klávesnici", "klidne", ("barvy", "duha", "smer"), (2, 8),
                {"barvy": ["#ff0040", "#0060ff"], "smer": 0}),
    "dychani": ("dýchání", "klidne", ("barvy", "rychlost"), (1, 8), {"barvy": ["#00a0ff", "#ff0080"]}),
    "vlastni": ("vlastní barvy kláves", "klidne", ("klavesy",), (0, 0), {"zaklad": "#202020", "klavesy": {}}),
    "vlna": ("vlna", "pohyb", ("barvy", "duha", "smer", "rychlost", "sirka"), (2, 8),
             {"duha": True, "smer": 0, "sirka": 6}),
    "kruh": ("kruhová vlna od středu", "pohyb", ("barvy", "duha", "rychlost", "sirka", "opacne"), (2, 8),
             {"duha": True, "sirka": 4}),
    "toceni": ("točení kolem středu", "pohyb", ("barvy", "duha", "rychlost", "sirka", "opacne"), (2, 8),
               {"duha": True, "sirka": 3}),
    "skener": ("skener tam a zpět", "pohyb", ("barvy", "pozadi", "smer", "rychlost", "sirka"), (1, 1),
               {"barvy": ["#ff0000"], "pozadi": "#100000", "smer": 0, "sirka": 3}),
    "stirani": ("stírání barev", "pohyb", ("barvy", "smer", "rychlost"), (2, 8),
                {"barvy": ["#ff0040", "#00a0ff", "#40ff00"], "smer": 0}),
    "dest": ("déšť (Matrix)", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 1),
             {"barvy": ["#00ff40"], "pozadi": "#000800", "sirka": 5}),
    "trpyt": ("třpyt", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 8),
              {"barvy": ["#ffffff", "#00a0ff"], "pozadi": "#000818", "sirka": 5}),
    "ohnostroj": ("ohňostroj", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 8),
                  {"barvy": ["#ff0040", "#ffb000", "#00a0ff", "#40ff00"], "pozadi": "#000000", "sirka": 5}),
    "plamen": ("plamen zespodu", "castice", ("barvy", "rychlost", "sirka"), (2, 4),
               {"barvy": ["#ff0000", "#ff6000", "#ffd000"], "sirka": 6}),
    "spektrum": ("spektrum hudby", "hudba", ("barvy", "barvy_hudba", "pozadi"), (2, 4),
                 {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "barvy_hudba": "vlastni", "pozadi": "#000000"}),
    "pulz": ("pulz do rytmu", "hudba", ("barvy", "barvy_hudba"), (1, 8),
             {"barvy": ["#ff0040", "#00a0ff"], "barvy_hudba": "obal"}),
    "vlna_uder": ("vlny od mezerníku na údery", "hudba", ("barvy", "barvy_hudba", "pozadi"), (1, 8),
                  {"barvy": ["#00a0ff", "#ff0080"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "teplota": ("barva podle senzoru", "senzor", ("barvy", "senzor"), (2, 8),
                {"barvy": ["#0060ff", "#00ff40", "#ffb000", "#ff0000"], "senzor": "CPU (Tctl/Tdie)",
                 "min": 40, "max": 90}),
    "ukazatel": ("ukazatel na řadě kláves", "senzor", ("barvy", "pozadi", "senzor", "rada"), (1, 8),
                 {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "pozadi": "#000818", "senzor": "CPU (Tctl/Tdie)",
                  "min": 40, "max": 90, "rada": "cisla"}),
}
GROUPS = [("klidne", "Klidné"), ("pohyb", "Pohyb"), ("castice", "Částice"), ("hudba", "Hudba"),
          ("senzor", "Senzor")]
STATIC = {"barva", "prechod", "vlastni"}               # bez animace (jen pri zmene / reakci na stisk)
DEFAULT_EFFECT = {"typ": "vlna", "rychlost": 5, "smer": 0, "sirka": 6, "duha": True, "opacne": False,
                  "barvy": DEFAULT_PALETTE[:3], "pozadi": "#000000", "reakce": "", "reakce_barva": "#ffffff",
                  "reakce_doba": 1.0}
DIRECTIONS = [(0, "→"), (45, "↘"), (90, "↓"), (135, "↙"), (180, "←"), (225, "↖"), (270, "↑"), (315, "↗")]
REACTIONS = [("", "bez reakce"), ("klavesa", "rozsvítit klávesu"), ("vlnka", "vlnka od klávesy")]
ROWS = {"cisla": [27 + i for i in range(10)] + [42, 43],          # 1 ... 0, -, =
        "f": [55 + i for i in range(12)]}                           # F1 ... F12
ROW_NAMES = [("cisla", "číselná řada"), ("f", "řada F1–F12")]
# skupiny klaves pro vyber v okne
KEY_GROUPS = [("vse", "vše", ZONES),
              ("wasd", "WASD", [23, 1, 19, 4]),
              ("sipky", "šipky", [76, 77, 78, 79]),
              ("f", "F1–F12", ROWS["f"]),
              ("cisla", "čísla", [27 + i for i in range(10)]),
              ("pismena", "písmena", list(range(1, 27))),
              ("num", "numerická", list(range(80, 97))),
              ("g", "G1–G5", [180, 181, 182, 183, 184]),
              ("horni", "logo a média", [210, 153, 155, 156, 157, 158])]


def info(typ):
    return EFFECTS.get(typ, EFFECTS["vlna"])


def get(eff, key):
    """Parametr efektu s vychozi hodnotou (z EFFECTS, pak DEFAULT_EFFECT)."""
    if key in eff:
        return eff[key]
    d = info(eff.get("typ"))[4]
    return d.get(key, DEFAULT_EFFECT.get(key))


def is_animated(eff):
    return eff.get("typ") not in STATIC or bool(eff.get("reakce"))


def hex_rgb(h):
    h = str(h).lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def color_count(eff):
    lo, hi = info(eff.get("typ"))[3]
    try:
        n = int(eff.get("pocet_barev", len(get(eff, "barvy") or [])))
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(hi, n)) if hi else 0


def palette(eff):
    """Barvy efektu jako hex (presne color_count, chybejici doplni DEFAULT_PALETTE)."""
    n = color_count(eff)
    cols = list(get(eff, "barvy") or [])[:n]
    for c in DEFAULT_PALETTE:
        if len(cols) >= n:
            break
        if c not in cols:
            cols.append(c)
    return cols[:n]


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def _add(a, b):
    return (min(255.0, a[0] + b[0]), min(255.0, a[1] + b[1]), min(255.0, a[2] + b[2]))


def _hsv(h, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, v)
    return (r * 255, g * 255, b * 255)


def _gradient(cols, p):
    if len(cols) == 1:
        return cols[0]
    p = max(0.0, min(1.0, p)) * (len(cols) - 1)
    i = min(int(p), len(cols) - 2)
    return _mix(cols[i], cols[i + 1], p - i)


def _cyclic(cols, p):
    k = len(cols)
    x = (p % 1.0) * k
    a = int(x) % k
    f = x - int(x)
    return _mix(cols[a], cols[(a + 1) % k], f * f * (3 - 2 * f))


def _proj(deg):
    """Poloha kazde klavesy ve smeru deg jako 0..1 (0 = kde smer zacina)."""
    a = math.radians(deg)
    dx, dy = math.cos(a), math.sin(a)
    v = [x * dx + y * dy for x, y in zip(CX, CY)]
    lo, hi = min(v), max(v)
    return [(p - lo) / (hi - lo or 1) for p in v]


_PROJ = {d: _proj(d) for d, _n in DIRECTIONS}
_DIST = [math.hypot(x - MIDX, (y - MIDY) * 1.0) for x, y in zip(CX, CY)]
_ANG = [math.atan2(y - MIDY, x - MIDX) / (2 * math.pi) for x, y in zip(CX, CY)]
_COLS = sorted({round(x) for x in CX})                  # sloupce pro dest
_COL_OF = [_COLS.index(round(x)) for x in CX]


def proj(eff):
    d = int(get(eff, "smer") or 0) % 360
    return _PROJ.get(d) or _proj(d)


class Engine:
    """Pocita snimky klavesnice. Drzi stav castic, stisku a vyhlazenych senzoru."""

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.clock = 0.0
        self.state = {}
        self.presses = []                       # [(index klavesy, cas stisku, barva duhy)]
        self.source = None                      # funkce vracejici nove stisknute zony (hook Windows)
        self._n_press = 0

    def press(self, zone):
        i = INDEX.get(zone)
        if i is not None:
            self._n_press += 1
            self.presses.append((i, self.clock, (self._n_press * 0.13) % 1.0))

    def reset(self):
        self.state.clear()

    # -------------------------------------------------------------- snimek
    def frame(self, eff, dt=1 / FPS, data=None, music=None):
        dt = max(0.0, min(0.25, dt))
        self.clock += dt
        if self.source is not None:
            for z in self.source():
                self.press(z)
        typ = eff.get("typ", "vlna")
        fn = getattr(self, "_" + typ, None) if typ in EFFECTS else None
        cols = fn(eff, self.clock, dt, data, music) if fn else [(0.0, 0.0, 0.0)] * len(KEYS)
        if eff.get("reakce"):
            cols = self._reaction(eff, cols)
        keep = self.clock - 4.0
        self.presses = [p for p in self.presses if p[1] > keep]
        return [(max(0.0, min(255.0, c[0])), max(0.0, min(255.0, c[1])), max(0.0, min(255.0, c[2])))
                for c in cols]

    def _speed(self, eff, k=1.0):
        try:
            return max(1, min(10, float(get(eff, "rychlost") or 5))) / 5.0 * k
        except (TypeError, ValueError):
            return k

    def _width(self, eff):
        try:
            return max(1, min(10, float(get(eff, "sirka") or 5)))
        except (TypeError, ValueError):
            return 5.0

    def _pal(self, eff):
        return [hex_rgb(c) for c in palette(eff)] or [(255, 255, 255)]

    def _music_pal(self, eff, music):
        if get(eff, "barvy_hudba") == "obal" and music and music.get("paleta"):
            return [hex_rgb(c) for c in music["paleta"]]
        return self._pal(eff)

    def _bg(self, eff):
        return hex_rgb(get(eff, "pozadi") or "#000000")

    # -------------------------------------------------------------- klidne
    def _barva(self, eff, t, dt, data, music):
        return [self._pal(eff)[0]] * len(KEYS)

    def _prechod(self, eff, t, dt, data, music):
        p = proj(eff)
        if get(eff, "duha"):
            return [_hsv(v * 0.85) for v in p]
        pal = self._pal(eff)
        return [_gradient(pal, v) for v in p]

    def _dychani(self, eff, t, dt, data, music):
        pal = self._pal(eff)
        period = 5.0 / self._speed(eff)
        n = int(t // period)
        f = (t % period) / period
        k = math.sin(math.pi * f) ** 2
        return [_scale(pal[n % len(pal)], k)] * len(KEYS)

    def _vlastni(self, eff, t, dt, data, music):
        base = hex_rgb(get(eff, "zaklad") or "#000000")
        keys = get(eff, "klavesy") or {}
        return [hex_rgb(keys[str(z)]) if str(z) in keys else base for z in ZONES]

    # -------------------------------------------------------------- pohyb
    def _wave_color(self, eff, p):
        if get(eff, "duha"):
            return _hsv(p)
        return _cyclic(self._pal(eff), p)

    def _vlna(self, eff, t, dt, data, music):
        w = self._width(eff) / 5.0                          # delka jedne vlny jako podil klavesnice
        s = t * self._speed(eff, 0.25)
        return [self._wave_color(eff, v / w - s) for v in proj(eff)]

    def _kruh(self, eff, t, dt, data, music):
        w = self._width(eff) * 2.0                          # delka vlny v u
        s = t * self._speed(eff, 0.35) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, d / w - s) for d in _DIST]

    def _toceni(self, eff, t, dt, data, music):
        twist = (self._width(eff) - 1) / 30.0               # spirala: posun podle vzdalenosti
        s = t * self._speed(eff, 0.2) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, a + d * twist - s) for a, d in zip(_ANG, _DIST)]

    def _skener(self, eff, t, dt, data, music):
        col, bg = self._pal(eff)[0], self._bg(eff)
        w = self._width(eff) / 25.0
        period = 2.4 / self._speed(eff)
        f = (t % (2 * period)) / period
        pos = f if f <= 1 else 2 - f                        # tam a zpet
        pos = -w + pos * (1 + 2 * w)
        out = []
        for v in proj(eff):
            k = max(0.0, 1 - abs(v - pos) / w)
            out.append(_mix(bg, col, k * k * (3 - 2 * k)))
        return out

    def _stirani(self, eff, t, dt, data, music):
        pal = self._pal(eff)
        dur = 1.0 / (0.15 * self._speed(eff))               # setreni jedne barvy (s)
        n = int(t // dur)
        f = (t % dur) / dur
        old, new = pal[n % len(pal)], pal[(n + 1) % len(pal)]
        edge = 0.08
        pos = -edge + f * (1 + 2 * edge)
        return [_mix(new, old, (v - pos) / edge + 0.5) for v in proj(eff)]

    # -------------------------------------------------------------- castice
    def _dest(self, eff, t, dt, data, music):
        col, bg = self._pal(eff)[0], self._bg(eff)
        head = _mix(col, (255, 255, 255), 0.6)
        drops = self.state.setdefault("dest", [])           # [sloupec, y, rychlost]
        dens = self._width(eff)
        sp = self._speed(eff)
        for c in range(len(_COLS)):
            if self.rng.random() < dens * 0.012 * sp * dt * FPS / 3:
                drops.append([c, Y0 - 0.5, (3.0 + self.rng.random() * 4.0) * sp])
        for d in drops:
            d[1] += d[2] * dt
        drops[:] = [d for d in drops if d[1] < Y1 + 4]
        out = []
        tail = 2.5
        for i in range(len(KEYS)):
            c, y = _COL_OF[i], CY[i]
            best, is_head = 0.0, False
            for d in drops:
                if d[0] != c:
                    continue
                dist = d[1] - y
                if -0.5 <= dist < 0.5:
                    best, is_head = 1.0, True
                elif 0.5 <= dist < tail:
                    best = max(best, (1 - (dist - 0.5) / (tail - 0.5)) ** 1.5)
            out.append(head if is_head else _mix(bg, col, best))
        return out

    def _trpyt(self, eff, t, dt, data, music):
        pal, bg = self._pal(eff), self._bg(eff)
        lv = self.state.setdefault("trpyt", [[0.0, pal[0]] for _ in KEYS])
        chance = self._width(eff) * 0.004 * self._speed(eff) * dt * FPS
        fade = dt * 2.5 * self._speed(eff)
        out = []
        for s in lv:
            if self.rng.random() < chance:
                s[0], s[1] = 1.0, self.rng.choice(pal)
            else:
                s[0] = max(0.0, s[0] - fade)
            out.append(_mix(bg, s[1], s[0] ** 1.5))
        return out

    def _ohnostroj(self, eff, t, dt, data, music):
        pal, bg = self._pal(eff), self._bg(eff)
        bursts = self.state.setdefault("ohnostroj", [])     # [x, y, cas, barva]
        sp = self._speed(eff)
        if self.rng.random() < self._width(eff) * 0.02 * sp * dt * FPS / 3:
            i = self.rng.randrange(len(KEYS))
            bursts.append([CX[i], CY[i], t, self.rng.choice(pal)])
        life = 1.6 / max(0.5, sp ** 0.5)
        bursts[:] = [b for b in bursts if t - b[2] < life]
        out = []
        for x, y in zip(CX, CY):
            c = bg
            for bx, by, bt, bc in bursts:
                age = (t - bt) / life
                r = age * 6.0
                d = abs(math.hypot(x - bx, (y - by) * 1.2) - r)
                k = max(0.0, 1 - d / 1.1) * (1 - age) ** 1.5
                if age < 0.12 and math.hypot(x - bx, y - by) < 0.7:
                    k = 1.0                                   # zablesk ve stredu
                c = _add(c, _scale(bc, k))
            out.append(c)
        return out

    def _plamen(self, eff, t, dt, data, music):
        pal = self._pal(eff)
        sp = self._speed(eff)
        hmax = 1.5 + self._width(eff) * 0.5                 # vyska plamenu (u)
        out = []
        for x, y in zip(CX, CY):
            n = (math.sin(x * 0.9 + t * 3.1 * sp) + math.sin(x * 2.3 - t * 4.7 * sp) * 0.6
                 + math.sin(x * 0.37 + t * 1.3 * sp) * 0.8) / 2.4
            h = hmax * (0.65 + 0.35 * n)
            fy = Y1 - y                                        # vyska od spodku
            k = max(0.0, 1 - fy / h)
            flick = 0.85 + 0.15 * math.sin(t * 11 * sp + x * 5.1 + y * 3.3)
            out.append(_scale(_gradient(pal, k), min(1.0, k * 1.6) * flick) if k > 0 else (0.0, 0.0, 0.0))
        return out

    # -------------------------------------------------------------- hudba
    def _spektrum(self, eff, t, dt, data, music):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        bands = (music or {}).get("bands") or []
        sm = self.state.setdefault("spektrum", [0.0] * 16)
        for b in range(16):
            v = bands[b] if b < len(bands) else 0.0
            sm[b] = v if v > sm[b] else sm[b] + (v - sm[b]) * min(1.0, dt * 6)
        out = []
        for x, y in zip(CX, CY):
            b = min(15, max(0, int((x - X0) / (X1 - X0) * 16)))
            lvl = (Y1 - y) / (Y1 - Y0)                       # 0 dole .. 1 nahore
            out.append(_gradient(pal, lvl) if lvl <= sm[b] * 1.05 else bg)
        return out

    def _beat(self, music):
        """(sila posledniho uderu 0..1 podle stari, cislo uderu)."""
        if not music:
            return 0.0, 0
        best = 0.0
        for age, strength, _n in music.get("beats", []):
            best = max(best, strength * math.exp(-age / 0.18))
        return best, int(music.get("beat_n", 0))

    def _pulz(self, eff, t, dt, data, music):
        pal = self._music_pal(eff, music)
        if not music:
            return [_scale(pal[0], 0.15)] * len(KEYS)
        flash, n = self._beat(music)
        col = pal[n % len(pal)]
        k = 0.15 + 0.45 * float(music.get("bass", 0)) + 0.4 * flash
        return [_scale(_mix(col, (255, 255, 255), flash * 0.25), min(1.0, k))] * len(KEYS)

    def _vlna_uder(self, eff, t, dt, data, music):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        rings = self.state.setdefault("vlna_uder", [])     # [cas, barva, sila]
        last = self.state.get("vlna_uder_n")
        if music:
            n = int(music.get("beat_n", 0))
            if last is not None and n != last:
                strength = max((s for a, s, _n in music.get("beats", []) if a < 0.2), default=0.8)
                rings.append([t, pal[n % len(pal)], strength])
            self.state["vlna_uder_n"] = n
        rings[:] = [r for r in rings if t - r[0] < 1.6]
        sx, sy = CX[SPACE], CY[SPACE]
        out = []
        for x, y in zip(CX, CY):
            c = bg
            d0 = math.hypot((x - sx) * 0.8, (y - sy) * 1.6)
            for rt, rc, rs in rings:
                age = t - rt
                d = abs(d0 - age * 14.0)
                k = max(0.0, 1 - d / 1.6) * (1 - age / 1.6) * rs
                c = _add(c, _scale(rc, k))
            out.append(c)
        return out

    # -------------------------------------------------------------- senzor
    def _sensor_frac(self, eff, dt, data):
        item = (data or {}).get(get(eff, "senzor") or "")
        v = item.get("value") if isinstance(item, dict) else None
        sm = self.state.get("senzor")
        if v is not None:
            sm = v if sm is None else sm + (v - sm) * min(1.0, dt / 2.0)
            self.state["senzor"] = sm
        if sm is None:
            return None
        lo, hi = float(get(eff, "min") or 0), float(get(eff, "max") or 100)
        return 0.0 if hi == lo else max(0.0, min(1.0, (sm - lo) / (hi - lo)))

    def _teplota(self, eff, t, dt, data, music):
        f = self._sensor_frac(eff, dt, data)
        pal = self._pal(eff)
        return [_gradient(pal, f if f is not None else 0.0)] * len(KEYS)

    def _ukazatel(self, eff, t, dt, data, music):
        f = self._sensor_frac(eff, dt, data)
        pal, bg = self._pal(eff), self._bg(eff)
        row = ROWS.get(get(eff, "rada"), ROWS["cisla"])
        out = [bg] * len(KEYS)
        if f is None:
            return out
        n = len(row)
        for j, z in enumerate(row):
            i = INDEX.get(z)
            if i is None:
                continue
            k = max(0.0, min(1.0, f * n - j))                # posledni klavesa jen castecne
            out[i] = _mix(bg, _gradient(pal, j / max(1, n - 1)), k)
        return out

    # -------------------------------------------------------------- reakce na stisk
    def _reaction(self, eff, cols):
        mode = eff.get("reakce")
        try:
            life = max(0.2, min(5.0, float(eff.get("reakce_doba", 1.0))))
        except (TypeError, ValueError):
            life = 1.0
        rc = eff.get("reakce_barva", "#ffffff")
        out = list(cols)
        for i, pt, hue in self.presses:
            age = self.clock - pt
            if age >= life:
                continue
            col = _hsv(hue) if rc == "duha" else hex_rgb(rc)
            fade = 1 - age / life
            if mode == "klavesa":
                out[i] = _mix(out[i], col, fade ** 0.7)
            else:                                            # vlnka od klavesy
                r = age * 9.0
                px, py = CX[i], CY[i]
                for j, (x, y) in enumerate(zip(CX, CY)):
                    d = abs(math.hypot(x - px, (y - py) * 1.3) - r)
                    k = max(0.0, 1 - d / 1.2) * fade
                    if j == i:
                        k = max(k, fade)
                    if k > 0:
                        out[j] = _mix(out[j], col, k)
        return out


def default_effect(typ):
    """Novy efekt daneho typu s vychozimi hodnotami (reakce zustava zvlast)."""
    e = {"typ": typ, "rychlost": 5}
    e.update({k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
              for k, v in info(typ)[4].items()})
    lo, hi = info(typ)[3]
    if hi:
        e["pocet_barev"] = max(lo, min(hi, len(e.get("barvy", DEFAULT_PALETTE[:lo]))))
    return e


def valid(eff):
    """Efekt klavesnice z nastaveni - neznamy typ (napr. starsi efekt ventilatoru) = vychozi vlna."""
    if not isinstance(eff, dict) or eff.get("typ") not in EFFECTS:
        return dict(DEFAULT_EFFECT)
    return eff


def engine_for(owner):
    """Engine klavesnice ulozeny u jineho objektu (led_efekty.Engine) - vlakno LED i nahled."""
    e = getattr(owner, "kb", None)
    if e is None:
        e = Engine()
        owner.kb = e
    return e


if __name__ == "__main__":
    import time
    eng = Engine(1)
    demo = {"bands": [0.5] * 16, "beats": [(0.05, 1.0, 3)], "beat_n": 3, "bass": 0.7, "paleta": ["#ff0000"]}
    for typ in EFFECTS:
        e = dict(default_effect(typ), reakce="vlnka")
        eng.press(1)
        t = time.perf_counter()
        for _ in range(30):
            c = eng.frame(e, 1 / 30, {"CPU (Tctl/Tdie)": {"value": 70}}, demo)
        assert len(c) == len(KEYS)
        print(f"{typ:12s} {(time.perf_counter() - t) / 30 * 1000:5.2f} ms/snímek")
