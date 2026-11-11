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

import collections
import colorsys
import math
import random
import time

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
    "plazma": ("plazma", "klidne", ("barvy", "duha", "rychlost", "sirka"), (2, 8),
               {"barvy": ["#ff0080", "#7a00ff", "#00e5ff"], "sirka": 5, "duha": False}),
    "polarni_zare": ("polární záře", "klidne", ("barvy", "pozadi", "rychlost", "sirka"), (2, 8),
                     {"barvy": ["#00ff80", "#00e5ff", "#7a00ff"], "pozadi": "#000408", "sirka": 5}),
    "lava": ("lávová lampa", "klidne", ("barvy", "pozadi", "rychlost", "sirka"), (2, 6),
             {"barvy": ["#ff0040", "#ff8000", "#b000ff"], "pozadi": "#080008", "sirka": 5}),
    "odlesk": ("odlesk", "klidne", ("barvy", "smer", "rychlost", "sirka"), (1, 4),
               {"barvy": ["#0040ff", "#00a0ff"], "smer": 0, "sirka": 4}),
    "konfety": ("konfety", "klidne", ("barvy", "duha", "rychlost"), (2, 8),
                {"barvy": ["#ff0040", "#ffb000", "#00ff40", "#00a0ff", "#b000ff"], "duha": True}),
    "vlna": ("vlna", "pohyb", ("barvy", "duha", "smer", "tvar", "rychlost", "sirka", "opacne"), (2, 8),
             {"duha": True, "smer": 0, "sirka": 6, "tvar": "rovna"}),
    "kruh": ("kruhová vlna od středu", "pohyb", ("barvy", "duha", "stred", "rychlost", "sirka", "opacne"), (2, 8),
             {"duha": True, "sirka": 4, "stred": ""}),
    "toceni": ("točení kolem středu", "pohyb", ("barvy", "duha", "stred", "rychlost", "sirka", "opacne"), (2, 8),
               {"duha": True, "sirka": 3, "stred": ""}),
    "radar": ("radar", "pohyb", ("barvy", "pozadi", "stred", "rychlost", "sirka", "opacne"), (2, 2),
              {"barvy": ["#00ff40", "#ffffff"], "pozadi": "#000800", "sirka": 6, "stred": ""}),
    "paprsky_kriz": ("křížící se paprsky", "pohyb", ("barvy", "pozadi", "rychlost", "sirka"), (2, 2),
                     {"barvy": ["#ff0040", "#00a0ff"], "pozadi": "#000000", "sirka": 3}),
    "pruhy": ("posuvné pruhy", "pohyb", ("barvy", "duha", "rychlost", "sirka"), (2, 8),
              {"barvy": ["#ff0040", "#00a0ff", "#40ff00"], "sirka": 4}),
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
    "bourka": ("bouřka", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (2, 2),
               {"barvy": ["#ffffff", "#0040ff"], "pozadi": "#000008", "sirka": 5}),
    "had": ("had", "hry", ("barvy", "pozadi", "rychlost"), (3, 3),
            {"barvy": ["#60ff00", "#006010", "#ff0040"], "pozadi": "#000400"}),
    "zivot": ("hra života", "hry", ("barvy", "pozadi", "rychlost"), (1, 4),
              {"barvy": ["#00ff80", "#00a0ff", "#7a00ff"], "pozadi": "#000008"}),
    "cihly": ("rozbíjení cihel", "hry", ("barvy", "pozadi", "rychlost"), (3, 6),
              {"barvy": ["#ffffff", "#ff0040", "#ffb000", "#00ff40", "#00a0ff"], "pozadi": "#000000"}),
    "tenis": ("tenis", "hry", ("barvy", "pozadi", "rychlost"), (3, 3),
              {"barvy": ["#ff0040", "#00a0ff", "#ffffff"], "pozadi": "#000000"}),
    "hvezdy": ("hvězdná obloha", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 4),
               {"barvy": ["#ffffff", "#80a0ff"], "pozadi": "#000004", "sirka": 5}),
    "snezeni": ("sněžení", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 2),
                {"barvy": ["#ffffff", "#a0d0ff"], "pozadi": "#000010", "sirka": 5}),
    "kruhy_voda": ("kruhy na vodě", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 6),
                   {"barvy": ["#00a0ff", "#00ffc0", "#ffffff"], "pozadi": "#000818", "sirka": 5}),
    "svetlusky": ("světlušky", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 4),
                  {"barvy": ["#c0ff00", "#ffd000"], "pozadi": "#000400", "sirka": 5}),
    "prskavka": ("prskavka", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (2, 2),
                 {"barvy": ["#ffffff", "#ffb000"], "pozadi": "#000000", "sirka": 5}),
    "meteory": ("meteorický roj", "castice", ("barvy", "pozadi", "rychlost", "sirka"), (1, 4),
                {"barvy": ["#ffd080", "#ff6000"], "pozadi": "#000004", "sirka": 5}),
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
    "spektrogram": ("spektrogram", "hudba", ("barvy", "barvy_hudba", "pozadi", "rychlost", "citlivost"), (2, 4),
                    {"barvy": ["#0030ff", "#ff0080", "#ffd000"], "barvy_hudba": "vlastni", "pozadi": "#000000"}),
    "dj": ("DJ světlo", "hudba", ("barvy", "barvy_hudba", "pozadi", "rychlost", "citlivost", "opacne"), (3, 3),
           {"barvy": ["#ff0040", "#00ff40", "#0060ff"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "ohnostroj_hudba": ("ohňostroj do rytmu", "hudba", ("barvy", "barvy_hudba", "pozadi", "sirka", "citlivost"),
                        (1, 8), {"barvy": ["#ff0040", "#ffb000", "#00a0ff", "#40ff00"], "barvy_hudba": "obal",
                                 "pozadi": "#000000", "sirka": 5}),
    "zaznam": ("záznam hlasitosti", "hudba", ("barvy", "barvy_hudba", "pozadi", "rychlost", "citlivost", "opacne"),
               (2, 4), {"barvy": ["#00e5ff", "#7a00ff", "#ff0080"], "barvy_hudba": "vlastni", "pozadi": "#000000"}),
    "plazma_hudba": ("plazma do hudby", "hudba", ("barvy", "barvy_hudba", "rychlost", "sirka", "citlivost"), (2, 8),
                     {"barvy": ["#ff0080", "#7a00ff", "#00e5ff"], "barvy_hudba": "obal", "sirka": 5}),
    "kostky": ("padající kostky do rytmu", "hudba", ("barvy", "barvy_hudba", "pozadi", "sirka", "citlivost"),
               (2, 8), {"barvy": ["#ff0040", "#ffb000", "#00a0ff", "#40ff00", "#b000ff"], "barvy_hudba": "obal",
                        "pozadi": "#000000", "sirka": 5}),
    "bici_automat": ("bicí automat", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost"), (3, 3),
                     {"barvy": ["#ff0040", "#ffb000", "#00e5ff"], "barvy_hudba": "vlastni", "pozadi": "#000000"}),
    "hvezdny_let": ("hvězdný let", "hudba", ("barvy", "barvy_hudba", "pozadi", "sirka", "citlivost"), (1, 6),
                    {"barvy": ["#ffffff", "#80c0ff"], "barvy_hudba": "vlastni", "pozadi": "#000000", "sirka": 5}),
    "stoupani": ("stoupání k dropu", "hudba", ("barvy", "barvy_hudba", "pozadi", "citlivost"), (2, 8),
                 {"barvy": ["#ff0080", "#7a00ff", "#00e5ff"], "barvy_hudba": "obal", "pozadi": "#000000"}),
    "kruhove_spektrum": ("kruhové spektrum", "hudba", ("barvy", "barvy_hudba", "pozadi", "stred", "rychlost",
                                                        "citlivost"), (2, 4),
                         {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "barvy_hudba": "vlastni", "pozadi": "#000000",
                          "stred": ""}),
    "glitch": ("porucha (glitch)", "hudba", ("barvy", "barvy_hudba", "rychlost", "citlivost"), (2, 8),
               {"barvy": ["#ff0080", "#00e5ff", "#7a00ff"], "barvy_hudba": "obal"}),
    "nalada": ("nálada skladby", "hudba", ("barvy", "barvy_hudba", "rychlost", "sirka", "citlivost"), (2, 8),
               {"barvy": ["#0030ff", "#00e5ff", "#b000ff", "#ff0080", "#ff6000"], "barvy_hudba": "vlastni",
                "sirka": 5}),
    "teplotni_mapa": ("teplotní mapa psaní", "senzor", ("barvy", "pozadi", "rychlost", "sirka"), (2, 6),
                      {"barvy": ["#0030ff", "#00ff40", "#ffd000", "#ff0000"], "pozadi": "#000008", "sirka": 3}),
    "teplota": ("barva podle senzoru", "senzor", ("barvy", "senzor"), (2, 8),
                {"barvy": ["#0060ff", "#00ff40", "#ffb000", "#ff0000"], "senzor": "CPU (Tctl/Tdie)",
                 "min": 40, "max": 90}),
    "ukazatel": ("ukazatel na řadě kláves", "senzor", ("barvy", "pozadi", "senzor", "rada"), (1, 8),
                 {"barvy": ["#00ff40", "#ffd000", "#ff0000"], "pozadi": "#000818", "senzor": "CPU (Tctl/Tdie)",
                  "min": 40, "max": 90, "rada": "cisla"}),
}
GROUPS = [("klidne", "Klidné"), ("pohyb", "Pohyb"), ("castice", "Částice"), ("hry", "Hry"), ("hudba", "Hudba"),
          ("senzor", "Senzor a psaní")]
STATIC = {"barva", "prechod", "vlastni"}               # bez animace (jen pri zmene / reakci na stisk)
KEY_EFFECTS = ("teplotni_mapa", "zivot")               # potrebuji stisky klaves (hook Windows)
ALIASES = {"tetris": "kostky"}                         # prejmenovane efekty (starsi nastaveni)
DEFAULT_EFFECT = {"typ": "vlna", "rychlost": 5, "smer": 0, "sirka": 6, "duha": True, "opacne": False,
                  "barvy": DEFAULT_PALETTE[:3], "pozadi": "#000000", "citlivost": 5, "citlivost_vlastni": False,
                  "spicka": True, "tvar": "rovna", "stred": "", "posun_barev": 0}
DIRECTIONS = [(0, "→"), (45, "↘"), (90, "↓"), (135, "↙"), (180, "←"), (225, "↖"), (270, "↑"), (315, "↗")]
# tvar vlny ("tvar"): rovna cara / sipka (spicka ve smeru pohybu) / kosoctverec (od stredu, smer se nepouzije)
SHAPES = [("rovna", "rovná"), ("sipka", "šipka"), ("kosoctverec", "kosočtverec")]
# stred kruhu / toceni / radaru ("stred"): "" = stred klavesnice (casti), jinak zona klavesy (i vybrana klikem)
CENTERS = [("", "střed klávesnice"), ("19", "WASD"), ("41", "mezerník"), ("38", "Esc – levý horní roh"),
           ("78", "šipky"), ("90", "numerická klávesnice"), ("210", "logo")]
REACTIONS = [("klavesa", "klávesa"), ("vlnka", "vlnka"), ("zare", "záře okolí"), ("kriz", "kříž"),
             ("paprsky", "paprsky"), ("jiskry", "jiskry"), ("plaminek", "plamínek"), ("inkoust", "inkoust")]
REACTION_DEFAULT = {"zapnuto": False, "rezim": "vlnka", "barva": "#ffffff", "doba": 1.0}
OLD_REACTION_KEYS = ("reakce", "reakce_barva", "reakce_doba")
# psani pohani efekt (config["led"]["psani_klavesnice"]): cim rychleji se pise, tim rychlejsi a jasnejsi
# efekt klavesnice; "sila" 1-10 = jak malo psani staci na plny jas
TYPING_DEFAULT = {"zapnuto": False, "sila": 5}
# sporic (config["led"]["sporic_klavesnice"]): po "minuty" bez vstupu (klavesnice i mys - GetLastInputInfo)
# klavesnice ztmavne na "jas" %, vstup ji probudi vlnou od stisknute klavesy
SAVER_DEFAULT = {"zapnuto": False, "minuty": 5, "jas": 10}
SAVER_FADE_S = 3.0           # jak dlouho klavesnice usina
WAKE_SPEED = 30.0            # vlna probuzeni (u za sekundu)


def _settings(lcfg, key, default):
    v = (lcfg or {}).get(key)
    v = v if isinstance(v, dict) else {}
    return {k: v.get(k, d) for k, d in default.items()}


def reaction_settings(lcfg):
    """Nastaveni reakce na stisk s vychozimi hodnotami (cteni)."""
    return _settings(lcfg, "reakce_klavesnice", REACTION_DEFAULT)


def typing_settings(lcfg):
    return _settings(lcfg, "psani_klavesnice", TYPING_DEFAULT)


def saver_settings(lcfg):
    return _settings(lcfg, "sporic_klavesnice", SAVER_DEFAULT)


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
    return eff.get("typ") not in STATIC or fx.hue_drift(eff) > 0


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


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
        self.my = my
        self.kw = [k[4] for k in keys]                                # sirka / vyska klaves (u)
        self.kh = [k[5] for k in keys]
        # sloupce, ktere klavesa zakryva (mezernik jich ma vic) - pro efekty v mrizce (padajici kostky)
        self.key_cols = [[c for c, x in enumerate(self.cols) if abs(x - cx) <= max(0.5, w / 2)] or [self.col_of[i]]
                         for i, (cx, w) in enumerate(zip(self.cx, self.kw))]
        self._proj = {}
        self._polar = {}
        self._nb = None

    def proj(self, eff):
        """Poloha kazde klavesy ve smeru efektu jako 0..1 (0 = kde smer zacina)."""
        d = int(get(eff, "smer") or 0) % 360
        if d not in self._proj:
            a = math.radians(d)
            v = [x * math.cos(a) + y * math.sin(a) for x, y in zip(self.cx, self.cy)]
            lo, hi = min(v, default=0.0), max(v, default=1.0)
            self._proj[d] = [(p - lo) / (hi - lo or 1) for p in v]
        return self._proj[d]

    def shape(self, eff):
        """Jako proj(), ale podle tvaru vlny ("tvar"): sipka = spicka vpredu ve smeru pohybu,
        kosoctverec = od stredu ven (smer se nepouzije)."""
        tvar = get(eff, "tvar") or "rovna"
        if tvar not in ("sipka", "kosoctverec"):
            return self.proj(eff)
        d = int(get(eff, "smer") or 0) % 360
        key = (tvar, d if tvar == "sipka" else 0)
        if key not in self._proj:
            a = math.radians(d)
            ca, sa = math.cos(a), math.sin(a)
            if tvar == "sipka":
                v = [(x - self.mx) * ca + (y - self.my) * sa + abs((y - self.my) * ca - (x - self.mx) * sa)
                     for x, y in zip(self.cx, self.cy)]
            else:
                v = [abs(x - self.mx) + abs(y - self.my) * 2.0 for x, y in zip(self.cx, self.cy)]
            lo, hi = min(v, default=0.0), max(v, default=1.0)
            self._proj[key] = [(p - lo) / (hi - lo or 1) for p in v]
        return self._proj[key]

    def polar(self, eff):
        """(vzdalenost, uhel jako podil otacky) kazde klavesy od stredu efektu: "stred" = zona klavesy,
        jinak (nebo kdyz klavesa v teto casti neni) stred klavesnice / casti."""
        try:
            i = self.index.get(int(get(eff, "stred")))
        except (TypeError, ValueError):
            i = None
        if i is None:
            return self.dist, self.ang
        if i not in self._polar:
            px, py = self.cx[i], self.cy[i]
            self._polar[i] = ([math.hypot(x - px, y - py) for x, y in zip(self.cx, self.cy)],
                              [math.atan2(y - py, x - px) / (2 * math.pi) for x, y in zip(self.cx, self.cy)])
        return self._polar[i]

    def neighbors(self):
        """Sousedni klavesy kazde klavesy (dotykaji se hranou, mezera nejvys 0,6 u) - had."""
        if self._nb is None:
            nb = []
            for i in range(self.n):
                out = []
                for j in range(self.n):
                    if j == i:
                        continue
                    gx = abs(self.cx[j] - self.cx[i]) - (self.kw[i] + self.kw[j]) / 2    # mezera vodorovne
                    gy = abs(self.cy[j] - self.cy[i]) - (self.kh[i] + self.kh[j]) / 2    # mezera svisle
                    if (gx < 0.6 and gy < -0.3) or (gy < 0.6 and gx < -0.3):
                        out.append(j)
                nb.append(out)
            self._nb = nb
        return self._nb


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
        self.typed = collections.deque(maxlen=512)   # (poradi stisku, index klavesy, cas) - mapa, psani, sporic

    def press(self, zone):
        for e in self.parts.values():           # casti klavesnice dostanou stisk taky (mapa, hra zivota)
            e.press(zone)
        i = self.g.index.get(zone)
        if i is not None:
            self._n_press += 1
            self.presses.append((i, self.rclock, (self._n_press * 0.13) % 1.0))
            del self.presses[:-64]
            self.typed.append((self._n_press, i, time.monotonic()))

    def new_presses(self, key):
        """Klavesy (indexy) stisknute od minuleho volani s timto klicem."""
        last = self.state.get(key)
        self.state[key] = self._n_press
        if last is None:
            return []
        return [i for n, i, _t in self.typed if n > last]

    def typing_rate(self, window=2.0):
        """Stisku za sekundu za poslednich window sekund."""
        now = time.monotonic()
        return sum(1 for _n, _i, t in self.typed if now - t < window) / window

    def drive(self, ts, dt):
        """Psani pohani efekt: 0 (nepise se) .. 1 (pise se rychle), nabeh 0,3 s, dobeh 2 s."""
        try:
            full = max(1.0, 12.0 - float(ts.get("sila", 5)))       # stisku/s pro plny jas (sila 5 -> 7/s)
        except (TypeError, ValueError):
            full = 7.0
        target = min(1.0, self.typing_rate() / full)
        d = self.state.get("_drive", 0.0)
        d += (target - d) * min(1.0, dt / (0.3 if target > d else 2.0))
        self.state["_drive"] = d
        return d

    def saver(self, sv, cols, idle, dt):
        """Sporic: po sv["minuty"] bez vstupu (idle s, None = nevi se / nahled) klavesnice ztmavne na sv["jas"] %,
        prvni vstup ji probudi vlnou od stisknute klavesy (bez stisku od stredu)."""
        st = self.state.setdefault("_saver", {"s": 0.0, "wake": None})
        if idle is None:
            st["s"], st["wake"] = 0.0, None
            return cols
        try:
            limit = max(0.5, float(sv.get("minuty", 5))) * 60.0
            floor = max(0.0, min(1.0, float(sv.get("jas", 10)) / 100.0))
        except (TypeError, ValueError):
            limit, floor = 300.0, 0.1
        g = self.g
        if idle >= limit:
            st["wake"] = None
            st["s"] = min(1.0, st["s"] + dt / SAVER_FADE_S)
        elif st["s"] > 0 and st["wake"] is None:
            now = time.monotonic()
            last = self.typed[-1] if self.typed and now - self.typed[-1][2] < 1.5 else None
            st["wake"] = [g.cx[last[1]], g.cy[last[1]], 0.0] if last else [g.mx, g.my, 0.0]
        if st["wake"] is not None:
            st["wake"][2] += dt * WAKE_SPEED
            if st["wake"][2] > (g.x1 - g.x0) + 4:
                st["s"], st["wake"] = 0.0, None
        if st["s"] <= 0:
            return cols
        out = []
        for i, c in enumerate(cols):
            f = floor
            if st["wake"] is not None:
                wx, wy, r = st["wake"]
                d = math.hypot(g.cx[i] - wx, (g.cy[i] - wy) * 1.3)
                f = floor + (1 - floor) * max(0.0, min(1.0, (r - d) / 2.0))
                if 0 < r - d < 1.5:                     # svetly okraj vlny
                    c = _mix(c, (255.0, 255.0, 255.0), 0.5 * (1 - (r - d) / 1.5))
            f = 1 - st["s"] * (1 - f)
            out.append((c[0] * f, c[1] * f, c[2] * f))
        return out

    def saver_state(self):
        """(usnula, prave usina / se probouzi)."""
        st = self.state.get("_saver") or {}
        s = st.get("s", 0.0)
        return s >= 1.0 and st.get("wake") is None, (0.0 < s < 1.0) or st.get("wake") is not None

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
        hd = fx.hue_drift(eff)
        if hd and typ != "vlastni":                  # pomaly posun barev
            cols = fx.hue_rotate(cols, self.clock * hd / fx.HUE_DRIFT_S)
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
        s = t * self._speed(eff, 0.25) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, v / w - s) for v in self.g.shape(eff)]

    def _kruh(self, eff, t, dt, data, music):
        w = self._width(eff) * 2.0                          # delka vlny v u
        s = t * self._speed(eff, 0.35) * (-1 if get(eff, "opacne") else 1)
        return [self._wave_color(eff, d / w - s) for d in self.g.polar(eff)[0]]

    def _toceni(self, eff, t, dt, data, music):
        twist = (self._width(eff) - 1) / 30.0               # spirala: posun podle vzdalenosti
        s = t * self._speed(eff, 0.2) * (-1 if get(eff, "opacne") else 1)
        dist, ang = self.g.polar(eff)
        return [self._wave_color(eff, a + d * twist - s) for a, d in zip(ang, dist)]

    def _radar(self, eff, t, dt, data, music):
        """Paprsek s dohasinajici stopou obiha stred; nahodne cile se rozsviti, kdyz je prejede."""
        pal, bg = self._pal(eff), self._bg(eff)
        beam, blip = pal[0], pal[-1]
        sign = -1 if get(eff, "opacne") else 1
        rate = self._speed(eff, 0.25)                       # otacky za sekundu
        st = self.state.setdefault("radar", {"a": 0.0, "cile": []})
        st["a"] = (st["a"] + rate * dt) % 1.0
        trail = 0.08 + self._width(eff) * 0.05              # delka stopy jako podil otacky
        dist, ang = self.g.polar(eff)
        near = max(0.03, rate * dt * 2)
        if len(st["cile"]) < 4 and self.rng.random() < dt * 0.6:
            st["cile"].append([self.rng.randrange(self.g.n), None])
        behind = [((st["a"] - a * sign) % 1.0) for a in ang]     # jak daleko za paprskem klavesa je
        out = []
        for i in range(self.g.n):
            k = max(0.0, 1 - behind[i] / trail) ** 2
            if dist[i] < 0.6:
                k = max(k, 0.5)                             # stred sviti porad
            out.append(_mix(bg, beam, k))
        for c in st["cile"]:
            if c[1] is None and behind[c[0]] < near:
                c[1] = t
            if c[1] is not None:
                out[c[0]] = _mix(out[c[0]], blip, max(0.0, 1 - (t - c[1]) / 1.8) ** 0.7)
        st["cile"] = [c for c in st["cile"] if c[1] is None or t - c[1] < 1.8]
        return out

    # -------------------------------------------------------------- plazma, polarni zare
    def _plasma(self, ph, sc):
        """Plazma -1..1 pro kazdou klavesu (soucet vln ve vice smerech)."""
        g = self.g
        return [(math.sin(x * sc + ph) + math.sin(y * sc * 1.7 - ph * 0.8) + math.sin((x + y) * sc * 0.6 + ph * 0.5)
                 + math.sin(math.hypot(x - g.mx, y - g.y1) * sc * 1.3 - ph * 1.1)) / 4 for x, y in zip(g.cx, g.cy)]

    def _plazma(self, eff, t, dt, data, music):
        ph = t * self._speed(eff, 0.9)
        amp = 0.35 if get(eff, "duha") else 0.5             # duha: jen cast odstinu naraz, at neni pestra
        return [self._wave_color(eff, 0.5 + amp * v + ph * 0.04) for v in self._plasma(ph, 1.6 / self._width(eff))]

    def _polarni_zare(self, eff, t, dt, data, music):
        """Zavesy svetla visi shora, vlni se a pomalu meni barvu."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        ph = t * self._speed(eff, 0.5)
        sc = 2.5 / self._width(eff)                         # sirka 5 -> zavesy pres ~12 u
        hh = (g.y1 - g.y0) or 1.0
        out = []
        for x, y in zip(g.cx, g.cy):
            fy = (g.y1 - y) / hh                            # 0 dole .. 1 nahore
            cur = 0.55 + 0.45 * math.sin(x * sc + ph * 1.3 + 2.0 * math.sin(x * sc * 0.35 + ph * 0.4))
            low = 0.35 + 0.3 * math.sin(x * sc * 0.6 - ph * 0.7)     # kam az zaves dosaha (0 = az dolu)
            k = cur * max(0.0, min(1.0, (fy - low) / 0.45 + 0.4))
            # barvy palety jdou za sebou (bez navratu z posledni na prvni - ta by dala sedou)
            c = _gradient(pal, 0.5 + 0.4 * math.sin(x * sc * 0.25 + ph * 0.3) + (fy - 0.5) * 0.3)
            out.append(_mix(bg, c, k))
        return out

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

    def _bourka(self, eff, t, dt, data, music):
        """Tlumeny dest a obcas blesk: cela klavesnice blikne, klikata cara blesku sviti naplno."""
        pal, bg = self._pal(eff), self._bg(eff)
        flash_c, rain_c = pal[0], pal[-1]
        g = self.g
        st = self.state.setdefault("bourka", {"kapky": [], "t": -9.0, "t2": -9.0, "x": {}})
        sp = self._speed(eff)
        for c in range(len(g.cols)):                        # dest: [sloupec, y, rychlost]
            if self.rng.random() < self._width(eff) * 0.012 * dt * FPS / 3:
                st["kapky"].append([c, g.y0 - 0.5, 5.0 + self.rng.random() * 5.0])
        for d in st["kapky"]:
            d[1] += d[2] * dt
        st["kapky"] = [d for d in st["kapky"] if d[1] < g.y1 + 3]
        if t - st["t"] > 1.2 and self.rng.random() < dt * 0.14 * sp:     # blesk: klikata cara shora dolu
            st["t"], st["t2"] = t, t + self.rng.uniform(0.09, 0.2)
            x = self.rng.uniform(g.x0 + 1, g.x1 - 1)
            st["x"] = {}
            for r in range(g.nrows - 1, -1, -1):
                st["x"][r] = x
                x = max(g.x0, min(g.x1, x + self.rng.uniform(-1.6, 1.6)))
        k1 = math.exp(-(t - st["t"]) / 0.1) if t >= st["t"] else 0.0
        k2 = 0.7 * math.exp(-(t - st["t2"]) / 0.14) if t >= st["t2"] else 0.0
        fl = max(k1, k2)                                    # dvojity zablesk
        out = []
        for i in range(g.n):
            c, y = g.col_of[i], g.cy[i]
            k = 0.0
            for d in st["kapky"]:
                if d[0] == c and -0.5 <= d[1] - y < 1.8:
                    k = max(k, 0.55 * (1 - max(0.0, d[1] - y - 0.5) / 1.3))
            col = _mix(bg, rain_c, k)
            if fl > 0.01:
                bx = st["x"].get(g.row_of[i])
                near = max(0.0, 1 - abs(g.cx[i] - bx) / max(1.0, g.kw[i] / 2 + 0.4)) if bx is not None else 0.0
                col = _mix(col, flash_c, fl * (0.3 + 0.7 * near))
            out.append(col)
        return out

    # -------------------------------------------------------------- hry
    def _had(self, eff, t, dt, data, music):
        """Had leze po sousednich klavesach za potravou a roste; kdyz se zamota nebo je moc dlouhy,
        blikne a zacne znovu. Barvy: hlava, ocas, potrava."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        nb = g.neighbors()
        st = self.state.get("had")
        if st is None or st["n"] != g.n:
            st = self.state["had"] = {"n": g.n, "telo": [], "jidlo": 0, "acc": 0.0, "konec": None, "rust": 2}
        ok = [i for i in range(g.n) if nb[i]]               # klavesy, na ktere se da dostat
        if not ok:
            return [bg] * g.n

        def food():
            free = [i for i in ok if i not in st["telo"]]
            st["jidlo"] = self.rng.choice(free or ok)
        if not st["telo"]:
            st.update(telo=[self.rng.choice(ok)], rust=2, konec=None)
            food()
        if st["konec"] is not None and t - st["konec"] > 0.9:
            st["telo"] = []
            return [bg] * g.n
        st["acc"] += dt
        step = 0.2 / self._speed(eff)
        while st["acc"] >= step and st["konec"] is None:
            st["acc"] -= step
            head = st["telo"][0]
            free = [j for j in nb[head] if j not in st["telo"][:-1]]
            if not free or len(st["telo"]) > max(6, g.n * 0.4):
                st["konec"] = t
                break
            fx_, fy_ = g.cx[st["jidlo"]], g.cy[st["jidlo"]]
            nxt = min(free, key=lambda j: math.hypot(g.cx[j] - fx_, g.cy[j] - fy_) + self.rng.random() * 0.8)
            st["telo"].insert(0, nxt)
            if nxt == st["jidlo"]:
                st["rust"] += 2
                food()
            if st["rust"] > 0:
                st["rust"] -= 1
            else:
                st["telo"].pop()
        if st["konec"] is not None:
            st["acc"] = 0.0
        out = [bg] * g.n
        m = len(st["telo"])
        dead = st["konec"] is not None
        blink = (0.25 + 0.75 * (int((t - st["konec"]) * 8) % 2)) * (1 - (t - st["konec"]) / 0.9) if dead else 1.0
        for k, i in enumerate(st["telo"]):
            c = _mix(pal[0], pal[1], k / max(1, m - 1) if m > 1 else 0.0)
            if k == 0:
                c = _mix(c, (255, 255, 255), 0.35)
            out[i] = _mix(bg, _mix(c, (255, 40, 0), 0.6) if dead else c, blink)
        if not dead:
            out[st["jidlo"]] = _scale(pal[2], 0.6 + 0.4 * math.sin(t * 7))
        return out

    def _zivot(self, eff, t, dt, data, music):
        """Hra zivota na mrizce rada x sloupec (okraje navazuji); stisk klavesy prida bunky, kdyz
        obrazec vymre nebo se zacykli, zaseje se znovu. Barva podle stari bunky."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        rows, ncol = g.nrows, len(g.cols)
        st = self.state.get("zivot")
        if st is None or st["dim"] != (rows, ncol):
            st = self.state["zivot"] = {"dim": (rows, ncol), "ted": {}, "pred": {}, "acc": 0.0, "stale": 0,
                                        "videl": collections.deque(maxlen=8), "np": self._n_press}

        def seed():
            st["ted"] = {(r, c): 0 for r in range(rows) for c in range(ncol) if self.rng.random() < 0.35}
            st["stale"] = 0
            st["videl"].clear()
        if not st["ted"] and not st["pred"]:
            seed()
        if self._n_press != st["np"]:                       # stisky: bunka a jeji sousede oziji
            for i, _pt, _h in self.presses[-max(1, min(8, self._n_press - st["np"])):]:
                r, c = g.row_of[i], g.col_of[i]
                for dr, dc in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
                    st["ted"].setdefault(((r + dr) % rows, (c + dc) % ncol), 0)
            st["np"] = self._n_press
            st["stale"] = 0
        step = 0.6 / self._speed(eff)
        st["acc"] += dt
        while st["acc"] >= step:
            st["acc"] -= step
            cur = st["ted"]
            cnt = {}
            for (r, c) in cur:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr or dc:
                            p = ((r + dr) % rows, (c + dc) % ncol)
                            cnt[p] = cnt.get(p, 0) + 1
            new = {p: cur.get(p, -1) + 1 for p, k in cnt.items() if k == 3 or (k == 2 and p in cur)}
            st["pred"], st["ted"] = cur, new
            sig = hash(frozenset(new))
            st["stale"] = st["stale"] + 1 if (sig in st["videl"] or not new) else 0
            st["videl"].append(sig)
            if st["stale"] > 6 or len(new) < 3:             # vymrelo / stoji / kmita -> novy obrazec
                seed()
        f = st["acc"] / step
        f = min(1.0, f * 2)
        f = f * f * (3 - 2 * f)                             # prechod mezi generacemi v prvni pulce kroku
        out = []
        for i in range(g.n):
            p = (g.row_of[i], g.col_of[i])
            a, b = p in st["pred"], p in st["ted"]
            k = (1 - f) * a + f * b
            age = st["ted"].get(p, st["pred"].get(p, 0))
            out.append(_mix(bg, _gradient(pal, min(1.0, age / 5.0)), k) if k > 0 else bg)
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
        citlivost efektu ignoruje slabsi udery (od 11. 11. 2026 je sila uderu 0,3 + 0,7 x narust vuci
        nejsilnejsim nedavnym uderum - hudba.Analyzer._strength): projde uder se silou
        k >= (c' - c) / c + 0,5, kde c' a c jsou prahy vlastni a spolecne citlivosti (fx.beat_ratio).
        Vyssi vlastni citlivost udery navic nepridava."""
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

    def _spektrogram(self, eff, t, dt, data, music):
        """Spodni rada = spektrum ted (sloupce = pasma, barva a jas = sila), rady se posouvaji nahoru."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        live, _pk = self._meter("spektrogram_m", (lv["bands"] if lv else [0.0] * 16), dt)
        st = self.state.setdefault("spektrogram", {"hist": collections.deque(maxlen=12), "acc": 0.0})
        step = 0.16 / self._speed(eff)                      # jak dlouho trva jedna rada
        st["acc"] += dt
        while st["acc"] >= step:
            st["acc"] -= step
            st["hist"].appendleft(list(live))
        f = st["acc"] / step
        hist = st["hist"]
        g = self.g
        zero = [0.0] * 16
        out = []
        for i in range(g.n):
            r = g.row_of[i]                                 # 0 = dolni rada (nejnovejsi)
            b = min(15, max(0, int((g.cx[i] - g.x0) / ((g.x1 - g.x0) or 1) * 16)))
            old = hist[r][b] if r < len(hist) else 0.0
            new = live[b] if r == 0 else (hist[r - 1][b] if r - 1 < len(hist) else zero[b])
            v = old + (new - old) * f                       # plynuly posun mezi radami
            out.append(_mix(bg, _gradient(pal, v), min(1.0, v * 1.5)))
        return out

    def _band_color(self, pal, bg, lv):
        """Barva okamziku: basy / stredy / vysky = prvni tri barvy palety, smichane podle sily."""
        if not lv:
            return bg
        return _add(bg, fx.band_mix((pal[0], pal[1 % len(pal)], pal[2 % len(pal)]),
                                    (lv["bass"] ** 1.5, lv["mid"] ** 2 * 0.7, lv["high"] ** 2 * 0.8)))

    def _dj(self, eff, t, dt, data, music):
        """Barva okamziku vznika uprostred a tece do obou stran (opacne = od kraju ke stredu)."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        st = self.state.setdefault("dj", {"hist": collections.deque(maxlen=256), "acc": 0.0})
        c = self._band_color(pal, bg, self._lv(eff, music, dt))
        step = 1 / 40
        st["acc"] += dt
        while st["acc"] >= step:
            st["acc"] -= step
            st["hist"].appendleft(c)
        hist = st["hist"]
        if not hist:
            return [bg] * self.g.n
        g = self.g
        half = max(g.mx - g.x0, g.x1 - g.mx) or 1.0
        span = 1.1 / self._speed(eff) / step                # snimku historie od stredu ke kraji
        out = []
        for x in g.cx:
            u = min(1.0, abs(x - g.mx) / half)
            if get(eff, "opacne"):
                u = 1 - u
            out.append(hist[min(len(hist) - 1, int(u * span))])
        return out

    def _ohnostroj_hudba(self, eff, t, dt, data, music):
        """Kazdy uder = vybuch na nahodnem miste, velikost a jas podle sily uderu."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        bursts = self.state.setdefault("ohnostroj_hudba", [])     # [x, y, cas, barva, sila]
        hit = self._hit(eff, music, "ohnostroj_hudba_n")
        if hit:
            n = int(music.get("beat_n", 0))
            for j in range(1 + int(hit * self._width(eff) / 4)):
                i = self.rng.randrange(self.g.n)
                bursts.append([self.g.cx[i], self.g.cy[i], t, pal[(n + j) % len(pal)], hit])
        life = 1.1
        bursts[:] = [b for b in bursts if t - b[2] < life][-10:]
        out = []
        for x, y in zip(self.g.cx, self.g.cy):
            c = bg
            for bx, by, bt, bc, bs in bursts:
                age = (t - bt) / life
                r = age * 7.0 * (0.5 + 0.7 * bs)
                k = max(0.0, 1 - abs(math.hypot(x - bx, (y - by) * 1.2) - r) / 1.2) * (1 - age) ** 1.5 * (0.5 + 0.5 * bs)
                if age < 0.14 and math.hypot(x - bx, y - by) < 0.7:
                    k = 1.0                                   # zablesk ve stredu
                c = _add(c, _scale(bc, k))
            out.append(c)
        return out

    def _zaznam(self, eff, t, dt, data, music):
        """Prubeh hlasitosti bezi pres klavesnici (nove vpravo) jako zrcadlova krivka kolem prostredni rady."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        a = max(lv["bass"], lv["level"] ** 2 * 0.6) if lv else 0.0     # hlasitost je skoro porad vysoko
        st = self.state.setdefault("zaznam", {"hist": collections.deque(maxlen=512), "acc": 0.0, "pk": 0.0})
        st["pk"] = max(st["pk"], a)
        step = 1 / 30
        st["acc"] += dt
        while st["acc"] >= step:
            st["acc"] -= step
            st["hist"].appendleft(st["pk"])
            st["pk"] = a
        hist = st["hist"]
        g = self.g
        hh = (g.y1 - g.y0) / 2 or 1.0
        span = 2.2 / self._speed(eff) / step                # snimku historie pres celou klavesnici
        out = []
        for i in range(g.n):
            u = (g.x1 - g.cx[i]) / ((g.x1 - g.x0) or 1)     # 0 = vpravo (ted) .. 1 = vlevo
            if get(eff, "opacne"):
                u = 1 - u
            j = int(u * span)
            amp = hist[j] if j < len(hist) else 0.0
            dy = abs(g.cy[i] - g.my)
            k = max(0.0, min(1.0, amp * hh - dy + 0.5))
            if dy < 1.0:
                k = max(k, 0.12)                            # tenka cara uprostred i v tichu
            out.append(_mix(bg, _gradient(pal, dy / hh), k))
        return out

    def _plazma_hudba(self, eff, t, dt, data, music):
        """Klidna plazma: rychlost a jas podle hlasitosti, uder posune barvy."""
        pal = self._music_pal(eff, music)
        lv = self._lv(eff, music, dt)
        st = self.state.setdefault("plazma_hudba", {"ph": 0.0, "posun": 0.0, "cil": 0.0, "lev": 0.0})
        level = max(lv["level"] ** 1.5, lv["bass"]) if lv else 0.0
        st["lev"] += (level - st["lev"]) * min(1.0, dt / (0.08 if level > st["lev"] else 0.35))
        st["ph"] += dt * self._speed(eff, 0.3 + 1.5 * st["lev"])
        if self._hit(eff, music, "plazma_hudba_n"):
            st["cil"] += 0.5 / max(2, len(pal))
        st["posun"] += (st["cil"] - st["posun"]) * min(1.0, dt / 0.15)
        k = 0.22 + 0.78 * st["lev"]
        return [_scale(_cyclic(pal, 0.5 + 0.6 * v + st["posun"]), k)
                for v in self._plasma(st["ph"], 1.6 / self._width(eff))]

    def _kostky(self, eff, t, dt, data, music):
        """Kazdy uder shodi kostku do nahodneho sloupce; plna spodni rada blikne a zmizi, drop nebo
        plna klavesnice smaze vse."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        g = self.g
        ncol, rows = len(g.cols), g.nrows
        st = self.state.get("kostky")
        if st is None or st["dim"] != (ncol, rows):
            st = self.state["kostky"] = {"dim": (ncol, rows), "sloupce": [[] for _ in range(ncol)], "pad": [],
                                         "vse": -9.0, "rada": None, "drop": None}
        drop = int((music or {}).get("drop_n", 0))
        if st["drop"] is None:
            st["drop"] = drop
        full = all(len(s) >= rows for s in st["sloupce"])
        if drop != st["drop"] or full:                      # drop / plna klavesnice: zablesk a znovu
            st["drop"] = drop
            if any(st["sloupce"]):
                st["vse"] = t
            st["sloupce"] = [[] for _ in range(ncol)]
            st["pad"], st["rada"] = [], None
        hit = self._hit(eff, music, "kostky_n")
        if hit:
            for _ in range(1 + int(hit * self._width(eff) / 3.5)):
                free = [c for c in range(ncol)
                        if len(st["sloupce"][c]) + sum(1 for p in st["pad"] if p[0] == c) < rows]
                if not free:
                    break
                # ze tri nahodnych sloupcu ten nejnizsi - rady se plni rovnomerneji a casteji mizi
                col = min(self.rng.sample(free, min(3, len(free))), key=lambda c: len(st["sloupce"][c]))
                st["pad"].append([col, rows + 0.5, self.rng.choice(pal)])     # sloupec, vyska, barva
        rest = []
        for p in st["pad"]:                                 # pad kostek
            p[1] -= dt * 14.0
            if p[1] <= len(st["sloupce"][p[0]]) + 1:
                st["sloupce"][p[0]].append(p[2])
            else:
                rest.append(p)
        st["pad"] = rest
        if st["rada"] is None and all(st["sloupce"]):       # plna spodni rada: blikne a zmizi
            st["rada"] = t
        if st["rada"] is not None and t - st["rada"] > 0.3:
            for s in st["sloupce"]:
                if s:
                    s.pop(0)
            st["rada"] = None
        wipe = math.exp(-(t - st["vse"]) / 0.25) if t - st["vse"] < 1.5 else 0.0
        line = (0.5 + 0.5 * math.cos((t - st["rada"]) * 40)) if st["rada"] is not None else 0.0
        out = []
        for i in range(g.n):
            r = g.row_of[i]
            c = bg
            for col in g.key_cols[i]:
                s = st["sloupce"][col]
                if r < len(s):
                    c = _mix(s[r], (255, 255, 255), line) if r == 0 else s[r]
                    break
            for pc, ph, pcol in st["pad"]:
                if pc in g.key_cols[i]:
                    c = _mix(c, pcol, max(0.0, 1 - abs(ph - 1 - r)))     # kostka je mezi ph - 1 a ph
            out.append(_mix(c, (255, 255, 255), wipe))
        return out

    # -------------------------------------------------------------- dalsi klidne a pohyb (11. 11. 2026)
    def _proj_deg(self, deg):
        """Poloha klaves ve smeru deg (stupne) jako 0..1."""
        cache = self.state.setdefault("_proj_deg", {})
        d = int(deg) % 360
        if d not in cache:
            a = math.radians(d)
            v = [x * math.cos(a) + y * math.sin(a) for x, y in zip(self.g.cx, self.g.cy)]
            lo, hi = min(v, default=0.0), max(v, default=1.0)
            cache[d] = [(p - lo) / (hi - lo or 1) for p in v]
        return cache[d]

    def _lava(self, eff, t, dt, data, music):
        """Lavova lampa: velke barevne kapky pomalu plujou a slevaji se (metaballs)."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        w_, h_ = (g.x1 - g.x0), (g.y1 - g.y0)
        sp = self._speed(eff, 0.35)
        r2 = (1.0 + self._width(eff) * 0.25) ** 2
        blobs = []
        for b in range(5):
            x = g.x0 + w_ * (0.5 + 0.46 * math.sin(t * sp * (0.31 + 0.07 * b) + b * 1.9))
            y = g.y0 + h_ * (0.5 + 0.5 * math.sin(t * sp * (0.53 + 0.05 * b) + b * 2.7))
            blobs.append((x, y, pal[b % len(pal)]))
        out = []
        for x, y in zip(g.cx, g.cy):
            f, cw = 0.0, [0.0, 0.0, 0.0]
            for bx, by, c in blobs:
                v = r2 / max(0.05, (x - bx) ** 2 + ((y - by) * 1.3) ** 2)
                f += v
                cw[0] += c[0] * v
                cw[1] += c[1] * v
                cw[2] += c[2] * v
            out.append(_mix(bg, (cw[0] / f, cw[1] / f, cw[2] / f), _smooth((f - 0.7) / 1.2)))
        return out

    def _odlesk(self, eff, t, dt, data, music):
        """Klidna barva / prechod, pres ktery obcas sikmo prejede lesk jako po kovu."""
        pal = self._pal(eff)
        p = self.g.proj(eff)
        base = [_gradient(pal, v) for v in p] if len(pal) > 1 else [pal[0]] * self.g.n
        q = self._proj_deg(int(get(eff, "smer") or 0) + 35)
        period = 1.0 + 4.0 / self._speed(eff)
        pos = -0.3 + (t % period) * 1.6                       # lesk prejede za ~0,8 s, pak klid
        w = 0.04 + self._width(eff) * 0.012
        out = []
        for c, v in zip(base, q):
            k = max(0.0, 1 - abs(v - pos) / w) ** 2
            out.append(_mix(_scale(c, 0.8), (255.0, 255.0, 255.0), 0.85 * k))
        return out

    def _konfety(self, eff, t, dt, data, music):
        """Kazda klavesa pomalu prechazi na nahodnou barvu (palety nebo duhy)."""
        pal = self._pal(eff)
        rainbow = bool(get(eff, "duha"))

        def pick():
            return _hsv(self.rng.random()) if rainbow else self.rng.choice(pal)
        st = self.state.get("konfety")
        if st is None or len(st) != self.g.n:
            st = self.state["konfety"] = [[pick(), pick()] for _ in range(self.g.n)]
        sp = self._speed(eff)
        a = min(1.0, dt * sp * 0.8)
        for s in st:
            s[0] = _mix(s[0], s[1], a)
            if self.rng.random() < dt * sp * 0.2:
                s[1] = pick()
        return [s[0] for s in st]

    def _paprsky_kriz(self, eff, t, dt, data, music):
        """Vodorovny paprsek jezdi nahoru a dolu, svisly doleva a doprava, v prusecniku se barvy sectou."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        sp = self._speed(eff)
        w = 0.4 + self._width(eff) * 0.25
        hy = g.y0 + 0.4 + (g.y1 - g.y0 - 0.8) * (0.5 - 0.5 * math.cos(t * sp * 1.3))
        vx = g.x0 + 0.5 + (g.x1 - g.x0 - 1.0) * (0.5 - 0.5 * math.cos(t * sp * 0.7))
        c0, c1 = pal[0], pal[1 % len(pal)]
        out = []
        for x, y in zip(g.cx, g.cy):
            kh = max(0.0, 1 - abs(y - hy) / w)
            kv = max(0.0, 1 - abs(x - vx) / (w * 1.5))
            out.append(_add(_add(bg, _scale(c0, kh)), _scale(c1, kv)))
        return out

    def _pruhy(self, eff, t, dt, data, music):
        """Rady s barevnymi pruhy jezdi stridave doleva a doprava."""
        pal = self._pal(eff)
        g = self.g
        seg = 1.5 + self._width(eff) * 0.6                    # delka pruhu (u)
        sp = self._speed(eff) * 2.5                           # u za sekundu
        rainbow = bool(get(eff, "duha"))
        out = []
        for i, x in enumerate(g.cx):
            d = 1 if g.row_of[i] % 2 else -1
            f = (x + d * t * sp) / seg
            idx = math.floor(f)
            fr = f - idx
            c = _hsv(idx * 0.13) if rainbow else pal[idx % len(pal)]
            edge = min(fr, 1 - fr)
            out.append(_scale(c, 0.35 + 0.65 * _smooth(edge / 0.15)))
        return out

    # -------------------------------------------------------------- dalsi castice
    def _star_rand(self):
        """Pevne nahodne vlastnosti klaves pro hvezdy (faze, rychlost, barva)."""
        st = self.state.get("_hv_rand")
        if st is None or len(st) != self.g.n:
            r = random.Random(11)
            st = self.state["_hv_rand"] = [(r.random() * 6.28, 0.5 + r.random() * 1.6, r.random()) for _ in range(self.g.n)]
        return st

    def _streak(self, x, y, mx, my, vx, vy, length, width):
        """Jas klavesy (x, y) od cary s hlavou (mx, my) letici smerem (vx, vy) s ocasem delky length."""
        ln = math.hypot(vx, vy) or 1.0
        rx, ry = x - mx, (y - my) * 1.2
        along = -(rx * vx + ry * vy) / ln
        side = abs(rx * vy - ry * vx) / ln
        if -0.7 < along < length and side < width:
            return (1 - max(0.0, along) / length) ** 1.5 * (1 - side / width)
        return 0.0

    def _hvezdy(self, eff, t, dt, data, music):
        """Hvezdna obloha: klavesy tlumene mihotaji jako hvezdy, obcas preleti padajici hvezda."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        sp = self._speed(eff)
        rnd = self._star_rand()
        out = []
        for i in range(g.n):
            ph, fr, cr = rnd[i]
            tw = 0.5 + 0.5 * math.sin(t * fr * sp + ph)
            out.append(_mix(bg, pal[int(cr * len(pal)) % len(pal)], 0.06 + 0.5 * tw ** 3))
        mets = self.state.setdefault("hvezdy_met", [])            # [x, y, vx, vy]
        if self.rng.random() < self._width(eff) * 0.05 * sp * dt:
            d = self.rng.choice((-1, 1))
            mets.append([self.rng.uniform(g.x0 + 2, g.x1 - 2), g.y0 - 0.5, d * 16.0 * sp ** 0.7, 5.0 * sp ** 0.7])
        for m in mets:
            m[0] += m[2] * dt
            m[1] += m[3] * dt
        mets[:] = [m for m in mets if g.x0 - 6 < m[0] < g.x1 + 6 and m[1] < g.y1 + 3]
        white = (255.0, 255.0, 255.0)
        for m in mets:
            for i, (x, y) in enumerate(zip(g.cx, g.cy)):
                k = self._streak(x, y, m[0], m[1], m[2], m[3], 5.0, 0.9)
                if k > 0:
                    out[i] = _mix(out[i], white, k)
        return out

    def _snezeni(self, eff, t, dt, data, music):
        """Vlocky padaji a kolebaji se, na spodnich radach se tvori zaveje, ktere pomalu taji."""
        pal, bg = self._pal(eff), self._bg(eff)
        flake, pile_c = pal[0], pal[-1]
        g = self.g
        ncol = len(g.cols)
        st = self.state.get("snezeni")
        if st is None or len(st["zaveje"]) != ncol:
            st = self.state["snezeni"] = {"vlocky": [], "zaveje": [0.0] * ncol}
        sp = self._speed(eff)
        if self.rng.random() < self._width(eff) * 0.7 * sp * dt * 2:
            st["vlocky"].append([self.rng.uniform(g.x0, g.x1), g.y0 - 0.5, self.rng.uniform(1.2, 2.2) * sp,
                                 self.rng.random() * 6.28])
        alive = []
        for f in st["vlocky"]:
            f[1] += f[2] * dt
            x = f[0] + 0.5 * math.sin(t * 1.5 + f[3])
            col = min(range(ncol), key=lambda c: abs(g.cols[c] - x))
            if f[1] >= g.y1 - 0.5 - st["zaveje"][col]:            # dopadla na zavej / dolni radu
                st["zaveje"][col] = min(2.0, st["zaveje"][col] + 0.25)
                for nb in (col - 1, col + 1):                      # trochu i do sousednich sloupcu
                    if 0 <= nb < ncol:
                        st["zaveje"][nb] = min(2.0, st["zaveje"][nb] + 0.08)
            else:
                alive.append(f)
        st["vlocky"] = alive[-60:]
        st["zaveje"] = [max(0.0, z - dt * 0.03) for z in st["zaveje"]]
        out = []
        for i, (x, y) in enumerate(zip(g.cx, g.cy)):
            c = bg
            z = max(st["zaveje"][cc] for cc in g.key_cols[i])
            k = max(0.0, min(1.0, z - g.row_of[i]))
            if k > 0:
                c = _mix(c, _scale(pile_c, 0.75), k)
            for f in st["vlocky"]:
                fx_ = f[0] + 0.5 * math.sin(t * 1.5 + f[3])
                kk = max(0.0, 1 - math.hypot(x - fx_, (y - f[1]) * 1.2) / 0.75)
                if kk > 0:
                    c = _mix(c, flake, kk)
            out.append(c)
        return out

    def _kruhy_voda(self, eff, t, dt, data, music):
        """Kapky dopadaji na nahodne klavesy a sireji se od nich kruhy, ktere se protinaji."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        drops = self.state.setdefault("kruhy_voda", [])          # [x, y, cas, barva]
        sp = self._speed(eff)
        if self.rng.random() < self._width(eff) * 0.16 * sp * dt * 3:
            i = self.rng.randrange(g.n)
            drops.append([g.cx[i], g.cy[i], t, self.rng.choice(pal)])
        life = 2.2
        drops[:] = [d for d in drops if t - d[2] < life][-12:]
        out = []
        for x, y in zip(g.cx, g.cy):
            c = bg
            for dx, dy, dt0, dc in drops:
                age = t - dt0
                d = math.hypot(x - dx, (y - dy) * 1.3)
                r = age * 5.0 * sp ** 0.5
                k = max(0.0, 1 - abs(d - r) / 0.9) + 0.5 * max(0.0, 1 - abs(d - r * 0.55) / 0.7)
                k *= (1 - age / life) ** 1.5
                if age < 0.15 and d < 0.7:
                    k = max(k, 1 - age / 0.15)                   # dopad kapky
                if k > 0.01:
                    c = _add(c, _scale(dc, 0.8 * k))
            out.append(c)
        return out

    def _svetlusky(self, eff, t, dt, data, music):
        """Mekka svetylka bloudi po klavesnici a pomalu blikaji."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        n = 2 + int(self._width(eff))
        st = self.state.get("svetlusky")
        if st is None or len(st) != n:
            st = self.state["svetlusky"] = [[self.rng.uniform(g.x0, g.x1), self.rng.uniform(g.y0, g.y1), 0.0, 0.0,
                                             self.rng.random(), self.rng.uniform(2.0, 4.5), b % len(pal)]
                                            for b in range(n)]
        sp = self._speed(eff)
        vmax = 2.0 * sp
        for f in st:                                             # [x, y, vx, vy, faze, perioda, barva]
            f[2] += self.rng.gauss(0, 6) * dt
            f[3] += self.rng.gauss(0, 4) * dt
            v = math.hypot(f[2], f[3])
            if v > vmax:
                f[2], f[3] = f[2] / v * vmax, f[3] / v * vmax
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            if not g.x0 < f[0] < g.x1:
                f[2] = -f[2]
                f[0] = max(g.x0, min(g.x1, f[0]))
            if not g.y0 < f[1] < g.y1:
                f[3] = -f[3]
                f[1] = max(g.y0, min(g.y1, f[1]))
        out = []
        for x, y in zip(g.cx, g.cy):
            c = bg
            for fx_, fy_, _vx, _vy, ph, per, ci in st:
                b = max(0.0, math.sin(2 * math.pi * (t / per + ph))) ** 2
                k = max(0.0, 1 - math.hypot(x - fx_, (y - fy_) * 1.2) / 1.4) ** 2 * b
                if k > 0.01:
                    c = _add(c, _scale(pal[ci % len(pal)], k))
            out.append(c)
        return out

    def _prskavka(self, eff, t, dt, data, music):
        """Jasny bod jezdi po okraji klavesnice a sypou se z nej jiskry, ktere padaji dolu."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        head_c, spark_c = pal[0], pal[1 % len(pal)]
        sp = self._speed(eff)
        x0, x1, y0, y1 = g.x0 + 0.5, g.x1 - 0.5, g.y0 + 0.5, g.y1 - 0.5
        w_, h_ = x1 - x0, y1 - y0
        per = 2 * (w_ + h_)
        s = (t * sp * 6.0) % per                                 # obvod po smeru hodin
        if s < w_:
            hx, hy = x0 + s, y0
        elif s < w_ + h_:
            hx, hy = x1, y0 + s - w_
        elif s < 2 * w_ + h_:
            hx, hy = x1 - (s - w_ - h_), y1
        else:
            hx, hy = x0, y1 - (s - 2 * w_ - h_)
        sparks = self.state.setdefault("prskavka", [])           # [x, y, vx, vy, vek, zivot]
        for _ in range(int(dt * self._width(eff) * 7 + self.rng.random())):
            a = self.rng.random() * 2 * math.pi
            v = self.rng.uniform(3.0, 7.0)
            sparks.append([hx, hy, v * math.cos(a), v * math.sin(a) * 0.7, 0.0, self.rng.uniform(0.35, 0.7)])
        for p in sparks:
            p[3] += 9.0 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] += dt
        sparks[:] = [p for p in sparks if p[4] < p[5]][-60:]
        out = []
        for x, y in zip(g.cx, g.cy):
            c = bg
            for px, py, _vx, _vy, age, life in sparks:
                k = (1 - age / life) * max(0.0, 1 - math.hypot(x - px, (y - py) * 1.2) / 0.7)
                if k > 0.01:
                    c = _add(c, _scale(spark_c, k))
            k = max(0.0, 1 - math.hypot(x - hx, (y - hy) * 1.2) / 1.1)
            if k > 0:
                c = _mix(c, _mix(head_c, (255.0, 255.0, 255.0), 0.4), k)
            out.append(c)
        return out

    def _meteory(self, eff, t, dt, data, music):
        """Meteory leti sikmo pres klavesnici a na spodni rade se rozstriknou."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        sp = self._speed(eff)
        st = self.state.setdefault("meteory", {"m": [], "s": []})  # meteory [x, y, vx, vy, barva], dopady [x, y, cas, barva]
        if self.rng.random() < self._width(eff) * 0.14 * sp * dt * 2:
            d = self.rng.choice((-1, 1))
            st["m"].append([self.rng.uniform(g.x0, g.x1), g.y0 - 1.0, d * self.rng.uniform(5.0, 9.0) * sp ** 0.7,
                            self.rng.uniform(6.0, 9.0) * sp ** 0.7, self.rng.choice(pal)])
        alive = []
        for m in st["m"]:
            m[0] += m[2] * dt
            m[1] += m[3] * dt
            if m[1] >= g.y1 - 0.5:
                st["s"].append([m[0], g.y1 - 0.5, t, m[4]])
            elif g.x0 - 4 < m[0] < g.x1 + 4:
                alive.append(m)
        st["m"] = alive[-10:]
        st["s"] = [s for s in st["s"] if t - s[2] < 0.5][-10:]
        out = []
        for x, y in zip(g.cx, g.cy):
            c = bg
            for mx, my, vx, vy, mc in st["m"]:
                k = self._streak(x, y, mx, my, vx, vy, 4.0, 0.9)
                if k > 0:
                    c = _add(c, _scale(_mix(mc, (255.0, 255.0, 255.0), 0.4 * k), k))
            for sx, sy, st0, sc in st["s"]:
                age = (t - st0) / 0.5
                d = math.hypot(x - sx, (y - sy) * 1.5)
                k = max(0.0, 1 - abs(d - age * 3.0) / 0.9) * (1 - age)
                if k > 0:
                    c = _add(c, _scale(sc, k))
            out.append(c)
        return out

    # -------------------------------------------------------------- dalsi hry
    def _ball_key(self, out, x, y, col, r=0.8):
        g = self.g
        for i, (kx, ky) in enumerate(zip(g.cx, g.cy)):
            k = max(0.0, 1 - math.hypot(kx - x, (ky - y) * 1.1) / r)
            if k > 0:
                out[i] = _mix(out[i], col, k)

    def _cihly(self, eff, t, dt, data, music):
        """Rozbijeni cihel: palka na spodni rade odrazi micek, ktery bori cihly v hornich radach. Hraje sam.
        Barvy: micek a palka, pak cihly po radach."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        top = g.nrows - 1
        brick_rows = [r for r in (top - 1, top - 2) if r > 0] if g.nrows >= 5 else [top]
        st = self.state.get("cihly")
        if st is None or st["n"] != g.n:
            st = self.state["cihly"] = {"n": g.n, "cihly": set(), "mic": None, "palka": g.mx, "konec": None,
                                        "chyba": 0.0, "vyhra": None}
        if not st["cihly"] and st["vyhra"] is None:
            st["cihly"] = {i for i in range(g.n) if g.row_of[i] in brick_rows}
        sp = self._speed(eff)
        y_pad = max((g.cy[i] for i in range(g.n) if g.row_of[i] == 0), default=g.y1 - 0.5)
        pw = 3.5
        if st["mic"] is None and st["konec"] is None and st["vyhra"] is None:   # podani
            a = self.rng.uniform(-0.9, 0.9)
            v = 8.0 * sp
            st["mic"] = [st["palka"], y_pad - 1.0, v * math.sin(a), -v * math.cos(a)]
            st["chyba"] = self.rng.uniform(-1.0, 1.0) * (3.0 if self.rng.random() < 0.3 else 0.8)
        m = st["mic"]
        if m is not None:
            # palka: sleduje micek s chybou (obcas netrefi)
            target = m[0] + st["chyba"]
            st["palka"] += max(-14.0 * sp * dt, min(14.0 * sp * dt, target - st["palka"]))
            st["palka"] = max(g.x0 + pw / 2, min(g.x1 - pw / 2, st["palka"]))
            steps = max(1, int(math.hypot(m[2], m[3]) * dt / 0.3) + 1)
            for _ in range(steps):
                m[0] += m[2] * dt / steps
                m[1] += m[3] * dt / steps
                if m[0] < g.x0 or m[0] > g.x1:
                    m[2] = -m[2]
                    m[0] = max(g.x0, min(g.x1, m[0]))
                if m[1] < g.y0:
                    m[3] = abs(m[3])
                hit = next((i for i in st["cihly"] if abs(g.cx[i] - m[0]) <= g.kw[i] / 2 and abs(g.cy[i] - m[1]) <= 0.5),
                           None)
                if hit is not None:
                    st["cihly"].discard(hit)
                    m[3] = -m[3]
                    m[2] += self.rng.uniform(-1.0, 1.0)
                if m[3] > 0 and m[1] >= y_pad - 0.6:
                    if abs(m[0] - st["palka"]) <= pw / 2 + 0.4:     # odraz od palky (kraj = sikmeji)
                        v = math.hypot(m[2], m[3])
                        a = max(-1.1, min(1.1, (m[0] - st["palka"]) / (pw / 2) * 1.0))
                        m[2], m[3] = v * math.sin(a), -v * math.cos(a)
                        st["chyba"] = self.rng.uniform(-1.0, 1.0) * (3.0 if self.rng.random() < 0.3 else 0.8)
                    elif m[1] > y_pad + 0.5:
                        st["mic"], st["konec"] = None, t
                        break
            if not st["cihly"]:
                st["mic"], st["vyhra"] = None, t
        if st["konec"] is not None and t - st["konec"] > 0.9:
            st["konec"] = None
        if st["vyhra"] is not None and t - st["vyhra"] > 1.5:
            st["vyhra"] = None
        out = [bg] * g.n
        brick_pal = pal[1:] or pal
        for i in range(g.n):
            if i in st["cihly"]:
                out[i] = brick_pal[brick_rows.index(g.row_of[i]) % len(brick_pal)] if g.row_of[i] in brick_rows else bg
            elif st["vyhra"] is not None and g.row_of[i] in brick_rows:
                out[i] = _hsv(g.cx[i] / 20 + t) if int((t - st["vyhra"]) * 6) % 2 == 0 else bg
            if g.row_of[i] == 0 and abs(g.cx[i] - st["palka"]) <= pw / 2:
                out[i] = pal[0]
        if st["konec"] is not None and int((t - st["konec"]) * 8) % 2 == 0:   # micek ztracen
            out = [_mix(c, (255.0, 0.0, 0.0), 0.35) if g.row_of[i] == 0 else c for i, c in enumerate(out)]
        if m is not None and st["mic"] is not None:
            self._ball_key(out, m[0], m[1], _mix(pal[0], (255.0, 255.0, 255.0), 0.5))
        return out

    def _tenis(self, eff, t, dt, data, music):
        """Tenis: palky na levem a pravem kraji, micek se odrazi mezi nimi. Hraje sam.
        Barvy: leva palka, prava palka, micek."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        lx, rx = g.x0 + 0.5, g.x1 - 0.5
        ph = 2.6                                                   # vyska palky (u)
        sp = self._speed(eff)
        st = self.state.get("tenis")
        if st is None:
            st = self.state["tenis"] = {"mic": None, "p": [g.my, g.my], "chyba": [0.0, 0.0], "bod": None, "kdo": 0}
        if st["mic"] is None and (st["bod"] is None or t - st["bod"] > 1.0):
            st["bod"] = None
            d = 1 if st["kdo"] == 0 else -1
            v = 9.0 * sp
            a = self.rng.uniform(-0.6, 0.6)
            st["mic"] = [g.mx, g.my, d * v * math.cos(a), v * math.sin(a) * 0.6]
            st["chyba"] = [self.rng.uniform(-1, 1) * (1.6 if self.rng.random() < 0.3 else 0.3) for _ in range(2)]
        m = st["mic"]
        if m is not None:
            for side, px in ((0, lx), (1, rx)):
                coming = (m[2] < 0) if side == 0 else (m[2] > 0)
                target = (m[1] + st["chyba"][side]) if coming else g.my
                st["p"][side] += max(-8.0 * sp * dt, min(8.0 * sp * dt, target - st["p"][side]))
                st["p"][side] = max(g.y0 + ph / 2, min(g.y1 - ph / 2, st["p"][side]))
            m[0] += m[2] * dt
            m[1] += m[3] * dt
            if m[1] < g.y0 + 0.3 or m[1] > g.y1 - 0.3:
                m[3] = -m[3]
                m[1] = max(g.y0 + 0.3, min(g.y1 - 0.3, m[1]))
            for side, px in ((0, lx + 0.8), (1, rx - 0.8)):
                if (side == 0 and m[2] < 0 and m[0] <= px) or (side == 1 and m[2] > 0 and m[0] >= px):
                    if abs(m[1] - st["p"][side]) <= ph / 2 + 0.3:
                        v = math.hypot(m[2], m[3]) * 1.03
                        a = (m[1] - st["p"][side]) / (ph / 2) * 0.8
                        m[2] = (1 if side == 0 else -1) * v * math.cos(a)
                        m[3] = v * math.sin(a) * 0.6
                        st["chyba"][1 - side] = self.rng.uniform(-1, 1) * (1.6 if self.rng.random() < 0.3 else 0.3)
                    elif (side == 0 and m[0] < g.x0) or (side == 1 and m[0] > g.x1):
                        st["mic"], st["bod"], st["kdo"] = None, t, side    # bod pro druhou stranu, podava porazeny
                        break
        out = []
        for i, (x, y) in enumerate(zip(g.cx, g.cy)):
            c = bg
            if abs(x - g.mx) < 0.5 and g.row_of[i] % 2 == 0:
                c = _add(c, _scale(pal[2 % len(pal)], 0.12))       # sit
            for side, px in ((0, lx), (1, rx)):
                if abs(x - px) < 1.2 and abs(y - st["p"][side]) <= ph / 2:
                    c = pal[side % len(pal)]
            if st["bod"] is not None and int((t - st["bod"]) * 6) % 2 == 0:
                win = 1 - st["kdo"]                                    # bliká strana, ktera bod ziskala
                if (win == 0 and x < g.mx) or (win == 1 and x > g.mx):
                    c = _mix(c, pal[win % len(pal)], 0.3)
            out.append(c)
        if st["mic"] is not None:
            self._ball_key(out, st["mic"][0], st["mic"][1], pal[2 % len(pal)])
        return out

    # -------------------------------------------------------------- dalsi hudba
    def _need(self, eff, music):
        """Nejmensi sila uderu pro efekt s vlastni nizsi citlivosti (jinak 0) - jako _hit."""
        if not get(eff, "citlivost_vlastni") or not music:
            return 0.0
        c = fx.beat_ratio(music.get("citlivost", 5))
        b = fx.beat_ratio(self._sens(eff, music))
        return (b - c) / c + 0.5 if b > c else 0.0

    def _events(self, eff, music, field, key):
        """Nove udery daneho nastroje ("kicks" / "snares" / "hats" / "beats") od minuleho snimku: [(vek, sila, poradi)]."""
        if not music:
            return []
        last = self.state.get(key, 0)
        evs = [e for e in music.get(field, ()) if len(e) > 2]
        if evs and max(e[2] for e in evs) < last - 5:            # analyza zacala znovu
            last = 0
        new = [e for e in evs if e[2] > last]
        if evs:
            self.state[key] = max([last] + [e[2] for e in evs])
        need = self._need(eff, music)
        return [e for e in new if e[1] >= need]

    def _bar_pos(self, music, key, dt):
        """(poloha v taktu 0..1, delka doby s) z rytmicke mrizky, bez ni takt 2 s."""
        bpm = float((music or {}).get("bpm") or 0.0)
        if music and bpm and float(music.get("grid", 0.0)) >= 0.3:
            return ((int(music.get("bar", 0)) + float(music.get("beat_ph", 0.0))) / 4.0) % 1.0, 60.0 / bpm
        st = self.state.setdefault(key, [0.0])
        st[0] = (st[0] + dt / 2.0) % 1.0
        return st[0], 0.5

    def _drop_age(self, music, key, dt):
        """Kolik s uplynulo od posledniho dropu (99 = davno / zadny)."""
        d = int((music or {}).get("drop_n", 0))
        st = self.state.setdefault(key, [d, 99.0])
        if d != st[0]:
            if d > st[0]:
                st[1] = 0.0
            st[0] = d
        st[1] += dt
        return st[1]

    def _bici_automat(self, eff, t, dt, data, music):
        """Bici automat: sloupce = takt (16 kroku zleva doprava), rady = kopak (dole), virbl, hi-hat (nahore).
        Udery zustanou svitit na svem miste v taktu - je videt rytmicky vzorec skladby."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        g = self.g
        bp, period = self._bar_pos(music, "ba_takt", dt)
        marks = self.state.setdefault("bici_automat", [])         # [krok 0-15, nastroj, sila, vek]
        for inst, field in enumerate(("kicks", "snares", "hats")):
            for age, s, _n in self._events(eff, music, field, "ba_" + field):
                step = int(((bp - age / (4 * period)) % 1.0) * 16) % 16
                marks[:] = [m for m in marks if not (m[0] == step and m[1] == inst)]
                marks.append([step, inst, s, 0.0])
        life = 8 * period                                         # dva takty
        for m in marks:
            m[3] += dt
        marks[:] = [m for m in marks if m[3] < life]
        cur = int(bp * 16) % 16
        top = g.nrows - 1 if g.nrows >= 5 else None              # horni pruh (logo, media) = doby taktu
        rows = g.nrows - (1 if top is not None else 0)
        light = {(m[0], m[1]): m for m in marks}
        out = []
        for i in range(g.n):
            step = min(15, int((g.cx[i] - g.x0) / ((g.x1 - g.x0) or 1) * 16))
            r = g.row_of[i]
            if r == top:
                on = step // 4 == cur // 4
                c = _mix(bg, (255.0, 255.0, 255.0), 0.45 if on else 0.05)
            else:
                inst = min(2, r * 3 // max(1, rows))
                c = bg
                m = light.get((step, inst))
                if m is not None:
                    c = _mix(bg, pal[inst % len(pal)], m[2] * (0.35 + 0.65 * math.exp(-m[3] / 0.25)) * (1 - m[3] / life))
                elif step % 4 == 0:
                    c = _add(c, _scale(pal[inst % len(pal)], 0.05))      # doby taktu tlumene
            if step == cur:
                c = _mix(c, (255.0, 255.0, 255.0), 0.2)            # prehravani
            out.append(c)
        return out

    def _hvezdny_let(self, eff, t, dt, data, music):
        """Hvezdy leti od stredu ke krajum, rychlost podle energie skladby, kopak = zrychleni, drop = skok."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        g = self.g
        st = self.state.setdefault("hvezdny_let", {"h": [], "boost": 0.0})
        energy = float((music or {}).get("energy", 0.5)) if music else 0.3
        if self._events(eff, music, "kicks", "hl_kick"):
            st["boost"] = 1.0
        st["boost"] *= math.exp(-dt / 0.3)
        warp = max(0.0, 1 - self._drop_age(music, "hl_drop", dt) / 1.2)
        v = (0.35 + 1.6 * energy + 1.4 * st["boost"] + 3.0 * warp)
        rmax = max(g.dist, default=10.0) + 1.0
        if self.rng.random() < self._width(eff) * 0.9 * dt * 4:
            st["h"].append([self.rng.random() * 2 * math.pi, 0.3, self.rng.choice(pal)])
        for s in st["h"]:
            s[1] += (s[1] * 0.9 + 0.6) * v * dt
        st["h"] = [s for s in st["h"] if s[1] < rmax][-40:]
        out = [bg] * g.n
        for a, r, c in st["h"]:
            ca, sa = math.cos(a), math.sin(a) * 0.55
            hx, hy = g.mx + r * ca, g.my + r * sa
            tail = 0.4 + r * 0.12 * v
            bright = min(1.0, 0.25 + r / rmax)
            col = _mix(c, (255.0, 255.0, 255.0), warp * 0.7)
            for i, (x, y) in enumerate(zip(g.cx, g.cy)):
                k = self._streak(x, y, hx, hy, ca, sa, tail, 0.8)
                if k > 0:
                    out[i] = _add(out[i], _scale(col, k * bright))
        return out

    def _stoupani(self, eff, t, dt, data, music):
        """Stoupani k dropu: v klidu dychani do taktu, pri stavbe napeti se klavesnice plni zleva a blika
        rychleji, v dropu vybuch barev od stredu."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        g = self.g
        b = max(0.0, min(1.0, float((music or {}).get("build", 0.0))))
        bp, _period = self._bar_pos(music, "st_takt", dt)
        a = self._drop_age(music, "st_drop", dt)
        lv = self._lv(eff, music, dt)
        level = lv["level"] if lv else 0.0
        breath = 0.5 - 0.5 * math.cos(2 * math.pi * bp)
        acc = pal[1 % len(pal)]
        riser = _mix(acc, (255.0, 255.0, 255.0), 0.6 * b)
        flash = 0.0
        if b > 0.05:
            sub = (1, 2, 4, 8)[min(3, int(b * 4))]
            flash = b * math.exp(-((float((music or {}).get("beat_ph", 0.0)) * sub) % 1.0) / 0.35)
        rmax = max(g.dist, default=10.0)
        out = []
        for i, (x, y) in enumerate(zip(g.cx, g.cy)):
            p = g.xlo[i]
            c = _scale(_gradient(pal, p), 0.12 + 0.2 * breath + 0.25 * level)
            if b > 0.02:
                fill = max(0.0, min(1.0, (b * 1.05 - p) / 0.06 + 0.5))
                c = _mix(c, _add(_scale(riser, 0.35 + 0.65 * b), _scale((255.0, 255.0, 255.0), 0.5 * flash)), fill)
            if a < 1.5:                                           # drop: kruh barev od stredu a zablesk
                d = g.dist[i]
                ring = max(0.0, 1 - abs(d - a * 16.0) / 2.5) * (1 - a / 1.5)
                burst = _cyclic(pal, g.ang[i] + a)
                c = _add(_scale(c, 1 - min(1.0, ring)), _scale(burst, ring))
                if a < 0.15:
                    c = _mix(c, (255.0, 255.0, 255.0), 1 - a / 0.15)
            out.append(c)
        return out

    def _kruhove_spektrum(self, eff, t, dt, data, music):
        """16 paprsku ze stredu, delka podle sily pasma (basy doleva a doprava, vysky nahoru a dolu - klavesnice
        je siroka), pomalu se toci."""
        pal, bg = self._music_pal(eff, music), self._bg(eff)
        lv = self._lv(eff, music, dt)
        v, _pk = self._meter("kruhove_spektrum", (lv["bands"] if lv else [0.0] * 16), dt)
        dist, ang = self.g.polar(eff)
        rmax = max(dist, default=1.0) or 1.0
        rot = t * self._speed(eff, 0.05)
        out = []
        for d, a in zip(dist, ang):
            m = abs(math.sin(2 * math.pi * (a + rot)))            # 0 vodorovne (basy) .. 1 svisle (vysky)
            b = min(15, int(m * 16))
            ln = 0.6 + v[b] * rmax
            k = max(0.0, min(1.0, ln - d))
            out.append(_mix(bg, _gradient(pal, min(1.0, d / rmax)), k))
        return out

    def _glitch(self, eff, t, dt, data, music):
        """Porucha: na virbl, kopak a hi-hat se rady posunou, barvy rozdeli nebo vypadnou."""
        pal = self._music_pal(eff, music)
        g = self.g
        st = self.state.setdefault("glitch", [0.0, 0, 0.0])          # zbyva s, druh, sila
        st[0] = max(0.0, st[0] - dt)
        for field, w in (("snares", 1.0), ("kicks", 0.8), ("hats", 0.55)):
            for _age, s, n in self._events(eff, music, field, "gl_" + field):
                if st[0] <= 0 or s * w >= st[2]:
                    st[0], st[1], st[2] = 0.07 + 0.18 * s * w, n * 7 + len(field), s * w
        lv = self._lv(eff, music, dt)
        dim = 0.4 + 0.6 * (lv["bass"] if lv else 0.3)
        w_ = (g.x1 - g.x0) or 1.0
        drift = t * self._speed(eff, 0.05)

        def base(x):
            return _scale(_cyclic(pal, (x - g.x0) / w_ * 0.8 + drift), dim)
        if st[0] <= 0:
            return [base(x) for x in g.cx]
        rr = random.Random(st[1] * 31 + int(st[0] * 40))
        kind = st[1] % 4
        out = []
        if kind == 0:                                            # rady se posunou
            shift = [rr.uniform(-4.0, 4.0) for _ in range(g.nrows)]
            out = [base(x + shift[g.row_of[i]]) for i, x in enumerate(g.cx)]
        elif kind == 1:                                          # barevne kanaly se rozjedou
            out = [(base(x - 2.5)[0], base(x)[1], base(x + 2.5)[2]) for x in g.cx]
        elif kind == 2:                                          # vypadek rad a sum
            off = {r for r in range(g.nrows) if rr.random() < 0.5}
            for i, x in enumerate(g.cx):
                c = (0.0, 0.0, 0.0) if g.row_of[i] in off else base(x)
                out.append((255.0, 255.0, 255.0) if rr.random() < 0.06 else c)
        else:                                                    # negativ
            out = [tuple(255.0 - v for v in base(x)) for x in g.cx]
        return out

    def _nalada(self, eff, t, dt, data, music):
        """Nalada skladby: tiche pasaze klidne a v prvnich barvach, refren rychleji a v poslednich (paleta od
        klidne k energicke); jeden nadech za takt."""
        pal = self._music_pal(eff, music)
        st = self.state.setdefault("nalada", {"e": 0.3, "ph": 0.0})
        e = float(music.get("energy", 0.5)) if music else 0.2
        lv = self._lv(eff, music, dt)
        if lv:
            e = 0.75 * e + 0.25 * lv["level"]
        st["e"] += (e - st["e"]) * min(1.0, dt / 2.0)
        en = st["e"]
        st["ph"] += dt * self._speed(eff, 0.25 + 1.2 * en)
        bp, _per = self._bar_pos(music, "na_takt", dt)
        br = 0.5 - 0.5 * math.cos(2 * math.pi * bp)
        k = (0.3 + 0.55 * en) * (0.8 + 0.2 * br)
        return [_scale(_gradient(pal, max(0.0, min(1.0, 0.1 + 0.75 * en + 0.18 * v))), k)
                for v in self._plasma(st["ph"], 1.6 / self._width(eff))]

    # -------------------------------------------------------------- psani
    def _teplotni_mapa(self, eff, t, dt, data, music):
        """Teplotni mapa psani: klavesy se pouzivanim ohrivaji a pomalu chladnou (jen v pameti, nic se neuklada)."""
        pal, bg = self._pal(eff), self._bg(eff)
        g = self.g
        heat = self.state.get("teplotni_mapa")
        if heat is None or len(heat) != g.n:
            heat = self.state["teplotni_mapa"] = [0.0] * g.n
        nb = g.neighbors()
        spread = self._width(eff) * 0.06
        for i in self.new_presses("tm_n"):
            heat[i] += 1.0
            for j in nb[i]:
                heat[j] += spread
        try:
            half = 600.0 / max(1.0, float(get(eff, "rychlost") or 5)) ** 1.6     # 1: 10 min ... 10: 15 s
        except (TypeError, ValueError):
            half = 46.0
        dec = 0.5 ** (dt / half)
        out = []
        for i in range(g.n):
            heat[i] *= dec
            v = 1 - math.exp(-heat[i] / 3.0)
            out.append(_mix(bg, _gradient(pal, v), min(1.0, v * 3)))
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
            px, py = self.g.cx[i], self.g.cy[i]
            if mode == "klavesa":
                out[i] = _mix(out[i], col, fade ** 0.7)
            elif mode == "zare":                             # sviti i okoli klavesy, k okraji slabne
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
                    k = max(0.0, 1 - math.hypot(x - px, (y - py) * 1.2) / 2.8) ** 1.3 * fade ** 0.7
                    if k > 0:
                        out[j] = _mix(out[j], col, k)
            elif mode in ("kriz", "paprsky"):                # cela rada a sloupec klavesy / pulz po nich ven
                r = age * 16.0
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
                    dx, dy = abs(x - px), abs(y - py)
                    if dy < 0.55:
                        d = dx
                    elif dx < 0.6 + abs(self.g.kw[j] - 1) / 2:
                        d = dy * 2.2                         # rady jsou u sebe bliz nez klavesy v rade
                    else:
                        continue
                    if mode == "kriz":
                        k = fade ** 0.8 * (1 - 0.45 * min(1.0, d / 12.0))
                    else:
                        k = max(max(0.0, 1 - abs(d - r) / 1.6) * fade ** 0.5, fade if j == i else 0.0)
                    if k > 0:
                        out[j] = _mix(out[j], col, k)
            elif mode == "jiskry":                           # z klavesy vyletnou jiskry, ktere padaji
                rr = random.Random(int(pt * 1000) * 131 + i)
                parts = []
                for s_ in range(8):
                    a = 2 * math.pi * s_ / 8 + rr.uniform(-0.3, 0.3)
                    v = rr.uniform(5.0, 9.0)
                    parts.append((px + v * math.cos(a) * age, py + v * math.sin(a) * 0.7 * age + 6.0 * age * age))
                out[i] = _mix(out[i], col, fade)
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
                    k = max((1 - math.hypot(x - sx, (y - sy) * 1.2) / 0.8 for sx, sy in parts), default=0.0)
                    if k > 0:
                        out[j] = _mix(out[j], _mix(col, (255.0, 255.0, 255.0), 0.3), k * fade)
            elif mode == "plaminek":                         # z klavesy vyslehne plaminek nahoru
                hmax = 3.5 * fade ** 0.5
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
                    dy = py - y
                    if -0.4 < dy < hmax and abs(x - px) < 0.6 + abs(self.g.kw[j] - 1) / 2 + max(0.0, 0.5 - dy * 0.3):
                        h = max(0.0, dy) / max(0.3, hmax)
                        flick = 0.8 + 0.2 * math.sin(self.rclock * 23 + j * 1.7)
                        c = _mix((255.0, 240.0, 160.0), col, min(1.0, h * 1.6))     # dole bila / zluta, nahore barva
                        out[j] = _mix(out[j], c, max(0.0, 1 - h) * fade ** 0.6 * flick)
            elif mode == "inkoust":                          # barva se z klavesy pomalu rozpiji do okoli
                r = 0.4 + 2.8 * (1 - math.exp(-3.0 * age / life))
                for j, (x, y) in enumerate(zip(self.g.cx, self.g.cy)):
                    d = math.hypot(x - px, (y - py) * 1.3)
                    k = max(0.0, 1 - d / r) ** 0.7 * fade ** 0.6
                    if k > 0:
                        out[j] = _mix(out[j], col, k)
            else:                                            # vlnka od klavesy
                r = age * 9.0
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
    if isinstance(eff, dict) and eff.get("typ") in ALIASES:
        eff["typ"] = ALIASES[eff["typ"]]
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
    for typ in EFFECTS:
        e = default_effect(typ)
        t = time.perf_counter()
        for f in range(300):                                 # 10 s se simulovanou hudbou
            if f % 20 == 0:
                eng.press(ZONES[(f * 7) % len(ZONES)])
            c = eng.frame(e, 1 / 30, {"CPU (Tctl/Tdie)": {"value": 70}}, dict(fx.music_demo(f / 30), citlivost=5))
        for mode, _name in REACTIONS:
            eng.press(1)
            c = eng.reaction(dict(REACTION_DEFAULT, zapnuto=True, rezim=mode), c)
        assert len(c) == len(KEYS)
        print(f"{typ:16s} {(time.perf_counter() - t) / 300 * 1000:5.2f} ms/snímek")
