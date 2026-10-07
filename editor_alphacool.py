# editor_alphacool.py - editor rozvrzeni Alphacool LCD pro okno nastaveni
#
# Nahled displeje zvetseny 3x: klik = vyber prvku, tazeni = posun, tazeni ctverecku
# v pravem dolnim rohu = zmena velikosti, sipky = posun o 1 bod (Shift = 5),
# Ctrl+sipky = zmena velikosti, Delete = smazat. Pod nahledem seznam prvku (poradi = poradi
# kresleni, dole v seznamu = navrchu) a vlastnosti vybraneho prvku.

import copy
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

import mono
import prvky
import vzhled as V

SCALE = 3
HANDLE = 4                     # polovina ctverecku pro zmenu velikosti (v bodech platna)
SEL_COLOR = "#ffb000"

COLORS = {"svítí": 1, "zhasnuto": 0}
ALIGN = ["vlevo", "stred", "vpravo"]
UNITS = ["auto", "°C", "°", "%", "GHz", "MHz", "G", "MB", "RPM", "W", "V", "MB/s", ""]

# vlastnosti podle typu: (klic, popisek, druh, moznosti)
_S = [("senzor", "Senzor", "sensor", None), ("min", "Minimum", "num", None),
      ("max", "Maximum", "num", None), ("delitel", "Dělitel", "num", None)]
_V = [("jednotka", "Jednotka", "unit", None), ("desetinna_mista", "Desetinná místa", "int", None)]
_FONT = [("pismo", "Písmo", "font", None)]
_COL = [("barva", "Barva", "color", None)]
FIELDS = {
    "text": [("popisek", "Popisek", "text", None), ("senzor", "Senzor (prázdný = jen popisek)", "sensor", None),
             ("delitel", "Dělitel", "num", None)] + _V
            + [("zarovnani", "Zarovnání", "choice", ALIGN)] + _FONT + _COL,
    "cislo": [("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel", "num", None)] + _V
             + [("popisek", "Popisek", "text", None)] + _FONT
             + [("pismo_male", "Písmo jednotky", "font", None)] + _COL,
    "hodiny": [("format", "Formát", "choice", ["HH:MM:SS", "HH:MM", "datum", "den datum", "den",
                                               "HH:MM datum"]),
               ("zarovnani", "Zarovnání", "choice", ALIGN)] + _FONT + _COL,
    "bar": [("styl", "Styl", "choice", ["plny", "segmenty", "rysky", "rastr"])] + _S
           + [("senzor2", "2. senzor (rozdělený bar)", "sensor", None)],
    "sloupce": [("senzory", "Senzory", "sensors", None), ("min", "Minimum", "num", None),
                ("max", "Maximum", "num", None), ("delitel", "Dělitel", "num", None),
                ("ramecek", "Rámeček", "bool", None)],
    "graf": [("styl", "Styl", "choice", ["plocha", "sloupce", "mrizka"])] + _S
            + [("delka_s", "Délka (s)", "int", None), ("ramecek", "Rámeček", "bool", None)],
    "budik": _S + _V + [("popisek", "Popisek", "text", None), ("hodnota", "Zobrazit hodnotu", "bool", None)]
             + _FONT,
    "prstenec": _S + [("segmenty", "Počet segmentů", "int", None), ("uhel", "Úhel (°)", "int", None),
                      ("tloustka", "Tloušťka", "int", None)] + _V
                + [("popisek", "Popisek", "text", None), ("hodnota", "Zobrazit hodnotu", "bool", None)]
                + _FONT + [("pismo_male", "Písmo popisku", "font", None)],
    "oblouk": _S + [("uhel", "Úhel (°)", "int", None), ("tloustka", "Tloušťka", "int", None)] + _V
              + [("popisek", "Popisek", "text", None), ("hodnota", "Zobrazit hodnotu", "bool", None)]
              + _FONT + [("pismo_male", "Písmo popisku", "font", None)],
    "ikona": [("nazev", "Ikona", "choice", list(prvky.ICONS)), ("meritko", "Měřítko (1–3)", "int", None)] + _COL,
    "obrazek": [("soubor", "Soubor", "file", None),
                ("velikost", "Velikost", "choice", ["puvodni", "prizpusobit"]),
                ("prah", "Práh jasu (0–255)", "int", None), ("rastr", "Rastrovat (fotky)", "bool", None),
                ("negativ", "Negativ", "bool", None), ("pozadi", "Neprůhledné pozadí", "bool", None)] + _COL,
    "cara": [("smer", "Směr", "choice", ["vodorovna", "svisla"]), ("tloustka", "Tloušťka", "int", None)] + _COL,
    "obdelnik": [("vypln", "Výplň", "choice", ["zadna", "plna", "rastr"]),
                 ("dvojity", "Dvojitý rámeček", "bool", None)] + _COL,
}

