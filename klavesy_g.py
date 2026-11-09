# klavesy_g.py - klavesy G1-G5, M1-M3 a MR na klavesnici G815
#
# config["led"]["klavesy_g"] = {"1": {"akce": ..., ...}, ... "5": {...}} - akce G-klaves:
#   "predvolba" + "cil" (klavesnice / ventilatory / vse) + "nastaveni" = vlastni nastaveni efektu
#               (klavesnici upravuje okno primo - "Nastavuji: predvolba Gn", ventilatory se prevezmou
#               ze stranky LED); stisk = prepnout na predvolbu, stejna G-klavesa znovu = zpet,
#               jina G-klavesa s predvolbou prepne rovnou na svou
#   "hudba"     = hudebni vizualizer ze Spotify zapnout / vypnout
#   "styl"      = dalsi styl vizualizeru (kdyz je vypnuty, zapne ho)
#   "pl_dalsi" / "pl_predchozi" = playlist LED ventilatoru na dalsi / predchozi efekt
#   "playlist"  = playlist LED ventilatoru zapnout / vypnout
#   "lcd"       = obrazovka "Prave hraje" na LCD Krakenu ukazat (na dobu z nastaveni) / schovat
#   osvetleni klavesy (light()): "svetlo" kontrolka / efekt (klavesa sviti podle efektu), "barva_zap"
#   (funkce zapnuta), "barva_vyp", "blik" + "barva_blik" = bliknuti pri stisku
# Sady M1-M3 (soubor sady_klavesnice.json, ne config.json - uklada je i bezici aplikace z klavesnice):
#   cele nastaveni klavesnice = podsviceni (efekt, casti, jas) i akce a osvetleni G-klaves (PARTS["sada"]).
#   M1 = vyvolat sadu, stejna M znovu = zpet na nastaveni z okna; MR a pak M1-M3 (do 10 s) = ulozit
#   prave svitici nastaveni klavesnice do sady (MR znovu = zrusit). Kontrolky M1-M3 / MR ukazuji
#   aktivni sadu / ukladani.
# Stav (State) drzi jen bezici aplikace v pameti - po startu plati nastaveni z okna. Ulozeni zmeny
# v okne (vlakno LED pozna nove nastaveni) vrati predvolbu i sadu na nastaveni z okna (reset_selection).
# Stisky cte klavesnice.Direct (HID++ 0x8010 / 0x8020 / 0x8030 se softwarovym ovladanim G-klaves).

import copy
import json
import logging
import os
import time

import led_efekty as fx

log = logging.getLogger("rgb_lcd")

KEYS = (1, 2, 3, 4, 5)
M_KEYS = (1, 2, 3)
ZONE = {n: 179 + n for n in KEYS}                 # zony podsviceni G1-G5 (0x8081)
ACTIONS = [("", "nic"), ("predvolba", "předvolba efektu"), ("hudba", "hudba ze Spotify zap. / vyp."),
           ("styl", "další styl hudby"), ("pl_dalsi", "playlist LED – další efekt"),
           ("pl_predchozi", "playlist LED – předchozí efekt"), ("playlist", "playlist LED zap. / vyp."),
           ("lcd", "skladba na LCD Krakenu")]
TOGGLES = ("predvolba", "hudba", "playlist", "lcd")   # akce se stavem zapnuto / vypnuto
TARGETS = [("klavesnice", "klávesnice"), ("ventilatory", "ventilátory a grafika"), ("vse", "vše")]
# co patri do predvolby / sady: klice config["led"] a vybrane polozky vnorenych slovniku
PARTS = {
    "klavesnice": (("efekt_klavesnice", "vrstvy_klavesnice"), {"klavesnice": ("efekt", "jas")}),
    "ventilatory": (("stejne_pro_vse", "efekt", "efekt_f140", "efekt_deska", "playlist", "vlna", "vlna_smer",
                     "vlna_f140_spolu", "efekt_grafika"), {"grafika": ("efekt",)}),
    "sada": (("efekt_klavesnice", "vrstvy_klavesnice", "klavesy_g"), {"klavesnice": ("efekt", "jas")}),
}
LIGHT_DEFAULT = {"svetlo": "kontrolka", "barva_zap": "#ffffff", "barva_vyp": "#2d2d2d", "blik": True,
                 "barva_blik": "#ffffff"}
