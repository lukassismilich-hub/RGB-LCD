# led.py - LED vsech ventilatoru: F140 RGB Core (NZXT 2023 RGB Controller) a ventilatory
# na desce (ARGB hlavicka Gigabyte RGB Fusion 2.0 / IT5701).
#
# Efekty pocita aplikace (led_efekty.py) a posila barvy kazde LED primo:
#   - NZXT: kanaly led1 a led2 = po jednom F140 (8 LED), rezim "super-fixed" (barva po LED)
#   - Gigabyte: ARGB hlavicka D_LED1 (0x58) - 2 ventilatory paralelne, kazdy 14 LED (sviti stejne);
#     D_LED2 (0x59) - 1 ventilator, 14 LED. Primy rezim: registr 0x32 = maska vypnutych vestavenych efektu
#     (D_LED1 0x01, D_LED2 0x02), barvy po LED paketem [0xCC, hlavicka, offset 2 B, pocet bajtu,
#     az 19 LED], poradi bajtu z kalibrace (GRB). Protokol podle OpenRGB.
#   - ostatni zony desky (male LED, 12V RGB) = jen jedna barva / efekt cipu pres liquidctl
#   - graficka karta RTX 5070 Eagle OC = jedna barva bocniho pasku pres I2C karty (grafika.py, NvAPI),
#     ve vlne za D_LED2 (karta je pod F140)
#   - klavesnice Logitech G815 primo pres HID++ (klavesnice.Direct, bez G HUB, vlastni vlakno odesilani):
#     vlastni plosne efekty po klavesach (klavesnice_efekty.py, efekt "vlastni" = efekt_klavesnice),
#     nebo cela klavesnice jednou barvou jako F140 / deska; reakce na stisk klaves (klavesy_stisk.py);
#     casti klavesnice s vlastnim efektem pres zaklad (vrstvy_klavesnice, kb_layers); klavesy G1-G5
#     prepinaji predvolby efektu, hudbu, playlist a skladbu na LCD, M1-M3 prepinaji tri nastaveni
#     klavesnice (klavesy_g.py - vlakno pocita s config["led"] + profil aktivniho M); osvetleni G-klaves
#     podle nastaveni kazde klavesy.
#     Integrovanou pamet klavesnice aplikace sama vypne a pri konci / vypnuti rizeni zase zapne.
# Liquidctl sam D_LED neovladne, kdyz ma hlavicka vypnute vestavene efekty (tak ji nechava GCC).
# LED desky jinak ridi Gigabyte Control Center (GCC) - pokud bezi, nastaveni prepise.
#
# Vlakno LedWorker drzi spojeni otevrena, animovane efekty posila ~30x za sekundu, staticke
# jen pri zmene. Po probuzeni PC (skok hodin) a po chybe se radice nastavi znovu.
# Chyba u LED nesmi zdrzet chlazeni - bezi mimo hlavni smycku.

import copy
import json
import math
import logging
import os
import threading
import time

import klavesnice_efekty as kbfx
import hlasitost
import klavesy_g
import led_efekty as fx

log = logging.getLogger("rgb_lcd")

RETRY_S = 30
RESUME_GAP_S = 20
REFRESH_S = 10               # staticky efekt: obcas poslat znovu (kdyby radic zapomnel)
LEDS_PER_FAN = 8

# ostatni zony Gigabyte (cela zona)
FUSION_MODES = {
    "off": ("vypnuto", False, False),
    "fixed": ("jedna barva", True, False),
    "pulse": ("pulz", True, True),
    "flash": ("blikání", True, True),
    "double-flash": ("dvojité blikání", True, True),
    "color-cycle": ("střídání barev", False, True),
    "grafika": ("jako grafika", False, False),   # barvu pocita aplikace stejne jako pasek grafiky
}
SYNC_ZONE = "grafika"                        # rezim zony desky, ktera sviti s grafikou (LED pasek u karty)
FUSION_SPEEDS = {"slowest": "nejpomaleji", "slower": "pomaleji", "normal": "normálně", "faster": "rychleji",
                 "fastest": "nejrychleji", "ludicrous": "šíleně rychle"}

# ARGB hlavicky desky: nazev -> (zona liquidctl, prikaz pro barvy po LED, bit masky 0x32)
ARGB_HEADERS = {"D_LED1": ("led6", 0x58, 0x01), "D_LED2": ("led7", 0x59, 0x02)}
ARGB_ZONES = {v[0] for v in ARGB_HEADERS.values()}
ARGB_MAX_LEDS = 32
ARGB_FAN_LEDS = 14           # vychozi pocet LED ventilatoru na desce (8. 11. 2026 - LED 15 a 16 nesviti, drive 16)
KEYBOARD = True              # klavesnice G815 (False = skryta v okne i ve vlakne)
EXTRAS = ("grafika", "klavesnice")   # cile s jednou "LED" mimo ventilatory (bez natoceni)
EXTRA_DEFAULT = {"zapnuto": False, "efekt": "deska", "jas": 100, "barva": "#ffffff"}


PLAYLIST_DEFAULT = {"zapnuto": False, "polozky": [], "prolinani": 1.0}
# hudebni vizualizer (stejne jako hudba.LED_DEFAULTS - led.py hudbu nenacita, at nezavisi na numpy)
MUSIC_DEFAULT = {"zapnuto": True, "styl": "pulz", "stridat": False, "styly_stridat": list(fx.MUSIC_STYLES),
                 "citlivost": 5, "basy": 7, "jas": 100,
                 "drop_zablesk": True,                 # duraz na drop: bily zablesk vlnou skrini
                 "barvy": "obal", "citlivost_barev": 7, "doplnit_barvy": True, "paleta": ["#ff2a6d", "#7b2cff", "#05d9e8"],
                 "zpozdeni_ms": 180, "navrat_s": 3, "otoceni": 0}
MAX_REPEATS = 999
MAX_FADE_S = 5.0

# test natoceni z okna nastaveni: na kazdem ventilatoru sviti jen jedna LED - spodek ventilatoru, jak ho
# vidi efekty (svisle efekty s otocenim 0: plameny zacinaji dole), nebo LED obiha od spodku po smeru hodin;
# okno posila natoceni i bez Ulozit a pozadavek obnovuje, jinak po TEST_TIMEOUT_S skonci
TEST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "led_test.json")
TEST_TIMEOUT_S = 15
TEST_TURN_S = 8.0                            # obihani: jedna otacka za 8 s (F140 1 LED/s, deska 2 LED/s)
TEST_COLORS = {"f140_1": (255, 0, 0), "f140_2": (0, 255, 0), "D_LED1": (0, 80, 255), "D_LED2": (255, 200, 0)}
TEST_MODES = {"dole": "svítí spodek", "obiha": "obíhá od spodku po směru hodin"}


def bottom_pos(n):
    """Pozice efektu (0..n-1), kterou efekty berou jako spodek ventilatoru (led_efekty.bottom_led)."""
    return fx.bottom_led(n)


