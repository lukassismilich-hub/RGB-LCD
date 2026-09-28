# vzhled.py - tmavy vzhled okna nastaveni (podle navrhu z Claude Design)
#   - barvy, pisma, styly ttk (zaklad "clam", prebarveny)
#   - pomocne prvky: karta, nadpis karty, posuvnik, prepinac v rade (segment), rolovaci panel

import tkinter as tk
from tkinter import font as tkfont, ttk

BG = "#0f1114"          # pozadi stranky
SIDEBAR = "#13161a"
CARD = "#171a1f"        # karty
CARD_LINE = "#22272e"
FIELD = "#0f1216"       # vstupni pole
LINE = "#2c323b"
BTN = "#1d2127"
BTN_HOVER = "#252a31"
SEL = "#222831"         # vybrany radek
SEG_ON = "#262c34"
TEXT = "#e8eaed"
MUTED = "#9aa3ae"
DIM = "#7d8691"
ACCENT = "#4cc9d6"      # kapalina, pumpa, vyber
ACCENT_HOVER = "#6fd6e0"
ON_ACCENT = "#071316"
ORANGE = "#f59e42"      # ventilatory
OK = "#5fd38d"
WARN = "#f5b86a"
ERR = "#ff7a7a"

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
H1 = ("Segoe UI Semibold", 17)
H2 = ("Segoe UI Semibold", 11)
SMALL = ("Segoe UI", 9)
MONO = ("Consolas", 10)
MONO_BIG = ("Consolas", 22)


def apply(root):
    """Nastavi tmave styly pro cele okno. Volat hned po vytvoreni Tk."""
    root.configure(bg=BG)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family="Segoe UI", size=10)
        except tk.TclError:
            pass
    for pat, val in (("*TCombobox*Listbox.background", FIELD), ("*TCombobox*Listbox.foreground", TEXT),
                     ("*TCombobox*Listbox.selectBackground", SEL), ("*TCombobox*Listbox.selectForeground", TEXT),
                     ("*TCombobox*Listbox.font", FONT), ("*Menu.background", BTN), ("*Menu.foreground", TEXT),
                     ("*Menu.activeBackground", SEL), ("*Menu.activeForeground", TEXT),
                     ("*Menu.relief", "flat"), ("*Menu.font", FONT)):
        root.option_add(pat, val)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=CARD, foreground=TEXT, fieldbackground=FIELD, bordercolor=LINE,
                lightcolor=CARD, darkcolor=CARD, troughcolor=FIELD, focuscolor=ACCENT,
                selectbackground=SEL, selectforeground=TEXT, insertcolor=TEXT, font=FONT)
    s.map(".", foreground=[("disabled", DIM)])
    s.configure("TFrame", background=CARD)
    s.configure("Page.TFrame", background=BG)
    s.configure("TLabel", background=CARD, foreground=TEXT)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Small.TLabel", foreground=MUTED, font=SMALL)
    s.configure("H2.TLabel", font=H2)
    s.configure("Bold.TLabel", font=FONT_B)
    s.configure("Page.TLabel", background=BG)
    s.configure("PageMuted.TLabel", background=BG, foreground=MUTED)
    s.configure("H1.TLabel", background=BG, font=H1)

    s.configure("TButton", background=BTN, foreground=TEXT, bordercolor=LINE, lightcolor=BTN, darkcolor=BTN,
                padding=(12, 5), relief="flat", focuscolor=BTN)
    s.map("TButton", background=[("pressed", SEL), ("active", BTN_HOVER)],
          lightcolor=[("active", BTN_HOVER)], darkcolor=[("active", BTN_HOVER)])
    s.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT, bordercolor=ACCENT,
                lightcolor=ACCENT, darkcolor=ACCENT, font=FONT_B, focuscolor=ACCENT)
    s.map("Accent.TButton", background=[("active", ACCENT_HOVER)], bordercolor=[("active", ACCENT_HOVER)],
          lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)])
    s.configure("Danger.TButton", foreground=ERR)
    s.configure("TMenubutton", background=BTN, foreground=TEXT, bordercolor=LINE, lightcolor=BTN,
                darkcolor=BTN, arrowcolor=MUTED, padding=(12, 5), relief="flat")
    s.map("TMenubutton", background=[("active", BTN_HOVER)])

    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=CARD, foreground=TEXT, indicatorbackground=FIELD, indicatorforeground=ON_ACCENT,
                    upperbordercolor=LINE, lowerbordercolor=LINE, focuscolor=CARD, padding=(0, 3))
        s.map(w, background=[("active", CARD)],
              indicatorbackground=[("selected", ACCENT), ("pressed", SEL)],
              upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)])

    # prepinac v rade (segmenty) a "cipy" efektu
    s.configure("Seg.Toolbutton", background=FIELD, foreground=MUTED, padding=(14, 5), relief="flat",
                borderwidth=0, lightcolor=FIELD, darkcolor=FIELD, bordercolor=FIELD, focuscolor=FIELD)
    s.map("Seg.Toolbutton", background=[("selected", SEG_ON), ("active", BTN)],
          foreground=[("selected", TEXT), ("active", TEXT)],
          lightcolor=[("selected", SEG_ON)], darkcolor=[("selected", SEG_ON)], bordercolor=[("selected", SEG_ON)])
    s.configure("Chip.Toolbutton", background="#13161a", foreground="#c3c9d0", padding=(10, 6), relief="solid",
                borderwidth=1, bordercolor="#262b33", lightcolor="#13161a", darkcolor="#13161a",
                font=SMALL, anchor="w", focuscolor="#13161a")
    s.map("Chip.Toolbutton", background=[("selected", SEL), ("active", BTN)],
          foreground=[("selected", "#ffffff")], bordercolor=[("selected", ACCENT), ("active", LINE)],
          lightcolor=[("selected", SEL)], darkcolor=[("selected", SEL)])

    for w in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(w, fieldbackground=FIELD, foreground=TEXT, bordercolor=LINE, lightcolor=FIELD,
                    darkcolor=FIELD, arrowcolor=MUTED, background=BTN, padding=(6, 4), insertcolor=TEXT)
        s.map(w, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", FIELD)],
              fieldbackground=[("readonly", FIELD), ("disabled", CARD)],
              foreground=[("readonly", TEXT)], selectbackground=[("readonly", FIELD)],
              selectforeground=[("readonly", TEXT)], background=[("active", BTN_HOVER)])

    s.configure("TScrollbar", background=LINE, troughcolor=CARD, bordercolor=CARD, lightcolor=LINE,
                darkcolor=LINE, arrowcolor=MUTED, gripcount=0, relief="flat")
    s.map("TScrollbar", background=[("active", DIM)])
    s.configure("TSeparator", background=CARD_LINE)
    s.configure("TLabelframe", background=CARD, bordercolor=CARD_LINE, lightcolor=CARD, darkcolor=CARD)
    s.configure("TLabelframe.Label", background=CARD, foreground=MUTED, font=SMALL)
    return s


