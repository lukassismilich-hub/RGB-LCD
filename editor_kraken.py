# editor_kraken.py - editor volneho rozvrzeni obrazovky Krakenu (typ "volne", prvky v kraken_prvky.py)
#
# Samostatne okno: nahled displeje zvetseny 2x (zive vykresleni), klik = vyber prvku,
# tazeni = posun, tazeni ctverecku v pravem dolnim rohu = velikost, sipky = posun o 1 bod
# (Shift = 5), Ctrl+sipky = velikost, Ctrl+D = duplikovat, Delete = smazat. Prichytavani
# na mrizku 4 px a na stred displeje (magentova cara). Vpravo seznam prvku (nize = navrchu),
# vlastnosti vybraneho prvku a sablony slozene z prvku existujicich obrazovek.
# Zmeny jdou primo do nastaveni v hlavnim okne (Ulozit / Ctrl+S).

import copy
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk

import kraken_prvky as K
import screens
import vzhled as V

SCALE = 2
HANDLE = 5
SNAP = 4
GUIDE = "#ff4fd8"


class KrakenEditor(tk.Toplevel):
    def __init__(self, app, scr):
        super().__init__(app)
        self.app, self.scr = app, scr
        self.title("Kraken LCD – editor rozvržení")
        self.configure(bg=V.BG)
        self.geometry("1220x840")
        self.minsize(1100, 740)
        self.transient(app)
        self.sel = None
        self._drag = None
        self._guides = []
        self._img = None
        self._render_job = None
        self._app_job = None
        self._vars = {}
        self._syncing = False
        self.snap = tk.BooleanVar(value=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_canvas()
        self._build_side()
        self._refresh_list()
        self._build_props()
        self.render()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Control-s>", lambda e: self.app.save())

    @property
    def items(self):
        return self.scr.setdefault("prvky", [])

    # ------------------------------------------------------------- platno
    def _build_canvas(self):
        card = V.card(self)
        card.grid(row=0, column=0, sticky="nsw", padx=(20, 10), pady=20)
        head = ttk.Frame(card)
        head.pack(fill="x", padx=16, pady=(14, 10))
        V.card_title(head, "Displej 240 × 240 (zvětšeno 2×)").pack(side="left")
        ttk.Checkbutton(head, text="Přichytávat po 4 px", variable=self.snap).pack(side="right")
        bezel = tk.Frame(card, bg="#0c0e11", padx=6, pady=6)
        bezel.pack(padx=16)
        self.canvas = tk.Canvas(bezel, width=240 * SCALE, height=240 * SCALE, bg="black", highlightthickness=0,
                                bd=0, cursor="crosshair")
        self.canvas.pack()
        self._bg = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        for key in ("Left", "Right", "Up", "Down"):
            self.canvas.bind(f"<{key}>", lambda e, k=key: self._key(e, k))
        self.canvas.bind("<Delete>", lambda e: self.remove())
        self.canvas.bind("<Control-d>", lambda e: self.duplicate())
        self.status = ttk.Label(card, style="Small.TLabel")
        self.status.pack(anchor="w", padx=16, pady=(8, 0))
        ttk.Label(card, style="Small.TLabel", justify="left", text=(
            "Klik = výběr prvku, tažení = posun, tažení čtverečku v rohu = velikost.\n"
            "Šipky = posun o 1 bod (Shift = 5), Ctrl+šipky = velikost, Ctrl+D = duplikovat, Delete = smazat.\n"
            "Magentová čára = prvek je na středu displeje. Prvky níž v seznamu se kreslí navrch.")).pack(
            anchor="w", padx=16, pady=(4, 10))
        btns = ttk.Frame(card)
        btns.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(btns, text="Uložit   Ctrl+S", style="Accent.TButton", command=self.app.save).pack(side="right")
        ttk.Button(btns, text="Zavřít", command=self.close).pack(side="right", padx=8)

    def render(self):
        """Prekresleni nahledu (sloucene - pri tazeni se nekresli vic nez ~40x za sekundu)."""
        if self._render_job is None:
            self._render_job = self.after(25, self._do_render)

    def _do_render(self):
        self._render_job = None
        try:
            _scr, data, hist, sample = self.app._preview_data(self.scr)
            big = K.render(self.items, data, hist)
            img = big.resize((240 * SCALE, 240 * SCALE), Image.LANCZOS)
            gamma = self.app.cfg.get("gama_grafiky", 1.0)
            if gamma and gamma != 1.0:
                lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
                img = img.point(lut * 3)
        except Exception as e:                       # chyba nahledu nesmi zavrit editor
            self.status.config(text=f"Chyba náhledu: {e}", foreground=V.ERR)
            return
        src = "Data z běžící aplikace" if self.app.running else "Data přímo z HWiNFO (aplikace neběží)"
        self.status.config(text=src + (" · chybějící hodnoty a grafy jsou ukázkové" if sample else ""),
                           foreground=V.MUTED)
        self._img = ImageTk.PhotoImage(img)
        self.canvas.itemconfig(self._bg, image=self._img)
        self._draw_selection()

    def refresh(self):
        """Nova data (vola hlavni okno kazdou sekundu)."""
        self.render()

    def _draw_selection(self):
        c = self.canvas
        c.delete("sel")
        for g in self._guides:
            if g == "v":
                c.create_line(120 * SCALE, 0, 120 * SCALE, 240 * SCALE, fill=GUIDE, dash=(4, 3), tags="sel")
            else:
                c.create_line(0, 120 * SCALE, 240 * SCALE, 120 * SCALE, fill=GUIDE, dash=(4, 3), tags="sel")
        if self.sel is None or self.sel >= len(self.items):
            return
        p = self.items[self.sel]
        x0, y0 = p["x"] * SCALE, p["y"] * SCALE
        x1, y1 = (p["x"] + p["w"]) * SCALE, (p["y"] + p["h"]) * SCALE
        c.create_rectangle(x0, y0, x1 - 1, y1 - 1, outline=V.ACCENT, dash=(4, 2), tags="sel")
        c.create_rectangle(x1 - HANDLE, y1 - HANDLE, x1 + HANDLE, y1 + HANDLE, fill=V.ACCENT, outline="black",
                           tags="sel")
        c.create_text(x0 + 2, y0 - 2 if y0 > 14 else y1 + 2, anchor="sw" if y0 > 14 else "nw", fill=V.ACCENT,
                      font=("Consolas", 9), text=f"{p['x']}, {p['y']} · {p['w']} × {p['h']}", tags="sel")

    # ------------------------------------------------------------ mys a klavesy
    def _hit(self, x, y):
        for i in range(len(self.items) - 1, -1, -1):
            p = self.items[i]
            if not p.get("skryty") and p["x"] <= x < p["x"] + p["w"] and p["y"] <= y < p["y"] + p["h"]:
                return i
        return None

    def _press(self, e):
        self.canvas.focus_set()
        if self.sel is not None and self.sel < len(self.items):
            p = self.items[self.sel]
            hx, hy = (p["x"] + p["w"]) * SCALE, (p["y"] + p["h"]) * SCALE
            if abs(e.x - hx) <= HANDLE + 2 and abs(e.y - hy) <= HANDLE + 2:
                self._drag = ("size", e.x, e.y, dict(p))
                return
        i = self._hit(e.x / SCALE, e.y / SCALE)
        if i != self.sel:
            self._select(i)
        if i is not None:
            self._drag = ("move", e.x, e.y, dict(self.items[i]))

    def _motion(self, e):
        if not self._drag or self.sel is None:
            return
        mode, sx, sy, o = self._drag
        dx, dy = (e.x - sx) / SCALE, (e.y - sy) / SCALE
        g = SNAP if self.snap.get() else 1
        p = self.items[self.sel]
        self._guides = []
        if mode == "move":
            nx, ny = round((o["x"] + dx) / g) * g, round((o["y"] + dy) / g) * g
            if abs(nx + p["w"] / 2 - 120) <= 3:                 # prichytit stred prvku ke stredu displeje
                nx = round(120 - p["w"] / 2)
                self._guides.append("v")
            if abs(ny + p["h"] / 2 - 120) <= 3:
                ny = round(120 - p["h"] / 2)
                self._guides.append("h")
            p["x"] = int(max(-p["w"] + 4, min(236, nx)))
            p["y"] = int(max(-p["h"] + 4, min(236, ny)))
        else:
            p["w"] = int(max(4, round((o["w"] + dx) / g) * g))
            p["h"] = int(max(4, round((o["h"] + dy) / g) * g))
        self._changed(geometry=True)

    def _release(self, _e):
        self._drag = None
        self._guides = []
        self._draw_selection()

    def _key(self, e, key):
        if self.sel is None:
            return None
        step = 5 if e.state & 0x0001 else 1
        dx, dy = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, -step), "Down": (0, step)}[key]
        p = self.items[self.sel]
        if e.state & 0x0004:                                    # Ctrl = velikost
            p["w"], p["h"] = max(4, p["w"] + dx), max(4, p["h"] + dy)
        else:
            p["x"], p["y"] = p["x"] + dx, p["y"] + dy
        self._changed(geometry=True)
        return "break"

    # ------------------------------------------------------------ seznam
    def _build_side(self):
        side = tk.Frame(self, bg=V.BG)
        side.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        lf = V.card(side)
        lf.grid(row=0, column=0, sticky="ew")
        lf.columnconfigure(0, weight=1)
        head = ttk.Frame(lf)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(16, 12), pady=(14, 8))
        head.columnconfigure(0, weight=1)
        V.card_title(head, "Prvky").grid(row=0, column=0, sticky="w")
        tpl = ttk.Menubutton(head, text="Šablona")
        tm = tk.Menu(tpl, tearoff=0)
        for name in K.templates():
            tm.add_command(label=name, command=lambda n=name: self.load_template(n))
        tpl["menu"] = tm
        tpl.grid(row=0, column=1, padx=(8, 0))
        add = ttk.Menubutton(head, text="+ Přidat")
        m = tk.Menu(add, tearoff=0)
        for t, name in K.TYPES.items():
            m.add_command(label=name, command=lambda t=t: self.add(t))
        add["menu"] = m
        add.grid(row=0, column=2, padx=(8, 0))
        self.lst = V.listbox(lf, height=11)
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
        pc = V.card(side)
        pc.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        pc.rowconfigure(0, weight=1)
        pc.columnconfigure(0, weight=1)
        sf = V.ScrollFrame(pc, bg=V.CARD)
        sf.grid(row=0, column=0, sticky="nsew", padx=(16, 4), pady=12)
        self.props = sf.inner
        self.props.columnconfigure(1, weight=1)

    def _list_index(self):
        s = self.lst.curselection()
        return s[0] if s else None

    def _refresh_list(self):
        self.lst.delete(0, "end")
        for i, p in enumerate(self.items):
            self.lst.insert("end", ("○ " if p.get("skryty") else "  ") + K.label(p))
            if p.get("skryty"):
                self.lst.itemconfig(i, fg=V.DIM)
        if self.sel is not None and self.sel < len(self.items):
            self.lst.selection_set(self.sel)
            self.lst.see(self.sel)

    def _select(self, i):
        self.sel = i if (i is not None and 0 <= i < len(self.items)) else None
        self._refresh_list()
        self._build_props()
        self._draw_selection()

    def add(self, typ):
        p = K.new(typ)
        if self.sel is not None and self.sel < len(self.items):
            q = self.items[self.sel]
            p["x"], p["y"] = min(q["x"] + 8, 200), min(q["y"] + 8, 200)
        self.items.append(p)
        self.sel = len(self.items) - 1
        self._changed(rebuild=True)

    def duplicate(self):
        if self.sel is None:
            return
        p = copy.deepcopy(self.items[self.sel])
        p["x"], p["y"] = p["x"] + 6, p["y"] + 6
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

    def load_template(self, name):
        if self.items and not messagebox.askyesno(
                "Šablona", f"Nahradit prvky této obrazovky šablonou „{name}“?", parent=self):
            return
        self.scr["prvky"] = copy.deepcopy(K.templates()[name])
        self.sel = None
        self._changed(rebuild=True)

    def _changed(self, geometry=False, rebuild=False):
        if geometry and self.sel is not None:
            self._sync_geometry()
            p = self.items[self.sel]
            self.lst.delete(self.sel)
            self.lst.insert(self.sel, ("○ " if p.get("skryty") else "  ") + K.label(p))
            self.lst.selection_set(self.sel)
        else:
            self._refresh_list()
            if rebuild:
                self._build_props()
        self.render()
        if self._app_job is None:                               # nahled v hlavnim okne mene casto
            self._app_job = self.after(300, self._update_app)

    def _update_app(self):
        self._app_job = None
        try:
            self.app._refresh_list()
            self.app._update_preview()
        except tk.TclError:
            pass

    # ---------------------------------------------------------- vlastnosti
    def _sync_geometry(self):
        if self.sel is None:
            return
        p = self.items[self.sel]
        self._syncing = True
        for k in ("x", "y", "w", "h"):
            v = self._vars.get(k)
            if v is not None and v.get() != str(p[k]):
                v.set(str(p[k]))
        self._syncing = False

    def _build_props(self):
        for w in self.props.winfo_children():
            w.destroy()
        self._vars = {}
        if self.sel is None or self.sel >= len(self.items):
            V.card_title(self.props, "Vlastnosti prvku").grid(row=0, column=0, columnspan=2, sticky="w")
            ttk.Label(self.props, style="Muted.TLabel", justify="left",
                      text="Vyber prvek na displeji nebo v seznamu,\nnebo přidej nový tlačítkem + Přidat "
                           "či začni šablonou.").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
            return
        p = self.items[self.sel]
        V.card_title(self.props, K.TYPES.get(p["typ"], p["typ"])).grid(row=0, column=0, columnspan=2, sticky="w",
                                                                       pady=(0, 8))
        geo = ttk.Frame(self.props)
        geo.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for c, (k, t) in enumerate((("x", "X"), ("y", "Y"), ("w", "Šířka"), ("h", "Výška"))):
            ttk.Label(geo, text=t, style="Muted.TLabel").grid(row=0, column=c * 2, padx=(0 if c == 0 else 12, 4))
            v = tk.StringVar(value=str(p[k]))
            ttk.Spinbox(geo, textvariable=v, from_=-240, to=480, width=5, font=V.MONO).grid(row=0, column=c * 2 + 1)
            v.trace_add("write", lambda *a, k=k, v=v: self._set(k, v.get(), "int"))
            self._vars[k] = v
        row = 2
        for key, text, kind, opts in K.FIELDS.get(p["typ"], []):
            ttk.Label(self.props, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10),
                                                                       pady=3)
            self._field(p, key, kind, opts).grid(row=row, column=1, sticky="w", pady=3)
            row += 1

    def _default(self, p, key):
        return K.NEW.get(p["typ"], {}).get(key, "")

    def _field(self, p, key, kind, opts):
        f = self.props
        if kind == "bool":
            v = tk.BooleanVar(value=bool(p.get(key, self._default(p, key))))
            return ttk.Checkbutton(f, variable=v, command=lambda: self._set(key, v.get(), "bool"))
        if kind == "color":
            col = p.get(key) or self._default(p, key) or "#ffffff"
            b = V.swatch(f, col, None, text=col, width=9)
            b.config(command=lambda: self._pick_color(key, b))
            return b
        v = tk.StringVar(value=str(p.get(key, self._default(p, key))))
        self._vars[key] = v
        if kind == "sensor":
            w = ttk.Combobox(f, textvariable=v, values=self.app._sensor_names() + K.TIME_SENSORS, width=30)
        elif kind == "unit":
            w = ttk.Combobox(f, textvariable=v, values=K.UNITS, width=10)
        elif kind == "choice":
            w = ttk.Combobox(f, textvariable=v, values=opts, width=14, state="readonly")
        elif kind == "image":
            w = ttk.Combobox(f, textvariable=v, values=screens.image_files(), width=32, state="readonly")
        elif kind == "mode":
            w = ttk.Combobox(f, textvariable=v, values=screens.IMAGE_MODES, width=30, state="readonly")
        else:
            w = ttk.Entry(f, textvariable=v, width=8 if kind in ("int", "num") else 30,
                          font=V.MONO if kind in ("int", "num") else V.FONT)
        v.trace_add("write", lambda *a: self._set(key, v.get(), kind))
        return w

    def _pick_color(self, key, button):
        if self.sel is None:
            return
        p = self.items[self.sel]
        c = colorchooser.askcolor(color=p.get(key) or self._default(p, key) or "#ffffff", parent=self)[1]
        if c:
            p[key] = c
            V.set_swatch(button, c)
            button.config(text=c)
            self._changed()

    def _set(self, key, raw, kind):
        if self._syncing or self.sel is None or self.sel >= len(self.items):
            return
        p = self.items[self.sel]
        v = raw
        if kind in ("int", "num"):
            try:
                v = float(str(raw).replace(",", "."))
            except ValueError:
                return
            v = int(round(v)) if kind == "int" or v.is_integer() else v
        p[key] = v
        self._changed(geometry=key in ("x", "y", "w", "h"))

    # ------------------------------------------------------------- konec
    def close(self):
        for job in (self._render_job, self._app_job):
            if job:
                self.after_cancel(job)
        self._render_job = self._app_job = None
        self.app._keditor = None
        self._update_app()
        self.destroy()
