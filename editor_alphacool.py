# editor_alphacool.py - editor rozvrzeni Alphacool LCD pro okno nastaveni
#
# Nahled displeje zvetseny 3x: klik = vyber prvku, tazeni = posun, tazeni ctverecku
# v pravem dolnim rohu = zmena velikosti, sipky = posun o 1 bod (Shift = 5),
# Ctrl+sipky = zmena velikosti, Delete = smazat. Vpravo seznam prvku (poradi = poradi
# kresleni, dole v seznamu = navrchu) a vlastnosti vybraneho prvku.

import copy
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

import mono
import prvky

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
    "cara": [("smer", "Směr", "choice", ["vodorovna", "svisla"]), ("tloustka", "Tloušťka", "int", None)] + _COL,
    "obdelnik": [("vypln", "Výplň", "choice", ["zadna", "plna", "rastr"]),
                 ("dvojity", "Dvojitý rámeček", "bool", None)] + _COL,
}


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
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)

        self._build_display(left)
        self._build_canvas(left)
        self._build_list(right)
        self.props = ttk.LabelFrame(right, text="Vlastnosti prvku")
        self.props.grid(row=2, column=0, sticky="new", pady=(8, 0))
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
        return self.acfg.setdefault("prvky", [])

    def _build_display(self, f):
        disp = ttk.LabelFrame(f, text="Displej")
        disp.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for col, (key, text) in enumerate((("zapnuto", "Zobrazovat na displeji"),
                                           ("podsviceni", "Podsvícení"),
                                           ("inverze", "Inverze (negativ)"))):
            v = tk.BooleanVar(value=self.acfg.get(key, key != "inverze"))

            def on(k=key, v=v):
                self.acfg[k] = v.get()
                self.refresh()
            ttk.Checkbutton(disp, text=text, variable=v, command=on).grid(
                row=0, column=col, sticky="w", padx=(6, 16), pady=(4, 2))
        self.status = ttk.Label(disp, font=("Segoe UI", 10, "bold"))
        self.status.grid(row=1, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 6))

    def _build_canvas(self, f):
        box = ttk.LabelFrame(f, text="Rozvržení 240×128 (zvětšeno 3×)")
        box.grid(row=1, column=0, sticky="w")
        W, H = mono.WIDTH * SCALE, mono.HEIGHT * SCALE
        self.canvas = tk.Canvas(box, width=W, height=H, bg="black", highlightthickness=1,
                                highlightbackground="#888", cursor="crosshair")
        self.canvas.pack(padx=6, pady=6)
        self._bg = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        for key in ("Left", "Right", "Up", "Down"):
            self.canvas.bind(f"<{key}>", lambda e, k=key: self._on_key(k, e))
        self.canvas.bind("<Delete>", lambda e: self.remove())
        ttk.Label(f, foreground="#666", justify="left", text=(
            "Klik = výběr prvku, tažení = posun, tažení oranžového čtverečku = velikost.\n"
            "Šipky = posun o 1 bod (Shift = 5), Ctrl+šipky = velikost, Delete = smazat.\n"
            "Prvky se kreslí v pořadí seznamu – níž v seznamu = navrchu.")).grid(
            row=2, column=0, sticky="w", pady=(6, 0))

    def _build_list(self, f):
        f.columnconfigure(0, weight=1)
        lf = ttk.LabelFrame(f, text="Prvky (pořadí kreslení)")
        lf.grid(row=0, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        self.lst = tk.Listbox(lf, height=11, exportselection=False, font=("Segoe UI", 10))
        self.lst.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lst.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=4)
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._select(self._list_index()))
        btns = ttk.Frame(f)
        btns.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        add = ttk.Menubutton(btns, text="Přidat ▾")
        m = tk.Menu(add, tearoff=0)
        for t, name in prvky.TYPES.items():
            m.add_command(label=name, command=lambda t=t: self.add(t))
        add["menu"] = m
        add.grid(row=0, column=0, padx=2, sticky="ew")
        for c, (text, cmd) in enumerate((("Duplikovat", self.duplicate), ("Odebrat", self.remove),
                                         ("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1)),
                                         ("Skrýt / ukázat", self.toggle))):
            ttk.Button(btns, text=text, command=cmd, width=len(text) + 2).grid(row=0, column=c + 1, padx=2)

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
            p["x"], p["y"] = min(q["x"] + 6, mono.WIDTH - 8), min(q["y"] + 6, mono.HEIGHT - 8)
        self.items.append(p)
        self.sel = len(self.items) - 1
        self._changed(rebuild=True)

    def duplicate(self):
        if self.sel is None:
            return
        p = copy.deepcopy(self.items[self.sel])
        p["x"], p["y"] = min(p["x"] + 4, mono.WIDTH - 4), min(p["y"] + 4, mono.HEIGHT - 4)
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
        x, y = e.x / SCALE, e.y / SCALE
        if self.sel is not None:                        # ctverecek pro zmenu velikosti
            p = self.items[self.sel]
            hx, hy = (p["x"] + p["w"]) * SCALE, (p["y"] + p["h"]) * SCALE
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
        dx, dy = round((e.x - sx) / SCALE), round((e.y - sy) / SCALE)
        p = self.items[self.sel]
        if mode == "move":
            p["x"] = max(-p["w"] + 2, min(mono.WIDTH - 2, orig["x"] + dx))
            p["y"] = max(-p["h"] + 2, min(mono.HEIGHT - 2, orig["y"] + dy))
        else:
            p["w"] = max(1, min(mono.WIDTH * 2, orig["w"] + dx))
            p["h"] = max(1, min(mono.HEIGHT * 2, orig["h"] + dy))
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
        x0, y0 = p["x"] * SCALE, p["y"] * SCALE
        x1, y1 = (p["x"] + p["w"]) * SCALE, (p["y"] + p["h"]) * SCALE
        self.canvas.create_rectangle(x0 - 1, y0 - 1, x1, y1, outline=SEL_COLOR, dash=(4, 2), tags="sel")
        self.canvas.create_rectangle(x1 - HANDLE, y1 - HANDLE, x1 + HANDLE, y1 + HANDLE,
                                     fill=SEL_COLOR, outline="black", tags="sel")

    def refresh(self):
        """Prekreslit nahled (volano i kazdou sekundu s novymi daty)."""
        try:
            img = mono.render(self.acfg, self.app.data, self.app.hist)
        except Exception as e:
            self.status.config(text=f"Chyba náhledu: {e}", foreground="#c33")
            return
        self._img = ImageTk.PhotoImage(mono.preview(img, SCALE))
        self.canvas.itemconfig(self._bg, image=self._img)
        self._draw_selection()
        self._update_status()

    def _update_status(self):
        st = (self.app.astate or {}).get("stav")
        texts = {"pripojen": ("Displej připojen – zobrazuje se.", "#2a7"),
                 "nenalezen": ("Displej nenalezen (připojený? ovladač WinUSB přes Zadig?)", "#c33"),
                 "chyba": ("Displej nejde otevřít – podrobnosti v rgb_lcd.log", "#c33"),
                 "vypnuto": ("Zobrazování vypnuto.", "#666")}
        text, color = texts.get(st, ("Stav displeje uvidíš, až poběží aplikace.", "#666"))
        if not self.app.running:
            text, color = "Aplikace neběží – náhled z dat HWiNFO.", "#666"
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
            ttk.Label(self.props, foreground="#666",
                      text="Vyber prvek v náhledu nebo v seznamu,\nnebo přidej nový tlačítkem Přidat.").grid(
                padx=6, pady=6, sticky="w")
            return
        p = self.items[self.sel]
        ttk.Label(self.props, text=prvky.TYPES.get(p["typ"], p["typ"]), font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 6))
        geo = ttk.Frame(self.props)
        geo.grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        for c, (k, t) in enumerate((("x", "X"), ("y", "Y"), ("w", "Šířka"), ("h", "Výška"))):
            ttk.Label(geo, text=t).grid(row=0, column=c * 2, padx=(0 if c == 0 else 8, 2))
            v = tk.StringVar(value=str(p[k]))
            ttk.Spinbox(geo, textvariable=v, from_=-240, to=480, width=5).grid(row=0, column=c * 2 + 1)
            v.trace_add("write", lambda *a, k=k, v=v: self._set(k, v.get(), "int"))
            self._form_vars[k] = v
        row = 2
        for key, text, kind, opts in FIELDS.get(p["typ"], []):
            ttk.Label(self.props, text=text).grid(row=row, column=0, sticky="nw", padx=6, pady=2)
            self._field(row, p, key, kind, opts).grid(row=row, column=1, sticky="w", padx=4, pady=2)
            row += 1

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
        if kind == "sensors":
            fr = ttk.Frame(f)
            lb = tk.Listbox(fr, selectmode="multiple", height=6, exportselection=False, width=30)
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

    def _font_field(self, p, key):
        spec = p.setdefault(key, {"rodina": "Tahoma", "velikost": 11, "tucne": False})
        fr = ttk.Frame(self.props)
        fam = tk.StringVar(value=spec.get("rodina", "Tahoma"))
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
