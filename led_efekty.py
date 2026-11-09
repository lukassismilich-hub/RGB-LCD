# led_efekty.py - softwarove efekty LED pro vsechny ventilatory
#
# Aplikace sama pocita barvu kazde LED (~30x za sekundu) a posila ji ventilatorum v primem
# rezimu (F140 pres NZXT "super-fixed", ventilatory na desce pres ARGB hlavicku D_LED1).
# Diky tomu je jas pod kontrolou a efekty jsou stejne a synchronni na vsech ventilatorech.
# Ciste vypocty bez hardwaru - pouziva je vlakno LED (led.py) i zivy nahled v nastaveni.
#
# Ventilator ("cil") = (klic, pocet LED, skupina): F140 maji 8 LED, ventilatory na desce 14 LED.
# Vlna: kazdy ventilator dostane posun faze (led.wave_offsets podle rozmisteni ve skrini).

import collections
import colorsys
import math
import random
import zlib

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
    "divadlo": ("běžící světla", 2, True, True),
    "odraz": ("odraz (ping-pong)", 2, True, False),
    "duhove_dychani": ("duhové dýchání", 0, True, False),
    "stridani": ("střídání barev", 3, True, False),
    "blesky": ("bouřka / blesky", 2, True, False),
    "ohnostroj": ("ohňostroj", 0, True, False),
    "konfety": ("konfety", 0, True, False),
    "staticky_prechod": ("stojící přechod", 3, False, False),
    "teplota": ("podle teploty", 3, False, False),
    "majak": ("maják", 2, True, True),
    "vlneni": ("vlnění barev", 3, True, True),
    "dychajici_paleta": ("paleta s dýcháním", 3, True, True),
    "kapky": ("kapky", 4, True, False),
    "plamen": ("plamen zespodu", 0, True, False),
    "vodopad": ("vodopád", 3, True, True),
    "hladina": ("hladina (senzor)", 3, False, False),
    "pretahovana": ("přetahovaná", 2, True, False),
    "stafeta": ("štafeta", 2, True, True),
    "pracka": ("pračka", 3, True, False),
    "rozpousteni": ("rozpouštění", 3, True, False),
    "skladani": ("skládání", 3, True, True),
    "micky": ("skákající míčky", 3, True, False),
    "obeznice": ("oběžnice", 3, True, True),
    "vypnuto": ("vypnuto", 0, False, False),
}
ANIMATED = {k for k, v in EFFECTS.items() if v[2]} | {"teplota", "hladina"}
SENSOR_EFFECTS = ("teplota", "hladina")          # barva / hladina podle senzoru (senzor, min, max)

# efekty s paletou: volitelny pocet barev "pocet_barev" (min, max); vychozi = pocet v EFFECTS
PALETTE = {"duha_prelevani": (2, 8), "dychani": (1, 8), "paleta": (2, 8), "vysece": (2, 8), "stirani": (2, 8), "polarni_zare": (2, 8),
           "stridani": (2, 8), "staticky_prechod": (2, 8), "teplota": (2, 8), "vlneni": (2, 8),
           "dychajici_paleta": (2, 8), "kapky": (1, 8), "vodopad": (2, 8), "hladina": (1, 8),
           "pracka": (2, 8), "rozpousteni": (2, 8), "skladani": (1, 8), "micky": (1, 4), "obeznice": (2, 6)}
MAX_COLORS = 8
# barvy pro dalsi pozice palety (kdyz uzivatel pocet barev zvysi)
DEFAULT_PALETTE = ["#ff0000", "#0060ff", "#00ff40", "#ffb000", "#b000ff", "#00e5ff", "#ff0080", "#ffffff"]
# hotove palety (okno nastaveni: "Hotova paleta" u efektu s paletou, u hudby i u klavesnice) - jen syte barvy,
# mene syte jsou na LED bile
PALETTES = [
    ("ohen", "Oheň", ["#ff0000", "#ff5000", "#ffa000", "#ffe040"]),
    ("lava", "Láva", ["#ff0000", "#a00000", "#ff3c00", "#ff9000"]),
    ("zapad", "Západ slunce", ["#ff3c00", "#ff0060", "#b000ff", "#2800ff"]),
    ("ocean", "Oceán", ["#0020ff", "#0090ff", "#00e5c8", "#00ff80"]),
    ("led", "Led", ["#ffffff", "#60d0ff", "#0090ff", "#0030ff"]),
    ("les", "Les", ["#0a8000", "#40ff00", "#b4ff00", "#ffd000"]),
    ("zare", "Polární záře", ["#00ff80", "#00e5ff", "#7a00ff", "#00ff20"]),
    ("neon", "Neon", ["#ff00c8", "#00e5ff", "#b4ff00", "#7a00ff"]),
    ("kyberpunk", "Kyberpunk", ["#ff0080", "#7a00ff", "#00e5ff", "#ffe600"]),
    ("jed", "Jed", ["#40ff00", "#b4ff00", "#00ff80", "#7a00ff"]),
    ("vanoce", "Vánoce", ["#ff0000", "#00c000", "#ffffff", "#ffb000"]),
    ("trikolora", "Trikolóra", ["#ffffff", "#ff0000", "#0040ff"]),
]


def preset_colors(pid, lo=1, hi=MAX_COLORS):
    """Barvy hotove palety pro efekt s lo..hi barvami (kdyz se cela nevejde, vyberou se rovnomerne)."""
    cols = next((list(c) for i, _n, c in PALETTES if i == pid), None)
    if not cols:
        return []
    n = max(lo, min(hi, len(cols)))
    if n >= len(cols):
        return cols + [cols[i % len(cols)] for i in range(n - len(cols))]
    return [cols[round(i * (len(cols) - 1) / max(1, n - 1))] for i in range(n)]


# efekty, ktere vyuzivaji polohu LED na kruhu (nahore / dole); "otoceni" = 0 / 90 / 180 / 270 stupnu
VERTICAL = ("plamen", "vodopad", "hladina", "pretahovana", "micky")
# duha - prelevani: "barvy_rezim" "duha" = plna duha (vychozi), "barvy" = vlastni paleta
# "pauza" (s, 0-10): dychani = jak dlouho LED sviti naplno, nez zacne zhasinat a dalsi barva;
# stridani / stirani / rozpousteni = jak dlouho vsechny ventilatory sviti stejnou barvou, nez zacne dalsi zmena
PAUSE_EFFECTS = ("dychani", "stridani", "stirani", "rozpousteni")
MAX_PAUSE = 10.0
# "jiskreni" 0-10 u libovolneho efektu = bile jiskry pres nej (0 = bez)
MAX_GLITTER = 10
RELAY_K = 0.4                # stafeta: cela skrin (vsechny ventilatory) za 1 / (rate * RELAY_K) s
STACK_HOLD_S, STACK_FADE_S = 0.6, 0.7       # skladani: plny kruh chvili sviti, pak zhasne
BALL_E, BALL_BOUNCES = 0.75, 5              # micky: kolik rychlosti zbyde po odrazu, pocet odrazu

DEFAULT_EFFECT = {"typ": "duha_toceni", "barvy": ["#ff0000", "#0060ff", "#00ff40"], "rychlost": 4,
                  "opacny_smer": False, "senzor": "CPU (Tctl/Tdie)", "min": 40, "max": 90}


def color_count(eff):
    """Pocet barev efektu s paletou (u ostatnich pevny pocet z EFFECTS)."""
    typ = eff.get("typ", "")
    default = EFFECTS.get(typ, ("", 0))[1]
    if typ not in PALETTE:
        return default
    default = default or 3
    lo, hi = PALETTE[typ]
    try:
        n = int(eff.get("pocet_barev", default))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def palette(eff):
    """Barvy palety jako hex (presne color_count polozek, chybejici doplni DEFAULT_PALETTE)."""
    n = color_count(eff)
    cols = list(eff.get("barvy", []))[:n]
    for c in DEFAULT_PALETTE:
        if len(cols) >= n:
            break
        if c not in cols:
            cols.append(c)
    return cols[:n]


