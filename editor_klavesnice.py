# editor_klavesnice.py - stranka Klavesnice v okne nastaveni (Logitech G815)
# Rozlozeni stranky: pevne nahore karta s nahledem klavesnice, vedle nej "Ridit podsviceni z aplikace",
# stav a vyber nastaveni M1-M3; pod ni zalozky (TABS, vybrana se pamatuje v KeyboardEditor.last_tab) -
# roluje se jen obsah zalozky:
#     Podsviceni (jas, casti klavesnice + karta Efekt) | Klavesy G1-G5 | Predvolby | Reakce a hlasitost | Pamet
# Podsviceni, Klavesy G1-G5 a Pamet patri k vybranemu M, Predvolby a Reakce a hlasitost jsou spolecne
# (SHARED_TABS; napis vedle zalozek - _scope). Klik na klavesu v nahledu dela to, co patri k zalozce
# (click_mode): klavesy casti / vyber pro vlastni barvy (Podsviceni), klavesy ukazatele hlasitosti
# (Reakce a hlasitost), jinak ukazkovy stisk.
#   - Nahled a stav: klavesnice po klavesach (klavesnice_rozlozeni.KEYS) v barvach, ktere pocita
#     zivy nahled LED (LedEditor._animate -> preview()); stav rizeni z bezici aplikace.
#   - Efekt: vlastni plosny efekt klavesnice (klavesnice_efekty, skupiny GROUPS) nebo jedna barva
#     jako F140 / jako deska; parametry efektu, malovani klaves, jas
#   - Reakce na stisk (config["led"]["reakce_klavesnice"]): nadrazena pres celou klavesnici, M1-M3 spolecne
#   - Casti klavesnice (vrstvy, config["led"]["vrstvy_klavesnice"]): vlastni efekt na vybranych klavesach
#     pres zaklad; "Upravuji" prepina, ceho se tyka vyber efektu (self.target), klik na klavesu = do casti
#   - Nastaveni M1-M3 (config["led"]["klavesnice_m"], klavesy_g.py): vyber nahore (self.m) - podsviceni
#     i klavesy G1-G5 na strance patri k vybranemu M (self.prof)
#   - Klavesy G1-G5: akce (predvolba ze seznamu, hudba, styl hudby, playlist, skladba na LCD) a osvetleni
#   - Predvolby (config["led"]["predvolby"], spolecne pro M1-M3): "Upravit klavesnici" prepne kartu
#     Podsviceni (self.preset = id) na nastaveni predvolby (self.src) - nahled ukazuje predvolbu
#   - Hlasitost (config["led"]["hlasitost_klavesnice"], hlasitost.py, spolecne pro M1-M3): ukazatel na
#     vybranych klavesach po pohybu posuvnikem; klik na klavesy (self.vol_pick), ukazka v nahledu (preview_top)
#   - Integrovana pamet: stav (cte se kazde 3 s, kdyz je stranka videt), zaloha. Pamet prepina
#     vlakno LED samo podle "Ridit podsviceni z aplikace" (klavesnice.Direct).
# Zmeny se projevi po Ulozit (config["led"]["klavesnice"], ["klavesnice_m"], ["predvolby"]).

import os
import random
import threading
import time
import tkinter as tk
from tkinter import colorchooser, ttk

import hlasitost
import klavesnice_efekty as kbfx
import klavesnice_rozlozeni as R
import klavesy_g
import led
import led_efekty as fx
import vzhled as V

POLL_MS = 3000               # stav integrovane pameti (prepina ji vlakno LED v bezici aplikaci)
DEMO_MS = 700                # ukazkove stisky v nahledu, kdyz je zapnuta reakce
WRAP = 620
U = 24                       # sirka klavesy 1u v nahledu (px) - vedle nahledu se musi vejit sloupec s M1-M3
PAD = 8
KB_W, KB_H = int(R.WIDTH * U) + 2 * PAD, int(R.HEIGHT * U) + 2 * PAD
KEY_DEFAULT = {"zapnuto": False, "efekt": "vlastni", "jas": 100, "barva": "#ffffff"}
# popisek posuvniku "sirka" podle efektu
WIDTH_LABEL = {"vlna": "Délka vlny", "kruh": "Šířka kruhů", "toceni": "Zkroucení", "skener": "Šířka",
               "dest": "Hustota", "trpyt": "Hustota", "ohnostroj": "Četnost", "plamen": "Výška plamene",
               "jiskry": "Množství", "dest_hudba": "Hustota", "plazma": "Velikost vzoru",
               "polarni_zare": "Šířka závěsů", "radar": "Délka stopy", "bourka": "Hustota deště",
               "ohnostroj_hudba": "Množství", "plazma_hudba": "Velikost vzoru", "kostky": "Množství kostek",
               "lava": "Velikost kapek", "odlesk": "Šířka lesku", "pruhy": "Délka pruhů", "paprsky_kriz": "Šířka",
               "hvezdy": "Padající hvězdy", "snezeni": "Hustota", "kruhy_voda": "Četnost kapek",
               "svetlusky": "Počet", "prskavka": "Jiskry", "meteory": "Četnost", "hvezdny_let": "Hustota",
               "nalada": "Velikost vzoru", "teplotni_mapa": "Rozptyl tepla"}
SPEED_LABEL = {"bourka": "Četnost blesků", "spektrogram": "Rychlost posunu", "dj": "Rychlost toku",
               "zaznam": "Rychlost posunu", "teplotni_mapa": "Chladnutí", "odlesk": "Jak často",
               "kruhove_spektrum": "Otáčení", "glitch": "Posun barev"}
OPP_LABEL = {"kruh": "Dovnitř", "hlasitost": "Od středu do stran", "vlna": "Opačně (kosočtverec dovnitř)",
             "radar": "Proti směru hodin", "dj": "Od krajů ke středu",
             "zaznam": "Zleva doprava"}      # popisek "opacne" podle efektu
# co znamenaji barvy efektu (v poradi) a kratka napoveda pod nastavenim
COLOR_NOTE = {"radar": "Barvy: paprsek, cíle.", "bourka": "Barvy: blesk, déšť.",
              "had": "Barvy: hlava, ocas, potrava. Had leze za potravou a roste; když se zamotá, začne znovu.",
              "zivot": "Barvy podle stáří buňky (nová → stará). Když obrazec vymře nebo se zacyklí, zaseje se "
                       "nový; stisk klávesy přidá buňky (se zapnutou reakcí na stisk nebo ukazatelem hlasitosti).",
              "dj": "Barvy: basy, středy, výšky – barva okamžiku vzniká uprostřed a teče do stran.",
              "spektrogram": "Barvy od slabého zvuku po silný. Spodní řada = spektrum teď (vlevo basy, vpravo "
                             "výšky), řady se posouvají nahoru.",
              "zaznam": "Barvy od prostřední řady k okrajům.",
              "kostky": "Každý úder shodí kostku; plná spodní řada blikne a zmizí, drop smaže vše.",
              "lava": "Barvy kapek; kde se kapky potkají, barvy se slijí.",
              "odlesk": "Barvy podkladu (přechod ve zvoleném směru); lesk je bílý.",
              "paprsky_kriz": "Barvy: vodorovný paprsek, svislý paprsek.",
              "hvezdy": "Barvy hvězd; padající hvězda je bílá.",
              "snezeni": "Barvy: vločky, závěje (s jednou barvou stejné). Závěje dole pomalu tají.",
              "prskavka": "Barvy: hlava, jiskry. Bod obíhá po okraji klávesnice.",
              "meteory": "Barvy meteorů; dole se rozstříknou.",
              "cihly": "Barvy: míček a pálka, pak cihly po řadách. Hraje sám, občas netrefí; po zboření všech "
                       "cihel začne znovu.",
              "tenis": "Barvy: levá pálka, pravá pálka, míček. Hraje sám, kdo netrefí, prohraje bod.",
              "bici_automat": "Barvy: kopák (spodní řady), virbl (prostřední), hi-hat (horní). Sloupce zleva doprava "
                              "jsou jeden takt, světlý sloupec je právě hraná doba; údery vydrží dva takty. "
                              "Horní pruh ukazuje dobu taktu.",
              "hvezdny_let": "Barvy hvězd. Rychlost podle energie skladby, kopák zrychlí, drop = skok s bílými "
                             "pruhy.",
              "stoupani": "Při stavbě napětí před dropem se klávesnice plní zleva a bliká čím dál rychleji, "
                          "v dropu vybuchne od středu.",
              "kruhove_spektrum": "Barvy od středu ke krajům. Basy a výšky jsou proti sobě, paprsky se točí.",
              "glitch": "Na údery virblu, kopáku a hi-hatu se řady posunou, barvy rozjedou, vypadnou nebo "
                        "obrátí.",
              "nalada": "Barvy od klidné (tiché pasáže) po energickou (refrén); jeden nádech za takt.",
              "teplotni_mapa": "Barvy od studené po horkou. Klávesy se psaním ohřívají a pomalu chladnou; "
                               "aplikace ví jen, která klávesa se stiskla, nic neukládá (po restartu je mapa "
                               "prázdná)."}
KEEP = ("klavesy", "zaklad")   # pri zmene efektu zustava
# zalozky stranky (nahled a vyber M1-M3 jsou pevne nad nimi)
TABS = [("podsviceni", "Podsvícení"), ("g", "Klávesy G1–G5"), ("predvolby", "Předvolby"),
        ("prekryvy", "Reakce a hlasitost"), ("pamet", "Paměť")]
SHARED_TABS = ("predvolby", "prekryvy")       # spolecne pro M1-M3 (ostatni patri k vybranemu M)


def fx_style(styl):
    import led_efekty
    return led_efekty.MUSIC_STYLES.get(styl, styl)


class _Lazy(dict):
    """Navrh, ktery se pri prvni zmene (e[k] = v) ulozi do nastaveni (attach)."""

    def __init__(self, data, attach):
        super().__init__(data)
        self._attach = attach
        self._target = None                        # ulozena kopie (obycejny slovnik v nastaveni)

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        if self._target is None:
            self._target = dict(self)
            self._attach(self._target)
        else:
            self._target[k] = v