FLASH_S = 0.35                                    # bliknuti po stisku: 0,08 s tma, pak barva bliknuti
FLASH_DARK_S = 0.08
RECORD_S = 10.0                                   # MR: do kdy stisknout M1-M3
SETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sady_klavesnice.json")
_sets_cache = (None, {})                          # (mtime, sady)


def actions(lcfg):
    """{cislo G-klavesy: nastaveni akce} - jen prirazene."""
    out = {}
    valid = {k for k, _t in ACTIONS if k}
    for n in KEYS:
        a = ((lcfg or {}).get("klavesy_g") or {}).get(str(n))
        if isinstance(a, dict) and a.get("akce") in valid:
            out[n] = a
    return out


def light(a):
    """Osvetleni G-klavesy (s vychozimi hodnotami)."""
    return {k: (a or {}).get(k, v) for k, v in LIGHT_DEFAULT.items()}


def _parts(cil):
    return ("klavesnice", "ventilatory") if cil == "vse" else (cil,) if cil in PARTS else ()


def snapshot(lcfg, cil):
    """Nastaveni efektu pro predvolbu / sadu (kopie z config["led"])."""
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


def has_keyboard(a):
    """Meni predvolba podsviceni klavesnice?"""
    return (a or {}).get("akce") == "predvolba" and (a or {}).get("cil", "klavesnice") in ("klavesnice", "vse")


def has_fans(a):
    return (a or {}).get("akce") == "predvolba" and (a or {}).get("cil") in ("ventilatory", "vse")


def ensure_keyboard(a, lcfg):
    """Predvolba bez nastaveni klavesnice ho dostane z okna (zacatek upravy). Vrati slovnik nastaveni."""
    a.setdefault("cil", "klavesnice")
    snap = a.get("nastaveni")
    if not isinstance(snap, dict):
        snap = a["nastaveni"] = {}
    keys, _subs = PARTS["klavesnice"]
    if any(k not in snap for k in keys):
        base = snapshot(lcfg, "klavesnice")
        for k in keys:
            if k not in snap and k in base:
                snap[k] = base[k]
    kc = snap.get("klavesnice")
    if not isinstance(kc, dict):
        kc = snap["klavesnice"] = {}
    src = lcfg.get("klavesnice") or {}
    kc.setdefault("efekt", src.get("efekt", "vlastni"))
    kc.setdefault("jas", src.get("jas", 100))
    return snap


def take_fans(a, lcfg):
    """Do predvolby prevzit nastaveni ventilatoru ze stranky LED (klavesnice v predvolbe zustane)."""
    snap = a.get("nastaveni")
    if not isinstance(snap, dict):
        snap = a["nastaveni"] = {}
    snap.update(snapshot(lcfg, "ventilatory"))


def overlay(lcfg, preset):
    """Nastaveni s predvolbou / sadou (novy slovnik, puvodni lcfg se nemeni)."""
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
    """Predvolbu / sadu nacist do nastaveni (okno - upravit a ulozit znovu)."""
    new = overlay(lcfg, preset)
    for k, v in new.items():
        lcfg[k] = copy.deepcopy(v)


def _kb_text(snap):
    import klavesnice_efekty as kbfx
    src = (snap.get("klavesnice") or {}).get("efekt", "vlastni")
    if src == "vlastni":
        txt = kbfx.info((snap.get("efekt_klavesnice") or {}).get("typ"))[0]
    else:
        txt = "jako F140" if src == "f140" else "jako deska"
    n = sum(1 for v in snap.get("vrstvy_klavesnice") or [] if isinstance(v, dict) and v.get("zapnuto", True))
    return txt + (f" + části: {n}" if n else "")


