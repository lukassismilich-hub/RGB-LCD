# klavesy_g.py - klavesy G1-G5 na klavesnici G815: predvolby efektu a hudba ze Spotify
#
# config["led"]["klavesy_g"] = {"1": {"akce": ..., ...}, ... "5": {...}}:
#   "predvolba" + "cil" (klavesnice / ventilatory / vse) + "nastaveni" = ulozene nastaveni efektu
#               (snapshot() z okna); stisk = prepnout na predvolbu, stejna G-klavesa znovu = zpet na
#               nastaveni z okna, jina G-klavesa s predvolbou prepne rovnou na svou
#   "hudba"     = hudebni vizualizer ze Spotify zapnout / vypnout
#   "styl"      = dalsi styl vizualizeru (kdyz je vypnuty, zapne ho)
# Stav (State) drzi jen bezici aplikace v pameti - nic se neuklada, po startu plati nastaveni z okna.
# Stisky G-klaves cte klavesnice.Direct (HID++ 0x8010, softwarove ovladani G-klaves).
# Kontrolky: prirazena G-klavesa sviti tlumene bile, zapnuta (aktivni predvolba, zapnuta hudba) naplno.

import copy
import logging
import time

import led_efekty as fx

log = logging.getLogger("rgb_lcd")

KEYS = (1, 2, 3, 4, 5)
ZONE = {n: 179 + n for n in KEYS}                 # zony podsviceni G1-G5 (0x8081)
ACTIONS = [("", "nic"), ("predvolba", "předvolba efektu"), ("hudba", "hudba ze Spotify zap. / vyp."),
           ("styl", "další styl hudby")]
TARGETS = [("klavesnice", "klávesnice"), ("ventilatory", "ventilátory a grafika"), ("vse", "vše")]
# co patri do predvolby: klice config["led"] a vybrane polozky vnorenych slovniku
PARTS = {
    "klavesnice": (("efekt_klavesnice", "vrstvy_klavesnice"), {"klavesnice": ("efekt",)}),
    "ventilatory": (("stejne_pro_vse", "efekt", "efekt_f140", "efekt_deska", "playlist", "vlna", "vlna_smer",
                     "vlna_f140_spolu", "efekt_grafika"), {"grafika": ("efekt",)}),
}
LIT = (255, 255, 255)                             # kontrolka zapnuto
IDLE = (45, 45, 45)                               # prirazena, vypnuto
FLASH_S = 0.35                                    # bliknuti po stisku (dalsi styl hudby)


def actions(lcfg):
    """{cislo G-klavesy: nastaveni akce} - jen prirazene."""
    out = {}
    for n in KEYS:
        a = ((lcfg or {}).get("klavesy_g") or {}).get(str(n))
        if isinstance(a, dict) and a.get("akce") in {k for k, _t in ACTIONS if k}:
            out[n] = a
    return out


def _parts(cil):
    return ("klavesnice", "ventilatory") if cil == "vse" else (cil,) if cil in PARTS else ()


def snapshot(lcfg, cil):
    """Nastaveni efektu pro predvolbu (kopie z config["led"])."""
    out = {}
    for part in _parts(cil):
        keys, subs = PARTS[part]
        for k in keys:
            if k in lcfg:
                out[k] = copy.deepcopy(lcfg[k])
        for k, sub in subs.items():
            src = lcfg.get(k) or {}
            out[k] = {s: copy.deepcopy(src[s]) for s in sub if s in src}
    return out


def overlay(lcfg, preset):
    """Nastaveni s predvolbou (novy slovnik, puvodni lcfg se nemeni)."""
    a = preset or {}
    snap = a.get("nastaveni") or {}
    out = dict(lcfg)
    for part in _parts(a.get("cil")):
        keys, subs = PARTS[part]
        for k in keys:
            if k in snap:
                out[k] = snap[k]
        for k in subs:
            if isinstance(snap.get(k), dict):
                out[k] = dict(out.get(k) or {}, **snap[k])
    return out


def load(lcfg, preset):
    """Predvolbu nacist do nastaveni (okno - upravit a ulozit znovu)."""
    new = overlay(lcfg, preset)
    for k, v in new.items():
        lcfg[k] = copy.deepcopy(v)


