# nastaveni.py - okno pro nastaveni displeje Krakenu
# Spusteni: nastaveni.bat (nebo: pyw nastaveni.py)
# Po kliknuti na "Ulozit" si bezici aplikace nastaveni nacte sama do 1 s.

import copy
import json
import os
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import ImageTk

import config
import hwinfo
import screens

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
}

# (klic, popisek, druh pole) pro editor obrazovky
_F_ONE = [("nadpis", "Popisek", "text"), ("senzor", "Senzor", "sensor"),
          ("min", "Minimum", "num"), ("max", "Maximum", "num")]
_F_TWO = [("nadpis1", "Horní / vnější – popisek", "text"), ("senzor1", "Horní / vnější – senzor", "sensor"),
          ("min1", "Horní / vnější – minimum", "num"), ("max1", "Horní / vnější – maximum", "num"),
          ("nadpis2", "Dolní / vnitřní – popisek", "text"), ("senzor2", "Dolní / vnitřní – senzor", "sensor"),
          ("min2", "Dolní / vnitřní – minimum", "num"), ("max2", "Dolní / vnitřní – maximum", "num")]
_F_FMT = [("jednotka", "Jednotka", "unit"), ("delitel", "Dělitel (1000 = MHz→GHz)", "num"),
          ("desetinna_mista", "Desetinná místa", "int")]
FIELDS = {
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
                    st.get("alphacool", {}))
    except (OSError, ValueError, KeyError):
        pass
    return hwinfo.read_full(), False, {}, {}, {}


