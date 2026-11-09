# editor_led.py - stranka LED v okne nastaveni
#   pevne nahore: rizeni LED z aplikace, stav, hlavni jas; vpravo zivy nahled (neroluje se)
#   zalozky (roluje se jen jejich obsah):
#   - Efekt: jeden efekt / playlist, stejny pro vse / zvlast F140 a deska, efekty ve skupinach
#     (FX_GROUPS), vlastni barvy LED (jen kdyz se efekt "vlastni barvy LED" pouziva)
#   - Hudba: vizualizer Spotify v blocich (zapnuti, styl, reakce, barvy)
#   - Synchronizace: synchronne / vlna, smer, F140 jako jeden, poradi vlny ve skrini
#   - Dalsi zarizeni: graficka karta RTX 5070, dalsi zony desky (klavesnice G815 ma vlastni stranku -
#     editor_klavesnice.py; barvu do jejiho nahledu posila _animate)
#   - Zapojeni: ARGB hlavicky, ktery F140 je vpredu, natoceni ventilatoru + test, vyrovnani jasu,
#     otoceni svislych efektu a hudby (spolecne pro vsechny efekty), klidny stav po ukonceni
# Zmeny se na ventilatorech projevi po Ulozit. Format config.json se nemeni.

import copy
import math
import os
import time
import tkinter as tk
from tkinter import colorchooser, ttk

import klavesy_g
import led
import led_efekty as fx
import vzhled as V

PREVIEW_MS = 40
PREVIEW_W, PREVIEW_H = 470, 180
WRAP = 450                    # zalomeni textu v kartach zalozek (sirka leveho sloupce)
PLAYLIST_ITEM_S = 20          # nova polozka playlistu trva asi tolik sekund (pocet opakovani podle delky)
_contrast = V.contrast

TABS = [("efekt", "Efekt"), ("hudba", "Hudba"), ("synchro", "Synchronizace"),
        ("zarizeni", "Další zařízení"), ("zapojeni", "⚙ Zapojení")]
# skupiny efektu v okne (jen vzhled stranky; efekt, ktery v zadne skupine neni, pujde do "Ostatni")
FX_GROUPS = [
    ("Klidné", ("vypnuto", "barva", "vlastni", "staticky_prechod", "prechod", "dychani", "duhove_dychani",
                "dychajici_paleta", "stridani", "tep")),
    ("Duha a palety", ("duha_toceni", "duha_prelevani", "plazma", "paleta", "vysece", "vlneni",
                       "polarni_zare", "stirani")),
    ("Pohyb", ("kometa", "dvojita_kometa", "divadlo", "odraz", "majak", "policie", "pretahovana")),
    ("Částice", ("trpyt", "duhovy_trpyt", "konfety", "ohnostroj", "blesky", "blikani", "stroboskop", "kapky")),
    ("Zespodu", ("ohen", "plamen", "vodopad")),
    ("Senzor", ("teplota", "hladina")),
]
FAN_NAMES = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "Deska – D_LED1", "D_LED2": "Deska – D_LED2",
             "grafika": "grafika", "klavesnice": "klávesnice"}


def fx_groups():
    """[(nazev skupiny, [klice efektu])] - jen existujici efekty, zbytek ve skupine Ostatni."""
    groups = [(n, [k for k in keys if k in fx.EFFECTS]) for n, keys in FX_GROUPS]
    seen = {k for _n, keys in groups for k in keys}
    rest = [k for k in fx.EFFECTS if k not in seen]
    if rest:
        groups.append(("Ostatní", rest))
    return [(n, keys) for n, keys in groups if keys]


def _dur(s):
    """Delka cesky: 3,1 s / 25 s / 1 min 05 s."""
    if s < 10:
        return f"{s:.1f} s".replace(".", ",")
    s = round(s)
    return f"{s} s" if s < 60 else f"{s // 60} min {s % 60:02d} s"


