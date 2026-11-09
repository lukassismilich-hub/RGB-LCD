# editor_klavesnice.py - stranka Klavesnice v okne nastaveni (Logitech G815)
#   - Nahled a stav: klavesnice po klavesach (klavesnice_rozlozeni.KEYS) v barvach, ktere pocita
#     zivy nahled LED (LedEditor._animate -> preview()); stav rizeni z bezici aplikace. Klik na klavesu
#     = vyber klaves (vlastni barvy klaves), jinak ukazkovy stisk (reakce na stisk).
#   - Efekt: vlastni plosny efekt klavesnice (klavesnice_efekty, skupiny GROUPS) nebo jedna barva
#     jako F140 / jako deska; parametry efektu, malovani klaves, reakce na stisk, jas
#   - Casti klavesnice (vrstvy, config["led"]["vrstvy_klavesnice"]): vlastni efekt na vybranych klavesach
#     pres zaklad; "Upravuji" prepina, ceho se tyka vyber efektu (self.target), klik na klavesu = do casti
#   - Klavesy G1-G5 (config["led"]["klavesy_g"], klavesy_g.py): akce (predvolba, hudba, styl hudby, playlist,
#     skladba na LCD) a osvetleni kazde G-klavesy; sady M1-M3 (sady_klavesnice.json - uklada se hned)
#   - Predvolba G: "Nastavuji" v karte Podsviceni (self.preset) prepne celou kartu (efekt, casti, jas)
#     na nastaveni predvolby (self.src) - nahled pak ukazuje predvolbu (preview_preset)
#   - Integrovana pamet: stav (cte se kazde 3 s, kdyz je stranka videt), zaloha. Pamet prepina
#     vlakno LED samo podle "Ridit podsviceni z aplikace" (klavesnice.Direct).
# Zmeny se projevi po Ulozit (config["led"]["klavesnice"], ["efekt_klavesnice"]).

import os
import random
import threading
import tkinter as tk
from tkinter import colorchooser, ttk

import klavesnice_efekty as kbfx
import klavesnice_rozlozeni as R
import klavesy_g
import led
import vzhled as V

POLL_MS = 3000               # stav integrovane pameti (prepina ji vlakno LED v bezici aplikaci)
DEMO_MS = 700                # ukazkove stisky v nahledu, kdyz je zapnuta reakce
WRAP = 620
BODY_W = 760                 # sirka karet (sirsi okno je nenatahuje)
U = 27                       # sirka klavesy 1u v nahledu (px)
PAD = 8
KB_W, KB_H = int(R.WIDTH * U) + 2 * PAD, int(R.HEIGHT * U) + 2 * PAD
KEY_DEFAULT = {"zapnuto": False, "efekt": "vlastni", "jas": 100, "barva": "#ffffff"}
# popisek posuvniku "sirka" podle efektu
WIDTH_LABEL = {"vlna": "Délka vlny", "kruh": "Šířka kruhů", "toceni": "Zkroucení", "skener": "Šířka",
               "dest": "Hustota", "trpyt": "Hustota", "ohnostroj": "Četnost", "plamen": "Výška plamene"}
KEEP = ("reakce", "reakce_barva", "reakce_doba", "klavesy", "zaklad")   # pri zmene efektu zustava


def fx_style(styl):
    import led_efekty
    return led_efekty.MUSIC_STYLES.get(styl, styl)


