# editor_klavesnice.py - stranka Klavesnice v okne nastaveni (Logitech G815)
#   - Nahled a stav: kresba klavesnice v barve, kterou ji ted pocita aplikace (stejny vypocet jako
#     zivy nahled LED - posila ho LedEditor._animate pres preview()), stav rizeni z bezici aplikace
#   - Podsviceni: rizeni z aplikace, efekt jako F140 / jako deska / vlastni (panel efektu z LedEditor), jas
#   - Integrovana pamet: stav (cte se kazde 3 s, kdyz je stranka videt), zaloha. Pamet prepina
#     vlakno LED samo podle "Ridit podsviceni z aplikace" (klavesnice.Direct).
# Zmeny se projevi po Ulozit (config["led"]["klavesnice"], ["efekt_klavesnice"]).

import os
import threading
import tkinter as tk
from tkinter import ttk

import led_efekty as fx
import vzhled as V

POLL_MS = 3000               # stav integrovane pameti (prepina ji vlakno LED v bezici aplikaci)
WRAP = 620
BODY_W = 760                 # sirka karet (sirsi okno je nenatahuje)
U = 21                       # sirka klavesy 1u v nahledu (px)
KEY_DEFAULT = {"zapnuto": False, "efekt": "deska", "jas": 100, "barva": "#ffffff"}

