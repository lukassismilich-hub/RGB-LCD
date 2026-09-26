# editor_led.py - zalozka LED v okne nastaveni
#   - ventilatory F140 (NZXT RGB Controller): rezim, rychlost, barvy; "kazda LED zvlast" =
#     kruh s 8 LED (LED 1 u cela PC), klik = barva
#   - zony zakladni desky (Gigabyte RGB Fusion): nazev, rezim, barva, rychlost
# Zmeny se projevi po Ulozit (bezici aplikace je nastavi do par sekund).

import math
import tkinter as tk
from tkinter import colorchooser, ttk

import led

RING = 190                   # velikost kruhu s LED
DOT = 13                     # polomer jedne LED v kruhu


def _contrast(hexcol):
    r, g, b = led.hex_rgb(hexcol)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"


class LedEditor:
    def __init__(self, parent, app):
        self.app = app
        parent.columnconfigure(0, weight=1)
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        v = tk.BooleanVar(value=self.lcfg.get("zapnuto", True))
        ttk.Checkbutton(top, text="Řídit LED z aplikace", variable=v,
                        command=lambda: self.lcfg.__setitem__("zapnuto", v.get())).pack(side="left")
        self.status = ttk.Label(top, font=("Segoe UI", 10, "bold"))
        self.status.pack(side="left", padx=16)

        body = ttk.Frame(parent)
        body.grid(row=1, column=0, sticky="nsew", padx=8)
        self.fans = ttk.LabelFrame(body, text="Ventilátory F140 RGB Core (NZXT RGB Controller)")
        self.fans.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.board = ttk.LabelFrame(body, text="Základní deska (Gigabyte RGB Fusion 2.0)")
        self.board.grid(row=0, column=1, sticky="nw")
        self._build_fans()
        self._build_board()
        ttk.Label(parent, foreground="#666", justify="left", text=(
            "Změny se na LED projeví po Uložit. LED desky jinak ovládá Gigabyte Control Center (GCC) – "
            "pokud běží, nastavení desky přepíše\n(autostart_zapnout.bat ho vypne). Deska umí jen jednu barvu "
            "nebo efekt na celou zónu, každou LED zvlášť jen ventilátory F140.")).grid(
            row=2, column=0, sticky="w", padx=8, pady=(8, 0))
        self.refresh()

    @property
    def lcfg(self):
        return self.app.cfg["led"]

    # ---------------------------------------------------------- ventilatory
    def _build_fans(self):
        for w in self.fans.winfo_children():
            w.destroy()
        same = tk.BooleanVar(value=self.lcfg.get("nzxt_stejne", True))

        def on_same():
            self.lcfg["nzxt_stejne"] = same.get()
            self._build_fans()
        ttk.Checkbutton(self.fans, text="Oba ventilátory stejně", variable=same, command=on_same).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 2))
        chans = ["led1"] if same.get() else ["led1", "led2"]
        for col, name in enumerate(chans):
            fr = ttk.LabelFrame(self.fans, text="Oba F140" if same.get() else self.lcfg["nzxt"][name].get(
                "nazev", name))
            fr.grid(row=1, column=col, sticky="nw", padx=6, pady=6)
            self._channel(fr, self.lcfg["nzxt"][name])

    def _channel(self, fr, ch):
        names = {k: v[0] for k, v in led.NZXT_MODES.items()}
        mode = tk.StringVar(value=names.get(ch.get("rezim", "off"), "vypnuto"))
        ttk.Label(fr, text="Režim").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(fr, textvariable=mode, values=list(names.values()), state="readonly", width=18).grid(
            row=0, column=1, sticky="w", padx=4)
        m = ch.get("rezim", "off")
        _n, lo, hi, has_speed = led.NZXT_MODES.get(m, led.NZXT_MODES["off"])
        if has_speed:
            sp = tk.StringVar(value=led.NZXT_SPEEDS.get(ch.get("rychlost", "normal"), "normálně"))
            ttk.Label(fr, text="Rychlost").grid(row=1, column=0, sticky="w", padx=4, pady=2)
            ttk.Combobox(fr, textvariable=sp, values=list(led.NZXT_SPEEDS.values()), state="readonly",
                         width=18).grid(row=1, column=1, sticky="w", padx=4)
            rev = {v: k for k, v in led.NZXT_SPEEDS.items()}
            sp.trace_add("write", lambda *a: ch.__setitem__("rychlost", rev[sp.get()]))
        area = ttk.Frame(fr)
        area.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=6)
        if m == "super-fixed":
            self._ring(area, ch)
        elif hi > 0:
            self._color_row(area, ch, lo, hi)
        else:
            ttk.Label(area, foreground="#666", text="Barvy určuje efekt.").pack(anchor="w")

        def on_mode(*_):
            key = {v: k for k, v in names.items()}[mode.get()]
            ch["rezim"] = key
            ch.setdefault("barvy", list(led.RAINBOW))
            ch.setdefault("barvy_efekt", ["#ff0000", "#0040ff"])
            self._build_fans()
        mode.trace_add("write", on_mode)

    def _ring(self, parent, ch):
        cols = (list(ch.get("barvy", [])) + list(led.RAINBOW))[:led.LEDS_PER_FAN]
        ch["barvy"] = cols
        c = tk.Canvas(parent, width=RING, height=RING, bg="#202020", highlightthickness=0)
        c.grid(row=0, column=0, rowspan=4)
        R = RING / 2 - DOT - 18
        cx = cy = RING / 2
        rev = ch.get("obraceny_smer", False)
        c.create_oval(cx - R + DOT, cy - R + DOT, cx + R - DOT, cy + R - DOT, outline="#444")
        for i, col in enumerate(cols):
            ang = math.radians((-1 if rev else 1) * 360 * i / led.LEDS_PER_FAN)   # LED 1 vpravo (celo PC)
            x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            tag = f"led{i}"
            c.create_oval(x - DOT, y - DOT, x + DOT, y + DOT, fill=col, outline="#ddd", tags=tag)
            c.create_text(x, y, text=str(i + 1), fill=_contrast(col), font=("Segoe UI", 8, "bold"), tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, i=i: self._pick(ch, i))
        c.create_text(RING - 3, cy + DOT + 12, text="čelo PC ▸", fill="#aaa", anchor="e", font=("Segoe UI", 7))
        btns = ttk.Frame(parent)
        btns.grid(row=0, column=1, sticky="nw", padx=8)

        def all_one():
            col = colorchooser.askcolor(color=cols[0], parent=parent)[1]
            if col:
                ch["barvy"] = [col] * led.LEDS_PER_FAN
                self._build_fans()

        def rainbow():
            ch["barvy"] = list(led.RAINBOW)
            self._build_fans()

        def rotate():
            ch["barvy"] = cols[-1:] + cols[:-1]
            self._build_fans()

        def flip():
            ch["obraceny_smer"] = not rev
            self._build_fans()
        for text, cmd in (("Vše jednou barvou…", all_one), ("Duha", rainbow), ("Posunout o 1 ↻", rotate),
                          ("Obrátit směr v náhledu", flip)):
            ttk.Button(btns, text=text, command=cmd, width=22).pack(anchor="w", pady=2)
        ttk.Label(btns, foreground="#666", justify="left",
                  text="Klik na LED = barva.\nLED 1 je u čela PC.").pack(anchor="w", pady=(6, 0))

    def _pick(self, ch, i):
        col = colorchooser.askcolor(color=ch["barvy"][i], parent=self.fans)[1]
        if col:
            ch["barvy"][i] = col
            self._build_fans()

    def _color_row(self, parent, ch, lo, hi):
        # ulozeny seznam se nezkracuje - rezim s mene barvami pouzije jen prvni
        stored = ch.setdefault("barvy_efekt", ["#ff0000", "#0040ff"])
        while len(stored) < lo:
            stored.append(led.RAINBOW[len(stored) % len(led.RAINBOW)])
        cols = stored[:max(lo, min(hi, len(stored)))]
        for i, col in enumerate(cols):
            b = tk.Button(parent, text=str(i + 1), bg=col, fg=_contrast(col), width=4, relief="groove",
                          command=lambda i=i: self._pick_row(ch, i))
            b.grid(row=0, column=i, padx=2)
        if hi > 1:
            ttk.Button(parent, text="+", width=3, command=lambda: self._resize(ch, 1, lo, hi)).grid(
                row=0, column=len(cols), padx=(8, 2))
            ttk.Button(parent, text="−", width=3, command=lambda: self._resize(ch, -1, lo, hi)).grid(
                row=0, column=len(cols) + 1)

    def _pick_row(self, ch, i):
        col = colorchooser.askcolor(color=ch["barvy_efekt"][i], parent=self.fans)[1]
        if col:
            ch["barvy_efekt"][i] = col
            self._build_fans()

    def _resize(self, ch, step, lo, hi):
        cols = ch["barvy_efekt"]
        n = max(lo, min(hi, len(cols)))
        if step > 0 and n < hi:
            del cols[n:]
            cols.append(led.RAINBOW[n % len(led.RAINBOW)])
        elif step < 0 and n > max(1, lo):
            del cols[n - 1:]
        self._build_fans()

    # -------------------------------------------------------------- deska
    def _build_board(self):
        f = self.board
        for c, t in enumerate(("Zóna", "Název", "Režim", "Barva", "Rychlost")):
            ttk.Label(f, text=t, foreground="#666").grid(row=0, column=c, sticky="w", padx=4, pady=(4, 0))
        names = {k: v[0] for k, v in led.FUSION_MODES.items()}
        rev_names = {v: k for k, v in names.items()}
        rev_speed = {v: k for k, v in led.FUSION_SPEEDS.items()}
        for r in range(1, 9):
            z = self.lcfg["fusion"][f"led{r}"]
            ttk.Label(f, text=f"led{r}").grid(row=r, column=0, sticky="w", padx=4, pady=2)
            nv = tk.StringVar(value=z.get("nazev", ""))
            ttk.Entry(f, textvariable=nv, width=20).grid(row=r, column=1, padx=4)
            nv.trace_add("write", lambda *a, z=z, nv=nv: z.__setitem__("nazev", nv.get()))
            mv = tk.StringVar(value=names.get(z.get("rezim", "off"), "vypnuto"))
            ttk.Combobox(f, textvariable=mv, values=list(names.values()), state="readonly", width=15).grid(
                row=r, column=2, padx=4)
            b = tk.Button(f, text="barva", width=6, relief="groove", bg=z.get("barva", "#ffffff"),
                          fg=_contrast(z.get("barva", "#ffffff")))
            b.grid(row=r, column=3, padx=4)
            b.config(command=lambda z=z, b=b: self._pick_zone(z, b))
            sv = tk.StringVar(value=led.FUSION_SPEEDS.get(z.get("rychlost", "normal"), "normálně"))
            sc = ttk.Combobox(f, textvariable=sv, values=list(led.FUSION_SPEEDS.values()), state="readonly",
                              width=13)
            sc.grid(row=r, column=4, padx=4)
            sv.trace_add("write", lambda *a, z=z, sv=sv: z.__setitem__("rychlost", rev_speed[sv.get()]))

            def on_mode(*a, z=z, mv=mv, b=b, sc=sc):
                z["rezim"] = rev_names[mv.get()]
                self._zone_state(z, b, sc)
            mv.trace_add("write", on_mode)
            self._zone_state(z, b, sc)

    def _zone_state(self, z, b, sc):
        _n, takes_color, has_speed = led.FUSION_MODES.get(z.get("rezim", "off"), led.FUSION_MODES["off"])
        b.config(state="normal" if takes_color else "disabled")
        sc.config(state="readonly" if has_speed else "disabled")

    def _pick_zone(self, z, b):
        col = colorchooser.askcolor(color=z.get("barva", "#ffffff"), parent=self.board)[1]
        if col:
            z["barva"] = col
            b.config(bg=col, fg=_contrast(col))

    # ---------------------------------------------------------------- stav
    def refresh(self):
        st = getattr(self.app, "lstate", None) or {}
        s = st.get("stav")
        if not self.app.running:
            text, color = "Aplikace neběží – LED se nastaví po jejím spuštění.", "#666"
        elif s == "nastaveno":
            text, color = "LED nastaveny.", "#2a7"
        elif s == "chyba":
            text, color = "Chyba: " + "; ".join(st.get("chyby", [])), "#c33"
        elif s == "vypnuto":
            text, color = "Řízení LED vypnuto – LED zůstávají, jak jsou.", "#666"
        else:
            text, color = "Stav LED uvidíš, až poběží aplikace (nová verze).", "#666"
        self.status.config(text=text, foreground=color)
