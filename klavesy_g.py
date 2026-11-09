# klavesy_g.py - klavesy G1-G5, M1-M3 a MR na klavesnici G815
#
# Tri nastaveni klavesnice M1-M3 (config["led"]["klavesnice_m"] = {"1": profil, "2": ..., "3": ...}),
# klavesnice je vzdy v jednom z nich (M = prepnout, kontrolka sviti u aktivniho; posledni pouzite se
# pamatuje v klavesnice_m.json - zapisuje bezici aplikace). Profil = podsviceni (PROFILE_KEYS: efekt,
# casti, "klavesnice": efekt / jas) a akce i osvetleni G1-G5 ("klavesy_g" = {"1": {"akce", ...}}).
# Spolecny seznam pojmenovanych predvoleb (config["led"]["predvolby"] = [{"id", "nazev", "cil",
# "nastaveni"}]) - v kazdem M si G-klavesa vybere kteroukoli ("akce": "predvolba", "predvolba": id).
# Akce G-klaves:
#   "predvolba" = prepnout na predvolbu (klavesnice / ventilatory / vse podle "cil" predvolby), stejna
#               G-klavesa znovu = zpet na nastaveni M, jina G-klavesa s predvolbou prepne rovnou na svou
#   "hudba"     = hudebni vizualizer ze Spotify zapnout / vypnout
#   "styl"      = dalsi styl vizualizeru (kdyz je vypnuty, zapne ho)
#   "pl_dalsi" / "pl_predchozi" = playlist LED ventilatoru na dalsi / predchozi efekt
#   "playlist"  = playlist LED ventilatoru zapnout / vypnout
#   "lcd"       = obrazovka "Prave hraje" na LCD Krakenu ukazat (na dobu z nastaveni) / schovat
#   osvetleni klavesy (light()): "svetlo" kontrolka / efekt (klavesa sviti podle efektu), "barva_zap"
#   (funkce zapnuta), "barva_vyp", "blik" + "barva_blik" = bliknuti pri stisku
# Stav (State): aktivni M (soubor), predvolba, hudba, playlist jen v pameti. Ulozeni zmeny v okne vypne
# predvolbu (reset_selection). Stary format (jedno nastaveni + sady_klavesnice.json + predvolby ulozene
# primo u G-klavesy) prevede migrate() pri nacteni configu.
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
ACTIONS = [("", "nic"), ("predvolba", "předvolba"), ("hudba", "hudba ze Spotify zap. / vyp."),
           ("styl", "další styl hudby"), ("pl_dalsi", "playlist LED – další efekt"),
           ("pl_predchozi", "playlist LED – předchozí efekt"), ("playlist", "playlist LED zap. / vyp."),
           ("lcd", "skladba na LCD Krakenu")]
TOGGLES = ("predvolba", "hudba", "playlist", "lcd")   # akce se stavem zapnuto / vypnuto
TARGETS = [("klavesnice", "klávesnice"), ("ventilatory", "ventilátory a grafika"), ("vse", "vše")]
# co patri do predvolby: klice config["led"] a vybrane polozky vnorenych slovniku
PARTS = {
    "klavesnice": (("efekt_klavesnice", "vrstvy_klavesnice"), {"klavesnice": ("efekt", "jas")}),
    "ventilatory": (("stejne_pro_vse", "efekt", "efekt_f140", "efekt_deska", "playlist", "vlna", "vlna_smer",
                     "vlna_f140_spolu", "efekt_grafika"), {"grafika": ("efekt",)}),
}
PROFILE_KEYS = ("efekt_klavesnice", "vrstvy_klavesnice", "klavesy_g")   # + "klavesnice": efekt, jas
LIGHT_DEFAULT = {"svetlo": "kontrolka", "barva_zap": "#ffffff", "barva_vyp": "#2d2d2d", "blik": True,
                 "barva_blik": "#ffffff"}
FLASH_S = 0.35                                    # bliknuti po stisku: 0,08 s tma, pak barva bliknuti
FLASH_DARK_S = 0.08
_DIR = os.path.dirname(os.path.abspath(__file__))
M_FILE = os.path.join(_DIR, "klavesnice_m.json")  # posledni pouzite M (zapisuje bezici aplikace)
OLD_SETS_FILE = os.path.join(_DIR, "sady_klavesnice.json")   # stary format sad M1-M3 (jen migrace)