def rainbow(n):
    """n barev duhy po obvodu (pro kruh s n LED)."""
    import colorsys
    out = []
    for i in range(n):
        r, g, b = colorsys.hsv_to_rgb(i / n, 1.0, 1.0)
        out.append(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")
    return out


RAINBOW = rainbow(8)


def default_config():
    zones = {f"led{i}": {"nazev": f"zóna {i}", "rezim": "off", "barva": "#ffffff", "rychlost": "normal"}
             for i in range(1, 9)}
    zones["led6"]["nazev"] = zones["led7"]["nazev"] = "ARGB hlavička"
    return {
        "zapnuto": True,
        "jas": 80,                                 # celkovy jas vsech ventilatoru (%)
        "jas_f140": 100,                           # vyrovnani jasu skupin (%)
        "jas_deska": 100,
        "stejne_pro_vse": True,                    # jeden efekt pro vsechny ventilatory
        "vlna": False,                             # efekt posunuty mezi ventilatory
        "vlna_smer": "dozadu",                     # "dozadu" = od predku skrine dozadu, "dopredu"
        "vlna_f140_spolu": True,                   # F140 ve vlne jako jeden ventilator
        "protismerne": False,                      # ozubena kola: kazdy druhy ventilator zrcadlove (toci se opacne)
        "f140_vpredu": "led1",                    # ktery F140 je bliz predku skrine (led1 / led2)
        "efekt": copy.deepcopy(fx.DEFAULT_EFFECT),
        "efekt_f140": copy.deepcopy(fx.DEFAULT_EFFECT),
        "efekt_deska": copy.deepcopy(fx.DEFAULT_EFFECT),
        "nzxt_stejne": True,                       # vlastni barvy LED: F140 (2) jako F140 (1)
        "nzxt": {"led1": {"nazev": "F140 (1)", "barvy": list(RAINBOW)},
                 "led2": {"nazev": "F140 (2)", "barvy": list(RAINBOW)}},
        "argb": {
            "D_LED1": {"nazev": "2 ventilátory paralelně", "pocet_led": ARGB_FAN_LEDS, "pouzito": True,
                       "barvy": rainbow(ARGB_FAN_LEDS)},
            "D_LED2": {"nazev": "1 ventilátor", "pocet_led": ARGB_FAN_LEDS, "pouzito": True,
                       "barvy": rainbow(ARGB_FAN_LEDS)},
        },
        "fusion": zones,
        # grafika a klavesnice: rizeni z aplikace, efekt "f140" / "deska" (jako ventilatory) / "vlastni",
        # barva = klidny stav po ukonceni aplikace
        "grafika": dict(EXTRA_DEFAULT),
        "efekt_grafika": copy.deepcopy(fx.DEFAULT_EFFECT),
        "klavesnice": dict(EXTRA_DEFAULT),
        # tri nastaveni klavesnice M1-M3 (klavesy_g.py): {"1": {"efekt_klavesnice", "vrstvy_klavesnice"
        # (casti s vlastnim efektem: [{"nazev", "zapnuto", "klavesy": [zony], "efekt"}], dalsi prekryje
        # predchozi), "klavesnice": {"efekt", "jas"}, "klavesy_g": {"1": {"akce", ...}}}, "2": ..., "3": ...}
        "klavesnice_m": {},
        # spolecne pojmenovane predvolby G-klaves: [{"id", "nazev", "cil", "nastaveni"}]
        "predvolby": [],
        # reakce na stisk klaves - nadrazeny efekt pres celou klavesnici (klavesnice_efekty.Engine.reaction)
        "reakce_klavesnice": dict(kbfx.REACTION_DEFAULT),
        # ukazatel hlasitosti na vybranych klavesach po pohybu posuvnikem (hlasitost.py), pro M1-M3 spolecne
        "hlasitost_klavesnice": dict(hlasitost.DEFAULT),
        # playlist efektu: polozky = efekty (jako "efekt") + "opakovani"; strida se dokola v poradi,
        # plati pro vsechny ventilatory (a grafiku / klavesnici s efektem "jako F140 / deska")
        "playlist": copy.deepcopy(PLAYLIST_DEFAULT),
        # hudebni vizualizer: kdyz hraje Spotify, ma prednost pred efektem i playlistem (hudba.py)
        "hudba": copy.deepcopy(MUSIC_DEFAULT),
    }


def gpu_zones(lcfg):
    """Zony desky (mimo ARGB) v rezimu "jako grafika" - sviti stejne jako pasek graficke karty."""
    return sorted(k for k, z in lcfg.get("fusion", {}).items()
                  if k not in ARGB_ZONES and z.get("rezim") == SYNC_ZONE)


def extra_on(lcfg, key):
    """Ridi aplikace grafiku / klavesnici?"""
    if key == "klavesnice" and not KEYBOARD:
        return False
    return bool(lcfg.get(key, {}).get("zapnuto"))


def kb_own(lcfg):
    """Ma klavesnice vlastni plosny efekt po klavesach (ne jednu barvu jako F140 / deska)? Zatim vzdy -
    synchronizaci klavesnice s ventilatory uzivatel 9. 11. 2026 odlozil (volba v okne skryta, "efekt"
    v nastaveni se ignoruje; vetev jedne barvy v render() zustava pro pripadny navrat)."""
    return True


def kb_effect(lcfg):
    """Vlastni efekt klavesnice (klavesnice_efekty), neznamy typ = vychozi."""
    return kbfx.valid(lcfg.get("efekt_klavesnice"))


def kb_layers(lcfg):
    """Zapnute casti klavesnice (vrstvy) s klavesami a znamym efektem."""
    return [v for v in lcfg.get("vrstvy_klavesnice") or []
            if isinstance(v, dict) and v.get("zapnuto", True) and kbfx.part_zones(v)
            and (v.get("efekt") or {}).get("typ") in kbfx.EFFECTS]


def kb_effects(lcfg):
    """Vsechny efekty, ktere klavesnice prave pocita po klavesach (zaklad a casti)."""
    if not extra_on(lcfg, "klavesnice"):
        return []
    out = [kb_effect(lcfg)] if kb_own(lcfg) else []
    return out + [kbfx.valid(v["efekt"]) for v in kb_layers(lcfg)]


def kb_music_on(lcfg):
    """Ma nektery efekt klavesnice (zaklad nebo cast) hudbu - potrebuje zvuk ze Spotify?"""
    return any(kbfx.info(e.get("typ"))[1] == "hudba" for e in kb_effects(lcfg))


def hex_rgb(h):
    return list(fx.hex_rgb(h))


def targets(lcfg):
    """Ventilatory: (klic, pocet LED, skupina, vlastni barvy LED)."""
    nz = lcfg.get("nzxt", {})
    c1 = nz.get("led1", {}).get("barvy", RAINBOW)
    c2 = c1 if lcfg.get("nzxt_stejne", True) else nz.get("led2", {}).get("barvy", RAINBOW)
    out = [("f140_1", LEDS_PER_FAN, "f140", c1), ("f140_2", LEDS_PER_FAN, "f140", c2)]
    for name in ARGB_HEADERS:
        h = lcfg.get("argb", {}).get(name, {})
        if h.get("pouzito", name == "D_LED1"):
            n = max(1, min(ARGB_MAX_LEDS, int(h.get("pocet_led", ARGB_FAN_LEDS))))
            out.append((name, n, "deska", h.get("barvy", rainbow(n))))
    for key in EXTRAS:                                     # grafika / klavesnice = jedna "LED"
        if extra_on(lcfg, key) or (key == "grafika" and gpu_zones(lcfg)):   # i kvuli zonam "jako grafika"
            out.append((key, 1, key, [lcfg.get(key, EXTRA_DEFAULT).get("barva", "#ffffff")]))
    return out


# rozmisteni ve skrini zepredu dozadu: D_LED1 vpredu, 2x F140 uprostred, D_LED2 vzadu; grafika je pod
# F140, ve vlne az za D_LED2 - vlna tak obehne skrin dokola (predek, nahore, zadek, dole) a navaze
# zase na predek (posuny jsou rovnomerne po kruhu 0..1)
CASE_ORDER = ("D_LED1", "F140", "D_LED2", "grafika")
NO_WAVE = ("klavesnice",)


def wave_offsets(lcfg, keys):
    """{klic: posun faze 0..1} pro vlnu podle rozmisteni ve skrini a smeru vlny.
    Vlna jde od ventilatoru s vetsim posunem k mensimu (ten je ve fazi napred)."""
    order = []
    front = "f140_1" if lcfg.get("f140_vpredu", "led1") == "led1" else "f140_2"
    for slot in CASE_ORDER:
        if slot == "F140":
            order += [k for k in (front, "f140_2" if front == "f140_1" else "f140_1") if k in keys]
        elif slot in keys:
            order.append(slot)
    order += [k for k in keys if k not in order]
    pos, n = {}, 0
    for k in order:
        if k.startswith("f140_") and lcfg.get("vlna_f140_spolu", True) and any(
                p.startswith("f140_") for p in pos):
            pos[k] = next(v for p, v in pos.items() if p.startswith("f140_"))    # F140 jako jeden
            continue
        pos[k] = n
        n += 1
    back = lcfg.get("vlna_smer", "dozadu") == "dozadu"
    return {k: ((n - 1 - v) if back else v) / max(1, n) for k, v in pos.items()}, order


# skutecne rozmisteni ve skrini (z fotky z boku 10. 11. 2026; vlevo na fotce zadek s I/O deskou, vpravo
# predek): x 0 = predek .. 1 = zadek, y 0 = nahore .. 1 = dole; (stred x, stred y, polomer x, polomer y, druh)
# - "svisle" = kruh ve svisle rovine (LED dole je dole), "vodorovne" = F140 lezi na stropu (vsechny LED
# ve stejne vysce, kruh se rozprostre dopredu / dozadu - kterym smerem jde "spodek" efektu, je odhad),
# "bod" = jedna LED. Dva ventilatory na D_LED1 jsou nad sebou na jednom kabelu (sviti vzdy stejne) -
# beru je jako jediny ventilator ve stejne vysce jako ten vzadu (prani uzivatele 10. 11. 2026).
CASE_LAYOUT = {
    "D_LED1": (0.08, 0.36, 0.01, 0.17, "svisle"),
    "f140_predni": (0.38, 0.10, 0.14, 0.0, "vodorovne"),
    "f140_zadni": (0.67, 0.10, 0.14, 0.0, "vodorovne"),
    "D_LED2": (0.90, 0.36, 0.05, 0.17, "svisle"),
    "grafika": (0.58, 0.80, 0.0, 0.0, "bod"),
}


def case_points(lcfg, key, n, eff=None):
    """Poloha kazde LED cile ve skrini [(x, y)] (x 0 predek .. 1 zadek, y 0 nahore .. 1 dole) v poradi LED
    efektu (pred natocenim ventilatoru) - pro prostorove styly hudby. None = cil ve skrini neni."""
    if key.startswith("f140_"):
        front = "f140_1" if lcfg.get("f140_vpredu", "led1") == "led1" else "f140_2"
        slot = "f140_predni" if key == front else "f140_zadni"
    else:
        slot = key
    lay = CASE_LAYOUT.get(slot)
    if lay is None:
        return None
    cx, cy, rx, ry, kind = lay
    out = []
    for i in range(n):
        if kind == "bod" or n == 1:
            out.append((cx, cy))
            continue
        a = fx._ring_angle(i, n, eff or {})
        if kind == "vodorovne":
            out.append((cx + rx * math.sin(a), cy))
        else:
            out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


def case_order(lcfg, keys):
    """Cile v poradi ve skrini (predek ... zadek, grafika posledni), kazdy F140 zvlast."""
    return wave_offsets(dict(lcfg, vlna_f140_spolu=False), keys)[1]


def relay_slots(lcfg, keys):
    """{klic: (poradi, pocet pozic)} pro stafetu - poradi ventilatoru jako u vlny (smer vlny, F140
    jako jeden / postupne), ale i kdyz je vlna vypnuta."""
    offs = wave_offsets(lcfg, keys)[0]
    n = len({round(v, 6) for v in offs.values()})
    top = max(offs.values(), default=0.0)
    return {k: (round((top - v) * n), n) for k, v in offs.items()}     # nejvetsi posun jde prvni


def mirrored(lcfg, keys):
    """Ventilatory, ktere se pri "protismerne" (ozubena kola) toci opacne: kazdy druhy v poradi ve skrini."""
    if not lcfg.get("protismerne"):
        return set()
    return {k for i, k in enumerate(case_order(lcfg, keys)) if i % 2}


def effect_for(lcfg, group):
    if group in EXTRAS:                                    # vlastni efekt, nebo jako F140 / deska
        src = lcfg.get(group, {}).get("efekt", "deska")
        if src == "vlastni":
            return lcfg.get(f"efekt_{group}", fx.DEFAULT_EFFECT)
        group = "f140" if src == "f140" else "deska"
    if lcfg.get("stejne_pro_vse", True):
        return lcfg.get("efekt", fx.DEFAULT_EFFECT)
    return lcfg.get(f"efekt_{group}", fx.DEFAULT_EFFECT)


def is_animated(lcfg):
    if any(kbfx.is_animated(e) for e in kb_effects(lcfg)):
        return True
    groups = {g for _k, _n, g, _c in targets(lcfg)}
    items = playlist_items(lcfg)
    if len(items) > 1:                                     # playlist strida efekty
        return True
    return any(fx.animated(items[0] if items and follows_playlist(lcfg, g) else effect_for(lcfg, g))
               for g in groups)


# ----------------------------------------------------------------- playlist

def playlist_items(lcfg):
    """Polozky zapnuteho playlistu (efekty s "opakovani"); prazdny seznam = playlist se nepouziva."""
    pl = lcfg.get("playlist") or {}
    if not pl.get("zapnuto"):
        return []
    return [p for p in pl.get("polozky", []) if isinstance(p, dict) and p.get("typ") in fx.EFFECTS]


def follows_playlist(lcfg, group):
    """Ridi se skupina playlistem? Ventilatory ano, grafika / klavesnice jen s efektem jako F140 / deska."""
    if group in EXTRAS:
        return lcfg.get(group, {}).get("efekt", "deska") != "vlastni"
    return True


def repeats(eff):
    try:
        return max(1, min(MAX_REPEATS, int(eff.get("opakovani", 1))))
    except (TypeError, ValueError):
        return 1


def wave_span(lcfg):
    """Sirka vlny (nejvetsi posun faze) jako v render() - pro delku efektu se setrenim pri vlne."""
    if not lcfg.get("vlna"):
        return 0.0
    offs = wave_offsets(lcfg, [k for k, *_ in targets(lcfg) if k not in NO_WAVE])[0]
    return max(offs.values(), default=0.0)


def playlist_shift(lcfg, t, step):
    """Cas playlistu posunuty na zacatek dalsi (step 1) / predchozi (step -1) polozky."""
    items = playlist_items(lcfg)
    info = playlist_at(lcfg, t)
    if not info:
        return t
    span = wave_span(lcfg)
    durs = [item_duration(e, span) for e in items]
    total = sum(durs)
    if step > 0:
        new = t + info["zbyva"] + 1e-3
    else:
        new = t - info["t"] - durs[(info["i"] - 1) % len(durs)] + 1e-3
    while new < 0:
        new += total
    return new


def item_duration(eff, span=0.0):
    """Delka polozky playlistu (s) = delka jednoho opakovani efektu x pocet opakovani."""
    return fx.cycle_s(eff, span) * repeats(eff)


def playlist_at(lcfg, t, span=None):
    """Co playlist hraje v case t (s od zacatku playlistu), None = playlist vypnuty / prazdny.
    {"i": index, "eff", "t": cas v polozce, "zbyva": s do konce polozky, "pocet": polozek,
     "prev", "t_prev", "k": prolnuti 0..1 z predchozi polozky (jen na zacatku polozky)}.
    Polozky se stridaji dokola; prolnuti probiha na zacatku nove polozky (predchozi efekt
    bezi dal pres svuj konec), celkova delka se tim nemeni."""
    items = playlist_items(lcfg)
    if not items:
        return None
    if span is None:
        span = wave_span(lcfg)
    durs = [item_duration(e, span) for e in items]
    n = len(items)
    x = max(0.0, t) % sum(durs)
    i = 0
    while i < n - 1 and x >= durs[i]:
        x -= durs[i]
        i += 1
    out = {"i": i, "eff": items[i], "t": x, "zbyva": durs[i] - x, "pocet": n}
    try:
        fade = max(0.0, min(MAX_FADE_S, float((lcfg.get("playlist") or {}).get("prolinani", 1.0))))
    except (TypeError, ValueError):
        fade = 0.0
    fade = min(fade, durs[i] / 2)
    if n > 1 and fade > 0 and x < fade and t - x > 1e-6:     # ne u uplne prvni polozky po startu
        p = (i - 1) % n
        u = x / fade
        out.update(prev=items[p], t_prev=durs[p] + x, k=u * u * (3 - 2 * u))
    return out


def orientation(lcfg, key):
    """(posun LED 1, obracene poradi) ventilatoru - aby se efekt na vsech tocil stejne,
    i kdyz ma kazdy ventilator LED 1 jinde nebo LED cislovane opacnym smerem."""
    if key.startswith("f140_"):
        ch = lcfg.get("nzxt", {}).get("led" + key[-1], {})
    else:
        ch = lcfg.get("argb", {}).get(key, {})
    try:
        shift = int(ch.get("posun", 0))
    except (TypeError, ValueError):
        shift = 0
    return shift, bool(ch.get("obracene", False))


def _orient(cols, shift, reverse):
    """Fyzicka LED k dostane barvu z pozice (posun +/- k) efektu."""
    n = len(cols)
    if not n or (shift % n == 0 and not reverse):
        return cols
    sign = -1 if reverse else 1
    return [cols[(shift + sign * k) % n] for k in range(n)]


def _kb_compose(engine, lcfg, base, dt, data, kb_music, kb_over, kb_top=None):
    """Barvy kazde klavesy (poradi kbfx.KEYS, pred jasem): zaklad = vlastni efekt klavesnice (base None)
    nebo jedna barva jako F140 / deska, pres nej casti klavesnice, kontrolky G-klaves (kb_over), reakce
    na stisk (reaction_settings, pres vse) a nakonec ukazatel hlasitosti (kb_top z hlasitost.Overlay.frame
    - ma prednost pred vsim)."""
    kbe = kbfx.engine_for(engine)
    if base is None:
        cols = kbe.frame(kb_effect(lcfg), dt, data, kb_music)
    else:
        kbe.poll()
        cols = [tuple(base)] * len(kbfx.KEYS)
    layers = kb_layers(lcfg)
    if layers or kbe.parts:
        cols = kbe.layers(layers, cols, dt, data, kb_music)
    if kb_over:
        cols = list(cols)
        for z, c in kb_over.items():
            i = kbfx.INDEX.get(z)
            if i is not None:
                cols[i] = c
    rc = kbfx.reaction_settings(lcfg)
    if rc["zapnuto"]:
        cols = kbe.reaction(rc, cols, dt)
    if kb_top:
        cols = hlasitost.compose(cols, kb_top)
    return cols


def render(engine, lcfg, t, data=None, dt=1 / fx.FPS, orient=True, music=None, kb_music=None, kb_over=None,
           kb_top=None):
    """{klic: [[r, g, b] x pocet LED]} s jasem - pro vlakno i nahled v nastaveni.
    orient=False (nahled): bez natoceni ventilatoru, tj. tak, jak ma efekt vypadat.
    music = snimek hudby ze Spotify (hudba.Music.led_snapshot / fx.music_demo): hudebni vizualizer
    pro vsechny cile, music["mix"] 0..1 = prolnuti s beznym efektem.
    Klavesnice s vlastnim efektem: barva kazde klavesy v poradi klavesnice_efekty.KEYS (engine
    klavesnice je kbfx.engine_for(engine)), vizualizer ventilatoru se na ni nepouzije; kb_music =
    snimek zvuku pro jeji hudebni efekty (hudba.Music.kb_snapshot). Casti klavesnice (vrstvy) a kontrolky
    G-klaves kb_over {zona: barva} a ukazatel hlasitosti kb_top se kresli i pres jednu barvu jako F140 / deska."""
    tg = targets(lcfg)
    wave = bool(lcfg.get("vlna"))
    wkeys = [k for k, *_ in tg if k not in NO_WAVE]
    offsets = wave_offsets(lcfg, wkeys)[0] if wave else {}
    span = max(offsets.values(), default=0.0)
    slots = relay_slots(lcfg, wkeys)                       # poradi ve skrini pro stafetu
    flip = mirrored(lcfg, wkeys)                           # ozubena kola: kazdy druhy ventilator zrcadlove
    pl = playlist_at(lcfg, t, span)
    mix = max(0.0, min(1.0, float(music.get("mix", 1.0)))) if music else 0.0
    if mix > 0:
        meff = (lcfg.get("hudba") or {})
        order = case_order(lcfg, wkeys)
        place = {k: i / max(1, len(order) - 1) for i, k in enumerate(order)}      # 0 predek .. 1 zadek
        hop = {k: (i, len(order)) for i, k in enumerate(order)}                   # skakani po skrini
    out = {}
    for idx, (key, n, group, custom) in enumerate(tg):
        if key == "klavesnice" and kb_own(lcfg):
            cols = _kb_compose(engine, lcfg, None, dt, data, kb_music, kb_over, kb_top)
            k = float(lcfg.get("jas", 80)) * float(lcfg.get(group, EXTRA_DEFAULT).get("jas", 100)) / 100.0
            out[key] = fx.apply_brightness(cols, k)
            continue

        def one(eff, tt):
            c = engine.frame(eff, tt, key, n, idx, len(tg), wave, custom, data, dt, offset=offsets.get(key, 0.0),
                             span=span, slot=slots.get(key))
            if eff.get("typ") not in ("vlastni", "vypnuto"):              # vlastni barvy jsou uz po LED
                if key in flip:
                    c = fx.mirror(c)
                if orient:
                    c = _orient(c, *orientation(lcfg, key))
            return c
        if mix >= 1.0:
            cols = None
        elif pl and follows_playlist(lcfg, group):
            cols = one(pl["eff"], pl["t"])
            if "k" in pl:                                  # prolnuti z predchozi polozky playlistu
                old = one(pl["prev"], pl["t_prev"])
                cols = [fx._mix(a, b, pl["k"]) for a, b in zip(old, cols)]
        else:
            cols = one(effect_for(lcfg, group), t)
        if mix > 0:                                        # hudba: uder jde vlnou od ventilatoru, ktery je napred
            delay = (span - offsets.get(key, 0.0)) / span if wave and span > 0 else 0.0
            mc = engine.music(meff, music, key, n, place.get(key, 0.0), delay, dt, slot=hop.get(key),
                              pts=case_points(lcfg, key, n, meff))
            if key in flip:
                mc = fx.mirror(mc)
            if orient:
                mc = _orient(mc, *orientation(lcfg, key))
            cols = mc if cols is None else [fx._mix(a, b, mix) for a, b in zip(cols, mc)]
        if key == "klavesnice" and (kb_over or kb_top or kb_layers(lcfg)
                                    or kbfx.reaction_settings(lcfg)["zapnuto"]):
            cols = _kb_compose(engine, lcfg, cols[0], dt, data, kb_music, kb_over, kb_top)
        if group in EXTRAS:
            k = float(lcfg.get("jas", 80)) * float(lcfg.get(group, EXTRA_DEFAULT).get("jas", 100)) / 100.0
        else:
            k = float(lcfg.get("jas", 80)) * float(lcfg.get(f"jas_{group}", 100)) / 100.0
        out[key] = fx.apply_brightness(cols, k)
    return out


# ----------------------------------------------------------------- test natoceni

def _test_orient(lcfg, test):
    """Konfigurace s natocenim z pozadavku testu (z okna, i neulozene)."""
    out = dict(lcfg)
    for grp in ("nzxt", "argb"):
        src = (test or {}).get(grp)
        if not isinstance(src, dict):
            continue
        merged = dict(lcfg.get(grp, {}))
        for ch, o in src.items():
            if isinstance(o, dict):
                merged[ch] = dict(merged.get(ch, {}), posun=o.get("posun", 0), obracene=bool(o.get("obracene")))
        out[grp] = merged
    return out


def test_frame(lcfg, test, t, orient=True):
    """Snimek testu natoceni: na kazdem ventilatoru jedna LED v jeho barve (TEST_COLORS).
    "dole" = spodek ventilatoru (kde zacinaji plameny), "obiha" = LED obiha od spodku po smeru
    hodin (spodek -> vlevo -> nahore -> vpravo). orient=False (nahled) = jak to ma vypadat.
    Grafika / klavesnice zhasnute."""
    lc = _test_orient(lcfg, test)
    mode = (test or {}).get("rezim", "dole")
    out = {}
    for key, n, group, _c in targets(lc):
        cols = [[0, 0, 0] for _ in range(n)]
        if group not in EXTRAS:
            pos = bottom_pos(n)
            if mode == "obiha":
                pos = (pos + int(max(0.0, t) / TEST_TURN_S * n)) % n
            cols[pos] = list(TEST_COLORS.get(key, (255, 255, 255)))
            if orient:
                cols = _orient(cols, *orientation(lc, key))
        out[key] = cols
    return out


def request_test(lcfg, mode):
    """Pozadat bezici aplikaci o test natoceni (okno ho obnovuje, jinak po TEST_TIMEOUT_S skonci)."""
    req = {"rezim": mode, "do": time.time() + TEST_TIMEOUT_S,
           "nzxt": {k: {"posun": v.get("posun", 0), "obracene": bool(v.get("obracene"))}
                    for k, v in lcfg.get("nzxt", {}).items() if isinstance(v, dict)},
           "argb": {k: {"posun": v.get("posun", 0), "obracene": bool(v.get("obracene"))}
                    for k, v in lcfg.get("argb", {}).items() if isinstance(v, dict)}}
    tmp = TEST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(req, f)
    os.replace(tmp, TEST_FILE)


def stop_test():
    try:
        os.remove(TEST_FILE)
    except OSError:
        pass


def read_test():
    """Platny pozadavek testu natoceni, nebo None (prosly se smaze)."""
    if not os.path.exists(TEST_FILE):
        return None
    try:
        with open(TEST_FILE, encoding="utf-8") as f:
            req = json.load(f)
        if float(req.get("do", 0)) > time.time() and req.get("rezim") in TEST_MODES:
            return req
    except (OSError, ValueError, TypeError, AttributeError):
        return None                              # okno zrovna zapisuje - priste znovu
    stop_test()
    return None


# ----------------------------------------------------------------- hardware

def argb_order(report):
    """Pozice bajtu R, G, B pro hlavicky D_LED1/2 z odpovedi na 0x60 (kalibrace, typicky GRB)."""
    import struct
    out = {}
    for name, off in (("D_LED1", 44), ("D_LED2", 48)):
        v = struct.unpack_from("<I", bytes(report), off)[0]
        order = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
        out[name] = order if sorted(order) == [0, 1, 2] else (1, 0, 2)    # nesmysl -> GRB
    return out


def _argb_report(dev):
    for _ in range(3):
        dev.send_feature_report([0xCC, 0x60] + [0] * 62)
        r = dev.get_feature_report(0xCC, 64)
        if len(r) >= 52 and r[0] in (0xCC, 0) and r[1] == 0x01:
            return r
        time.sleep(0.3)
    return None


def _argb_strip(dev, cmd, colors, order):
    """Barvy po LED na hlavicku (po 19 LED v jednom paketu)."""
    sent = 0
    for i in range(0, len(colors), 19):
        chunk = colors[i:i + 19]
        pkt = [0] * 64
        pkt[0], pkt[1], pkt[2], pkt[3], pkt[4] = 0xCC, cmd, sent & 0xFF, sent >> 8, len(chunk) * 3
        for j, (r, g, b) in enumerate(chunk):
            o = 5 + j * 3
            pkt[o + order[0]], pkt[o + order[1]], pkt[o + order[2]] = r, g, b
        dev.send_feature_report(pkt)
        sent += len(chunk) * 3


def _zone_fixed(dev, zone, rgb):
    """Cela zona desky (male LED, 12V RGB) jednou barvou - stejny paket jako liquidctl
    set_color(zone, "fixed"): registr 0x20+n s maskou zony, barva v poradi B G R, jas 90,
    pak 0x28 = pouzit nastaveni a znovu maska primeho rezimu ARGB (0x32), at ji to nezmeni."""
    import liquidctl.driver.rgb_fusion2 as rf
    addr1, addr2 = rf._COLOR_CHANNELS[zone]
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    data = [0xCC, addr1, addr2] + [0] * 8 + [0x01, 90, 0x00, b, g, r]
    dev.send_feature_report(data + [0] * (64 - len(data)))
    dev.send_feature_report([0xCC, 0x28, 0xFF] + [0] * 61)
    dev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)