class KeyboardEditor:
    def __init__(self, parent, app):
        self.app = app
        self._job = None                          # bezici prace s klavesnici (vlakno) a jeji vysledek
        self._mode = None                         # rezim pameti klavesnice (klavesnice.MODE_*)
        self._last = None                         # posledni barvy v nahledu
        self.sel = set()                          # vybrane klavesy (vlastni barvy klaves)
        self.target = None                        # upravovana cast klavesnice (index vrstvy), None = zaklad
        self.preset = None                        # upravovana predvolba (cislo G-klavesy), None = bezne podsviceni
        self.layer_lbl = None
        self.items = {}
        self.sel_lbl = None
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.scroll = V.ScrollFrame(parent)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        body = self.scroll.inner
        body.columnconfigure(0, weight=0, minsize=BODY_W)
        self.top = V.card(body)
        self.top.grid(row=0, column=0, sticky="ew")
        self.light = V.card(body)
        self.light.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        self.react = V.card(body)
        self.react.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.gcard = V.card(body)
        self.gcard.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.mcard = V.card(body)
        self.mcard.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        self.mem = V.card(body)
        self.mem.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        self._build_top()
        self._build_light()
        self._build_g()
        self._build_m()
        self._build_mem()
        self.refresh()
        self._run(self._read_mode)
        self.mem.after(POLL_MS, self._tick)
        self.top.after(DEMO_MS, self._demo)

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    @property
    def kc(self):
        return self.lcfg.setdefault("klavesnice", dict(KEY_DEFAULT))

    def preset_cfg(self):
        """Upravovana predvolba G (nastaveni akce), nebo None = bezne podsviceni."""
        if self.preset is not None:
            a = self.gcfg.get(str(self.preset))
            if isinstance(a, dict) and klavesy_g.has_keyboard(a):
                return a
        self.preset = None
        return None

    @property
    def src(self):
        """Co upravuje karta Podsviceni: config["led"], nebo nastaveni predvolby G."""
        a = self.preset_cfg()
        return self.lcfg if a is None else klavesy_g.ensure_keyboard(a, self.lcfg)

    @property
    def ekc(self):
        """Efekt a jas klavesnice, ktere karta upravuje (bezne / predvolba)."""
        return self.kc if self.preset_cfg() is None else self.src["klavesnice"]

    def view_cfg(self):
        """Nastaveni, ktere ukazuje nahled (s upravovanou predvolbou)."""
        a = self.preset_cfg()
        return self.lcfg if a is None else klavesy_g.overlay(self.lcfg, a)

    def preview_preset(self):
        """Cislo predvolby pro zivy nahled LED - jen kdyz je stranka Klavesnice videt."""
        try:
            if self.preset_cfg() is None or not self.top.winfo_ismapped():
                return None
        except tk.TclError:
            return None
        return self.preset

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
        return self.ekc.get("efekt", "deska") == "vlastni"

    def painting(self):
        return self.layer() is None and self.own() and self.eff.get("typ") == "vlastni"

    def reacting(self):
        """Ma nektery efekt klavesnice (zaklad nebo cast) reakci na stisk?"""
        lc = self.view_cfg()
        lc = dict(lc, klavesnice=dict(lc.get("klavesnice") or {}, zapnuto=True))
        return any(e.get("reakce") for e in led.kb_effects(lc))

    # ------------------------------------------------------------ nahled a stav
    def _build_top(self):
        f = self.top
        f.columnconfigure(0, weight=1)
        V.card_title(f, "Klávesnice Logitech G815").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        self.status = ttk.Label(f, font=V.FONT_B, wraplength=WRAP, justify="left")
        self.status.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))
        c = self.canvas = tk.Canvas(f, width=KB_W, height=KB_H, bg=V.CARD, highlightthickness=0)
        c.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 6))
        c.create_rectangle(1, 1, KB_W - 1, KB_H - 1, outline="#262b33", fill="#111418")
        for z, _name, x, y, w, h in R.KEYS:
            x0, y0 = PAD + x * U + 2, PAD + y * U + 2
            self.items[z] = c.create_rectangle(x0, y0, x0 + w * U - 4, y0 + h * U - 4, fill="#1c2128",
                                               outline="#2a3038", width=1, tags=("key", f"z{z}"))
        self.empty_txt = c.create_text(KB_W / 2, KB_H / 2 + U, fill=V.MUTED, font=V.FONT_B, text="")
        c.tag_bind("key", "<Button-1>", self._on_key)
        self.hint = ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left")
        self.hint.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 14))

    def _on_key(self, _event):
        hit = self.canvas.find_withtag("current")
        z = next((int(t[1:]) for t in (self.canvas.gettags(hit[0]) if hit else ()) if t[:1] == "z"), None)
        if z is None:
            return
        lay = self.layer()
        if lay is not None:                       # klavesa do casti / z casti
            lay["klavesy"] = sorted(set(kbfx.part_zones(lay)) ^ {z})
            self._show_sel()
            self._layer_info()
        elif self.painting():
            self.sel ^= {z}
            self._show_sel()
            self._sel_info()
        else:                                     # ukazkovy stisk (reakce)
            kbfx.engine_for(self.app.leds.engine).press(z)

    def _show_sel(self):
        lay = self.layer()
        marked = set(kbfx.part_zones(lay)) if lay is not None else self.sel
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
        if g and (g.get("sada") or g.get("aktivni")):
            text += (" – teď platí " + self._now_text(g) + " (uložení změn v okně ji vypne, nebo znovu stiskni "
                     "tu klávesu)")
        self.status.config(text=text + ".", foreground=color)
        self._g_status(st, saved)
        pre = f"Náhled ukazuje předvolbu G{self.preset}. " if self.preset_cfg() is not None else ""
        if not self.kc.get("zapnuto"):
            hint = "Náhled ukáže efekt, až zapneš řízení podsvícení z aplikace."
        elif self.layer() is not None:
            hint = "Klik na klávesu = přidat do části / odebrat z ní (klávesy části mají bílý rámeček)."
        elif self.painting():
            hint = "Klik na klávesu = vybrat / zrušit výběr; vybrané klávesy obarvíš níže."
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
        if self.preset is not None:
            self._build_g()                       # popis predvolby u G-klavesy
        self._show_sel()
        self.refresh()

    def _build_light(self):
        for w in self.light.winfo_children() + self.react.winfo_children():
            w.destroy()
        self.sel_lbl = None
        f = self.light
        kc = self.kc
        pa = self.preset_cfg()
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Podsvícení" if pa is None else f"Podsvícení – předvolba G{self.preset}").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 6))
        on = tk.BooleanVar(value=bool(kc.get("zapnuto")))

        def on_toggle():
            kc["zapnuto"] = on.get()
            self._rebuild()
            self._show_mode()
        ttk.Checkbutton(f, text="Řídit podsvícení klávesnice z aplikace", variable=on,
                        command=on_toggle).grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 4))
        self.react.grid_remove()
        if not kc.get("zapnuto"):
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                      text="Klávesnice svítí podle profilu v integrované paměti. Po zapnutí aplikace paměť sama "
                           "vypne a podsvícení počítá po jednotlivých klávesách.").grid(
                row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 16))
            self._refit()
            return
        self._preset_row(f, 2)
        ek = self.ekc
        ttk.Label(f, text="Jas", style="Muted.TLabel").grid(row=4, column=0, sticky="w", padx=(20, 10), pady=4)
        jv = tk.IntVar(value=int(ek.get("jas", kc.get("jas", 100))))
        jl = ttk.Label(f, width=5, text=f"{jv.get()} %", font=V.MONO, anchor="e")
        jl.grid(row=4, column=2, sticky="e", padx=(8, 20))

        def on_jas(_e=None):
            ek["jas"] = int(jv.get())
            jl.config(text=f"{int(jv.get())} %")
        V.scale(f, variable=jv, from_=10, to=100, resolution=5, length=200, command=on_jas).grid(
            row=4, column=1, sticky="w", pady=4)
        ttk.Label(f, text="Efekt", style="Muted.TLabel").grid(row=5, column=0, sticky="w", padx=(20, 10), pady=4)
        src = tk.StringVar(value=ek.get("efekt", "vlastni"))

        def on_src():
            ek["efekt"] = src.get()
            self._rebuild()
        V.segmented(f, src, [("vlastni", "efekt klávesnice"), ("f140", "jako F140"), ("deska", "jako deska")],
                    command=on_src).grid(row=5, column=1, columnspan=2, sticky="w", pady=4)
        self._parts_row(f, 6)
        lay = self.layer()
        if lay is not None:
            lf = ttk.Frame(f)
            lf.grid(row=7, column=0, columnspan=3, sticky="ew", padx=20, pady=(6, 0))
            self._layer_controls(lf, lay)
        elif not self.own():
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                      text="Celá klávesnice jednou barvou – efekt se počítá jako pro jeden ventilátor "
                           f"({'F140' if ek.get('efekt') == 'f140' else 'ventilátory na desce'}, nastavení na "
                           "stránce LED ventilátorů). Části klávesnice můžou mít i tak vlastní efekt.").grid(
                row=7, column=0, columnspan=3, sticky="w", padx=20, pady=(4, 16))
            self._refit()
            return
        pf = ttk.Frame(f)
        pf.grid(row=8, column=0, columnspan=3, sticky="ew", padx=20, pady=(6, 16))
        self._effect_chooser(pf, exclude=("vlastni",) if lay is not None else ())
        self.react.grid()
        self._build_react()
        self._refit()

    # ------------------------------------------------------------ predvolby G (co karta upravuje)
    def _preset_row(self, f, row):
        """Nastavuji: bezne podsviceni / predvolba Gn (radek row, pod nim popis predvolby v row + 1)."""
        keys = [n for n in klavesy_g.KEYS if klavesy_g.has_keyboard(self.gcfg.get(str(n)))]
        if not keys:
            return
        ttk.Label(f, text="Nastavuji", style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 10),
                                                                  pady=4)
        pv = tk.StringVar(value="" if self.preset_cfg() is None else str(self.preset))

        def on_p():
            self.preset = int(pv.get()) if pv.get() else None
            self.target = None
            self.sel.clear()
            self._rebuild()
        V.segmented(f, pv, [("", "běžné podsvícení")] + [(str(n), f"předvolba G{n}") for n in keys],
                    command=on_p, style="SegSmall.Toolbutton").grid(row=row, column=1, columnspan=2, sticky="w",
                                                                   pady=4)
        if self.preset_cfg() is None:
            return
        bf = ttk.Frame(f)
        bf.grid(row=row + 1, column=0, columnspan=3, sticky="ew", padx=20, pady=(2, 6))
        bf.columnconfigure(0, weight=1)
        ttk.Label(bf, style="Small.TLabel", wraplength=WRAP - 160, justify="left", foreground=V.ACCENT, text=(
            f"Takhle bude klávesnice svítit po stisku G{self.preset} (stejná klávesa znovu = zpět). Běžné "
            "podsvícení ani sady M1–M3 se tím nemění. Náhled ukazuje předvolbu; na klávesnici platí po Uložit.")
        ).grid(row=0, column=0, sticky="w")

        def copy_base():
            a = self.preset_cfg()
            snap = a.get("nastaveni") or {}
            for k in ("efekt_klavesnice", "vrstvy_klavesnice", "klavesnice"):
                snap.pop(k, None)
            klavesy_g.ensure_keyboard(a, self.lcfg)
            self.target = None
            self._rebuild()

        def done():
            self.preset = self.target = None
            self._rebuild()
        ttk.Button(bf, text="Zkopírovat běžné", command=copy_base).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Button(bf, text="Hotovo", command=done).grid(row=0, column=2, sticky="e", padx=(6, 0))

    def edit_preset(self, n):
        """Karta Podsviceni na predvolbu Gn (tlacitko Upravit u G-klavesy)."""
        self.preset, self.target = n, None
        self.sel.clear()
        self._rebuild()
        try:
            self.scroll.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ casti klavesnice (vrstvy)
    def _parts_row(self, f, row):
        ttk.Label(f, text="Upravuji", style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 10),
                                                                 pady=4)
        fr = ttk.Frame(f)
        fr.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
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
        ttk.Separator(f).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

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
            chips.columnconfigure(c, weight=1, uniform="chip")
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
        if "duha" in names:
            dv = tk.BooleanVar(value=bool(kbfx.get(eff, "duha")))
            ttk.Checkbutton(f, text="Plná duha místo barev", variable=dv,
                            command=lambda: eff.__setitem__("duha", dv.get())).grid(row=row, column=1, sticky="w")
            row += 1
        if "barvy_hudba" in names:
            self._label(f, row, "Barvy z")
            hv = tk.StringVar(value=kbfx.get(eff, "barvy_hudba"))
            V.segmented(f, hv, [("obal", "obalu alba"), ("vlastni", "výběru výše")],
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
        if "rychlost" in names:
            self._slider(f, row, "Rychlost", eff, "rychlost", 1, 10)
            row += 1
        if "sirka" in names:
            self._slider(f, row, WIDTH_LABEL.get(typ, "Šířka"), eff, "sirka", 1, 10)
            row += 1
        if "opacne" in names:
            ov = tk.BooleanVar(value=bool(kbfx.get(eff, "opacne")))
            ttk.Checkbutton(f, text="Dovnitř" if typ == "kruh" else "Opačný směr", variable=ov,
                            command=lambda: eff.__setitem__("opacne", ov.get())).grid(row=row, column=1, sticky="w")
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
        if kbfx.info(typ)[1] == "hudba":
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP - 40, justify="left",
                      text="Reaguje na hudbu ze Spotify (zvuk zachytává jen Spotify). V náhledu je simulovaná "
                           "hudba; bez hudby svítí jen pozadí.").grid(row=row, column=0, columnspan=2, sticky="w",
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

    # ------------------------------------------------------------ reakce na stisk
    def _build_react(self):
        f = self.react
        eff = self.eff
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Reakce na stisk kláves").grid(row=0, column=0, columnspan=2, sticky="w", padx=20,
                                                       pady=(14, 6))
        rv = tk.StringVar(value=eff.get("reakce", ""))

        def on_r():
            eff["reakce"] = rv.get()
            self._build_react_rest()
            self.refresh()
        V.segmented(f, rv, kbfx.REACTIONS, command=on_r).grid(row=1, column=0, columnspan=2, sticky="w", padx=20,
                                                              pady=4)
        self.react_rest = ttk.Frame(f)
        self.react_rest.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                  text="Funguje s každým efektem. Aplikace pozná jen to, která klávesa se stiskla – nic "
                       "neukládá a sledování běží, jen když je reakce zapnutá. Logo, jas a G1–G5 se nehlásí.").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=20, pady=(6, 16))
        self._build_react_rest()

    def _build_react_rest(self):
        f = self.react_rest
        for w in f.winfo_children():
            w.destroy()
        eff = self.eff
        if not eff.get("reakce"):
            self._refit()
            return
        f.columnconfigure(1, weight=1)
        self._label(f, 0, "Barva")
        cf = ttk.Frame(f)
        cf.grid(row=0, column=1, sticky="w", pady=4)
        rainbow = tk.BooleanVar(value=eff.get("reakce_barva") == "duha")
        col = eff.get("reakce_barva", "#ffffff")
        state = {"col": col if col != "duha" else "#ffffff"}

        def pick():
            c = colorchooser.askcolor(color=state["col"], parent=self.react)[1]
            if c:
                state["col"] = c
                eff["reakce_barva"] = c
                rainbow.set(False)
                V.set_swatch(b, c)
        b = V.swatch(cf, state["col"], pick)
        b.pack(side="left")

        def on_rb():
            eff["reakce_barva"] = "duha" if rainbow.get() else state["col"]
        ttk.Checkbutton(cf, text="každý stisk jinou barvou duhy", variable=rainbow, command=on_rb).pack(
            side="left", padx=(12, 0))
        self._slider(f, 1, "Doba dohasnutí", eff, "reakce_doba", 0.2, 3.0, 0.1, "{:.1f} s")
        self._refit()

    def _refit(self):
        def fit():
            try:
                self.scroll.inner.update_idletasks()
                self.scroll._fit()
            except tk.TclError:
                pass
        self.scroll.after_idle(fit)

    # ------------------------------------------------------------ klavesy G1-G5
    @property
    def gcfg(self):
        g = self.lcfg.get("klavesy_g")
        if not isinstance(g, dict):
            g = self.lcfg["klavesy_g"] = {}
        return g

    def _build_g(self):
        f = self.gcard
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(2, weight=1)
        V.card_title(f, "Klávesy G1–G5").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(14, 2))
        self.g_lbl = ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left")
        self.g_lbl.grid(row=1, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 8))
        names = [t for _k, t in klavesy_g.ACTIONS]
        tnames = [t for _k, t in klavesy_g.TARGETS]
        notes = {"hudba": "vizualizér LED ze Spotify zapne / vypne",
                 "styl": "další styl vizualizéru (vypnutý vizualizér nejdřív zapne)",
                 "pl_dalsi": "playlist LED ventilátorů skočí na další efekt",
                 "pl_predchozi": "playlist LED ventilátorů skočí na předchozí efekt",
                 "playlist": "přepíná playlist LED ventilátorů / jeden efekt",
                 "lcd": "obrazovka Právě hraje (název, obal) na dobu z nastavení LCD, znovu = schovat"}
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
                else:
                    self.gcfg.pop(str(n), None)
                self._build_g()
                self._build_light()
                self._refit()
            cb.bind("<<ComboboxSelected>>", on_a)
            if kind == "predvolba":
                tf = ttk.Frame(f)
                tf.grid(row=row, column=2, columnspan=2, sticky="w", padx=(10, 20), pady=(10, 0))
                tv = tk.StringVar(value=dict(klavesy_g.TARGETS).get(a.get("cil", "klavesnice"), tnames[0]))
                tc = ttk.Combobox(tf, textvariable=tv, values=tnames, width=20, state="readonly")
                tc.pack(side="left")

                def on_t(_e=None, n=n, tv=tv):
                    a = self.gcfg[str(n)]
                    a["cil"] = next(k for k, t in klavesy_g.TARGETS if t == tv.get())
                    if klavesy_g.has_fans(a) and not any(k in (a.get("nastaveni") or {})
                                                         for k in klavesy_g.PARTS["ventilatory"][0]):
                        klavesy_g.take_fans(a, self.lcfg)    # zacatek: ventilatory jak jsou ted
                    self._build_g()
                    self._build_light()
                tc.bind("<<ComboboxSelected>>", on_t)
                if klavesy_g.has_keyboard(a):
                    editing = self.preset_cfg() is a
                    eb = ttk.Button(tf, text="Upravuje se nahoře" if editing else "Upravit klávesnici",
                                    command=lambda n=n: self.edit_preset(n))
                    eb.pack(side="left", padx=(8, 0))
                    if editing:
                        eb.state(["disabled"])
                if klavesy_g.has_fans(a):
                    def fans(n=n):
                        klavesy_g.take_fans(self.gcfg[str(n)], self.lcfg)
                        self._build_g()
                    ttk.Button(tf, text="Převzít ventilátory ze stránky LED", command=fans).pack(
                        side="left", padx=(6, 0))
                row += 1
                ttk.Label(f, style="Small.TLabel", text=klavesy_g.describe(a), wraplength=WRAP - 60,
                          justify="left").grid(row=row, column=1, columnspan=3, sticky="w", pady=(2, 0))
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
            "Předvolba = dočasně jiné podsvícení: „Upravit klávesnici“ přepne kartu Podsvícení nahoře na "
            "předvolbu (efekt, části, jas – náhled ji ukazuje), ventilátory se převezmou tak, jak jsou nastavené na "
            "stránce LED. Stisk G-klávesy přepne na předvolbu, stejná G-klávesa znovu vrátí předchozí (běžné "
            "nebo sadu M). Po startu aplikace a po uložení změn v okně platí nastavení z okna. Osvětlení: "
            "kontrolka = barva podle toho, jestli je "
            "funkce zapnutá; podle efektu = klávesa svítí jako ostatní. Platí po Uložit. G1–G5 a M1–M3 ovládá "
            "aplikace, dokud řídí podsvícení – v G HUB je nech bez přiřazení nebo s nepoužívanou klávesou "
            "(F20–F24).")).grid(row=row, column=0, columnspan=4, sticky="w", padx=20, pady=(12, 16))

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
            text = "Teď: " + self._now_text(g) + "."
        if (saved.get("klavesy_g") or {}) != self.gcfg:
            text += " Změny G-kláves se projeví po Uložit."
        lbl.config(text=text)
        self._m_status(g)

    def _now_text(self, g):
        on = []
        if g.get("sada"):
            on.append(f"sada M{g['sada']}")
        if g.get("aktivni"):
            on.append(f"předvolba G{g['aktivni']}")
        if g.get("hudba") is not None:
            on.append("hudba " + ("zapnutá" if g["hudba"] else "vypnutá"))
        if g.get("styl"):
            on.append("styl hudby: " + fx_style(g["styl"]))
        if g.get("playlist") is not None:
            on.append("playlist " + ("zapnutý" if g["playlist"] else "vypnutý"))
        if g.get("uklada"):
            on.append("MR – čeká na M1–M3")
        return ", ".join(on) if on else "nastavení z okna"

    # ------------------------------------------------------------ sady M1-M3
    def _build_m(self):
        f = self.mcard
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Sady M1–M3").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 2))
        self.m_lbl = ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left")
        self.m_lbl.grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 8))
        sets = klavesy_g.load_sets()
        self._m_seen = dict(sets)
        row = 2
        for n in klavesy_g.M_KEYS:
            s_ = sets.get(n)
            ttk.Label(f, text=f"M{n}", style="Bold.TLabel").grid(row=row, column=0, sticky="nw", padx=(20, 10),
                                                                 pady=(8, 0))
            ttk.Label(f, text=klavesy_g.describe_set(s_), wraplength=430, justify="left").grid(
                row=row, column=1, sticky="w", pady=(8, 0))
            bf = ttk.Frame(f)
            bf.grid(row=row, column=2, sticky="e", padx=(10, 20), pady=(8, 0))

            def store(n=n):
                klavesy_g.save_set(n, self.lcfg)
                self._build_m()

            def load(n=n):
                klavesy_g.load(self.lcfg, klavesy_g.set_preset(klavesy_g.load_sets().get(n)))
                self.app.reload_with(self.app.cfg)

            def delete(n=n):
                klavesy_g.delete_set(n)
                self._build_m()
            ttk.Button(bf, text="Uložit současné", command=store).pack(side="left")
            for text, fn in (("Načíst do okna", load), ("Smazat", delete)):
                b = ttk.Button(bf, text=text, command=fn)
                b.pack(side="left", padx=(6, 0))
                if s_ is None:
                    b.state(["disabled"])
            row += 1
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Sada = celé nastavení klávesnice: efekt, části klávesnice, jas a akce i osvětlení G1–G5. "
            "M1 vyvolá sadu, stejná M znovu vrátí nastavení z okna (svítí kontrolka aktivní M). Uložení přímo "
            "z klávesnice: MR a pak M1–M3 do 10 s uloží, jak klávesnice právě svítí (MR znovu = zrušit; při "
            "ukládání blikají kontrolky M). „Uložit současné“ tady ukládá nastavení z okna hned, bez Uložit.")
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=20, pady=(12, 16))

    def _m_status(self, g):
        lbl = getattr(self, "m_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        if klavesy_g.load_sets() != getattr(self, "_m_seen", None):
            self._build_m()                       # sadu ulozila bezici aplikace (MR + M)
            self._refit()
            return
        if g is None:
            lbl.config(text="")
        elif g.get("uklada"):
            lbl.config(text="Ukládání (MR): stiskni M1, M2 nebo M3.")
        else:
            lbl.config(text=f"Teď: sada M{g['sada']}." if g.get("sada") else "Teď: nastavení z okna.")

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
                                                                   padx=20, pady=(4, 16))

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