# sci-fi prvky (prvky_scifi.py); "template" = text se {senzor|dělitel|místa}, "lines" = víc řádků
_R = [("senzor", "Senzor", "sensor", None), ("min", "Minimum", "num", None), ("max", "Maximum", "num", None),
      ("delitel", "Dělitel", "num", None)]
_TXT = [("jednotka", "Jednotka (text)", "text", None), ("popisek", "Popisek", "text", None)]
FIELDS.update({
    "seg": [("cas", "Zobrazit čas místo hodnoty", "bool", None),
            ("format_casu", "Formát času", "choice", ["%H:%M", "%H:%M:%S"]),
            ("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel", "num", None),
            ("desetinna_mista", "Desetinná místa", "int", None)] + _TXT
           + [("zarovnani", "Zarovnání", "choice", ALIGN), ("barva", "Barva", "color", None)],
    "radek": [("sablona", "Text se {senzor|dělitel|místa}", "template", None),
              ("zarovnani", "Zarovnání", "choice", ALIGN)] + _FONT + _COL,
    "term": [("radky", "Řádky: POPISEK = {senzor}jednotka", "lines", None),
             ("radek_px", "Výška řádku (px)", "int", None), ("kurzor", "Blikající kurzor", "bool", None)] + _FONT,
    "pasek": [("popisek", "Popisek", "text", None), ("sablona", "Hodnoty vpravo", "template", None)]
             + _R + _FONT,
    "duhovka": list(_R),
    "esper": [("sablona", "Štítek vlevo nahoře", "template", None), ("roh", "Text v rohu", "text", None)]
             + _R + [("delka_s", "Délka (s)", "int", None)],
    "teren": _R + [("delka_s", "Délka (s)", "int", None)],
    "blok": _R + [("desetinna_mista", "Desetinná místa", "int", None)] + _TXT,
    "radar": _R + [("delka_s", "Délka historie (s)", "int", None)],
    "lcars_ram": [("popisek", "Popisek v horní liště", "text", None), ("kody", "Kódy v levém pásu", "text", None),
                  ("pas", "Šířka levého pásu", "int", None), ("pas_nahore", "Výška horní lišty", "int", None)],
    "lcars_hodnota": [("popisek", "Popisek štítku", "text", None), ("sirka_stitku", "Šířka štítku", "int", None),
                      ("senzor", "Senzor", "sensor", None), ("delitel", "Dělitel", "num", None),
                      ("desetinna_mista", "Desetinná místa", "int", None), ("jednotka", "Jednotka (text)", "text", None),
                      ("min", "Minimum (bloky)", "num", None), ("max", "Maximum (bloky)", "num", None),
                      ("bloky", "Počet bloků (od výšky 24 px)", "int", None)],
    "warp": list(_R),
    # Star Wars (prvky_starwars.py)
    "zamerovac": _R,
    "mec": [("popisek", "Popisek", "text", None), ("sablona", "Hodnoty vpravo", "template", None)] + _R + _FONT,
    "hvezda_smrti": _R + [("prstenec", "Prstenec nabití", "bool", None)],
    "hyperprostor": _R + [("hvezdy", "Počet hvězd", "int", None), ("ramecek", "Rámeček", "bool", None)],
    "yavin": list(_R),
    "stitek": [("popisek", "Štítek", "text", None), ("sirka_stitku", "Šířka štítku (0 = podle textu)", "int", None),
               ("sablona", "Text se {senzor|dělitel|místa}", "template", None),
               ("zarovnani", "Zarovnání textu", "choice", ALIGN)] + _FONT,
    "rohy": [("delka", "Délka rohů (px)", "int", None)],
})