class App(tk.Tk):
    last_page = 0            # vybrana hlavni zalozka (zachova se pri "Vratit ulozene")

    def __init__(self):
        super().__init__()
        self.title("RGB-LCD – nastavení")
        try:
            self.iconbitmap(default=os.path.join(config.BASE, "ikona.ico"))
        except tk.TclError:
            pass
        self.minsize(1120, 720)
        self.cfg = config.load()
        self.saved = copy.deepcopy(self.cfg)
        self.data, self.running, self.cstate, self.hist, self.astate = load_data()
        self.sel = 0
        self._preview_img = None
        self._building = False

        # hlavni zalozky: kazde zarizeni ma vlastni ovladani, tlacitka Ulozit/Zavrit jsou spolecna
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.pages = ttk.Notebook(self)
        self.pages.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 4))
        self.kraken_page = ttk.Frame(self.pages)
        self.alpha_page = ttk.Frame(self.pages)
        self.pages.add(self.kraken_page, text="  Kraken (LCD a chlazení)  ")
        self.pages.add(self.alpha_page, text="  Alphacool LCD  ")
        self.kraken_page.columnconfigure(1, weight=1)
        self.kraken_page.rowconfigure(0, weight=1)
        self._build_list()
        self._build_editor()
        self._build_right()
        self._build_alphacool()
        self._build_bottom()
        self.pages.select(App.last_page)
        self.pages.bind("<<NotebookTabChanged>>",
                        lambda e: setattr(App, "last_page", self.pages.index("current")))
        self._refresh_list()
        self._select(0)
        self.bind("<Control-s>", lambda e: self.save())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(1000, self._tick)

    # ---------------------------------------------------------- seznam
    def _build_list(self):
        f = ttk.LabelFrame(self.kraken_page, text="Obrazovky (pořadí rotace)")
        f.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        f.rowconfigure(0, weight=1)
        self.lst = tk.Listbox(f, width=30, height=18, exportselection=False, font=("Segoe UI", 10))
        self.lst.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._select(self._cur_index()))

        add = ttk.Menubutton(f, text="Přidat ▾")
        m = tk.Menu(add, tearoff=0)
        for t, name in TYPES.items():
            m.add_command(label=name, command=lambda t=t: self.add(t))
        add["menu"] = m
        add.grid(row=1, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(f, text="Odebrat", command=self.remove).grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(f, text="▲ Nahoru", command=lambda: self.move(-1)).grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(f, text="▼ Dolů", command=lambda: self.move(1)).grid(row=2, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(f, text="Zapnout / vypnout", command=self.toggle).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=2)

    def _cur_index(self):
        s = self.lst.curselection()
        return s[0] if s else self.sel

    def _label(self, s):
        mark = "✓" if s.get("zapnuto", True) else "✗"
        if s["typ"] in ("dva_bary", "dva_kruhy"):
            name = f"{s.get('nadpis1', '')} / {s.get('nadpis2', '')}"
        elif s["typ"] in ("oblouk", "budik", "graf"):
            name = s.get("nadpis") or s.get("senzor", "")
        else:
            name = ""
        return f"{mark}  {TYPES[s['typ']]}: {name}".rstrip(": ")

    def _refresh_list(self):
        self.lst.delete(0, "end")
        for s in self.cfg["obrazovky"]:
            self.lst.insert("end", self._label(s))
        if self.cfg["obrazovky"]:
            self.sel = min(self.sel, len(self.cfg["obrazovky"]) - 1)
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(self.sel)

    def add(self, typ):
        new = copy.deepcopy(NEW_SCREEN[typ])
        new["zapnuto"] = True
        new["velikost_obsahu"] = 0.92
        if typ != "hodiny":
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

    # ---------------------------------------------------------- editor
    def _build_editor(self):
        self.nb = ttk.Notebook(self.kraken_page)
        self.nb.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.ed = ttk.Frame(self.nb)
        self.ed.columnconfigure(1, weight=1)
        self.nb.add(self.ed, text="Vybraná obrazovka")
        self.cool = ttk.Frame(self.nb)
        self.nb.add(self.cool, text="Chlazení (pumpa a ventilátory)")
        self._build_cooling()

    # ------------------------------------------------------- alphacool
    def _build_alphacool(self):
        """Hlavni zalozka Alphacool LCD: editor rozvrzeni (editor_alphacool.py)."""
        from editor_alphacool import AlphaEditor
        self.alpha = AlphaEditor(self.alpha_page, self)

    def _update_alpha(self):
        if hasattr(self, "alpha"):
            self.alpha.refresh()

    def _sensor_names(self):
        own = sorted(k for k in self.data if k.startswith("@") and k != config.LIQUID)
        names = sorted(k for k in self.data if not k.startswith("@"))
        return [config.LIQUID] + own + names

    # --------------------------------------------------------- chlazeni
    COOL_ROWS = 8

    def _build_cooling(self):
        f = self.cool
        cool = self.cfg["chlazeni"]
        cool.setdefault("cpu", copy.deepcopy(config.DEFAULTS["chlazeni"]["cpu"]))

        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        cv = tk.BooleanVar(value=cool.get("zapnuto", True))
        ttk.Checkbutton(top, text="Řídit pumpu a ventilátory Krakenu", variable=cv,
                        command=lambda: cool.__setitem__("zapnuto", cv.get())).grid(
            row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(top, text="Řídit podle:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.mode = tk.StringVar(value=cool.get("zdroj", "cpu"))

        def on_mode():
            cool["zdroj"] = self.mode.get()
            self.edit_mode.set(self.mode.get())
            self._build_curve_table()
        ttk.Radiobutton(top, text="teploty CPU (jako v CAMu)", value="cpu", variable=self.mode,
                        command=on_mode).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Radiobutton(top, text="teploty kapaliny (řídí Kraken sám)", value="kapalina",
                        variable=self.mode, command=on_mode).grid(row=1, column=2, sticky="w",
                                                                 padx=(10, 0), pady=(6, 0))

        ttk.Label(top, text="Senzor CPU:").grid(row=2, column=0, sticky="w", pady=3)
        sv = tk.StringVar(value=cool.get("senzor_cpu", "CPU (Tctl/Tdie)"))
        ttk.Combobox(top, textvariable=sv, width=28,
                     values=sorted(k for k in self.data if not k.startswith("@"))).grid(
            row=2, column=1, sticky="w", pady=3)
        sv.trace_add("write", lambda *a: cool.__setitem__("senzor_cpu", sv.get()))

        ttk.Label(top, text="Vyhlazení (s):").grid(row=3, column=0, sticky="w", pady=3)
        hv = tk.StringVar(value=str(cool.get("vyhlazeni_s", 5)))
        ttk.Spinbox(top, textvariable=hv, from_=1, to=30, increment=1, width=6).grid(
            row=3, column=1, sticky="w", pady=3)

        def on_h(*_):
            try:
                cool["vyhlazeni_s"] = max(1, int(float(hv.get())))
            except ValueError:
                pass
        hv.trace_add("write", on_h)

        self.cool_status = ttk.Label(f, font=("Segoe UI", 10, "bold"), justify="left")
        self.cool_status.grid(row=1, column=0, sticky="w", padx=8, pady=(6, 6))

        ed = ttk.Frame(f)
        ed.grid(row=2, column=0, sticky="w", padx=8)
        ttk.Label(ed, text="Upravuji křivky:").grid(row=0, column=0, sticky="w")
        self.edit_mode = tk.StringVar(value=self.mode.get())
        ttk.Radiobutton(ed, text="podle CPU", value="cpu", variable=self.edit_mode,
                        command=self._build_curve_table).grid(row=0, column=1, padx=6)
        ttk.Radiobutton(ed, text="podle kapaliny (i záloha)", value="kapalina",
                        variable=self.edit_mode, command=self._build_curve_table).grid(row=0, column=2)

        self.curve_frame = ttk.Frame(f)
        self.curve_frame.grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.cool_canvas = tk.Canvas(f, width=460, height=170, bg="white", highlightthickness=1,
                                     highlightbackground="#bbb")
        self.cool_canvas.grid(row=4, column=0, sticky="w", padx=8, pady=6)
        ttk.Label(f, foreground="#666", justify="left", text=(
            "Podle CPU: aplikace každou sekundu nastaví výkon podle průměrné teploty CPU.\n"
            "Když aplikace skončí (i zavřením okna nebo vypnutím PC), nastane chyba spojení\n"
            "nebo HWiNFO přestane posílat teplotu, převezme řízení Kraken sám podle křivek\n"
            "kapaliny (záloha). Totéž platí při vypnutém řízení. Od 59 °C kapaliny vždy 100 %.")).grid(
            row=5, column=0, sticky="w", padx=8)
        self._build_curve_table()

    def _curves(self):
        cool = self.cfg["chlazeni"]
        return cool["cpu"] if self.edit_mode.get() == "cpu" else cool

    def _build_curve_table(self):
        f = self.curve_frame
        for w in f.winfo_children():
            w.destroy()
        curves = self._curves()
        unit = "CPU °C" if self.edit_mode.get() == "cpu" else "kapalina °C"
        self.cool_vars = {}
        for col, (key, title) in enumerate((("pumpa", "Pumpa"), ("ventilatory", "Ventilátory"))):
            x = col * 3
            ttk.Label(f, text=title, font=("Segoe UI", 10, "bold")).grid(row=0, column=x, columnspan=2,
                                                                       sticky="w", padx=(0 if col == 0 else 30, 0))
            ttk.Label(f, text=unit).grid(row=1, column=x, sticky="w", padx=(0 if col == 0 else 30, 0))
            ttk.Label(f, text="výkon %").grid(row=1, column=x + 1, sticky="w", padx=4)
            pts = curves.get(key, [])
            rows = []
            for i in range(self.COOL_ROWS):
                t = tk.StringVar(value=str(pts[i][0]) if i < len(pts) else "")
                d = tk.StringVar(value=str(pts[i][1]) if i < len(pts) else "")
                ttk.Entry(f, textvariable=t, width=7).grid(row=2 + i, column=x, pady=1, sticky="w",
                                                          padx=(0 if col == 0 else 30, 0))
                ttk.Entry(f, textvariable=d, width=7).grid(row=2 + i, column=x + 1, padx=4, pady=1, sticky="w")
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
        W, H, L, B = 460, 170, 34, 22
        tx = lambda t: L + (min(max(t, x_lo), x_hi) - x_lo) / (x_hi - x_lo) * (W - L - 10)
        ty = lambda d: H - B - d / 100 * (H - B - 10)
        for d in (0, 50, 100):
            c.create_line(L, ty(d), W - 10, ty(d), fill="#eee")
            c.create_text(L - 4, ty(d), text=f"{d}%", anchor="e", font=("Segoe UI", 8))
        step = 10
        for t in range(x_lo, x_hi + 1, step):
            c.create_text(tx(t), H - B + 10, text=f"{t}°", font=("Segoe UI", 8))
        curves = self._curves()
        for key, color in (("pumpa", "#1f77d0"), ("ventilatory", "#e08010")):
            pts = sorted(curves.get(key, []))
            if not pts:
                continue
            xy = [(tx(x_lo), ty(pts[0][1]))] + [(tx(t), ty(d)) for t, d in pts] + [(tx(x_hi), ty(pts[-1][1]))]
            if not is_cpu:
                xy = xy[:-1] + [(tx(59), ty(pts[-1][1])), (tx(59), ty(100)), (tx(60), ty(100))]
            c.create_line(*[v for p in xy for v in p], fill=color, width=2)
            for t, d in pts:
                c.create_oval(tx(t) - 3, ty(d) - 3, tx(t) + 3, ty(d) + 3, fill=color, outline=color)
        if not is_cpu:
            c.create_line(tx(59), 10, tx(59), H - B, fill="#e66", dash=(3, 2))
        c.create_text(L + 8, 16, text="pumpa", fill="#1f77d0", anchor="w", font=("Segoe UI", 8, "bold"))
        c.create_text(L + 8, 30, text="ventilátory", fill="#e08010", anchor="w", font=("Segoe UI", 8, "bold"))
        cur = (self.cstate.get("teplota") if is_cpu
               else (self.data.get(config.LIQUID) or {}).get("value"))
        if cur is not None:
            c.create_line(tx(cur), 10, tx(cur), H - B, fill="#2a7", width=2)
            c.create_text(tx(cur) + 3, 12, text=f"{cur:.0f}°", anchor="nw", fill="#2a7",
                          font=("Segoe UI", 8, "bold"))

    def _update_cool_status(self):
        g = lambda k: (self.data.get(k) or {}).get("value")
        lq, pr, pd, fr, fd = (g("@kapalina"), g("@pumpa"), g("@pumpa_vykon"),
                              g("@ventilatory"), g("@ventilatory_vykon"))
        if lq is None:
            self.cool_status.config(text="Aktuální stav uvidíš, až poběží aplikace (spustit.bat).",
                                    foreground="")
            return
        st = self.cstate
        if st.get("rezim") == "cpu" and st.get("zaloha"):
            head, color = "ZÁLOHA: chybí teplota CPU z HWiNFO – řídí Kraken podle kapaliny", "#c33"
        elif st.get("rezim") == "cpu":
            head, color = f"Řízeno podle CPU {st.get('teplota', 0):.1f} °C (průměr)", ""
        elif st.get("rezim") == "kapalina":
            head, color = "Řídí Kraken sám podle kapaliny", ""
        else:
            head, color = "Řízení aplikací vypnuto – Kraken řídí sám podle křivek kapaliny", "#c33"
        self.cool_status.config(foreground=color, text=(
            f"{head}\nKapalina {lq:.1f} °C  ·  pumpa {pr or 0:.0f} RPM ({pd or 0:.0f} %)  ·  "
            f"ventilátory {fr or 0:.0f} RPM ({fd or 0:.0f} %)"))

    def _select(self, i):
        for w in self.ed.winfo_children():
            w.destroy()
        if not self.cfg["obrazovky"]:
            ttk.Label(self.ed, text="Žádná obrazovka – přidej ji tlačítkem Přidat.").grid(padx=8, pady=8)
            return
        self.sel = i
        self.lst.selection_clear(0, "end")
        self.lst.selection_set(i)
        s = self.cfg["obrazovky"][i]
        self._color_btn = {}
        self._building = True
        row = 0
        ttk.Label(self.ed, text=f"Typ: {TYPES[s['typ']]}", font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 8))
        row += 1
        sizes = [("velikost_obsahu", "Velikost obsahu", 0.6, 1.0, 0.01)]
        if s["typ"] != "hodiny":
            sizes.append(("velikost_textu", "Velikost textu", 0.7, 1.4, 0.05))
        for key, text, lo, hi, res in sizes:
            ttk.Label(self.ed, text=text).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            v = tk.DoubleVar(value=s.get(key, self.cfg.get(key, 1.0)))
            val = ttk.Label(self.ed, width=5, text=f"{v.get():.2f}")
            val.grid(row=row, column=2, sticky="w", padx=4)

            def on(_e=None, k=key, v=v, val=val, res=res):
                x = round(round(v.get() / res) * res, 2)
                self.cfg["obrazovky"][self.sel][k] = x
                val.config(text=f"{x:.2f}")
                self._update_preview()
            tk.Scale(self.ed, variable=v, from_=lo, to=hi, resolution=res, orient="horizontal",
                     showvalue=False, length=220, command=on).grid(row=row, column=1, sticky="w", padx=4)
            row += 1
        ttk.Separator(self.ed).grid(row=row, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        row += 1
        for key, text, kind in FIELDS[s["typ"]]:
            ttk.Label(self.ed, text=text).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            var = tk.StringVar(value=str(s.get(key, "")))
            if kind == "sensor":
                w = ttk.Combobox(self.ed, textvariable=var, values=self._sensor_names(), width=28)
                self._with_value_hint(row, var)
            elif kind == "unit":
                w = ttk.Combobox(self.ed, textvariable=var, values=UNITS, width=10)
            else:
                w = ttk.Entry(self.ed, textvariable=var, width=14 if kind != "text" else 24)
            w.grid(row=row, column=1, sticky="w", padx=4, pady=3)
            var.trace_add("write", lambda *a, k=key, v=var, kd=kind: self._changed(k, v, kd))
            row += 1
        row = self._build_colors(s, row)
        ttk.Label(self.ed, foreground="#666",
                  text=f"{config.LIQUID} = teplota kapaliny přímo z Krakenu.\n"
                       "Senzor z HWiNFO se v seznamu objeví, když u něj zaškrtneš\n"
                       "Report value in Gadget (Hlásit hodnotu pro Gadget).", justify="left").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        self._building = False
        self._update_preview()

    def _with_value_hint(self, row, var):
        lbl = ttk.Label(self.ed, foreground="#666")
        lbl.grid(row=row, column=2, sticky="w", padx=4)

        def upd(*_):
            item = self.data.get(var.get())
            lbl.config(text=f"= {item['value']:g} {item.get('unit', '')}" if item else "(nenalezeno)")
        var.trace_add("write", upd)
        upd()

    def _build_colors(self, s, row):
        """Barvy casti obrazovky: prechod Od -> Do (stejne barvy = jednobarevne)."""
        ttk.Separator(self.ed).grid(row=row, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        row += 1
        ttk.Label(self.ed, text="Barvy (přechod od → do)", font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=8)
        row += 1
        for part, text, d_od, d_do in screens.COLORS.get(s["typ"], []):
            ttk.Label(self.ed, text=text).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            fr = ttk.Frame(self.ed)
            fr.grid(row=row, column=1, columnspan=2, sticky="w", padx=4)
            btns = {}
            for i, (end, dflt) in enumerate((("od", d_od), ("do", d_do))):
                key = f"{part}_{end}"
                col = s.get(key, dflt)
                b = tk.Button(fr, text=end, bg=col, fg=self._contrast(col), width=6, relief="groove",
                              command=lambda k=key, dd=dflt: self._pick_color(k, dd))
                b.grid(row=0, column=i, padx=(0, 4))
                btns[key] = b
            same = ttk.Button(fr, text="= jednobarevně", width=15,
                              command=lambda p=part, do=d_od: self._same_color(p, do))
            same.grid(row=0, column=2, padx=(6, 0))
            self._color_btn.update(btns)
            row += 1
        return row

    @staticmethod
    def _contrast(hexcol):
        r, g, b = screens.hex_rgb(hexcol)
        return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"

    def _pick_color(self, key, default):
        s = self.cfg["obrazovky"][self.sel]
        c = colorchooser.askcolor(color=s.get(key, default), parent=self)[1]
        if c:
            s[key] = c
            self._color_btn[key].config(bg=c, fg=self._contrast(c))
            self._update_preview()

    def _same_color(self, part, default):
        s = self.cfg["obrazovky"][self.sel]
        c = s.get(f"{part}_od", default)
        s[f"{part}_do"] = c
        self._color_btn[f"{part}_do"].config(bg=c, fg=self._contrast(c))
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
    def _build_right(self):
        f = ttk.Frame(self.kraken_page)
        f.grid(row=0, column=2, sticky="nsew", padx=8, pady=8)
        pv = ttk.LabelFrame(f, text="Náhled")
        pv.pack(fill="x")
        self.preview = tk.Label(pv, bg="black", width=240, height=240)
        self.preview.pack(padx=6, pady=6)
        self.src_lbl = ttk.Label(pv, foreground="#666")
        self.src_lbl.pack(pady=(0, 4))

        g = ttk.LabelFrame(f, text="Obecné")
        g.pack(fill="x", pady=(8, 0))
        self.gvars = {}

        def scale(key, text, lo, hi, res, row):
            ttk.Label(g, text=text).grid(row=row, column=0, sticky="w", padx=6)
            v = tk.DoubleVar(value=self.cfg[key])
            val = ttk.Label(g, width=5)
            val.grid(row=row, column=2, padx=4)

            def on(*_):
                x = round(v.get() / res) * res
                self.cfg[key] = int(x) if res >= 1 else round(x, 2)
                val.config(text=str(self.cfg[key]))
                self._update_preview()
            tk.Scale(g, variable=v, from_=lo, to=hi, resolution=res, orient="horizontal",
                     showvalue=False, length=150, command=lambda e: on()).grid(row=row, column=1)
            on()

        def spin(key, text, lo, hi, inc, row):
            ttk.Label(g, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            v = tk.StringVar(value=str(self.cfg[key]))
            ttk.Spinbox(g, textvariable=v, from_=lo, to=hi, increment=inc, width=6).grid(
                row=row, column=1, sticky="w")

            def on(*_):
                try:
                    self.cfg[key] = max(lo, min(hi, float(v.get().replace(",", "."))))
                except ValueError:
                    pass
            v.trace_add("write", on)

        scale("jas", "Jas displeje (%)", 0, 100, 5, 0)
        scale("gama_grafiky", "Světlost grafiky", 0.4, 1.0, 0.05, 3)
        ttk.Label(g, text="(nižší = světlejší)", foreground="#666").grid(row=4, column=1, sticky="w")
        spin("rotace_s", "Rotace obrazovek (s)", 1, 60, 1, 5)
        spin("obnova_s", "Obnova hodnot (s)", MIN_REFRESH_S, 10, 0.25, 6)
        ttk.Label(g, text="(platí i pro Alphacool)", foreground="#666").grid(row=6, column=2, sticky="w")
        av = tk.BooleanVar(value=self.cfg.get("auto_obrazovky", True))

        def on_auto():
            self.cfg["auto_obrazovky"] = av.get()
        ttk.Checkbutton(g, text="Automaticky zobrazit nové senzory z HWiNFO", variable=av,
                        command=on_auto).grid(row=7, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 4))

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
        base = "Data: z běžící aplikace" if self.running else "Data: přímo z HWiNFO (aplikace neběží)"
        self.src_lbl.config(text=base + ("\nchybějící hodnoty = ukázkové" if sample else ""))
        self._preview_img = ImageTk.PhotoImage(img)
        self.preview.config(image=self._preview_img, width=240, height=240)

    def _preview_data(self, scr):
        """Data pro nahled; chybejici senzory (napr. kapalina bez bezici aplikace)
        dostanou ukazkovou hodnotu uprostred rozsahu, graf ukazkovou krivku."""
        import math
        data = dict(self.data)
        hist = dict(self.hist)
        sample = False
        scr = dict(scr)
        for n in ("", "1", "2"):
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
        if scr.get("typ") == "graf":
            name = scr.get("senzor")
            if name and len(hist.get(name, [])) < 2:
                lo, hi = float(scr.get("min", 0)), float(scr.get("max", 100))
                div = float(scr.get("delitel", 1)) or 1
                hist[name] = [(lo + (hi - lo) * (0.45 + 0.25 * math.sin(i / 7))) * div
                              for i in range(90)]
                sample = True
        return scr, data, hist, sample

    def _tick(self):
        self.data, self.running, self.cstate, self.hist, self.astate = load_data()
        self._update_preview()
        self._update_cool_status()
        self._draw_curves()
        self._update_alpha()
        self.after(1000, self._tick)

    # ---------------------------------------------------------- ulozeni
    def _build_bottom(self):
        b = ttk.Frame(self)
        b.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.status = ttk.Label(b, foreground="#2a7")
        self.status.pack(side="left")
        ttk.Button(b, text="Zavřít", command=self.on_close).pack(side="right", padx=4)
        ttk.Button(b, text="Uložit  (Ctrl+S)", command=self.save).pack(side="right", padx=4)
        ttk.Button(b, text="Vrátit uložené", command=self.revert).pack(side="right", padx=4)

    def save(self):
        config.save(self.cfg)
        self.saved = copy.deepcopy(self.cfg)
        self.status.config(text="Uloženo – běžící aplikace změnu načte do 1 s.")
        self.after(4000, lambda: self.status.config(text=""))

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