# playlist: efekty bez pravidelneho cyklu (nahodne nebo staticke) - jedno "opakovani" = NOMINAL_S sekund
NOMINAL_S = 5.0
NO_CYCLE = ("barva", "vlastni", "trpyt", "ohen", "duhovy_trpyt", "blesky", "ohnostroj", "konfety",
            "staticky_prechod", "teplota", "kapky", "plamen", "hladina", "vypnuto")


def cycle_s(eff, span=0.0):
    """Delka jednoho opakovani efektu v sekundach (pro playlist) - jedna otacka, jeden nadech, jedno
    projiti vsech barev palety...; efekty bez cyklu (NO_CYCLE) NOMINAL_S. span = sirka vlny jako ve frame()."""
    typ = eff.get("typ", "vypnuto")
    try:
        speed = max(1, min(10, int(eff.get("rychlost", 4))))
    except (TypeError, ValueError):
        speed = 4
    rate = 0.08 * speed
    k = color_count(eff) if typ in PALETTE else len(eff.get("barvy", [])) or 1
    if typ in NO_CYCLE or typ not in EFFECTS:
        s = NOMINAL_S
    elif typ == "duha_prelevani":
        s = k / (3 * rate) if eff.get("barvy_rezim") == "barvy" else 1 / (0.5 * rate)
    elif typ == "dychani":                       # nadech kazdou barvou palety
        s = (12.0 / speed + _pause(eff)) * k
    elif typ == "stirani":                       # setreni kazdou barvou palety (pri vlne vsech ventilatoru)
        span = max(0.0, min(0.95, span or 0.0))
        slots = max(1, round(1.0 / (1.0 - span)))
        s = (slots / (rate * 1.5) + _pause(eff)) * k
    elif typ == "stridani":
        s = (4.0 / speed + _pause(eff)) * k
    elif typ == "blikani":
        s = 1 / (speed * 0.8)
    elif typ == "polarni_zare":
        s = 1 / (rate * 0.35)
    elif typ == "plazma":
        s = 1 / (rate * 0.25)
    elif typ == "tep":                           # jeden uder
        s = 60.0 / (40 + 10 * speed)
    elif typ == "stroboskop":
        s = 1 / (0.4 * speed)
    elif typ == "policie":
        s = 1 / (speed * 0.3)
    elif typ == "divadlo":
        s = 2.0 / speed
    elif typ == "odraz":
        s = 1 / (rate * 1.2)
    elif typ in ("duhove_dychani", "dychajici_paleta"):
        s = 12.0 / speed
    elif typ == "vlneni":                        # paleta obejde kruh jednou
        s = 4 / rate
    elif typ == "vodopad":
        s = 1 / (rate * 1.2)
    elif typ == "pretahovana":
        s = 1 / (rate * 0.6)
    elif typ == "stafeta":                       # kometa obehne vsechny ventilatory
        s = 1 / (rate * RELAY_K)
    elif typ == "pracka":                        # tam a zpet
        s = 32.0 / speed
    elif typ == "rozpousteni":                   # jako stirani: kazdou barvou palety, pri vlne postupne
        span = max(0.0, min(0.95, span or 0.0))
        slots = max(1, round(1.0 / (1.0 - span)))
        s = (slots / (rate * 1.2) + _pause(eff)) * k
    elif typ == "skladani":
        s = 1 / (rate * 0.5) + STACK_HOLD_S + STACK_FADE_S
    elif typ == "micky":
        s = _ball_times(speed)[2]
    else:                                        # otacive: duha, kometa, prechod, paleta, vysece, majak...
        s = 1 / rate
    return max(0.1, s)


def glitter(eff):
    """Jiskreni navic 0..MAX_GLITTER (0 = vypnuto)."""
    try:
        return max(0, min(MAX_GLITTER, int(eff.get("jiskreni", 0))))
    except (TypeError, ValueError):
        return 0


def animated(eff):
    """Meni se efekt v case? (staticky s jiskrenim taky)"""
    typ = eff.get("typ")
    return typ in ANIMATED or (typ in EFFECTS and typ != "vypnuto" and glitter(eff) > 0)


def _ball_times(speed):
    """Skakajici micky: (doba prvniho padu, [doby odrazu], cely cyklus) v sekundach."""
    t0 = 4.0 / (1 + speed * 0.5)                 # odraz do plne vysky by trval t0
    bounces = [t0 * BALL_E ** i for i in range(1, BALL_BOUNCES + 1)]
    return t0 / 2, bounces, t0 / 2 + sum(bounces) + t0 * 0.25


def _ball_height(tt, speed):
    """Vyska micku 0..1 v case tt od zacatku cyklu: pad shora, pak odrazy cim dal niz."""
    fall, bounces, _total = _ball_times(speed)
    if tt < fall:
        return 1 - (tt / fall) ** 2
    tt -= fall
    for i, d in enumerate(bounces, start=1):
        if tt < d:
            u = tt / d
            return BALL_E ** (2 * i) * 4 * u * (1 - u)
        tt -= d
    return 0.0


def mirror(cols):
    """Zrcadlove otoceny kruh (osa svisle pres spodni LED) - "ozubena kola": sousedni ventilator se
    pak toci opacne, svisle efekty zustanou stejne."""
    n = len(cols)
    if n < 2:
        return cols
    b = 2 * bottom_led(n)
    return [cols[(b - i) % n] for i in range(n)]


