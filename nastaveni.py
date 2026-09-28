# nastaveni.py - okno nastaveni RGB-LCD (Kraken LCD, chlazeni, LED, Alphacool)
# Vzhled: vzhled.py (tmavy motiv podle navrhu z Claude Design).
# Spusteni: nastaveni.bat (nebo: pyw nastaveni.py)
# Po kliknuti na "Ulozit" si bezici aplikace nastaveni nacte sama do 1 s.

import copy
import json
import os
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

import config
import hwinfo
import screens
import vzhled as V

STATE = os.path.join(config.BASE, "stav.json")

TYPES = screens.TYPES
MIN_REFRESH_S = config.MIN_REFRESH_S
UNITS = ["auto", "°", "GHz", "MHz", "%", "RPM", "W", "V", ""]

_ONE = {"nadpis": "", "senzor": "", "min": 0, "max": 100, "jednotka": "auto",
        "delitel": 1, "desetinna_mista": 0}
_TWO = {"nadpis1": "A", "senzor1": "", "min1": 0, "max1": 100,
        "nadpis2": "B", "senzor2": "", "min2": 0, "max2": 100,
        "jednotka": "auto", "delitel": 1, "desetinna_mista": 0}
NEW_SCREEN = {
    "dva_bary": dict(_TWO, typ="dva_bary"),
    "oblouk": dict(_ONE, typ="oblouk"),
    "budik": dict(_ONE, typ="budik"),
    "dva_kruhy": dict(_TWO, typ="dva_kruhy"),
    "graf": dict(_ONE, typ="graf", delka_s=120),
    "hodiny": {"typ": "hodiny"},
    "dva_oblouky": dict(_TWO, typ="dva_oblouky", nadpis1="CPU", senzor1="CPU (Tctl/Tdie)",
                        nadpis2="GPU", senzor2="Teplota GPU"),
    "segmenty": dict(_ONE, typ="segmenty"),
    "ctyri_hodnoty": dict(_TWO, typ="ctyri_hodnoty", nadpis3="C", senzor3="", min3=0, max3=100,
                          nadpis4="D", senzor4="", min4=0, max4=100),
    "chlazeni": {"typ": "chlazeni"},
    "graf_dva": dict(_TWO, typ="graf_dva", delka_s=120),
    "hodiny_analog": {"typ": "hodiny_analog", "datum": False},
    "hodiny_datum": {"typ": "hodiny_datum", "datum": False},
    "hodiny_pod_sebou": {"typ": "hodiny_pod_sebou", "datum": False},
    "obrazek": {"typ": "obrazek", "soubor": "kraken/ryzen7_odznak.png", "uprava": "beze změny"},
}
CLOCKS = ("hodiny", "hodiny_analog", "obrazek")         # bez posuvniku velikosti textu

# (klic, popisek, druh pole) pro editor obrazovky
_F_ONE = [("nadpis", "Popisek", "text"), ("senzor", "Senzor", "sensor"),
          ("min", "Minimum", "num"), ("max", "Maximum", "num")]
_F_TWO = [("nadpis1", "Horní / vnější – popisek", "text"), ("senzor1", "Horní / vnější – senzor", "sensor"),
          ("min1", "Horní / vnější – minimum", "num"), ("max1", "Horní / vnější – maximum", "num"),
          ("nadpis2", "Dolní / vnitřní – popisek", "text"), ("senzor2", "Dolní / vnitřní – senzor", "sensor"),
          ("min2", "Dolní / vnitřní – minimum", "num"), ("max2", "Dolní / vnitřní – maximum", "num")]
_F_FMT = [("jednotka", "Jednotka", "unit"), ("delitel", "Dělitel (1000 = MHz→GHz)", "num"),
          ("desetinna_mista", "Desetinná místa", "int")]
_F_TWO_LR = [(k, t.replace("Horní / vnější", "Levý").replace("Dolní / vnitřní", "Pravý"), kd)
             for k, t, kd in _F_TWO]
_F_FOUR = [(f"{k}{n}", f"{pos} – {t}", kd)
           for n, pos in (("1", "Vlevo nahoře"), ("2", "Vpravo nahoře"), ("3", "Vlevo dole"), ("4", "Vpravo dole"))
           for k, t, kd in (("nadpis", "popisek", "text"), ("senzor", "senzor", "sensor"),
                            ("min", "minimum", "num"), ("max", "maximum", "num"))]
FIELDS = {
    "dva_oblouky": _F_TWO_LR + _F_FMT,
    "segmenty": _F_ONE + _F_FMT,
    "ctyri_hodnoty": _F_FOUR + _F_FMT,
    "chlazeni": [],
    "graf_dva": [(k, t.replace("Horní / vnější", "Hodnota 1").replace("Dolní / vnitřní", "Hodnota 2"), kd)
                 for k, t, kd in _F_TWO] + [("delka_s", "Délka grafu (s)", "int")] + _F_FMT,
    "hodiny_analog": [("datum", "Zobrazit datum", "bool")],
    "hodiny_datum": [("datum", "Zobrazit datum", "bool")],
    "hodiny_pod_sebou": [("datum", "Zobrazit datum", "bool")],
    "obrazek": [("soubor", "Obrázek (složka obrazky)", "image"), ("uprava", "Úprava", "mode")],
    "dva_bary": _F_TWO + _F_FMT,
    "dva_kruhy": _F_TWO + _F_FMT,
    "oblouk": _F_ONE + _F_FMT,
    "budik": _F_ONE + _F_FMT,
    "graf": _F_ONE + [("delka_s", "Délka grafu (s)", "int")] + _F_FMT,
    "hodiny": [],
}


def load_data():
    """Aktualni hodnoty: ze stav.json (pise ho bezici aplikace), jinak primo z HWiNFO."""
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
        if time.time() - st.get("cas", 0) < 10:
            return (st["data"], True, st.get("chlazeni", {}), st.get("historie", {}),
                    st.get("alphacool", {}), st.get("led", {}))
    except (OSError, ValueError, KeyError):
        pass
    import systemdata
    data = hwinfo.read_full()
    data.update(systemdata.read())
    return data, False, {}, {}, {}, {}