# ----------------------------------------------------------------- profily M1-M3

def default_profile():
    import klavesnice_efekty as kbfx
    return {"efekt_klavesnice": kbfx.default_effect("vlna"), "vrstvy_klavesnice": [], "klavesy_g": {},
            "klavesnice": {"efekt": "vlastni", "jas": 100}}


def profiles(lcfg):
    """{"1": profil, "2": ..., "3": ...} z config["led"] (chybejici doplni - zapisuje do lcfg)."""
    p = lcfg.get("klavesnice_m")
    if not isinstance(p, dict):
        p = lcfg["klavesnice_m"] = {}
    for m in M_KEYS:
        prof = p.get(str(m))
        if not isinstance(prof, dict):
            prof = p[str(m)] = default_profile()
        d = None
        for k in PROFILE_KEYS:
            if k not in prof:
                d = d or default_profile()
                prof[k] = d[k]
        kc = prof.get("klavesnice")
        if not isinstance(kc, dict):
            kc = prof["klavesnice"] = {}
        kc.setdefault("efekt", "vlastni")
        kc.setdefault("jas", 100)
    return p


def profile(lcfg, m):
    return profiles(lcfg)[str(m if m in M_KEYS else 1)]


def with_profile(lcfg, m):
    """Nastaveni z okna s profilem Mm (novy slovnik, lcfg se nemeni - jen chybejici profily doplni)."""
    prof = profile(lcfg, m)
    out = dict(lcfg)
    for k in PROFILE_KEYS:
        out[k] = prof[k]
    out["klavesnice"] = dict(lcfg.get("klavesnice") or {}, **prof["klavesnice"])
    return out


def copy_profile(lcfg, src, dst):
    profiles(lcfg)[str(dst)] = copy.deepcopy(profile(lcfg, src))


def describe_profile(prof):
    acts = [f"G{n}" for n in actions(prof)]
    return (f"{_kb_text(prof)}; jas {(prof.get('klavesnice') or {}).get('jas', 100)} %; "
            + ("G-klávesy: " + ", ".join(acts) if acts else "G-klávesy bez akcí"))


def load_m():
    """Posledni pouzite M (1-3)."""
    try:
        with open(M_FILE, encoding="utf-8") as f:
            m = int(json.load(f).get("m", 1))
        return m if m in M_KEYS else 1
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


def save_m(m):
    try:
        tmp = M_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"m": m}, f)
        os.replace(tmp, M_FILE)
    except OSError as e:
        log.warning("Klávesnice: aktivní M nejde uložit: %s", e)


# ----------------------------------------------------------------- predvolby

def presets(lcfg):
    """Spolecny seznam pojmenovanych predvoleb (zapisuje do lcfg, kdyz chybi)."""
    v = lcfg.get("predvolby")
    if not isinstance(v, list):
        v = lcfg["predvolby"] = []
    return v


def preset_by_id(lcfg, pid):
    return next((p for p in presets(lcfg) if isinstance(p, dict) and p.get("id") == pid), None)


def new_preset(lcfg, name=None):
    ps = presets(lcfg)
    pid = max([p.get("id", 0) for p in ps if isinstance(p, dict)] + [0]) + 1
    names = {p.get("nazev") for p in ps if isinstance(p, dict)}
    n = len(ps) + 1
    while name is None or name in names:
        name, n = f"Předvolba {n}", n + 1
    p = {"id": pid, "nazev": name, "cil": "klavesnice", "nastaveni": {}}
    ps.append(p)
    return p


def preset_name(p):
    return str((p or {}).get("nazev") or f"Předvolba {(p or {}).get('id', '?')}")


def actions(lcfg):
    """{cislo G-klavesy: nastaveni akce} - jen prirazene (lcfg = profil nebo nastaveni s profilem)."""
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


def has_keyboard(p):
    """Meni predvolba podsviceni klavesnice?"""
    return (p or {}).get("cil", "klavesnice") in ("klavesnice", "vse")


def has_fans(p):
    return (p or {}).get("cil") in ("ventilatory", "vse")


def snapshot(lcfg, cil):
    """Nastaveni efektu pro predvolbu (kopie z nastaveni s profilem)."""
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