def _pause(eff):
    try:
        return max(0.0, min(MAX_PAUSE, float(eff.get("pauza", 0))))
    except (TypeError, ValueError):
        return 0.0


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

    def frame(self, eff, t, key, n, fan_idx=0, fan_count=1, wave=False, custom=None, data=None, dt=1 / FPS,
              offset=None, span=None, slot=None):
        """Barvy (r, g, b) 0-255 jako float pro n LED jednoho ventilatoru v case t.
        offset = posun faze pri vlne (0..1); jinak fan_idx / fan_count, kdyz je wave.
        span = nejvetsi posun faze ze vsech ventilatoru (sirka vlny, pro pauzu u dychani).
        slot = (poradi ventilatoru ve skrini, pocet pozic) pro stafetu - i bez vlny (led.relay_slots).
        "jiskreni" u efektu = bile jiskry pres hotovy snimek."""
        out = self._frame(eff, t, key, n, fan_idx, fan_count, wave, custom, data, dt, offset, span, slot)
        g = glitter(eff)
        if g and n > 1 and eff.get("typ") != "vypnuto":
            st = self.state.setdefault(("jiskreni", key), [])
            if len(st) != n:
                st[:] = [0.0] * n
            dec = math.exp(-dt / 0.12)
            out = list(out)
            for i in range(n):
                st[i] *= dec
                if self.rng.random() < dt * g * 0.06:
                    st[i] = 1.0
                if st[i] > 0.02:
                    out[i] = tuple(max(out[i][j], 255.0 * st[i]) for j in range(3))
        return out

    def _perm(self, key, step, n):
        """Nahodne poradi n LED pro krok step (stejne po celou dobu kroku)."""
        st = self.state.get(("perm", key))
        if st is None or st[0] != (step, n):
            order = list(range(n))
            random.Random(zlib.crc32(f"{key}:{step}".encode())).shuffle(order)
            st = self.state[("perm", key)] = ((step, n), order)
        return st[1]

    def _frame(self, eff, t, key, n, fan_idx, fan_count, wave, custom, data, dt, offset, span, slot):
        typ = eff.get("typ", "vypnuto")
        src = palette(eff) if typ in PALETTE else eff.get("barvy", [])
        cols = [hex_rgb(c) for c in src] or [(255, 255, 255)]
        speed = max(1, min(10, int(eff.get("rychlost", 4))))
        rate = 0.08 * speed                       # otacky za sekundu (1 -> 0,08, 10 -> 0,8)
        direction = -1 if eff.get("opacny_smer") else 1
        if offset is None:
            offset = fan_idx / max(1, fan_count) if wave else 0.0
            if span is None:
                span = (fan_count - 1) / max(1, fan_count) if wave else 0.0
        span = max(0.0, span or 0.0, offset)
        if EFFECTS.get(typ, (0, 0, False, False))[3]:
            offset *= direction                   # vlna jde stejnym smerem i pri opacnem otaceni
        black = (0.0, 0.0, 0.0)

        if typ == "barva":
            return [cols[0]] * n
        if typ == "vlastni":
            src = [hex_rgb(c) for c in (custom or [])] or [(255, 255, 255)]
            return [src[i % len(src)] for i in range(n)]
        if typ == "duha_toceni":
            ph = t * rate * direction + offset
            return [_hsv(_ring_u(i, n) + ph) for i in range(n)]
        if typ == "duha_prelevani":
            if eff.get("barvy_rezim") == "barvy":
                # kazda barva trva stejne dlouho jako jedna ze sesti zakladnich barev plne duhy
                return [_cyclic(cols, t * rate * 0.5 * 6 / len(cols) + offset)] * n
            c = _hsv(t * rate * 0.5 + offset)
            return [c] * n
        if typ == "dychani":
            period = 6.0 / speed * 2              # jeden nadech (s)
            pause = _pause(eff)
            # cyklus trva vzdy period + pauza (rychlost efektu se pauzou ani vlnou nemeni);
            # nadech jde vlnou (ventilator s nejvetsim posunem prvni), pak sviti vsechny najednou
            # "pauza" sekund a vlnou zhasnou - vlna se vejde do nadechu a vydechu
            spread = span * period / 2            # za jak dlouho vlna projde vsemi ventilatory
            breath = period - spread              # nadech + vydech jednoho ventilatoru
            total = period + pause
            x = (t - (span - offset) * period / 2) / total
            cycle = math.floor(x)
            s = (x - cycle) * total
            hold = spread + pause                 # jak dlouho tento ventilator sviti naplno
            if s >= breath / 2 + hold:
                s -= hold
            elif s >= breath / 2:
                s = breath / 2
            k = (1 - math.cos(s / breath * 2 * math.pi)) / 2
            return [_scale(cols[cycle % len(cols)], k)] * n
        if typ == "kometa":
            head = ((t * rate * direction + offset) % 1.0) * n + _ring_shift(n)
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
            return [_mix(cols[0], c2, (1 + math.cos(2 * math.pi * (_ring_u(i, n) + ph))) / 2) for i in range(n)]
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
            return [_cyclic(cols, _ring_u(i, n) + ph, hard=typ == "vysece") for i in range(n)]
        if typ == "dvojita_kometa":
            head = ((t * rate * direction + offset) % 1.0) * n + _ring_shift(n)
            c2 = cols[1] if len(cols) > 1 else cols[0]
            a = _comet(head, n, max(2.0, n * 0.4), cols[0], direction)
            b = _comet((head + n / 2) % n, n, max(2.0, n * 0.4), c2, direction)
            return [tuple(max(a[i][j], b[i][j]) for j in range(3)) for i in range(n)]
        if typ == "stirani":
            # jedno setreni ventilatoru trva "wipe" (podle rychlosti). Pri vlne se ventilatory setrou
            # postupne jeden po druhem (poradi podle posunu, ventilator s nejvetsim posunem prvni);
            # az sviti vsechny novou barvou, drzi ji "pauza" sekund, pak dalsi barva.
            # Posuny vlny jsou v/m pro m pozic, span = (m - 1) / m -> m = 1 / (1 - span).
            wipe = 1.0 / (rate * 1.5)
            slots = max(1, round(1.0 / (1.0 - span))) if span < 1 else 1
            slot = round((span - abs(offset)) * slots)            # 0 = setre se prvni
            total = slots * wipe + _pause(eff)
            step = math.floor(t / total)
            sh = _ring_shift(n)                                   # setreni zacina vpravo u vsech ventilatoru
            edge = max(0.0, min(1.0, (t - step * total - slot * wipe) / wipe)) * (n + sh)
            prev, cur = cols[step % len(cols)], cols[(step + 1) % len(cols)]
            out = []
            for i in range(n):
                j = (i - sh) % n if direction > 0 else (sh - i - 1) % n     # poradi LED pri setreni
                out.append(_mix(prev, cur, edge - j))            # mekka hrana jedne LED
            return out
        if typ == "polarni_zare":
            ph = t * rate * 0.35
            out = []
            for i in range(n):
                u = _ring_u(i, n) + offset
                x = 0.5 + 0.3 * math.sin(2 * math.pi * (u + ph)) + 0.2 * math.sin(2 * math.pi * (2 * u - ph * 1.7) + 1.3)
                k = 0.55 + 0.45 * math.sin(2 * math.pi * (u * 3 + ph * 0.8) + 0.5)
                out.append(_scale(_gradient(cols, x), k))
            return out
        if typ == "plazma":
            ph = t * rate
            out = []
            for i in range(n):
                u = _ring_u(i, n) + offset
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
                mine = ((i - _ring_shift(n)) % n < n / 2) == (side == 0)
                out.append((cols[0] if side == 0 else c2) if on and mine else black)
            return out
        if typ == "divadlo":                      # kazda treti LED sviti a posouva se
            step = int(math.floor(t * speed * 1.5 + offset * 3))
            bg = _scale(cols[1], 0.1) if len(cols) > 1 else black
            return [cols[0] if (i * direction - step) % 3 == 0 else bg for i in range(n)]
        if typ == "odraz":                        # svetlo s ocasem jezdi tam a zpet po pulce kruhu
            bg = _scale(cols[1], 0.08) if len(cols) > 1 else black
            x = (t * rate * 1.2 + offset) % 1.0
            tri = 1 - abs(2 * x - 1)              # 0 -> 1 -> 0
            pos = tri * 0.5                       # od vpravo (0) k vlevo (0,5 otacky), zrcadlove dole i nahore
            out = []
            for i in range(n):
                u = _ring_u(i, n) % 1.0
                d = abs(min(u, 1 - u) - pos)      # vzdalenost po kruhu (podil otacky)
                k = max(0.0, 1 - d / 0.275) ** 2  # sirka jako drive 2,2 LED z 8
                out.append(tuple(max(bg[j], cols[0][j] * k) for j in range(3)))
            return out
        if typ == "duhove_dychani":
            period = 6.0 / speed * 2
            x = t / period + offset
            k = (1 - math.cos((x % 1.0) * 2 * math.pi)) / 2
            return [_hsv(int(x) * 0.13 + x * 0.02, k)] * n
        if typ == "stridani":                     # ostre prepinani barev
            # krok = jak dlouho trva jedna barva (podle rychlosti); cyklus = krok + pauza.
            # Pri vlne se kazda zmena barvy siri ventilator po ventilatoru (ventilator s nejvetsim
            # posunem prvni, prodleva (span - offset) * krok) - az sviti vsechny stejne, drzi barvu
            # do konce kroku a "pauza" sekund, pak zacne dalsi zmena.
            step = 4.0 / speed
            total = step + _pause(eff)
            idx = int(math.floor((t - (span - offset) * step) / total)) % len(cols)
            return [cols[idx]] * n
        if typ == "blesky":
            st = self.state.setdefault(("blesky", key), [0.0, 0.0])      # jas zablesku, cas dalsiho
            bg = _scale(cols[1], 0.12) if len(cols) > 1 else black
            st[0] *= 0.02 ** dt                   # rychle hasne
            if self.rng.random() < dt * speed * 0.12:
                st[0] = 1.0
                st[1] = t + self.rng.uniform(0.08, 0.2)           # casto dvojity zablesk
            elif st[1] and t >= st[1]:
                st[0], st[1] = max(st[0], 0.8), 0.0
            k = st[0]
            return [tuple(max(bg[j], cols[0][j] * k * (0.7 + 0.3 * ((i * 7 + int(t * 30)) % 5) / 4))
                          for j in range(3)) for i in range(n)]
        if typ == "ohnostroj":                    # vybuchy nahodne barvy se siri od jedne LED
            bursts = self.state.setdefault(("ohnostroj", key), [])
            if self.rng.random() < dt * speed * 0.35:
                bursts.append([self.rng.randrange(n), 0.0, self.rng.random()])
            out = [black] * n
            for b in bursts:
                b[1] += dt * (0.4 + speed * 0.08)
            bursts[:] = [b for b in bursts if b[1] < 1.2]
            for center, age, hue in bursts:
                radius = age * n * 0.45
                fade = max(0.0, 1 - age / 1.2)
                c = _hsv(hue)
                for i in range(n):
                    d = min((i - center) % n, (center - i) % n)
                    k = max(0.0, 1 - abs(d - radius) / 1.5) * fade
                    if k > 0:
                        out[i] = tuple(max(out[i][j], c[j] * k) for j in range(3))
            return out
        if typ == "konfety":                      # kazda LED plynule prechazi na nahodnou barvu
            st = self.state.setdefault(("konfety", key), [])
            if len(st) != n:
                st[:] = [[_hsv(self.rng.random()), _hsv(self.rng.random())] for _ in range(n)]
            a = min(1.0, dt * speed * 0.6)
            for s_ in st:
                s_[0] = _mix(s_[0], s_[1], a)
                if self.rng.random() < dt * speed * 0.08:
                    s_[1] = _hsv(self.rng.random())
            return [s_[0] for s_ in st]
        if typ == "staticky_prechod":
            k = len(cols)
            out = []
            for i in range(n):
                x = (_ring_u(i, n) % 1.0) * k
                a = int(x) % k
                out.append(_mix(cols[a], cols[(a + 1) % k], x - int(x)))
            return out
        if typ in SENSOR_EFFECTS:
            fr = self._sensor_frac(eff, typ, key, data, dt)
            if fr is None:
                return [(40.0, 40.0, 40.0)] * n
            if typ == "teplota":
                return [_gradient(cols, fr)] * n
            # hladina: LED rozsvicene odspodu do vysky podle hodnoty, barva podle vysky (mekka hrana)
            out = []
            for i in range(n):
                h = 1 - (_ring_y(i, n, eff) + 1) / 2              # 0 = dole, 1 = nahore
                k = max(0.0, min(1.0, (fr - h) * n / 2 + 0.5))
                out.append(_scale(_gradient(cols, h), 0.06 + 0.94 * k))
            return out
        if typ == "majak":                        # jeden siroky paprsek obiha dokola, slaba zare kolem
            pos = ((t * rate * direction + offset) % 1.0) * n + _ring_shift(n)
            bg = _scale(cols[1], 0.06) if len(cols) > 1 else black
            width = max(1.2, n * 0.14)
            out = []
            for i in range(n):
                d = min((i - pos) % n, (pos - i) % n)
                k = max(max(0.0, 1 - d / width) ** 1.5, 0.12 * max(0.0, 1 - d / (n * 0.4)))
                out.append(tuple(max(bg[j], cols[0][j] * k) for j in range(3)))
            return out
        if typ == "vlneni":                       # paleta po obvodu, pres ni bezi vlny jasu
            ph = t * rate * direction + offset
            out = []
            for i in range(n):
                u = _ring_u(i, n)
                k = 0.12 + 0.88 * ((1 + math.sin(2 * math.pi * (2 * u - ph))) / 2) ** 2
                out.append(_scale(_cyclic(cols, u + ph * 0.25), k))
            return out
        if typ == "dychajici_paleta":             # otacejici se paleta, cela dycha
            ph = t * rate * direction + offset
            period = 12.0 / speed
            k = 0.1 + 0.9 * (1 - math.cos(2 * math.pi * (t / period + offset))) / 2
            return [_scale(_cyclic(cols, _ring_u(i, n) + ph), k) for i in range(n)]
        if typ == "kapky":                        # nahodne LED se rozsviti barvou z palety a pomalu hasnou
            st = self.state.setdefault(("kapky", key), [[0.0, 0] for _ in range(n)])
            if len(st) != n:
                st[:] = [[0.0, 0] for _ in range(n)]
            decay = 0.5 ** (dt * speed * 0.9)
            for s_ in st:
                s_[0] *= decay
                if self.rng.random() < dt * speed * 0.09:
                    s_[:] = [1.0, self.rng.randrange(len(cols))]
            return [_scale(cols[s_[1] % len(cols)], s_[0] ** 1.5) for s_ in st]
        if typ == "plamen":                       # ohen hori odspodu: dole jasne zluta, nahore temne cervena
            st = self.state.setdefault(("plamen", key), [0.6] * n)
            if len(st) != n:
                st[:] = [0.6] * n
            a = min(1.0, dt * speed * 1.8)
            out = []
            for i in range(n):
                st[i] += (self.rng.uniform(0.3, 1.0) - st[i]) * a
                h = (_ring_y(i, n, eff) + 1) / 2                 # 1 = dole, 0 = nahore
                v = st[i] * (0.08 + 0.92 * h ** 1.3)
                out.append(_scale(_mix((255, 25, 0), (255, 190, 40), min(1.0, v * 1.2)), min(1.0, 0.1 + v)))
            return out
        if typ == "vodopad":                      # barvy teknou shora dolu po obou stranach
            ph = t * rate * direction * 1.2 - offset
            return [_cyclic(cols, (_ring_y(i, n, eff) + 1) / 2 * 0.8 - ph) for i in range(n)]
        if typ == "pretahovana":                  # dve barvy, hranice mezi nimi se hybe nahoru a dolu
            c2 = cols[1] if len(cols) > 1 else black
            x = 0.12 + 0.76 * (1 + math.sin(2 * math.pi * (t * rate * 0.6 + offset))) / 2
            out = []
            for i in range(n):
                h = (_ring_y(i, n, eff) + 1) / 2                 # 0 = nahore, 1 = dole
                out.append(_mix(cols[0], c2, max(0.0, min(1.0, (h - x) / 0.18 + 0.5))))
            return out
        if typ == "stafeta":                      # kometa obehne ventilator a preskoci na dalsi ve skrini
            if slot is None:                      # bez udaje o poradi: z posunu vlny jako u stirani
                cnt = max(1, round(1.0 / (1.0 - span))) if span < 1 else 1
                slot = (round((span - abs(offset)) * cnt), cnt)
            idx, cnt = slot[0], max(1, slot[1])
            lap = 1.0 / (rate * RELAY_K) / cnt    # obeh jednoho ventilatoru
            x = (t / lap - idx) % cnt             # 0..1 = hlava je na tomto ventilatoru
            bg = _scale(cols[1], 0.06) if len(cols) > 1 else black
            if n == 1:
                k = math.sin(math.pi * x) ** 2 if x < 1 else 0.0
                return [tuple(max(bg[j], cols[0][j] * k) for j in range(3))]
            tail = max(2.0, n * 0.5)
            head = x * n                          # LED od zacatku obehu (vpravo)
            out = []
            for i in range(n):
                j = i if direction > 0 else (n - i) % n
                d = (head - j) % n if cnt == 1 else head - j       # vzdalenost za hlavou
                if cnt > 1 and (d < -1 or head > n + tail):
                    k = 0.0
                elif d < 0:
                    k = 1 + d                     # mekka hlava
                else:
                    k = max(0.0, 1 - d / tail) ** 2
                out.append(tuple(max(bg[j2], cols[0][j2] * k) for j2 in range(3)))
            return out
        if typ == "pracka":                       # vysece se roztoci, zpomali, zastavi a rozjedou opacne
            th = 2 * math.pi * (t * speed / 32.0 + offset)
            ph = 1.1 * (math.sin(th) - math.sin(3 * th) / 9)       # skoro rovnomerne otaceni, mekky obrat
            return [_cyclic(cols, _ring_u(i, n) + ph, hard=True) for i in range(n)]
        if typ == "rozpousteni":                  # LED po jedne nahodne preskakuji na dalsi barvu palety
            dis = 1.0 / (rate * 1.2)              # rozpusteni jednoho ventilatoru; pri vlne postupne (jako stirani)
            slots = max(1, round(1.0 / (1.0 - span))) if span < 1 else 1
            sl = round((span - abs(offset)) * slots)
            total = slots * dis + _pause(eff)
            step = math.floor(t / total)
            f = max(0.0, min(1.0, (t - step * total - sl * dis) / dis))
            prev, cur = cols[step % len(cols)], cols[(step + 1) % len(cols)]
            if n == 1:
                return [_mix(prev, cur, f)]
            order = self._perm(key, step, n)
            return [_mix(prev, cur, f * (n + 1) - order[i]) for i in range(n)]
        if typ == "skladani":                     # svetla obihaji a skladaji se vedle sebe, plny kruh zhasne
            fill = 1.0 / (rate * 0.5)
            total = fill + STACK_HOLD_S + STACK_FADE_S
            x = t / total + offset
            cyc = int(math.floor(x))
            tt = (x - cyc) * total
            fade = 1.0 if tt < fill + STACK_HOLD_S else max(0.0, 1 - (tt - fill - STACK_HOLD_S) / STACK_FADE_S)
            flash = max(0.0, 1 - (tt - fill) / STACK_HOLD_S) * 0.5 if tt >= fill else 0.0
            if n == 1:
                return [_scale(_mix(cols[cyc % len(cols)], (255, 255, 255), flash), min(1.0, tt / fill) * fade)]
            dist = n * (n + 1) / 2.0              # soucet drah vsech svetel (svetlo k dojede na pozici n - 1 - k)
            lit = [None] * n                      # barva na pozici (v poradi skladani)
            mov = None                            # (pozice, barva) svetla na ceste
            start = 0.0
            for k in range(n):
                d = fill * (n - k) / dist
                c = cols[(k + cyc) % len(cols)]
                if tt >= start + d:
                    lit[n - 1 - k] = c
                elif tt >= start:
                    mov = (-1 + (tt - start) / d * (n - k), c)
                    break
                start += d
            out = []
            for i in range(n):
                j = i if direction > 0 else n - 1 - i
                c = lit[j] or black
                if mov:
                    c = tuple(max(c[j2], mov[1][j2] * max(0.0, 1 - abs(j - mov[0]))) for j2 in range(3))
                out.append(_scale(_mix(c, (255, 255, 255), flash if lit[j] else 0.0), fade))
            return out
        if typ == "micky":                        # micky padaji ke spodku a odrazeji se cim dal niz
            total = _ball_times(speed)[2]
            w = max(0.22, 2.9 / n)
            hs = [_ball_height((t + (offset + b / len(cols)) * total) % total, speed) for b in range(len(cols))]
            if n == 1:
                return [_scale(cols[0], 0.1 + 0.9 * (1 - hs[0]) ** 2)]
            out = []
            for i in range(n):
                h = 1 - (_ring_y(i, n, eff) + 1) / 2              # 0 = dole, 1 = nahore
                c = black
                for b, hb in enumerate(hs):
                    k = max(0.0, 1 - abs(h - hb) / w) ** 1.5
                    c = tuple(max(c[j], cols[b][j] * k) for j in range(3))
                out.append(c)
            return out
        if typ == "obeznice":                     # kazda barva = bod s ocasem a vlastni rychlosti, barvy se michaji
            if n == 1:
                return [_cyclic(cols, t * rate + offset)]
            out = [black] * n
            tail = max(2.0, n * 0.35)
            for b, c in enumerate(cols):
                dirb = direction * (-1 if b % 2 else 1)            # liche obihaji proti
                head = ((t * rate * (1 + 0.45 * b) * dirb + offset + b / len(cols)) % 1.0) * n
                for i, cc in enumerate(_comet(head, n, tail, c, dirb)):
                    out[i] = tuple(min(255.0, out[i][j] + cc[j]) for j in range(3))
            return out
        return [black] * n

    def _sensor_frac(self, eff, typ, key, data, dt):
        """Vyhlazena hodnota senzoru (~2 s, at barva neskace) jako podil min..max, None = bez dat."""
        v = None
        item = (data or {}).get(eff.get("senzor", ""))
        if item is not None:
            v = item.get("value")
        smooth = self.state.get((typ, key))
        if v is not None:
            smooth = v if smooth is None else smooth + (v - smooth) * min(1.0, dt / 2.0)
            self.state[(typ, key)] = smooth
        if smooth is None:
            return None
        lo, hi = float(eff.get("min", 40)), float(eff.get("max", 90))
        return 0.0 if hi == lo else max(0.0, min(1.0, (smooth - lo) / (hi - lo)))


    # ------------------------------------------------------------- hudebni vizualizer (Spotify)

    def music(self, eff, snap, key, n, pos=0.0, delay=0.0, dt=1 / FPS, slot=None):
        """Barvy n LED jednoho cile pro hudebni vizualizer. snap = snimek analyzy (hudba.Analyzer /
        music_demo), pos = poloha ve skrini 0 (predek) .. 1 (zadek) - spektrum, delay = 0..1 jak pozde
        k cili dorazi uder pri vlne (MUSIC_WAVE_S), slot = (poradi ve skrini, pocet cilu) pro skakani."""
        out = self._music(eff, snap, key, n, pos, delay, dt, slot)
        if not eff.get("drop_zablesk", True):
            return out
        # duraz na drop: bily zablesk, ktery probehne skrini zepredu dozadu
        d = int(snap.get("drop_n", 0))
        st = self.state.setdefault(("hudba_drop", key), [d, 99.0])
        if d != st[0]:
            if d > st[0] and not snap.get("quiet"):
                st[1] = 0.0
            st[0] = d
        st[1] += dt
        a = st[1] - max(0.0, min(1.0, pos)) * DROP_WAVE_S
        if 0 <= a < 1.5:
            k = math.exp(-a / 0.3) * 255.0 * self._jas(eff)
            out = [tuple(max(c[j], k) for j in range(3)) for c in out]
        return out

    @staticmethod
    def _jas(eff):
        try:
            return max(0.0, min(1.0, float(eff.get("jas", 100)) / 100.0)) ** 2
        except (TypeError, ValueError):
            return 1.0

    def _music(self, eff, snap, key, n, pos, delay, dt, slot):
        cols = [hex_rgb(c) for c in (snap.get("paleta") or [])] or [hex_rgb(c) for c in DEFAULT_PALETTE[:3]]
        k = len(cols)
        d = int(snap.get("drop_n", 0))                    # refren / drop: prohodi hlavni a doplnkovou barvu
        main, acc = cols[d % k], cols[(d + 1) % k]
        white = (255.0, 255.0, 255.0)
        jas = self._jas(eff)
        styl = music_style(eff, snap)
        lag = delay * MUSIC_WAVE_S
        bass, mid, high = (float(snap.get(x, 0.0)) for x in ("bass", "mid", "high"))
        level, ph = float(snap.get("level", 0.0)), float(snap.get("phase", 0.0))
        bands = list(snap.get("bands") or [0.0] * 16)
        raw = list(bands)                                 # pasma bez durazu na basy (barva podle tonu)
        # duraz na basy 0..1: kontrast basu (mezi udery tma, kopak naplno), silnejsi zablesk uderu,
        # slabsi vliv stredu a vysek; v pasmech se vyssi frekvence utlumi
        e = bass_emphasis(eff)
        bass = _contrast(bass, e)
        high *= 1 - 0.8 * e
        nb = max(1, len(bands) - 1)
        bands = [_contrast(v, e) * (1 - 0.55 * e * i / nb) for i, v in enumerate(bands)]
        level = (1 - e) * level + e * bass
        fl = 0.0                                          # zablesk uderu (s vlnou skrini)
        for b in snap.get("beats", ()):
            a = b[0] - lag
            if a >= 0:
                fl = max(fl, b[1] * math.exp(-a / (0.14 + 0.06 * e)))
        new = self._new_beats(key, snap, lag)
        rnd = self.rng

        if snap.get("quiet"):                             # pauza / ticho: klidne vlneni v barvach skladby
            out = [_scale(_cyclic(cols, _ring_u(i, n) + ph * 0.3), 0.22 + 0.08 * math.sin(ph * 6)) for i in range(n)]
        elif styl == "spektrum":
            x = max(0.0, min(1.0, pos)) * (len(bands) - 1)
            lv = _band_at(bands, x)
            st = self.state.setdefault(("hudba_spicka", key), [0.0])
            st[0] = max(lv, st[0] - dt * 0.5)             # spicka pomalu klesa
            if n == 1:
                out = [_scale(_gradient(cols, lv), 0.12 + 0.88 * lv)]
            else:
                out = []
                for i in range(n):
                    h = 1 - (_ring_y(i, n, eff) + 1) / 2  # 0 = dole, 1 = nahore
                    lit = max(0.0, min(1.0, (lv - h) * n / 2 + 0.5))
                    c = _scale(_gradient(cols, h), 0.05 + 0.95 * lit)
                    pk = max(0.0, 1 - abs(h - st[0]) * n / 1.5) if st[0] > 0.08 else 0.0
                    out.append(_mix(c, _mix(acc, white, 0.6), pk * 0.8))
        elif styl == "ekvalizer":
            out = []
            for i in range(n):
                h = 0.5 if n == 1 else 1 - (_ring_y(i, n, eff) + 1) / 2
                v = level if n == 1 else _band_at(bands, h * (len(bands) - 1))
                out.append(_scale(_gradient(cols, h), min(1.0, 0.05 + 0.95 * v ** 1.4 + 0.2 * fl)))
        elif styl == "komety":
            st = self.state.setdefault(("hudba_komety", key), [])
            bpm = float(snap.get("bpm") or 120.0)
            for _bid, strength in new:
                st.append([rnd.random() * n, rnd.choice((-1, 1)) * (0.5 + bpm / 160.0), rnd.randrange(k), strength, 0.0])
            for c in st:
                c[0] = (c[0] + c[1] * n * dt) % max(1, n)
                c[4] += dt
            st[:] = [c for c in st if c[4] < 1.3][-6:]
            bg = _scale(main, 0.04 + 0.16 * bass)
            out = [bg] * n
            if n == 1:
                last = st[-1] if st else None
                out = [_mix(bg, cols[last[2] % k], fl) if last else bg]
            else:
                for head, vel, ci, strength, age in st:
                    life = strength * max(0.0, 1 - age / 1.3)
                    tail = max(2.0, n * 0.45)
                    for i in range(n):
                        dd = ((head - i) if vel > 0 else (i - head)) % n
                        kk = max(0.0, 1 - dd / tail) ** 2 * life
                        if kk > 0:
                            out[i] = tuple(max(out[i][j], cols[ci % k][j] * kk) for j in range(3))   # paleta se mohla zmenit
        elif styl == "jiskry":
            st = self.state.setdefault(("hudba_jiskry", key), [])
            if len(st) != n:
                st[:] = [[0.0, 0] for _ in range(n)]
            dec = math.exp(-dt / 0.25)
            for s in st:
                s[0] *= dec
            for _bid, strength in new:
                for i in rnd.sample(range(n), max(1, int(n * (0.25 + 0.35 * strength)))):
                    st[i] = [strength, rnd.randrange(k)]
            if n > 1:
                for s in st:
                    if rnd.random() < dt * 8 * high ** 2.5:
                        s[0], s[1] = max(s[0], 0.6), -1
            bg = _scale(main, 0.04 + 0.1 * level)
            out = []
            for v, ci in st:
                c = _mix(acc, white, 0.45) if ci < 0 else cols[ci % k]
                out.append(tuple(max(bg[j], c[j] * v) for j in range(3)))
        elif styl == "klidny":
            st = self.state.setdefault(("hudba_klid", key), [0.0])
            st[0] += (level - st[0]) * min(1.0, dt / 0.6)
            out = [_scale(_cyclic(cols, _ring_u(i, n) + ph * 0.5), 0.15 + 0.85 * st[0]) for i in range(n)]
        elif styl == "zablesky":                         # kazdy uder = kratky zablesk dalsi barvou, jinak tma
            st = self.state.setdefault(("hudba_zab", key), [0.0, 0])
            st[0] *= math.exp(-dt / 0.07)
            for _bid, strength in new:
                st[0], st[1] = max(st[0], strength), (st[1] + 1) % k
            c = _mix(cols[st[1] % k], white, 0.35 * st[0])
            out = [tuple(max(main[j] * 0.02, c[j] * st[0]) for j in range(3))] * n
        elif styl == "vlny":                             # kazdy uder = vlna od spodku kruhu nahoru po obou stranach
            st = self.state.setdefault(("hudba_vlny", key), [])
            for _bid, strength in new:
                st.append([0.0, rnd.randrange(k), strength])
            for w in st:
                w[0] += dt
            st[:] = [w for w in st if w[0] < 0.6][-5:]
            bg = _scale(main, 0.03 + 0.1 * bass)
            out = [bg] * n
            for i in range(n):
                d = 0.0 if n == 1 else 1 - (_ring_y(i, n, eff) + 1) / 2     # 0 = dole, 1 = nahore
                for age, ci, strength in st:
                    front = age / 0.35                    # nahoru za 0,35 s
                    kk = strength * max(0.0, 1 - abs(d - front) / 0.3) * max(0.0, 1 - age / 0.6)
                    if n == 1:
                        kk = strength * max(0.0, 1 - age / 0.3)
                    if kk > 0:
                        out[i] = tuple(max(out[i][j], cols[ci % k][j] * kk) for j in range(3))
        elif styl == "vu":                               # ukazatel hlasitosti dokola od vrsku, spicka drzi
            st = self.state.setdefault(("hudba_vu", key), [0.0, 0.0])
            lv = max(level, bass)
            st[0] += (lv - st[0]) * min(1.0, dt / 0.05)
            st[1] = max(st[0], st[1] - dt * 0.4)
            if n == 1:
                out = [_scale(_gradient(cols, st[0]), 0.1 + 0.9 * st[0])]
            else:
                out = []
                for i in range(n):
                    u = ((_ring_angle(i, n, eff) + math.pi / 2) / (2 * math.pi)) % 1.0   # 0 = nahore, po smeru hodin
                    lit = max(0.0, min(1.0, (st[0] - u) * n + 0.5))
                    c = _scale(_gradient(cols, u), 0.04 + 0.96 * lit)
                    pk = max(0.0, 1 - abs(u - st[1]) * n) if st[1] > 0.05 else 0.0
                    out.append(_mix(c, _mix(acc, white, 0.6), pk * 0.9))
        elif styl == "stridani":                         # kazdy uder = cely ventilator dalsi barvou palety
            st = self.state.setdefault(("hudba_strid", key), [0, 0, 1.0])
            for _bid, _strength in new:
                st[1], st[0], st[2] = st[0], (st[0] + 1) % k, 0.0
            st[2] = min(1.0, st[2] + dt / 0.08)
            c = _mix(cols[st[1] % k], cols[st[0] % k], st[2])
            out = [_scale(c, min(1.0, 0.3 + 0.7 * max(bass, fl)))] * n
        elif styl == "rotace":                           # vysece palety se toci, s uderem poskoci
            st = self.state.setdefault(("hudba_rot", key), [0.0, 0.0])
            for _bid, strength in new:
                st[1] += 0.5 / k * (0.5 + strength)
            st[1] += dt * (0.05 + 0.4 * bass)
            st[0] += (st[1] - st[0]) * min(1.0, dt / 0.06)
            kk = min(1.0, 0.25 + 0.75 * max(bass, fl))
            out = [_scale(_cyclic(cols, _ring_u(i, n) + st[0], hard=True), kk) for i in range(n)]
        elif styl == "plameny":                          # plameny zespodu, vyska podle basu
            st = self.state.setdefault(("hudba_plam", key), [0.0, [0.6] * n])
            if len(st[1]) != n:
                st[1] = [0.6] * n
            st[0] += (min(1.2, 0.25 + 0.9 * bass + 0.3 * fl) - st[0]) * min(1.0, dt / 0.06)
            a = min(1.0, dt * 12)
            out = []
            for i in range(n):
                st[1][i] += (rnd.uniform(0.5, 1.0) - st[1][i]) * a
                h = 0.5 if n == 1 else 1 - (_ring_y(i, n, eff) + 1) / 2     # 0 = dole, 1 = nahore
                lit = max(0.0, min(1.0, (st[0] * st[1][i] - h) * 3 + 0.5)) if n > 1 else st[0]
                out.append(_scale(_gradient(cols, h), 0.03 + 0.97 * lit))
        elif styl in ("michani", "prutok"):               # barva okamziku smichana ze 3 barev palety
            c0 = cols[d % k]                              # basy, stredy, vysky = tri barvy palety
            c = band_mix((c0, cols[(d + 1) % k], cols[(d + 2) % k]),
                         (bass ** 1.5, (mid * (1 - 0.5 * e)) ** 2 * 0.7, high ** 2 * 0.8))
            c = tuple(max(c0[j] * 0.03, c[j]) for j in range(3))
            if styl == "michani":                         # cely ventilator jednou barvou, uder ji zesvetli
                out = [_mix(c, white, 0.25 * fl * fl)] * n
            else:                                         # prutok: barva vstoupi vpredu a tece skrini dozadu,
                hist = self.state.get(("hudba_tok", key))     # na kruhu odspodu nahoru
                if hist is None:
                    hist = self.state[("hudba_tok", key)] = collections.deque(maxlen=160)
                hist.appendleft(c)
                step = max(dt, 1e-3)
                out = []
                for i in range(n):
                    h = 0.0 if n == 1 else 1 - (_ring_y(i, n, eff) + 1) / 2     # 0 = dole, 1 = nahore
                    age = max(0.0, min(1.0, pos)) * FLOW_CASE_S + h * FLOW_RING_S
                    out.append(hist[min(len(hist) - 1, int(age / step))])
        elif styl == "skakani":                           # kazdy uder rozsviti dalsi ventilator ve skrini
            idx, cnt = slot or (0, 1)
            cnt = max(1, cnt)
            st = self.state.setdefault(("hudba_skok", key), [0.0, 0])
            st[0] *= math.exp(-dt / 0.22)
            for bid, strength in self._new_beats(key, snap, 0.0, tag="hudba_skok_n"):
                if bid % cnt == idx % cnt:
                    st[0], st[1] = max(st[0], 0.55 + 0.45 * strength), bid
            c = _mix(cols[st[1] % k], white, 0.3 * st[0] ** 3)
            out = [tuple(max(main[j] * 0.03, c[j] * st[0]) for j in range(3))] * n
        elif styl == "metronom":                          # svetlo obehne kruh za jednu dobu, na uder je dole
            bpm = float(snap.get("bpm") or 0.0) or 120.0
            period = 60.0 / max(50.0, min(220.0, bpm))
            st = self.state.setdefault(("hudba_metro", key), [0.0, 0])
            st[0] += dt / period
            for _bid, _strength in new:                   # uder: faze na cele cislo (svetlo presne dole)
                st[0], st[1] = float(round(st[0])), st[1] + 1
            f = st[0] % 1.0
            c = cols[st[1] % k]
            tick = math.exp(-f * period / 0.12)           # zablesk na uder
            if n == 1:
                out = [tuple(max(main[j] * 0.03, c[j] * tick) for j in range(3))]
            else:
                head = math.pi / 2 + 2 * math.pi * f
                out = []
                for i in range(n):
                    back = ((head - _ring_angle(i, n, eff)) % (2 * math.pi)) / (2 * math.pi)   # jak daleko za hlavou
                    kk = max(max(0.0, 1 - back / 0.45) ** 2, 0.3 * tick)
                    out.append(_mix(_scale(c, max(0.03, kk)), white, 0.35 * tick * max(0.0, 1 - back * 6)))
        elif styl == "ton":                               # barva = ktere pasmo je prave nejsilnejsi (basy cervena ... vysky fialova)
            avg = sum(raw) / max(1, len(raw))             # pocitaji se jen pasma, ktera vycnivaji nad prumer -
            w = [max(0.0, v - avg) ** 2 for v in raw]     # jinak by barva zustavala uprostred (zelena)
            s = sum(w)
            st = self.state.setdefault(("hudba_ton", key), [0.0])
            if s > 1e-3:
                x = sum(i * v for i, v in enumerate(w)) / s / max(1, len(w) - 1)
                st[0] += (x - st[0]) * min(1.0, dt / 0.1)
            kk = min(1.0, 0.08 + 0.92 * max(level, bass, fl))
            out = [_scale(_hsv(st[0] * 0.78 + 0.04 * math.sin(2 * math.pi * (_ring_u(i, n) + ph))), kk)
                   for i in range(n)]
        elif styl == "bici":                              # kopak rozsviti spodek kruhu, virbl a cinely vrsek
            st = self.state.setdefault(("hudba_bici", key), [0.0, 0.0])
            st[0] *= math.exp(-dt / 0.16)
            st[1] *= math.exp(-dt / 0.09)
            for _bid, strength in new:
                st[0] = max(st[0], strength)
            for _hid, strength in self._new_beats(key, snap, lag, field="beats_hi", tag="hudba_cinel"):
                st[1] = max(st[1], strength)
            hat = _mix(acc, white, 0.35)
            bg = _scale(main, 0.03)
            if n == 1:
                out = [tuple(max(bg[j], main[j] * st[0], hat[j] * st[1] * 0.7) for j in range(3))]
            else:
                out = []
                for i in range(n):
                    h = 1 - (_ring_y(i, n, eff) + 1) / 2          # 0 = dole, 1 = nahore
                    low = max(0.0, min(1.0, (0.5 - h) * 4 + 0.5))    # podil spodni pulky (mekka hranice)
                    out.append(tuple(max(bg[j], main[j] * st[0] * low, hat[j] * st[1] * (1 - low))
                                     for j in range(3)))
        else:                                             # "pulz": basy = jas, uder = zablesk vlnou, vysky = jiskry
            kk = min(1.0, 0.10 - 0.04 * e + (0.55 + 0.2 * e) * bass + (0.6 + 0.4 * e) * fl)
            out = []
            rot = cols[d % k:] + cols[:d % k]             # drop posune paletu (hlavni barva = prvni)
            for i in range(n):                        # cela paleta po obvodu, otaci se se stredy
                c = _mix(_cyclic(rot, _ring_u(i, n) + ph), white, 0.3 * fl * fl)
                out.append(_scale(c, kk))
            if n > 1:
                st = self.state.setdefault(("hudba_jiskry", key), [])
                if len(st) != n:
                    st[:] = [[0.0, 0] for _ in range(n)]
                dec = math.exp(-dt / 0.09)
                spark = _mix(acc, white, 0.45)
                for i, s in enumerate(st):
                    s[0] *= dec
                    if rnd.random() < dt * 10 * high ** 2.5:
                        s[0] = 1.0
                    if s[0] > 0.02:
                        out[i] = tuple(max(out[i][j], spark[j] * s[0]) for j in range(3))
        return [_scale(c, jas) for c in out]

    def _new_beats(self, key, snap, lag, field="beats", tag="hudba_uder"):
        """Udery, ktere k cili prave dorazily (s vlnou o lag s pozdeji): [(poradi, sila)].
        field "beats_hi" = virbl / cinely (hudba.Analyzer), tag = vlastni pocitadlo (styl si udery bere sam)."""
        st = self.state.setdefault((tag, key), [0])
        beats = [b for b in snap.get(field, ()) if len(b) > 2]
        if beats and max(b[2] for b in beats) < st[0] - 5:   # analyza zacala znovu (nova skladba / restart)
            st[0] = 0
        out = []
        for age, strength, bid in beats:
            if age >= lag and bid > st[0]:
                out.append((bid, strength))
        if out:
            st[0] = max(b for b, _s in out)
        return out