class AlphaEditor:
    def __init__(self, parent, app):
        self.app = app
        self.sel = None                      # index vybraneho prvku
        self._drag = None                    # (rezim, start_x, start_y, puvodni prvek)
        self._img = None
        self._form_vars = {}
        self._syncing = False

        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        top = V.card(parent)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)

        self._build_canvas(top)
        self._build_display(top)
        self._build_list(parent)
        self.props = V.card(parent)
        self.props.grid(row=1, column=1, sticky="nsew", padx=(16, 0), pady=(16, 0))
        self.props.columnconfigure(1, weight=1)
        self.refresh()
        self._refresh_list()
        self._build_props()

    # ------------------------------------------------------------ zaklad
    @property
    def acfg(self):
        return self.app.cfg["alphacool"]

    @property
    def items(self):
        return self.acfg.setdefault(prvky.layout_key(self.acfg), [])

    @property
    def scale(self):
        return 2 if prvky.portrait(self.acfg) else SCALE       # na vysku mensi, at se okno vejde

    @property
    def _cw(self):
        return prvky.canvas_size(self.acfg)[0]

    @property
    def _ch(self):
        return prvky.canvas_size(self.acfg)[1]

    def _build_display(self, f):
        disp = ttk.Frame(f)
        disp.grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=16)
        V.card_title(disp, "Displej").pack(anchor="w", pady=(0, 8))
        for key, text in (("zapnuto", "Zobrazovat na displeji"), ("podsviceni", "Podsvícení"),
                          ("inverze", "Inverze (negativ)")):
            v = tk.BooleanVar(value=self.acfg.get(key, key != "inverze"))

            def on(k=key, v=v):
                self.acfg[k] = v.get()
                self.refresh()
            ttk.Checkbutton(disp, text=text, variable=v, command=on).pack(anchor="w")
        ttk.Label(disp, text="Otočení displeje", style="Small.TLabel").pack(anchor="w", pady=(12, 4))
        names = list(prvky.ROTATIONS.values())
        rv = tk.StringVar(value=prvky.ROTATIONS[prvky.rotation(self.acfg)])
        ttk.Combobox(disp, textvariable=rv, values=names, state="readonly", width=24).pack(anchor="w", fill="x")
        rv.trace_add("write", lambda *a: self._set_rotation(
            next(k for k, v in prvky.ROTATIONS.items() if v == rv.get())))
        self.status = ttk.Label(disp, font=V.FONT_B, wraplength=200, justify="left")
        self.status.pack(anchor="w", pady=(14, 0))
        ttk.Label(disp, style="Small.TLabel", justify="left", wraplength=200, text=(
            "Klik = výběr prvku, tažení = posun, tažení oranžového čtverečku = velikost. "
            "Šipky = posun o 1 bod (Shift = 5), Ctrl+šipky = velikost, Delete = smazat. "
            "Prvky se kreslí v pořadí seznamu – níž v seznamu = navrchu.")).pack(anchor="w", pady=(12, 0))

    def _set_rotation(self, rot):
        """Na sirku a na vysku maji kazde sve rozvrzeni; na vysku se poprve vytvori vychozi."""
        self.acfg["otoceni"] = rot
        if prvky.portrait(self.acfg) and not self.acfg.get("prvky_na_vysku"):
            self.acfg["prvky_na_vysku"] = prvky.default_portrait_layout()
        self.sel = None
        self._resize_canvas()
        self._refresh_list()
        self._build_props()
        self.refresh()

    def _resize_canvas(self):
        self.canvas.config(width=self._cw * self.scale, height=self._ch * self.scale)
        self.canvas_box.config(text=f"Rozvržení {self._cw} × {self._ch} (zvětšeno {self.scale}×)")

    def _build_canvas(self, f):
        box = ttk.Frame(f)
        box.grid(row=0, column=0, sticky="nw", padx=20, pady=16)
        self.canvas_box = ttk.Label(box, text=f"Rozvržení {self._cw} × {self._ch} (zvětšeno {self.scale}×)",
                                    style="H2.TLabel")
        self.canvas_box.pack(anchor="w", pady=(0, 10))
        W, H = self._cw * self.scale, self._ch * self.scale
        # ramecek jako okolni Frame: okraj platna (highlightthickness) by prekryl krajni body nahledu
        bezel = tk.Frame(box, bg="#0c0e11", padx=6, pady=6)
        bezel.pack()
        self.canvas = tk.Canvas(bezel, width=W, height=H, bg="black", highlightthickness=0, bd=0,
                                cursor="crosshair")
        self.canvas.pack()
        self._bg = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        for key in ("Left", "Right", "Up", "Down"):
            self.canvas.bind(f"<{key}>", lambda e, k=key: self._on_key(k, e))
        self.canvas.bind("<Delete>", lambda e: self.remove())

    def _build_list(self, parent):
        lf = V.card(parent)
        lf.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        lf.columnconfigure(0, weight=1)
        head = ttk.Frame(lf)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(16, 12), pady=(14, 8))
        head.columnconfigure(0, weight=1)
        V.card_title(head, "Prvky (pořadí kreslení)").grid(row=0, column=0, sticky="w")
        add = ttk.Menubutton(head, text="+ Přidat")
        m = tk.Menu(add, tearoff=0)
        for t, name in prvky.TYPES.items():
            m.add_command(label=name, command=lambda t=t: self.add(t))
        add["menu"] = m
        add.grid(row=0, column=1, padx=(8, 0))
        screens = ttk.Frame(head)                 # obrazovky na druhem radku (na vysku je sloupec uzky)
        screens.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        mine = ttk.Menubutton(screens, text="Moje obrazovky")
        self.my_menu = tk.Menu(mine, tearoff=0, postcommand=self._fill_my_menu)
        mine["menu"] = self.my_menu
        mine.grid(row=0, column=0)
        tpl = ttk.Menubutton(screens, text="Hotové obrazovky")
        tm = tk.Menu(tpl, tearoff=0)
        for name in prvky._scifi.templates():
            tm.add_command(label=name, command=lambda n=name: self.load_template(n))
        tm.add_separator()
        tm.add_command(label="Vrátit předchozí rozvržení", command=self.restore_layout)
        tpl["menu"] = tm
        tpl.grid(row=0, column=1, padx=(8, 0))
        self.lst = V.listbox(lf, height=12, width=32)
        self.lst.grid(row=1, column=0, sticky="nsew", padx=(8, 0))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lst.yview)
        sb.grid(row=1, column=1, sticky="ns", padx=(0, 4))
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._select(self._list_index()))
        btns = ttk.Frame(lf)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        for c, (text, cmd, style) in enumerate((("▲", lambda: self.move(-1), "TButton"),
                                                ("▼", lambda: self.move(1), "TButton"),
                                                ("Duplikovat", self.duplicate, "TButton"),
                                                ("Skrýt / ukázat", self.toggle, "TButton"),
                                                ("Odebrat", self.remove, "Danger.TButton"))):
            ttk.Button(btns, text=text, command=cmd, style=style, width=3 if len(text) == 1 else None).grid(
                row=0, column=c, padx=2, sticky="ew")
            btns.columnconfigure(c, weight=1 if len(text) > 1 else 0)

    # ------------------------------------------------- hotove obrazovky
    def load_template(self, name):
        """Nahradi rozvrzeni na sirku hotovou obrazovkou; puvodni se uschova do "prvky_zaloha"."""
        if prvky.portrait(self.acfg):
            messagebox.showinfo("Hotové obrazovky", "Hotové obrazovky jsou na šířku (240 × 128).\n"
                                "Přepni otočení displeje na 0° nebo 180°.", parent=self.canvas)
            return
        if not messagebox.askyesno("Hotové obrazovky", f"Nahradit současné rozvržení obrazovkou\n„{name}“?\n\n"
                                   "Současné se uschová – vrátíš ho položkou „Vrátit předchozí rozvržení“.\n"
                                   "Na displeji se projeví po Uložit.", parent=self.canvas):
            return
        self._stash_current()
        self.acfg["prvky"] = copy.deepcopy(prvky._scifi.templates()[name])
        self.sel = None
        self._changed(rebuild=True)

    def _stash_current(self):
        """Uschovat soucasne rozvrzeni na sirku do "prvky_zaloha" - jen kdyz neni hotova ani ulozena
        obrazovka (prochazeni obrazovek nesmi prepsat rozpracovane rozvrzeni)."""
        current = self.acfg.get("prvky", [])
        known = list(prvky._scifi.templates().values()) + [s["prvky"] for s in self._mine().values()]
        if current and current not in known:
            self.acfg["prvky_zaloha"] = copy.deepcopy(current)

    # --------------------------------------------------- moje obrazovky
    def _mine(self):
        """Ulozene vlastni obrazovky: nazev -> {"na_vysku": bool, "prvky": [...]}."""
        return self.acfg.setdefault("moje_obrazovky", {})

    def _fill_my_menu(self):
        m = self.my_menu
        m.delete(0, "end")
        m.add_command(label="Uložit současnou jako…", command=self.save_mine)
        mine = self._mine()
        if mine:
            m.add_separator()
            for name, s in sorted(mine.items(), key=lambda kv: kv[0].lower()):
                m.add_command(label=name + ("  (na výšku)" if s.get("na_vysku") else ""),
                              command=lambda n=name: self.load_mine(n))
            m.add_separator()
            dm = tk.Menu(m, tearoff=0)
            for name in sorted(mine, key=str.lower):
                dm.add_command(label=name, command=lambda n=name: self.delete_mine(n))
            m.add_cascade(label="Smazat uloženou", menu=dm)

    def save_mine(self):
        from tkinter import simpledialog
        mine = self._mine()
        name = simpledialog.askstring("Moje obrazovky", "Název obrazovky:", parent=self.canvas)
        name = (name or "").strip()
        if not name:
            return
        if name in mine and not messagebox.askyesno("Moje obrazovky", f"Obrazovka „{name}“ už je uložená.\n"
                                                    "Přepsat ji současným rozvržením?", parent=self.canvas):
            return
        mine[name] = {"na_vysku": prvky.portrait(self.acfg), "prvky": copy.deepcopy(self.items)}
        self._changed()
        messagebox.showinfo("Moje obrazovky", f"Obrazovka „{name}“ je připravená.\n"
                            "Natrvalo se uloží tlačítkem Uložit nahoře.", parent=self.canvas)

    def load_mine(self, name):
        s = self._mine().get(name)
        if s is None:
            return
        if bool(s.get("na_vysku")) != prvky.portrait(self.acfg):
            messagebox.showinfo("Moje obrazovky", f"Obrazovka „{name}“ je " +
                                ("na výšku – přepni otočení displeje na 90° nebo 270°."
                                 if s.get("na_vysku") else "na šířku – přepni otočení displeje na 0° nebo 180°."),
                                parent=self.canvas)
            return
        if not messagebox.askyesno("Moje obrazovky", f"Nahradit současné rozvržení obrazovkou „{name}“?\n\n"
                                   "Na displeji se projeví po Uložit.", parent=self.canvas):
            return
        if not s.get("na_vysku"):
            self._stash_current()
        self.acfg[prvky.layout_key(self.acfg)] = copy.deepcopy(s["prvky"])
        self.sel = None
        self._changed(rebuild=True)

    def delete_mine(self, name):
        if not messagebox.askyesno("Moje obrazovky", f"Smazat uloženou obrazovku „{name}“?\n"
                                   "Současné rozvržení na displeji zůstane.", parent=self.canvas):
            return
        self._mine().pop(name, None)
        self._changed()

    def restore_layout(self):
        """Prohodi soucasne a uschovane rozvrzeni (jde tedy i zpet)."""
        if prvky.portrait(self.acfg) or not self.acfg.get("prvky_zaloha"):
            messagebox.showinfo("Hotové obrazovky", "Žádné uschované rozvržení na šířku není.", parent=self.canvas)
            return
        self.acfg["prvky"], self.acfg["prvky_zaloha"] = self.acfg["prvky_zaloha"], self.acfg.get("prvky", [])
        self.sel = None
        self._changed(rebuild=True)

    # ---------------------------------------------------------- seznam
    def _list_index(self):
        s = self.lst.curselection()
        return s[0] if s else None

    def _refresh_list(self):
        self.lst.delete(0, "end")
        for p in self.items:
            mark = "  " if not p.get("skryty") else "✗ "
            self.lst.insert("end", mark + prvky.label(p))
        if self.sel is not None and self.sel < len(self.items):
            self.lst.selection_set(self.sel)
            self.lst.see(self.sel)

    def _select(self, i):
        self.sel = i if (i is not None and 0 <= i < len(self.items)) else None
        self._refresh_list()
        self._build_props()
        self._draw_selection()

    def add(self, typ):
        p = prvky.new(typ)
        if self.sel is not None:                        # kousek vedle vybraneho
            q = self.items[self.sel]
            p["x"], p["y"] = min(q["x"] + 6, self._cw - 8), min(q["y"] + 6, self._ch - 8)
        self.items.append(p)
        self.sel = len(self.items) - 1
        self._changed(rebuild=True)

    def duplicate(self):
        if self.sel is None:
            return
        p = copy.deepcopy(self.items[self.sel])
        p["x"], p["y"] = min(p["x"] + 4, self._cw - 4), min(p["y"] + 4, self._ch - 4)
        self.items.insert(self.sel + 1, p)
        self.sel += 1
        self._changed(rebuild=True)

    def remove(self):
        if self.sel is None:
            return
        del self.items[self.sel]
        self.sel = min(self.sel, len(self.items) - 1) if self.items else None
        self._changed(rebuild=True)

    def move(self, step):
        if self.sel is None:
            return
        j = self.sel + step
        if 0 <= j < len(self.items):
            self.items[self.sel], self.items[j] = self.items[j], self.items[self.sel]
            self.sel = j
            self._changed()

    def toggle(self):
        if self.sel is not None:
            p = self.items[self.sel]
            p["skryty"] = not p.get("skryty")
            self._changed()

    # ------------------------------------------------------------ platno
    def _hit(self, x, y):
        for i in range(len(self.items) - 1, -1, -1):
            p = self.items[i]
            if p.get("skryty"):
                continue
            tol = 2 if min(p["w"], p["h"]) < 4 else 0
            if p["x"] - tol <= x < p["x"] + p["w"] + tol and p["y"] - tol <= y < p["y"] + p["h"] + tol:
                return i
        return None

    def _on_press(self, e):
        self.canvas.focus_set()
        x, y = e.x / self.scale, e.y / self.scale
        if self.sel is not None:                        # ctverecek pro zmenu velikosti
            p = self.items[self.sel]
            hx, hy = (p["x"] + p["w"]) * self.scale, (p["y"] + p["h"]) * self.scale
            if abs(e.x - hx) <= HANDLE + 2 and abs(e.y - hy) <= HANDLE + 2:
                self._drag = ("size", e.x, e.y, dict(p))
                return
        i = self._hit(x, y)
        if i != self.sel:
            self._select(i)
        if i is not None:
            self._drag = ("move", e.x, e.y, dict(self.items[i]))

    def _on_drag(self, e):
        if not self._drag or self.sel is None:
            return
        mode, sx, sy, orig = self._drag
        dx, dy = round((e.x - sx) / self.scale), round((e.y - sy) / self.scale)
        p = self.items[self.sel]
        if mode == "move":
            p["x"] = max(-p["w"] + 2, min(self._cw - 2, orig["x"] + dx))
            p["y"] = max(-p["h"] + 2, min(self._ch - 2, orig["y"] + dy))
        else:
            p["w"] = max(1, min(self._cw * 2, orig["w"] + dx))
            p["h"] = max(1, min(self._ch * 2, orig["h"] + dy))
        self._changed(geometry_only=True)

    def _on_key(self, key, e):
        if self.sel is None:
            return
        step = 5 if e.state & 0x0001 else 1              # Shift
        dx, dy = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, -step), "Down": (0, step)}[key]
        p = self.items[self.sel]
        if e.state & 0x0004:                             # Ctrl = velikost
            p["w"], p["h"] = max(1, p["w"] + dx), max(1, p["h"] + dy)
        else:
            p["x"], p["y"] = p["x"] + dx, p["y"] + dy
        self._changed(geometry_only=True)
        return "break"

    def _draw_selection(self):
        self.canvas.delete("sel")
        if self.sel is None or self.sel >= len(self.items):
            return
        p = self.items[self.sel]
        x0, y0 = p["x"] * self.scale, p["y"] * self.scale
        x1, y1 = (p["x"] + p["w"]) * self.scale, (p["y"] + p["h"]) * self.scale
        self.canvas.create_rectangle(x0 - 1, y0 - 1, x1, y1, outline=SEL_COLOR, dash=(4, 2), tags="sel")
        self.canvas.create_rectangle(x1 - HANDLE, y1 - HANDLE, x1 + HANDLE, y1 + HANDLE,
                                     fill=SEL_COLOR, outline="black", tags="sel")

    def refresh(self):
        """Prekreslit nahled (volano i kazdou sekundu s novymi daty)."""
        try:
            img = mono.render(self.acfg, self.app.data, self.app.hist)
        except Exception as e:
            self.status.config(text=f"Chyba náhledu: {e}", foreground=V.ERR)
            return
        self._img = ImageTk.PhotoImage(mono.preview(img, self.scale))
        self.canvas.itemconfig(self._bg, image=self._img)
        self._draw_selection()
        self._update_status()

    def _update_status(self):
        st = (self.app.astate or {}).get("stav")
        texts = {"pripojen": ("● Displej připojen – zobrazuje se.", V.OK),
                 "nenalezen": ("Displej nenalezen (připojený? ovladač WinUSB přes Zadig?)", V.ERR),
                 "chyba": ("Displej nejde otevřít – podrobnosti v rgb_lcd.log", V.ERR),
                 "vypnuto": ("Zobrazování vypnuto.", V.MUTED)}
        text, color = texts.get(st, ("Stav displeje uvidíš, až poběží aplikace.", V.MUTED))
        if not self.app.running:
            text, color = "Aplikace neběží – náhled z dat HWiNFO.", V.MUTED
        self.status.config(text=text, foreground=color)

    def _changed(self, rebuild=False, geometry_only=False):
        if geometry_only:
            self._sync_geometry()
            if self.sel is not None:
                self.lst.delete(self.sel)
                p = self.items[self.sel]
                self.lst.insert(self.sel, ("  " if not p.get("skryty") else "✗ ") + prvky.label(p))
                self.lst.selection_set(self.sel)
        else:
            self._refresh_list()
            if rebuild:
                self._build_props()
        self.refresh()

    # -------------------------------------------------------- vlastnosti
    def _sync_geometry(self):
        if self.sel is None:
            return
        p = self.items[self.sel]
        self._syncing = True
        for k in ("x", "y", "w", "h"):
            v = self._form_vars.get(k)
            if v is not None and v.get() != str(p[k]):
                v.set(str(p[k]))
        self._syncing = False

    def _build_props(self):
        for w in self.props.winfo_children():
            w.destroy()
        self._form_vars = {}
        if self.sel is None or self.sel >= len(self.items):
            V.card_title(self.props, "Vlastnosti prvku").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))
            ttk.Label(self.props, style="Muted.TLabel",
                      text="Vyber prvek v náhledu nebo v seznamu,\nnebo přidej nový tlačítkem Přidat.").grid(
                row=1, column=0, padx=16, pady=(0, 14), sticky="w")
            return
        p = self.items[self.sel]
        V.card_title(self.props, prvky.TYPES.get(p["typ"], p["typ"])).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))
        geo = ttk.Frame(self.props)
        geo.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 8))
        for c, (k, t) in enumerate((("x", "X"), ("y", "Y"), ("w", "Šířka"), ("h", "Výška"))):
            ttk.Label(geo, text=t, style="Muted.TLabel").grid(row=0, column=c * 2, padx=(0 if c == 0 else 12, 4))
            v = tk.StringVar(value=str(p[k]))
            ttk.Spinbox(geo, textvariable=v, from_=-240, to=480, width=5, font=V.MONO).grid(row=0, column=c * 2 + 1)
            v.trace_add("write", lambda *a, k=k, v=v: self._set(k, v.get(), "int"))
            self._form_vars[k] = v
        row = 2
        for key, text, kind, opts in FIELDS.get(p["typ"], []):
            wide = kind in ("template", "lines")               # sablony pod popiskem pres celou sirku
            ttk.Label(self.props, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="nw",
                                                                       columnspan=2 if wide else 1,
                                                                       padx=(16, 8), pady=3)
            if wide:
                row += 1
                self._field(row, p, key, kind, opts).grid(row=row, column=0, columnspan=2, sticky="ew",
                                                          padx=16, pady=(0, 6))
            else:
                self._field(row, p, key, kind, opts).grid(row=row, column=1, sticky="w", padx=(0, 16), pady=3)
            row += 1
        ttk.Frame(self.props, height=10).grid(row=row, column=0)

    def _set(self, key, raw, kind):
        if self._syncing or self.sel is None:
            return
        p = self.items[self.sel]
        v = raw
        if kind in ("int", "num"):
            try:
                v = int(float(str(raw).replace(",", "."))) if kind == "int" else float(str(raw).replace(",", "."))
            except ValueError:
                return
            if kind == "num" and float(v).is_integer():
                v = int(v)
        p[key] = v
        if p["typ"] == "ikona" and key == "meritko":
            p["w"] = p["h"] = 11 * max(1, int(v or 1))
            self._sync_geometry()
        self._changed(geometry_only=True)

    def _field(self, row, p, key, kind, opts):
        f = self.props
        names = [""] + self.app._sensor_names()
        if kind == "font":
            return self._font_field(p, key)
        if kind == "file":
            return self._file_field(p, key)
        if kind == "sensors":
            fr = ttk.Frame(f)
            lb = V.listbox(fr, selectmode="multiple", height=6, width=30, bg=V.FIELD)
            sb = ttk.Scrollbar(fr, orient="vertical", command=lb.yview)
            lb.config(yscrollcommand=sb.set)
            lb.pack(side="left")
            sb.pack(side="left", fill="y")
            cur = p.get(key, [])
            for i, n in enumerate(names[1:]):
                lb.insert("end", n)
                if n in cur:
                    lb.selection_set(i)

            def on(_e=None):
                p[key] = [lb.get(i) for i in lb.curselection()]
                self._changed(geometry_only=True)
            lb.bind("<<ListboxSelect>>", on)
            return fr
        if kind in ("template", "lines"):
            return self._template_field(p, key, kind, names[1:])
        if kind == "bool":
            v = tk.BooleanVar(value=bool(p.get(key)))
            self._form_vars[key] = v
            return ttk.Checkbutton(f, variable=v, command=lambda: (p.__setitem__(key, v.get()),
                                                                   self._changed(geometry_only=True)))
        if kind == "color":
            v = tk.StringVar(value="svítí" if int(p.get(key, 1)) else "zhasnuto")
            w = ttk.Combobox(f, textvariable=v, values=list(COLORS), width=10, state="readonly")
            v.trace_add("write", lambda *a: self._set(key, COLORS[v.get()], "int"))
            return w
        v = tk.StringVar(value=str(p.get(key, "")))
        self._form_vars[key] = v
        if kind == "sensor":
            w = ttk.Combobox(f, textvariable=v, values=names, width=28)
        elif kind == "unit":
            w = ttk.Combobox(f, textvariable=v, values=UNITS, width=8)
        elif kind == "choice":
            w = ttk.Combobox(f, textvariable=v, values=opts, width=14, state="readonly")
        else:
            w = ttk.Entry(f, textvariable=v, width=8 if kind in ("int", "num") else 20)
        v.trace_add("write", lambda *a: self._set(key, v.get(), kind))
        return w

    def _template_field(self, p, key, kind, sensors):
        """Text se zastupnymi symboly {senzor|delitel|mista}; pod nim nabidka "vlozit senzor".
        kind "lines" = vice radku (terminal: POPISEK = sablona)."""
        fr = ttk.Frame(self.props)
        if kind == "lines":
            w = tk.Text(fr, width=40, height=7, wrap="none", bg=V.FIELD, fg=V.TEXT, insertbackground=V.TEXT,
                        relief="flat", highlightthickness=1, highlightbackground=V.LINE, highlightcolor=V.ACCENT,
                        font=("Consolas", 9))
            w.insert("1.0", str(p.get(key, "")))

            def on(_e=None):
                p[key] = w.get("1.0", "end-1c")
                self._changed(geometry_only=True)
            w.bind("<KeyRelease>", on)
            insert = lambda s: (w.insert("insert", s), on())
        else:
            v = tk.StringVar(value=str(p.get(key, "")))
            self._form_vars[key] = v
            w = ttk.Entry(fr, textvariable=v, width=40)
            v.trace_add("write", lambda *a: self._set(key, v.get(), "text"))
            insert = lambda s: w.insert("insert", s)
        w.pack(anchor="w", fill="x")
        row = ttk.Frame(fr)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Label(row, text="Vložit senzor:", style="Small.TLabel").pack(side="left")
        sv = tk.StringVar()
        cb = ttk.Combobox(row, textvariable=sv, values=sensors, width=26, state="readonly")
        cb.pack(side="left", padx=4)

        def ins(_e=None):
            if sv.get():
                insert("{" + sv.get() + "}")
                sv.set("")
        cb.bind("<<ComboboxSelected>>", ins)
        ttk.Label(fr, style="Small.TLabel", text="{senzor|dělitel|desetinná místa}, např. {Takt jader|1000|1}GHz").pack(
            anchor="w", pady=(2, 0))
        return fr

    def _file_field(self, p, key):
        """Obrazek: nabidka ze slozky obrazky/, Vybrat... (zkopiruje do obrazky/), puvodni velikost."""
        fr = ttk.Frame(self.props)
        v = tk.StringVar(value=p.get(key, ""))

        def files():
            os.makedirs(prvky.IMAGES_DIR, exist_ok=True)
            return sorted(f for f in os.listdir(prvky.IMAGES_DIR)
                          if f.lower().endswith((".png", ".bmp", ".jpg", ".jpeg", ".gif")))
        cb = ttk.Combobox(fr, textvariable=v, values=files(), width=20)
        cb.pack(side="left")
        cb.bind("<Button-1>", lambda e: cb.config(values=files()))

        def native():
            size = prvky.image_size(p.get(key, ""))
            if size:
                p["w"], p["h"] = size
                p["velikost"] = "puvodni"
                self._changed(rebuild=True)

        def pick():
            path = filedialog.askopenfilename(
                parent=self.props, title="Vyber obrázek",
                filetypes=[("Obrázky", "*.png *.bmp *.jpg *.jpeg *.gif"), ("Vše", "*.*")])
            if not path:
                return
            name = os.path.basename(path)
            dst = os.path.join(prvky.IMAGES_DIR, name)
            if os.path.normcase(os.path.abspath(path)) != os.path.normcase(dst):
                shutil.copy2(path, dst)                   # obrazek patri k aplikaci
            p[key] = name
            native()

        def on(*_):
            p[key] = v.get()
            if prvky.image_size(v.get()) and p.get("velikost", "puvodni") == "puvodni":
                p["w"], p["h"] = prvky.image_size(v.get())
                self._sync_geometry()
            self._changed(geometry_only=True)
        v.trace_add("write", on)
        ttk.Button(fr, text="Vybrat…", command=pick).pack(side="left", padx=4)
        ttk.Button(fr, text="Původní velikost", command=native).pack(side="left")
        return fr

    def _font_field(self, p, key):
        spec = p.setdefault(key, prvky._f(12))
        fr = ttk.Frame(self.props)
        fam = tk.StringVar(value=spec.get("rodina", prvky.DEFAULT_FAMILY))
        size = tk.StringVar(value=str(spec.get("velikost", 11)))
        bold = tk.BooleanVar(value=bool(spec.get("tucne")))
        ttk.Combobox(fr, textvariable=fam, values=prvky.font_families(), width=20,
                     state="readonly").pack(side="left")
        ttk.Spinbox(fr, textvariable=size, from_=5, to=80, width=4).pack(side="left", padx=4)
        ttk.Checkbutton(fr, text="tučně", variable=bold).pack(side="left")

        def on(*_):
            try:
                px = int(float(size.get()))
            except ValueError:
                return
            p[key] = {"rodina": fam.get(), "velikost": px, "tucne": bold.get()}
            self._changed(geometry_only=True)
        for v in (fam, size, bold):
            v.trace_add("write", on)
        return fr