def ensure_keyboard(p, cfg):
    """Predvolba bez nastaveni klavesnice ho dostane z cfg (nastaveni s profilem M). Vrati nastaveni."""
    snap = p.get("nastaveni")
    if not isinstance(snap, dict):
        snap = p["nastaveni"] = {}
    keys, _subs = PARTS["klavesnice"]
    if any(k not in snap for k in keys):
        base = snapshot(cfg, "klavesnice")
        for k in keys:
            if k not in snap and k in base:
                snap[k] = base[k]
    kc = snap.get("klavesnice")
    if not isinstance(kc, dict):
        kc = snap["klavesnice"] = {}
    src = cfg.get("klavesnice") or {}
    kc.setdefault("efekt", src.get("efekt", "vlastni"))
    kc.setdefault("jas", src.get("jas", 100))
    return snap


def take_fans(p, lcfg):
    """Do predvolby prevzit nastaveni ventilatoru ze stranky LED (klavesnice v predvolbe zustane)."""
    snap = p.get("nastaveni")
    if not isinstance(snap, dict):
        snap = p["nastaveni"] = {}
    snap.update(snapshot(lcfg, "ventilatory"))


def overlay(lcfg, p):
    """Nastaveni s predvolbou (novy slovnik, puvodni lcfg se nemeni)."""
    p = p or {}
    snap = p.get("nastaveni") or {}
    out = dict(lcfg)
    for part in _parts(p.get("cil", "klavesnice")):
        keys, subs = PARTS[part]
        for k in keys:
            if k in snap:
                out[k] = snap[k]
        for k in subs:
            if isinstance(snap.get(k), dict):
                out[k] = dict(out.get(k) or {}, **snap[k])
    return out


def _kb_text(snap):
    import klavesnice_efekty as kbfx
    txt = kbfx.info((snap.get("efekt_klavesnice") or {}).get("typ"))[0]   # "jako F140 / deska" zatim neni
    n = sum(1 for v in snap.get("vrstvy_klavesnice") or [] if isinstance(v, dict) and v.get("zapnuto", True))
    return txt + (f" + části: {n}" if n else "")


def describe(p):
    """Kratky popis predvolby pro okno."""
    p = p or {}
    snap = p.get("nastaveni") or {}
    out = []
    for x in _parts(p.get("cil", "klavesnice")):
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


def users(lcfg, pid):
    """Kde je predvolba prirazena: ["M1 G2", ...]."""
    out = []
    for m in M_KEYS:
        for n, a in actions(profile(lcfg, m)).items():
            if a["akce"] == "predvolba" and a.get("predvolba") == pid:
                out.append(f"M{m} G{n}")
    return out


# ----------------------------------------------------------------- migrace stareho formatu