MUSIC_STYLES = {
    "pulz": "pulz s vlnou",
    "spektrum": "spektrum po skříni",
    "ekvalizer": "ekvalizér na kruhu",
    "komety": "komety do rytmu",
    "jiskry": "jiskry do rytmu",
    "klidny": "klidné vlnění",
    "zablesky": "záblesky na údery",
    "vlny": "vlny od kopáku",
    "vu": "ukazatel hlasitosti",
    "stridani": "barvy do rytmu",
    "rotace": "točení do rytmu",
    "plameny": "plameny z basů",
    "prutok": "průtok hudby skříní",
    "skakani": "skákání po skříni",
    "metronom": "metronom",
    "ton": "barva podle tónu",
    "michani": "míchání pásem",
    "bici": "kopák dole, činely nahoře",
}
MUSIC_WAVE_S = 0.25          # za jak dlouho uder probehne celou skrini (pri vlne)
DROP_WAVE_S = 0.3            # duraz na drop: za jak dlouho bily zablesk probehne skrini
FLOW_CASE_S, FLOW_RING_S = 0.55, 0.22       # prutok: za jak dlouho barva protece skrini / vystoupa po kruhu
MUSIC_FPS = 50               # snimky za sekundu, kdyz hraje hudba (jinak FPS)
_style_seq = {}              # (vyber stylu) -> [styl pro skladbu 0, 1, 2...] - nahodne bez opakovani


