# editor_led.py - zalozka LED v okne nastaveni
#   - jas vsech ventilatoru + vyrovnani F140 / ventilatory na desce
#   - efekt pro vsechny ventilatory (nebo zvlast F140 a deska), rychlost, smer, barvy, vlna
#   - vlastni barvy LED (kruh 8 / 16 LED) - pro efekt "vlastni barvy LED" a klidny stav po ukonceni
#   - zivy animovany nahled (stejny vypocet jako ve vlakne LED)
#   - sbalene: ARGB hlavicky (pocet LED, D_LED2) a ostatni zony desky
# Zmeny se na ventilatorech projevi po Ulozit.

import math
import time
import tkinter as tk
from tkinter import colorchooser, ttk

import led
import led_efekty as fx

RING = 190
DOT = 13
PREVIEW_MS = 40


def _contrast(hexcol):
    r, g, b = fx.hex_rgb(hexcol)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"


class LedEditor:
    def __init__(self, parent, app):
        self.app = app
        self.engine = fx.Engine(seed=7)
        self.t0 = time.monotonic()
        self._prev = self.t0
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        v = tk.BooleanVar(value=self.lcfg.get("zapnuto", True))
        ttk.Checkbutton(top, text="Řídit LED z aplikace", variable=v,
                        command=lambda: self.lcfg.__setitem__("zapnuto", v.get())).pack(side="left")
        self.status = ttk.Label(top, font=("Segoe UI", 10, "bold"))
        self.status.pack(side="left", padx=16)

        left = ttk.Frame(parent)
        left.grid(row=1, column=0, sticky="nw", padx=8)
        right = ttk.Frame(parent)
        right.grid(row=1, column=1, sticky="nw", padx=8)

        self._build_brightness(left)
        self.fx_frame = ttk.LabelFrame(left, text="Efekt")
        self.fx_frame.grid(row=1, column=0, sticky="ew", pady=6)
        self._build_effects()
        self.custom = ttk.LabelFrame(left, text="Vlastní barvy LED (efekt „vlastní barvy LED“ a klidný stav "
                                                "po ukončení aplikace)")
        self.custom.grid(row=2, column=0, sticky="ew", pady=6)
        self._build_custom()

        pv = ttk.LabelFrame(right, text="Živý náhled")
        pv.pack(anchor="nw")
        self.preview = tk.Canvas(pv, width=420, height=170, bg="#111", highlightthickness=0)
        self.preview.pack(padx=6, pady=6)
        ttk.Label(right, foreground="#666", justify="left", text=(
            "Náhled počítá efekt stejně jako aplikace,\nvčetně jasu. Na ventilátorech se změna\n"
            "projeví po Uložit.")).pack(anchor="w", pady=(4, 10))
        self.hw = ttk.Frame(right)
        self.hw.pack(anchor="nw", fill="x")
        self._build_hw()
        self.refresh()
        self._animate()

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    # ---------------------------------------------------------------- jas
    def _build_brightness(self, parent):
        f = ttk.LabelFrame(parent, text="Jas")
        f.grid(row=0, column=0, sticky="ew")
        for row, (key, text, lo) in enumerate((("jas", "Všechny ventilátory", 0),
                                              ("jas_f140", "F140 (vyrovnání)", 20),
                                              ("jas_deska", "Ventilátory na desce (vyrovnání)", 20))):
            ttk.Label(f, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            v = tk.IntVar(value=int(self.lcfg.get(key, 100 if key != "jas" else 80)))
            val = ttk.Label(f, width=5, text=f"{v.get()} %")
            val.grid(row=row, column=2, sticky="w")

            def on(_e=None, key=key, v=v, val=val):
                self.lcfg[key] = int(v.get())
                val.config(text=f"{int(v.get())} %")
            tk.Scale(f, variable=v, from_=lo, to=100, resolution=5, orient="horizontal", showvalue=False,
                     length=220, command=on).grid(row=row, column=1, padx=4)

    # -------------------------------------------------------------- efekty
    def _build_effects(self):
        f = self.fx_frame
        for w in f.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("stejne_pro_vse", True))

        def on_same():
            self.lcfg["stejne_pro_vse"] = same.get()
            self._build_effects()
        ttk.Radiobutton(f, text="Stejný efekt pro všechny ventilátory", value=True, variable=same,
                        command=on_same).grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))
        ttk.Radiobutton(f, text="Zvlášť F140 a ventilátory na desce", value=False, variable=same,
                        command=on_same).grid(row=0, column=1, sticky="w", padx=6, pady=(4, 0))
        wave = tk.BooleanVar(value=self.lcfg.get("vlna", False))
        ttk.Checkbutton(f, text="Vlna přes všechny ventilátory (efekt se mezi nimi posouvá)", variable=wave,
                        command=lambda: self.lcfg.__setitem__("vlna", wave.get())).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        if same.get():
            panels = [("efekt", "Všechny ventilátory")]
        else:
            panels = [("efekt_f140", "F140"), ("efekt_deska", "Ventilátory na desce")]
        for col, (key, title) in enumerate(panels):
            eff = self.lcfg.setdefault(key, dict(fx.DEFAULT_EFFECT))
            pf = ttk.LabelFrame(f, text=title)
            pf.grid(row=2, column=col, columnspan=2 if len(panels) == 1 else 1, sticky="nw", padx=6, pady=6)
            self._effect_panel(pf, eff)

    def _effect_panel(self, f, eff):
        names = {k: v[0] for k, v in fx.EFFECTS.items()}
        rev = {v: k for k, v in names.items()}
        typ = eff.get("typ", "duha_toceni")
        _n, ncolors, has_speed, has_dir = fx.EFFECTS.get(typ, fx.EFFECTS["vypnuto"])
        tv = tk.StringVar(value=names.get(typ, "vypnuto"))
        ttk.Label(f, text="Efekt").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(f, textvariable=tv, values=list(names.values()), state="readonly", width=20).grid(
            row=0, column=1, sticky="w", padx=4)

        def on_typ(*_):
            eff["typ"] = rev[tv.get()]
            self._build_effects()
        tv.trace_add("write", on_typ)
        row = 1
        if has_speed:
            ttk.Label(f, text="Rychlost").grid(row=row, column=0, sticky="w", padx=4, pady=2)
            sv = tk.IntVar(value=int(eff.get("rychlost", 4)))
            tk.Scale(f, variable=sv, from_=1, to=10, orient="horizontal", length=160,
                     command=lambda _e: eff.__setitem__("rychlost", int(sv.get()))).grid(
                row=row, column=1, sticky="w", padx=4)
            row += 1
        if has_dir:
            dv = tk.BooleanVar(value=bool(eff.get("opacny_smer")))
            ttk.Checkbutton(f, text="Opačný směr", variable=dv,
                            command=lambda: eff.__setitem__("opacny_smer", dv.get())).grid(
                row=row, column=1, sticky="w", padx=4)
            row += 1
        if ncolors:
            labels = {"kometa": ["kometa", "pozadí"], "trpyt": ["záblesky", "pozadí"],
                      "prechod": ["barva 1", "barva 2"], "teplota": ["studená", "střední", "horká"]}.get(
                typ, [f"barva {i + 1}" for i in range(ncolors)])
            cols = eff.setdefault("barvy", list(fx.DEFAULT_EFFECT["barvy"]))
            while len(cols) < ncolors:
                cols.append("#ffffff")
            ttk.Label(f, text="Barvy").grid(row=row, column=0, sticky="w", padx=4, pady=2)
            bf = ttk.Frame(f)
            bf.grid(row=row, column=1, sticky="w", padx=4)
            for i in range(ncolors):
                b = tk.Button(bf, text=labels[i], bg=cols[i], fg=_contrast(cols[i]), relief="groove", width=8)
                b.config(command=lambda i=i, b=b: self._pick_list(cols, i, b))
                b.pack(side="left", padx=2)
            row += 1
        if typ == "teplota":
            ttk.Label(f, text="Senzor").grid(row=row, column=0, sticky="w", padx=4, pady=2)
            sn = tk.StringVar(value=eff.get("senzor", "CPU (Tctl/Tdie)"))
            ttk.Combobox(f, textvariable=sn, values=self.app._sensor_names(), width=26).grid(
                row=row, column=1, sticky="w", padx=4)
            sn.trace_add("write", lambda *a: eff.__setitem__("senzor", sn.get()))
            row += 1
            rf = ttk.Frame(f)
            rf.grid(row=row, column=1, sticky="w", padx=4)
            for key, text in (("min", "studená od"), ("max", "horká od")):
                ttk.Label(rf, text=text).pack(side="left")
                v = tk.StringVar(value=str(eff.get(key, 40 if key == "min" else 90)))
                ttk.Entry(rf, textvariable=v, width=5).pack(side="left", padx=(2, 8))

                def on(*a, key=key, v=v):
                    try:
                        eff[key] = float(v.get().replace(",", "."))
                    except ValueError:
                        pass
                v.trace_add("write", on)
            row += 1
        if typ == "vlastni":
            ttk.Label(f, foreground="#666", text="Barvy jednotlivých LED nastavíš níže.").grid(
                row=row, column=0, columnspan=2, sticky="w", padx=4, pady=2)

    def _pick_list(self, cols, i, b):
        c = colorchooser.askcolor(color=cols[i], parent=self.fx_frame)[1]
        if c:
            cols[i] = c
            b.config(bg=c, fg=_contrast(c))

    # ------------------------------------------------------ vlastni barvy LED
    def _build_custom(self):
        f = self.custom
        for w in f.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("nzxt_stejne", True))

        def on_same():
            self.lcfg["nzxt_stejne"] = same.get()
            self._build_custom()
        ttk.Checkbutton(f, text="Oba F140 stejně", variable=same, command=on_same).grid(
            row=0, column=0, sticky="w", padx=6, pady=(4, 0))
        rings = [("F140 (1)" if not same.get() else "F140", self.lcfg["nzxt"]["led1"], led.LEDS_PER_FAN,
                  "čelo PC ▸")]
        if not same.get():
            rings.append(("F140 (2)", self.lcfg["nzxt"]["led2"], led.LEDS_PER_FAN, "čelo PC ▸"))
        h = self.lcfg["argb"]["D_LED1"]
        rings.append(("Ventilátory na desce", h, max(1, min(led.ARGB_MAX_LEDS, int(h.get("pocet_led", 16)))),
                      None))
        for col, (title, ch, n, front) in enumerate(rings):
            fr = ttk.Frame(f)
            fr.grid(row=1, column=col, sticky="nw", padx=6, pady=4)
            ttk.Label(fr, text=title, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            self._ring(fr, ch, n, front)

    def _ring(self, parent, ch, n, front):
        cols = (list(ch.get("barvy", [])) + led.rainbow(n))[:n]
        ch["barvy"] = cols
        size = 150
        dot = 11 if n <= 8 else 7
        c = tk.Canvas(parent, width=size, height=size, bg="#202020", highlightthickness=0)
        c.pack(anchor="w")
        R = size / 2 - dot - 12
        cx = cy = size / 2
        for i, col in enumerate(cols):
            ang = math.radians(360 * i / n)
            x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            tag = f"l{i}"
            c.create_oval(x - dot, y - dot, x + dot, y + dot, fill=col, outline="#ddd", tags=tag)
            c.create_text(x, y, text=str(i + 1), fill=_contrast(col), font=("Segoe UI", 6 if n > 8 else 7, "bold"),
                          tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._pick_led(ch, i))
        if front:
            c.create_text(size - 3, cy + dot + 10, text=front, fill="#aaa", anchor="e", font=("Segoe UI", 7))
        bf = ttk.Frame(parent)
        bf.pack(anchor="w", pady=(4, 0))

        def all_one():
            col = colorchooser.askcolor(color=cols[0], parent=parent)[1]
            if col:
                ch["barvy"] = [col] * n
                self._build_custom()

        def rainbow():
            ch["barvy"] = led.rainbow(n)
            self._build_custom()

        def rotate():
            ch["barvy"] = cols[-1:] + cols[:-1]
            self._build_custom()
        for text, cmd in (("Vše…", all_one), ("Duha", rainbow), ("↻", rotate)):
            ttk.Button(bf, text=text, command=cmd, width=6).pack(side="left", padx=1)

    def _pick_led(self, ch, i):
        col = colorchooser.askcolor(color=ch["barvy"][i], parent=self.custom)[1]
        if col:
            ch["barvy"][i] = col
            self._build_custom()

    # -------------------------------------------------------------- hardware
    def _build_hw(self):
        f = self.hw
        show = tk.BooleanVar(value=False)
        inner = ttk.Frame(f)
        ttk.Checkbutton(f, text="Zobrazit nastavení hardwaru (ARGB hlavičky, další zóny desky)", variable=show,
                        command=lambda: inner.pack(anchor="w") if show.get() else inner.pack_forget()).pack(
            anchor="w")
        af = ttk.LabelFrame(inner, text="ARGB hlavičky desky")
        af.pack(anchor="w", fill="x", pady=4)
        for r, name in enumerate(led.ARGB_HEADERS):
            h = self.lcfg["argb"].setdefault(name, {"pocet_led": 16, "pouzito": False})
            used = tk.BooleanVar(value=h.get("pouzito", name == "D_LED1"))
            ttk.Checkbutton(af, text=f"{name} – {h.get('nazev', '')}", variable=used,
                            command=lambda h=h, used=used: h.__setitem__("pouzito", used.get())).grid(
                row=r, column=0, sticky="w", padx=4, pady=2)
            ttk.Label(af, text="počet LED").grid(row=r, column=1, padx=(10, 2))
            pv = tk.StringVar(value=str(h.get("pocet_led", 16)))
            ttk.Spinbox(af, textvariable=pv, from_=1, to=led.ARGB_MAX_LEDS, width=4).grid(row=r, column=2)

            def on_count(*a, h=h, pv=pv):
                try:
                    h["pocet_led"] = max(1, min(led.ARGB_MAX_LEDS, int(pv.get())))
                except ValueError:
                    pass
            pv.trace_add("write", on_count)
        ttk.Label(af, foreground="#666", text="Nezaškrtnutá hlavička zůstane zhasnutá.").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=4)
        zf = ttk.LabelFrame(inner, text="Další zóny desky (malé LED na desce, 12V RGB) – jen celá zóna")
        zf.pack(anchor="w", fill="x", pady=4)
        self._build_zones(zf)
        ttk.Label(inner, foreground="#666", justify="left", text=(
            "LED desky jinak ovládá Gigabyte Control Center (GCC) – pokud běží,\n"
            "nastavení desky přepíše (autostart_zapnout.bat ho vypne).")).pack(anchor="w")

    def _build_zones(self, f):
        names = {k: v[0] for k, v in led.FUSION_MODES.items()}
        rev_names = {v: k for k, v in names.items()}
        rev_speed = {v: k for k, v in led.FUSION_SPEEDS.items()}
        r = 0
        for i in range(1, 9):
            zone = f"led{i}"
            if zone in led.ARGB_ZONES:
                continue
            z = self.lcfg["fusion"][zone]
            ttk.Label(f, text=zone).grid(row=r, column=0, sticky="w", padx=4, pady=1)
            mv = tk.StringVar(value=names.get(z.get("rezim", "off"), "vypnuto"))
            ttk.Combobox(f, textvariable=mv, values=list(names.values()), state="readonly", width=14).grid(
                row=r, column=1, padx=4)
            b = tk.Button(f, text="barva", width=6, relief="groove", bg=z.get("barva", "#ffffff"),
                          fg=_contrast(z.get("barva", "#ffffff")))
            b.grid(row=r, column=2, padx=4)
            b.config(command=lambda z=z, b=b: self._pick_zone(z, b))
            sv = tk.StringVar(value=led.FUSION_SPEEDS.get(z.get("rychlost", "normal"), "normálně"))
            ttk.Combobox(f, textvariable=sv, values=list(led.FUSION_SPEEDS.values()), state="readonly",
                         width=12).grid(row=r, column=3, padx=4)
            sv.trace_add("write", lambda *a, z=z, sv=sv: z.__setitem__("rychlost", rev_speed[sv.get()]))
            mv.trace_add("write", lambda *a, z=z, mv=mv: z.__setitem__("rezim", rev_names[mv.get()]))
            r += 1

    def _pick_zone(self, z, b):
        col = colorchooser.askcolor(color=z.get("barva", "#ffffff"), parent=self.hw)[1]
        if col:
            z["barva"] = col
            b.config(bg=col, fg=_contrast(col))

    # ---------------------------------------------------------------- nahled
    def _animate(self):
        try:
            if not self.preview.winfo_exists():
                return
        except tk.TclError:
            return
        now = time.monotonic()
        dt, self._prev = now - self._prev, now
        c = self.preview
        c.delete("all")
        lc = self.lcfg
        if not lc.get("zapnuto", True):
            c.create_text(210, 85, text="Řízení LED vypnuto", fill="#888")
        else:
            frame = led.render(self.engine, lc, now - self.t0, self.app.data, min(dt, 0.2))
            items = [(k, v) for k, v in frame.items()]
            n_items = len(items)
            for idx, (key, cols) in enumerate(items):
                cx = 70 + idx * (280 / max(1, n_items - 1)) if n_items > 1 else 210
                cy = 78
                n = len(cols)
                R = 50
                dot = 7 if n <= 8 else 5
                c.create_oval(cx - R - 12, cy - R - 12, cx + R + 12, cy + R + 12, outline="#333", width=2)
                for i, rgb in enumerate(cols):
                    a = math.radians(360 * i / n)
                    x, y = cx + R * math.cos(a), cy + R * math.sin(a)
                    # LED sviti vic, nez stejna hodnota na monitoru -> pro nahled zesvetlit (gama)
                    r, g, b = (round(255 * (v / 255) ** 0.5) for v in rgb)
                    c.create_oval(x - dot, y - dot, x + dot, y + dot, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
                label = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "deska (3×)",
                         "D_LED2": "D_LED2"}.get(key, key)
                c.create_text(cx, cy, text=label, fill="#999", font=("Segoe UI", 8))
        self.preview.after(PREVIEW_MS, self._animate)

    # ---------------------------------------------------------------- stav
    def refresh(self):
        st = getattr(self.app, "lstate", None) or {}
        s = st.get("stav")
        if not self.app.running:
            text, color = "Aplikace neběží – LED se nastaví po jejím spuštění.", "#666"
        elif s in ("běží", "nastaveno"):
            text, color = "LED běží.", "#2a7"
        elif s == "chyba":
            text, color = "Chyba: " + "; ".join(st.get("chyby", [])), "#c33"
        elif s == "vypnuto":
            text, color = "Řízení LED vypnuto – LED zůstávají, jak jsou.", "#666"
        else:
            text, color = "Stav LED uvidíš, až poběží aplikace (nová verze).", "#666"
        self.status.config(text=text, foreground=color)