def describe(preset):
    """Kratky popis predvolby pro okno."""
    import klavesnice_efekty as kbfx
    a = preset or {}
    snap = a.get("nastaveni")
    if not snap:
        return "zatím neuložená"
    out = []
    parts = [x for x in _parts(a.get("cil")) if any(k in snap for k in PARTS[x][0])]
    if "klavesnice" in parts:
        src = (snap.get("klavesnice") or {}).get("efekt", "vlastni")
        if src == "vlastni":
            txt = kbfx.info((snap.get("efekt_klavesnice") or {}).get("typ"))[0]
        else:
            txt = "jako F140" if src == "f140" else "jako deska"
        n = sum(1 for v in snap.get("vrstvy_klavesnice") or [] if isinstance(v, dict) and v.get("zapnuto", True))
        out.append(f"klávesnice: {txt}" + (f" + části: {n}" if n else ""))
    if "ventilatory" in parts:
        pl = snap.get("playlist") or {}
        if pl.get("zapnuto") and pl.get("polozky"):
            txt = f"playlist ({len(pl['polozky'])})"
        elif snap.get("stejne_pro_vse", True):
            txt = fx.EFFECTS.get((snap.get("efekt") or {}).get("typ"), ("?",))[0]
        else:
            txt = " / ".join(fx.EFFECTS.get((snap.get(k) or {}).get("typ"), ("?",))[0]
                             for k in ("efekt_f140", "efekt_deska"))
        out.append(f"ventilátory: {txt}")
    return "; ".join(out) or "uložená pro jiný cíl – ulož znovu"


class State:
    """Co je prave zapnute G-klavesami (jen v pameti bezici aplikace)."""

    def __init__(self):
        self.active = None                        # cislo G-klavesy s aktivni predvolbou
        self.music = None                         # vizualizer zapnuty / vypnuty G-klavesou (None = jak v okne)
        self.style = None                         # styl vizualizeru vybrany G-klavesou
        self.flash = {}                           # {cislo: cas stisku}

    def press(self, n, lcfg, cur_style=None):
        """Stisk G-klavesy n (lcfg = nastaveni z okna, bez predvoleb)."""
        a = actions(lcfg).get(n)
        self.flash[n] = time.monotonic()
        if a is None:
            return
        kind = a["akce"]
        if kind == "predvolba":
            if self.active == n or not a.get("nastaveni"):
                self.active = None
                log.info("G%d: zpět na nastavení z okna.", n)
            else:
                self.active = n
                log.info("G%d: předvolba – %s.", n, describe(a))
        elif kind == "hudba":
            on = not self.music_on(lcfg)
            saved = bool((lcfg.get("hudba") or {}).get("zapnuto"))
            self.music = None if on == saved else on
            log.info("G%d: hudba ze Spotify %s.", n, "zapnuta" if on else "vypnuta")
        elif kind == "styl":
            if not self.music_on(lcfg):
                self.music = None if (lcfg.get("hudba") or {}).get("zapnuto") else True
                log.info("G%d: hudba ze Spotify zapnuta.", n)
                return
            h = self.apply(lcfg).get("hudba") or {}
            pool = fx.style_pool(h) if len(fx.style_pool(h)) > 1 else list(fx.MUSIC_STYLES)
            cur = cur_style or h.get("styl", "pulz")
            self.style = pool[(pool.index(cur) + 1) % len(pool)] if cur in pool else pool[0]
            log.info("G%d: styl hudby – %s.", n, fx.MUSIC_STYLES.get(self.style, self.style))

    def music_on(self, lcfg):
        if self.music is not None:
            return self.music
        return bool((lcfg.get("hudba") or {}).get("zapnuto"))

    def apply(self, lcfg):
        """Nastaveni s tim, co je zapnute G-klavesami (novy slovnik; bez zmen = lcfg)."""
        acts = actions(lcfg)
        out = lcfg
        if self.active is not None:
            a = acts.get(self.active)
            if a is None or a["akce"] != "predvolba" or not a.get("nastaveni"):
                self.active = None                  # predvolba v okne zrusena / zmenena
            else:
                out = overlay(out, a)
        if self.music is not None or self.style is not None:
            h = dict(out.get("hudba") or {})
            if self.music is not None:
                h["zapnuto"] = self.music
            if self.style is not None:
                h["styl"], h["stridat"] = self.style, False
            out = dict(out, hudba=h)
        return out

    def leds(self, lcfg, now=None):
        """Kontrolky G-klaves {zona: (r, g, b)} (pred jasem) - jen prirazene klavesy."""
        now = time.monotonic() if now is None else now
        out = {}
        for n, a in actions(lcfg).items():
            kind = a["akce"]
            lit = ((kind == "predvolba" and self.active == n) or (kind == "hudba" and self.music_on(lcfg))
                   or now - self.flash.get(n, -9.0) < FLASH_S)
            out[ZONE[n]] = LIT if lit else IDLE
        return out

    def flashing(self, now=None):
        now = time.monotonic() if now is None else now
        return any(now - t < FLASH_S for t in self.flash.values())

    def status(self):
        return {"aktivni": self.active, "hudba": self.music, "styl": self.style}