def describe(preset):
    """Kratky popis predvolby pro okno."""
    a = preset or {}
    snap = a.get("nastaveni") or {}
    out = []
    for x in _parts(a.get("cil", "klavesnice")):
        if not any(k in snap for k in PARTS[x][0]):
            out.append("klávesnice: zatím nenastavená" if x == "klavesnice" else
                       "ventilátory: zatím nepřevzaté ze stránky LED")
        elif x == "klavesnice":
            jas = (snap.get("klavesnice") or {}).get("jas")
            out.append("klávesnice: " + _kb_text(snap) + (f", jas {jas} %" if jas is not None else ""))
        else:
            pl = snap.get("playlist") or {}
            if pl.get("zapnuto") and pl.get("polozky"):
                txt = f"playlist ({len(pl['polozky'])})"
            elif snap.get("stejne_pro_vse", True):
                txt = fx.EFFECTS.get((snap.get("efekt") or {}).get("typ"), ("?",))[0]
            else:
                txt = " / ".join(fx.EFFECTS.get((snap.get(k) or {}).get("typ"), ("?",))[0]
                                 for k in ("efekt_f140", "efekt_deska"))
            out.append(f"ventilátory: {txt}")
    return "; ".join(out)


# ----------------------------------------------------------------- sady M1-M3

def load_sets():
    """{cislo M: {"nastaveni", "ulozeno"}} ze sady_klavesnice.json (cte znovu jen po zmene souboru)."""
    global _sets_cache
    try:
        mt = os.path.getmtime(SETS_FILE)
    except OSError:
        _sets_cache = (None, {})
        return {}
    if mt != _sets_cache[0]:
        try:
            with open(SETS_FILE, encoding="utf-8") as f:
                raw = json.load(f)
            sets = {int(k): v for k, v in raw.items()
                    if str(k).isdigit() and int(k) in M_KEYS and isinstance(v, dict) and v.get("nastaveni")}
        except (OSError, ValueError) as e:
            log.warning("Sady klávesnice (M1–M3) nejde načíst: %s", e)
            sets = _sets_cache[1]
        _sets_cache = (mt, sets)
    return _sets_cache[1]


def _write_sets(sets):
    tmp = SETS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(sets.items())}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETS_FILE)


def save_set(n, lcfg):
    """Nastaveni klavesnice z lcfg ulozit do sady Mn."""
    sets = dict(load_sets())
    sets[n] = {"nastaveni": snapshot(lcfg, "sada"), "ulozeno": time.strftime("%d. %m. %Y %H:%M")}
    _write_sets(sets)


def delete_set(n):
    sets = dict(load_sets())
    if sets.pop(n, None) is not None:
        _write_sets(sets)


def set_preset(s):
    return {"cil": "sada", "nastaveni": (s or {}).get("nastaveni") or {}}


def describe_set(s):
    snap = (s or {}).get("nastaveni")
    if not snap:
        return "prázdná"
    acts = [f"G{n}" for n in actions(snap)]
    return (f"klávesnice: {_kb_text(snap)}; jas {(snap.get('klavesnice') or {}).get('jas', 100)} %; "
            + ("G-klávesy: " + ", ".join(acts) if acts else "G-klávesy bez akcí")
            + (f" (uloženo {s['ulozeno']})" if s.get("ulozeno") else ""))


# ----------------------------------------------------------------- stav