def _devices():
    import kraken  # noqa: F401  oprava GUID pred prvnim importem liquidctl
    from liquidctl import find_liquidctl_devices
    nzxt = fusion = None
    for d in find_liquidctl_devices():
        if "NZXT 2023 RGB" in d.description:
            nzxt = d
        elif "Fusion" in d.description:
            fusion = d
    return nzxt, fusion


def _init(dev, tries=3):
    for _ in range(tries):                         # Fusion obcas napoprve odpovi nesmyslem
        try:
            return dev.initialize()
        except AssertionError:
            time.sleep(0.3)
    return dev.initialize()


class Session:
    """Otevrena spojeni s radici a posilani snimku. Kazdy radic zvlast: kdyz jeden chybi
    nebo selze, druhy jede dal a chybejici se zkusi pripojit znovu (retry_missing)."""

    NAMES = {"nzxt": "NZXT RGB Controller (F140)", "fusion": "Gigabyte RGB Fusion (ventilátory na desce)",
             "grafika": "grafická karta", "klavesnice": "klávesnice G815"}

    def __init__(self, lcfg):
        self.nzxt = self.fusion = self.fdev = None
        self.kbd = None                           # klavesnice.Direct, kdyz ji aplikace ridi
        self.kb_retry_at = 0.0                    # kdy zkusit klavesnici znovu po chybe
        self.gpu = None                           # grafika.Gpu, kdyz ji aplikace ridi
        self.sync_zones = gpu_zones(lcfg)         # zony desky "jako grafika"
        self.orders = {k: (1, 0, 2) for k in ARGB_HEADERS}
        self.errors = {}                          # radic -> chyba
        self.last = {}
        self.retry_missing(lcfg)
        self.setup_keyboard(lcfg)
        self.setup_gpu(lcfg)

    def setup_gpu(self, lcfg):
        """LED graficke karty (I2C pres NvAPI): prevzit / pustit. Pri vypnuti rizeni zustane
        klidna barva - vlastni nastaveni karty se vrati az po restartu PC."""
        if not extra_on(lcfg, "grafika"):
            if self.gpu is not None and self.gpu.ok:
                try:
                    self.gpu.color(hex_rgb(lcfg.get("grafika", {}).get("barva", "#ffffff")), True)
                except Exception:
                    pass
                self.gpu.stop()
            self.gpu = None
            self.errors.pop("grafika", None)
            return
        if self.gpu is None:
            import grafika
            self.gpu = grafika.Gpu()
        try:
            if self.gpu.start():
                self.errors.pop("grafika", None)
                self.last.pop("grafika", None)
        except Exception as e:
            self.errors["grafika"] = str(e)

    def setup_keyboard(self, lcfg):
        """Klavesnice G815 primo pres HID++: prevzit (vypne pamet) / vratit (zapne integrovanou pamet)."""
        want = extra_on(lcfg, "klavesnice")
        if not want:
            if self.kbd is not None:
                self.kbd.stop()                   # klavesnice zpet na integrovanou pamet
                self.kbd = None
            self.errors.pop("klavesnice", None)
            return
        if self.kbd is None:
            import klavesnice
            self.kbd = klavesnice.Direct()
        try:
            if self.kbd.start():
                self.errors.pop("klavesnice", None)
        except Exception as e:
            self._kb_error(e)

    def _kb_error(self, e):
        """Chyba klavesnice: kdy to zkusit znovu (nenalezena 2 s, jinak 10 / 30 s - klavesnice.retry_after)."""
        import klavesnice
        secs, text = klavesnice.retry_after(e)
        self.errors["klavesnice"] = text
        self.kb_retry_at = time.monotonic() + secs

    def retry_keyboard(self, lcfg):
        """Klavesnici zkusit znovu, kdyz uz je cas (vlastni casovani - ne po RETRY_S jako radice)."""
        if "klavesnice" in self.errors and time.monotonic() >= self.kb_retry_at:
            self.setup_keyboard(lcfg)
            if "klavesnice" not in self.errors:
                self.last.pop("klavesnice", None)          # poslat klavesnici cely snimek
                return True
        return False

    def retry_missing(self, lcfg):
        """Pripojit radice, ktere zatim nejedou. Vrati True, kdyz nejaky pribyl."""
        if "grafika" in self.errors:
            self.setup_gpu(lcfg)
        if self.nzxt is not None and self.fusion is not None:
            return False
        try:
            nzxt, fusion = _devices()
        except Exception as e:
            for k in ("nzxt", "fusion"):
                if getattr(self, k) is None:
                    self.errors[k] = f"hledání řadičů: {e}"
            return False
        added = False
        if self.nzxt is None:
            if nzxt is None:
                self.errors["nzxt"] = "nenalezen"
            else:
                try:
                    nzxt.connect()
                    _init(nzxt)
                    nzxt.set_color("led3", "off", [])                     # volny kanal zhasnout
                    self.nzxt, added = nzxt, True
                    self.errors.pop("nzxt", None)
                except Exception as e:
                    self._drop_dev(nzxt)
                    self.errors["nzxt"] = str(e)
        if self.fusion is None:
            if fusion is None:
                self.errors["fusion"] = "nenalezen"
            else:
                try:
                    fusion.connect()
                    _init(fusion)
                    self.fusion, self.fdev = fusion, fusion.device
                    self.setup_zones(lcfg)
                    report = _argb_report(self.fdev)
                    if report:
                        self.orders = argb_order(report)
                    self.fdev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)   # D_LED1+2 primy rezim
                    time.sleep(0.05)
                    added = True
                    self.errors.pop("fusion", None)
                except Exception as e:
                    self._drop_dev(fusion)
                    self.fusion = self.fdev = None
                    self.errors["fusion"] = str(e)
        if added:
            self.last = {}                        # novemu radici poslat cely snimek
        return added

    @staticmethod
    def _drop_dev(d):
        try:
            d.disconnect()
        except Exception:
            pass

    def _fail(self, which, e):
        """Chyba jednoho radice: odpojit jen ten, druhy jede dal."""
        if which in EXTRAS:
            dev = self.kbd if which == "klavesnice" else self.gpu
            if dev is not None:
                dev.stop()
            self.errors[which] = str(e)
            secs = RETRY_S
            if which == "klavesnice":
                self._kb_error(e)
                secs = round(self.kb_retry_at - time.monotonic())
            log.warning("LED: %s – %s, zkusím znovu za %d s.", self.NAMES[which], self.errors[which], secs)
            return
        self._drop_dev(getattr(self, which))
        setattr(self, which, None)
        if which == "fusion":
            self.fdev = None
        self.errors[which] = str(e)
        log.warning("LED: %s – %s, zkusím znovu za %d s.", self.NAMES[which], e, RETRY_S)

    @property
    def running(self):
        return self.nzxt is not None or self.fusion is not None or (self.gpu is not None and self.gpu.ok)

    def error_text(self):
        return [f"{self.NAMES[k]}: {v}" for k, v in sorted(self.errors.items())]

    def setup_zones(self, lcfg):
        """Ostatni zony desky (male LED, 12V RGB) - jedna barva / efekt cipu."""
        self.sync_zones = gpu_zones(lcfg)          # "jako grafika" - barvu posila send() po snimcich
        self.last.pop("grafika", None)
        if self.fusion is None:
            return
        for name, z in sorted(lcfg.get("fusion", {}).items()):
            if name in ARGB_ZONES or name in self.sync_zones:
                continue
            mode = z.get("rezim", "off")
            _n, takes_color, has_speed = FUSION_MODES.get(mode, FUSION_MODES["off"])
            cols = [hex_rgb(z.get("barva", "#ffffff"))] if takes_color else []
            speed = z.get("rychlost", "normal") if has_speed else "normal"
            if mode == "double-flash" and speed == "slower":
                speed = "normal"                    # v liquidctl 1.16 preklep v nazvu rychlosti
            self.fusion.set_color(name, mode, cols, speed=speed)
        self.fdev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)       # liquidctl mohl masku zmenit
    def send(self, frame, force=False):
        """Poslat jen to, co se zmenilo (force = vse). Chyba jednoho radice nezastavi druhy."""
        f1, f2 = frame.get("f140_1"), frame.get("f140_2")
        if self.nzxt is not None and f1 is not None:
            if force or f1 != self.last.get("f140_1") or f2 != self.last.get("f140_2"):
                try:
                    if f1 == f2:
                        self.nzxt.set_color("sync", "super-fixed", f1)
                    else:
                        self.nzxt.set_color("led1", "super-fixed", f1)
                        self.nzxt.set_color("led2", "super-fixed", f2)
                except Exception as e:
                    self._fail("nzxt", e)
        if self.fdev is not None:
            try:
                for name, (_zone, cmd, _bit) in ARGB_HEADERS.items():
                    cols = frame.get(name)
                    if cols is None:                                      # nepouzita hlavicka = zhasnout
                        if force:
                            _argb_strip(self.fdev, cmd, [[0, 0, 0]] * ARGB_MAX_LEDS, self.orders[name])
                        continue
                    if force or cols != self.last.get(name):
                        pad = [[0, 0, 0]] * (ARGB_MAX_LEDS - len(cols))
                        _argb_strip(self.fdev, cmd, cols + pad, self.orders[name])
                gp = frame.get("grafika")                                 # zony "jako grafika"
                if gp and self.sync_zones and (force or gp != self.last.get("grafika")):
                    for zone in self.sync_zones:
                        _zone_fixed(self.fdev, zone, gp[0])
            except Exception as e:
                self._fail("fusion", e)
        kb = frame.get("klavesnice")
        if self.kbd is not None and self.kbd.ok and kb:
            try:
                if len(kb) == 1:
                    self.kbd.color(kb[0], force)
                elif force or kb != self.last.get("klavesnice"):
                    self.kbd.keys(dict(zip(kbfx.ZONES, kb)), force)
            except Exception as e:
                self._fail("klavesnice", e)
        gp = frame.get("grafika")
        if self.gpu is not None and self.gpu.ok and gp:
            try:
                self.gpu.color(gp[0], force)
            except Exception as e:
                self._fail("grafika", e)
        self.last = frame

    def close(self):
        if self.gpu is not None:
            self.gpu.stop()                       # karta drzi posledni poslanou barvu
            self.gpu = None
        if self.kbd is not None:
            self.kbd.stop()                       # klavesnice zpet na integrovanou pamet
            self.kbd = None
        for d in (self.nzxt, self.fusion):
            if d is not None:
                try:
                    d.disconnect()
                except Exception:
                    pass