PAGES = [("lcd", "Kraken LCD", "Obrazovky displeje 240 × 240 a jejich rotace"),
         ("cool", "Chlazení", "Pumpa a ventilátory Krakenu"),
         ("led", "LED ventilátorů", "2× F140 RGB Core (NZXT) a ventilátory na ARGB hlavičce desky"),
         ("alpha", "Alphacool LCD", "Monochromatický displej 240 × 128 – editor rozvržení")]


def _nav_icon(c, kind, color):
    """Ikony navigace kreslene na platne 20x20."""
    c.delete("all")
    w = dict(fill="", outline=color, width=1.6)
    if kind == "lcd":
        c.create_oval(2, 2, 18, 18, **w)
        c.create_oval(7, 7, 13, 13, **w)
    elif kind == "cool":
        c.create_oval(8, 8, 12, 12, **w)
        for a in (0, 90, 180, 270):
            c.create_arc(3, 3, 17, 17, start=a, extent=60, style="arc", outline=color, width=1.6)
    elif kind == "led":
        c.create_oval(7, 7, 13, 13, **w)
        for x0, y0, x1, y1 in ((10, 1, 10, 4), (10, 16, 10, 19), (1, 10, 4, 10), (16, 10, 19, 10),
                               (3.5, 3.5, 5.5, 5.5), (14.5, 14.5, 16.5, 16.5), (3.5, 16.5, 5.5, 14.5),
                               (14.5, 5.5, 16.5, 3.5)):
            c.create_line(x0, y0, x1, y1, fill=color, width=1.6)
    else:
        c.create_rectangle(2, 5, 18, 15, outline=color, width=1.6)
        c.create_line(5, 9, 9, 9, fill=color, width=1.6)
        c.create_line(5, 12, 15, 12, fill=color, width=1.6)