class KeyboardEditor:
    last_tab = "podsviceni"       # vybrana zalozka (zachova se pri "Vratit ulozene" - okno se postavi znovu)

    def __init__(self, parent, app):
        self.app = app
        self._job = None                          # bezici prace s klavesnici (vlakno) a jeji vysledek
        self._mode = None                         # rezim pameti klavesnice (klavesnice.MODE_*)
        self._last = None                         # posledni barvy v nahledu
        self.sel = set()                          # vybrane klavesy (vlastni barvy klaves)
        self.target = None                        # upravovana cast klavesnice (index vrstvy), None = zaklad
        self.preset = None                        # upravovana predvolba (id), None = nastaveni M
        st = (getattr(app, "lstate", None) or {}).get("klavesy_g") or {}
        self.m = st.get("m") if st.get("m") in klavesy_g.M_KEYS else klavesy_g.load_m()   # upravovane M1-M3
        self.layer_lbl = None
        self.items = {}
        self.sel_lbl = None
        self.vol_pick = False                     # klik na klavesu = do ukazatele hlasitosti / z nej
        self.center_pick = False                  # klik na klavesu = stred efektu (kruh, toceni, radar)
        self._vdemo = (None, False)
        self._vov = hlasitost.Overlay()
        self._back = None                         # zalozka, ze ktere se slo upravit predvolbu (Hotovo se vrati)
        self._side_w = 220                        # sirka sloupce vedle nahledu (zalamovani textu)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        # pevne nahore: nahled klavesnice, rizeni z aplikace, stav a vyber M1-M3 (neroluje se)
        self.top = V.card(parent)
        self.top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        keys = [k for k, _t in TABS]
        self._tab = tk.StringVar(value=KeyboardEditor.last_tab if KeyboardEditor.last_tab in keys else keys[0])
        tb = tk.Frame(parent, bg=V.BG)
        tb.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        V.segmented(tb, self._tab, TABS, command=self._show_tab, style="Tab.Toolbutton").pack(side="left")
        self.scope_lbl = tk.Label(tb, bg=V.BG, fg=V.MUTED, font=V.SMALL)      # ceho se zalozka tyka
        self.scope_lbl.pack(side="left", padx=(14, 0))
        self.scroll = V.ScrollFrame(parent)
        self.scroll.grid(row=2, column=0, sticky="nsew")
        body = self.scroll.inner
        body.columnconfigure(0, weight=1)
        self.tabs = {}
        for key in keys:
            f = tk.Frame(body, bg=V.BG)
            f.columnconfigure(0, weight=1)
            self.tabs[key] = f
        # Podsviceni (vybrane M / upravovana predvolba)
        t = self.tabs["podsviceni"]
        self.light = V.card(t)
        self.light.grid(row=0, column=0, sticky="ew")
        self.fxcard = V.card(t)                   # efekt cele klavesnice / vybrane casti
        self.fxcard.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        # Klavesy G1-G5 (vybrane M)
        self.gcard = V.card(self.tabs["g"])
        self.gcard.grid(row=0, column=0, sticky="ew")
        # Predvolby (spolecne)
        self.pcard = V.card(self.tabs["predvolby"])
        self.pcard.grid(row=0, column=0, sticky="ew")
        # Reakce a hlasitost (spolecne, kresli se pres vsechno ostatni)
        t = self.tabs["prekryvy"]
        self.react = V.card(t)
        self.react.grid(row=0, column=0, sticky="ew")
        self.vcard = V.card(t)
        self.vcard.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        self.tcard = V.card(t)                    # psani pohani efekt a sporic
        self.tcard.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        # Pamet
        self.mem = V.card(self.tabs["pamet"])
        self.mem.grid(row=0, column=0, sticky="ew")
        self._build_top()
        self._build_light()
        self._build_react()
        self._build_vol()
        self._build_typing()
        self._build_g()
        self._build_presets()
        self._build_mem()
        self._show_tab()
        self._run(self._read_mode)
        self.mem.after(POLL_MS, self._tick)
        self.top.after(DEMO_MS, self._demo)

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    @property
    def kc(self):
        return self.lcfg.setdefault("klavesnice", dict(KEY_DEFAULT))

    @property
    def prof(self):
        """Upravovane nastaveni klavesnice M (profil v config["led"]["klavesnice_m"])."""
        return klavesy_g.profile(self.lcfg, self.m)

    def preset_cfg(self):
        """Upravovana predvolba (ze seznamu), nebo None = nastaveni M."""
        if self.preset is not None:
            p = klavesy_g.preset_by_id(self.lcfg, self.preset)
            if p is not None and klavesy_g.has_keyboard(p):
                return p
        self.preset = None
        return None

    def m_cfg(self, lc=None):
        """Nastaveni z okna s upravovanym M."""
        return klavesy_g.with_profile(self.lcfg if lc is None else lc, self.m)

    @property
    def src(self):
        """Co upravuje karta Podsviceni: profil M, nebo nastaveni predvolby."""
        p = self.preset_cfg()
        return self.prof if p is None else klavesy_g.ensure_keyboard(p, self.m_cfg())

    @property
    def ekc(self):
        """Efekt a jas klavesnice, ktere karta upravuje (M / predvolba)."""
        kc = self.src.get("klavesnice")
        if not isinstance(kc, dict):
            kc = self.src["klavesnice"] = {"efekt": "vlastni", "jas": 100}
        return kc

    def preview_cfg(self, lc):
        """Pro zivy nahled LED (editor_led): nastaveni s upravovanym M; predvolba jen, kdyz je stranka
        Klavesnice videt. Vrati (nastaveni, cislo G-klavesy s predvolbou v tomto M nebo None)."""
        try:
            visible = self.top.winfo_ismapped()
        except tk.TclError:
            visible = False
        p = self.preset_cfg() if visible else None
        if p is None:
            return self.m_cfg(lc), None
        key = next((n for n, a in klavesy_g.actions(self.prof).items()
                    if a["akce"] == "predvolba" and a.get("predvolba") == p.get("id")), None)
        return klavesy_g.overlay(self.m_cfg(lc), p), key

    @property
    def layers(self):
        v = self.src.get("vrstvy_klavesnice")
        if not isinstance(v, list):
            v = self.src["vrstvy_klavesnice"] = []
        return v

    def layer(self):
        """Upravovana cast klavesnice (vrstva), nebo None = zaklad."""
        if self.target is not None and 0 <= self.target < len(self.layers) and isinstance(
                self.layers[self.target], dict):
            return self.layers[self.target]
        self.target = None
        return None

    @property
    def eff(self):
        lay = self.layer()
        if lay is not None:                       # cast klavesnice: vlastni barvy klaves nema (ty umi zaklad)
            e = lay.get("efekt")
            if not isinstance(e, dict) or e.get("typ") not in kbfx.EFFECTS or e.get("typ") == "vlastni":
                e = lay["efekt"] = kbfx.default_effect("dest")
            return e
        e = self.src.get("efekt_klavesnice")
        if not isinstance(e, dict) or e.get("typ") not in kbfx.EFFECTS:
            e = kbfx.default_effect("vlna")
            self.src["efekt_klavesnice"] = e
        return e

    def own(self):
        return led.kb_own(self.lcfg)

    def painting(self):
        return self.layer() is None and self.own() and self.eff.get("typ") == "vlastni"

    @property
    def rcfg(self):
        """Reakce na stisk (spolecna, nadrazena)."""
        v = self.lcfg.get("reakce_klavesnice")
        if not isinstance(v, dict):
            v = self.lcfg["reakce_klavesnice"] = {}
        for k, d in kbfx.REACTION_DEFAULT.items():
            v.setdefault(k, d)
        return v

    def reacting(self):
        """Ukazovat v nahledu ukazkove stisky? (reakce, psani pohani efekt, efekt kreslici ze stisku)"""
        return bool(self.rcfg["zapnuto"] or self.cfg_part("psani_klavesnice", kbfx.TYPING_DEFAULT)["zapnuto"]
                    or any(e.get("typ") in kbfx.KEY_EFFECTS for e in led.kb_effects(self.preview_cfg(self.lcfg)[0])))

    def cfg_part(self, key, default):
        """Spolecne nastaveni klavesnice (psani, sporic) - doplnene o vychozi hodnoty."""
        v = self.lcfg.get(key)
        if not isinstance(v, dict):
            v = self.lcfg[key] = {}
        for k, d in default.items():
            v.setdefault(k, d)
        return v

    # ------------------------------------------------------------ nahled a stav (pevne nad zalozkami)
    def _build_top(self):
        """Vlevo nahled klavesnice, vedle nej rizeni z aplikace, stav a vyber M1-M3; pod nim napoveda."""
        f = self.top
        f.columnconfigure(1, weight=1)
        c = self.canvas = tk.Canvas(f, width=KB_W, height=KB_H, bg=V.CARD, highlightthickness=0)
        c.grid(row=0, column=0, sticky="nw", padx=16, pady=(14, 4))
        c.create_rectangle(1, 1, KB_W - 1, KB_H - 1, outline="#262b33", fill="#111418")
        for z, _name, x, y, w, h in R.KEYS:
            x0, y0 = PAD + x * U + 2, PAD + y * U + 2
            self.items[z] = c.create_rectangle(x0, y0, x0 + w * U - 4, y0 + h * U - 4, fill="#1c2128",
                                               outline="#2a3038", width=1, tags=("key", f"z{z}"))
        self.empty_txt = c.create_text(KB_W / 2, KB_H / 2 + U, fill=V.MUTED, font=V.FONT_B, text="")
        c.tag_bind("key", "<Button-1>", self._on_key)
        f.rowconfigure(1, weight=1)
        side = ttk.Frame(f)
        side.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(0, 16), pady=(12, 8))
        on = tk.BooleanVar(value=bool(self.kc.get("zapnuto")))

        def on_toggle():
            self.kc["zapnuto"] = on.get()
            self._rebuild()
            self._show_mode()
        ttk.Checkbutton(side, text="Řídit podsvícení z aplikace", variable=on, command=on_toggle).pack(anchor="w")
        self.status = ttk.Label(side, font=V.FONT_B, wraplength=self._side_w, justify="left")
        self.status.pack(anchor="w", pady=(2, 10))
        self.mrow = ttk.Frame(side)               # Nastaveni M1 / M2 / M3
        self.mrow.pack(anchor="w")
        self.m_lbl = ttk.Label(side, style="Small.TLabel", wraplength=self._side_w, justify="left")
        self.m_lbl.pack(anchor="w", pady=(4, 8))
        self.crow = ttk.Frame(side)               # Zkopirovat Mx do ...
        self.crow.pack(anchor="w")
        self.m_msg = None
        self._build_mrow()
        self.hint = ttk.Label(f, style="Small.TLabel", wraplength=KB_W - 4, justify="left")
        self.hint.grid(row=1, column=0, sticky="nw", padx=16, pady=(0, 10))

        def on_side(e):                           # texty vedle nahledu zalamovat na sirku sloupce
            self._side_w = max(140, e.width - 4)
            for lbl in (self.status, self.m_lbl, self.m_msg):
                if lbl is not None:
                    lbl.config(wraplength=self._side_w)
        side.bind("<Configure>", on_side)

    # ------------------------------------------------------------ zalozky
    def _show_tab(self):
        key = self._tab.get()
        KeyboardEditor.last_tab = key
        for k, f in self.tabs.items():
            if k == key:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_forget()
        try:
            self.scroll.canvas.yview_moveto(0)
        except tk.TclError:
            pass
        self._scope()
        self._show_sel()                          # klik na klavesy v nahledu patri k zalozce (click_mode)
        self.refresh()
        self._refit()
        if key == "pamet":                        # stav pameti hned, ne az za 3 s
            self._run(self._read_mode)

    def _scope(self):
        """Vedle zalozek: ceho se zalozka tyka (vybrane M / spolecne pro vsechna M / upravovana predvolba)."""
        lbl = getattr(self, "scope_lbl", None)
        if lbl is None:
            return
        tab, p = self._tab.get(), self.preset_cfg()
        if tab in SHARED_TABS:
            text, color = "společné pro M1–M3", V.MUTED
        elif tab == "podsviceni" and p is not None:
            text, color = f"upravuješ předvolbu „{klavesy_g.preset_name(p)}“", V.ACCENT
        elif tab == "pamet":
            text, color = f"paměť klávesnice · nastavení M{self.m}", V.MUTED
        else:
            text, color = f"platí pro nastavení M{self.m}", V.MUTED
        lbl.config(text=text, fg=color)

    def click_mode(self):
        """Co dela klik na klavesu v nahledu - podle zalozky: "hlasitost" (klavesy ukazatele hlasitosti),
        "cast" (klavesy upravovane casti), "barvy" (vyber pro vlastni barvy klaves), jinak "stisk"."""
        tab = self._tab.get()
        if not self.kc.get("zapnuto"):
            return "stisk"
        if tab == "prekryvy" and self.vol_pick and self.vcfg["zapnuto"]:
            return "hlasitost"
        if tab == "podsviceni":
            if self.center_pick and "stred" in kbfx.info(self.eff.get("typ"))[2]:
                return "stred"                    # klik = stred kruhu / toceni / radaru
            if self.layer() is not None:
                return "cast"
            if self.painting():
                return "barvy"
        return "stisk"

    def _on_key(self, _event):
        hit = self.canvas.find_withtag("current")
        z = next((int(t[1:]) for t in (self.canvas.gettags(hit[0]) if hit else ()) if t[:1] == "z"), None)
        if z is None:
            return
        mode = self.click_mode()
        if mode == "stred":                       # stred efektu na kliknutou klavesu
            self.eff["stred"] = str(z)
            self.center_pick = False
            self._rebuild()
        elif mode == "hlasitost":                 # klavesa do ukazatele hlasitosti / z nej
            self.vcfg["klavesy"] = sorted(set(self.vcfg["klavesy"]) ^ {z})
            self._show_sel()
            self._vol_info()
        elif mode == "cast":                      # klavesa do casti / z casti
            lay = self.layer()
            lay["klavesy"] = sorted(set(kbfx.part_zones(lay)) ^ {z})
            self._show_sel()
            self._layer_info()
        elif mode == "barvy":
            self.sel ^= {z}
            self._show_sel()
            self._sel_info()
        else:                                     # ukazkovy stisk (reakce)
            kbfx.engine_for(self.app.leds.engine).press(z)

    def _show_sel(self):
        mode = self.click_mode()
        if mode == "hlasitost":
            marked = set(self.vcfg["klavesy"])
        elif mode == "cast":
            marked = set(kbfx.part_zones(self.layer()))
        else:
            marked = self.sel if mode == "barvy" else set()
        for z, it in self.items.items():
            on = z in marked
            self.canvas.itemconfig(it, outline="#ffffff" if on else ("" if self._last else "#2a3038"),
                                   width=2 if on else 1)

    def preview(self, kb):
        """Barvy klavesnice ze ziveho nahledu LED (LedEditor._animate): 1 barva = cela klavesnice,
        jinak barva kazde klavesy v poradi KEYS; None = aplikace klavesnici neridi."""
        if kb is not None and len(kb) == 1:
            kb = kb * len(R.KEYS)
        key = None if kb is None else tuple(tuple(c) for c in kb)
        if key == self._last and key is not None:
            return
        try:
            if not self.canvas.winfo_exists():
                return
        except tk.TclError:
            return
        was_empty = self._last is None
        self._last = key
        c = self.canvas
        if key is None:
            for z, it in self.items.items():
                c.itemconfig(it, fill="#1c2128", outline="#ffffff" if z in self.sel else "#2a3038")
            c.itemconfig(self.empty_txt, text="svítí podle profilu v integrované paměti")
            return
        for (z, *_r), col in zip(R.KEYS, key):
            r, g, b = (round(255 * (max(0, min(255, v)) / 255) ** 0.5) for v in col)   # LED sviti vic nez monitor
            c.itemconfig(self.items[z], fill=f"#{r:02x}{g:02x}{b:02x}")
        if was_empty:
            c.itemconfig(self.empty_txt, text="")
            self._show_sel()

    def _demo(self):
        """Ukazkove stisky v nahledu (reakce na stisk)."""
        try:
            if not self.top.winfo_exists():
                return
        except tk.TclError:
            return
        if self.kc.get("zapnuto") and self.reacting() and self.top.winfo_ismapped():
            z = random.choice([z for z in kbfx.ZONES if z < 112])
            kbfx.engine_for(self.app.leds.engine).press(z)
        self.top.after(DEMO_MS + random.randint(-300, 400), self._demo)

    def refresh(self):
        """Stav z bezici aplikace (volano kazdou sekundu z App._tick)."""
        st = getattr(self.app, "lstate", None) or {}
        errs = [e for e in st.get("chyby", []) if e.startswith("klávesnice")]
        saved = self.app.saved.get("led", {})                     # bezici aplikace ma ulozene nastaveni
        kc = saved.get("klavesnice", {})
        if not kc.get("zapnuto"):
            text, color = "Klávesnice svítí podle profilu v integrované paměti (aplikace ji neřídí)", V.MUTED
        elif not saved.get("zapnuto", True):
            text, color = ("Řízení LED je vypnuté (stránka LED ventilátorů) – klávesnice svítí podle profilu "
                           "v integrované paměti"), V.WARN
        elif not self.app.running:
            text, color = "Aplikace neběží – klávesnici převezme po spuštění", V.MUTED
        elif errs:
            text, color = "Chyba: " + "; ".join(e.split(": ", 1)[-1] for e in errs) + " (zkouší znovu)", V.ERR
        elif st.get("stav") in ("běží", "nastaveno"):
            text, color = "● Podsvícení řídí aplikace", V.OK
        else:
            text, color = "Stav uvidíš, až poběží aplikace", V.MUTED
        if bool(self.kc.get("zapnuto")) != bool(kc.get("zapnuto")):
            text += " – změna řízení se projeví po Uložit"
        g = st.get("klavesy_g") if self.app.running and kc.get("zapnuto") else None
        if g and g.get("aktivni"):
            text += f" – teď platí předvolba „{g.get('predvolba') or '?'}“"
        self.status.config(text=text + ".", foreground=color)
        self._g_status(st, saved)
        p = self.preset_cfg()
        pre = (f"Náhled ukazuje předvolbu „{klavesy_g.preset_name(p)}“. " if p is not None
               else f"Náhled ukazuje nastavení M{self.m}. ")
        mode = self.click_mode()
        if not self.kc.get("zapnuto"):
            hint = "Náhled ukáže efekt, až zapneš řízení podsvícení z aplikace."
        elif mode == "stred":
            hint = "Klikni na klávesu, která má být středem efektu."
        elif mode == "hlasitost":
            hint = "Klik na klávesu = přidat do ukazatele hlasitosti / odebrat z něj (bílý rámeček)."
        elif mode == "cast":
            hint = "Klik na klávesu = přidat do části / odebrat z ní (klávesy části mají bílý rámeček)."
        elif mode == "barvy":
            hint = "Klik na klávesu = vybrat / zrušit výběr; vybrané klávesy obarvíš v kartě Efekt."
        elif self.reacting():
            hint = "Náhled ukazuje i ukázkové stisky; klik na klávesu = stisk."
        else:
            hint = "Náhled počítá barvy stejně jako aplikace (i s jasem). Na klávesnici se změna projeví po Uložit."
        self.hint.config(text=pre + hint)

    # ------------------------------------------------------------ podsviceni a efekt
    def _rebuild(self):
        if not self.painting():
            self.sel.clear()                      # vyber klaves jen u vlastnich barev klaves
        self._build_light()
        self._show_sel()
        self.refresh()

    def _build_light(self):
        """Zalozka Podsviceni: karta s jasem a castmi klavesnice + karta Efekt (cela klavesnice / cast)."""
        for card in (self.light, self.fxcard):
            for w in card.winfo_children():
                w.destroy()
        self.sel_lbl = None
        f = self.light
        kc = self.kc
        pa = self.preset_cfg()
        f.columnconfigure(1, weight=1)
        V.card_title(f, f"Podsvícení – nastavení M{self.m}" if pa is None
                     else f"Předvolba „{klavesy_g.preset_name(pa)}“").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(14, 6))
        self._scope()
        if not kc.get("zapnuto"):
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                      text="Klávesnice svítí podle profilu v integrované paměti. Zapni nahoře „Řídit podsvícení "
                           "z aplikace“ – aplikace pak paměť sama vypne a podsvícení počítá po jednotlivých "
                           "klávesách.").grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 16))
            self.fxcard.grid_remove()
            self._refit()
            return
        self.fxcard.grid()
        self._preset_row(f, 1)
        ek = self.ekc
        ttk.Label(f, text="Jas", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(20, 10), pady=4)
        jf = ttk.Frame(f)
        jf.grid(row=2, column=1, sticky="w", pady=4)
        jv = tk.IntVar(value=int(ek.get("jas", kc.get("jas", 100))))
        jl = ttk.Label(jf, width=5, text=f"{jv.get()} %", font=V.MONO, anchor="e")

        def on_jas(_e=None):
            ek["jas"] = int(jv.get())
            jl.config(text=f"{int(jv.get())} %")
        V.scale(jf, variable=jv, from_=10, to=100, resolution=5, length=200, command=on_jas).pack(side="left")
        jl.pack(side="left", padx=(8, 0))
        self._parts_row(f, 3)
        lay = self.layer()
        if lay is not None:
            lf = ttk.Frame(f)
            lf.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 0))
            self._layer_controls(lf, lay)
        ttk.Frame(f).grid(row=5, column=0, pady=(0, 12))
        g = self.fxcard
        g.columnconfigure(0, weight=1)
        V.card_title(g, "Efekt – celá klávesnice" if lay is None else
                     f"Efekt – část „{lay.get('nazev') or f'Část {self.target + 1}'}“").grid(
            row=0, column=0, sticky="w", padx=20, pady=(14, 6))
        pf = ttk.Frame(g)
        pf.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 16))
        self._effect_chooser(pf, exclude=("vlastni",) if lay is not None else ())
        self._refit()

    # ------------------------------------------------------------ upravovana predvolba (pruh v karte)
    def _preset_row(self, f, row):
        """Pruh v karte Podsviceni, kdyz se upravuje predvolba (radek row)."""
        p = self.preset_cfg()
        if p is None:
            return
        bf = ttk.Frame(f)
        bf.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(2, 6))
        used = klavesy_g.users(self.lcfg, p.get("id"))
        ttk.Label(bf, style="Small.TLabel", wraplength=WRAP - 170, justify="left", foreground=V.ACCENT, text=(
            "Upravuješ předvolbu – takhle bude klávesnice svítit po stisku G-klávesy, která ji má "
            + (f"({', '.join(used)})" if used else "(zatím žádná – přiřaď ji na záložce Klávesy G1–G5)")
            + ". Nastavení M1–M3 se tím nemění. Náhled ukazuje předvolbu; na klávesnici platí po Uložit.")
        ).grid(row=0, column=0, sticky="w")

        def copy_m():
            snap = p.get("nastaveni") or {}
            for k in ("efekt_klavesnice", "vrstvy_klavesnice", "klavesnice"):
                snap.pop(k, None)
            klavesy_g.ensure_keyboard(p, self.m_cfg())
            self.target = None
            self._rebuild()

        def done():
            self.preset = self.target = None
            self._rebuild()
            self._build_g()
            self._build_presets()
            back, self._back = self._back, None
            if back in self.tabs:                 # zpet na zalozku, ze ktere se slo upravovat
                self._tab.set(back)
                self._show_tab()
        ttk.Button(bf, text=f"Zkopírovat z M{self.m}", command=copy_m).grid(row=0, column=1, sticky="e",
                                                                              padx=(12, 0))
        ttk.Button(bf, text="Hotovo", command=done).grid(row=0, column=2, sticky="e", padx=(6, 0))

    def edit_preset(self, pid):
        """Zalozka Podsviceni na predvolbu pid (tlacitko Upravit); Hotovo se vrati na puvodni zalozku."""
        if self._tab.get() != "podsviceni":
            self._back = self._tab.get()
        self.preset, self.target = pid, None
        self.sel.clear()
        self._rebuild()
        self._build_g()
        self._build_presets()
        self._tab.set("podsviceni")
        self._show_tab()

    # ------------------------------------------------------------ casti klavesnice (vrstvy)
    def _parts_row(self, f, row):
        ttk.Label(f, text="Upravuji", style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 10),
                                                                 pady=4)
        fr = ttk.Frame(f)
        fr.grid(row=row, column=1, sticky="w", pady=4)
        opts = [("z", "celou klávesnici")]
        for i, lay in enumerate(self.layers):
            if isinstance(lay, dict):
                name = str(lay.get("nazev") or f"Část {i + 1}")
                opts.append((str(i), name + ("" if lay.get("zapnuto", True) else " (vyp.)")))
        tv = tk.StringVar(value="z" if self.layer() is None else str(self.target))

        def on_t():
            self.target = None if tv.get() == "z" else int(tv.get())
            self.sel.clear()
            self._rebuild()
        V.segmented(fr, tv, opts, command=on_t, style="SegSmall.Toolbutton").pack(side="left")

        def add():
            self.layers.append({"nazev": f"Část {len(self.layers) + 1}", "zapnuto": True, "klavesy": [],
                                "efekt": kbfx.default_effect("dest")})
            self.target = len(self.layers) - 1
            self._rebuild()
        ttk.Button(fr, text="+ Přidat část", command=add).pack(side="left", padx=(10, 0))

    def _layer_controls(self, f, lay):
        f.columnconfigure(1, weight=1)
        self._label(f, 0, "Název")
        nf = ttk.Frame(f)
        nf.grid(row=0, column=1, sticky="w", pady=4)
        nv = tk.StringVar(value=str(lay.get("nazev") or ""))

        def on_name(*_a):
            lay["nazev"] = nv.get().strip() or f"Část {self.target + 1}"
        nv.trace_add("write", on_name)
        e = ttk.Entry(nf, textvariable=nv, width=24)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: self._rebuild())
        ov = tk.BooleanVar(value=bool(lay.get("zapnuto", True)))

        def on_on():
            lay["zapnuto"] = ov.get()
            self._rebuild()
        ttk.Checkbutton(nf, text="zapnutá", variable=ov, command=on_on).pack(side="left", padx=(14, 0))
        self._label(f, 1, "Klávesy")
        gf = ttk.Frame(f)
        gf.grid(row=1, column=1, sticky="w", pady=4)
        names = {gid: name for gid, name, _z in kbfx.KEY_GROUPS}
        default_names = {f"Část {i + 1}" for i in range(len(self.layers) + 1)}
        groups = [g for g in kbfx.KEY_GROUPS if g[0] != "vse"] + [("nic", "vymazat", None)]
        for i, (gid, name, zones) in enumerate(groups):
            def add(gid=gid, zones=zones):
                cur = set(kbfx.part_zones(lay))
                if zones is None:
                    cur = set()
                else:
                    zs = set(zones) & set(self.items)
                    cur = cur - zs if zs <= cur else cur | zs
                    if str(lay.get("nazev")) in default_names or not lay.get("nazev"):
                        lay["nazev"] = names[gid]             # pojmenovat podle prvni vybrane skupiny
                        nv.set(names[gid])
                lay["klavesy"] = sorted(cur)
                self._show_sel()
                self._layer_info()
            ttk.Button(gf, text=name, command=add).grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)
        self._label(f, 2, "Pořadí")
        of = ttk.Frame(f)
        of.grid(row=2, column=1, sticky="w", pady=4)

        def move(step):
            i, j = self.target, self.target + step
            if 0 <= j < len(self.layers):
                self.layers[i], self.layers[j] = self.layers[j], self.layers[i]
                self.target = j
                self._rebuild()

        def remove():
            del self.layers[self.target]
            self.target = None
            self._rebuild()
        ttk.Button(of, text="◀ Níž", command=lambda: move(-1)).pack(side="left", padx=(0, 6))
        ttk.Button(of, text="Výš ▶", command=lambda: move(1)).pack(side="left", padx=(0, 6))
        ttk.Button(of, text="Odebrat část", command=remove).pack(side="left", padx=(12, 0))
        self.layer_lbl = ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 40, justify="left")
        self.layer_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._layer_info()

    def _layer_info(self):
        lbl, lay = self.layer_lbl, self.layer()
        try:
            if lbl is None or lay is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        n = len(kbfx.part_zones(lay))
        pos = f"vrstva {self.target + 1} z {len(self.layers)}"
        lbl.config(text=(f"Kláves v části: {n} ({pos} – vyšší vrstva překryje nižší). " if n else
                         "Část zatím nemá klávesy – vyber skupinu nebo klikni na klávesy v náhledu. ")
                   + "Efekt se počítá jen v rámci těchto kláves (vlna, kruh, déšť vyplní celou část).")

    def _effect_chooser(self, f, exclude=()):
        eff = self.eff
        typ = eff.get("typ")
        f.columnconfigure(1, weight=1)
        gv = tk.StringVar(value=kbfx.info(typ)[1])
        tv = tk.StringVar(value=typ)
        chips = ttk.Frame(f)

        def on_typ():
            new = kbfx.default_effect(tv.get())
            new.update({k: eff[k] for k in KEEP if k in eff})
            eff.clear()
            eff.update(new)
            self.sel.clear()
            self._show_sel()
            self._rebuild()

        def fill():
            for w in chips.winfo_children():
                w.destroy()
            keys = [k for k, v in kbfx.EFFECTS.items() if v[1] == gv.get() and k not in exclude]
            for i, k in enumerate(keys):
                ttk.Radiobutton(chips, text=kbfx.EFFECTS[k][0], value=k, variable=tv, command=on_typ,
                                style="Chip.Toolbutton").grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
        V.segmented(f, gv, kbfx.GROUPS, command=fill, style="SegSmall.Toolbutton").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for c in range(3):
            chips.columnconfigure(c, weight=1, uniform="chip", minsize=225)
        chips.grid(row=1, column=0, columnspan=2, sticky="ew")
        fill()
        ttk.Separator(f).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Label(f, text=kbfx.info(typ)[0], style="Bold.TLabel").grid(row=3, column=0, columnspan=2, sticky="w",
                                                                       pady=(0, 4))
        self._params(f, eff, 4)

    def _label(self, f, row, text):
        ttk.Label(f, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="nw", pady=4, padx=(0, 12))

    def _slider(self, f, row, text, eff, key, lo, hi, res=1, fmt="{:g}"):
        self._label(f, row, text)
        fr = ttk.Frame(f)
        fr.grid(row=row, column=1, sticky="w", pady=4)
        v = tk.DoubleVar(value=float(kbfx.get(eff, key) or lo))
        lbl = ttk.Label(fr, width=6, font=V.MONO, text=fmt.format(v.get()).replace(".", ","))

        def on(_e=None):
            x = round(float(v.get()), 2)
            eff[key] = int(x) if res >= 1 else x
            lbl.config(text=fmt.format(x).replace(".", ","))
        V.scale(fr, variable=v, from_=lo, to=hi, resolution=res, length=220, command=on).pack(side="left")
        lbl.pack(side="left", padx=(10, 0))

    def _color_btn(self, parent, eff, key):
        def pick():
            c = colorchooser.askcolor(color=kbfx.get(eff, key) or "#000000", parent=self.light)[1]
            if c:
                eff[key] = c
                V.set_swatch(b, c)
        b = V.swatch(parent, kbfx.get(eff, key) or "#000000", pick)
        return b

    def _params(self, f, eff, row):
        typ = eff.get("typ")
        names = kbfx.info(typ)[2]
        if "barvy" in names:
            lo, hi = kbfx.info(typ)[3]
            self._label(f, row, "Barvy" if hi > 1 else "Barva")
            fr = ttk.Frame(f)
            fr.grid(row=row, column=1, sticky="w", pady=4)
            pal = kbfx.palette(eff)
            extra = [c for c in eff.get("barvy", []) if c not in pal]          # barvy nad zvoleny pocet
            eff["barvy"] = (list(pal) + extra)[:8]
            if lo < hi:
                nv = tk.IntVar(value=len(pal))

                def on_n():
                    eff["pocet_barev"] = int(nv.get())
                    self._rebuild()
                ttk.Spinbox(fr, from_=lo, to=hi, width=3, textvariable=nv, command=on_n,
                            state="readonly").pack(side="left", padx=(0, 10))
            btns = []
            for i, c in enumerate(pal):
                def pick(i=i):
                    col = colorchooser.askcolor(color=eff["barvy"][i], parent=self.light)[1]
                    if col:
                        eff["barvy"][i] = col
                        V.set_swatch(btns[i], col)
                b = V.swatch(fr, c, pick)
                b.pack(side="left", padx=2)
                btns.append(b)
            row += 1
            if hi > 1:                                       # hotova paleta nastavi barvy i jejich pocet
                def preset(_e=None):
                    new = fx.preset_colors(fx.PALETTES[pb.current()][0], lo, hi)
                    eff["barvy"], eff["pocet_barev"] = new, len(new)
                    if "duha" in names:
                        eff["duha"] = False
                    self._rebuild()
                pb = ttk.Combobox(f, values=[n for _i, n, _c in fx.PALETTES], state="readonly", width=22)
                pb.set("Hotová paleta…")
                pb.bind("<<ComboboxSelected>>", preset)
                pb.grid(row=row, column=1, sticky="w", pady=(0, 4))
                row += 1
        if "duha" in names:
            dv = tk.BooleanVar(value=bool(kbfx.get(eff, "duha")))
            ttk.Checkbutton(f, text="Plná duha místo barev", variable=dv,
                            command=lambda: eff.__setitem__("duha", dv.get())).grid(row=row, column=1, sticky="w")
            row += 1
        if "barvy_hudba" in names:
            self._label(f, row, "Barvy z")
            hv = tk.StringVar(value=kbfx.get(eff, "barvy_hudba"))
            V.segmented(f, hv, [("obal", "hudby (jako ventilátory)"), ("vlastni", "výběru výše")],
                        command=lambda: eff.__setitem__("barvy_hudba", hv.get())).grid(row=row, column=1, sticky="w",
                                                                                       pady=4)
            row += 1
        if "pozadi" in names:
            self._label(f, row, "Pozadí")
            self._color_btn(f, eff, "pozadi").grid(row=row, column=1, sticky="w", pady=4)
            row += 1
        if "smer" in names:
            self._label(f, row, "Směr")
            sv = tk.IntVar(value=int(kbfx.get(eff, "smer") or 0))
            V.segmented(f, sv, kbfx.DIRECTIONS, command=lambda: eff.__setitem__("smer", int(sv.get())),
                        style="SegSmall.Toolbutton").grid(row=row, column=1, sticky="w", pady=4)
            row += 1
        if "tvar" in names:                                  # tvar vlny: rovna / sipka / kosoctverec
            self._label(f, row, "Tvar")
            shv = tk.StringVar(value=kbfx.get(eff, "tvar") or "rovna")
            V.segmented(f, shv, kbfx.SHAPES, command=lambda: eff.__setitem__("tvar", shv.get()),
                        style="SegSmall.Toolbutton").grid(row=row, column=1, sticky="w", pady=4)
            row += 1
        if "stred" in names:                                 # stred efektu: stred klavesnice / vybrana klavesa
            self._label(f, row, "Střed")
            cf = ttk.Frame(f)
            cf.grid(row=row, column=1, sticky="w", pady=4)
            cur = str(kbfx.get(eff, "stred") or "")
            named = dict(kbfx.CENTERS)
            opts = list(kbfx.CENTERS)
            if cur not in named:                             # klavesa vybrana klikem
                name = next((k[1] for k in R.KEYS if str(k[0]) == cur), cur)
                opts.append((cur, f"klávesa {name}"))
            cb = ttk.Combobox(cf, values=[n for _z, n in opts], state="readonly", width=24)
            cb.current(next(i for i, (z, _n) in enumerate(opts) if z == cur))

            def on_center(_e=None):
                eff["stred"] = opts[cb.current()][0]
            cb.bind("<<ComboboxSelected>>", on_center)
            cb.pack(side="left")
            pick = tk.BooleanVar(value=self.center_pick)

            def on_pick():
                self.center_pick = pick.get()
                self._show_sel()
                self.refresh()
            ttk.Checkbutton(cf, text="vybrat klikem na klávesu v náhledu", variable=pick, command=on_pick).pack(
                side="left", padx=(12, 0))
            row += 1
        if "rychlost" in names:
            self._slider(f, row, SPEED_LABEL.get(typ, "Rychlost"), eff, "rychlost", 1, 10)
            row += 1
        if "sirka" in names:
            self._slider(f, row, WIDTH_LABEL.get(typ, "Šířka"), eff, "sirka", 1, 10)
            row += 1
        if "opacne" in names:
            ov = tk.BooleanVar(value=bool(kbfx.get(eff, "opacne")))
            ttk.Checkbutton(f, text=OPP_LABEL.get(typ, "Opačný směr"), variable=ov,
                            command=lambda: eff.__setitem__("opacne", ov.get())).grid(row=row, column=1, sticky="w")
            row += 1
        if "citlivost" in names:
            fan = (self.lcfg.get("hudba") or {}).get("citlivost", 5)
            same = tk.BooleanVar(value=not kbfx.get(eff, "citlivost_vlastni"))

            def on_same():
                eff["citlivost_vlastni"] = not same.get()
                if not same.get() and "citlivost" not in eff:
                    eff["citlivost"] = fan
                self._rebuild()
            self._label(f, row, "Citlivost")
            ttk.Checkbutton(f, text=f"Jako ventilátory ({fan})", variable=same, command=on_same).grid(
                row=row, column=1, sticky="w", pady=4)
            row += 1
            if not same.get():
                self._slider(f, row, "", eff, "citlivost", 1, 10)
                row += 1
        if "spicka" in names:
            pv = tk.BooleanVar(value=bool(kbfx.get(eff, "spicka")))
            ttk.Checkbutton(f, text="Držet špičku", variable=pv,
                            command=lambda: eff.__setitem__("spicka", pv.get())).grid(row=row, column=1, sticky="w")
            row += 1
        if "senzor" in names:
            self._label(f, row, "Senzor")
            sens = sorted(k for k, v in (self.app.data or {}).items() if isinstance(v, dict))
            cv = tk.StringVar(value=kbfx.get(eff, "senzor"))
            cb = ttk.Combobox(f, textvariable=cv, values=sens, width=34, state="readonly")
            cb.grid(row=row, column=1, sticky="w", pady=4)
            cb.bind("<<ComboboxSelected>>", lambda _e: eff.__setitem__("senzor", cv.get()))
            row += 1
            self._label(f, row, "Rozsah")
            fr = ttk.Frame(f)
            fr.grid(row=row, column=1, sticky="w", pady=4)
            for key, txt in (("min", "od"), ("max", "do")):
                v = tk.StringVar(value=f"{float(kbfx.get(eff, key)):g}")

                def on(*_a, key=key, v=v):
                    try:
                        eff[key] = float(v.get().replace(",", "."))
                    except ValueError:
                        pass
                v.trace_add("write", on)
                ttk.Label(fr, text=txt, style="Muted.TLabel").pack(side="left", padx=(0, 4))
                ttk.Entry(fr, textvariable=v, width=7).pack(side="left", padx=(0, 12))
            row += 1
        if "rada" in names:
            self._label(f, row, "Řada")
            rv = tk.StringVar(value=kbfx.get(eff, "rada"))
            V.segmented(f, rv, kbfx.ROW_NAMES, command=lambda: eff.__setitem__("rada", rv.get())).grid(
                row=row, column=1, sticky="w", pady=4)
            row += 1
        if "klavesy" in names:
            row = self._paint(f, eff, row)
        if typ != "vlastni":                                 # barvy se pomalu posouvaji po barevnem kruhu
            self._slider(f, row, "Posun barev", eff, "posun_barev", 0, 10)
            ttk.Label(f, style="Small.TLabel", text="0 = bez posunu, 1 = celý barevný kruh za 10 min, 10 = za 1 min").grid(
                row=row + 1, column=1, sticky="w")
            row += 2
        if typ in COLOR_NOTE:
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 40, justify="left", text=COLOR_NOTE[typ]).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
            row += 1
        if kbfx.info(typ)[1] == "hudba":
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 40, justify="left",
                      text="Reaguje na hudbu ze Spotify (zvuk zachytává jen Spotify). Citlivost je společná "
                           "s ventilátory (LED → Hudba → Reakce na hudbu), stejné číslo = stejná reakce; vlastní "
                           "nižší citlivost svítí jen při výraznějším zesílení a slabší údery vynechá, vyšší "
                           "než u ventilátorů údery navíc nepřidá. V náhledu je simulovaná hudba; bez hudby "
                           "svítí jen pozadí.").grid(row=row, column=0, columnspan=2, sticky="w",
                                                                      pady=(6, 0))

    # ------------------------------------------------------------ vlastni barvy klaves
    def _paint(self, f, eff, row):
        keys = eff.setdefault("klavesy", {})
        self._label(f, row, "Základní barva")
        self._color_btn(f, eff, "zaklad").grid(row=row, column=1, sticky="w", pady=4)
        row += 1
        self._label(f, row, "Vybrat")
        gf = ttk.Frame(f)
        gf.grid(row=row, column=1, sticky="w", pady=4)
        groups = list(kbfx.KEY_GROUPS) + [("nic", "zrušit výběr", None)]
        for i, (_gid, name, zones) in enumerate(groups):
            def add(zones=zones):
                if zones is None:
                    self.sel.clear()
                else:
                    zs = set(zones) & set(self.items)
                    self.sel = self.sel - zs if zs <= self.sel else self.sel | zs
                self._show_sel()
                self._sel_info()
            ttk.Button(gf, text=name, command=add).grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)
        row += 1
        self._label(f, row, "Vybrané")
        bf = ttk.Frame(f)
        bf.grid(row=row, column=1, sticky="w", pady=4)

        def color_sel():
            if not self.sel:
                return
            first = keys.get(str(min(self.sel)), kbfx.get(eff, "zaklad"))
            c = colorchooser.askcolor(color=first, parent=self.light)[1]
            if c:
                for z in self.sel:
                    keys[str(z)] = c

        def clear_sel():
            for z in self.sel:
                keys.pop(str(z), None)
        ttk.Button(bf, text="Obarvit…", command=color_sel).pack(side="left", padx=(0, 6))
        ttk.Button(bf, text="Vrátit na základní", command=clear_sel).pack(side="left")
        self.sel_lbl = ttk.Label(bf, style="Small.TLabel")
        self.sel_lbl.pack(side="left", padx=(12, 0))
        self._sel_info()
        return row + 1

    def _sel_info(self):
        lbl = self.sel_lbl
        try:
            if lbl is not None and lbl.winfo_exists():
                n = len(self.sel)
                lbl.config(text="nic nevybráno" if not n else f"vybráno kláves: {n}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------ reakce na stisk (nadrazena)
    def _build_react(self):
        f = self.react
        for w in f.winfo_children():
            w.destroy()
        rc = self.rcfg
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Reakce na stisk kláves").grid(row=0, column=0, columnspan=3, sticky="w", padx=20,
                                                       pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Přes celou klávesnici a všechno ostatní – efekt, části, předvolbu i hudbu "
            "(přednost má jen ukazatel hlasitosti). Platí ve všech M1–M3. Aplikace pozná jen to, která klávesa "
            "se stiskla – nic neukládá a sledování běží, jen když ho něco potřebuje (reakce, ukazatel hlasitosti, "
            "psaní pohání efekt, teplotní mapa, hra života). Logo, jas a G1–G5 Windows nehlásí.")).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 6))
        on = tk.BooleanVar(value=bool(rc["zapnuto"]))

        def on_toggle():
            rc["zapnuto"] = on.get()
            self._build_react()
            self.refresh()
        ttk.Checkbutton(f, text="Reagovat na stisk kláves", variable=on, command=on_toggle).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 4))
        if not rc["zapnuto"]:
            ttk.Frame(f).grid(row=3, pady=(0, 10))
            self._refit()
            return
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 16))
        b.columnconfigure(1, weight=1)
        self._label(b, 0, "Reakce")
        mv = tk.StringVar(value=rc["rezim"] if rc["rezim"] in dict(kbfx.REACTIONS) else "vlnka")

        def on_m():
            rc["rezim"] = mv.get()
        chips = ttk.Frame(b)                                 # 8 reakci - mrizka po ctyrech
        chips.grid(row=0, column=1, sticky="w", pady=4)
        for i, (key, name) in enumerate(kbfx.REACTIONS):
            ttk.Radiobutton(chips, text=name, value=key, variable=mv, command=on_m, style="Chip.Toolbutton",
                            width=11).grid(row=i // 4, column=i % 4, sticky="ew", padx=2, pady=2)
        self._label(b, 1, "Barva")
        cf = ttk.Frame(b)
        cf.grid(row=1, column=1, sticky="w", pady=4)
        rainbow = tk.BooleanVar(value=rc["barva"] == "duha")
        state = {"col": rc["barva"] if rc["barva"] != "duha" else "#ffffff"}

        def pick():
            c = colorchooser.askcolor(color=state["col"], parent=self.react)[1]
            if c:
                state["col"] = c
                rc["barva"] = c
                rainbow.set(False)
                V.set_swatch(sw, c)
        sw = V.swatch(cf, state["col"], pick)
        sw.pack(side="left")

        def on_rb():
            rc["barva"] = "duha" if rainbow.get() else state["col"]
        ttk.Checkbutton(cf, text="každý stisk jinou barvou duhy", variable=rainbow, command=on_rb).pack(
            side="left", padx=(12, 0))
        self._slider(b, 2, "Doba dohasnutí", rc, "doba", 0.2, 3.0, 0.1, "{:.1f} s")
        self._refit()

    # ------------------------------------------------------------ psani pohani efekt a sporic (spolecne)
    def _build_typing(self):
        f = self.tcard
        for w in f.winfo_children():
            w.destroy()
        ts = self.cfg_part("psani_klavesnice", kbfx.TYPING_DEFAULT)
        sv = self.cfg_part("sporic_klavesnice", kbfx.SAVER_DEFAULT)
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Psaní a spořič").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Platí ve všech M1–M3 pro efekt i části klávesnice.")).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 6))
        tv = tk.BooleanVar(value=bool(ts["zapnuto"]))

        def on_t():
            ts["zapnuto"] = tv.get()
            self._build_typing()
            self.refresh()
        ttk.Checkbutton(f, text="Psaní pohání efekt – čím rychleji píšeš, tím rychlejší a jasnější efekt",
                        variable=tv, command=on_t).grid(row=2, column=0, columnspan=3, sticky="w", padx=20, pady=2)
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=3, sticky="ew", padx=20)
        b.columnconfigure(1, weight=1)
        row = 0
        if ts["zapnuto"]:
            self._slider(b, row, "Citlivost", ts, "sila", 1, 10)
            ttk.Label(b, style="Small.TLabel", wraplength=WRAP - 40, justify="left", text=(
                "Bez psaní svítí efekt na 35 % a běží pomaleji. Vyšší citlivost = plný jas už při pomalém "
                "psaní (5 ≈ 7 kláves za sekundu).")).grid(row=row + 1, column=0, columnspan=2, sticky="w",
                                                           pady=(0, 6))
            row += 2
        svv = tk.BooleanVar(value=bool(sv["zapnuto"]))

        def on_s():
            sv["zapnuto"] = svv.get()
            self._build_typing()
        ttk.Checkbutton(f, text="Spořič – po nečinnosti klávesnici ztlumit", variable=svv, command=on_s).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=20, pady=(8, 2))
        c = ttk.Frame(f)
        c.grid(row=5, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 16))
        c.columnconfigure(1, weight=1)
        if sv["zapnuto"]:
            self._slider(c, 0, "Po nečinnosti", sv, "minuty", 1, 30, 1, "{:g} min")
            self._slider(c, 1, "Jas ve spánku", sv, "jas", 0, 50, 5, "{:g} %")
            ttk.Label(c, style="Small.TLabel", wraplength=WRAP - 40, justify="left", text=(
                "Nečinnost = nikdo nesáhl na klávesnici ani myš (herní ovladač Windows nepočítají). Klávesnice "
                "za 3 s ztmavne, první stisk nebo pohyb myší ji probudí vlnou od stisknuté klávesy. "
                "V náhledu se spořič neukazuje.")).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._refit()

    def _refit(self):
        def fit():
            try:
                self.scroll.inner.update_idletasks()
                self.scroll._fit()
            except tk.TclError:
                pass
        self.scroll.after_idle(fit)

    # ------------------------------------------------------------ hlasitost (spolecne pro M1-M3)
    @property
    def vcfg(self):
        v = self.lcfg.get("hlasitost_klavesnice")
        if not isinstance(v, dict):
            v = self.lcfg["hlasitost_klavesnice"] = {}
        for k, d in hlasitost.DEFAULT.items():
            v.setdefault(k, list(d) if isinstance(d, list) else d)
        return v

    def _build_vol(self):
        f = self.vcard
        for w in f.winfo_children():
            w.destroy()
        v = self.vcfg
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Hlasitost na klávesnici").grid(row=0, column=0, columnspan=3, sticky="w", padx=20,
                                                         pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Po pohybu posuvníkem hlasitosti (nebo tlačítkem ztlumení) ukážou vybrané klávesy hlasitost Windows "
            "jako ukazatel – přednost před efektem, předvolbou i hudbou. Platí ve všech M1–M3.")).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 6))
        on = tk.BooleanVar(value=bool(v["zapnuto"]))

        def on_toggle():
            v["zapnuto"] = on.get()
            if not on.get():
                self.vol_pick = False
            self._build_vol()
            self._show_sel()
            self.refresh()
        ttk.Checkbutton(f, text="Ukazovat hlasitost na klávesnici", variable=on, command=on_toggle).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 4))
        if not v["zapnuto"]:
            ttk.Frame(f).grid(row=3, pady=(0, 10))
            self._refit()
            return
        r = 3
        self._vlabel(f, r, "Klávesy")
        gf = ttk.Frame(f)
        gf.grid(row=r, column=1, columnspan=2, sticky="w", pady=4)
        groups = [g for g in kbfx.KEY_GROUPS if g[0] != "vse"] + [("nic", "vymazat", None)]
        for i, (gid, name, zones) in enumerate(groups):
            def add(zones=zones):
                cur = set(v["klavesy"])
                if zones is None:
                    cur = set()
                else:
                    zs = set(zones) & set(self.items)
                    cur = cur - zs if zs <= cur else cur | zs
                v["klavesy"] = sorted(cur)
                self._vol_info()
                self._show_sel()
                self.vol_demo()
            ttk.Button(gf, text=name, command=add).grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)
        r += 1
        pv = tk.BooleanVar(value=self.vol_pick)

        def on_pick():
            self.vol_pick = pv.get()
            self._show_sel()
            self.refresh()
        pf = ttk.Frame(f)
        pf.grid(row=r, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(pf, text="vybírat klikem na klávesy v náhledu", variable=pv, command=on_pick).pack(
            side="left")
        self.vol_lbl = ttk.Label(pf, style="Small.TLabel")
        self.vol_lbl.pack(side="left", padx=(12, 0))
        self._vol_info()
        r += 1
        self._vlabel(f, r, "Plní se")
        sv = tk.StringVar(value=v["smer"])

        def on_dir():
            v["smer"] = sv.get()
            self.vol_demo()
        V.segmented(f, sv, hlasitost.DIRECTIONS, command=on_dir, style="SegSmall.Toolbutton").grid(
            row=r, column=1, columnspan=2, sticky="w", pady=4)
        r += 1
        self._vlabel(f, r, "Barvy")
        cf = ttk.Frame(f)
        cf.grid(row=r, column=1, columnspan=2, sticky="w", pady=4)
        for key, text in (("barva_od", "začátek"), ("barva_do", "konec"), ("pozadi", "nesvítící"),
                          ("ztlumeno", "ztlumeno")):
            ttk.Label(cf, text=text, style="Muted.TLabel").pack(side="left", padx=(0 if key == "barva_od" else 12, 4))

            def pick(key=key):
                c = colorchooser.askcolor(color=v[key], parent=self.vcard)[1]
                if c:
                    v[key] = c
                    V.set_swatch(btns[key], c)
                    self.vol_demo(muted=key == "ztlumeno")
            btns = getattr(self, "_vbtns", {})
            self._vbtns = btns
            btns[key] = V.swatch(cf, v[key], pick)
            btns[key].pack(side="left")
        r += 1
        self._vlabel(f, r, "Ostatní klávesy")
        ov = tk.StringVar(value=v["ostatni"])

        def on_other():
            v["ostatni"] = ov.get()
            self.vol_demo()
        V.segmented(f, ov, hlasitost.OTHERS, command=on_other, style="SegSmall.Toolbutton").grid(
            row=r, column=1, columnspan=2, sticky="w", pady=4)
        r += 1
        self._vlabel(f, r, "Zobrazit na")
        dv = tk.DoubleVar(value=float(v["doba_s"]))
        df = ttk.Frame(f)
        df.grid(row=r, column=1, columnspan=2, sticky="w", pady=4)
        dl = ttk.Label(df, width=6, text=f"{dv.get():.1f} s", font=V.MONO, anchor="e")

        def on_d(_e=None):
            v["doba_s"] = round(float(dv.get()), 1)
            dl.config(text=f"{v['doba_s']:.1f} s")
        V.scale(df, variable=dv, from_=0.5, to=6, resolution=0.5, length=200, command=on_d).pack(side="left")
        dl.pack(side="left", padx=(8, 0))
        r += 1
        bf = ttk.Frame(f)
        bf.grid(row=r, column=0, columnspan=3, sticky="w", padx=20, pady=(8, 16))
        ttk.Button(bf, text="Ukázat v náhledu", command=self.vol_demo).pack(side="left")
        ttk.Button(bf, text="Ukázat ztlumení", command=lambda: self.vol_demo(muted=True)).pack(side="left",
                                                                                             padx=(6, 0))
        ttk.Label(bf, style="Small.TLabel", text="  (na klávesnici platí po Uložit – zkus posuvníkem)").pack(
            side="left")
        self._refit()

    def _vlabel(self, f, row, text):
        ttk.Label(f, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="nw", padx=(20, 12), pady=4)

    def _vol_info(self):
        lbl = getattr(self, "vol_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        n = len(hlasitost.order(self.vcfg["klavesy"], "zleva"))
        lbl.config(text=f"vybráno kláves: {n}" if n else "zatím žádné klávesy – vyber skupinu nebo klikni")

    def vol_demo(self, muted=False):
        """Ukazka v nahledu: ukazatel vystoupa na 70 % (nebo ztlumeno)."""
        self._vdemo = (time.monotonic(), muted)

    def preview_top(self, now):
        """Ukazatel hlasitosti pro zivy nahled (editor_led): ukazka po tlacitku / pri vyberu klaves klikem."""
        v = self.vcfg
        if not v["zapnuto"] or not self.kc.get("zapnuto"):
            return None
        try:
            if not self.top.winfo_ismapped():
                return None
        except tk.TclError:
            return None
        t0, muted = getattr(self, "_vdemo", (None, False))
        if self.click_mode() == "hlasitost":      # vyber klaves klikem: ukazatel sviti porad
            self._vov.trigger(now)
            return self._vov.frame(v, now, 0.6, False)
        if t0 is None:
            return None
        age = now - t0
        if age < 1.2:
            self._vov.trigger(now)
        lvl = min(0.7, age / 1.2 * 0.7)
        top = self._vov.frame(v, now, lvl, muted)
        if top is None and age > 1.2:
            self._vdemo = (None, False)
        return top

    # ------------------------------------------------------------ klavesy G1-G5 (v nastaveni M)
    @property
    def gcfg(self):
        return self.prof["klavesy_g"]

    def _build_g(self):
        f = self.gcard
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(2, weight=1)
        V.card_title(f, f"Klávesy G1–G5 – nastavení M{self.m}").grid(row=0, column=0, columnspan=4, sticky="w",
                                                                       padx=20, pady=(14, 2))
        self.g_lbl = ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left")
        self.g_lbl.grid(row=1, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 8))
        names = [t for _k, t in klavesy_g.ACTIONS]
        notes = {"hudba": "vizualizér LED ze Spotify zapne / vypne",
                 "styl": "další styl vizualizéru (vypnutý vizualizér nejdřív zapne)",
                 "pl_dalsi": "playlist LED ventilátorů skočí na další efekt",
                 "pl_predchozi": "playlist LED ventilátorů skočí na předchozí efekt",
                 "playlist": "přepíná playlist LED ventilátorů / jeden efekt",
                 "lcd": "obrazovka Právě hraje (název, obal) na dobu z nastavení LCD, znovu = schovat"}
        NEW = "+ nová předvolba…"
        row = 2
        for n in klavesy_g.KEYS:
            a = self.gcfg.get(str(n))
            a = a if isinstance(a, dict) else {}
            kind = a.get("akce", "")
            ttk.Label(f, text=f"G{n}", style="Bold.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 10),
                                                                 pady=(10, 0))
            av = tk.StringVar(value=dict(klavesy_g.ACTIONS).get(kind, names[0]))
            cb = ttk.Combobox(f, textvariable=av, values=names, width=28, state="readonly")
            cb.grid(row=row, column=1, sticky="w", pady=(10, 0))

            def on_a(_e=None, n=n, av=av):
                k = next(k for k, t in klavesy_g.ACTIONS if t == av.get())
                old = self.gcfg.get(str(n)) if isinstance(self.gcfg.get(str(n)), dict) else {}
                if k:
                    self.gcfg[str(n)] = dict(old, akce=k)
                    if k == "predvolba" and klavesy_g.preset_by_id(self.lcfg, old.get("predvolba")) is None:
                        ps = [p for p in klavesy_g.presets(self.lcfg) if isinstance(p, dict)]
                        if ps:                          # prvni predvolba ze seznamu
                            self.gcfg[str(n)]["predvolba"] = ps[0].get("id")
                else:
                    self.gcfg.pop(str(n), None)
                self._build_g()
                self._refit()
            cb.bind("<<ComboboxSelected>>", on_a)
            if kind == "predvolba":
                pf = ttk.Frame(f)
                pf.grid(row=row, column=2, columnspan=2, sticky="w", padx=(10, 20), pady=(10, 0))
                ps = [p for p in klavesy_g.presets(self.lcfg) if isinstance(p, dict)]
                cur = klavesy_g.preset_by_id(self.lcfg, a.get("predvolba"))
                pv = tk.StringVar(value=klavesy_g.preset_name(cur) if cur else "")
                pc = ttk.Combobox(pf, textvariable=pv, values=[klavesy_g.preset_name(p) for p in ps] + [NEW],
                                  width=26, state="readonly")
                pc.pack(side="left")

                def on_p(_e=None, n=n, pv=pv):
                    if pv.get() == NEW:
                        p = klavesy_g.new_preset(self.lcfg)
                        self.gcfg[str(n)]["predvolba"] = p["id"]
                        self.edit_preset(p["id"])
                        return
                    p = next((p for p in klavesy_g.presets(self.lcfg)
                              if isinstance(p, dict) and klavesy_g.preset_name(p) == pv.get()), None)
                    if p is not None:
                        self.gcfg[str(n)]["predvolba"] = p.get("id")
                    self._build_g()
                    self._build_presets()
                pc.bind("<<ComboboxSelected>>", on_p)
                if cur is not None and klavesy_g.has_keyboard(cur):
                    eb = ttk.Button(pf, text="Upravit", command=lambda pid=cur.get("id"): self.edit_preset(pid))
                    eb.pack(side="left", padx=(8, 0))
                    if self.preset_cfg() is cur:
                        eb.state(["disabled"])
                row += 1
                ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 60, justify="left",
                          text=klavesy_g.describe(cur) if cur else
                          "Vyber předvolbu (seznam je na záložce Předvolby).").grid(
                    row=row, column=1, columnspan=3, sticky="w", pady=(2, 0))
            elif kind in notes:
                ttk.Label(f, style="Small.TLabel", text=notes[kind], wraplength=380, justify="left").grid(
                    row=row, column=2, columnspan=2, sticky="w", padx=(10, 20), pady=(10, 0))
            row += 1
            if kind:
                lf = ttk.Frame(f)
                lf.grid(row=row, column=1, columnspan=3, sticky="w", pady=(4, 0))
                self._g_light(lf, self.gcfg[str(n)], kind in klavesy_g.TOGGLES)
                row += 1
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            f"Akce a osvětlení G1–G5 patří k nastavení M{self.m} – v každém M můžou být jiné. Předvolba = "
            "dočasně jiné podsvícení ze seznamu předvoleb; stejná G-klávesa znovu vrátí nastavení M. Po startu "
            "aplikace a po uložení změn v okně platí nastavení M bez předvolby. Osvětlení: kontrolka = barva podle "
            "toho, jestli je funkce zapnutá; podle efektu = klávesa svítí jako ostatní. Platí po Uložit. G1–G5 a "
            "M1–M3 ovládá aplikace, dokud řídí podsvícení – v G HUB je nech bez přiřazení.")).grid(
            row=row, column=0, columnspan=4, sticky="w", padx=20, pady=(12, 16))

    def _g_light(self, f, a, toggle):
        """Osvetleni G-klavesy: kontrolka / podle efektu, barvy zapnuto / vypnuto, bliknuti pri stisku."""
        L = klavesy_g.light(a)
        ttk.Label(f, text="Osvětlení", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        sv = tk.StringVar(value=L["svetlo"])

        def on_s():
            a["svetlo"] = sv.get()
            self._build_g()
        V.segmented(f, sv, [("kontrolka", "kontrolka"), ("efekt", "podle efektu")], command=on_s,
                    style="SegSmall.Toolbutton").pack(side="left")

        def swatch(key, text):
            ttk.Label(f, text=text, style="Muted.TLabel").pack(side="left", padx=(12, 4))

            def pick():
                c = colorchooser.askcolor(color=klavesy_g.light(a)[key], parent=self.gcard)[1]
                if c:
                    a[key] = c
                    V.set_swatch(b, c)
            b = V.swatch(f, L[key], pick)
            b.pack(side="left")
        if L["svetlo"] == "kontrolka":
            if toggle:
                swatch("barva_zap", "zapnuto")
            swatch("barva_vyp", "vypnuto" if toggle else "barva")
        bv = tk.BooleanVar(value=bool(L["blik"]))

        def on_b():
            a["blik"] = bv.get()
            self._build_g()
        ttk.Checkbutton(f, text="bliknout při stisku", variable=bv, command=on_b).pack(side="left", padx=(14, 0))
        if L["blik"]:
            swatch("barva_blik", "")

    def _g_status(self, st, saved):
        lbl = getattr(self, "g_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        g = st.get("klavesy_g") if self.app.running else None
        if g is None:
            text = "Klávesy G a M začnou fungovat, až aplikace převezme klávesnici."
        else:
            text = "Na klávesnici teď: " + self._now_text(g) + "."
        if saved.get("klavesnice_m") != self.lcfg.get("klavesnice_m") or \
                saved.get("predvolby") != self.lcfg.get("predvolby"):
            text += " Změny klávesnice se projeví po Uložit."
        lbl.config(text=text)
        self._m_status(g)

    def _now_text(self, g):
        on = [f"M{g.get('m') or 1}"]
        if g.get("aktivni"):
            on.append(f"předvolba „{g.get('predvolba') or '?'}“ (G{g['aktivni']})")
        if g.get("hudba") is not None:
            on.append("hudba " + ("zapnutá" if g["hudba"] else "vypnutá"))
        if g.get("styl"):
            on.append("styl hudby: " + fx_style(g["styl"]))
        if g.get("playlist") is not None:
            on.append("playlist " + ("zapnutý" if g["playlist"] else "vypnutý"))
        return ", ".join(on)

    # ------------------------------------------------------------ nastaveni M1-M3 (nahore)
    def _build_mrow(self):
        """Vedle nahledu: vyber upravovaneho M (self.mrow) a zkopirovani do jineho M (self.crow)."""
        for f in (self.mrow, self.crow):
            for w in f.winfo_children():
                w.destroy()
        # popisky nad sebou / kratke: sloupec ma pri nejmensim okne jen ~240 px
        ttk.Label(self.mrow, text="Upravuji nastavení", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        mv = tk.StringVar(value=str(self.m))

        def on_m():
            self.set_m(int(mv.get()))
        V.segmented(self.mrow, mv, [(str(m), f"M{m}") for m in klavesy_g.M_KEYS], command=on_m).pack(anchor="w")
        row = ttk.Frame(self.crow)
        row.pack(anchor="w")
        ttk.Label(row, text="Zkopírovat do", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        for m in (m for m in klavesy_g.M_KEYS if m != self.m):
            def cp(m=m):
                klavesy_g.copy_profile(self.lcfg, self.m, m)
                self.m_msg.config(text=f"M{self.m} zkopírováno do M{m} (platí po Uložit).")
            ttk.Button(row, text=f"M{m}", command=cp, width=3).pack(side="left", padx=(0, 4))
        self.m_msg = ttk.Label(self.crow, style="Small.TLabel", wraplength=self._side_w, justify="left")
        self.m_msg.pack(anchor="w", pady=(2, 0))

    def set_m(self, m):
        """Upravovat nastaveni klavesnice Mm (zalozky Podsviceni, Klavesy G1-G5 a Pamet)."""
        self.m, self.preset, self.target, self._back = m, None, None, None
        self.sel.clear()
        self._build_mrow()
        self._build_light()
        self._build_g()
        self._build_presets()
        self._build_mem_m()
        self._scope()
        self._show_sel()
        self.refresh()
        self._refit()

    def _m_status(self, g):
        lbl = getattr(self, "m_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        if g is None:
            lbl.config(text="")
        else:
            act = g.get("m") or 1
            lbl.config(text=(f"Na klávesnici je teď M{act} (přepni klávesou M1–M3)." if act != self.m else
                             f"M{act} je na klávesnici právě aktivní."))

    # ------------------------------------------------------------ predvolby (spolecny seznam)
    def _build_presets(self):
        f = self.pcard
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Předvolby").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Společné pro M1–M3 – v každém M ji můžeš dát na kteroukoli G-klávesu (akce „předvolba“). Změna "
            "předvolby platí všude, kde je přiřazená.")).grid(row=1, column=0, columnspan=3, sticky="w", padx=20,
                                                              pady=(0, 8))
        tnames = [t for _k, t in klavesy_g.TARGETS]
        row = 2
        ps = klavesy_g.presets(self.lcfg)
        for i, p in enumerate(ps):
            if not isinstance(p, dict):
                continue
            nv = tk.StringVar(value=klavesy_g.preset_name(p))
            e = ttk.Entry(f, textvariable=nv, width=26)
            e.grid(row=row, column=0, sticky="w", padx=(20, 10), pady=(10, 0))

            def on_name(*_a, p=p, nv=nv):
                p["nazev"] = nv.get().strip() or f"Předvolba {p.get('id')}"
            nv.trace_add("write", on_name)
            e.bind("<Return>", lambda _e: (self._build_g(), self._build_light()))
            e.bind("<FocusOut>", lambda _e: self._build_g())
            bf = ttk.Frame(f)
            bf.grid(row=row, column=1, columnspan=2, sticky="w", pady=(10, 0))
            tv = tk.StringVar(value=dict(klavesy_g.TARGETS).get(p.get("cil", "klavesnice"), tnames[0]))
            tc = ttk.Combobox(bf, textvariable=tv, values=tnames, width=17, state="readonly")
            tc.pack(side="left")

            def on_t(_e=None, p=p, tv=tv):
                p["cil"] = next(k for k, t in klavesy_g.TARGETS if t == tv.get())
                if klavesy_g.has_fans(p) and not any(k in (p.get("nastaveni") or {})
                                                     for k in klavesy_g.PARTS["ventilatory"][0]):
                    klavesy_g.take_fans(p, self.lcfg)        # zacatek: ventilatory jak jsou ted
                self._build_presets()
                self._build_g()
                self._build_light()
            tc.bind("<<ComboboxSelected>>", on_t)
            if klavesy_g.has_keyboard(p):
                eb = ttk.Button(bf, text="Upravit klávesnici", command=lambda pid=p.get("id"): self.edit_preset(pid))
                eb.pack(side="left", padx=(8, 0))
                if self.preset_cfg() is p:
                    eb.state(["disabled"])
            if klavesy_g.has_fans(p):
                def fans(p=p):
                    klavesy_g.take_fans(p, self.lcfg)
                    self._build_presets()
                ttk.Button(bf, text="Převzít ventilátory", command=fans).pack(side="left", padx=(6, 0))

            def delete(i=i, p=p):
                if self.preset == p.get("id"):
                    self.preset = None
                del klavesy_g.presets(self.lcfg)[i]
                self._build_presets()
                self._build_g()
                self._build_light()
            ttk.Button(bf, text="Smazat", command=delete).pack(side="left", padx=(6, 0))
            row += 1
            used = klavesy_g.users(self.lcfg, p.get("id"))
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 40, justify="left", text=(
                klavesy_g.describe(p) + " · " + ("přiřazená: " + ", ".join(used) if used else "zatím nepřiřazená"))
            ).grid(row=row, column=0, columnspan=3, sticky="w", padx=(20, 20), pady=(2, 0))
            row += 1

        def add():
            p = klavesy_g.new_preset(self.lcfg)
            self.edit_preset(p["id"])
        ttk.Button(f, text="+ Nová předvolba", command=add).grid(row=row, column=0, sticky="w", padx=20,
                                                                  pady=(12, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "„Upravit klávesnici“ otevře záložku Podsvícení s nastavením předvolby (efekt, části, jas – náhled ji "
            "ukazuje), „Hotovo“ tam vrátí zpět sem. Ventilátory se do předvolby převezmou tak, jak jsou teď "
            "nastavené na stránce LED.")).grid(
            row=row + 1, column=0, columnspan=3, sticky="w", padx=20, pady=(8, 16))

    # ------------------------------------------------------------ integrovana pamet
    def _build_mem(self):
        f = self.mem
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Integrovaná paměť").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 6))
        ttk.Label(f, text="Stav", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(20, 10))
        self.mode_lbl = ttk.Label(f, text="zjišťuji…", font=V.FONT_B)
        self.mode_lbl.grid(row=1, column=1, sticky="w")
        ttk.Button(f, text="Záloha paměti", command=lambda: self._run(self._backup)).grid(
            row=1, column=2, sticky="e", padx=20)
        self.msg = ttk.Label(f, text="", style="Small.TLabel", wraplength=WRAP, justify="left")
        self.msg.grid(row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(4, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Paměť přepíná aplikace sama: když řídí podsvícení, paměť vypne, a při ukončení aplikace, "
            "uspání PC nebo vypnutí řízení ji zase zapne – klávesnice pak svítí podle profilu v paměti. "
            "V G HUB nech u klávesnice paměť zapnutou (jinak G HUB barvy přepisuje). "
            "Záloha jen čte obsah paměti do složky zalohy.")).grid(row=3, column=0, columnspan=3, sticky="w",
                                                                   padx=20, pady=(4, 10))
        self.mem_m = ttk.Frame(f)
        self.mem_m.grid(row=4, column=0, columnspan=3, sticky="ew", padx=20, pady=(0, 16))
        self._build_mem_m()
        self._run(self._read_mem_lights)

    # ------------------------------------------------------------ podsviceni v pameti (bez aplikace)
    def mem_cfg(self, m=None):
        """Co se nahraje do pameti pro Mm: {"klavesy": efekt ({} = podle M), "logo": efekt / "jako"}."""
        return klavesy_g.profile(self.lcfg, self.m if m is None else m)["pamet"]

    def mem_lights(self, m):
        import klavesnice_pamet as P
        v = self.mem_cfg(m)
        keys = v["klavesy"] or {"typ": "ponechat"}         # vychozi: v pameti nic nemenit
        logo = v.get("logo", "jako")
        logo = {"typ": "ponechat"} if logo == "jako" and keys["typ"] == "ponechat" else (
            keys if logo == "jako" else logo)
        return dict(keys), dict(logo)

    def _build_mem_m(self):
        import klavesnice_pamet as P
        f = self.mem_m
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(1, weight=1)
        v = self.mem_cfg()
        auto = not v["klavesy"]
        if auto:                                  # vychozi "nechat, jak je"; prvni zmena se ulozi do nastaveni M
            def attach(d):
                v["klavesy"] = d
            e = _Lazy({"typ": "ponechat"}, attach)
        else:
            e = v["klavesy"]
        ttk.Separator(f).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(f, text=f"Bez aplikace – nastavení M{self.m} v paměti klávesnice", style="Bold.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w")
        cur = (getattr(self, "_mem_lights", None) or {}).get(self.m)
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            (f"V paměti teď (profil {self.m}): klávesy {P.describe(cur[0])}, logo {P.describe(cur[1])}. "
             if cur else "Co je v paměti teď, se načítá… ")
            + "Paměť umí jen vestavěné efekty – barvy jednotlivých kláves, části a efekty aplikace se uložit "
              "nedají. Klávesnice tak svítí, když aplikace neběží (před přihlášením, po ukončení).")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(2, 6))

        def rebuild():
            self._build_mem_m()
            self._refit()
        self._label(f, 3, "Klávesy")
        tv = tk.StringVar(value=e.get("typ", "cyklus"))

        def on_t():
            e["typ"] = tv.get()
            rebuild()
        V.segmented(f, tv, [P.KEEP] + P.TYPES, command=on_t, style="SegSmall.Toolbutton").grid(
            row=3, column=1, sticky="w", pady=4)
        r = 4
        if e.get("typ") in ("barva", "dychani"):
            self._label(f, r, "Barva")
            cf = ttk.Frame(f)
            cf.grid(row=r, column=1, sticky="w", pady=4)

            def pick():
                c = colorchooser.askcolor(color=e.get("barva", "#ffffff"), parent=self.mem)[1]
                if c:
                    e["barva"] = c
                    V.set_swatch(sw, c)
            sw = V.swatch(cf, e.get("barva", "#ffffff"), pick)
            sw.pack(side="left")
            r += 1
        if e.get("typ") in ("dychani", "cyklus"):
            e.setdefault("perioda_s", 5.0)
            self._slider(f, r, "Délka cyklu", e, "perioda_s", 1.0, 20.0, 0.5, "{:.1f} s")
            r += 1
        if e.get("typ") not in ("vypnuto", "ponechat"):
            e.setdefault("jas", 100)
            self._slider(f, r, "Jas", e, "jas", 10, 100, 5, "{:.0f} %")
            r += 1
        self._label(f, r, "Logo")
        lf = ttk.Frame(f)
        lf.grid(row=r, column=1, sticky="w", pady=4)
        logo = v.get("logo", "jako")
        lv = tk.StringVar(value="jako" if logo == "jako" else (logo.get("typ") if isinstance(logo, dict) else "jako"))

        def on_l():
            if lv.get() == "jako":
                v["logo"] = "jako"
            elif lv.get() in ("vypnuto", "ponechat"):
                v["logo"] = {"typ": lv.get()}
            else:
                v["logo"] = {"typ": "barva", "barva": e.get("barva", "#ffffff"), "jas": 100}
            rebuild()
        V.segmented(lf, lv, [("jako", "jako klávesy"), ("ponechat", "nechat, jak je"), ("vypnuto", "vypnuto"),
                             ("barva", "jedna barva")],
                    command=on_l, style="SegSmall.Toolbutton").pack(side="left")
        if isinstance(logo, dict) and logo.get("typ") == "barva":
            def pick_l():
                c = colorchooser.askcolor(color=logo.get("barva", "#ffffff"), parent=self.mem)[1]
                if c:
                    logo["barva"] = c
                    V.set_swatch(lsw, c)
            lsw = V.swatch(lf, logo.get("barva", "#ffffff"), pick_l)
            lsw.pack(side="left", padx=(10, 0))
        r += 1
        bf = ttk.Frame(f)
        bf.grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))

        def suggest():
            v["klavesy"], v["logo"] = P.suggest(klavesy_g.profile(self.lcfg, self.m))[0], "jako"
            rebuild()
        ttk.Button(bf, text=f"Navrhnout podle efektu M{self.m}", command=suggest).pack(side="left")
        ttk.Button(bf, text="Nahrát M1–M3 do paměti klávesnice",
                   command=lambda: self._run(self._write_mem)).pack(side="left", padx=(6, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            ("Teď se v paměti nic nezmění („nechat, jak je“ – tvoje rozložení po klávesách z G HUB zůstane). "
             if auto else "")
            + "Nahrání zapíše všechna tři M (každé svoje nastavení odsud) hned, bez Uložit; předtím udělá zálohu "
            "celé paměti a po zápisu ji přečte a porovná. Nastavení odsud se do config.json uloží až po Uložit.")
        ).grid(row=r + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _read_mem_lights(self):
        import klavesnice_pamet as P
        self._mem_lights = P.read_lights()
        self._mode = __import__("klavesnice").get_mode()
        return None

    def _write_mem(self):
        import klavesnice_pamet as P
        path = P.write_lights({m: self.mem_lights(m) for m in klavesy_g.M_KEYS})
        self._mem_lights = P.read_lights()
        return f"Nahráno do paměti klávesnice (M1–M3), záloha před zápisem: zalohy\\{os.path.basename(path)}"

    def _run(self, fn):
        """Prace s klavesnici ve vlakne (HID muze chvili trvat); vysledek ukaze _poll."""
        if self._job is not None and "hotovo" not in self._job:
            return
        job = self._job = {}

        def work():
            try:
                job["zprava"] = fn()
            except Exception as e:
                job["chyba"] = str(e)
            finally:
                job["hotovo"] = True
        threading.Thread(target=work, name="klavesnice", daemon=True).start()
        self.mem.after(100, self._poll)

    def _poll(self):
        job = self._job
        try:
            if not self.mem.winfo_exists():
                return
        except tk.TclError:
            return
        if job is None or "hotovo" not in job:
            self.mem.after(100, self._poll)
            return
        if "chyba" in job:
            self.msg.config(text="Chyba: " + job["chyba"], foreground=V.ERR)
        elif job.get("zprava"):
            self.msg.config(text=job["zprava"], foreground=V.OK)
        self._show_mode()
        if getattr(self, "_mem_shown", None) != getattr(self, "_mem_lights", None):
            self._mem_shown = getattr(self, "_mem_lights", None)
            self._build_mem_m()                   # co je v pameti (po nacteni / zapisu)
            self._refit()

    def _tick(self):
        """Stav pameti obcas precist znovu (prepina ji vlakno LED v bezici aplikaci)."""
        try:
            if not self.mem.winfo_exists():
                return
        except tk.TclError:
            return
        if self.mem.winfo_ismapped():
            self._run(self._read_mode)
        self.mem.after(POLL_MS, self._tick)

    def _read_mode(self):
        import klavesnice
        self._mode = klavesnice.get_mode()
        return None

    def _backup(self):
        import klavesnice
        path = klavesnice.backup_memory()
        self._mode = klavesnice.get_mode()
        return f"Záloha uložena: zalohy\\{os.path.basename(path)}"

    def _show_mode(self):
        import klavesnice
        m = self._mode
        if m is None:
            self.mode_lbl.config(text="nezjištěno", foreground=V.MUTED)
            return
        onboard = m == klavesnice.MODE_ONBOARD
        want = bool(self.kc.get("zapnuto")) and self.lcfg.get("zapnuto", True)
        self.mode_lbl.config(text="zapnutá – klávesnice svítí sama" if onboard else "vypnutá – podsvícení řídí aplikace",
                             foreground=V.WARN if onboard == want else V.TEXT)
        if onboard and want:
            self.msg.config(text="Paměť je ještě zapnutá – běžící aplikace ji vypne do pár sekund po Uložit.",
                            foreground=V.WARN)
        elif not onboard and not want:
            self.msg.config(text="Paměť je vypnutá – běžící aplikace ji zapne do pár sekund po Uložit.",
                            foreground=V.WARN)
        elif str(self.msg.cget("foreground")) == str(V.WARN):
            self.msg.config(text="")