def style_pool(eff):
    """Styly, ze kterych se pri "stridat" nahodne vybira (vybrane uzivatelem, jinak vsechny)."""
    pool = [s for s in (eff.get("styly_stridat") or []) if s in MUSIC_STYLES]
    return pool or list(MUSIC_STYLES)


def music_style(eff, snap):
    """Styl vizualizeru; "stridat" = s kazdou skladbou nahodne jiny ze zvolenych stylu (styly_stridat),
    dvakrat po sobe stejny ne. Poradi je pevne dane cislem skladby - vsechny ventilatory i nahled se shodnou."""
    if not eff.get("stridat"):
        styl = eff.get("styl", "pulz")
        return styl if styl in MUSIC_STYLES else "pulz"
    pool = style_pool(eff)
    tn = max(0, int(snap.get("track_n", 0)))
    seq = _style_seq.setdefault(tuple(pool), [])
    if len(seq) > 5000:
        seq.clear()
    rng = random.Random(len(pool) * 7919)
    while len(seq) <= tn:
        i = len(seq)
        rng.seed(i * 7919 + len(pool))
        choice = rng.choice(pool)
        if len(pool) > 1 and seq and choice == seq[-1]:
            choice = rng.choice([s for s in pool if s != seq[-1]])
        seq.append(choice)
    return seq[tn]


