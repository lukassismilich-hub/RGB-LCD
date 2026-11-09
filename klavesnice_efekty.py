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
# Reakce na stisk klaves je nadrazeny efekt pro celou klavesnici (config["led"]["reakce_klavesnice"] =
#   REACTION_DEFAULT: "zapnuto", "rezim" klavesa / vlnka, "barva" hex nebo "duha", "doba" s) - kresli ji
#   led._kb_compose pres efekt, casti, predvolbu i hudbu (Engine.reaction); drive byla u kazdeho efektu
#   ("reakce", "reakce_barva", "reakce_doba" - prevede migrate_reaction).
# Stisky klaves (zona) dodava Engine.press() - ve vlakne LED z hooku Windows (klavesy_stisk.py),
# v nahledu simulovane.

import colorsys
import math
import random

import klavesnice_rozlozeni as R
import led_efekty as fx

FPS = 30
KEYS = R.KEYS
ZONES = [k[0] for k in KEYS]
INDEX = {z: i for i, z in enumerate(ZONES)}

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
    "spektrum": ("spektrum hudby", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost", "spicka"), (2, 4),
                 {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "barvy_hudba": "vlastni", "pozadi": "#000000"}),
    "spektrum_stred": ("spektrum od středu", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost", "spicka"),
                       (2, 4), {"barvy": ["#00a0ff", "#b000ff", "#ff0080"], "barvy_hudba": "vlastni",
                                "pozadi": "#000000"}),
    "pasma_rady": ("pásma po řadách", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost", "spicka"), (2, 8),
                   {"barvy": ["#ff0000", "#ffb000", "#00ff40", "#00a0ff", "#b000ff"], "barvy_hudba": "vlastni",
                    "pozadi": "#000000"}),
    "hlasitost": ("ukazatel hlasitosti", "hudba", ("barvy", "pozadi", "citlivost", "spicka", "opacne"), (2, 4),
                  {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "pozadi": "#000000"}),
    "mozaika": ("mozaika pásem", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost"), (2, 8),
                {"barvy": ["#ff0040", "#ffb000", "#00ff40", "#00a0ff"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "kruh_basy": ("pulzující kruh z basů", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost"), (1, 8),
                  {"barvy": ["#ffffff", "#ff0080", "#0060ff"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "plamen_basy": ("plamen z basů", "hudba", ("barvy", "citlivost"), (2, 4),
                    {"barvy": ["#ff0000", "#ff6000", "#ffd000"]}),
    "pulz": ("pulz do rytmu", "hudba", ("barvy", "barvy_hudba", "citlivost"), (1, 8),
             {"barvy": ["#ff0040", "#00a0ff"], "barvy_hudba": "obal"}),
    "vlna_uder": ("vlny od mezerníku na údery", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost"), (1, 8),
                  {"barvy": ["#00a0ff", "#ff0080"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "prebarveni": ("přebarvení na údery", "hudba", ("barvy", "barvy_hudba", "smer", "rychlost", "citlivost"),
                   (2, 8), {"barvy": ["#ff0040", "#00a0ff", "#40ff00", "#ffb000"], "barvy_hudba": "obal",
                            "smer": 0}),
    "jiskry": ("jiskry do rytmu", "hudba", ("barvy", "barvy_hudba", "pozadi", "sirka", "citlivost"), (1, 8),
               {"barvy": ["#ffffff", "#00a0ff", "#ff0080"], "barvy_hudba": "obal", "pozadi": "#000000", "sirka": 5}),
    "dest_hudba": ("déšť do rytmu", "hudba", ("barvy", "barvy_hudba", "pozadi", "sirka", "citlivost"), (1, 8),
                   {"barvy": ["#00ff40"], "barvy_hudba": "vlastni", "pozadi": "#000000", "sirka": 5}),
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
                  "barvy": DEFAULT_PALETTE[:3], "pozadi": "#000000", "citlivost": 5, "citlivost_vlastni": False,
                  "spicka": True}
DIRECTIONS = [(0, "→"), (45, "↘"), (90, "↓"), (135, "↙"), (180, "←"), (225, "↖"), (270, "↑"), (315, "↗")]
REACTIONS = [("klavesa", "rozsvítit klávesu"), ("vlnka", "vlnka od klávesy")]
REACTION_DEFAULT = {"zapnuto": False, "rezim": "vlnka", "barva": "#ffffff", "doba": 1.0}
OLD_REACTION_KEYS = ("reakce", "reakce_barva", "reakce_doba")


def reaction_settings(lcfg):
    """Nastaveni reakce na stisk s vychozimi hodnotami (cteni)."""
    v = (lcfg or {}).get("reakce_klavesnice")
    v = v if isinstance(v, dict) else {}
    return {k: v.get(k, d) for k, d in REACTION_DEFAULT.items()}


def migrate_reaction(lc):
    """Stara reakce u efektu -> nadrazena (prvni efekt s reakci: zaklad M1 / stary zaklad, pak casti);
    klice reakce z efektu smaze. Vrati True, kdyz neco prevedl."""
    effs = []

    def collect(src):
        if not isinstance(src, dict):
            return
        effs.append(src.get("efekt_klavesnice"))
        for lay in src.get("vrstvy_klavesnice") or []:
            if isinstance(lay, dict):
                effs.append(lay.get("efekt"))
    collect(lc)
    profs = lc.get("klavesnice_m")
    for m in ("1", "2", "3"):
        collect((profs or {}).get(m) if isinstance(profs, dict) else None)
    for p in lc.get("predvolby") or []:
        if isinstance(p, dict):
            collect(p.get("nastaveni"))
    effs = [e for e in effs if isinstance(e, dict)]
    found = next((e for e in effs if e.get("reakce")), None)
    changed = False
    if "reakce_klavesnice" not in lc:
        lc["reakce_klavesnice"] = dict(REACTION_DEFAULT)
        if found is not None:
            lc["reakce_klavesnice"].update(zapnuto=True, rezim=found.get("reakce") if found.get("reakce") in
                                           ("klavesa", "vlnka") else "vlnka",
                                           barva=found.get("reakce_barva", "#ffffff"),
                                           doba=found.get("reakce_doba", 1.0))
        changed = True
    for e in effs:
        for k in OLD_REACTION_KEYS:
            if k in e:
                del e[k]
                changed = True
    return changed
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
    return eff.get("typ") not in STATIC


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


METER_FALL = 3.5            # jak rychle padaji ukazatele hudby (cela vyska za 0,3 s)
PEAK_HOLD_S = 0.5           # spicka chvili drzi
PEAK_FALL = 0.8


class Levels:
    """Urovne hudby 0..1 pro efekty klavesnice ze surovych dB (hudba.Analyzer: bands_db, db).
    Analyza pro ventilatory ma u kazdeho pasma vlastni automaticke zesileni, takze je kazde pasmo
    skoro porad u sveho maxima a spektrum svitilo naplno. Tady ma spektrum spolecnou spicku vsech
    pasem (tichsi pasma jsou nizko) a spodek kazdeho pasma je jeho dolni obalka - ukazatel jde od
    nuly, jen kdyz pasmo opravdu zesili. Citlivost 1-10 meni gamu stejne jako u ventilatoru
    (led_efekty.music_gamma)."""
    PEAK_FALL_DB = 3.0          # dB/s - spicka pomalu klesa
    FLOOR_UP_S = 2.0            # spodek pasma (prumer posunuty dolu): roste pomaleji ...
    FLOOR_DOWN_S = 1.5          # ... nez klesa
    RANGE_DB = 30.0             # nejvys tolik dB pod spickou = nula
    MIN_SPAN_DB = 8.0           # nejmensi rozsah (sum v tichu se neroztahne na plnou vysku)
    TILT_DB = 0.8               # dB na pasmo navic smerem k vyskam (hudba ma ve vyskach mene energie) - odhad
    SILENCE_DB = -62.0          # pod tim ticho (jako hudba.Analyzer.FLOOR_DB)
    SOFT_DB = 6.0               # basy / stredy / vysky / hlasitost: spodek niz, at neskacou jen mezi 0 a 1

    def __init__(self):
        self.peak, self.floor = {}, {}

    def _track(self, k, db, dt):
        pk = self.peak.get(k)
        pk = db if pk is None else max(db, pk - self.PEAK_FALL_DB * dt)
        fl = self.floor.get(k)
        if fl is None:
            fl = db - 6.0
        else:
            fl += (db - fl) * min(1.0, dt / (self.FLOOR_DOWN_S if db < fl else self.FLOOR_UP_S))
        self.peak[k], self.floor[k] = pk, fl
        return pk, fl

    def _map(self, db, top, fl, gamma):
        top = max(top, self.SILENCE_DB + self.MIN_SPAN_DB)
        bottom = min(max(fl, top - self.RANGE_DB, self.SILENCE_DB), top - self.MIN_SPAN_DB)
        return max(0.0, min(1.0, (db - bottom) / (top - bottom))) ** gamma

    def update(self, music, dt, sens=5.0):
        gamma = fx.music_gamma(sens)
        bdb = music.get("bands_db")
        if not bdb:                           # starsi analyza / simulovana hudba v nahledu: 0..1 -> dB
            bdb = [(float(v) - 1.0) * 30.0 for v in (music.get("bands") or [0.0] * 16)]
        bdb = [float(db) + self.TILT_DB * i for i, db in enumerate(bdb)]
        tr = [self._track(f"b{i}", db, dt) for i, db in enumerate(bdb)]
        g = max((pk for pk, _fl in tr), default=0.0)
        # vrchol pasma = napul mezi jeho spickou a spolecnou spickou: tvar spektra zustane videt
        out = {"bands": [self._map(db, pk + 0.5 * (g - pk), fl, gamma) for db, (pk, fl) in zip(bdb, tr)]}
        raw = music.get("db")
        if not raw:                           # simulovana hudba: hodnoty 0..1 uz jsou pripravene
            out.update({k: max(0.0, min(1.0, float(music.get(k, 0.0)))) ** gamma
                        for k in ("bass", "mid", "high", "level")})
            return out
        for k in ("bass", "mid", "high", "level"):
            db = float(raw.get(k, -120.0))
            pk, fl = self._track(k, db, dt)
            out[k] = self._map(db, pk, fl - self.SOFT_DB, gamma)
        return out


class Geo:
    """Geometrie klaves, pro ktere se efekt pocita - cela klavesnice nebo jen jeji cast (vrstva):
    smer, stred, sloupce i mezernik se berou jen z techto klaves, efekt tak vyplni celou cast."""

    def __init__(self, zones=None):
        sel = None if zones is None else set(zones)
        keys = [k for k in KEYS if sel is None or k[0] in sel]
        self.n = len(keys)
        self.zones = [k[0] for k in keys]
        self.index = {z: i for i, z in enumerate(self.zones)}
        self.cx = [k[2] + k[4] / 2 for k in keys]
        self.cy = [k[3] + k[5] / 2 for k in keys]
        self.x0 = min((k[2] for k in keys), default=0.0)
        self.x1 = max((k[2] + k[4] for k in keys), default=1.0)
        self.y0 = min((k[3] for k in keys), default=0.0)
        self.y1 = max((k[3] + k[5] for k in keys), default=1.0)
        mx, my = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        self.dist = [math.hypot(x - mx, y - my) for x, y in zip(self.cx, self.cy)]
        self.ang = [math.atan2(y - my, x - mx) / (2 * math.pi) for x, y in zip(self.cx, self.cy)]
        hh, ww = (self.y1 - self.y0) or 1.0, (self.x1 - self.x0) or 1.0
        self.mx = mx
        self.ylo = [(self.y1 - k[3] - k[5]) / hh for k in keys]       # spodni / horni hrana 0 (dole) .. 1
        self.yhi = [(self.y1 - k[3]) / hh for k in keys]
        self.xlo = [(k[2] - self.x0) / ww for k in keys]              # leva / prava hrana 0 .. 1
        self.xhi = [(k[2] + k[4] - self.x0) / ww for k in keys]
        rows = []                                                     # rady podle stredu (vysoke klavesy
        for y in sorted(set(self.cy)):                                # se pridaji k blizsi rade)
            if rows and y - rows[-1][-1] < 0.6:
                rows[-1].append(y)
            else:
                rows.append([y])
        self.nrows = max(1, len(rows))
        top = {y: r for r, ys in enumerate(rows) for y in ys}
        self.row_of = [self.nrows - 1 - top[y] for y in self.cy]      # 0 = dolni rada
        self.cols = sorted({round(x) for x in self.cx})             # sloupce pro dest
        self.col_of = [self.cols.index(round(x)) for x in self.cx]
        # vlny na udery jdou od mezerniku, v casti bez nej od klavesy dole uprostred
        self.space = self.index.get(41, min(range(self.n), default=0,
                                            key=lambda i: abs(self.cx[i] - mx) + abs(self.cy[i] - self.y1)))
        self._proj = {}

    def proj(self, eff):
        """Poloha kazde klavesy ve smeru efektu jako 0..1 (0 = kde smer zacina)."""
        d = int(get(eff, "smer") or 0) % 360
        if d not in self._proj:
            a = math.radians(d)
            v = [x * math.cos(a) + y * math.sin(a) for x, y in zip(self.cx, self.cy)]
            lo, hi = min(v, default=0.0), max(v, default=1.0)
            self._proj[d] = [(p - lo) / (hi - lo or 1) for p in v]
        return self._proj[d]


_GEOS = {}


def geo(zones=None):
    key = None if zones is None else tuple(sorted(zones))
    if key not in _GEOS:
        _GEOS[key] = Geo(key)
    return _GEOS[key]


def part_zones(lay):
    """Zony casti klavesnice (vrstvy) - jen existujici klavesy, serazene."""
    out = set()
    for z in (lay or {}).get("klavesy") or []:
        try:
            if int(z) in INDEX:
                out.add(int(z))
        except (TypeError, ValueError):
            pass
    return tuple(sorted(out))


class Engine:
    """Pocita snimky klavesnice. Drzi stav castic, stisku a vyhlazenych senzoru."""

    def __init__(self, seed=None, zones=None):
        self.rng = random.Random(seed)
        self.g = geo(zones)                     # klavesy, pro ktere se efekt pocita (None = cela klavesnice)
        self.clock = 0.0
        self.state = {}
        self.presses = []                       # [(index klavesy, cas stisku rclock, barva duhy)]
        self.rclock = 0.0                       # hodiny reakce na stisk (bezi i bez frame - jedna barva)
        self.source = None                      # funkce vracejici nove stisknute zony (hook Windows)
        self.parts = {}                         # enginy casti klavesnice (vrstvy) - vlastni stav efektu
        self._n_press = 0

    def press(self, zone):
        i = self.g.index.get(zone)
        if i is not None:
            self._n_press += 1
            self.presses.append((i, self.rclock, (self._n_press * 0.13) % 1.0))
            del self.presses[:-64]

    def reaction(self, rc, cols, dt=1 / FPS):
        """Nadrazena reakce na stisk (rc = reaction_settings) pres barvy cols (poradi KEYS)."""
        self.rclock += max(0.0, min(0.25, dt))
        self.poll()
        life = self._life(rc)
        self.presses = [p for p in self.presses if self.rclock - p[1] < life]
        if not self.presses:
            return cols
        return self._reaction({"reakce": rc.get("rezim"), "reakce_barva": rc.get("barva"),
                               "reakce_doba": life}, cols)

    def reacting(self, rc):
        """Dohasina jeste nejaky stisk (vlakno LED pak kresli dalsi snimky)?"""
        return bool(rc.get("zapnuto")) and any(self.rclock - p[1] < self._life(rc) for p in self.presses)

    @staticmethod
    def _life(rc):
        try:
            return max(0.2, min(5.0, float(rc.get("doba", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def poll(self):
        """Nove stisky z hooku Windows (ve frame() se vola samo)."""
        if self.source is not None:
            for z in self.source():
                self.press(z)

    def layers(self, layers, cols, dt=1 / FPS, data=None, music=None):
        """Efekty na castech klavesnice pres zakladni barvy cols (poradi KEYS): kazda vrstva
        {"klavesy": [zony], "efekt": {...}} se pocita jen v ramci svych klaves (vlastni geometrie)
        a prekryje predchozi; vrstvy jsou uz vybrane (led.kb_layers). Stav efektu drzi engine casti."""
        out = list(cols)
        alive = set()
        for n, lay in enumerate(layers):
            zones = part_zones(lay)
            if not zones:
                continue
            eff = valid(lay.get("efekt"))
            key = (n, zones, eff.get("typ"))
            e = self.parts.get(key)
            if e is None:
                e = self.parts[key] = Engine(zones=zones)
            alive.add(key)
            for z, c in zip(e.g.zones, e.frame(eff, dt, data, music)):
                out[INDEX[z]] = c
        for key in [k for k in self.parts if k not in alive]:
            del self.parts[key]
        return out

    def reset(self):
        self.state.clear()

    # -------------------------------------------------------------- snimek
    def frame(self, eff, dt=1 / FPS, data=None, music=None):
        dt = max(0.0, min(0.25, dt))
        self.clock += dt
        self.poll()
        typ = eff.get("typ", "vlna")
        fn = getattr(self, "_" + typ, None) if typ in EFFECTS else None
        cols = fn(eff, self.clock, dt, data, music) if fn else [(0.0, 0.0, 0.0)] * self.g.n
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
        """Barvy hudby jako u ventilatoru (z obalu / vlastni paleta vizualizeru - hudba.music_palette),
        pri dropu posunute o jednu jako ve vizualizeru ventilatoru (led_efekty.Engine.music);
        "barvy_hudba" "vlastni" = barvy efektu."""
        if get(eff, "barvy_hudba") == "obal" and music and music.get("paleta"):
            cols = [hex_rgb(c) for c in music["paleta"]]
            d = int(music.get("drop_n", 0)) % len(cols)
            return cols[d:] + cols[:d]
        return self._pal(eff)

    def _bg(self, eff):
        return hex_rgb(get(eff, "pozadi") or "#000000")

    # -------------------------------------------------------------- klidne
    def _barva(self, eff, t, dt, data, music):
        return [self._pal(eff)[0]] * self.g.n

    def _prechod(self, eff, t, dt, data, music):
        p = self.g.proj(eff)
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
        return [_scale(pal[n % len(pal)], k)] * self.g.n

    def _vlastni(self, eff, t, dt, data, music):
        base = hex_rgb(get(eff, "zaklad") or "#000000")
        keys = get(eff, "klavesy") or {}
        return [hex_rgb(keys[str(z)]) if str(z) in keys else base for z in self.g.zones]

    # -------------------------------------------------------------- pohyb
    def _wave_color(self, eff, p):
        if get(eff, "duha"):
            return _hsv(p)
        return _cyclic(self._pal(eff), p)

    def _vlna(self, eff, t, dt, data, music):
        w = self._width(eff) / 5.0                          # delka jedne vlny jako podil klavesnice
        s = t * self._speed(eff, 0.25)
        return [self._wave_color(eff, v / w - s) for v in self.g.proj(eff)]

    def _kruh(self, eff, t, dt, data, music):
        w = self._width(eff) * 2.0                          # delka vlny v u
        s = t * self._speed(eff, 0.35) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, d / w - s) for d in self.g.dist]

    def _toceni(self, eff, t, dt, data, music):
        twist = (self._width(eff) - 1) / 30.0               # spirala: posun podle vzdalenosti
        s = t * self._speed(eff, 0.2) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, a + d * twist - s) for a, d in zip(self.g.ang, self.g.dist)]

    def _skener(self, eff, t, dt, data, music):
        col, bg = self._pal(eff)[0], self._bg(eff)
        w = self._width(eff) / 25.0
        period = 2.4 / self._speed(eff)
        f = (t % (2 * period)) / period
        pos = f if f <= 1 else 2 - f                        # tam a zpet
        pos = -w + pos * (1 + 2 * w)
        out = []
        for v in self.g.proj(eff):
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
        return [_mix(new, old, (v - pos) / edge + 0.5) for v in self.g.proj(eff)]

    # -------------------------------------------------------------- castice
    def _dest(self, eff, t, dt, data, music):
        col, bg = self._pal(eff)[0], self._bg(eff)
        head = _mix(col, (255, 255, 255), 0.6)
        drops = self.state.setdefault("dest", [])           # [sloupec, y, rychlost]
        dens = self._width(eff)
        sp = self._speed(eff)
        for c in range(len(self.g.cols)):
            if self.rng.random() < dens * 0.012 * sp * dt * FPS / 3:
                drops.append([c, self.g.y0 - 0.5, (3.0 + self.rng.random() * 4.0) * sp])
        for d in drops:
            d[1] += d[2] * dt
        drops[:] = [d for d in drops if d[1] < self.g.y1 + 4]
        out = []
        tail = 2.5
        for i in range(self.g.n):
            c, y = self.g.col_of[i], self.g.cy[i]
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
        lv = self.state.setdefault("trpyt", [[0.0, pal[0]] for _ in range(self.g.n)])
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
            i = self.rng.randrange(self.g.n)
            bursts.append([self.g.cx[i], self.g.cy[i], t, self.rng.choice(pal)])
        life = 1.6 / max(0.5, sp ** 0.5)
        bursts[:] = [b for b in bursts if t - b[2] < life]
        out = []
        for x, y in zip(self.g.cx, self.g.cy):
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
        for x, y in zip(self.g.cx, self.g.cy):
            n = (math.sin(x * 0.9 + t * 3.1 * sp) + math.sin(x * 2.3 - t * 4.7 * sp) * 0.6
                 + math.sin(x * 0.37 + t * 1.3 * sp) * 0.8) / 2.4
            h = hmax * (0.65 + 0.35 * n)
            fy = self.g.y1 - y                                        # vyska od spodku
            k = max(0.0, 1 - fy / h)
            flick = 0.85 + 0.15 * math.sin(t * 11 * sp + x * 5.1 + y * 3.3)
            out.append(_scale(_gradient(pal, k), min(1.0, k * 1.6) * flick) if k > 0 else (0.0, 0.0, 0.0))
        return out

    # -------------------------------------------------------------- hudba
    def _sens(self, eff, music=None):
        """Citlivost na hudbu 1-10: vlastni efektu, jinak jako ventilatory (music["citlivost"])."""
        v = get(eff, "citlivost") if get(eff, "citlivost_vlastni") else (music or {}).get("citlivost", 5)
        try:
            return max(1.0, min(10.0, float(v or 5)))
        except (TypeError, ValueError):
            return 5.0

    def _lv(self, eff, music, dt):
        """Urovne hudby 0..1 pro tento snimek (Levels, citlivost efektu), None = bez hudby."""
        if not music:
            return None
        c = self.state.get("_lv_c")
        if c and c[0] == self.clock:
            return c[1]
        lv = self.state.get("_lv")
        if lv is None:
            lv = self.state["_lv"] = Levels()
        out = lv.update(music, dt, self._sens(eff, music))
        self.state["_lv_c"] = (self.clock, out)
        return out

    def _meter(self, key, vals, dt):
        """Vyhlazene hodnoty ukazatelu (nahoru hned, dolu padaji) a drzene spicky."""
        st = self.state.get(key)
        if st is None or len(st[0]) != len(vals):
            st = self.state[key] = ([0.0] * len(vals), [0.0] * len(vals), [0.0] * len(vals))
        v, pk, pt = st
        for i, x in enumerate(vals):
            v[i] = x if x > v[i] else max(x, v[i] - METER_FALL * dt)
            if v[i] >= pk[i]:
                pk[i], pt[i] = v[i], self.clock
            elif self.clock - pt[i] > PEAK_HOLD_S:
                pk[i] = max(v[i], pk[i] - PEAK_FALL * dt)
        return v, pk

    def _bar_key(self, eff, col, bg, v, pk, lo, hi):
        """Klavesa ukazatele mezi lo..hi (0..1): plna pod v, castecne na hrane, spicka nad."""
        k = max(0.0, min(1.0, (v - lo) / ((hi - lo) or 1)))
        c = _mix(bg, col, k)
        if get(eff, "spicka") and pk > 0.06 and lo <= pk < hi and pk > v + 0.02:
            c = _mix(col, (255, 255, 255), 0.35)
        return c

    def _spektrum(self, eff, t, dt, data, music, center=False):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        v, pk = self._meter("spektrum", (lv["bands"] if lv else [0.0] * 16), dt)
        g = self.g
        half = max(g.mx - g.x0, g.x1 - g.mx) or 1.0
        out = []
        for i in range(g.n):
            if center:                                    # basy uprostred, vysky na krajich
                b = int(abs(g.cx[i] - g.mx) / half * 16)
            else:
                b = int((g.cx[i] - g.x0) / ((g.x1 - g.x0) or 1) * 16)
            b = min(15, max(0, b))
            out.append(self._bar_key(eff, _gradient(pal, (g.ylo[i] + g.yhi[i]) / 2), bg, v[b], pk[b],
                                     g.ylo[i], g.yhi[i]))
        return out

    def _spektrum_stred(self, eff, t, dt, data, music):
        return self._spektrum(eff, t, dt, data, music, center=True)

    def _pasma_rady(self, eff, t, dt, data, music):
        """Kazda rada klaves = cast spektra (dole basy, nahore vysky), sviti zleva podle urovne."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        g = self.g
        nr = g.nrows
        bands = lv["bands"] if lv else [0.0] * 16
        vals = []
        for r in range(nr):
            a = r * 16 // nr
            vals.append(max(bands[a:max(a + 1, (r + 1) * 16 // nr)]))
        v, pk = self._meter("pasma_rady", vals, dt)
        return [self._bar_key(eff, _gradient(pal, g.row_of[i] / max(1, nr - 1)), bg, v[g.row_of[i]],
                              pk[g.row_of[i]], g.xlo[i], g.xhi[i]) for i in range(g.n)]

    def _hlasitost(self, eff, t, dt, data, music):
        pal, bg = self._pal(eff), self._bg(eff)
        lv = self._lv(eff, music, dt)
        v, pk = self._meter("hlasitost", [lv["level"] ** 1.5 if lv else 0.0], dt)   # hlasitost je skoro porad vysoko
        g = self.g
        out = []
        for i in range(g.n):
            lo, hi = g.xlo[i], g.xhi[i]
            if get(eff, "opacne"):                            # od stredu do stran
                lo, hi = sorted((abs(lo - 0.5) * 2, abs(hi - 0.5) * 2))
                if g.xlo[i] < 0.5 < g.xhi[i]:
                    lo = 0.0
            out.append(self._bar_key(eff, _gradient(pal, (lo + hi) / 2), bg, v[0], pk[0], lo, hi))
        return out

    def _mozaika(self, eff, t, dt, data, music):
        """Kazda klavesa patri k jednomu pasmu (pevne nahodne) a sviti podle jeho urovne."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        v, _pk = self._meter("mozaika", (lv["bands"] if lv else [0.0] * 16), dt)
        own = self.state.get("mozaika_pasma")
        if own is None or len(own) != self.g.n:
            r = random.Random(7)
            own = self.state["mozaika_pasma"] = [r.randrange(16) for _ in range(self.g.n)]
        return [_mix(bg, _gradient(pal, b / 15), min(1.0, v[b] * 1.3)) for b in own]

    def _kruh_basy(self, eff, t, dt, data, music):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        v, _pk = self._meter("kruh_basy", [lv["bass"] if lv else 0.0, lv["high"] if lv else 0.0], dt)
        rmax = max(self.g.dist, default=1.0) or 1.0
        r = 0.6 + v[0] * rmax
        out = []
        for d in self.g.dist:
            k = max(0.0, min(1.0, (r - d) / 1.2))
            c = _mix(bg, _gradient(pal, d / rmax), k)
            if v[1] > 0.4 and 0 < r - d < 1.2:              # vysky = svetly okraj kruhu
                c = _mix(c, (255, 255, 255), (v[1] - 0.4) * 0.8)
            out.append(c)
        return out

    def _plamen_basy(self, eff, t, dt, data, music):
        pal = self._pal(eff)
        lv = self._lv(eff, music, dt)
        v, _pk = self._meter("plamen_basy", [lv["bass"] if lv else 0.0, lv["level"] if lv else 0.0], dt)
        hmax = 0.6 + (v[0] * 0.7 + v[1] * 0.3) * (self.g.y1 - self.g.y0) * 1.1      # vyska plamene (u)
        out = []
        for x, y in zip(self.g.cx, self.g.cy):
            n = (math.sin(x * 0.9 + t * 3.1) + math.sin(x * 2.3 - t * 4.7) * 0.6
                 + math.sin(x * 0.37 + t * 1.3) * 0.8) / 2.4
            k = max(0.0, 1 - (self.g.y1 - y) / (hmax * (0.7 + 0.3 * n)))
            flick = 0.85 + 0.15 * math.sin(t * 11 + x * 5.1 + y * 3.3)
            out.append(_scale(_gradient(pal, k), min(1.0, k * 1.6) * flick) if k > 0 else (0.0, 0.0, 0.0))
        return out

    def _hit(self, eff, music, key):
        """Sila noveho uderu 0..1, jinak 0. Udery hleda analyza s citlivosti ventilatoru; nizsi vlastni
        citlivost efektu ignoruje udery pod svym prahem - sila uderu k = (pomer - prah) / prah + 0,5
        (hudba.Analyzer), takze prah c' odpovida k >= (c' - c) / c + 0,5. Vyssi vlastni citlivost
        udery navic nepridava."""
        if not music:
            return 0.0
        n = int(music.get("beat_n", 0))
        last = self.state.get(key)
        self.state[key] = n
        if last is None or n == last:
            return 0.0
        st = max((s for a, s, _n in music.get("beats", []) if a < 0.25), default=0.8)
        c = fx.beat_ratio(music.get("citlivost", 5))
        need = (fx.beat_ratio(self._sens(eff, music)) - c) / c + 0.5
        return st if st >= need else 0.0

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
            return [_scale(pal[0], 0.15)] * self.g.n
        flash, n = self._beat(music)
        col = pal[n % len(pal)]
        k = 0.15 + 0.45 * self._lv(eff, music, dt)["bass"] + 0.4 * flash
        return [_scale(_mix(col, (255, 255, 255), flash * 0.25), min(1.0, k))] * self.g.n

    def _vlna_uder(self, eff, t, dt, data, music):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        rings = self.state.setdefault("vlna_uder", [])     # [cas, barva, sila]
        hit = self._hit(eff, music, "vlna_uder_n")
        if hit:
            rings.append([t, pal[int(music.get("beat_n", 0)) % len(pal)], hit])
        rings[:] = [r for r in rings if t - r[0] < 1.6]
        sx, sy = self.g.cx[self.g.space], self.g.cy[self.g.space]
        out = []
        for x, y in zip(self.g.cx, self.g.cy):
            c = bg
            d0 = math.hypot((x - sx) * 0.8, (y - sy) * 1.6)
            for rt, rc, rs in rings:
                age = t - rt
                d = abs(d0 - age * 14.0)
                k = max(0.0, 1 - d / 1.6) * (1 - age / 1.6) * rs
                c = _add(c, _scale(rc, k))
            out.append(c)
        return out

    def _prebarveni(self, eff, t, dt, data, music):
        """Kazdy uder prejede klavesnici dalsi barvou palety ve zvolenem smeru."""
        pal = self._music_pal(eff, music)
        st = self.state.setdefault("prebarveni", {"old": pal[0], "new": pal[0], "t": -9.0, "i": 0, "k": 0.0})
        dur = 0.35 / self._speed(eff)                     # jak dlouho barva prejizdi klavesnici
        hit = self._hit(eff, music, "prebarveni_n")
        if hit:
            st["i"] += 1
            k = max(0.0, min(1.0, (t - st["t"]) / dur))   # predchozi prejezd jeste nedobehl - prolnout
            st["old"] = _mix(st["old"], st["new"], k)
            st["new"], st["t"], st["k"] = pal[st["i"] % len(pal)], t, hit
        front = (t - st["t"]) / dur * 1.25
        flash = st["k"] * math.exp(-(t - st["t"]) / 0.25)
        return [_scale(_mix(st["old"], st["new"], (front - p) * 4), 0.55 + 0.45 * flash) for p in self.g.proj(eff)]

    def _jiskry(self, eff, t, dt, data, music):
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self.state.setdefault("jiskry", [[0.0, pal[0]] for _ in range(self.g.n)])
        amount = self._width(eff) / 5.0
        hit = self._hit(eff, music, "jiskry_n")
        if hit:
            col = pal[int(music.get("beat_n", 0)) % len(pal)]
            for i in self.rng.sample(range(self.g.n), min(self.g.n, int(self.g.n * (0.08 + 0.17 * hit) * amount))):
                lv[i][0], lv[i][1] = 1.0, col
        levels = self._lv(eff, music, dt)
        if levels:                                        # vysky = drobny trpyt mezi udery
            for _ in range(int(levels["high"] ** 2 * 4 * amount * dt * FPS + self.rng.random())):
                s = lv[self.rng.randrange(self.g.n)]
                if s[0] < 0.5:
                    s[0], s[1] = 0.7, self.rng.choice(pal)
        fade = math.exp(-dt / 0.3)
        out = []
        for s in lv:
            s[0] *= fade
            out.append(_mix(bg, s[1], s[0] ** 1.3))
        return out

    def _dest_hudba(self, eff, t, dt, data, music):
        """Dest Matrix: kapky padaji na udery (pocet podle sily), rychlost podle hlasitosti."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        drops = self.state.setdefault("dest_hudba", [])     # [sloupec, y, rychlost, barva]
        lv = self._lv(eff, music, dt)
        ncol = len(self.g.cols)
        dens = self._width(eff) / 5.0
        hit = self._hit(eff, music, "dest_hudba_n")
        if hit:
            for c in self.rng.sample(range(ncol), min(ncol, int(ncol * (0.15 + 0.35 * hit) * dens))):
                drops.append([c, self.g.y0 - 0.5, 9.0 + self.rng.random() * 5.0, self.rng.choice(pal)])
        if lv and self.rng.random() < lv["level"] * dens * 0.25 * dt * FPS:
            drops.append([self.rng.randrange(ncol), self.g.y0 - 0.5, 4.0 + self.rng.random() * 3.0,
                          self.rng.choice(pal)])
        boost = 0.6 + (lv["level"] if lv else 0.0)
        for d in drops:
            d[1] += d[2] * boost * dt
        drops[:] = [d for d in drops if d[1] < self.g.y1 + 3]
        out = []
        for i in range(self.g.n):
            c, y = self.g.col_of[i], self.g.cy[i]
            col = bg
            for d in drops:
                if d[0] != c:
                    continue
                dist = d[1] - y
                if -0.5 <= dist < 0.5:
                    col = _mix(d[3], (255, 255, 255), 0.5)
                    break
                if 0.5 <= dist < 2.2:
                    col = _add(col, _scale(d[3], (1 - (dist - 0.5) / 1.7) ** 1.5))
            out.append(col)
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
        return [_gradient(pal, f if f is not None else 0.0)] * self.g.n

    def _ukazatel(self, eff, t, dt, data, music):
        f = self._sensor_frac(eff, dt, data)
        pal, bg = self._pal(eff), self._bg(eff)
        row = ROWS.get(get(eff, "rada"), ROWS["cisla"])
        out = [bg] * self.g.n
        if f is None:
            return out
        n = len(row)
        for j, z in enumerate(row):
            i = self.g.index.get(z)
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
            age = self.rclock - pt
            if age >= life:
                continue
            col = _hsv(hue) if rc == "duha" else hex_rgb(rc)
            fade = 1 - age / life
            if mode == "klavesa":
                out[i] = _mix(out[i], col, fade ** 0.7)
            else:                                            # vlnka od klavesy
                r = age * 9.0
                px, py = self.g.cx[i], self.g.cy[i]
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
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
    demo = {"bands": [0.5] * 16, "beats": [(0.05, 1.0, 3)], "beat_n": 3, "bass": 0.7, "paleta": ["#ff0000"],
            "citlivost": 5}
    for typ in EFFECTS:
        e = default_effect(typ)
        eng.press(1)
        t = time.perf_counter()
        for _ in range(30):
            c = eng.frame(e, 1 / 30, {"CPU (Tctl/Tdie)": {"value": 70}}, demo)
        c = eng.reaction(dict(REACTION_DEFAULT, zapnuto=True), c)
        assert len(c) == len(KEYS)
        print(f"{typ:12s} {(time.perf_counter() - t) / 30 * 1000:5.2f} ms/snímek")