class App(tk.Tk):
    last_page = 0            # vybrana stranka (zachova se pri "Vratit ulozene")

    def __init__(self):
        super().__init__()
        self.title("RGB-LCD – nastavení")
        try:
            self.iconbitmap(default=os.path.join(config.BASE, "ikona.ico"))
        except tk.TclError:
            pass
        V.apply(self)
        self.geometry("1320x860")
        self.minsize(1180, 740)
        self.cfg = config.load()
        self.saved = copy.deepcopy(self.cfg)
        self.data, self.running, self.cstate, self.hist, self.astate, self.lstate = load_data()
        self.sel = 0
        self._preview_img = None
        self._building = False

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()
        main = tk.Frame(self, bg=V.BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        self._build_header(main)

        self.pages = {}
        for key, _t, _s in PAGES:
            f = tk.Frame(main, bg=V.BG)
            f.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
            self.pages[key] = f
        self._build_lcd_page(self.pages["lcd"])
        cool_scroll = V.ScrollFrame(self.pages["cool"])
        cool_scroll.pack(fill="both", expand=True)
        self._build_cool_page(cool_scroll.inner)
        led_scroll = V.ScrollFrame(self.pages["led"])
        led_scroll.pack(fill="both", expand=True)
        from editor_led import LedEditor
        self.leds = LedEditor(led_scroll.inner, self)
        alpha_scroll = V.ScrollFrame(self.pages["alpha"])
        alpha_scroll.pack(fill="both", expand=True)
        from editor_alphacool import AlphaEditor
        self.alpha = AlphaEditor(alpha_scroll.inner, self)

        self.show_page(App.last_page)
        self._refresh_list()
        self._select(0)
        self._update_sidebar()
        self.bind("<Control-s>", lambda e: self.save())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1000, self._tick)

    # ------------------------------------------------------- navigace
    def _build_sidebar(self):
        sb = tk.Frame(self, bg=V.SIDEBAR, width=236, highlightthickness=1, highlightbackground=V.CARD_LINE)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(len(PAGES) + 1, weight=1)

        logo = tk.Frame(sb, bg=V.SIDEBAR)
        logo.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 22))
        c = tk.Canvas(logo, width=30, height=30, bg=V.SIDEBAR, highlightthickness=0)
        c.create_oval(2, 2, 28, 28, outline=V.ACCENT, width=2)
        c.create_oval(8, 8, 22, 22, outline=V.ORANGE, width=2, dash=(3, 2))
        c.pack(side="left")
        t = tk.Frame(logo, bg=V.SIDEBAR)
        t.pack(side="left", padx=10)
        tk.Label(t, text="RGB-LCD", bg=V.SIDEBAR, fg=V.TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(t, text="Kraken 240 RGB", bg=V.SIDEBAR, fg=V.DIM, font=V.SMALL).pack(anchor="w")

        self._nav = []
        for i, (key, title, _s) in enumerate(PAGES):
            item = tk.Frame(sb, bg=V.SIDEBAR, height=44, cursor="hand2")
            item.grid(row=i + 1, column=0, sticky="new", padx=12, pady=2)
            item.pack_propagate(False)
            ic = tk.Canvas(item, width=20, height=20, bg=V.SIDEBAR, highlightthickness=0)
            ic.pack(side="left", padx=(12, 12))
            lb = tk.Label(item, text=title, bg=V.SIDEBAR, fg=V.MUTED, font=("Segoe UI Semibold", 10))
            lb.pack(side="left")
            for w in (item, ic, lb):
                w.bind("<Button-1>", lambda e, i=i: self.show_page(i))
                w.bind("<Enter>", lambda e, i=i: self._paint_nav(i, hover=True))
                w.bind("<Leave>", lambda e, i=i: self._paint_nav(i))
            self._nav.append((key, item, ic, lb))
        sb.rowconfigure(len(PAGES), weight=0)

        box = tk.Frame(sb, bg="#181c21", highlightthickness=1, highlightbackground=V.CARD_LINE)
        box.grid(row=len(PAGES) + 2, column=0, sticky="sew", padx=14, pady=16)
        box.columnconfigure(1, weight=1)
        self._side = {}
        for r, key in enumerate(("app", "hwinfo")):
            dot = tk.Label(box, text="●", bg="#181c21", fg=V.DIM, font=("Segoe UI", 8))
            dot.grid(row=r, column=0, sticky="w", padx=(12, 6), pady=(10 if r == 0 else 2, 2))
            lbl = tk.Label(box, text="", bg="#181c21", fg=V.TEXT, font=V.SMALL, anchor="w")
            lbl.grid(row=r, column=1, columnspan=2, sticky="w", pady=(10 if r == 0 else 2, 2))
            self._side[key] = (dot, lbl)
        tk.Frame(box, bg="#262b33", height=1).grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=8)
        for r, (key, text, color) in enumerate((("cpu", "CPU", V.TEXT), ("liquid", "Kapalina", V.ACCENT)), start=3):
            tk.Label(box, text=text, bg="#181c21", fg=V.MUTED, font=V.SMALL).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10 if r == 4 else 2))
            val = tk.Label(box, text="–", bg="#181c21", fg=color, font=("Consolas", 10))
            val.grid(row=r, column=2, sticky="e", padx=12, pady=(0, 10 if r == 4 else 2))
            self._side[key] = val

    def _paint_nav(self, i, hover=False):
        key, item, ic, lb = self._nav[i]
        active = i == App.last_page
        bg = "#1f242b" if active else ("#1b1f25" if hover else V.SIDEBAR)
        for w in (item, ic, lb):
            w.config(bg=bg)
        lb.config(fg=V.TEXT if active or hover else V.MUTED)
        _nav_icon(ic, key, V.ACCENT if active else (V.TEXT if hover else V.MUTED))

    def show_page(self, i):
        App.last_page = i
        key, title, sub = PAGES[i]
        for k, f in self.pages.items():
            if k == key:
                f.grid()
            else:
                f.grid_remove()
        for j in range(len(PAGES)):
            self._paint_nav(j)
        self.h_title.config(text=title)
        self.h_sub.config(text=sub)

    def _update_sidebar(self):
        dot, lbl = self._side["app"]
        dot.config(fg=V.OK if self.running else V.WARN)
        lbl.config(text="Aplikace běží" if self.running else "Aplikace neběží")
        dot, lbl = self._side["hwinfo"]
        hw = any(not k.startswith("@") for k in self.data)
        dot.config(fg=V.OK if hw else V.ERR)
        lbl.config(text="HWiNFO posílá data" if hw else "HWiNFO bez dat", fg=V.MUTED)
        cpu = self._cpu_temp()
        self._side["cpu"].config(text=f"{cpu:.0f} °C" if cpu is not None else "–")
        lq = (self.data.get(config.LIQUID) or {}).get("value")
        self._side["liquid"].config(text=f"{lq:.1f} °C".replace(".", ",") if lq is not None else "–")

    def _cpu_temp(self):
        if self.cstate.get("teplota") is not None:
            return self.cstate["teplota"]
        name = self.cfg["chlazeni"].get("senzor_cpu", "CPU (Tctl/Tdie)")
        return (self.data.get(name) or {}).get("value")

    # ---------------------------------------------------------- hlavicka
    def _build_header(self, main):
        h = tk.Frame(main, bg=V.BG)
        h.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 16))
        h.columnconfigure(0, weight=1)
        self.h_title = ttk.Label(h, style="H1.TLabel")
        self.h_title.grid(row=0, column=0, sticky="w")
        self.h_sub = ttk.Label(h, style="PageMuted.TLabel")
        self.h_sub.grid(row=1, column=0, sticky="w")
        self.status = tk.Label(h, text="", bg=V.BG, fg=V.WARN, font=V.SMALL)
        self.status.grid(row=0, column=1, rowspan=2, padx=12)
        ttk.Button(h, text="Vrátit uložené", command=self.revert).grid(row=0, column=2, rowspan=2, padx=4)
        ttk.Button(h, text="Uložit   Ctrl+S", style="Accent.TButton", command=self.save).grid(
            row=0, column=3, rowspan=2, padx=(4, 0))
        self._status_msg = None

    def _update_dirty(self):
        if self._status_msg:
            return
        if self.cfg != self.saved:
            self.status.config(text="●  Neuložené změny", fg=V.WARN)
        else:
            self.status.config(text="")

    # ------------------------------------------------------ stranka LCD
    def _build_lcd_page(self, page):
        page.columnconfigure(1, weight=1)
        page.rowconfigure(0, weight=1)
        self._build_list(page)
        ec = V.card(page)
        ec.grid(row=0, column=1, sticky="nsew", padx=16)
        ec.rowconfigure(0, weight=1)
        ec.columnconfigure(0, weight=1)
        sc = V.ScrollFrame(ec, bg=V.CARD)
        sc.grid(row=0, column=0, sticky="nsew", padx=(16, 4), pady=12)
        self.ed = sc.inner
        self.ed.columnconfigure(0, weight=1)
        self._build_right(page)

    # ---------------------------------------------------------- seznam
    def _build_list(self, page):
        f = V.card(page, width=290)
        f.grid(row=0, column=0, sticky="ns")
        f.grid_propagate(False)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew", padx=(16, 12), pady=(14, 8))
        top.columnconfigure(0, weight=1)
        V.card_title(top, "Pořadí rotace").grid(row=0, column=0, sticky="w")
        add = ttk.Menubutton(top, text="+ Přidat")
        m = tk.Menu(add, tearoff=0)
        for t, name in TYPES.items():
            m.add_command(label=name, command=lambda t=t: self.add(t))
        add["menu"] = m
        add.grid(row=0, column=1)
        self.lst = V.listbox(f, width=30, height=18)
        self.lst.grid(row=1, column=0, sticky="nsew", padx=8)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._select(self._cur_index()))

        b = ttk.Frame(f)
        b.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        b.columnconfigure(2, weight=1)
        ttk.Button(b, text="▲", width=3, command=lambda: self.move(-1)).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(b, text="▼", width=3, command=lambda: self.move(1)).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(b, text="Odebrat", style="Danger.TButton", command=self.remove).grid(
            row=0, column=2, sticky="ew", padx=2)
        ttk.Button(b, text="Zapnout / vypnout", command=self.toggle).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=2, pady=(6, 0))

    def _cur_index(self):
        s = self.lst.curselection()
        return s[0] if s else self.sel

    def _label(self, s):
        mark = "●" if s.get("zapnuto", True) else "○"
        if "nadpis1" in s:
            name = " / ".join(s.get(f"nadpis{n}", "") for n in "1234" if f"nadpis{n}" in s)
        elif "senzor" in s:
            name = s.get("nadpis") or s.get("senzor", "")
        elif s["typ"] == "obrazek":
            name = os.path.splitext(os.path.basename(s.get("soubor", "")))[0]
        else:
            name = ""
        return f" {mark}  {TYPES[s['typ']]}: {name}".rstrip(": ")

    def _refresh_list(self):
        self.lst.delete(0, "end")
        for i, s in enumerate(self.cfg["obrazovky"]):
            self.lst.insert("end", self._label(s))
            if not s.get("zapnuto", True):
                self.lst.itemconfig(i, fg=V.DIM)
        if self.cfg["obrazovky"]:
            self.sel = min(self.sel, len(self.cfg["obrazovky"]) - 1)
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(self.sel)

    def add(self, typ):
        new = copy.deepcopy(NEW_SCREEN[typ])
        new["zapnuto"] = True
        new["velikost_obsahu"] = 0.92
        if typ not in CLOCKS:
            new["velikost_textu"] = 1.0
        self.cfg["obrazovky"].insert(self.sel + 1, new)
        self.sel += 1 if self.cfg["obrazovky"][:-1] else 0
        self._refresh_list()
        self._select(self.sel)

    def remove(self):
        if not self.cfg["obrazovky"]:
            return
        del self.cfg["obrazovky"][self.sel]
        self.sel = max(0, self.sel - 1)
        self._refresh_list()
        self._select(self.sel)

    def move(self, step):
        i, j = self.sel, self.sel + step
        s = self.cfg["obrazovky"]
        if 0 <= j < len(s):
            s[i], s[j] = s[j], s[i]
            self.sel = j
            self._refresh_list()

    def toggle(self):
        if self.cfg["obrazovky"]:
            s = self.cfg["obrazovky"][self.sel]
            s["zapnuto"] = not s.get("zapnuto", True)
            self._refresh_list()

    # ------------------------------------------------------- alphacool
    def _update_alpha(self):
        if hasattr(self, "alpha"):
            self.alpha.refresh()

    def _sensor_names(self):
        own = sorted(k for k in self.data if k.startswith("@") and k != config.LIQUID)
        names = sorted(k for k in self.data if not k.startswith("@"))
        return [config.LIQUID] + own + names

    # --------------------------------------------------------- chlazeni
    COOL_ROWS = 8

    def _build_cool_page(self, page):
        cool = self.cfg["chlazeni"]
        cool.setdefault("cpu", copy.deepcopy(config.DEFAULTS["chlazeni"]["cpu"]))
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        # dlazdice s aktualnim stavem
        tiles = tk.Frame(page, bg=V.BG)
        tiles.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        self.tiles = {}
        for c, (key, label, color) in enumerate((("cpu", "Teplota CPU (průměr)", V.TEXT),
                                                 ("liquid", "Kapalina", V.ACCENT),
                                                 ("pump", "Pumpa", V.ACCENT),
                                                 ("fans", "Ventilátory", V.ORANGE))):
            tiles.columnconfigure(c, weight=1, uniform="tile")
            t = V.card(tiles)
            t.grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 8, 0 if c == 3 else 8))
            ttk.Label(t, text=label, style="Small.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                               padx=16, pady=(12, 0))
            val = tk.Label(t, text="–", bg=V.CARD, fg=color, font=V.MONO_BIG)
            val.grid(row=1, column=0, sticky="w", padx=(14, 4))
            unit = ttk.Label(t, text="", style="Muted.TLabel")
            unit.grid(row=1, column=1, sticky="sw", pady=(0, 6))
            t.columnconfigure(1, weight=1)
            bar = tk.Canvas(t, height=4, bg="#262b33", highlightthickness=0)
            bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 4))
            sub = ttk.Label(t, text="", style="Small.TLabel")
            sub.grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))
            self.tiles[key] = (val, unit, bar, sub, color)

        # graf krivek
        gc = V.card(page)
        gc.grid(row=1, column=0, sticky="nsew")
        gc.columnconfigure(0, weight=1)
        head = ttk.Frame(gc)
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 4))
        head.columnconfigure(0, weight=1)
        V.card_title(head, "Křivky výkonu").grid(row=0, column=0, sticky="w")
        self.mode = tk.StringVar(value=cool.get("zdroj", "cpu"))
        self.edit_mode = tk.StringVar(value=self.mode.get())
        V.segmented(head, self.edit_mode, [("cpu", "Podle CPU"), ("kapalina", "Podle kapaliny (i záloha)")],
                    command=self._build_curve_table).grid(row=0, column=1)
        self.cool_status = ttk.Label(gc, font=V.FONT_B, justify="left")
        self.cool_status.grid(row=1, column=0, sticky="w", padx=20, pady=(4, 6))
        self.cool_canvas = tk.Canvas(gc, height=300, bg=V.CARD, highlightthickness=0)
        self.cool_canvas.grid(row=2, column=0, sticky="ew", padx=12)
        self.cool_canvas.bind("<Configure>", lambda e: self._draw_curves())
        note = ttk.Label(gc, style="Small.TLabel", justify="left", wraplength=560, text=(
            "Podle CPU: aplikace každou sekundu nastaví výkon podle průměrné teploty CPU. "
            "Když aplikace skončí (i zavřením okna nebo vypnutím PC), nastane chyba spojení nebo HWiNFO "
            "přestane posílat teplotu, převezme řízení Kraken sám podle křivek kapaliny (záloha). "
            "Totéž platí při vypnutém řízení. Od 59 °C kapaliny vždy 100 %, pumpa nikdy pod 20 %."))
        note.grid(row=3, column=0, sticky="ew", padx=20, pady=(8, 16))
        gc.bind("<Configure>", lambda e: note.config(wraplength=max(200, e.width - 44)))

        right = tk.Frame(page, bg=V.BG, width=330)
        right.grid(row=1, column=1, sticky="ns", padx=(16, 0))

        rc = V.card(right)
        rc.pack(fill="x")
        rc.columnconfigure(0, weight=1)
        cv = tk.BooleanVar(value=cool.get("zapnuto", True))
        ttk.Checkbutton(rc, text="Řídit pumpu a ventilátory", variable=cv, style="TCheckbutton",
                        command=lambda: cool.__setitem__("zapnuto", cv.get())).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        def on_mode():
            cool["zdroj"] = self.mode.get()
            self.edit_mode.set(self.mode.get())
            self._build_curve_table()
        ttk.Label(rc, text="Řídit podle", style="Small.TLabel").grid(row=1, column=0, sticky="w", padx=16)
        V.segmented(rc, self.mode, [("cpu", "Teploty CPU"), ("kapalina", "Kapaliny (Kraken sám)")],
                    command=on_mode).grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 10))
        ttk.Label(rc, text="Senzor CPU", style="Small.TLabel").grid(row=3, column=0, sticky="w", padx=16)
        sv = tk.StringVar(value=cool.get("senzor_cpu", "CPU (Tctl/Tdie)"))
        ttk.Combobox(rc, textvariable=sv, width=30,
                     values=sorted(k for k in self.data if not k.startswith("@"))).grid(
            row=4, column=0, sticky="ew", padx=16, pady=(4, 10))
        sv.trace_add("write", lambda *a: cool.__setitem__("senzor_cpu", sv.get()))
        ttk.Label(rc, text="Vyhlazení (s)", style="Small.TLabel").grid(row=5, column=0, sticky="w", padx=16)
        hv = tk.StringVar(value=str(cool.get("vyhlazeni_s", 5)))
        ttk.Spinbox(rc, textvariable=hv, from_=1, to=30, increment=1, width=6).grid(
            row=6, column=0, sticky="w", padx=16, pady=(4, 16))

        def on_h(*_):
            try:
                cool["vyhlazeni_s"] = max(1, int(float(hv.get())))
            except ValueError:
                pass
        hv.trace_add("write", on_h)

        tc = V.card(right)
        tc.pack(fill="x", pady=(16, 0))
        V.card_title(tc, "Body křivek").pack(anchor="w", padx=16, pady=(14, 6))
        self.curve_frame = ttk.Frame(tc)
        self.curve_frame.pack(anchor="w", padx=16, pady=(0, 14))
        self._build_curve_table()

    def _curves(self):
        cool = self.cfg["chlazeni"]
        return cool["cpu"] if self.edit_mode.get() == "cpu" else cool

    def _build_curve_table(self):
        f = self.curve_frame
        for w in f.winfo_children():
            w.destroy()
        curves = self._curves()
        unit = "CPU °C" if self.edit_mode.get() == "cpu" else "kapal. °C"
        self.cool_vars = {}
        for col, (key, title, color) in enumerate((("pumpa", "Pumpa", V.ACCENT),
                                                   ("ventilatory", "Ventilátory", V.ORANGE))):
            x = col * 2
            pad = (0 if col == 0 else 24, 0)
            tk.Label(f, text=title, bg=V.CARD, fg=color, font=V.FONT_B).grid(
                row=0, column=x, columnspan=2, sticky="w", padx=pad)
            ttk.Label(f, text=unit, style="Small.TLabel").grid(row=1, column=x, sticky="w", padx=pad)
            ttk.Label(f, text="výkon %", style="Small.TLabel").grid(row=1, column=x + 1, sticky="w", padx=4)
            pts = curves.get(key, [])
            rows = []
            for i in range(self.COOL_ROWS):
                t = tk.StringVar(value=str(pts[i][0]) if i < len(pts) else "")
                d = tk.StringVar(value=str(pts[i][1]) if i < len(pts) else "")
                ttk.Entry(f, textvariable=t, width=6, font=V.MONO).grid(row=2 + i, column=x, pady=2, sticky="w",
                                                                       padx=pad)
                ttk.Entry(f, textvariable=d, width=6, font=V.MONO).grid(row=2 + i, column=x + 1, padx=4, pady=2,
                                                                       sticky="w")
                for v in (t, d):
                    v.trace_add("write", lambda *a, k=key: self._cool_changed(k))
                rows.append((t, d))
            self.cool_vars[key] = rows
        self._draw_curves()

    def _cool_changed(self, key):
        pts = []
        for t, d in self.cool_vars[key]:
            if not t.get().strip() and not d.get().strip():
                continue
            try:
                tv, dv = int(float(t.get())), int(float(d.get()))
            except ValueError:
                return
            if not (0 <= dv <= 100 and 0 <= tv <= 110):
                return
            pts.append([tv, dv])
        if pts:
            self._curves()[key] = sorted(pts)
            self._draw_curves()

    def _draw_curves(self):
        c = self.cool_canvas
        c.delete("all")
        is_cpu = self.edit_mode.get() == "cpu"
        x_lo, x_hi = (20, 100) if is_cpu else (20, 60)
        W, H, L, B, T, R = max(300, c.winfo_width()), 300, 48, 26, 24, 30
        tx = lambda t: L + (min(max(t, x_lo), x_hi) - x_lo) / (x_hi - x_lo) * (W - L - R)
        ty = lambda d: H - B - d / 100 * (H - B - T)
        for d in (0, 25, 50, 75, 100):
            c.create_line(L, ty(d), W - R, ty(d), fill="#232830")
            c.create_text(L - 8, ty(d), text=f"{d} %", anchor="e", fill=V.DIM, font=("Consolas", 9))
        for t in range(x_lo, x_hi + 1, 10 if is_cpu else 5):
            c.create_line(tx(t), T, tx(t), H - B, fill="#232830")
            c.create_text(tx(t), H - B + 14, text=f"{t} °C", fill=V.DIM, font=("Consolas", 9))
        if not is_cpu:
            c.create_line(tx(59), T, tx(59), H - B, fill=V.ERR, dash=(3, 3))
        curves = self._curves()
        for key, color in (("ventilatory", V.ORANGE), ("pumpa", V.ACCENT)):
            pts = sorted(curves.get(key, []))
            if not pts:
                continue
            xy = [(tx(x_lo), ty(pts[0][1]))] + [(tx(t), ty(d)) for t, d in pts] + [(tx(x_hi), ty(pts[-1][1]))]
            if not is_cpu:
                xy = xy[:-1] + [(tx(59), ty(pts[-1][1])), (tx(59), ty(100)), (tx(60), ty(100))]
            c.create_line(*[v for p in xy for v in p], fill=color, width=2.5)
            for t, d in pts:
                c.create_oval(tx(t) - 4.5, ty(d) - 4.5, tx(t) + 4.5, ty(d) + 4.5, fill=V.CARD, outline=color, width=2)
        for i, (text, color) in enumerate((("pumpa", V.ACCENT), ("ventilátory", V.ORANGE))):
            x = L + i * 80
            c.create_line(x, 7, x + 14, 7, fill=color, width=3)
            c.create_text(x + 20, 7, text=text, fill=V.MUTED, anchor="w", font=V.SMALL)
        cur = (self.cstate.get("teplota") if is_cpu
               else (self.data.get(config.LIQUID) or {}).get("value"))
        if cur is not None:
            c.create_line(tx(cur), T, tx(cur), H - B, fill=V.TEXT, dash=(3, 4))
            c.create_text(tx(cur) + 5, T + 2, text=f"{cur:.0f} °C", anchor="nw", fill=V.TEXT, font=V.FONT_B)

    def _set_tile(self, key, value, unit, frac, sub):
        val, unit_lbl, bar, sub_lbl, color = self.tiles[key]
        val.config(text=value)
        unit_lbl.config(text=unit)
        sub_lbl.config(text=sub)
        bar.delete("all")
        if frac is not None:
            w = bar.winfo_width()
            bar.create_rectangle(0, 0, w * max(0.0, min(1.0, frac)), 4, fill=color, outline="")

    def _update_cool_status(self):
        g = lambda k: (self.data.get(k) or {}).get("value")
        lq, pr, pd, fr, fd = (g("@kapalina"), g("@pumpa"), g("@pumpa_vykon"),
                              g("@ventilatory"), g("@ventilatory_vykon"))
        cpu = self._cpu_temp()
        num = lambda v, d=1: f"{v:.{d}f}".replace(".", ",")
        self._set_tile("cpu", num(cpu) if cpu is not None else "–", "°C",
                       cpu / 100 if cpu is not None else None,
                       f"senzor {self.cfg['chlazeni'].get('senzor_cpu', '')}")
        self._set_tile("liquid", num(lq) if lq is not None else "–", "°C",
                       lq / 59 if lq is not None else None, "pojistka 100 % od 59 °C")
        self._set_tile("pump", num(pd, 0) if pd is not None else "–", "%", (pd or 0) / 100,
                       f"{pr:.0f} ot/min" if pr is not None else "bez dat z Krakenu")
        self._set_tile("fans", num(fd, 0) if fd is not None else "–", "%", (fd or 0) / 100,
                       f"{fr:.0f} ot/min" if fr is not None else "bez dat z Krakenu")
        if lq is None:
            self.cool_status.config(text="Aktuální stav uvidíš, až poběží aplikace (spustit.bat).",
                                    foreground=V.MUTED)
            return
        st = self.cstate
        if st.get("rezim") == "cpu" and st.get("zaloha"):
            head, color = "ZÁLOHA: chybí teplota CPU z HWiNFO – řídí Kraken podle kapaliny", V.ERR
        elif st.get("rezim") == "cpu":
            head, color = f"Řízeno podle CPU {st.get('teplota', 0):.1f} °C (průměr)", V.OK
        elif st.get("rezim") == "kapalina":
            head, color = "Řídí Kraken sám podle kapaliny", V.OK
        else:
            head, color = "Řízení aplikací vypnuto – Kraken řídí sám podle křivek kapaliny", V.ERR
        self.cool_status.config(foreground=color, text=head)

    # ---------------------------------------------------- editor obrazovky
    def _select(self, i):
        for w in self.ed.winfo_children():
            w.destroy()
        if not self.cfg["obrazovky"]:
            ttk.Label(self.ed, text="Žádná obrazovka – přidej ji tlačítkem Přidat.", style="Muted.TLabel").grid(
                padx=8, pady=8)
            return
        self.sel = i
        self.lst.selection_clear(0, "end")
        self.lst.selection_set(i)
        s = self.cfg["obrazovky"][i]
        self._color_btn = {}
        self._building = True
        row = 0
        V.card_title(self.ed, TYPES[s["typ"]]).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 10))
        row += 1
        sizes = [("velikost_obsahu", "Velikost obsahu", 0.6, 1.0, 0.01)]
        if s["typ"] not in CLOCKS:
            sizes.append(("velikost_textu", "Velikost textu", 0.7, 1.4, 0.05))
        for key, text, lo, hi, res in sizes:
            ttk.Label(self.ed, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 0))
            v = tk.DoubleVar(value=s.get(key, self.cfg.get(key, 1.0)))
            val = ttk.Label(self.ed, width=5, text=f"{v.get():.2f}", font=V.MONO, anchor="e")
            val.grid(row=row, column=1, sticky="e", padx=(0, 12), pady=(6, 0))
            row += 1

            def on(_e=None, k=key, v=v, val=val, res=res):
                x = round(round(v.get() / res) * res, 2)
                self.cfg["obrazovky"][self.sel][k] = x
                val.config(text=f"{x:.2f}")
                self._update_preview()
            V.scale(self.ed, variable=v, from_=lo, to=hi, resolution=res, length=200, command=on).grid(
                row=row, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(6, 4))
            row += 1
        ttk.Separator(self.ed).grid(row=row, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=10)
        row += 1
        for key, text, kind in FIELDS[s["typ"]]:
            ttk.Label(self.ed, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 2))
            var = tk.StringVar(value=str(s.get(key, "")))
            wide = kind in ("sensor", "text", "image")
            if kind == "sensor":
                w = ttk.Combobox(self.ed, textvariable=var, values=self._sensor_names(), width=30)
                self._with_value_hint(row, var)
            elif kind == "unit":
                w = ttk.Combobox(self.ed, textvariable=var, values=UNITS, width=10)
            elif kind == "bool":
                bv = tk.BooleanVar(value=bool(s.get(key)))
                w = ttk.Checkbutton(self.ed, variable=bv)
                bv.trace_add("write", lambda *a, k=key, v=bv: self._set_flag(k, v.get()))
            elif kind == "image":
                w = ttk.Combobox(self.ed, textvariable=var, values=screens.image_files(), width=32,
                                 state="readonly")
            elif kind == "mode":
                w = ttk.Combobox(self.ed, textvariable=var, values=screens.IMAGE_MODES, width=18,
                                 state="readonly")
            else:
                w = ttk.Entry(self.ed, textvariable=var, width=14 if kind != "text" else 24,
                              font=V.MONO if kind != "text" else V.FONT)
            if kind == "bool":
                w.grid(row=row, column=1, sticky="e", padx=(0, 12), pady=(6, 2))
            else:
                row += 1
                w.grid(row=row, column=0, columnspan=2, sticky="ew" if wide else "w", padx=(0, 12))
            var.trace_add("write", lambda *a, k=key, v=var, kd=kind: self._changed(k, v, kd))
            row += 1
        row = self._build_colors(s, row)
        ttk.Label(self.ed, style="Small.TLabel",
                  text=f"{config.LIQUID} = teplota kapaliny přímo z Krakenu.\n"
                       "Senzor z HWiNFO se v seznamu objeví, když u něj zaškrtneš\n"
                       "Report value in Gadget (Hlásit hodnotu pro Gadget).", justify="left").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self._building = False
        self._update_preview()

    def _with_value_hint(self, row, var):
        lbl = ttk.Label(self.ed, style="Small.TLabel")
        lbl.grid(row=row, column=1, sticky="e", padx=(0, 12), pady=(6, 2))

        def upd(*_):
            item = self.data.get(var.get())
            lbl.config(text=f"= {item['value']:g} {item.get('unit', '')}" if item else "(nenalezeno)")
        var.trace_add("write", upd)
        upd()

    def _build_colors(self, s, row):
        """Barvy casti obrazovky: prechod Od -> Do (stejne barvy = jednobarevne)."""
        parts = screens.COLORS.get(s["typ"], [])
        if not parts:
            return row
        ttk.Separator(self.ed).grid(row=row, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=10)
        row += 1
        ttk.Label(self.ed, text="Barvy (přechod od → do)", style="Bold.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        for part, text, d_od, d_do in parts:
            ttk.Label(self.ed, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 2))
            row += 1
            fr = ttk.Frame(self.ed)
            fr.grid(row=row, column=0, columnspan=2, sticky="w")
            for i, (end, dflt) in enumerate((("od", d_od), ("do", d_do))):
                key = f"{part}_{end}"
                b = V.swatch(fr, s.get(key, dflt), lambda k=key, dd=dflt: self._pick_color(k, dd),
                             text=end, width=6)
                b.grid(row=0, column=i, padx=(0, 6), ipady=3)
                self._color_btn[key] = b
            ttk.Button(fr, text="Jednobarevně", command=lambda p=part, do=d_od: self._same_color(p, do)).grid(
                row=0, column=2, padx=(4, 0))
            row += 1
        return row

    @staticmethod
    def _contrast(hexcol):
        return V.contrast(hexcol)

    def _pick_color(self, key, default):
        s = self.cfg["obrazovky"][self.sel]
        c = colorchooser.askcolor(color=s.get(key, default), parent=self)[1]
        if c:
            s[key] = c
            V.set_swatch(self._color_btn[key], c)
            self._update_preview()

    def _same_color(self, part, default):
        s = self.cfg["obrazovky"][self.sel]
        c = s.get(f"{part}_od", default)
        s[f"{part}_do"] = c
        V.set_swatch(self._color_btn[f"{part}_do"], c)
        self._update_preview()

    def _set_flag(self, key, value):
        if not self._building:
            self.cfg["obrazovky"][self.sel][key] = bool(value)
            self._update_preview()

    def _changed(self, key, var, kind):
        if self._building:
            return
        s = self.cfg["obrazovky"][self.sel]
        v = var.get()
        if kind in ("num", "int"):
            try:
                v = int(v) if kind == "int" else float(v.replace(",", "."))
            except ValueError:
                return
            if kind == "num" and float(v).is_integer():
                v = int(v)
        s[key] = v
        self.lst.delete(self.sel)
        self.lst.insert(self.sel, self._label(s))
        self.lst.selection_set(self.sel)
        self._update_preview()

    # ------------------------------------------------ obecne + nahled
    def _build_right(self, page):
        f = tk.Frame(page, bg=V.BG)
        f.grid(row=0, column=2, sticky="ns")
        pv = V.card(f)
        pv.pack(fill="x")
        V.card_title(pv, "Náhled").pack(anchor="w", padx=16, pady=(14, 8))
        self.preview = tk.Label(pv, bg=V.CARD, width=264, height=264, bd=0)
        self.preview.pack(padx=16)
        self.src_lbl = ttk.Label(pv, style="Small.TLabel", justify="center")
        self.src_lbl.pack(pady=(6, 14))

        g = V.card(f)
        g.pack(fill="x", pady=(16, 0))
        g.columnconfigure(0, weight=1)
        V.card_title(g, "Obecné").grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))
        self.gvars = {}

        def scale(key, text, lo, hi, res, row):
            ttk.Label(g, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=16, pady=(6, 0))
            v = tk.DoubleVar(value=self.cfg[key])
            val = ttk.Label(g, width=5, font=V.MONO, anchor="e")
            val.grid(row=row, column=1, sticky="e", padx=16, pady=(6, 0))

            def on(*_):
                x = round(v.get() / res) * res
                self.cfg[key] = int(x) if res >= 1 else round(x, 2)
                val.config(text=str(self.cfg[key]))
                self._update_preview()
            V.scale(g, variable=v, from_=lo, to=hi, resolution=res, length=240, command=lambda e: on()).grid(
                row=row + 1, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 4))
            on()

        def spin(key, text, lo, hi, inc, row):
            ttk.Label(g, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=16, pady=4)
            v = tk.StringVar(value=str(self.cfg[key]))
            ttk.Spinbox(g, textvariable=v, from_=lo, to=hi, increment=inc, width=6, font=V.MONO).grid(
                row=row, column=1, sticky="e", padx=16, pady=4)

            def on(*_):
                try:
                    self.cfg[key] = max(lo, min(hi, float(v.get().replace(",", "."))))
                except ValueError:
                    pass
            v.trace_add("write", on)

        scale("jas", "Jas displeje (%)", 0, 100, 5, 1)
        scale("gama_grafiky", "Světlost grafiky (nižší = světlejší)", 0.4, 1.0, 0.05, 3)
        spin("rotace_s", "Rotace obrazovek (s)", 1, 60, 1, 5)
        spin("obnova_s", "Obnova hodnot (s), i Alphacool", MIN_REFRESH_S, 10, 0.25, 6)
        av = tk.BooleanVar(value=self.cfg.get("auto_obrazovky", True))

        def on_auto():
            self.cfg["auto_obrazovky"] = av.get()
        ttk.Checkbutton(g, text="Přidávat nové senzory z HWiNFO", variable=av,
                        command=on_auto).grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 14))

    def _round_preview(self, img):
        """Kulaty displej: obrazek oriznuty do kruhu, kolem jemny ramecek."""
        S, R = 264, 120
        out = Image.new("RGB", (S, S), V.CARD)
        big = Image.new("L", (S * 4, S * 4), 0)
        d = ImageDraw.Draw(big)
        c = S * 2
        d.ellipse((c - (R + 5) * 4, c - (R + 5) * 4, c + (R + 5) * 4, c + (R + 5) * 4), fill=255)
        ring = big.resize((S, S), Image.LANCZOS)
        out.paste(V.LINE, (0, 0), ring)
        big = Image.new("L", (S * 4, S * 4), 0)
        ImageDraw.Draw(big).ellipse((c - (R + 4) * 4, c - (R + 4) * 4, c + (R + 4) * 4, c + (R + 4) * 4), fill=255)
        out.paste("#000000", (0, 0), big.resize((S, S), Image.LANCZOS))
        big = Image.new("L", (S * 4, S * 4), 0)
        ImageDraw.Draw(big).ellipse((c - R * 4, c - R * 4, c + R * 4, c + R * 4), fill=255)
        o = (S - img.width) // 2
        out.paste(img.convert("RGB"), (o, o), big.resize((S, S), Image.LANCZOS).crop((o, o, o + img.width,
                                                                                         o + img.height)))
        return out

    def _update_preview(self):
        if not self.cfg["obrazovky"]:
            return
        try:
            scr = self.cfg["obrazovky"][self.sel]
            scr, data, hist, sample = self._preview_data(scr)
            img = screens.render(scr, data, self.cfg["velikost_obsahu"], self.cfg["gama_grafiky"],
                                 self.cfg.get("velikost_textu", 1.0), hist)
        except Exception as e:
            self.src_lbl.config(text=f"Chyba náhledu: {e}")
            return
        base = "Data z běžící aplikace" if self.running else "Data přímo z HWiNFO (aplikace neběží)"
        self.src_lbl.config(text=base + ("\nchybějící hodnoty = ukázkové" if sample else ""))
        self._preview_img = ImageTk.PhotoImage(self._round_preview(img))
        self.preview.config(image=self._preview_img, width=264, height=264)

    def _preview_data(self, scr):
        """Data pro nahled; chybejici senzory (napr. kapalina bez bezici aplikace)
        dostanou ukazkovou hodnotu uprostred rozsahu, graf ukazkovou krivku."""
        import math
        data = dict(self.data)
        hist = dict(self.hist)
        sample = False
        scr = dict(scr)
        for n in ("", "1", "2", "3", "4"):
            if ("senzor" + n) not in scr:
                continue
            if not scr["senzor" + n]:                 # senzor jeste nevybrany -> ukazka
                scr["senzor" + n] = ("Ukázka " + n).strip()
            name = scr["senzor" + n]
            if name in data:
                continue
            lo, hi = float(scr.get("min" + n, 0)), float(scr.get("max" + n, 100))
            div = float(scr.get("delitel", 1)) or 1
            data[name] = {"value": (lo + (hi - lo) * 0.6) * div,
                          "unit": "°C" if name == config.LIQUID else ""}
            sample = True
        for n in {"graf": ("",), "graf_dva": ("1", "2")}.get(scr.get("typ"), ()):
            name = scr.get("senzor" + n)
            if name and len(hist.get(name, [])) < 2:
                lo, hi = float(scr.get("min" + n, 0)), float(scr.get("max" + n, 100))
                div = float(scr.get("delitel", 1)) or 1
                ph = 0 if n != "2" else 2.0
                hist[name] = [(lo + (hi - lo) * (0.45 + 0.25 * math.sin(i / 7 + ph))) * div
                              for i in range(90)]
                sample = True
        if scr.get("typ") == "chlazeni":                  # bez bezici aplikace nejsou data Krakenu
            for k, v in (("@kapalina", 31.4), ("@pumpa", 1720), ("@pumpa_vykon", 45),
                         ("@ventilatory", 650), ("@ventilatory_vykon", 30)):
                if k not in data:
                    data[k] = {"value": v, "unit": ""}
                    sample = True
        return scr, data, hist, sample

    def _tick(self):
        self.data, self.running, self.cstate, self.hist, self.astate, self.lstate = load_data()
        self._update_preview()
        self._update_cool_status()
        self._draw_curves()
        self._update_alpha()
        self.leds.refresh()
        self._update_sidebar()
        self._update_dirty()
        self.after(1000, self._tick)

    # ---------------------------------------------------------- ulozeni
    def save(self):
        config.save(self.cfg)
        self.saved = copy.deepcopy(self.cfg)
        self._status_msg = True
        self.status.config(text="✓  Uloženo – běžící aplikace změnu načte do 1 s.", fg=V.OK)

        def done():
            self._status_msg = None
            self._update_dirty()
        self.after(4000, done)

    def revert(self):
        self.cfg = copy.deepcopy(self.saved)
        self.destroy()
        App().mainloop()

    def on_close(self):
        if self.cfg != self.saved and messagebox.askyesno(
                "Neuložené změny", "Máš neuložené změny. Uložit před zavřením?", parent=self):
            self.save()
        self.destroy()


if __name__ == "__main__":
    try:    # vlastni skupina na hlavnim panelu -> ikona okna misto ikony Pythonu
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RGB-LCD.Nastaveni")
    except (AttributeError, OSError):
        pass
    App().mainloop()
