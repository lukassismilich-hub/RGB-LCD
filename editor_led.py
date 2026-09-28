# editor_led.py - stranka LED v okne nastaveni
#   - jas vsech ventilatoru + vyrovnani F140 / ventilatory na desce
#   - efekt pro vsechny ventilatory (nebo zvlast F140 a deska), rychlost, smer, barvy, vlna
#   - vlastni barvy LED (kruh 8 / 16 LED) - pro efekt "vlastni barvy LED" a klidny stav po ukonceni
#   - natoceni ventilatoru (posun LED 1, obraceny smer) - aby se efekt na vsech tocil stejne
#   - zivy animovany nahled (stejny vypocet jako ve vlakne LED)
#   - sbalene: ARGB hlavicky (pocet LED, D_LED2) a ostatni zony desky
# Zmeny se na ventilatorech projevi po Ulozit.

import math
import time
import tkinter as tk
from tkinter import colorchooser, ttk

import led
import led_efekty as fx
import vzhled as V

PREVIEW_MS = 40
PREVIEW_W, PREVIEW_H = 470, 180
_contrast = V.contrast


class LedEditor:
    def __init__(self, parent, app):
        self.app = app
        self.engine = fx.Engine(seed=7)
        self.t0 = time.monotonic()
        self._prev = self.t0
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)

        top = V.card(parent)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        v = tk.BooleanVar(value=self.lcfg.get("zapnuto", True))
        ttk.Checkbutton(top, text="Řídit LED z aplikace", variable=v,
                        command=lambda: self.lcfg.__setitem__("zapnuto", v.get())).pack(
            side="left", padx=16, pady=10)
        self.status = ttk.Label(top, font=V.FONT_B)
        self.status.pack(side="left", padx=16)

        left = tk.Frame(parent, bg=V.BG)
        left.grid(row=1, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        right = tk.Frame(parent, bg=V.BG)
        right.grid(row=1, column=1, sticky="n", padx=(16, 0))

        self._build_brightness(left)
        self.fx_frame = V.card(left)
        self.fx_frame.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        self._build_effects()

        pv = V.card(right)
        pv.pack(fill="x")
        V.card_title(pv, "Živý náhled").pack(anchor="w", padx=16, pady=(14, 6))
        self.preview = tk.Canvas(pv, width=PREVIEW_W, height=PREVIEW_H, bg=V.CARD, highlightthickness=0)
        self.preview.pack(padx=12)
        ttk.Label(pv, style="Small.TLabel", text="Náhled počítá efekt stejně jako aplikace, včetně jasu. "
                                                 "Na ventilátorech se změna projeví po Uložit.",
                  wraplength=PREVIEW_W).pack(anchor="w", padx=16, pady=(4, 14))
        self.sync = V.card(right)                          # natoceni hned pod nahledem
        self.sync.pack(fill="x", pady=(16, 0))
        self._build_sync()
        self.custom = V.card(right)
        self.custom.pack(fill="x", pady=(16, 0))
        self._build_custom()
        self.hw = V.card(right)
        self.hw.pack(fill="x", pady=(16, 0))
        self._build_hw()
        self.refresh()
        self._animate()

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    # ---------------------------------------------------------------- jas
    def _build_brightness(self, parent):
        f = V.card(parent)
        f.grid(row=0, column=0, sticky="ew")
        V.card_title(f, "Jas").grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 4))
        f.columnconfigure(1, weight=1)
        for row, (key, text, lo) in enumerate((("jas", "Všechny ventilátory", 0),
                                              ("jas_f140", "Vyrovnání F140", 20),
                                              ("jas_deska", "Vyrovnání desky", 20)), start=1):
            last = row == 3
            ttk.Label(f, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(16, 12),
                                                               pady=(4, 16 if last else 4))
            v = tk.IntVar(value=int(self.lcfg.get(key, 100 if key != "jas" else 80)))
            val = ttk.Label(f, width=5, text=f"{v.get()} %", font=V.MONO, anchor="e")
            val.grid(row=row, column=2, sticky="e", padx=(8, 16), pady=(4, 16 if last else 4))

            def on(_e=None, key=key, v=v, val=val):
                self.lcfg[key] = int(v.get())
                val.config(text=f"{int(v.get())} %")
            V.scale(f, variable=v, from_=lo, to=100, resolution=5, length=140, command=on).grid(
                row=row, column=1, sticky="ew", pady=(4, 16 if last else 4))

    # -------------------------------------------------------------- efekty
    def _build_effects(self):
        f = self.fx_frame
        for w in f.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("stejne_pro_vse", True))

        def on_same():
            self.lcfg["stejne_pro_vse"] = same.get()
            self._build_effects()
        head = ttk.Frame(f)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(14, 4))
        head.columnconfigure(0, weight=1)
        V.card_title(head, "Efekt").grid(row=0, column=0, sticky="w")
        V.segmented(head, same, [(True, "Stejný pro všechny"), (False, "Zvlášť F140 a deska")],
                    command=on_same).grid(row=0, column=1)
        wave = tk.BooleanVar(value=self.lcfg.get("vlna", False))
        wf = ttk.Frame(f)
        wf.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 6))
        ttk.Label(wf, text="Mezi ventilátory", style="Muted.TLabel").pack(side="left", padx=(0, 10))
        V.segmented(wf, wave, [(False, "Synchronně"), (True, "Vlna (posunutě)")],
                    command=lambda: self.lcfg.__setitem__("vlna", wave.get())).pack(side="left")
        if same.get():
            panels = [("efekt", None)]
        else:
            panels = [("efekt_f140", "F140"), ("efekt_deska", "Ventilátory na desce")]
        for col, (key, title) in enumerate(panels):
            f.columnconfigure(col, weight=1, uniform="fx")
            eff = self.lcfg.setdefault(key, dict(fx.DEFAULT_EFFECT))
            pf = ttk.Frame(f)
            one = len(panels) == 1
            pf.grid(row=2, column=col, columnspan=2 if one else 1, sticky="nsew",
                    padx=(20 if col == 0 else 8, 20 if one or col == 1 else 8), pady=(0, 16))
            if title:
                ttk.Label(pf, text=title, style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
            self._effect_panel(pf, eff, 3 if one else 2)

    def _effect_panel(self, f, eff, chip_cols=3):
        typ = eff.get("typ", "duha_toceni")
        _n, ncolors, has_speed, has_dir = fx.EFFECTS.get(typ, fx.EFFECTS["vypnuto"])
        tv = tk.StringVar(value=typ if typ in fx.EFFECTS else "vypnuto")
        chips = ttk.Frame(f)
        chips.grid(row=1, column=0, columnspan=2, sticky="ew")

        def on_typ():
            eff["typ"] = tv.get()
            self._build_effects()
        for i, (key, spec) in enumerate(fx.EFFECTS.items()):
            chips.columnconfigure(i % chip_cols, weight=1, uniform="chip")
            ttk.Radiobutton(chips, text=spec[0], value=key, variable=tv, command=on_typ,
                            style="Chip.Toolbutton").grid(row=i // chip_cols, column=i % chip_cols,
                                                          sticky="ew", padx=2, pady=2)
        ttk.Separator(f).grid(row=2, column=0, columnspan=2, sticky="ew", pady=12)
        f.columnconfigure(1, weight=1)
        row = 3
        if has_speed:
            ttk.Label(f, text="Rychlost", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            sv = tk.IntVar(value=int(eff.get("rychlost", 4)))
            V.scale(f, variable=sv, from_=1, to=10, length=180,
                    command=lambda _e: eff.__setitem__("rychlost", int(sv.get()))).grid(
                row=row, column=1, sticky="ew", padx=8)
            row += 1
        if has_dir:
            dv = tk.BooleanVar(value=bool(eff.get("opacny_smer")))
            ttk.Checkbutton(f, text="Opačný směr", variable=dv,
                            command=lambda: eff.__setitem__("opacny_smer", dv.get())).grid(
                row=row, column=1, sticky="w", padx=8)
            row += 1
        if ncolors:
            labels = {"kometa": ["kometa", "pozadí"], "trpyt": ["záblesky", "pozadí"],
                      "prechod": ["barva 1", "barva 2"], "teplota": ["studená", "střední", "horká"],
                      "dvojita_kometa": ["kometa 1", "kometa 2"], "policie": ["první", "druhá"],
                      "tep": ["barva"], "stroboskop": ["barva"]}.get(
                typ, [f"barva {i + 1}" for i in range(ncolors)])
            cols = eff.setdefault("barvy", list(fx.DEFAULT_EFFECT["barvy"]))
            while len(cols) < ncolors:
                cols.append("#ffffff")
            ttk.Label(f, text="Barvy", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            bf = ttk.Frame(f)
            bf.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            for i in range(ncolors):
                b = V.swatch(bf, cols[i], None, text=labels[i], width=8)
                b.config(command=lambda i=i, b=b: self._pick_list(cols, i, b))
                b.pack(side="left", padx=(0, 6), ipady=4)
            row += 1
        if typ == "teplota":
            ttk.Label(f, text="Senzor", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            sn = tk.StringVar(value=eff.get("senzor", "CPU (Tctl/Tdie)"))
            ttk.Combobox(f, textvariable=sn, values=self.app._sensor_names(), width=26).grid(
                row=row, column=1, sticky="w", padx=8, pady=4)
            sn.trace_add("write", lambda *a: eff.__setitem__("senzor", sn.get()))
            row += 1
            rf = ttk.Frame(f)
            rf.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            for key, text in (("min", "studená od"), ("max", "horká od")):
                ttk.Label(rf, text=text, style="Muted.TLabel").pack(side="left")
                v = tk.StringVar(value=str(eff.get(key, 40 if key == "min" else 90)))
                ttk.Entry(rf, textvariable=v, width=5, font=V.MONO).pack(side="left", padx=(4, 12))

                def on(*a, key=key, v=v):
                    try:
                        eff[key] = float(v.get().replace(",", "."))
                    except ValueError:
                        pass
                v.trace_add("write", on)
            row += 1
        if typ == "vlastni":
            ttk.Label(f, style="Small.TLabel", text="Barvy jednotlivých LED nastavíš vpravo ve Vlastních barvách.").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=4)

    def _pick_list(self, cols, i, b):
        c = colorchooser.askcolor(color=cols[i], parent=self.fx_frame)[1]
        if c:
            cols[i] = c
            V.set_swatch(b, c)

    # ------------------------------------------------------ vlastni barvy LED
    def _build_custom(self):
        f = self.custom
        for w in f.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("nzxt_stejne", True))

        def on_same():
            self.lcfg["nzxt_stejne"] = same.get()
            self._build_custom()
        V.card_title(f, "Vlastní barvy LED").grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=PREVIEW_W,
                  text="Pro efekt „vlastní barvy LED“ a klidný stav po ukončení aplikace. "
                       "Klik na LED = změna barvy.").grid(row=1, column=0, columnspan=3, sticky="w", padx=16)
        ttk.Checkbutton(f, text="Oba F140 stejně", variable=same, command=on_same).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=16, pady=(6, 0))
        rings = [("F140 (1)" if not same.get() else "F140", self.lcfg["nzxt"]["led1"], led.LEDS_PER_FAN,
                  "čelo PC ▸")]
        if not same.get():
            rings.append(("F140 (2)", self.lcfg["nzxt"]["led2"], led.LEDS_PER_FAN, "čelo PC ▸"))
        for name in led.ARGB_HEADERS:                      # kazda zapojena ARGB hlavicka desky zvlast
            h = self.lcfg["argb"].get(name, {})
            if h.get("pouzito", name == "D_LED1"):
                rings.append((f"Deska – {name}", h, max(1, min(led.ARGB_MAX_LEDS, int(h.get("pocet_led", 16)))),
                              None))
        for i, (title, ch, n, front) in enumerate(rings):   # po dvou do radku, at karta nezuzi levy sloupec
            row, col = 3 + i // 2, i % 2
            fr = ttk.Frame(f)
            fr.grid(row=row, column=col, sticky="nw", padx=(16 if col == 0 else 4, 4), pady=(6, 16))
            ttk.Label(fr, text=title, style="Bold.TLabel").pack(anchor="w")
            self._ring(fr, ch, n, front)

    def _ring(self, parent, ch, n, front):
        cols = (list(ch.get("barvy", [])) + led.rainbow(n))[:n]
        ch["barvy"] = cols
        size = 140
        dot = 11 if n <= 8 else 7
        c = tk.Canvas(parent, width=size, height=size, bg=V.FIELD, highlightthickness=1,
                      highlightbackground=V.CARD_LINE)
        c.pack(anchor="w")
        R = size / 2 - dot - 12
        cx = cy = size / 2
        for i, col in enumerate(cols):
            ang = math.radians(360 * i / n)
            x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            tag = f"l{i}"
            c.create_oval(x - dot, y - dot, x + dot, y + dot, fill=col, outline=V.LINE, tags=tag)
            c.create_text(x, y, text=str(i + 1), fill=_contrast(col), font=("Segoe UI", 6 if n > 8 else 7, "bold"),
                          tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._pick_led(ch, i))
        if front:
            c.create_text(size - 3, cy + dot + 10, text=front, fill=V.DIM, anchor="e", font=("Segoe UI", 7))
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
            ttk.Button(bf, text=text, command=cmd, width=5).pack(side="left", padx=(0, 3))

    def _pick_led(self, ch, i):
        col = colorchooser.askcolor(color=ch["barvy"][i], parent=self.custom)[1]
        if col:
            ch["barvy"][i] = col
            self._build_custom()

    def _set_used(self, h, used):
        h["pouzito"] = used
        self._build_custom()                                # kruhy barev a natoceni podle zapojenych hlavicek
        self._build_sync()

    # ------------------------------------------------ natoceni (synchronizace)
    def _build_sync(self):
        """Posun LED 1 a smer cislovani kazdeho ventilatoru - aby se efekt na vsech tocil stejne."""
        f = self.sync
        for w in f.winfo_children():
            w.destroy()
        V.card_title(f, "Natočení ventilátorů").grid(row=0, column=0, columnspan=4, sticky="w", padx=16,
                                                      pady=(14, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=PREVIEW_W, justify="left",
                  text="Když se efekt na skutečných ventilátorech točí posunutě nebo opačně: zvol efekt "
                       "„kometa“, pomalou rychlost a Synchronně, ulož a posouvej LED 1 / obracej směr, "
                       "dokud nejsou hlavy komet na všech ventilátorech na stejném místě a neběží stejným "
                       "směrem. Náhled natočení zohledňuje (LED 1 vpravo, číslování po směru hodin).").grid(
            row=1, column=0, columnspan=4, sticky="w", padx=16, pady=(2, 6))
        names = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "Deska – D_LED1", "D_LED2": "Deska – D_LED2"}
        for r, (key, n, _g, _c) in enumerate(led.targets(self.lcfg), start=2):
            if key.startswith("f140_"):
                ch = self.lcfg["nzxt"].setdefault("led" + key[-1], {})
            else:
                ch = self.lcfg["argb"].setdefault(key, {})
            last = r == 1 + len(led.targets(self.lcfg))
            pad = (2, 14 if last else 2)
            ttk.Label(f, text=names.get(key, key), style="Muted.TLabel").grid(row=r, column=0, sticky="w",
                                                                              padx=(16, 12), pady=pad)
            ttk.Label(f, text="posun LED", style="Small.TLabel").grid(row=r, column=1, sticky="e", pady=pad)
            sv = tk.StringVar(value=str(int(ch.get("posun", 0)) % n))
            ttk.Spinbox(f, textvariable=sv, from_=0, to=n - 1, width=4, wrap=True).grid(
                row=r, column=2, padx=(6, 12), pady=pad)

            def on_shift(*a, ch=ch, sv=sv, n=n):
                try:
                    ch["posun"] = int(sv.get()) % n
                except ValueError:
                    pass
            sv.trace_add("write", on_shift)
            rv = tk.BooleanVar(value=bool(ch.get("obracene", False)))
            ttk.Checkbutton(f, text="obrácený směr", variable=rv,
                            command=lambda ch=ch, rv=rv: ch.__setitem__("obracene", rv.get())).grid(
                row=r, column=3, sticky="w", padx=(0, 16), pady=pad)

    # -------------------------------------------------------------- hardware
    def _build_hw(self):
        f = self.hw
        show = tk.BooleanVar(value=False)
        inner = ttk.Frame(f)
        ttk.Checkbutton(f, text="Hardware – ARGB hlavičky a další zóny desky", variable=show,
                        command=lambda: inner.pack(anchor="w", padx=16, pady=(0, 14)) if show.get()
                        else inner.pack_forget()).pack(anchor="w", padx=16, pady=10)
        af = ttk.LabelFrame(inner, text="ARGB hlavičky desky")
        af.pack(anchor="w", fill="x", pady=4)
        for r, name in enumerate(led.ARGB_HEADERS):
            h = self.lcfg["argb"].setdefault(name, {"pocet_led": 16, "pouzito": False})
            used = tk.BooleanVar(value=h.get("pouzito", name == "D_LED1"))
            ttk.Checkbutton(af, text=f"{name} – {h.get('nazev', '')}", variable=used,
                            command=lambda h=h, used=used: self._set_used(h, used.get())).grid(
                row=r, column=0, sticky="w", padx=4, pady=2)
            ttk.Label(af, text="počet LED", style="Muted.TLabel").grid(row=r, column=1, padx=(10, 4))
            pv = tk.StringVar(value=str(h.get("pocet_led", 16)))
            ttk.Spinbox(af, textvariable=pv, from_=1, to=led.ARGB_MAX_LEDS, width=4).grid(row=r, column=2)

            def on_count(*a, h=h, pv=pv):
                try:
                    h["pocet_led"] = max(1, min(led.ARGB_MAX_LEDS, int(pv.get())))
                except ValueError:
                    pass
            pv.trace_add("write", on_count)
        ttk.Label(af, style="Small.TLabel", text="Nezaškrtnutá hlavička zůstane zhasnutá.").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 4))
        zf = ttk.LabelFrame(inner, text="Další zóny desky (malé LED, 12V RGB) – jen celá zóna")
        zf.pack(anchor="w", fill="x", pady=4)
        self._build_zones(zf)
        ttk.Label(inner, style="Small.TLabel", justify="left", text=(
            "LED desky jinak ovládá Gigabyte Control Center (GCC) – pokud běží,\n"
            "nastavení desky přepíše (autostart_zapnout.bat ho vypne).")).pack(anchor="w", pady=(4, 0))

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
            ttk.Label(f, text=zone, style="Muted.TLabel").grid(row=r, column=0, sticky="w", padx=4, pady=2)
            mv = tk.StringVar(value=names.get(z.get("rezim", "off"), "vypnuto"))
            ttk.Combobox(f, textvariable=mv, values=list(names.values()), state="readonly", width=14).grid(
                row=r, column=1, padx=4, pady=2)
            b = V.swatch(f, z.get("barva", "#ffffff"), None, text="barva", width=6)
            b.grid(row=r, column=2, padx=4, ipady=2)
            b.config(command=lambda z=z, b=b: self._pick_zone(z, b))
            sv = tk.StringVar(value=led.FUSION_SPEEDS.get(z.get("rychlost", "normal"), "normálně"))
            ttk.Combobox(f, textvariable=sv, values=list(led.FUSION_SPEEDS.values()), state="readonly",
                         width=12).grid(row=r, column=3, padx=4, pady=2)
            sv.trace_add("write", lambda *a, z=z, sv=sv: z.__setitem__("rychlost", rev_speed[sv.get()]))
            mv.trace_add("write", lambda *a, z=z, mv=mv: z.__setitem__("rezim", rev_names[mv.get()]))
            r += 1

    def _pick_zone(self, z, b):
        col = colorchooser.askcolor(color=z.get("barva", "#ffffff"), parent=self.hw)[1]
        if col:
            z["barva"] = col
            V.set_swatch(b, col)

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
            c.create_text(PREVIEW_W / 2, PREVIEW_H / 2, text="Řízení LED vypnuto", fill=V.MUTED)
        else:
            # vcetne natoceni - LED v poradi, jak je aplikace posila (LED 1 vpravo, po smeru hodin)
            frame = led.render(self.engine, lc, now - self.t0, self.app.data, min(dt, 0.2))
            items = [(k, v) for k, v in frame.items()]
            n_items = len(items)
            cell = PREVIEW_W / max(1, n_items)                  # 3-4 ventilatory vedle sebe
            for idx, (key, cols) in enumerate(items):
                cx = cell * (idx + 0.5)
                cy = PREVIEW_H / 2
                n = len(cols)
                R = min(50, cell / 2 - 20)
                dot = 7 if n <= 8 else 5
                c.create_rectangle(cx - R - 18, cy - R - 18, cx + R + 18, cy + R + 18, outline="#262b33",
                                   fill="#111418")
                c.create_oval(cx - R - 8, cy - R - 8, cx + R + 8, cy + R + 8, outline="#1d2228", width=10)
                for i, rgb in enumerate(cols):
                    a = math.radians(360 * i / n)
                    x, y = cx + R * math.cos(a), cy + R * math.sin(a)
                    # LED sviti vic, nez stejna hodnota na monitoru -> pro nahled zesvetlit (gama)
                    r, g, b = (round(255 * (v / 255) ** 0.5) for v in rgb)
                    c.create_oval(x - dot, y - dot, x + dot, y + dot, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
                label = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "D_LED1",
                         "D_LED2": "D_LED2"}.get(key, key)
                c.create_text(cx, cy, text=label, fill=V.MUTED, font=("Segoe UI", 8))
        self.preview.after(PREVIEW_MS, self._animate)

    # ---------------------------------------------------------------- stav
    def refresh(self):
        st = getattr(self.app, "lstate", None) or {}
        s = st.get("stav")
        if not self.app.running:
            text, color = "Aplikace neběží – LED se nastaví po jejím spuštění.", V.MUTED
        elif s in ("běží", "nastaveno"):
            text, color = "● LED běží", V.OK
        elif s == "chyba":
            text, color = "Chyba: " + "; ".join(st.get("chyby", [])), V.ERR
        elif s == "vypnuto":
            text, color = "Řízení LED vypnuto – LED zůstávají, jak jsou.", V.MUTED
        else:
            text, color = "Stav LED uvidíš, až poběží aplikace (nová verze).", V.MUTED
        self.status.config(text=text, foreground=color)