def band_mix(colors, weights):
    """Barva okamziku ze tri barev (basy, stredy, vysky) a jejich sil 0..1: prevazi barva nejsilnejsiho
    pasma (podily z tretich mocnin - prosty prumer barev by byl bledy), jas = nejsilnejsi pasmo."""
    p = [max(0.0, w) ** 3 for w in weights]
    s = sum(p)
    if s <= 1e-9:
        return (0.0, 0.0, 0.0)
    top = min(1.0, max(weights))
    return tuple(sum(c[j] * q for c, q in zip(colors, p)) / s * top for j in range(3))


def bass_emphasis(eff):
    """Duraz na basy 0..1 z nastaveni "basy" 0-10 (vychozi 7)."""
    try:
        return max(0.0, min(1.0, float(eff.get("basy", 7)) / 10.0))
    except (TypeError, ValueError):
        return 0.7


def _contrast(v, e):
    """Kontrast urovne podle durazu na basy: pod prahem tma, nad nim strme nahoru."""
    if e <= 0:
        return v
    lo = 0.1 + 0.35 * e
    return max(0.0, min(1.0, (v - lo) / (1 - lo))) ** (1 + 1.5 * e)


def _band_at(bands, x):
    """Uroven pasma na (necele) pozici x - prumer okoli, at sousedni ventilatory neskacou."""
    if not bands:
        return 0.0
    lo, hi = max(0, int(math.floor(x - 1))), min(len(bands) - 1, int(math.ceil(x + 1)))
    vals = bands[lo:hi + 1]
    return max(0.0, min(1.0, sum(vals) / len(vals)))