class LedEditor:
    last_tab = "efekt"            # vybrana zalozka (zachova se pri "Vratit ulozene" - okno se postavi znovu)

    def __init__(self, parent, app):
        self.app = app
        self.engine = fx.Engine(seed=7)
        self.t0 = time.monotonic()
        self._prev = self.t0
        self._pl_t0 = self.t0                     # playlist v nahledu od zacatku
        self._pl_sel = 0                          # vybrana polozka playlistu
        self._pl_view = "vse"                     # nahled: "vse" = cely playlist, "polozka" = jen vybrana
        self._pl_ui = None
        self._test = tk.StringVar(value="")       # test natoceni: "" / "dole" / "obiha"
        self._test_t0 = self.t0
        self._test_job = None
        self._custom_hosts = []                   # karty s kruhy vlastnich barev LED (Efekt, Zapojeni)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        parent.rowconfigure(2, weight=1)

        self._build_top(parent)
        keys = [k for k, _t in TABS]
        self._tab = tk.StringVar(value=LedEditor.last_tab if LedEditor.last_tab in keys else keys[0])
        tb = tk.Frame(parent, bg=V.BG)
        tb.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        V.segmented(tb, self._tab, TABS, command=self._show_tab, style="Tab.Toolbutton").pack(side="left")
        self.scroll = V.ScrollFrame(parent)
        self.scroll.grid(row=2, column=0, sticky="nsew")
        body = self.scroll.inner
        body.columnconfigure(0, weight=1)
        self.tabs = {}
        for key in keys:
            f = tk.Frame(body, bg=V.BG)
            f.columnconfigure(0, weight=1)
            self.tabs[key] = f
        right = tk.Frame(parent, bg=V.BG)                  # nahled se neroluje - je videt na kazde zalozce
        right.grid(row=1, column=1, rowspan=2, sticky="n", padx=(16, 0))
        self._build_preview(right)

        # Efekt
        t = self.tabs["efekt"]
        self.fx_frame = V.card(t)
        self.fx_frame.grid(row=0, column=0, sticky="ew")
        self.custom_fx = V.card(t)                         # jen kdyz se efekt "vlastni barvy LED" pouziva
        self._custom_hosts.append((self.custom_fx, "Vlastní barvy LED",
                                   "Barvy jednotlivých LED pro efekt „vlastní barvy LED“. Stejné barvy svítí "
                                   "i jako klidný stav po ukončení aplikace. Klik na LED = změna barvy."))
        # Hudba
        self.music = tk.Frame(self.tabs["hudba"], bg=V.BG)
        self.music.grid(row=0, column=0, sticky="ew")
        self.music.columnconfigure(0, weight=1)
        # Synchronizace
        self.wave = V.card(self.tabs["synchro"])
        self.wave.grid(row=0, column=0, sticky="ew")
        # Dalsi zarizeni
        t = self.tabs["zarizeni"]
        self.gpu = V.card(t)
        self.gpu.grid(row=0, column=0, sticky="ew")
        self.zones = V.card(t)
        self.zones.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        # Zapojeni
        t = self.tabs["zapojeni"]
        self.fans = V.card(t)
        self.fans.grid(row=0, column=0, sticky="ew")
        self.sync = V.card(t)
        self.sync.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        self.sync.bind("<Destroy>", lambda e: led.stop_test() if self._test.get() else None)
        self.balance = V.card(t)
        self.balance.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.rotation = V.card(t)
        self.rotation.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.custom_idle = V.card(t)
        self.custom_idle.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        self._custom_hosts.append((self.custom_idle, "Klidný stav po ukončení",
                                   "Takhle ventilátory svítí po ukončení aplikace a při vypnutém řízení LED; "
                                   "stejné barvy používá efekt „vlastní barvy LED“. Klik na LED = změna barvy."))

        self._build_effects()
        self._build_music()
        self._build_wave()
        self._build_gpu()
        self._build_zones_card()
        self._build_fans()
        self._build_sync()
        self._build_balance()
        self._build_rotation()
        self._build_custom()
        self._show_tab()
        self.refresh()
        self._animate()

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    # ------------------------------------------------------- horni lista a zalozky
    def _build_top(self, parent):
        """Rizeni LED z aplikace, stav a hlavni jas - pevne nad zalozkami."""
        top = V.card(parent)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        top.columnconfigure(1, weight=1)
        v = tk.BooleanVar(value=self.lcfg.get("zapnuto", True))
        ttk.Checkbutton(top, text="Řídit LED z aplikace", variable=v,
                        command=lambda: self.lcfg.__setitem__("zapnuto", v.get())).grid(
            row=0, column=0, sticky="w", padx=16, pady=10)
        self.status = ttk.Label(top, font=V.FONT_B, wraplength=520, justify="left")
        self.status.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(top, text="Jas", style="Muted.TLabel").grid(row=0, column=2, sticky="e", padx=(16, 8))
        jv = tk.IntVar(value=int(self.lcfg.get("jas", 80)))
        val = ttk.Label(top, width=5, text=f"{jv.get()} %", font=V.MONO, anchor="e")
        val.grid(row=0, column=4, sticky="e", padx=(8, 16))

        def on(_e=None):
            self.lcfg["jas"] = int(jv.get())
            val.config(text=f"{int(jv.get())} %")
        V.scale(top, variable=jv, from_=0, to=100, resolution=5, length=170, command=on).grid(row=0, column=3)

    def _show_tab(self):
        key = self._tab.get()
        LedEditor.last_tab = key
        if key == "synchro":                               # poradi vlny podle aktualnich cilu (grafika, D_LED2)
            self._build_wave()
        for k, f in self.tabs.items():
            if k == key:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_forget()
        self.scroll.canvas.yview_moveto(0)
        self._refit()
        if key != "zapojeni" and self._test.get():         # test natoceni jen na zalozce Zapojeni
            self._test.set("")
            self._test_changed()

    def _refit(self):
        """Po zmene obsahu zalozky prepocitat rolovani (kratsi obsah = bez posuvniku a prazdna mista)."""
        def fit():
            try:
                self.scroll.inner.update_idletasks()
                self.scroll._fit()
            except tk.TclError:
                pass
        self.scroll.after_idle(fit)

    def _build_preview(self, right):
        pv = V.card(right)
        pv.pack(fill="x")
        V.card_title(pv, "Živý náhled").pack(anchor="w", padx=16, pady=(14, 6))
        self.preview = tk.Canvas(pv, width=PREVIEW_W, height=PREVIEW_H, bg=V.CARD, highlightthickness=0)
        self.preview.pack(padx=12)
        self._music_demo = tk.BooleanVar(value=False)       # nahled: simulovana hudba
        ttk.Checkbutton(pv, text="Simulovaná hudba (120 úderů za minutu) – když je zapnutý vizualizér",
                        variable=self._music_demo).pack(anchor="w", padx=16, pady=(6, 0))
        ttk.Label(pv, style="Small.TLabel", text="Náhled počítá efekt stejně jako aplikace, včetně jasu, a ukazuje, "
                                                 "jak má vypadat na srovnaných ventilátorech (spodek dole). "
                                                 "Na ventilátorech se změna projeví po Uložit.",
                  wraplength=PREVIEW_W).pack(anchor="w", padx=16, pady=(4, 14))

    # -------------------------------------------------------------- efekty
    def _build_effects(self):
        self._refit()
        f = self.fx_frame
        for w in f.winfo_children():
            w.destroy()
        pl = self.lcfg.setdefault("playlist", copy.deepcopy(led.PLAYLIST_DEFAULT))
        mode = tk.BooleanVar(value=bool(pl.get("zapnuto")))
        same = tk.BooleanVar(value=self.lcfg.get("stejne_pro_vse", True))

        def on_mode():
            pl["zapnuto"] = mode.get()
            if mode.get() and not pl.get("polozky"):      # prvni polozka = dosavadni efekt
                pl["polozky"] = [self._pl_new(self.lcfg.get("efekt", fx.DEFAULT_EFFECT))]
                self._pl_sel = 0
            self._pl_t0 = time.monotonic()
            self._build_effects()

        def on_same():
            self.lcfg["stejne_pro_vse"] = same.get()
            self._build_effects()
        head = ttk.Frame(f)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(14, 4))
        head.columnconfigure(0, weight=1)
        V.card_title(head, "Efekt ventilátorů").grid(row=0, column=0, sticky="w")
        V.segmented(head, mode, [(False, "Jeden efekt"), (True, "Playlist")], command=on_mode).grid(row=0, column=1)
        wf = ttk.Frame(f)
        wf.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 10))
        wave = "vlna – " + ("zepředu dozadu" if self.lcfg.get("vlna_smer", "dozadu") == "dozadu"
                            else "zezadu dopředu") if self.lcfg.get("vlna") else "synchronně"
        if not mode.get():
            ttk.Label(wf, text="Ventilátory", style="Muted.TLabel").grid(row=0, column=0, sticky="w",
                                                                         padx=(0, 10), pady=3)
            V.segmented(wf, same, [(True, "Stejný efekt pro všechny"), (False, "Zvlášť F140 a deska")],
                        command=on_same).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(wf, style="Small.TLabel", text=f"Mezi ventilátory: {wave} (záložka Synchronizace)").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        f.columnconfigure(0, weight=1)
        self._custom_visibility()
        if mode.get():
            self._build_playlist(f, pl)
            return
        self._pl_ui = None
        if same.get():
            panels = [("efekt", None)]
        else:
            panels = [("efekt_f140", "F140"), ("efekt_deska", "Ventilátory na desce")]
        # zvlast: panely pod sebou pres celou sirku (vedle sebe se pravy nevesel a orizl se)
        for i, (key, title) in enumerate(panels):
            eff = self.lcfg.setdefault(key, dict(fx.DEFAULT_EFFECT))
            if i:
                ttk.Separator(f).grid(row=3 + i * 2 - 1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 12))
            pf = ttk.Frame(f)
            pf.grid(row=3 + i * 2, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 16))
            if title:
                ttk.Label(pf, text=title, style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
            self._effect_panel(pf, eff, 3)

    # ------------------------------------------------------------- playlist
    def _pl_reps_for(self, eff):
        """Pocet opakovani, aby polozka trvala asi PLAYLIST_ITEM_S sekund."""
        return max(1, min(led.MAX_REPEATS, round(PLAYLIST_ITEM_S / fx.cycle_s(eff, led.wave_span(self.lcfg)))))

    def _pl_new(self, eff):
        e = copy.deepcopy(dict(eff))
        e["opakovani"] = self._pl_reps_for(e)
        rot = self._rotation()                              # spolecne otoceni (zalozka Zapojeni)
        if rot:
            e["otoceni"] = rot
        return e

    def _build_playlist(self, f, pl):
        """Seznam efektu playlistu (poradi, pocet opakovani), prolinani a nastaveni vybrane polozky."""
        items = pl.setdefault("polozky", [])
        if not items:
            items.append(self._pl_new(fx.DEFAULT_EFFECT))
        self._pl_sel = max(0, min(self._pl_sel, len(items) - 1))
        sel = self._pl_sel
        item = items[sel]
        pf = ttk.Frame(f)
        pf.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=20, pady=(4, 16))
        pf.columnconfigure(0, weight=1)
        ttk.Label(pf, style="Small.TLabel", wraplength=440, justify="left", text=(
            "Efekty se střídají dokola v tomto pořadí; každý běží zvolený počet opakování (jedno opakování = "
            "jedna otáčka, nádech, projití všech barev…, u efektů bez cyklu 5 s). Playlist platí pro všechny "
            "ventilátory i grafiku s efektem „jako F140 / deska“.")).grid(row=0, column=0, columnspan=2,
                                                                         sticky="w", pady=(0, 8))
        lf = tk.Frame(pf, bg=V.FIELD, highlightthickness=1, highlightbackground=V.LINE)
        lf.grid(row=1, column=0, sticky="nsew")
        lb = V.listbox(lf, height=max(4, min(12, len(items))), bg=V.FIELD, font=V.MONO, width=44)
        lb.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        if len(items) > 12:
            sb = ttk.Scrollbar(lf, orient="vertical", command=lb.yview)
            sb.pack(side="right", fill="y")
            lb.config(yscrollcommand=sb.set)
        for text in self._pl_lines(items, None):
            lb.insert("end", text)
        lb.selection_set(sel)
        lb.see(sel)

        def on_select(_e=None):
            cur = lb.curselection()
            if cur and cur[0] != self._pl_sel:
                self._pl_sel = cur[0]
                if self._pl_view == "polozka":
                    self._pl_t0 = time.monotonic()
                f.after_idle(self._build_effects)
        lb.bind("<<ListboxSelect>>", on_select)
        bf = ttk.Frame(pf)
        bf.grid(row=1, column=1, sticky="n", padx=(8, 0))

        def add():
            items.insert(sel + 1, self._pl_new(fx.DEFAULT_EFFECT))
            self._pl_sel = sel + 1
            self._build_effects()

        def dup():
            items.insert(sel + 1, copy.deepcopy(item))
            self._pl_sel = sel + 1
            self._build_effects()

        def move(d):
            j = sel + d
            if 0 <= j < len(items):
                items[sel], items[j] = items[j], items[sel]
                self._pl_sel = j
                self._build_effects()

        def remove():
            if len(items) > 1:
                del items[sel]
                self._pl_sel = min(sel, len(items) - 1)
                self._build_effects()
        for text, cmd, ok in (("+ Přidat", add, True), ("Duplikovat", dup, True),
                              ("▲ Nahoru", lambda: move(-1), sel > 0),
                              ("▼ Dolů", lambda: move(1), sel < len(items) - 1),
                              ("Odebrat", remove, len(items) > 1)):
            b = ttk.Button(bf, text=text, command=cmd, width=11)
            b.pack(fill="x", pady=(0, 4))
            if not ok:
                b.state(["disabled"])
        of = ttk.Frame(pf)
        of.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(of, text="Prolínání", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        fv = tk.DoubleVar(value=float(pl.get("prolinani", 1.0)))
        fl = ttk.Label(of, style="Muted.TLabel", width=8)

        def show_fade():
            x = round(float(fv.get()), 1)
            fl.config(text="ostře" if x <= 0 else f"{x:g} s".replace(".", ","))

        def on_fade(_e=None):
            pl["prolinani"] = round(float(fv.get()), 1)
            show_fade()
        V.scale(of, variable=fv, from_=0, to=led.MAX_FADE_S, resolution=0.5, length=150, command=on_fade).grid(
            row=0, column=1, sticky="w")
        fl.grid(row=0, column=2, sticky="w", padx=(8, 0))
        show_fade()
        total = ttk.Label(of, style="Muted.TLabel")
        total.grid(row=0, column=3, sticky="e", padx=(16, 0))
        of.columnconfigure(3, weight=1)
        ttk.Label(of, text="Náhled", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        vf = ttk.Frame(of)
        vf.grid(row=1, column=1, columnspan=3, sticky="w", pady=3)
        view = tk.StringVar(value=self._pl_view)

        def on_view():
            self._pl_view = view.get()
            self._pl_t0 = time.monotonic()
        V.segmented(vf, view, [("vse", "celý playlist"), ("polozka", "jen vybraný efekt")],
                    command=on_view).pack(side="left")
        ttk.Button(vf, text="⟲ Od začátku", command=lambda: setattr(self, "_pl_t0", time.monotonic())).pack(
            side="left", padx=(8, 0))
        ttk.Separator(pf).grid(row=3, column=0, columnspan=2, sticky="ew", pady=12)
        ef = ttk.Frame(pf)
        ef.grid(row=4, column=0, columnspan=2, sticky="nsew")
        ef.columnconfigure(1, weight=1)
        ttk.Label(ef, text=f"Efekt {sel + 1} z {len(items)}", style="Bold.TLabel").grid(row=0, column=0, sticky="w")
        rf = ttk.Frame(ef)
        rf.grid(row=0, column=1, sticky="e")
        ttk.Label(rf, text="Opakování", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        rv = tk.StringVar(value=str(led.repeats(item)))
        ttk.Spinbox(rf, textvariable=rv, from_=1, to=led.MAX_REPEATS, width=5, font=V.MONO).pack(side="left")
        reps = ttk.Label(rf, style="Muted.TLabel", width=18)
        reps.pack(side="left", padx=(6, 0))

        def on_reps(*a):
            try:
                item["opakovani"] = max(1, min(led.MAX_REPEATS, int(rv.get())))
            except ValueError:
                pass
        rv.trace_add("write", on_reps)
        typ_before = item.get("typ")

        def changed():                                     # jiny efekt = jina delka opakovani
            if item.get("typ") != typ_before:
                item["opakovani"] = self._pl_reps_for(item)
            self._build_effects()
        panel = ttk.Frame(ef)
        panel.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        self._effect_panel(panel, item, 3, rebuild=changed)
        self._pl_ui = {"lb": lb, "total": total, "reps": reps, "lines": None}

    def _pl_lines(self, items, playing):
        span = led.wave_span(self.lcfg)
        out = []
        for i, e in enumerate(items):
            name = fx.EFFECTS.get(e.get("typ"), ("?",))[0]
            mark = "▶" if i == playing else " "
            out.append(f"{mark}{i + 1:>2}. {name:<18} {led.repeats(e):>3}× {_dur(led.item_duration(e, span)):>9}")
        return out

    def _pl_update(self, playing):
        """Delky polozek a celkem (meni se s rychlosti efektu) a hrajici polozka v nahledu."""
        ui = self._pl_ui
        if not ui:
            return
        try:
            if not ui["lb"].winfo_exists():
                self._pl_ui = None
                return
        except tk.TclError:
            self._pl_ui = None
            return
        items = self.lcfg.get("playlist", {}).get("polozky", [])
        lines = self._pl_lines(items, playing)
        if lines == ui["lines"]:
            return
        lb = ui["lb"]
        if len(lines) == lb.size():
            for i, text in enumerate(lines):
                if text != lb.get(i):
                    lb.delete(i)
                    lb.insert(i, text)
            lb.selection_clear(0, "end")
            lb.selection_set(self._pl_sel)
        ui["lines"] = lines
        span = led.wave_span(self.lcfg)
        ui["total"].config(text="celkem " + _dur(sum(led.item_duration(e, span) for e in items)))
        if 0 <= self._pl_sel < len(items):
            e = items[self._pl_sel]
            ui["reps"].config(text=f"× {_dur(fx.cycle_s(e, span))} = {_dur(led.item_duration(e, span))}")

    # -------------------------------------------------------- synchronizace
    def _build_wave(self):
        """Synchronne / vlna, smer vlny, F140 jako jeden a vysledne poradi ventilatoru ve vlne."""
        self._refit()
        f = self.wave
        for w in f.winfo_children():
            w.destroy()
        lc = self.lcfg
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Synchronizace ventilátorů").grid(row=0, column=0, columnspan=2, sticky="w", padx=20,
                                                         pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Jak se efekt šíří mezi ventilátory. Platí pro jeden efekt, playlist i hudbu ze Spotify.")).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 8))

        def setter(key, var, rebuild=True):
            def on():
                lc[key] = var.get()
                if rebuild:
                    self._build_wave()
                    self._build_effects()                       # souhrn vlny v karte efektu, delky playlistu
            return on
        wave = tk.BooleanVar(value=lc.get("vlna", False))
        rows = [("Mezi ventilátory", wave, [(False, "Synchronně"), (True, "Vlna (posunutě)")], "vlna")]
        if wave.get():
            rows += [("Směr vlny", tk.StringVar(value=lc.get("vlna_smer", "dozadu")),
                      [("dozadu", "zepředu dozadu"), ("dopredu", "zezadu dopředu")], "vlna_smer"),
                     ("F140", tk.BooleanVar(value=lc.get("vlna_f140_spolu", True)),
                      [(True, "jako jeden (oba stejně)"), (False, "postupně")], "vlna_f140_spolu")]
        for r, (text, var, opts, key) in enumerate(rows, start=2):
            ttk.Label(f, text=text, style="Muted.TLabel").grid(row=r, column=0, sticky="w", padx=(20, 10), pady=3)
            V.segmented(f, var, opts, command=setter(key, var)).grid(row=r, column=1, sticky="w", pady=3)
        r = 2 + len(rows)
        keys = [k for k, _n, _g, _c in led.targets(lc) if k not in led.NO_WAVE]
        if wave.get():
            offs = led.wave_offsets(lc, keys)[0]
            steps = []                                          # vlna jde od vetsiho posunu k mensimu
            for o in sorted({round(v, 6) for v in offs.values()}, reverse=True):
                steps.append(" + ".join(FAN_NAMES.get(k, k) for k in keys if round(offs[k], 6) == o))
            order = "  →  ".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
            note = ("Pak vlna naváže znovu na začátek. Ve skříni: D_LED1 vpředu, 2× F140 uprostřed, D_LED2 "
                    "vzadu, grafika pod F140 (ve vlně za D_LED2 – vlna oběhne skříň dokola). Který F140 je "
                    "vpředu, se nastavuje v záložce Zapojení.")
        else:
            order = "všechny najednou: " + ", ".join(FAN_NAMES.get(k, k) for k in keys)
            note = "Všechny ventilátory i grafika mají stejnou fázi efektu."
        ttk.Label(f, text="Pořadí", style="Muted.TLabel").grid(row=r, column=0, sticky="nw", padx=(20, 10),
                                                               pady=(8, 3))
        ttk.Label(f, text=order, font=V.FONT_B, wraplength=WRAP - 120, justify="left").grid(
            row=r, column=1, sticky="w", pady=(8, 3), padx=(0, 20))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=note).grid(
            row=r + 1, column=0, columnspan=2, sticky="w", padx=20, pady=(4, 16))

    def _effect_panel(self, f, eff, chip_cols=3, rebuild=None, custom_note=True):
        """Vyber efektu (skupiny FX_GROUPS + cipy efektu ve skupine) a nastaveni vybraneho efektu."""
        rebuild = rebuild or self._build_effects           # po zmene prekreslit svou kartu
        typ = eff.get("typ", "duha_toceni")
        _n, ncolors, has_speed, has_dir = fx.EFFECTS.get(typ, fx.EFFECTS["vypnuto"])
        tv = tk.StringVar(value=typ if typ in fx.EFFECTS else "vypnuto")
        groups = fx_groups()
        gv = tk.StringVar(value=next((n for n, keys in groups if tv.get() in keys), groups[0][0]))
        chips = ttk.Frame(f)

        def on_typ():
            eff["typ"] = tv.get()
            rebuild()

        def fill():                                         # cipy efektu vybrane skupiny (bez prestavby karty)
            for w in chips.winfo_children():
                w.destroy()
            for i, key in enumerate(dict(groups)[gv.get()]):
                ttk.Radiobutton(chips, text=fx.EFFECTS[key][0], value=key, variable=tv, command=on_typ,
                                style="Chip.Toolbutton").grid(row=i // chip_cols, column=i % chip_cols,
                                                              sticky="ew", padx=2, pady=2)
        V.segmented(f, gv, [(n, n) for n, _k in groups], command=fill, style="SegSmall.Toolbutton").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for c in range(chip_cols):
            chips.columnconfigure(c, weight=1, uniform="chip")
        chips.grid(row=2, column=0, columnspan=2, sticky="ew")
        fill()
        ttk.Separator(f).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Label(f, text=fx.EFFECTS.get(tv.get(), ("?",))[0], style="Bold.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
        f.columnconfigure(1, weight=1)
        row = 5
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
        if typ in fx.PAUSE_EFFECTS:                         # pauza naplno / se stejnou barvou
            ttk.Label(f, text="Pauza naplno" if typ == "dychani" else "Pauza", style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", pady=4)
            pf = ttk.Frame(f)
            pf.grid(row=row, column=1, sticky="ew", padx=8)
            pv = tk.DoubleVar(value=float(eff.get("pauza", 0)))
            pl = ttk.Label(pf, style="Muted.TLabel", width=9)

            def show_pause():
                x = round(float(pv.get()), 1)
                pl.config(text="bez pauzy" if x <= 0 else f"{x:g} s".replace(".", ","))

            def on_pause(_e=None):                          # jen zmena uzivatelem (ne pri sestaveni)
                eff["pauza"] = round(float(pv.get()), 1)
                show_pause()
            V.scale(pf, variable=pv, from_=0, to=fx.MAX_PAUSE, resolution=0.5, length=150,
                    command=on_pause).pack(side="left", fill="x", expand=True)
            pl.pack(side="left", padx=(8, 0))
            show_pause()
            row += 1
        if typ == "duha_prelevani":                         # plna duha, nebo vlastni barvy (az 8)
            ttk.Label(f, text="Režim barev", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            mv = tk.StringVar(value="barvy" if eff.get("barvy_rezim") == "barvy" else "duha")

            def on_mode():
                eff["barvy_rezim"] = mv.get()
                rebuild()
            V.segmented(f, mv, [("duha", "plná duha"), ("barvy", "vlastní barvy")], command=on_mode).grid(
                row=row, column=1, sticky="w", padx=8, pady=4)
            row += 1
        if typ in fx.PALETTE and not (typ == "duha_prelevani" and eff.get("barvy_rezim") != "barvy"):
            row = self._palette_editor(f, eff, typ, row, rebuild=rebuild)   # paleta s volitelnym poctem barev
        elif ncolors:
            labels = {"kometa": ["kometa", "pozadí"], "trpyt": ["záblesky", "pozadí"],
                      "prechod": ["barva 1", "barva 2"], "teplota": ["studená", "střední", "horká"],
                      "dvojita_kometa": ["kometa 1", "kometa 2"], "policie": ["první", "druhá"],
                      "tep": ["barva"], "stroboskop": ["barva"], "divadlo": ["světla", "pozadí"],
                      "odraz": ["světlo", "pozadí"], "blesky": ["blesk", "pozadí"]}.get(
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
        if typ in fx.VERTICAL and int(eff.get("otoceni", 0)) % 360:   # otoceni se nastavuje v Zapojeni
            ttk.Label(f, style="Small.TLabel", text=f"Otočení {int(eff['otoceni']) % 360}° (záložka Zapojení)").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=4)
            row += 1
        if typ in fx.SENSOR_EFFECTS:
            ttk.Label(f, text="Senzor", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            sn = tk.StringVar(value=eff.get("senzor", "CPU (Tctl/Tdie)"))
            ttk.Combobox(f, textvariable=sn, values=self.app._sensor_names(), width=26).grid(
                row=row, column=1, sticky="w", padx=8, pady=4)
            sn.trace_add("write", lambda *a: eff.__setitem__("senzor", sn.get()))
            row += 1
            rf = ttk.Frame(f)
            rf.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            texts = (("min", "prázdná při"), ("max", "plná při")) if typ == "hladina" else \
                (("min", "studená od"), ("max", "horká od"))
            for key, text in texts:
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
        if typ == "vlastni" and custom_note:
            ttk.Label(f, style="Small.TLabel", text="Barvy jednotlivých LED nastavíš níže ve Vlastních barvách LED.").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=4)

    def _palette_editor(self, f, eff, typ, row, rebuild=None):
        rebuild = rebuild or self._build_effects
        """Pocet barev (napr. 2-8) a mrizka barev po ctyrech; seznam "barvy" si pamatuje i barvy
        nad zvoleny pocet, takze po zvyseni se vrati."""
        lo, hi = fx.PALETTE[typ]
        n = fx.color_count(eff)
        cols = eff.setdefault("barvy", list(fx.DEFAULT_EFFECT["barvy"]))
        if len(cols) < n:
            cols.extend(fx.palette(eff)[len(cols):n])
        ttk.Label(f, text="Počet barev", style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=4)
        nv = tk.IntVar(value=n)

        def on_count():
            eff["pocet_barev"] = nv.get()
            rebuild()
        V.segmented(f, nv, [(k, str(k)) for k in range(lo, hi + 1)], command=on_count).grid(
            row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1
        if typ == "teplota":
            labels = ["studená"] + [str(i + 1) for i in range(1, n - 1)] + ["horká"]
        elif typ == "hladina":
            labels = ["dole"] + [str(i + 1) for i in range(1, n - 1)] + ["nahoře"]
        else:
            labels = [str(i + 1) for i in range(n)]
        labels = labels[:n] if n > 1 else ["barva"]
        ttk.Label(f, text="Barvy", style="Muted.TLabel").grid(row=row, column=0, sticky="nw", pady=6)
        bf = ttk.Frame(f)
        bf.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        for i in range(n):
            b = V.swatch(bf, cols[i], None, text=labels[i], width=7)
            b.config(command=lambda i=i, b=b: self._pick_list(cols, i, b))
            b.grid(row=i // 4, column=i % 4, padx=(0, 6), pady=(0, 6), ipady=4)
        row += 1
        if n > 1:
            tf = ttk.Frame(f)
            tf.grid(row=row, column=1, sticky="w", padx=8, pady=(0, 4))

            def rainbow():
                cols[:n] = led.rainbow(n)
                rebuild()

            def reverse():
                cols[:n] = cols[:n][::-1]
                rebuild()

            def rotate():
                cols[:n] = cols[n - 1:n] + cols[:n - 1]
                rebuild()
            for text, cmd, w in (("Duha", rainbow, None), ("Obrátit pořadí", reverse, None), ("↻", rotate, 3)):
                ttk.Button(tf, text=text, command=cmd, width=w).pack(side="left", padx=(0, 4))
            row += 1
        return row

    def _pick_list(self, cols, i, b):
        c = colorchooser.askcolor(color=cols[i], parent=self.fx_frame)[1]
        if c:
            cols[i] = c
            V.set_swatch(b, c)

    # ------------------------------------------------------ vlastni barvy LED
    def _uses_custom(self):
        """Pouziva nektery efekt ventilatoru (jeden efekt / zvlast / playlist) "vlastni barvy LED"?"""
        lc = self.lcfg
        pl = lc.get("playlist") or {}
        if pl.get("zapnuto"):
            effs = pl.get("polozky", [])
        elif lc.get("stejne_pro_vse", True):
            effs = [lc.get("efekt") or {}]
        else:
            effs = [lc.get("efekt_f140") or {}, lc.get("efekt_deska") or {}]
        return any(e.get("typ") == "vlastni" for e in effs)

    def _custom_visibility(self):
        if self._uses_custom():
            self.custom_fx.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        else:
            self.custom_fx.grid_remove()

    def _build_custom(self):
        """Kruhy vlastnich barev LED - stejne v zalozce Efekt (jen kdyz se pouzivaji) i v Zapojeni."""
        self._refit()
        for host in self._custom_hosts:
            self._build_custom_card(*host)

    def _build_custom_card(self, f, title, text):
        for w in f.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("nzxt_stejne", True))

        def on_same():
            self.lcfg["nzxt_stejne"] = same.get()
            self._build_custom()
        V.card_title(f, title).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=text).grid(
            row=1, column=0, columnspan=3, sticky="w", padx=20)
        ttk.Checkbutton(f, text="Oba F140 stejně", variable=same, command=on_same).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(6, 0))
        rings = [("F140 (1)" if not same.get() else "F140", self.lcfg["nzxt"]["led1"], led.LEDS_PER_FAN,
                  "čelo PC ▸")]
        if not same.get():
            rings.append(("F140 (2)", self.lcfg["nzxt"]["led2"], led.LEDS_PER_FAN, "čelo PC ▸"))
        for name in led.ARGB_HEADERS:                      # kazda zapojena ARGB hlavicka desky zvlast
            h = self.lcfg["argb"].get(name, {})
            if h.get("pouzito", name == "D_LED1"):
                rings.append((f"Deska – {name}", h, max(1, min(led.ARGB_MAX_LEDS, int(h.get("pocet_led", led.ARGB_FAN_LEDS)))),
                              None))
        for i, (name, ch, n, front) in enumerate(rings):    # po dvou do radku (tri se do sloupce nevejdou)
            row, col = 3 + i // 2, i % 2
            fr = ttk.Frame(f)
            fr.grid(row=row, column=col, sticky="nw", padx=(20 if col == 0 else 4, 4), pady=(6, 16))
            ttk.Label(fr, text=name, style="Bold.TLabel").pack(anchor="w")
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
        col = colorchooser.askcolor(color=ch["barvy"][i], parent=self.fx_frame)[1]
        if col:
            ch["barvy"][i] = col
            self._build_custom()

    def _set_used(self, h, used):
        h["pouzito"] = used
        self._build_custom()                                # kruhy barev a natoceni podle zapojenych hlavicek
        self._build_sync()
        self._build_balance()

    # ------------------------------------------------------- hudba ze Spotify
    def _build_music(self):
        """Zalozka Hudba: zapnuti a stav, styl, reakce na hudbu, barvy - kazdy blok ve vlastni karte."""
        self._refit()
        host = self.music
        for w in host.winfo_children():
            w.destroy()
        self._cover_strip = None
        mc = self.lcfg.setdefault("hudba", copy.deepcopy(led.MUSIC_DEFAULT))
        for key, v in led.MUSIC_DEFAULT.items():
            mc.setdefault(key, copy.deepcopy(v))

        def card(row, title):
            c = V.card(host)
            c.grid(row=row, column=0, sticky="ew", pady=(16 if row else 0, 0))
            c.columnconfigure(1, weight=1)
            V.card_title(c, title).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 4))
            return c

        def note(f, row, text, pady=(0, 4)):
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=text).grid(
                row=row, column=0, columnspan=3, sticky="w", padx=20, pady=pady)

        def slider(f, row, text, key, lo, hi, res, fmt, last=False):
            ttk.Label(f, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 10),
                                                               pady=(4, 16 if last else 4))
            v = tk.DoubleVar(value=float(mc.get(key, lo)))
            lbl = ttk.Label(f, width=8, font=V.MONO, anchor="e")
            lbl.grid(row=row, column=2, sticky="e", padx=(8, 20), pady=(4, 16 if last else 4))

            def on(_e=None):
                x = round(float(v.get()) / res) * res
                mc[key] = int(x) if float(res).is_integer() else round(x, 2)
                lbl.config(text=fmt(mc[key]))
            V.scale(f, variable=v, from_=lo, to=hi, resolution=res, length=160, command=on).grid(
                row=row, column=1, sticky="ew", pady=(4, 16 if last else 4))
            on()

        # 1) zapnuti, stav, navrat po pauze
        a = card(0, "Hudba ze Spotify")
        on = tk.BooleanVar(value=bool(mc.get("zapnuto")))

        def on_toggle():
            mc["zapnuto"] = on.get()
            self._build_music()
        ttk.Checkbutton(a, text="Když hraje Spotify, přepnout na hudební vizualizér", variable=on,
                        command=on_toggle).grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 2))
        self._music_lbl = ttk.Label(a, style="Small.TLabel", wraplength=WRAP, justify="left")
        self._music_lbl.grid(row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 6))
        intro = ("Reaguje jen na zvuk Spotify – hra, Discord ani upozornění ne. Má přednost před efektem "
                 "i playlistem; po pauze se za zvolenou dobu vrátí. Údery jdou při vlně skříní od předku dozadu.")
        if not mc.get("zapnuto"):
            note(a, 3, intro, pady=(0, 16))
            self._music_refresh()
            return
        slider(a, 3, "Návrat po pauze", "navrat_s", 0, 30, 1, lambda x: f"{x} s")
        note(a, 4, intro, pady=(0, 16))

        # 2) styl
        b = card(1, "Styl")
        sf = ttk.Frame(b)
        sf.grid(row=1, column=0, columnspan=3, sticky="ew", padx=20, pady=(2, 2))
        sf.columnconfigure(0, weight=1)
        alt = tk.BooleanVar(value=bool(mc.get("stridat")))

        def on_alt():
            mc["stridat"] = alt.get()
            self._build_music()
        V.segmented(sf, alt, [(False, "Jeden styl"), (True, "Náhodně s každou skladbou")], command=on_alt).grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        chips = ttk.Frame(sf)
        chips.grid(row=1, column=0, sticky="ew")
        tip = None
        if not alt.get():                                    # jeden styl: vyber jednoho
            sv = tk.StringVar(value=mc.get("styl", "pulz"))
            for i, (key, name) in enumerate(fx.MUSIC_STYLES.items()):
                chips.columnconfigure(i % 3, weight=1, uniform="chip")
                ttk.Radiobutton(chips, text=name, value=key, variable=sv, style="Chip.Toolbutton",
                                command=lambda: mc.__setitem__("styl", sv.get())).grid(
                    row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
        else:                                                # nahodne: zaskrtnout, ze kterych stylu
            pool = mc.setdefault("styly_stridat", list(fx.MUSIC_STYLES))
            vars_ = {}

            def on_pick(key):
                sel = [k for k in fx.MUSIC_STYLES if vars_[k].get()]
                if not sel:                                  # aspon jeden styl musi zustat
                    vars_[key].set(True)
                    sel = [key]
                mc["styly_stridat"] = sel
                count.config(text=f"vybráno {len(sel)} z {len(fx.MUSIC_STYLES)}")
            for i, (key, name) in enumerate(fx.MUSIC_STYLES.items()):
                chips.columnconfigure(i % 3, weight=1, uniform="chip")
                vars_[key] = tk.BooleanVar(value=key in pool)
                ttk.Checkbutton(chips, text=name, variable=vars_[key], style="Chip.Toolbutton",
                                command=lambda k=key: on_pick(k)).grid(
                    row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
            bf = ttk.Frame(sf)
            bf.grid(row=2, column=0, sticky="w", pady=(4, 0))

            def select(all_):
                for k, v in vars_.items():
                    v.set(all_ or k == next(iter(fx.MUSIC_STYLES)))
                on_pick(next(iter(fx.MUSIC_STYLES)))
            ttk.Button(bf, text="Vybrat vše", command=lambda: select(True)).pack(side="left", padx=(0, 4))
            ttk.Button(bf, text="Zrušit výběr", command=lambda: select(False)).pack(side="left", padx=(0, 10))
            count = ttk.Label(bf, style="Small.TLabel")
            count.pack(side="left")
            on_pick(next((k for k in fx.MUSIC_STYLES if k in pool), "pulz"))
            tip = ("S každou novou skladbou se náhodně vybere jeden ze zaškrtnutých stylů (dvakrát po sobě "
                   "stejný ne). V náhledu se styl mění každých 8 s.")
        rot = int(mc.get("otoceni", 0)) % 360
        if rot:
            tip = (tip + " " if tip else "") + f"Otočení svislých stylů {rot}° (záložka Zapojení)."
        note(b, 2, tip or "", pady=(6, 14))

        # 3) reakce na hudbu
        c = card(2, "Reakce na hudbu")
        slider(c, 1, "Důraz na basy", "basy", 0, 10, 1, lambda x: f"{x}")
        note(c, 2, "Vyšší = světla pumpují s basy: mezi údery ztmavnou, s kopákem se rozsvítí, záblesk úderu je "
                   "silnější a delší; středy a výšky (třpyt, přelévání barev) mají menší vliv. 0 = reaguje na vše "
                   "stejně.")
        slider(c, 3, "Citlivost na údery", "citlivost", 1, 10, 1, lambda x: f"{x}")
        slider(c, 4, "Jas", "jas", 10, 100, 5, lambda x: f"{x} %")
        slider(c, 5, "Zpoždění světel", "zpozdeni_ms", 0, 500, 10, lambda x: f"{x} ms")
        note(c, 6, "Bluetooth sluchátka hrají o 150–250 ms později než reproduktory – o tolik zpozdi světla, "
                   "aby údery seděly. S kabelem / reproduktory 0 ms.", pady=(0, 16))

        # 4) barvy
        d = card(3, "Barvy")
        bv = tk.StringVar(value=mc.get("barvy", "obal"))

        def on_colors():
            mc["barvy"] = bv.get()
            self._build_music()
        ttk.Label(d, text="Zdroj", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(20, 10), pady=4)
        V.segmented(d, bv, [("obal", "z obalu alba"), ("vlastni", "vlastní")], command=on_colors).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=4)
        if mc.get("barvy", "obal") == "obal":
            slider(d, 2, "Citlivost na barvy", "citlivost_barev", 1, 10, 1, lambda x: f"{x}")
            self._cover_strip = tk.Canvas(d, height=22, bg=V.CARD, highlightthickness=0)
            self._cover_strip.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 2))
            fv = tk.BooleanVar(value=bool(mc.get("doplnit_barvy", True)))
            ttk.Checkbutton(d, text="Doplnit kontrastní barvy, když jich obal má málo", variable=fv,
                            command=lambda: mc.__setitem__("doplnit_barvy", fv.get())).grid(
                row=4, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 0))
            note(d, 5, "Nejvýš 6 plně sytých barev, každé dvě se liší aspoň o 40° odstínu (žádné dvě podobné "
                       "modré). Vyšší citlivost = bere i méně syté a tmavší barvy a malé plochy obalu a chce víc "
                       "barev (1 → 2, 4 → 3, 7 → 4, 10 → 5). Když je obal nemá, doplní se odstíny co nejdál od "
                       "barev obalu (jde vypnout). Změna se projeví po Uložit.", pady=(0, 16))
        else:
            cols = mc.setdefault("paleta", list(led.MUSIC_DEFAULT["paleta"]))
            ttk.Label(d, text="Počet barev", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(20, 10),
                                                                       pady=4)
            nv = tk.IntVar(value=max(2, min(5, len(cols))))

            def on_count():
                n = nv.get()
                while len(cols) < n:
                    cols.append(next(c for c in fx.DEFAULT_PALETTE if c not in cols))
                del cols[n:]
                self._build_music()
            V.segmented(d, nv, [(k, str(k)) for k in range(2, 6)], command=on_count).grid(
                row=2, column=1, columnspan=2, sticky="w", pady=4)
            bf = ttk.Frame(d)
            bf.grid(row=3, column=1, columnspan=2, sticky="w", pady=(4, 16))
            for i in range(len(cols)):
                b2 = V.swatch(bf, cols[i], None, text="hlavní" if i == 0 else ("doplňková" if i == 1 else str(i + 1)),
                              width=9)
                b2.config(command=lambda i=i, b2=b2: self._pick_list(cols, i, b2))
                b2.pack(side="left", padx=(0, 6), ipady=4)
        self._music_refresh()

    def _music_palette(self):
        """Barvy pro nahled: z obalu prave hrajici skladby (ze stav.json), jinak vlastni."""
        mc = self.lcfg.get("hudba") or {}
        st = getattr(self.app, "mstate", None) or {}
        if mc.get("barvy", "obal") == "obal" and st.get("paleta"):
            return st["paleta"]
        return mc.get("paleta") or led.MUSIC_DEFAULT["paleta"]

    def _music_refresh(self):
        lbl = getattr(self, "_music_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
        except tk.TclError:
            return
        st = getattr(self.app, "mstate", None) or {}
        if not self.app.running:
            text = "Aplikace neběží."
        elif not st:
            text = "Stav hudby uvidíš, až poběží nová verze aplikace."
        elif st.get("chyba"):
            text = "Chyba: " + st["chyba"]
        elif not st.get("spotify"):
            text = "Spotify nehraje (není otevřené)."
        else:
            song = f"{st.get('interpret', '')} – {st.get('nazev', '')}" if st.get("nazev") else "?"
            text = ("▶ " if st.get("hraje") else "❚❚ ") + song
            if st.get("vizualizer"):
                text += " · vizualizér běží"
                u = st.get("uroven")
                if u:
                    text += f" · basy {u['bass']:.0%} středy {u['mid']:.0%} výšky {u['high']:.0%}".replace("%", " %")
                if st.get("bpm"):
                    text += f" · {st['bpm']:.0f} BPM"
        lbl.config(text=text)
        strip = getattr(self, "_cover_strip", None)          # barvy z obalu prave hrajici skladby
        try:
            if strip is not None and strip.winfo_exists():
                strip.delete("all")
                pal = st.get("paleta") or []
                if not pal:
                    strip.create_text(0, 11, anchor="w", fill=V.DIM, font=("Segoe UI", 8),
                                      text="barvy z obalu uvidíš, až bude Spotify hrát")
                for i, col in enumerate(pal):
                    strip.create_rectangle(i * 34, 2, i * 34 + 30, 20, fill=col, outline="")
                if pal:
                    strip.create_text(len(pal) * 34 + 4, 11, anchor="w", fill=V.DIM, font=("Segoe UI", 8),
                                      text="z obalu teď")
        except tk.TclError:
            pass

    # ------------------------------------------------------- graficka karta
    def _build_gpu(self):
        self._refit()
        f = self.gpu
        for w in f.winfo_children():
            w.destroy()
        gc = self.lcfg.setdefault("grafika", dict(led.EXTRA_DEFAULT))
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Grafická karta RTX 5070").grid(row=0, column=0, columnspan=2, sticky="w", padx=20,
                                                         pady=(14, 6))
        self.gpu_prev = tk.Canvas(f, width=120, height=34, bg=V.CARD, highlightthickness=0)
        self.gpu_prev.grid(row=0, column=2, rowspan=2, sticky="e", padx=20, pady=(10, 0))
        on = tk.BooleanVar(value=bool(gc.get("zapnuto")))

        def on_toggle():
            gc["zapnuto"] = on.get()
            self._build_gpu()
        ttk.Checkbutton(f, text="Řídit světelný pásek karty z aplikace", variable=on,
                        command=on_toggle).grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(2, 4))
        zones = led.gpu_zones(self.lcfg)
        if zones:
            ttk.Label(f, style="Small.TLabel", foreground=V.OK, text=(
                "S grafikou svítí i zóna desky: " + ", ".join(zones) + " (režim „jako grafika“ v kartě Další zóny desky níže).")).grid(
                row=7, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 12))
        if not gc.get("zapnuto") and not zones:
            ttk.Label(f, style="Small.TLabel", wraplength=440, justify="left", text=(
                "Karta svítí podle svého uloženého nastavení (z Gigabyte Control Center).")).grid(
                row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 16))
            return
        ttk.Label(f, text="Efekt", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(20, 10), pady=4)
        src = tk.StringVar(value=gc.get("efekt", "deska"))

        def on_src():
            gc["efekt"] = src.get()
            self._build_gpu()
        V.segmented(f, src, [("f140", "jako F140"), ("deska", "jako deska"), ("vlastni", "vlastní")],
                    command=on_src).grid(row=2, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Label(f, text="Jas", style="Muted.TLabel").grid(row=3, column=0, sticky="w", padx=(20, 10), pady=4)
        jv = tk.IntVar(value=int(gc.get("jas", 100)))
        jl = ttk.Label(f, width=5, text=f"{jv.get()} %", font=V.MONO, anchor="e")
        jl.grid(row=3, column=2, sticky="e", padx=(8, 20))

        def on_jas(_e=None):
            gc["jas"] = int(jv.get())
            jl.config(text=f"{int(jv.get())} %")
        V.scale(f, variable=jv, from_=10, to=100, resolution=5, length=140, command=on_jas).grid(
            row=3, column=1, sticky="ew", pady=4)
        ttk.Label(f, text="Klidná barva", style="Muted.TLabel").grid(row=4, column=0, sticky="w", padx=(20, 10),
                                                                     pady=4)
        b = V.swatch(f, gc.get("barva", "#ffffff"), None, width=6)
        b.grid(row=4, column=1, sticky="w", pady=4, ipady=2)

        def pick():
            col = colorchooser.askcolor(color=gc.get("barva", "#ffffff"), parent=self.gpu)[1]
            if col:
                gc["barva"] = col
                V.set_swatch(b, col)
        b.config(command=pick)
        ttk.Label(f, style="Small.TLabel", wraplength=440, justify="left", text=(
            "Klidná barva = po ukončení aplikace a u efektu „vlastní barvy LED“. Celý pásek svítí jednou "
            "barvou – efekt se počítá jako pro jeden ventilátor. Karta je pod F140: ve vlně svítí až za "
            "D_LED2, vlna tak oběhne skříň dokola. Pro souhru s ventilátory zvol „jako F140“ nebo „jako "
            "deska“. Do paměti karty se nic neukládá: po restartu PC karta svítí po svém, dokud ji "
            "aplikace nepřevezme.")).grid(
            row=5, column=0, columnspan=3, sticky="w", padx=20, pady=(4, 4))
        if gc.get("efekt") == "vlastni":
            eff = self.lcfg.setdefault("efekt_grafika", dict(fx.DEFAULT_EFFECT))
            pf = ttk.Frame(f)
            pf.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=20, pady=(4, 16))
            self._effect_panel(pf, eff, 3, rebuild=self._build_gpu, custom_note=False)
        else:
            ttk.Frame(f, height=12).grid(row=6, column=0)

    def _gpu_preview(self, col):
        """Barva pasku v karte grafiky (obrys karty se svetelnym paskem)."""
        c = getattr(self, "gpu_prev", None)
        try:
            if c is None or not c.winfo_exists():
                return
        except tk.TclError:
            return
        c.delete("all")
        c.create_rectangle(2, 4, 118, 30, outline="#262b33", fill="#111418")
        for x in (32, 88):                                    # dva ventilatory karty
            c.create_oval(x - 11, 6, x + 11, 28, outline="#1d2228", width=3)
        if not col:
            return
        r, g, b = (round(255 * (v / 255) ** 0.5) for v in col[0])
        c.create_rectangle(6, 30, 114, 33, outline="", fill=f"#{r:02x}{g:02x}{b:02x}")

    # ------------------------------------------------ natoceni (synchronizace)
    def _build_sync(self):
        """Posun LED 1 a smer cislovani kazdeho ventilatoru - aby se efekt na vsech tocil stejne."""
        f = self.sync
        for w in f.winfo_children():
            w.destroy()
        V.card_title(f, "Natočení ventilátorů").grid(row=0, column=0, columnspan=5, sticky="w", padx=16,
                                                      pady=(14, 0))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                  text="Test: na každém ventilátoru svítí jen jedna LED v jeho barvě (tečka u názvu). "
                       "„Svítí spodek“ – LED, kde efekty mají spodek ventilátoru (tam začínají plameny, "
                       "hladina…); posouvej LED, dokud nesvítí na každém ventilátoru dole. "
                       "„Obíhá“ – LED jde od spodku po směru hodin (dole → vlevo → nahoře → vpravo); "
                       "kde jde opačně, zaškrtni obrácený směr. Změny se v testu projeví do 3 s, "
                       "natrvalo až po Uložit. Po srovnání mají svislé efekty správně otočení 0°.").grid(
            row=1, column=0, columnspan=5, sticky="w", padx=16, pady=(2, 6))
        tf = tk.Frame(f, bg=V.CARD)
        tf.grid(row=2, column=0, columnspan=5, sticky="w", padx=16, pady=(0, 8))
        ttk.Label(tf, text="Test", style="Muted.TLabel").pack(side="left", padx=(0, 10))
        V.segmented(tf, self._test, [("", "vypnuto")] + list(led.TEST_MODES.items()),
                    command=self._test_changed).pack(side="left")
        self.test_msg = ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left")
        self.test_msg.grid(row=3, column=0, columnspan=5, sticky="w", padx=16)
        names = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "Deska – D_LED1", "D_LED2": "Deska – D_LED2"}
        fans = [t for t in led.targets(self.lcfg) if t[0] not in led.EXTRAS]   # grafika/klavesnice = 1 LED
        for r, (key, n, _g, _c) in enumerate(fans, start=4):
            if key.startswith("f140_"):
                ch = self.lcfg["nzxt"].setdefault("led" + key[-1], {})
            else:
                ch = self.lcfg["argb"].setdefault(key, {})
            last = r == 3 + len(fans)
            pad = (2, 14 if last else 2)
            dot = "#%02x%02x%02x" % led.TEST_COLORS.get(key, (255, 255, 255))
            tk.Label(f, text="●", fg=dot, bg=V.CARD, font=V.FONT_B).grid(row=r, column=0, sticky="w",
                                                                       padx=(16, 4), pady=pad)
            ttk.Label(f, text=names.get(key, key), style="Muted.TLabel").grid(row=r, column=1, sticky="w",
                                                                              padx=(0, 12), pady=pad)
            ttk.Label(f, text="posun LED", style="Small.TLabel").grid(row=r, column=2, sticky="e", pady=pad)
            sv = tk.StringVar(value=str(int(ch.get("posun", 0)) % n))
            ttk.Spinbox(f, textvariable=sv, from_=0, to=n - 1, width=4, wrap=True).grid(
                row=r, column=3, padx=(6, 12), pady=pad)

            def on_shift(*a, ch=ch, sv=sv, n=n):
                try:
                    ch["posun"] = int(sv.get()) % n
                except ValueError:
                    return
                self._test_send()
            sv.trace_add("write", on_shift)
            rv = tk.BooleanVar(value=bool(ch.get("obracene", False)))

            def on_rev(ch=ch, rv=rv):
                ch["obracene"] = rv.get()
                self._test_send()
            ttk.Checkbutton(f, text="obrácený směr", variable=rv, command=on_rev).grid(
                row=r, column=4, sticky="w", padx=(0, 16), pady=pad)
        self._test_show()

    # test natoceni: pozadavek pro bezici aplikaci (led_test.json), obnovuje se kazde 3 s,
    # po zavreni okna aplikace test sama ukonci (led.TEST_TIMEOUT_S)
    def _test_changed(self):
        self._test_t0 = time.monotonic()
        if self._test_job is not None:
            try:
                self.sync.after_cancel(self._test_job)
            except tk.TclError:
                pass
            self._test_job = None
        if self._test.get():
            self._test_beat()
        else:
            led.stop_test()
        self._test_show()

    def _test_beat(self):
        self._test_job = None
        if not self._test.get():
            return
        self._test_send()
        try:
            self._test_job = self.sync.after(3000, self._test_beat)
        except tk.TclError:
            pass

    def _test_send(self):
        if not self._test.get():
            return
        try:
            led.request_test(self.lcfg, self._test.get())
        except OSError as e:
            self.test_msg.config(text=f"Test nejde spustit: {e}", foreground=V.ERR)

    def _test_show(self):
        msg = getattr(self, "test_msg", None)
        if msg is None or not msg.winfo_exists():
            return
        if not self._test.get():
            msg.config(text="")
        elif not self.app.running:
            msg.config(text="Aplikace neběží – test uvidíš jen v náhledu.", foreground=V.WARN)
        elif not self.lcfg.get("zapnuto", True):
            msg.config(text="Řízení LED je vypnuté – zapni ho a ulož, jinak se test na ventilátorech "
                            "neukáže.", foreground=V.WARN)
        else:
            msg.config(text="Test běží na ventilátorech (efekty i hudba stojí). Po vypnutí testu "
                            "nebo zavření okna se efekt vrátí.", foreground=V.OK)

    # -------------------------------------------------------------- zapojeni
    def _build_fans(self):
        """ARGB hlavicky desky (zapojeno, pocet LED) a ktery F140 je blize predku skrine."""
        f = self.fans
        for w in f.winfo_children():
            w.destroy()
        lc = self.lcfg
        V.card_title(f, "Zapojení ventilátorů").grid(row=0, column=0, columnspan=4, sticky="w", padx=20,
                                                    pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "F140 jsou na řadiči NZXT (kanály led1 a led2, 8 LED). Ventilátory na desce jsou na ARGB "
            "hlavičkách – nezaškrtnutá hlavička zůstane zhasnutá.")).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 6))
        for r, name in enumerate(led.ARGB_HEADERS, start=2):
            h = lc["argb"].setdefault(name, {"pocet_led": led.ARGB_FAN_LEDS, "pouzito": False})
            used = tk.BooleanVar(value=h.get("pouzito", name == "D_LED1"))
            ttk.Checkbutton(f, text=f"{name} – {h.get('nazev', '')}", variable=used,
                            command=lambda h=h, used=used: self._set_used(h, used.get())).grid(
                row=r, column=0, sticky="w", padx=(20, 4), pady=2)
            ttk.Label(f, text="počet LED", style="Muted.TLabel").grid(row=r, column=1, padx=(10, 4))
            pv = tk.StringVar(value=str(h.get("pocet_led", led.ARGB_FAN_LEDS)))
            ttk.Spinbox(f, textvariable=pv, from_=1, to=led.ARGB_MAX_LEDS, width=4).grid(row=r, column=2,
                                                                                       sticky="w")

            def on_count(*a, h=h, pv=pv):
                try:
                    n = max(1, min(led.ARGB_MAX_LEDS, int(pv.get())))
                except ValueError:
                    return
                if n != h.get("pocet_led", led.ARGB_FAN_LEDS):
                    h["pocet_led"] = n
                    self._build_custom()                    # kruh barev a rozsah posunu podle poctu LED
                    self._build_sync()
            pv.trace_add("write", on_count)
        r = 2 + len(led.ARGB_HEADERS)
        ttk.Label(f, text="Blíž předku skříně", style="Muted.TLabel").grid(row=r, column=0, sticky="w",
                                                                          padx=(20, 4), pady=(10, 3))
        front = tk.StringVar(value=lc.get("f140_vpredu", "led1"))
        V.segmented(f, front, [("led1", "F140 (1)"), ("led2", "F140 (2)")],
                    command=lambda: lc.__setitem__("f140_vpredu", front.get())).grid(
            row=r, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=(10, 3))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Který F140 je vpředu, poznáš s efektem „blikání“, vlnou a F140 postupně (záložka Synchronizace): "
            "vlna musí jít plynule jedním směrem – když F140 bliknou obráceně, přepni.")).grid(
            row=r + 1, column=0, columnspan=4, sticky="w", padx=20, pady=(2, 16))

    def _build_balance(self):
        """Vyrovnani jasu F140 a ventilatoru na desce (hlavni jas je v horni liste)."""
        f = self.balance
        for w in f.winfo_children():
            w.destroy()
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Vyrovnání jasu").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Když F140 a ventilátory na desce svítí při stejném nastavení různě jasně, ztlum ten jasnější. "
            "Hlavní jas je nahoře v liště.")).grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 4))
        for row, (key, text) in enumerate((("jas_f140", "F140"), ("jas_deska", "Ventilátory na desce")), start=2):
            last = row == 3
            pad = (4, 16 if last else 4)
            ttk.Label(f, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(20, 12), pady=pad)
            v = tk.IntVar(value=int(self.lcfg.get(key, 100)))
            val = ttk.Label(f, width=5, text=f"{v.get()} %", font=V.MONO, anchor="e")
            val.grid(row=row, column=2, sticky="e", padx=(8, 20), pady=pad)

            def on(_e=None, key=key, v=v, val=val):
                self.lcfg[key] = int(v.get())
                val.config(text=f"{int(v.get())} %")
            V.scale(f, variable=v, from_=20, to=100, resolution=5, length=160, command=on).grid(
                row=row, column=1, sticky="ew", pady=pad)

    def _rotation_targets(self):
        """Efekty, ktere nesou "otoceni": efekt (i zvlast F140 / deska), polozky playlistu, hudba."""
        lc = self.lcfg
        out = [lc[k] for k in ("efekt", "efekt_f140", "efekt_deska") if isinstance(lc.get(k), dict)]
        out += (lc.get("playlist") or {}).get("polozky", [])
        if isinstance(lc.get("hudba"), dict):
            out.append(lc["hudba"])
        return out

    def _rotation(self):
        """Spolecne otoceni (0/90/180/270), nebo None, kdyz se u efektu lisi."""
        vals = {int(e.get("otoceni", 0)) % 360 for e in self._rotation_targets()}
        return vals.pop() if len(vals) == 1 else (0 if not vals else None)

    def _build_rotation(self):
        f = self.rotation
        for w in f.winfo_children():
            w.destroy()
        V.card_title(f, "Otočení svislých efektů a hudby").grid(row=0, column=0, columnspan=2, sticky="w",
                                                               padx=20, pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Kde je „dole“ u svislých efektů (plamen, vodopád, hladina, přetahovaná) a stylů hudby (plameny, "
            "spektrum, vlny…). Po srovnání natočení ventilátorů patří 0°; jiné otočení jen když chceš efekt "
            "celý otočit (např. plamen shora). Platí pro všechny efekty, playlist i hudbu.")).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 6))
        cur = self._rotation()
        ov = tk.IntVar(value=-1 if cur is None else cur)

        def on():
            for e in self._rotation_targets():
                e["otoceni"] = ov.get()
            self._build_rotation()
            self._build_effects()                               # poznamka o otoceni u efektu
            self._build_music()
        ttk.Label(f, text="Otočení", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(20, 10),
                                                               pady=(4, 16))
        of = ttk.Frame(f)
        of.grid(row=2, column=1, sticky="w", pady=(4, 16))
        V.segmented(of, ov, [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")], command=on).pack(side="left")
        if cur is None:
            ttk.Label(of, style="Small.TLabel", foreground=V.WARN,
                      text="  teď se u efektů liší – výběr nastaví všem stejně").pack(side="left")

    def _build_zones_card(self):
        f = self.zones
        for w in f.winfo_children():
            w.destroy()
        V.card_title(f, "Další zóny desky").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "Malé LED a 12V RGB na desce – jen celá zóna, vestavěné režimy řadiče. Režim „jako grafika“ = zóna "
            "svítí stejně jako pásek grafické karty.")).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 6))
        zf = ttk.Frame(f)
        zf.grid(row=2, column=0, sticky="w", padx=16)
        self._build_zones(zf)
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left", text=(
            "LED desky jinak ovládá Gigabyte Control Center (GCC) – pokud běží, nastavení desky přepíše "
            "(autostart_zapnout.bat ho vypne).")).grid(row=3, column=0, sticky="w", padx=20, pady=(6, 16))

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
            nazev = z.get("nazev", "")
            label = zone if not nazev or nazev.startswith("zóna") else f"{zone} – {nazev}"
            ttk.Label(f, text=label, style="Muted.TLabel").grid(row=r, column=0, sticky="w", padx=4, pady=2)
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
            mv.trace_add("write", lambda *a, z=z, mv=mv: self._zone_mode(z, rev_names[mv.get()]))
            r += 1

    def _zone_mode(self, z, mode):
        was = z.get("rezim") == led.SYNC_ZONE
        z["rezim"] = mode
        if was != (mode == led.SYNC_ZONE):
            self._build_gpu()                                # karta grafiky ukazuje zony "jako grafika"

    def _pick_zone(self, z, b):
        col = colorchooser.askcolor(color=z.get("barva", "#ffffff"), parent=self.zones)[1]
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
        gs = klavesy_g.State()                                  # predvolba G upravovana na strance Klavesnice
        kbd = getattr(self.app, "kbd", None)
        gs.active = kbd.preview_preset() if kbd is not None else None
        if gs.active is not None:
            lc = gs.apply(lc)
        if not lc.get("zapnuto", True):
            c.create_text(PREVIEW_W / 2, PREVIEW_H / 2, text="Řízení LED vypnuto", fill=V.MUTED)
            self._kb_preview(None)
        else:
            # bez natoceni ventilatoru = jak ma efekt vypadat (spodek dole, jako test natoceni)
            lr, t, info = lc, now - self.t0, None
            items = led.playlist_items(lc)
            if items:                                           # playlist: od zacatku / jen vybrany efekt
                t = now - self._pl_t0
                sel = max(0, min(self._pl_sel, len(items) - 1))
                if self._pl_view == "polozka":
                    lr = dict(lc, playlist=dict(lc["playlist"], polozky=[items[sel]]))
                info = led.playlist_at(lr, t)
                if info and self._pl_view == "polozka":
                    info = dict(info, i=sel, pocet=len(items))
            self._pl_update(info["i"] if info and self._pl_view == "vse" else None)
            snap = None
            if self._music_demo.get() and (lc.get("hudba") or {}).get("zapnuto"):   # simulovana hudba
                snap = fx.music_demo(now - self.t0, self._music_palette(), track_n=int((now - self.t0) // 8))
                info = None
            if self._test.get():                                # test natoceni: jen jedna LED
                frame = led.test_frame(lc, {"rezim": self._test.get()}, now - self._test_t0, orient=False)
                snap = info = None
                c.create_text(4, 2, anchor="nw", fill=V.MUTED, font=("Segoe UI", 8),
                              text="Test: " + led.TEST_MODES[self._test.get()] + " – takhle to má vypadat")
            else:
                kb_music = None                                 # hudebni efekt klavesnice: simulovana hudba
                if led.kb_music_on(lc):
                    kb_music = fx.music_demo(now - self.t0, fx.DEFAULT_PALETTE[:4])
                kb_over = gs.leds(self.lcfg) if led.extra_on(lc, "klavesnice") else None
                frame = led.render(self.engine, lr, t, self.app.data, min(dt, 0.2), orient=False, music=snap,
                                   kb_music=kb_music, kb_over=kb_over)
            if snap is not None:
                c.create_text(4, 2, anchor="nw", fill=V.MUTED, font=("Segoe UI", 8),
                              text="♪ simulovaná hudba · " + fx.MUSIC_STYLES[fx.music_style(lc["hudba"], snap)])
            if info:
                name = fx.EFFECTS.get(info["eff"].get("typ"), ("?",))[0]
                c.create_text(4, 2, anchor="nw", fill=V.MUTED, font=("Segoe UI", 8),
                              text=f"▶ {info['i'] + 1}/{info['pocet']}  {name} · ještě {_dur(info['zbyva'])}")
            self._kb_preview(frame.pop("klavesnice", None))
            gpu = frame.pop("grafika", None)
            self._gpu_preview(gpu)
            order = led.wave_offsets(lc, list(frame))[1]          # jako ve skrini: vlevo predek, vpravo zadek
            items = [(k, frame[k]) for k in order]
            n_items = len(items)
            cell = PREVIEW_W / max(1, n_items)                  # 3-4 ventilatory vedle sebe
            c.create_text(4, PREVIEW_H - 2, text="◂ předek skříně", fill=V.DIM, anchor="sw", font=("Segoe UI", 8))
            c.create_text(PREVIEW_W - 4, PREVIEW_H - 2, text="zadek skříně ▸", fill=V.DIM, anchor="se",
                          font=("Segoe UI", 8))
            for idx, (key, cols) in enumerate(items):
                cx = cell * (idx + 0.5)
                cy = PREVIEW_H / 2 - 6
                n = len(cols)
                R = min(50, cell / 2 - 20)
                dot = 7 if n <= 8 else 5
                c.create_rectangle(cx - R - 18, cy - R - 18, cx + R + 18, cy + R + 18, outline="#262b33",
                                   fill="#111418")
                c.create_oval(cx - R - 8, cy - R - 8, cx + R + 8, cy + R + 8, outline="#1d2228", width=10)
                for i, rgb in enumerate(cols):
                    a = fx._ring_angle(i, n, {})                # jako efekty: spodek dole i u 14 LED
                    x, y = cx + R * math.cos(a), cy + R * math.sin(a)
                    # LED sviti vic, nez stejna hodnota na monitoru -> pro nahled zesvetlit (gama)
                    r, g, b = (round(255 * (v / 255) ** 0.5) for v in rgb)
                    c.create_oval(x - dot, y - dot, x + dot, y + dot, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
                label = {"f140_1": "F140 (1)", "f140_2": "F140 (2)", "D_LED1": "D_LED1",
                         "D_LED2": "D_LED2"}.get(key, key)
                c.create_text(cx, cy, text=label, fill=V.MUTED, font=("Segoe UI", 8))
            if gpu:                                             # grafika je ve skrini pod F140
                f_idx = [i for i, (k, _c) in enumerate(items) if k.startswith("f140_")] or [n_items // 2]
                x0, x1 = cell * min(f_idx) + 14, cell * (max(f_idx) + 1) - 14
                r, g, b = (round(255 * (v / 255) ** 0.5) for v in gpu[0])
                c.create_rectangle(x0, PREVIEW_H - 33, x1, PREVIEW_H - 25, outline="#262b33",
                                   fill=f"#{r:02x}{g:02x}{b:02x}")
                c.create_text((x0 + x1) / 2, PREVIEW_H - 14, text="grafika", fill=V.MUTED, font=("Segoe UI", 8))
        self.preview.after(PREVIEW_MS, self._animate)

    def _kb_preview(self, kb):
        """Barva klavesnice do nahledu na jeji strance (editor_klavesnice.py)."""
        kv = getattr(self.app, "kbd", None)
        if kv is not None:
            kv.preview(kb)

    # ---------------------------------------------------------------- stav
    def refresh(self):
        st = getattr(self.app, "lstate", None) or {}
        s = st.get("stav")
        if not self.app.running:
            text, color = "Aplikace neběží – LED se nastaví po jejím spuštění.", V.MUTED
        elif s in ("běží", "nastaveno") and st.get("chyby"):
            text, color = "● LED běží jen zčásti – " + "; ".join(st["chyby"]) + " (zkouší znovu po 30 s)", V.WARN
        elif s in ("běží", "nastaveno"):
            text, color = "● LED běží", V.OK
            p = st.get("playlist")
            if st.get("test"):
                text += " · test natočení: " + led.TEST_MODES.get(st["test"], "?")
            elif st.get("hudba"):
                text += " · ♪ hudba: " + fx.MUSIC_STYLES.get(st["hudba"].get("styl"), "?")
            elif p:
                text += (f" · playlist {p.get('i', 0) + 1}/{p.get('pocet', '?')}: "
                         f"{fx.EFFECTS.get(p.get('typ'), ('?',))[0]} (ještě {p.get('zbyva', '?')} s)")
        elif s == "chyba":
            text, color = "Chyba: " + "; ".join(st.get("chyby", [])), V.ERR
        elif s == "vypnuto":
            text, color = "Řízení LED vypnuto – ventilátory mají vlastní barvy LED.", V.MUTED
        else:
            text, color = "Stav LED uvidíš, až poběží aplikace (nová verze).", V.MUTED
        self.status.config(text=text, foreground=color)
        self._test_show()
        self._music_refresh()