def _still(lcfg, typ):
    """Staticky stav vsech ventilatoru: "vlastni" = vlastni barvy LED, "vypnuto" = zhasnuto.
    Plati i pro grafiku / klavesnici (jejich vlastni efekt se pri tom nepouzije)."""
    extras = {k: dict(lcfg[k], efekt="deska") for k in EXTRAS if isinstance(lcfg.get(k), dict)}
    return dict(lcfg, stejne_pro_vse=True, efekt={"typ": typ}, playlist=None, **extras)


class LedWorker(threading.Thread):
    def __init__(self):
        super().__init__(name="led", daemon=True)
        self._lock = threading.Lock()
        self._cfg = None
        self._data = {}
        self._quit = threading.Event()
        self._wake = threading.Event()
        self._off_req = threading.Event()    # uspani: zhasnout a do probuzeni nic neposilat
        self._off_done = threading.Event()
        self._resume = threading.Event()
        self._shutdown = False               # konci Windows: LED zhasnout (ne klidny stav)
        self.music = None                    # hudba.Music - hudebni vizualizer, kdyz hraje Spotify
        self.gkeys = klavesy_g.State()       # co je zapnute klavesami G1-G5 (jen v pameti)
        self.vol = hlasitost.Overlay()       # ukazatel hlasitosti na klavesnici (kdy ukazat)
        self.volume = None                   # hlasitost Windows (hlasitost.Volume, otevre se pri prvnim pouziti)
        self.state = {"stav": "čeká"}

    def update(self, lcfg, data=None):
        with self._lock:
            self._cfg = lcfg
            if data is not None:
                self._data = data
        self._wake.set()

    def blackout(self, timeout=1.5):
        """PC se uspava: zhasnout LED. Deska drzi hlavicku ARGB pod napetim i ve spanku
        a ve vypnutem PC, takze by na ventilatorech zustal zamrzly posledni snimek."""
        if not self.is_alive():
            return
        self._off_done.clear()
        self._resume.clear()
        self._off_req.set()
        self._wake.set()
        self._off_done.wait(timeout)

    def resume(self):
        self._resume.set()
        self._wake.set()

    def stop(self, timeout=1.0, off=False):
        """off=True (vypnuti PC, odhlaseni): LED zhasnout; jinak klidny stav (vlastni barvy)."""
        self._shutdown = off
        self._quit.set()
        self._wake.set()
        self.join(timeout)

    def _keyboard_hook(self, engine, want, on):
        """Sledovani stisku klaves (reakce podsviceni, posuvnik hlasitosti) zapnout / vypnout. Vrati stav."""
        if want == on:
            return on
        import klavesy_stisk
        kb = kbfx.engine_for(engine)
        if want:
            try:
                w = klavesy_stisk.start()
                w.on_volume = w.on_key = self._wake.set  # posuvnik hlasitosti / stisk = hned novy snimek
                kb.source = w.drain
            except Exception as e:
                log.warning("Klávesnice: sledování kláves nejde – %s", e)
                kb.source = None
                return True                      # nezkouset znovu kazdy snimek
        else:
            kb.source = None
            klavesy_stisk.stop()
        return want

    def _set_state(self, state):
        if state.get("stav") != self.state.get("stav") or state.get("chyby") != self.state.get("chyby"):
            if state.get("stav") == "chyba":
                log.warning("LED: %s", "; ".join(state.get("chyby", [])))
            elif state.get("stav") == "běží" and state.get("chyby"):
                log.warning("LED: běží jen část – %s", "; ".join(state["chyby"]))
            elif state.get("stav") == "běží":
                log.info("LED: efekty běží.")
        self.state = state

    def run(self):
        engine = fx.Engine()
        session, hw_key, t0 = None, None, time.monotonic()
        pl_key = None                            # zmena playlistu (po Ulozit) = playlist od zacatku
        snap, music_err, music_fps, frames, fps_t = None, None, None, 0, time.monotonic()
        last_exc = None
        test_mode, test_t0 = None, 0.0           # bezici test natoceni (rezim) a jeho zacatek
        hook_on = False                          # sleduji se stisky klaves (reakce klavesnice)
        base_ref, base_key = None, None          # nastaveni z okna - po zmene konci predvolba / sada (klavesy_g)
        last_wall, last_force, prev, last_retry = time.time(), 0.0, time.monotonic(), time.monotonic()
        while not self._quit.is_set():
            with self._lock:
                lcfg, data = self._cfg, self._data
            if lcfg is None or not lcfg.get("zapnuto", True):
                if session:
                    # rizeni LED vypnuto: klidny stav (vlastni barvy), at nezustane zamrzly snimek
                    try:
                        session.send(render(engine, _still(lcfg, "vlastni"), 0.0), force=True)
                    except Exception:
                        pass
                    session.close()
                    session = None
                    log.info("LED: řízení vypnuto – ventilátory mají vlastní barvy LED.")
                hook_on = self._keyboard_hook(engine, False, hook_on)
                if lcfg is not None:
                    self._set_state({"stav": "vypnuto"})
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            if self._off_req.is_set():
                self._off_req.clear()
                if session:
                    try:
                        session.send(render(engine, _still(lcfg, "vypnuto"), 0.0), force=True)
                    except Exception:
                        pass
                    session.close()
                    session = None
                self._off_done.set()
                log.info("LED: PC se uspava - LED zhasnute.")
                # do probuzeni nic neposilat; kdyby se uspani nepovedlo, po 2 min pokracovat
                deadline = time.time() + 120
                while not (self._quit.is_set() or self._resume.is_set()) and time.time() < deadline:
                    self._quit.wait(1.0)
                last_wall = time.time()
                continue
            now_wall, now = time.time(), time.monotonic()
            base_cfg = lcfg                              # nastaveni z okna (profily M1-M3, bez predvoleb G)
            if base_cfg is not base_ref:                 # nove nastaveni z okna (po Ulozit)
                k_base = json.dumps(base_cfg, sort_keys=True, default=str)
                if base_key is not None and k_base != base_key:
                    self.gkeys.reset_selection()
                base_ref, base_key = base_cfg, k_base
            kbd = session.kbd if session is not None else None
            if kbd is not None:
                kbd.want_g = True
                kbd.on_gkey = self._wake.set             # stisk G / M = hned novy snimek
                for kind, n in kbd.g_drain():
                    if kind == "G":
                        cmd = self.gkeys.press(n, base_cfg, (self.state.get("hudba") or {}).get("styl"))
                        if cmd and cmd[0] == "pl":
                            cur = self.gkeys.apply(base_cfg)
                            if playlist_items(cur):
                                t0 = now - playlist_shift(cur, now - t0, cmd[1])
                                info = playlist_at(cur, now - t0)
                                log.info("G%d: playlist LED – %s (%d/%d).", n,
                                         fx.EFFECTS.get(info["eff"].get("typ"), ("?",))[0], info["i"] + 1,
                                         info["pocet"])
                            else:
                                log.info("G%d: playlist LED je vypnutý.", n)
                        elif cmd and cmd[0] == "lcd" and self.music is not None:
                            self.music.toggle_lcd()
                    elif kind == "M":
                        self.gkeys.press_m(n, base_cfg, self.gkeys.apply(base_cfg))
                    elif kind == "MR":
                        self.gkeys.press_mr()
                kbd.m_want = self.gkeys.m_leds(now)
            lcfg = self.gkeys.apply(base_cfg)
            resumed = now_wall - last_wall > RESUME_GAP_S
            last_wall = now_wall
            k_pl = json.dumps(lcfg.get("playlist"), sort_keys=True)
            if k_pl != pl_key:
                if pl_key is not None and playlist_items(lcfg):
                    t0 = now
                    log.info("LED: playlist efektů (%d) od začátku.", len(playlist_items(lcfg)))
                pl_key = k_pl
            key = json.dumps({"z": lcfg.get("fusion"), "a": lcfg.get("argb"),
                              "k": extra_on(lcfg, "klavesnice"), "g": extra_on(lcfg, "grafika")}, sort_keys=True)
            try:
                if session is None or resumed:
                    if session:
                        session.close()
                    if resumed:
                        log.info("LED: PC se probudilo - nastavuji LED znovu.")
                    session = Session(lcfg)
                    hw_key, last_force, last_retry = key, 0.0, now
                    if not session.running:              # nejede ani jeden radic
                        raise RuntimeError("; ".join(session.error_text()))
                elif session.retry_keyboard(lcfg):            # klavesnice ma kratsi casovani
                    pass
                elif session.errors and now - last_retry > RETRY_S:
                    last_retry = now                     # chybejici radic zkusit znovu, druhy jede dal
                    if session.retry_missing(lcfg):
                        hw_key, last_force = key, 0.0
                elif key != hw_key:
                    try:
                        session.setup_zones(lcfg)
                    except Exception as e:
                        session._fail("fusion", e)
                    session.setup_keyboard(lcfg)              # klavesnice prevzata / vracena na pamet
                    session.setup_gpu(lcfg)                   # grafika zapnuta / vypnuta
                    hw_key, last_force = key, 0.0
                dt, prev = now - prev, now
                snap = None
                test = read_test()
                if test is not None:                     # test natoceni z okna: jen jedna LED
                    if test_mode is None:
                        log.info("LED: test natočení (%s).", TEST_MODES[test["rezim"]])
                        test_t0 = now
                    elif test["rezim"] != test_mode:
                        test_t0 = now
                    test_mode = test["rezim"]
                    force = now - last_force > REFRESH_S
                    session.send(test_frame(lcfg, test, now - test_t0), force)
                    if force:
                        last_force = now
                    if not session.running:
                        raise RuntimeError("; ".join(session.error_text()))
                    st = {"stav": "běží", "test": test_mode}
                    if session.errors:
                        st["chyby"] = session.error_text()
                    self._set_state(st)
                    self._quit.wait(0.1)
                    continue
                if test_mode is not None:
                    test_mode = None
                    log.info("LED: test natočení skončil.")
                if self.music is not None:
                    try:
                        snap = self.music.led_snapshot(lcfg.get("hudba"))
                    except Exception as e:                # chyba hudby nesmi zastavit LED
                        if str(e) != music_err:
                            music_err = str(e)
                            log.warning("LED: hudba – %s", e)
                kb_snap = None
                vcfg = hlasitost.settings(lcfg)
                vol_on = bool(vcfg["zapnuto"]) and extra_on(lcfg, "klavesnice")
                react_on = kbfx.reaction_settings(lcfg)["zapnuto"] and extra_on(lcfg, "klavesnice")
                hook_on = self._keyboard_hook(engine, react_on or vol_on, hook_on)
                kb_top = None
                if vol_on:
                    import klavesy_stisk
                    w = klavesy_stisk._watcher
                    if w is not None and w.drain_volume():
                        self.vol.trigger(now)
                    if self.vol.busy(vcfg, now):
                        if self.volume is None:
                            self.volume = hlasitost.Volume()
                        cur = self.volume.read()
                        if cur is not None:
                            kb_top = self.vol.frame(vcfg, now, *cur)
                if self.music is not None:            # hudebni efekty klavesnice chteji zvuk i bez vizualizeru
                    self.music.extra_audio = kb_music_on(lcfg)
                    if self.music.extra_audio:
                        try:
                            kb_snap = self.music.kb_snapshot()
                        except Exception:
                            kb_snap = None
                lcd_on = self.music is not None and self.music.lcd_active() is not None
                kb_over = self.gkeys.leds(base_cfg, now, lcd_on) if extra_on(lcfg, "klavesnice") else None
                frame = render(engine, lcfg, now - t0, data, min(dt, 0.2), music=snap, kb_music=kb_snap,
                               kb_over=kb_over, kb_top=kb_top)
                force = now - last_force > REFRESH_S
                session.send(frame, force)
                if force:
                    last_force = now
                if not session.running:                  # oba radice selhaly za behu
                    raise RuntimeError("; ".join(session.error_text()))
                st = {"stav": "běží", "chyby": session.error_text()} if session.errors else {"stav": "běží"}
                pl = playlist_at(lcfg, now - t0)
                if pl:                                   # co prave hraje (okno nastaveni)
                    st["playlist"] = {"i": pl["i"], "pocet": pl["pocet"], "typ": pl["eff"].get("typ"),
                                      "zbyva": round(pl["zbyva"])}
                if extra_on(lcfg, "klavesnice"):
                    st["klavesy_g"] = self.gkeys.status(base_cfg)
                if snap is not None:
                    st["hudba"] = {"styl": fx.music_style(lcfg.get("hudba") or {}, snap), "mix": round(snap["mix"], 2)}
                    frames += 1
                    if now - fps_t >= 60:                # skutecna snimkova frekvence s hudbou (do logu 1x za minutu)
                        if music_fps is None or abs(frames / (now - fps_t) - music_fps) > 5:
                            music_fps = frames / (now - fps_t)
                            log.info("LED: hudba %.0f snímků/s.", music_fps)
                        frames, fps_t = 0, now
                else:
                    frames, fps_t = 0, now
                self._set_state(st)
            except Exception as e:
                if str(e) != last_exc:                   # podrobny vypis do logu (jednou), at jde najit misto
                    last_exc = str(e)
                    log.error("LED: %s – podrobně:", e, exc_info=True)
                if session:
                    session.close()
                    session = None
                self._set_state({"stav": "chyba", "chyby": [str(e)]})
                self._quit.wait(RETRY_S)
                last_wall = time.time()                  # cekani po chybe neni probuzeni PC
                continue
            if snap is not None:                         # hudba: plynulejsi (udery jsou kratke)
                self._quit.wait(max(0.0, 1 / fx.MUSIC_FPS - (time.monotonic() - now)))
            elif (is_animated(lcfg) or self.gkeys.busy() or self.vol.busy(hlasitost.settings(lcfg), time.monotonic())
                  or kbfx.engine_for(engine).reacting(kbfx.reaction_settings(lcfg))):
                self._quit.wait(max(0.0, 1 / fx.FPS - (time.monotonic() - now)))
            else:
                self._wake.wait(1.0)
                self._wake.clear()
        self._keyboard_hook(engine, False, hook_on)
        # konec aplikace: klidny staticky stav (vlastni barvy LED s nastavenym jasem);
        # pri vypnuti PC zhasnout - deska drzi ARGB pod napetim i ve vypnutem PC
        if session:
            try:
                session.send(render(engine, _still(lcfg, "vypnuto" if self._shutdown else "vlastni"), 0.0),
                             force=True)
            except Exception:
                pass
            session.close()