# ------------------------------------------------------------------ prvky
def card(parent, **kw):
    """Karta: tmavy panel s jemnym okrajem."""
    return tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=CARD_LINE,
                    highlightcolor=CARD_LINE, bd=0, **kw)


def card_title(parent, text, **grid):
    lbl = ttk.Label(parent, text=text, style="H2.TLabel")
    if grid:
        lbl.grid(**grid)
    return lbl


def scale(parent, **kw):
    """Posuvnik (tk.Scale kvuli 'resolution') v barvach vzhledu."""
    # tk.Scale: bg = barva jezdce, troughcolor = draha
    opts = dict(orient="horizontal", showvalue=False, bg=ACCENT, troughcolor=LINE, activebackground=ACCENT_HOVER,
                highlightthickness=0, bd=0, sliderrelief="flat", width=8, sliderlength=18)
    opts.update(kw)
    return tk.Scale(parent, **opts)


def segmented(parent, var, options, command=None, bg=CARD):
    """Prepinac v rade: options = [(hodnota, text), ...]."""
    outer = tk.Frame(parent, bg=FIELD, highlightthickness=1, highlightbackground=LINE, bd=0)
    for i, (value, text) in enumerate(options):
        ttk.Radiobutton(outer, text=text, value=value, variable=var, command=command,
                        style="Seg.Toolbutton").grid(row=0, column=i, padx=2, pady=2, sticky="ew")
        outer.columnconfigure(i, weight=1)
    return outer


def swatch(parent, color, command, text="", width=4):
    """Tlacitko s barvou (vyber barvy)."""
    b = tk.Button(parent, text=text, bg=color, activebackground=color, fg=contrast(color),
                  activeforeground=contrast(color), relief="flat", bd=0, width=width, height=1, cursor="hand2",
                  highlightthickness=1, highlightbackground=LINE, command=command, font=SMALL)
    return b


def set_swatch(b, color):
    b.config(bg=color, activebackground=color, fg=contrast(color), activeforeground=contrast(color))


def contrast(hexcol):
    h = str(hexcol).lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#000000"
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"


def listbox(parent, **kw):
    opts = dict(bg=CARD, fg=TEXT, selectbackground=SEL, selectforeground="#ffffff", activestyle="none",
                relief="flat", bd=0, highlightthickness=0, font=FONT, exportselection=False)
    opts.update(kw)
    return tk.Listbox(parent, **opts)


class ScrollFrame(tk.Frame):
    """Svisle rolovaci panel: obsah patri do self.inner. Kolecko mysi funguje, kdyz je nad nim kurzor."""

    def __init__(self, parent, bg=BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.sb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._fit)
        self.canvas.bind("<Configure>", self._fit)
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def _on_scroll(self, lo, hi):
        self.sb.set(lo, hi)
        if float(lo) <= 0 and float(hi) >= 1:
            self.sb.grid_remove()
        else:
            self.sb.grid()

    def _fit(self, _e=None):
        """Obsah na sirku panelu; na vysku aspon jako panel (kvuli roztazeni), jinak roluje."""
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        hh = max(self.inner.winfo_reqheight(), h)
        self.canvas.itemconfigure(self._win, width=w, height=hh)
        self.canvas.configure(scrollregion=(0, 0, w, hh))

    def _on_wheel(self, e):
        if self.sb.winfo_ismapped():
            w = e.widget
            if isinstance(w, str) or w.winfo_class() in ("Listbox", "TCombobox", "Text"):
                return                                  # vlastni rolovani seznamu
            self.canvas.yview_scroll(int(-e.delta / 120), "units")