def migrate(lcfg):
    """Stary format -> M1-M3 + spolecne predvolby. M1 = dosavadni nastaveni z okna, M2 / M3 = sady ze
    sady_klavesnice.json (jinak kopie M1); predvolby ulozene u G-klaves se stanou pojmenovanymi.
    Vrati True, kdyz neco prevedl."""
    done = isinstance(lcfg.get("klavesnice_m"), dict) and lcfg["klavesnice_m"]
    if done or not any(k in lcfg for k in PROFILE_KEYS):
        for k in PROFILE_KEYS:
            lcfg.pop(k, None)
        profiles(lcfg)
        presets(lcfg)
        return False
    seen = {}                                     # json nastaveni -> id (stejna predvolba ve vic sadach)

    def conv(src, label):
        prof = default_profile()
        for k in ("efekt_klavesnice", "vrstvy_klavesnice"):
            if k in src:
                prof[k] = copy.deepcopy(src[k])
        kc = src.get("klavesnice") or {}
        for k in ("efekt", "jas"):
            if k in kc:
                prof["klavesnice"][k] = kc[k]
        g = {}
        for n, a in (src.get("klavesy_g") or {}).items():
            if not isinstance(a, dict):
                continue
            a = copy.deepcopy(a)
            snap, cil = a.pop("nastaveni", None), a.pop("cil", None)
            if a.get("akce") == "predvolba":
                key = json.dumps([cil, snap], sort_keys=True)
                if key not in seen:
                    p = new_preset(lcfg, f"Předvolba z G{n}" + ("" if label == "M1" else f" ({label})"))
                    p["cil"] = cil or "klavesnice"
                    p["nastaveni"] = snap or {}
                    seen[key] = p["id"]
                a["predvolba"] = seen[key]
            g[str(n)] = a
        prof["klavesy_g"] = g
        return prof

    m1 = conv(lcfg, "M1")
    sets = {}
    try:
        with open(OLD_SETS_FILE, encoding="utf-8") as f:
            sets = {str(k): v.get("nastaveni") for k, v in json.load(f).items() if isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        pass
    out = {"1": m1}
    for m in ("2", "3"):
        out[m] = conv(sets[m], "M" + m) if isinstance(sets.get(m), dict) else copy.deepcopy(m1)
    lcfg["klavesnice_m"] = out
    for k in PROFILE_KEYS:
        lcfg.pop(k, None)
    return True


# ----------------------------------------------------------------- stav

class State:
    """Co je prave zapnute klavesami G / M (aktivni M se pamatuje v souboru, zbytek jen v pameti)."""

    def __init__(self, m=None):
        self.m = m if m in M_KEYS else load_m()   # aktivni nastaveni klavesnice M1-M3
        self.active = None                        # cislo G-klavesy s aktivni predvolbou
        self.music = None                         # vizualizer zapnuty / vypnuty G-klavesou (None = jak v okne)
        self.style = None                         # styl vizualizeru vybrany G-klavesou
        self.playlist = None                      # playlist zapnuty / vypnuty G-klavesou
        self.flash = {}                           # {cislo G: cas stisku}

    # --- nastaveni
    def with_set(self, base):
        """Nastaveni z okna s profilem aktivniho M (podsviceni a akce G-klaves)."""
        return with_profile(base, self.m)

    def preset(self, cfg):
        """Aktivni predvolba (slovnik ze seznamu), nebo None."""
        if self.active is None:
            return None
        a = actions(cfg).get(self.active)
        p = preset_by_id(cfg, a.get("predvolba")) if a is not None and a["akce"] == "predvolba" else None
        if p is None:
            self.active = None                      # predvolba zrusena / zmenena
        return p

    def _with_preset(self, cfg):
        p = self.preset(cfg)
        return cfg if p is None else overlay(cfg, p)

    def apply(self, base):
        """Nastaveni s tim, co je zapnute klavesami (novy slovnik)."""
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
        """V okne ulozena zmena: predvolba zpet na nastaveni M."""
        if self.active is not None:
            self.active = None
            log.info("Klávesnice: uloženo nové nastavení – předvolba vypnuta, platí M%d.", self.m)

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
            p = preset_by_id(cfg, a.get("predvolba"))
            if self.active == n or p is None:
                self.active = None
                log.info("G%d: zpět na nastavení M%d.", n, self.m)
            else:
                self.active = n
                log.info("G%d: předvolba „%s“ – %s.", n, preset_name(p), describe(p))
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

    def press_m(self, n, base=None, current=None):
        """Stisk M-klavesy n = prepnout na nastaveni klavesnice Mn (stejna M = vypnout predvolbu)."""
        if n == self.m:
            if self.active is not None:
                self.active = None
                log.info("M%d: předvolba vypnuta – zpět na nastavení M%d.", n, n)
            return
        self.m, self.active = n, None
        save_m(n)
        log.info("M%d: nastavení klávesnice M%d%s.", n, n,
                 " – " + describe_profile(profile(base, n)) if base is not None else "")

    def press_mr(self):
        log.info("MR: nemá přiřazenou funkci.")

    # --- stav pro kontrolky
    def music_on(self, cfg):
        if self.music is not None:
            return self.music
        return bool((cfg.get("hudba") or {}).get("zapnuto"))

    def playlist_on(self, cfg):
        if self.playlist is not None:
            return self.playlist
        return bool((cfg.get("playlist") or {}).get("zapnuto"))

    def m_leds(self, now=None):
        """(maska kontrolek M1-M3, kontrolka MR): sviti kontrolka aktivniho M."""
        return 1 << (self.m - 1), False

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
        """Bezi neco, co chce dalsi snimky (bliknuti)?"""
        now = time.monotonic() if now is None else now
        return any(now - t < FLASH_S for t in self.flash.values())

    def status(self, base=None):
        p = self.preset(self.with_set(base)) if base is not None else None
        return {"m": self.m, "aktivni": self.active, "predvolba": preset_name(p) if p else None,
                "hudba": self.music, "styl": self.style, "playlist": self.playlist}