def music_gamma(sens):
    """Citlivost na hudbu 1-10 -> gama urovni (vyssi citlivost = vyraznejsi reakce na tissi zvuk).
    Spolecna pro ventilatory (hudba.Analyzer) i efekty klavesnice (klavesnice_efekty.Levels)."""
    return 1.6 - 0.1 * max(1.0, min(10.0, float(sens)))


def beat_ratio(sens):
    """Citlivost na hudbu 1-10 -> prah uderu (energie basu vuci prumeru posledni sekundy)."""
    return 1.7 - 0.05 * max(1.0, min(10.0, float(sens)))


def music_demo(t, paleta=None, track_n=0):
    """Simulovana hudba pro nahled v okne (120 uderu za minutu, hi-hat mezi udery, drop kazdych 16 s)."""
    period = 0.5
    cur = math.floor(t / period)
    beats = []
    for j in range(3, -1, -1):
        bid = cur - j
        if bid >= 0:
            beats.append((t - bid * period, 1.0 if bid % 4 == 0 else 0.7, bid + 1))
    hats = []                                             # virbl / cinely mezi udery
    hcur = math.floor(t / period - 0.5)
    for j in range(3, -1, -1):
        hid = hcur - j
        if hid >= 0:
            hats.append((t - (hid + 0.5) * period, 0.8, hid + 1))
    age = t - cur * period
    bass = 0.1 + 0.85 * math.exp(-age / 0.15)
    high = 0.85 * math.exp(-((t - period / 2) % period) / 0.05)
    mid = 0.45 + 0.25 * math.sin(t * 0.7)
    bands = []
    for b in range(16):
        x = b / 15
        v = bass * (1 - x) ** 2 + mid * math.exp(-((x - 0.5) / 0.25) ** 2) + high * x * x
        bands.append(max(0.0, min(1.0, v * 0.9 + 0.08 * math.sin(t * 3 + b))))
    return {"bass": bass, "mid": mid, "high": high, "level": 0.6 + 0.2 * math.sin(t * 0.3), "bands": bands,
            "beats": beats, "beats_hi": hats, "beat_n": cur + 1, "drop_n": int(t // 16), "phase": t * 0.3,
            "bpm": 120.0,
            "quiet": False, "paleta": list(paleta or DEFAULT_PALETTE[:3]), "track_n": track_n, "mix": 1.0}


def bottom_led(n):
    """Pozice (0..n-1), ktera je pri otoceni 0 presne dole: ctvrt otacky za LED 1 (LED 1 vpravo,
    po smeru hodin). Kdyz n neni delitelne 4 (14 LED na desce), spodek by vysel mezi dve LED -
    bere se blizsi LED, at efekty sedi s testem natoceni (led.test_frame sviti prave na ni)."""
    return round(n / 4) % max(1, n)


def _ring_shift(n):
    """O kolik LED je kruh pootoceny, aby LED bottom_led(n) byla presne dole (0 pro 8 / 12 / 16 LED,
    0,5 pro 14 LED)."""
    return bottom_led(n) - n / 4 if n > 1 else 0.0


def _ring_u(i, n):
    """Poloha LED i na kruhu 0..1 (0 = vpravo, po smeru hodin) - stejna pro vsechny ventilatory bez
    ohledu na pocet LED, at efekty sedi s testem natoceni."""
    return (i - _ring_shift(n)) / n if n > 1 else 0.0


def _ring_angle(i, n, eff):
    """Uhel LED i na kruhu (0 = vpravo, po smeru hodin, rad), LED bottom_led(n) presne dole (pi/2);
    "otoceni" efektu otoci svisle efekty po 90 stupnich."""
    try:
        rot = math.radians(float(eff.get("otoceni", 0)))
    except (TypeError, ValueError):
        rot = 0.0
    return 2 * math.pi * _ring_u(i, n) + rot


def _ring_y(i, n, eff):
    """Svisla poloha LED i na kruhu (-1 nahore, +1 dole). LED 1 vpravo, cislovani po smeru hodin
    (jako v nahledu)."""
    return math.sin(_ring_angle(i, n, eff))


def apply_brightness(colors, percent):
    """Jas 0-100 % -> vnimany jas (kvadraticky), vystup cela cisla 0-255."""
    k = max(0.0, min(1.0, percent / 100.0)) ** 2
    return [[int(round(max(0, min(255, c[j] * k)))) for j in range(3)] for c in colors]