# rozlozeni G815 pro nahled: radky (y v u, [(x, sirka)]) - hlavni blok, sipky a navigace, numericka cast
_MAIN = [
    (0.0, [(0, 1)] + [(2 + i + i // 4 * 0.5, 1) for i in range(12)]),
    (1.4, [(i, 1) for i in range(13)] + [(13, 2)]),
    (2.4, [(0, 1.5)] + [(1.5 + i, 1) for i in range(12)] + [(13.5, 1.5)]),
    (3.4, [(0, 1.75)] + [(1.75 + i, 1) for i in range(11)] + [(12.75, 2.25)]),
    (4.4, [(0, 2.25)] + [(2.25 + i, 1) for i in range(10)] + [(12.25, 2.75)]),
    (5.4, [(0, 1.25), (1.25, 1.25), (2.5, 1.25), (3.75, 6.25), (10, 1.25), (11.25, 1.25), (12.5, 1.25),
           (13.75, 1.25)]),
]
_NAV = [(0.0, [0, 1, 2]), (1.4, [0, 1, 2]), (2.4, [0, 1, 2]), (4.4, [1]), (5.4, [0, 1, 2])]
_NUM = [(1.4, [(0, 1), (1, 1), (2, 1), (3, 1)]), (2.4, [(0, 1), (1, 1), (2, 1), (3, 1)]),
        (3.4, [(0, 1), (1, 1), (2, 1)]), (4.4, [(0, 1), (1, 1), (2, 1), (3, 1)]), (5.4, [(0, 2), (2, 1)])]
_GX, _MX, _NX, _PX = 0.0, 1.5, 17.0, 20.5       # x (u): G-klavesy, hlavni blok, navigace, numericka cast
_TOP = 1.3                                        # misto nahore pro logo a multimedia
KB_W, KB_H = int(25 * U) + 12, int((_TOP + 6.4) * U) + 12


class KeyboardEditor:
    def __init__(self, parent, app):
        self.app = app
        self._job = None                          # bezici prace s klavesnici (vlakno) a jeji vysledek
        self._mode = None                         # rezim pameti klavesnice (klavesnice.MODE_*)
        self._color = None                        # barva z nahledu LED (None = aplikace ji neridi)
        self._drawn = False
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
        self.mem = V.card(body)
        self.mem.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self._build_top()
        self._build_light()
        self._build_mem()
        self.refresh()
        self._run(self._read_mode)
        self.mem.after(POLL_MS, self._tick)

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    @property
    def kc(self):
        return self.lcfg.setdefault("klavesnice", dict(KEY_DEFAULT))

    # ------------------------------------------------------------ nahled a stav
    def _build_top(self):
        f = self.top
        f.columnconfigure(0, weight=1)
        V.card_title(f, "Klávesnice Logitech G815").grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        self.status = ttk.Label(f, font=V.FONT_B, wraplength=WRAP, justify="left")
        self.status.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))
        self.canvas = tk.Canvas(f, width=KB_W, height=KB_H, bg=V.CARD, highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 6))
        ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                  text="Náhled počítá barvu stejně jako aplikace (i s jasem). Na klávesnici se změna projeví "
                       "po Uložit.").grid(row=3, column=0, sticky="w", padx=20, pady=(0, 14))

    def preview(self, kb):
        """Barva klavesnice z ziveho nahledu LED (LedEditor._animate), None = aplikace ji neridi."""
        col = tuple(kb[0]) if kb else None
        if col == self._color and self._drawn:
            return
        self._color, self._drawn = col, True
        try:
            if not self.canvas.winfo_exists():
                return
        except tk.TclError:
            return
        self._draw(col)

    def _draw(self, rgb):
        c = self.canvas
        c.delete("all")
        if rgb is None:
            fill, line = "#1c2128", "#2a3038"
        else:
            r, g, b = (round(255 * (v / 255) ** 0.5) for v in rgb)       # LED sviti vic nez monitor (gama)
            fill, line = f"#{r:02x}{g:02x}{b:02x}", ""
        c.create_rectangle(1, 1, KB_W - 1, KB_H - 1, outline="#262b33", fill="#111418", width=1)
        pad = 3

        def key(x, y, w, h=1.0):
            x0, y0 = 6 + x * U, 6 + (y + _TOP) * U
            c.create_rectangle(x0 + pad / 2, y0 + pad / 2, x0 + w * U - pad / 2, y0 + h * U - pad / 2,
                               fill=fill, outline=line)
        for y, keys in _MAIN:
            for x, w in keys:
                key(_MX + x, y, w)
        for y, cols in _NAV:
            for x in cols:
                key(_NX + x, y, 1)
        for y, keys in _NUM:
            for x, w in keys:
                key(_PX + x, y, w, 2.0 if (y, x) in ((2.4, 3), (4.4, 3)) else 1.0)
        for i in range(5):                                            # G1-G5
            key(_GX, 1.4 + i, 1)
        for i in range(4):                                            # multimedia vpravo nahore
            key(_PX + i, -_TOP + 0.15, 1, 0.8)
        lx, ly = 6 + (_MX + 0.1) * U, 6 + 0.55 * U                    # logo G vlevo nahore
        c.create_text(lx, ly, text="G", anchor="w", fill=fill if rgb else "#3a414b",
                      font=("Segoe UI Black", 13))
        if rgb is None:
            c.create_text(KB_W / 2, KB_H / 2 + U * 0.6, fill=V.MUTED, font=V.FONT_B,
                          text="svítí podle profilu v integrované paměti")

    def refresh(self):
        """Stav z bezici aplikace (volano kazdou sekundu z App._tick)."""
        st = getattr(self.app, "lstate", None) or {}
        errs = [e for e in st.get("chyby", []) if e.startswith("klávesnice")]
        saved = self.app.saved.get("led", {})                     # bezici aplikace ma ulozene nastaveni
        kc = saved.get("klavesnice", {})
        if not kc.get("zapnuto"):
            text, color = "Klávesnice svítí podle profilu v integrované paměti (aplikace ji neřídí).", V.MUTED
        elif not saved.get("zapnuto", True):
            text, color = ("Řízení LED je vypnuté (stránka LED ventilátorů) – klávesnice svítí podle profilu "
                           "v integrované paměti."), V.WARN
        elif not self.app.running:
            text, color = "Aplikace neběží – klávesnici převezme po spuštění.", V.MUTED
        elif errs:
            text, color = "Chyba: " + "; ".join(e.split(": ", 1)[-1] for e in errs) + " (zkouší znovu po 30 s)", V.ERR
        elif st.get("stav") in ("běží", "nastaveno"):
            text, color = "● Podsvícení řídí aplikace", V.OK
        else:
            text, color = "Stav uvidíš, až poběží aplikace.", V.MUTED
        if bool(self.kc.get("zapnuto")) != bool(kc.get("zapnuto")):
            text = text.rstrip(".") + " – změna řízení se projeví po Uložit."
        self.status.config(text=text, foreground=color)

    # ------------------------------------------------------------ podsviceni
    def _build_light(self):
        f = self.light
        for w in f.winfo_children():
            w.destroy()
        kc = self.kc
        f.columnconfigure(1, weight=1)
        V.card_title(f, "Podsvícení").grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(14, 6))
        on = tk.BooleanVar(value=bool(kc.get("zapnuto")))

        def on_toggle():
            kc["zapnuto"] = on.get()
            self._build_light()
            self._show_mode()
            self.refresh()
        ttk.Checkbutton(f, text="Řídit podsvícení klávesnice z aplikace", variable=on,
                        command=on_toggle).grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(2, 4))
        if not kc.get("zapnuto"):
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                      text="Klávesnice svítí podle profilu v integrované paměti. Po zapnutí aplikace paměť sama "
                           "vypne a podsvícení počítá jako ventilátory.").grid(
                row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 16))
            return
        ttk.Label(f, text="Efekt", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=(20, 10), pady=4)
        src = tk.StringVar(value=kc.get("efekt", "deska"))

        def on_src():
            kc["efekt"] = src.get()
            self._build_light()
        V.segmented(f, src, [("f140", "jako F140"), ("deska", "jako deska"), ("vlastni", "vlastní")],
                    command=on_src).grid(row=2, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Label(f, text="Jas", style="Muted.TLabel").grid(row=3, column=0, sticky="w", padx=(20, 10), pady=4)
        jv = tk.IntVar(value=int(kc.get("jas", 100)))
        jl = ttk.Label(f, width=5, text=f"{jv.get()} %", font=V.MONO, anchor="e")
        jl.grid(row=3, column=2, sticky="e", padx=(8, 20))

        def on_jas(_e=None):
            kc["jas"] = int(jv.get())
            jl.config(text=f"{int(jv.get())} %")
        V.scale(f, variable=jv, from_=10, to=100, resolution=5, length=140, command=on_jas).grid(
            row=3, column=1, sticky="ew", pady=4)
        if kc.get("efekt") == "vlastni":
            eff = self.lcfg.setdefault("efekt_klavesnice", dict(fx.DEFAULT_EFFECT))
            pf = ttk.Frame(f)
            pf.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=20, pady=(4, 16))
            self.app.leds._effect_panel(pf, eff, 3, rebuild=self._build_light, custom_note=False)
        else:
            ttk.Label(f, style="Small.TLabel", wraplength=WRAP, justify="left",
                      text="Celá klávesnice jednou barvou – efekt se počítá jako pro jeden ventilátor "
                           f"({'F140' if kc.get('efekt') == 'f140' else 'ventilátory na desce'}, "
                           "nastavení na stránce LED ventilátorů).").grid(
                row=4, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 16))
        self._refit()

    def _refit(self):
        def fit():
            try:
                self.scroll.inner.update_idletasks()
                self.scroll._fit()
            except tk.TclError:
                pass
        self.scroll.after_idle(fit)

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