class State:
    """Co je prave zapnute klavesami G / M (jen v pameti bezici aplikace)."""

    def __init__(self):
        self.active = None                        # cislo G-klavesy s aktivni predvolbou
        self.mset = None                          # aktivni sada M1-M3
        self.record_until = 0.0                   # MR: ukladani do sady ceka na M1-M3
        self.music = None                         # vizualizer zapnuty / vypnuty G-klavesou (None = jak v okne)
        self.style = None                         # styl vizualizeru vybrany G-klavesou
        self.playlist = None                      # playlist zapnuty / vypnuty G-klavesou
        self.flash = {}                           # {cislo G: cas stisku}

    # --- nastaveni
    def with_set(self, base):
        """Nastaveni z okna s aktivni sadou M (klavesnice a akce G-klaves)."""
        if self.mset is None:
            return base
        s = load_sets().get(self.mset)
        if s is None:
            self.mset = None                        # sada smazana
            return base
        return overlay(base, set_preset(s))

    def _with_preset(self, cfg):
        if self.active is None:
            return cfg
        a = actions(cfg).get(self.active)
        if a is None or a["akce"] != "predvolba" or not a.get("nastaveni"):
            self.active = None                      # predvolba zrusena / zmenena
            return cfg
        return overlay(cfg, a)

    def apply(self, base):
        """Nastaveni s tim, co je zapnute klavesami (novy slovnik; bez zmen = base)."""
        out = self._with_preset(self.with_set(base))
        if self.music is not None or self.style is not None:
            h = dict(out.get("hudba") or {})
            if self.music is not None:
                h["zapnuto"] = self.music
            if self.style is not None:
                h["styl"], h["stridat"] = self.style, False
            out = dict(out, hudba=h)
        if self.playlist is not None:
            out = dict(out, playlist=dict(out.get("playlist") or {}, zapnuto=self.playlist))
        return out

    def reset_selection(self):
        """V okne ulozena zmena: predvolba i sada zpet na nastaveni z okna."""
        if self.active is not None or self.mset is not None:
            self.active = self.mset = None
            log.info("Klávesnice: uloženo nové nastavení – zpět na nastavení z okna (předvolba / sada vypnuta).")

    # --- stisky
    def press(self, n, base, cur_style=None):
        """Stisk G-klavesy n (base = nastaveni z okna). Vrati prikaz pro vlakno LED, nebo None:
        ("pl", +1 / -1) = playlist o polozku dal / zpet, ("lcd",) = skladba na LCD ukazat / schovat."""
        cfg = self.with_set(base)
        a = actions(cfg).get(n)
        self.flash[n] = time.monotonic()
        if a is None:
            return None
        kind = a["akce"]
        if kind == "predvolba":
            if self.active == n or not a.get("nastaveni"):
                self.active = None
                log.info("G%d: zpět na nastavení %s.", n, f"sady M{self.mset}" if self.mset else "z okna")
            else:
                self.active = n
                log.info("G%d: předvolba – %s.", n, describe(a))
        elif kind == "hudba":
            on = not self.music_on(cfg)
            saved = bool((cfg.get("hudba") or {}).get("zapnuto"))
            self.music = None if on == saved else on
            log.info("G%d: hudba ze Spotify %s.", n, "zapnuta" if on else "vypnuta")
        elif kind == "styl":
            if not self.music_on(cfg):
                self.music = None if (cfg.get("hudba") or {}).get("zapnuto") else True
                log.info("G%d: hudba ze Spotify zapnuta.", n)
                return None
            h = self.apply(base).get("hudba") or {}
            pool = fx.style_pool(h) if len(fx.style_pool(h)) > 1 else list(fx.MUSIC_STYLES)
            cur = cur_style or h.get("styl", "pulz")
            self.style = pool[(pool.index(cur) + 1) % len(pool)] if cur in pool else pool[0]
            log.info("G%d: styl hudby – %s.", n, fx.MUSIC_STYLES.get(self.style, self.style))
        elif kind == "playlist":
            eff = self._with_preset(cfg)
            on = not self.playlist_on(eff)
            saved = bool((eff.get("playlist") or {}).get("zapnuto"))
            self.playlist = None if on == saved else on
            log.info("G%d: playlist LED %s.", n, "zapnut" if on else "vypnut")
        elif kind in ("pl_dalsi", "pl_predchozi"):
            return ("pl", 1 if kind == "pl_dalsi" else -1)
        elif kind == "lcd":
            return ("lcd",)
        return None

    def press_m(self, n, base, current):
        """Stisk M-klavesy n; current = prave platne nastaveni (apply) - pro ulozeni po MR."""
        now = time.monotonic()
        if now < self.record_until:
            self.record_until = 0.0
            cfg = self.with_set(base)
            snap = dict(cfg)                        # podsviceni, jak prave sviti; akce G-klaves ze sady / okna
            for k in ("efekt_klavesnice", "vrstvy_klavesnice", "klavesnice"):
                if k in current:
                    snap[k] = current[k]
            save_set(n, snap)
            self.mset, self.active = n, None
            log.info("M%d: uloženo současné nastavení klávesnice (%s).", n, describe_set(load_sets().get(n)))
            return
        if self.mset == n:
            self.mset = None
            log.info("M%d: zpět na nastavení z okna.", n)
        elif load_sets().get(n) is None:
            log.info("M%d: sada je prázdná – MR a pak M%d do ní uloží současné nastavení.", n, n)
        else:
            self.mset, self.active = n, None
            log.info("M%d: sada – %s.", n, describe_set(load_sets().get(n)))

    def press_mr(self):
        if time.monotonic() < self.record_until:
            self.record_until = 0.0
            log.info("MR: ukládání do sady zrušeno.")
        else:
            self.record_until = time.monotonic() + RECORD_S
            log.info("MR: stiskni M1–M3 – uloží se do ní současné nastavení klávesnice.")

    # --- stav pro kontrolky
    def music_on(self, cfg):
        if self.music is not None:
            return self.music
        return bool((cfg.get("hudba") or {}).get("zapnuto"))

    def playlist_on(self, cfg):
        if self.playlist is not None:
            return self.playlist
        return bool((cfg.get("playlist") or {}).get("zapnuto"))

    def recording(self, now=None):
        return (time.monotonic() if now is None else now) < self.record_until

    def m_leds(self, now=None):
        """(maska kontrolek M1-M3, kontrolka MR): aktivni sada; pri ukladani (MR) blikaji vsechny M."""
        now = time.monotonic() if now is None else now
        if self.recording(now):
            return (7 if int(now * 3) % 2 else 0), True
        return (1 << (self.mset - 1) if self.mset else 0), False

    def leds(self, base, now=None, lcd_on=False):
        """Osvetleni G-klaves {zona: (r, g, b)} (pred jasem) podle nastaveni kazde G-klavesy."""
        now = time.monotonic() if now is None else now
        cfg = self.with_set(base)
        eff = self.apply(base)
        out = {}
        for n, a in actions(cfg).items():
            L = light(a)
            kind = a["akce"]
            on = ((kind == "predvolba" and self.active == n) or (kind == "hudba" and self.music_on(cfg))
                  or (kind == "playlist" and self.playlist_on(eff)) or (kind == "lcd" and lcd_on))
            col = None
            if L["svetlo"] == "kontrolka":
                col = fx.hex_rgb(L["barva_zap"] if on else L["barva_vyp"])
            age = now - self.flash.get(n, -9.0)
            if L["blik"] and age < FLASH_S:
                col = (0, 0, 0) if age < FLASH_DARK_S else fx.hex_rgb(L["barva_blik"])
            if col is not None:
                out[ZONE[n]] = tuple(col)
        return out

    def busy(self, now=None):
        """Bezi neco, co chce dalsi snimky (bliknuti, ukladani do sady)?"""
        now = time.monotonic() if now is None else now
        return self.recording(now) or any(now - t < FLASH_S for t in self.flash.values())

    def status(self):
        return {"aktivni": self.active, "sada": self.mset, "hudba": self.music, "styl": self.style,
                "playlist": self.playlist, "uklada": self.recording()}
