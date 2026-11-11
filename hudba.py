# hudba.py - hudba ze Spotify: co hraje (LCD Krakenu) a analyza zvuku (hudebni vizualizer LED)
#
# Vlakno Player kazdych 0,5 s precte z Windows (Global System Media Transport Controls) relaci
# Spotify - jen Spotify, jine prehravace (prohlizec, hra) se ignoruji: stav (hraje / pauza),
# nazev, interpret, album, obal a pozici ve skladbe. Z obalu vybere paletu zivych barev pro LED.
# Na zacatku kazde skladby ohlasi obrazovku "Prave hraje" (lcd_active, wake - hlavni smycka ji
# ukaze hned).
#
# Vlakno Analyzer zachytava zvuk jen procesu Spotify (zvuk_procesu.py - process loopback, hra ani
# upozorneni se nezachyti) a ~47x za sekundu z nej spocita: basy, stredy, vysky, 16 frekvencnich
# pasem (0..1 s automatickym zesilenim, pasma se spolecnou spickou - tvar spektra zustane videt).
# Udery hleda s krokem ~5 ms zvlast pro kopak, virbl a hi-hat (buben se pozna podle "tela"
# 165-400 Hz), z nich pocita tempo a fazi doby (rytmicka mrizka), energii skladby (ticha sloka x
# refren), stavbu napeti pred dropem a drop (basy se po odmlce vrati / hudba nahle zesili).
# Zachytava jen kdyz Spotify hraje a vizualizer je zapnuty. LED (led.py) si bere snimek
# s nastavitelnym zpozdenim (Bluetooth sluchatka hraji pozdeji) - led_snapshot(); diky zpozdeni
# vi o uderu predem ("next_in").
#
# Chyba tady nesmi zdrzet chlazeni ani LCD: vse ve vlastnich vlaknech, v try/except, do logu jednou.
#
# config["hudba"] (LCD): zapnuto, doba_s, po_pauze, rozvrzeni ("obal" / "cely"), prubeh, zare
# config["led"]["hudba"] (LED): zapnuto, styl, stridat, citlivost, jas, barvy ("obal" / "vlastni"),
#   paleta, zpozdeni_ms, navrat_s

import bisect
import collections
import colorsys
import io
import json
import logging
import math
import os
import threading
import time

# numpy (OpenBLAS) si pri importu zabere buffery pro kazde vlakno CPU: pri 16 vlaknech ~490 MB
# soukrome pameti a 15 vlaken navic. Analyza velke maticove vypocty nedela - staci jedno vlakno
# (zmereno 11. 11. 2026: 535 MB -> 53 MB). Musi byt nastavene pred prvnim importem numpy.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import led
import led_efekty as fx

log = logging.getLogger("rgb_lcd")

BASE = os.path.dirname(os.path.abspath(__file__))
# test z okna nastaveni ("Vyzkouset"): {"doba_s", ...} - aplikace ukaze prave hrajici skladbu na LCD
TEST_FILE = os.path.join(BASE, "hudba_test.json")

PLAYER_APP = "spotify"                 # relace Windows, jejiz AppUserModelId obsahuje tento text
PLAYER_EXE = "Spotify.exe"
COVER_RELOAD_S = (1.0, 3.0, 6.0, 10.0)   # obal nacist znovu tolik s po zmene skladby
COVER_WAIT_S = 15.0                      # dokud obal neni, zkouset kazde kolo az tak dlouho
POLL_S = 0.5
RETRY_S = 30
PLAYING = 4                            # GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing

LCD_DEFAULTS = {"zapnuto": True, "doba_s": 15, "po_pauze": False, "rozvrzeni": "obal", "prubeh": True,
                "zare": True}
LCD_LAYOUTS = {"obal": "obal a název", "cely": "obal přes celý displej"}
PAUSE_SHOW_S = 5.0                     # "po_pauze": znovu ukazat po pauze delsi nez tohle

LED_DEFAULTS = led.MUSIC_DEFAULT
DEFAULT_PALETTE = LED_DEFAULTS["paleta"]
MAX_DELAY_MS = 500
START_S = 1.0                          # Spotify hraje aspon tak dlouho -> vizualizer
FADE_S = 1.0                           # prolnuti s beznym efektem


def lcd_settings(cfg):
    out = dict(LCD_DEFAULTS)
    out.update(cfg or {})
    return out


def led_settings(cfg):
    out = dict(LED_DEFAULTS)
    out.update(cfg or {})
    return out


def music_palette(led_cfg, track):
    """Barvy hudby pro ventilatory i klavesnici: z obalu skladby, nebo vlastni paleta vizualizeru
    (config["led"]["hudba"]: barvy "obal" / "vlastni" + paleta)."""
    c = led_cfg or {}
    if c.get("barvy", "obal") == "obal" and track and track.get("paleta"):
        return list(track["paleta"])
    return [p for p in c.get("paleta", []) if isinstance(p, str)] or list(DEFAULT_PALETTE)


def _num(v, default, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------ paleta z obalu alba

def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _vivid(h, s, floor=0.75):
    """Ziva barva pro LED: plny jas, sytost aspon floor (bledsi barvy LED ukazou skoro bile)."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, floor + (1 - floor) * s, 1.0)
    return _hex((r * 255, g * 255, b * 255))


MAX_COVER_COLORS = 6
# kontrast barev: kazde dve barvy palety se lisi aspon o tolik stupnu odstinu (HSV). Uzivatel vidi
# jako podobne i 23-25 stupnu (svetle modra / tyrkysova, modra 200 / 225) a stejny odstin bledy
# a plny (na LED bledy = belavy) - proto pevne 40 stupnu, bez bledych tonu.
MIN_HUE_DEG = 40.0
LED_SATURATION = 0.85        # sytost barev na LED aspon tolik - mene syte na LED vypadaji skoro bile


def _hue_gap(h, hues):
    return min((min(abs(h - x), 1 - abs(h - x)) for x in hues), default=1.0)


def cover_palette(img, n=MAX_COVER_COLORS, sens=5, fill=True):
    """Az n (nejvys 6) zivych barev z obalu alba, nejvyraznejsi prvni (hlavni barva, pak doplnkova).
    Kazde dve barvy se lisi aspon o MIN_HUE_DEG stupnu odstinu a jsou plne syte (LED_SATURATION).
    Vynecha cernou, bilou, sedou a (pri nizsi citlivosti) hnedou - na LED vypadaji spatne.
    sens = citlivost na barvy 1..10: vyssi = vezme i malo syte a tmave barvy obalu a male plochy
    (akcenty) a chce vic barev (1 -> 2, 4 -> 3, 7 -> 4, 10 -> 5). fill = kdyz obal tolik ruznych
    odstinu nema, doplni kontrastni odstiny co nejdal od tech z obalu. Prazdny seznam = obal je
    cernobily / sedy (vychozi paleta)."""
    from PIL import Image
    n = max(1, min(MAX_COVER_COLORS, int(n)))
    c = max(1.0, min(10.0, float(sens)))
    min_s = 0.36 - 0.026 * c                             # 5 -> 0,23, 10 -> 0,10
    min_v = 0.26 - 0.016 * c                             # 5 -> 0,18, 10 -> 0,10
    area = 1.0 - 0.06 * c                                # vaha velikosti plochy: 10 -> 0,4 (akcenty)
    min_dh = MIN_HUE_DEG / 360.0
    want = min(n, 2 + round((c - 1) / 3))
    small = img.convert("RGB").resize((64, 64), Image.BILINEAR)
    q = small.quantize(colors=int(8 + 2 * c), method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    colors = [(count, colorsys.rgb_to_hsv(*(v / 255 for v in pal[idx * 3:idx * 3 + 3])))
              for count, idx in q.getcolors() or []]
    cand = [(count ** area * (0.25 + s) * (0.35 + v), h, s) for count, (h, s, v) in colors
            if v >= min_v and s >= min_s                 # cerna, seda, bila ne
            and not (c < 7 and 0.02 <= h <= 0.12 and v < 0.6 and s < 0.85)]   # hneda ne
    if not cand:                                         # tmavy / sedy obal: aspon jeho jemny nadech barvy
        total = sum(count for count, _ in colors) or 1   # (plocha aspon 2 %, jinak by to byl sum)
        cand = [(count * (0.25 + s) * (0.35 + v), h, s) for count, (h, s, v) in colors
                if v >= 0.08 and s >= 0.06 and count >= 0.02 * total]
    cand.sort(reverse=True)
    hues, out = [], []
    for _score, h, s in cand:
        if len(out) >= n:
            break
        if _hue_gap(h, hues) < min_dh:
            continue                                     # podobny odstin uz je (malo kontrastni)
        hues.append(h)
        out.append(_vivid(h, s, LED_SATURATION))
    while fill and hues and len(out) < want:             # doplnit odstin co nejdal od vsech dosavadnich
        best = max((i / 72.0 for i in range(72)), key=lambda h: _hue_gap(h, hues))
        if _hue_gap(best, hues) < min_dh:
            break
        hues.append(best)
        out.append(_vivid(best, 1.0, LED_SATURATION))
    if len(out) == 1 and not fill and c >= 10:           # jedina barva obalu, bez doplnovani: druha bila
        out.append("#ffffff")
    return out


# ------------------------------------------------------------ prehravac (Windows SMTC)

class Player:
    """Stav relace Spotify. Bezi ve vlakne Music (asyncio + WinRT)."""

    def __init__(self):
        self.playing = False
        self.track = None                 # dict: nazev, interpret, album, obal (PIL), paleta, klic
        self.pos = None                   # (pozice s, delka s, monotonic cas pozice) nebo None
        self.since = -1e9                 # od kdy plati playing (monotonic)
        self.seen = False                 # relace Spotify existuje


# ------------------------------------------------------------ analyza zvuku

class _Rise:
    """Narust energie jednoho pasma vuci prumeru posledni sekundy (krok Analyzer.OHOP) a vrchol
    narustu: r = 1 + (energie - energie pred ~16 ms) / prumer; uder = mistni vrchol r nad prahem."""

    def __init__(self, n_avg, lag):
        self.hist = collections.deque(maxlen=n_avg)
        self.sum = 0.0
        self.lag = lag
        self.r1 = self.r2 = 1.0

    def push(self, e, floor):
        """Prida energii dalsiho kroku. Vraci (r tohoto kroku, vrchol r v predchozim kroku nebo 0)."""
        h = self.hist
        if len(h) > self.lag:
            ref = min(h[-self.lag], h[-self.lag - 1])
            r = 1.0 + max(0.0, e - ref) / (self.sum / len(h) + floor)
        else:
            r = 1.0
        peak = self.r1 if (self.r1 > self.r2 and self.r1 >= r and len(h) > 20) else 0.0
        self.r2, self.r1 = self.r1, r
        if len(h) == h.maxlen:
            self.sum -= h[0]
        h.append(e)
        self.sum += e
        return r, peak


class Analyzer:
    """Z PCM (int16 stereo 48 kHz) pocita snimky s casovou znackou (cas = kdy zvuk opravdu znel).
    Urovne 0..1 s automatickym zesilenim (spicka v dB, pomalu klesa). Udery se hledaji v kratkem okne
    s krokem ~5 ms zvlast pro kopak, virbl a hi-hat (narust energie pasma), z nich tempo a faze doby
    (rytmicka mrizka), energie skladby (ticha sloka x refren), stavba napeti pred dropem a drop."""

    N = 2048                              # okno FFT pro urovne a pasma (~43 ms)
    HOP = 1024                            # krok (~21 ms = ~47 snimku za sekundu)
    BANDS = 16
    FLOOR_DB = -62.0                      # pod tim je ticho (dB vuci plne urovni)
    RANGE_DB = 26.0                       # rozsah od spicky dolu, ktery se mapuje na 0..1
    RELEASE_DB_S = 2.5                    # jak rychle klesa spicka automatickeho zesileni
    KEEP_S = 1.5                          # historie snimku (zpozdeni az 0,5 s + rezerva)
    # --- udery
    ON = 1024                             # okno pro hledani uderu (~21 ms)
    OHOP = 256                            # jeho krok (~5 ms) - 4 kroky na jeden snimek urovni
    RISE_LAG = 3                          # narust se meri proti energii pred 3-4 kroky (~16-21 ms)
    ONSET_LAG_S = 0.016                   # vrchol narustu je tolik za skutecnym zacatkem uderu (zmereno)
    HAT_RATIO = 1.15                      # prah virblu / cinelu vuci prahu uderu (vysky kolisaji vic nez basy)
    GAP_MAIN, GAP_KICK, GAP_SNARE, GAP_HAT = 0.15, 0.15, 0.10, 0.07     # nejmensi odstup uderu (s)
    NEAR_S = 0.04                         # telo, basy a vysky jednoho bubnu prijdou nejvys takhle po sobe
    SNARE_STEPS = 6                       # virbl se rozhodne az za 6 kroku (~32 ms): neprijde jeste kopak?
    HAT_STEPS = 9                         # hi-hat za 9 kroku (~48 ms): nepatri k bubnu?
    SUB_KICK = 10.0                       # kopak bez "tela" (jen hluboke basy): prah narustu tolikrat vys
    NO_DRUMS_S = 2.0                      # bez kopaku a virblu tak dlouho -> udery i z melodie (stredy)
    FLOORS = {"k": 0.02, "b": 0.01, "m": 0.02, "h": 0.0005}      # nejmensi jmenovatel = podil celkoveho vykonu
    XMAX_S = 4.0                          # nejsilnejsi nedavny narust pasma klesa s touto casovou konstantou
    XMAX_CLIP = 10.0                      # ... a nepocita se vic nez tolik (prvni uder po tichu je obrovsky)
    HAT_FRAC = 0.15                       # hi-hat: aspon tolik nejsilnejsiho nedavneho narustu vysek
    # --- tempo a faze (rytmicka mrizka)
    OSS_S = 8.0                           # z kolika sekund narustu se pocita tempo
    OSS_MIN_S = 4.0                       # nejmene tolik, nez se tempo zacne pocitat
    TEMPO_EVERY_S = 0.5
    BPM_MIN, BPM_MAX = 70.0, 185.0
    HALF_RATIO = 0.7                      # dvojnasobne tempo, kdyz je pulka periody aspon takhle silna
    GRID_OK = 0.5                         # jistota mrizky, od ktere se s ni pocita (predjimani, doplneni uderu)
    GRID_EASE = 0.6                       # o kolik je prah uderu nizsi tam, kde mrizka uder ceka
    # --- energie skladby, stavba napeti, drop
    ENERGY_RANGE_DB = 10.0                # tolik dB pod hlasitymi castmi skladby = energie 0
    ENERGY_FALL_DB_S = 0.08               # jak rychle klesa uroven "hlasite casti" (pomalu - sloka zustane tissi)
    BUILD_SLOPE_DB_S = 1.5                # stoupani stredu a vysek, ktere uz je plna stavba napeti
    DROP_BASS_RATIO = 6.0                 # drop: basy se vrati aspon tolikrat silnejsi nez pred tim
    DROP_GAP_S = 8.0
    # --- pasma: spolecna spicka -> tvar spektra zustane videt (drive melo kazde pasmo vlastni zesileni
    # a spektrum svitilo skoro porad naplno; stejny princip jako klavesnice_efekty.Levels)
    BAND_TILT_DB = 0.8                    # dB na pasmo navic k vyskam (hudba ma ve vyskach mene energie)
    BAND_SHAPE = 0.25                     # vrchol pasma = jeho spicka + tento dil odstupu od spolecne spicky
    BAND_PEAK_FALL_DB_S = 2.5             # (0 = kazde pasmo zvlast jako drive, 1 = jen spolecna spicka)

    def __init__(self):
        import numpy as np
        self.np = np
        from zvuk_procesu import RATE
        self.rate = RATE
        self.win = np.hanning(self.N).astype(np.float32)
        norm = (self.win.sum() / 2) ** 2                 # plna sinusovka = 0 dB
        self.norm = norm
        f = np.fft.rfftfreq(self.N, 1 / RATE)

        def rng(lo, hi, fr=f):
            a, b = np.searchsorted(fr, lo), np.searchsorted(fr, hi)
            return (int(a), int(max(a + 1, b)))
        self.r_bass, self.r_mid, self.r_high, self.r_all = rng(30, 160), rng(160, 2000), rng(2000, 12000), \
            rng(30, 16000)
        self.r_top = rng(500, 12000)                     # stredy a vysky bez basu (stavba napeti)
        edges = np.geomspace(40, 14000, self.BANDS + 1)
        self.r_bands = [rng(edges[i], edges[i + 1]) for i in range(self.BANDS)]
        # hledani uderu: kratke okno, pasma kopak (jen do ~117 Hz - telo virblu kolem 190 Hz by se
        # v kratkem okne pletlo s kopakem) / telo virblu / stredy / vysky / vse
        self.owin = np.hanning(self.ON).astype(np.float32)
        self.onorm = (self.owin.sum() / 2) ** 2
        fo = np.fft.rfftfreq(self.ON, 1 / RATE)
        self.o_bands = {"k": rng(30, 120, fo), "b": rng(165, 400, fo), "m": rng(165, 2000, fo),
                        "h": rng(2000, 12000, fo), "a": rng(30, 16000, fo)}
        self.o_rate = RATE / self.OHOP
        self.o_starts = [self.N - self.ON - (3 - j) * self.OHOP for j in range(self.HOP // self.OHOP)]
        self.oss_len = int(self.OSS_S * self.o_rate)
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        np = self.np
        self.track_changed = False
        self.buf = np.zeros(0, dtype=np.float32)
        self.side = np.zeros(0, dtype=np.float32)        # (L - R) / 2 - stereo (do stran skrine)
        self.bal = 0.0
        self.ref = {}                                     # spicka (dB) pro automaticke zesileni
        self.env = {}                                     # obalky 0..1
        self.bpk = {}                                     # pasma: spicka (dB) - tvar spektra
        n1 = int(self.o_rate)                             # 1 s kroku hledani uderu
        self.rise = {k: _Rise(n1, self.RISE_LAG) for k in "kbmh"}
        self.all_hist = collections.deque(maxlen=n1)      # celkovy vykon za 1 s (krok OHOP)
        self.all_sum = 0.0
        self.xmax = {k: 0.0 for k in "kbmh"}              # nejsilnejsi nedavny narust pasma (pomalu klesa)
        self.pend = []                                    # vysky cekajici na rozhodnuti [kroky, t, sila]
        self.b_wait = []                                  # telo bubnu cekajici, jestli je to virbl [kroky, t, sila]
        self.k_wait = None                                # narust basu cekajici na telo (t, sila)
        self.last_main = self.last_kick = self.last_snare = self.last_hat = self.last_drum = -1e9
        self.last_body = -1e9
        self.last_beat = -1e9
        self.oss = np.zeros(self.oss_len, dtype=np.float32)      # sila narustu po krocich (pro tempo)
        self.oss_n = 0
        self.oss_since = 0
        self.g_T = None                                   # perioda doby (s), None = mrizka zatim neni
        self.g_t = 0.0                                    # cas posledni doby mrizky
        self.g_n = 0                                      # poradi doby
        self.g_conf = 0.0
        self.g_switch = self.g_flip = 0
        self.g_bar = 0                                    # ktera doba (g_n % 4) je prvni v taktu
        self.bar_acc = [0.0] * 4
        self.short_db = collections.deque(maxlen=70)      # celkovy vykon ~1,5 s
        self.long_db = collections.deque(maxlen=560)      # ~12 s
        self.bass_pw = collections.deque(maxlen=118)      # vykon basu ~2,5 s (drop = basy se vrati)
        self.bass_ref = 0.0                               # jak silne basy skladba miva (pomalu klesa)
        self.top_hist = collections.deque(maxlen=141)     # stredy + vysky v dB ~3 s (stoupani = stavba napeti)
        self.top_db = None
        self.hi_times = collections.deque(maxlen=64)      # casy virblu a hi-hatu (zhustovani = stavba napeti)
        self.e_ref = None                                 # uroven hlasitych casti skladby (dB)
        self.energy = 1.0
        self.build = 0.0
        self.last_drop = -1e9
        self.ibi = collections.deque(maxlen=8)            # intervaly mezi udery (tempo, nez je mrizka)
        self.phase = 0.0
        self.quiet_since = None
        with self.lock:
            self.frames = collections.deque()             # (t, snimek)
            self.beats = collections.deque(maxlen=24)     # hlavni udery - kopak nebo virbl (t, sila, poradi)
            self.kicks = collections.deque(maxlen=16)     # jen kopak
            self.snares = collections.deque(maxlen=24)    # jen virbl
            self.hihats = collections.deque(maxlen=32)    # jen hi-hat / cinely
            self.hats = collections.deque(maxlen=32)      # virbl i cinely dohromady ("beats_hi")
            self.drops = collections.deque(maxlen=8)      # (t, poradi)
            self.beat_n = self.drop_n = self.hat_n = self.kick_n = self.snare_n = self.hihat_n = 0

    def new_track(self):
        """Nova skladba: tempo, mrizku a dlouhodoby prumer (drop) pocitat znovu, at se neprenesou
        z predchozi; uroven hlasitych casti jen o kus niz (Spotify hlasitost skladeb vyrovnava).
        Vola se z vlakna prehravace - jen si to poznamena, provede to vlakno zvuku v feed()."""
        self.track_changed = True

    def _new_track(self):
        self.track_changed = False
        self.ibi.clear()
        self.long_db.clear()
        self.short_db.clear()
        self.oss_n = 0
        self.g_T, self.g_conf, self.g_switch, self.g_flip = None, 0.0, 0, 0
        self.bar_acc = [0.0] * 4
        self.build = 0.0
        if self.e_ref is not None:
            self.e_ref -= 3.0

    def _db(self, p, r):
        return 10 * math.log10(float(p[r[0]:r[1]].sum()) / self.norm + 1e-12)     # vykon pasma, plna sinusovka ~0 dB

    def _level(self, name, db, dt, gamma):
        ref = max(db, self.ref.get(name, self.FLOOR_DB + self.RANGE_DB) - self.RELEASE_DB_S * dt,
                  self.FLOOR_DB + self.RANGE_DB * 0.6)
        self.ref[name] = ref
        return max(0.0, min(1.0, (db - (ref - self.RANGE_DB)) / self.RANGE_DB)) ** gamma

    def _envelope(self, name, v, dt, tau):
        e = max(v, self.env.get(name, 0.0) * math.exp(-dt / tau))
        self.env[name] = e
        return e

    def _band_levels(self, bdb, dt, gamma):
        """16 pasem 0..1: spicka kazdeho pasma se posune ke spolecne spicce vsech pasem, takze pasma, ktera
        jsou v hudbe slabsi, zustanou niz a tvar spektra je videt (nejsilnejsi pasmo se chova jako drive)."""
        floor = self.FLOOR_DB + self.RANGE_DB * 0.6
        pks = []
        for i, db in enumerate(bdb):
            db += self.BAND_TILT_DB * i
            pk = max(db, self.bpk.get(i, self.FLOOR_DB + self.RANGE_DB) - self.BAND_PEAK_FALL_DB_S * dt, floor)
            self.bpk[i] = pk
            pks.append((db, pk))
        g = max(pk for _db, pk in pks)
        return [max(0.0, min(1.0, (db - (pk + self.BAND_SHAPE * (g - pk) - self.RANGE_DB)) / self.RANGE_DB)) ** gamma
                for db, pk in pks]

    # ---------------------------------------------------------------- udery (krok ~5 ms)

    def _expected(self, t):
        """Ceka mrizka v case t uder? (jista mrizka, do 8 % periody od doby)"""
        if not self.g_T or self.g_conf < self.GRID_OK:
            return False
        x = ((t - self.g_t) / self.g_T) % 1.0
        return min(x, 1.0 - x) < 0.08

    def _main(self, t, k):
        if t - self.last_main < self.GAP_MAIN:
            return
        if t - self.last_beat < 2.0:
            self.ibi.append(t - self.last_beat)
        self.last_beat = self.last_main = t
        with self.lock:
            self.beat_n += 1
            self.beats.append((t, k, self.beat_n))

    @staticmethod
    def _strength(x, top):
        """Sila uderu 0,35..1 podle narustu x vuci nejsilnejsimu nedavnemu narustu pasma."""
        return max(0.35, min(1.0, 0.3 + 0.7 * x / max(top, x, 1e-9)))

    def _kick(self, t, k):
        self.last_kick = self.last_drum = t
        self.k_wait = None
        with self.lock:
            self.kick_n += 1
            self.kicks.append((t, k, self.kick_n))
        if self.g_T and self.g_conf >= 0.4:               # ktera doba taktu miva kopak nejsilnejsi
            i = (self.g_n + int(round((t - self.g_t) / self.g_T))) % 4
            self.bar_acc = [a * 0.97 for a in self.bar_acc]
            self.bar_acc[i] += k
            best = max(range(4), key=lambda q: self.bar_acc[q])
            if self.bar_acc[best] > 1.25 * self.bar_acc[self.g_bar]:
                self.g_bar = best

    def _high(self, t, k, snare):
        """Virbl (snare=True) nebo hi-hat / cinel."""
        if snare:
            if t - self.last_snare < self.GAP_SNARE:
                return
            self.last_snare = t
        elif t - self.last_hat < self.GAP_HAT:
            return
        with self.lock:
            if snare:
                self.snare_n += 1
                self.snares.append((t, k, self.snare_n))
            else:
                self.hihat_n += 1
                self.hihats.append((t, k, self.hihat_n))
            if t - self.last_hat >= self.GAP_HAT:
                self.hat_n += 1
                self.hats.append((t, k, self.hat_n))
        self.hi_times.append(t)
        self.last_hat = max(self.last_hat, t)

    def _onsets(self, p4, t_end, beat_c, frac):
        """Kroky hledani uderu (p4 = vykonove spektrum kratkych oken, posledni konci v t_end).
        Vrchol narustu pasma je "silny", kdyz je nad prahem beat_c a zaroven ma aspon frac nejsilnejsiho
        nedavneho narustu tehoz pasma (xmax) - vlneni basu vedle silneho kopaku uder neni.
        Buben se pozna podle "tela" (165-400 Hz - maji ho kopak i virbl, vlnici se bas a hi-hat ne):
        silne telo = hlavni uder; se silnym narustem basu je to kopak, bez nej virbl. Narust jen ve
        vyskach = hi-hat / cinel."""
        hat_c = beat_c * self.HAT_RATIO
        sub_c = 1 + (beat_c - 1) * self.SUB_KICK
        abs_floor = 10 ** ((self.FLOOR_DB + 6) / 10)
        xmax = self.xmax
        near = self.NEAR_S
        dec = math.exp(-self.OHOP / self.rate / self.XMAX_S)
        en = {k: (p4[:, r[0]:r[1]].sum(axis=1) / self.onorm).tolist() for k, r in self.o_bands.items()}
        steps = len(en["a"])
        for j in range(steps):
            te = t_end - (steps - 1 - j) * self.OHOP / self.rate
            ea = en["a"][j]
            if len(self.all_hist) == self.all_hist.maxlen:
                self.all_sum -= self.all_hist[0]
            self.all_hist.append(ea)
            self.all_sum += ea
            avg_all = self.all_sum / len(self.all_hist)
            r, pk = {}, {}
            for k in "kbmh":
                r[k], pk[k] = self.rise[k].push(en[k][j], self.FLOORS[k] * avg_all + abs_floor)
            t_ev = te - self.OHOP / self.rate - self.ONSET_LAG_S        # vrchol byl v predchozim kroku
            loud = avg_all > abs_floor
            x = {k: min(self.XMAX_CLIP, pk[k] - 1.0) if pk[k] else 0.0 for k in "kbmh"}
            top = dict(xmax)                                         # nejsilnejsi narust pred timto krokem
            for k in "kbmh":
                xmax[k] = max(xmax[k] * dec, x[k] if loud else 0.0)
            ease = self.GRID_EASE if (pk["k"] or pk["b"]) and self._expected(t_ev) else 1.0
            c = 1 + (beat_c - 1) * ease
            strong = {k: bool(pk[k]) and loud and pk[k] > c and x[k] >= frac * ease * top[k] for k in "kbm"}
            # telo bubnu: hlavni uder; kopak, kdyz k nemu patri silny narust basu, jinak (za chvili) virbl
            if strong["b"]:
                kb = self._strength(x["b"], top["b"])
                self.last_body = self.last_drum = t_ev
                self._main(t_ev, kb)
                if self.k_wait and t_ev - self.k_wait[0] <= near:
                    self._kick(*self.k_wait)
                elif t_ev - self.last_kick > near:
                    self.b_wait.append([self.SNARE_STEPS, t_ev, kb])
            # kopak: silny narust basu s telem; bez tela jen hodne silny (hluboky kopak)
            if strong["k"] and t_ev - self.last_kick >= self.GAP_KICK:
                kk = self._strength(x["k"], top["k"])
                if t_ev - self.last_body <= near:
                    self._kick(t_ev, kk)
                elif pk["k"] > sub_c:
                    self._kick(t_ev, kk)
                    self._main(t_ev, kk)
                else:
                    self.k_wait = (t_ev, kk)                         # pocka, jestli prijde telo
            if self.k_wait and t_ev - self.k_wait[0] > near:
                self.k_wait = None
            for q in self.b_wait:
                q[0] -= 1
            while self.b_wait and self.b_wait[0][0] <= 0:
                _s, tb, kb = self.b_wait.pop(0)
                if abs(tb - self.last_kick) > near:                  # telo bez kopaku = virbl
                    self._high(tb, kb, True)
            # vysky: hi-hat / cinel, pokud nepatri k bubnu (rozhodne se az za chvili)
            if pk["h"] and loud and pk["h"] > hat_c and x["h"] >= self.HAT_FRAC * top["h"]:
                self.pend.append([self.HAT_STEPS, t_ev, self._strength(x["h"], top["h"])])
            for q in self.pend:
                q[0] -= 1
            while self.pend and self.pend[0][0] <= 0:
                _s, th, kh = self.pend.pop(0)
                if abs(th - self.last_body) > near + 0.005 and abs(th - self.last_kick) > near + 0.005:
                    self._high(th, kh, False)
            # bez bicich: udery z nastupu melodie / akordu (stredy)
            if (strong["m"] and pk["m"] > beat_c * 1.1 and t_ev - self.last_drum > self.NO_DRUMS_S
                    and t_ev - self.last_main >= 0.25):
                self._main(t_ev, 0.85 * self._strength(x["m"], top["m"]))
            # sila narustu pro tempo
            self.oss[self.oss_n % self.oss_len] = (min(4.0, r["k"] - 1) + min(4.0, r["b"] - 1)
                                                   + 0.6 * min(4.0, r["h"] - 1) + 0.3 * min(4.0, r["m"] - 1))
            self.oss_n += 1
            self.oss_since += 1
            if self.g_T:
                while te - self.ONSET_LAG_S >= self.g_t + self.g_T:
                    self.g_t += self.g_T
                    self.g_n += 1
            if self.oss_since >= self.TEMPO_EVERY_S * self.o_rate and self.oss_n >= self.OSS_MIN_S * self.o_rate:
                self.oss_since = 0
                self._tempo(te - self.ONSET_LAG_S)

    # ---------------------------------------------------------------- tempo a faze doby

    def _tempo(self, t_last):
        """Tempo (autokorelace sily narustu za poslednich az 8 s) a faze doby; t_last = cas posledniho kroku."""
        np = self.np
        W = min(self.oss_n, self.oss_len)
        i = self.oss_n % self.oss_len
        x = np.concatenate((self.oss[i:], self.oss[:i])) if self.oss_n >= self.oss_len else self.oss[:W].copy()
        x = np.maximum(x, 0.0)
        if float(x.max()) < 0.3:                          # ticho / zadne nastupy
            self.g_conf *= 0.7
            return
        xm = x - x.mean()
        F = np.fft.rfft(xm, 4096)
        acf = np.fft.irfft(F * np.conj(F))[:W]
        lmin, lmax = int(round(60 / self.BPM_MAX * self.o_rate)), int(round(60 / self.BPM_MIN * self.o_rate))
        maxlag = min(W * 6 // 10, 4 * lmax + 2)
        acf = acf[:maxlag + 1] / (W - np.arange(maxlag + 1))
        if acf[0] <= 0:
            return
        acf = acf / acf[0]
        ls = np.arange(lmin, lmax + 1)
        s = acf[ls].copy()
        wsum = np.ones(len(ls))
        for m, w in ((2, 0.5), (3, 0.33), (4, 0.25)):     # perioda sedi i na nasobcich (takt)
            idx = m * ls
            ok = idx + 1 <= maxlag
            ic = np.minimum(idx, maxlag - 1)
            v = np.maximum(acf[ic - 1], np.maximum(acf[ic], acf[ic + 1]))
            s += np.where(ok, w * v, 0.0)
            wsum += np.where(ok, w, 0.0)
        s /= wsum
        bpm = 60.0 * self.o_rate / ls
        s *= np.exp(-0.5 * np.log2(bpm / 120.0) ** 2)     # mirna prednost tempum kolem 120
        xs = x.copy()                                     # narust s toleranci +-1 krok (pro fazi)
        xs[1:-1] = np.maximum(x[1:-1], np.maximum(x[:-2], x[2:]))

        def fit(L):
            """Jak perioda L (kroku) sedi na nastupy: (faze = kroku od posledni doby, kontrast 0..1,
            kolik narustu za jednotku casu na doby pripadne - mrizka 2 : 3 jich chyti mnohem min)."""
            nph = int(math.ceil(L))
            kmax = int((W - 1 - nph) / L)
            if kmax < 3:
                return None
            idx = np.rint((W - 1) - np.arange(nph)[:, None] - np.arange(kmax + 1)[None, :] * L).astype(int)
            sc = xs[idx].sum(axis=1)
            p = int(np.argmax(sc))
            return p, float((sc[p] - sc.mean()) / (sc[p] + 1e-9)), float(sc[p]) / ((kmax + 1) * L)

        def half(q):                                      # index pulky periody (dvojnasobne tempo), nebo -1
            if ls[q] // 2 < lmin:
                return -1
            h = max(1, min(len(ls) - 2, int(round(ls[q] / 2)) - lmin))
            return h - 1 + int(np.argmax(acf[ls[h] - 1:ls[h] + 2]))
        b = int(np.argmax(s))
        h = half(b)                                       # dvojnasobne tempo (DnB 174 misto 87), kdyz je pulka
        if h >= 0 and acf[ls[h]] >= self.HALF_RATIO * acf[ls[b]]:      # periody dost silna
            b = h
        lc = int(round(self.g_T * self.o_rate)) - lmin if self.g_T else -1
        if 0 <= lc < len(ls):                             # mrizka uz bezi: drzet se ji
            a0, a1 = max(0, lc - 3), min(len(ls), lc + 4)
            loc = a0 + int(np.argmax(s[a0:a1]))
            ratio = ls[b] / ls[loc]
            if abs(b - loc) <= 3:
                self.g_switch = 0
            elif abs(ratio - round(ratio)) < 0.06 * ratio and round(ratio) >= 2:
                b = loc                                   # pomalejsi nasobek (polovicni rytmus) = porad stejna mrizka
                self.g_switch = 0
            else:
                if abs(ratio - 0.5) < 0.03:               # dvakrat rychlejsi: staci, kdyz je dost silne
                    better = acf[ls[b]] >= self.HALF_RATIO * acf[ls[loc]]
                else:                                     # jine tempo: musi jasne vyhravat a chytit vic nastupu
                    fb, fl_ = fit(float(ls[b])), fit(float(ls[loc]))
                    better = s[b] >= 1.2 * s[loc] and fb is not None and (fl_ is None or fb[2] > fl_[2])
                self.g_switch = self.g_switch + 1 if better else 0
                if self.g_switch < 3:                     # ... a to trikrat po sobe (1,5 s)
                    b = loc
                else:
                    self.g_switch = 0
        L = float(ls[b])
        if 0 < b < len(ls) - 1:                           # jemne doladeni periody (parabola pres vrchol)
            y0, y1, y2 = float(s[b - 1]), float(s[b]), float(s[b + 1])
            den = y0 - 2 * y1 + y2
            if den < 0:
                L += max(-0.5, min(0.5, 0.5 * (y0 - y2) / den))
        f = fit(L)                                        # faze: posun, pri kterem na doby pripadne nejvic narustu
        if f is None:
            return
        ph, contrast, _cap = f
        conf =max(0.0, min(1.0, (contrast - 0.3) / 0.4)) * max(0.0, min(1.0, float(acf[ls[b]]) / 0.2))
        T = L / self.o_rate
        anchor = t_last - ph / self.o_rate
        if self.g_T is None or abs(T / self.g_T - 1) > 0.06:
            self.g_T, self.g_t, self.g_flip = T, anchor, 0
        else:
            self.g_T += 0.3 * (T - self.g_T)
            e = ((anchor - self.g_t + self.g_T / 2) % self.g_T) - self.g_T / 2
            if abs(e) < 0.2 * self.g_T:
                self.g_t += 0.5 * e
                self.g_flip = 0
            else:                                         # faze jinde (napr. o pul doby): az kdyz to trva
                self.g_flip += 1
                if self.g_flip >= 3:
                    self.g_t, self.g_flip = self.g_t + e, 0
        self.g_conf += (conf - self.g_conf) * 0.5

    # ---------------------------------------------------------------- hlavni smycka

    def feed(self, pcm, now, sens=5):
        """Pridat PCM (bytes) zachycene ted; spocita vsechny cele kroky."""
        np = self.np
        if self.track_changed:
            self._new_track()
        if pcm:
            x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            sd = (x[0::2] - x[1::2]) * (0.5 / 32768.0)
            x = (x[0::2] + x[1::2]) * (0.5 / 32768.0)
            self.buf = np.concatenate((self.buf, x))
            self.side = np.concatenate((self.side, sd))
        dt = self.HOP / self.rate
        gamma = fx.music_gamma(sens)                      # citlivost: vyssi = vyraznejsi reakce na tichsi
        beat_c = fx.beat_ratio(sens)                      # prah uderu vuci prumeru pasma
        frac = fx.beat_share(sens)                        # ... a vuci nejsilnejsim nedavnym uderum
        while len(self.buf) >= self.N:
            left = len(self.buf) - self.N                 # vzorky za timto oknem (zachycene pozdeji)
            t_end = now - left / self.rate                # konec okna
            t = t_end - self.N / 2 / self.rate            # snimek plati pro stred okna
            frame = self.buf[:self.N]
            sframe = self.side[:self.N]
            self.buf = self.buf[self.HOP:]
            self.side = self.side[self.HOP:]
            o = np.stack([frame[a:a + self.ON] for a in self.o_starts]) * self.owin
            self._onsets(np.abs(np.fft.rfft(o, axis=1)) ** 2, t_end, beat_c, frac)
            p = np.abs(np.fft.rfft(frame * self.win)) ** 2
            if len(sframe) == len(frame):                 # stereo: -1 = jen levy kanal, +1 = jen pravy
                pl = float(np.mean((frame + sframe) ** 2))
                pr = float(np.mean((frame - sframe) ** 2))
                b = (pr - pl) / (pl + pr + 1e-12)
                self.bal += (b - self.bal) * min(1.0, dt / 0.08)
            db_all = self._db(p, self.r_all)
            snap = {}
            raw = {"level": round(db_all, 1)}                  # surove urovne v dB (efekty klavesnice si je
            for name, r, tau in (("bass", self.r_bass, 0.12), ("mid", self.r_mid, 0.25),   # normuji samy)
                                 ("high", self.r_high, 0.08)):
                db = self._db(p, r)
                raw[name] = round(db, 1)
                snap[name] = self._envelope(name, self._level(name, db, dt, gamma), dt, tau)
            snap["level"] = self._envelope("level", self._level("all", db_all, dt, gamma), dt, 0.3)
            snap["stereo"] = round(self.bal, 3)
            bdb = [self._db(p, r) for r in self.r_bands]
            snap["bands"] = [round(self._envelope(f"b{i}", v, dt, 0.15), 3)
                             for i, v in enumerate(self._band_levels(bdb, dt, gamma))]
            snap["bands_db"] = [round(db, 1) for db in bdb]
            snap["db"] = raw
            self._sections(p, db_all, t, dt)
            snap["energy"] = round(self.energy, 3)
            snap["build"] = round(self.build, 3)
            bpm = 0.0
            if self.g_T:
                bpm = 60.0 / self.g_T
            elif len(self.ibi) >= 4:                       # mrizka jeste neni: z odstupu uderu
                bpm = 60.0 / sorted(self.ibi)[len(self.ibi) // 2]
                while bpm > self.BPM_MAX:
                    bpm /= 2
            snap["grid"] = round(self.g_conf, 2) if self.g_T else 0.0
            snap["g_t"], snap["g_T"], snap["g_n"], snap["g_bar"] = self.g_t, self.g_T or 0.0, self.g_n, self.g_bar
            # faze otaceni barev: rychleji pri hlasitejsi hudbe a rychlejsim tempu
            speed = (0.08 + 0.35 * snap["mid"] + 0.2 * snap["level"]) * ((bpm / 120.0) if bpm else 1.0)
            self.phase = (self.phase + dt * speed) % 1000.0
            snap["phase"] = self.phase
            snap["bpm"] = round(bpm, 1)
            if db_all < self.FLOOR_DB:
                self.quiet_since = self.quiet_since or t
            else:
                self.quiet_since = None
            snap["quiet"] = bool(self.quiet_since is not None and t - self.quiet_since > 1.5)
            with self.lock:
                self.frames.append((t, snap))
                while self.frames and t - self.frames[0][0] > self.KEEP_S:
                    self.frames.popleft()

    def _sections(self, p, db_all, t, dt):
        """Energie skladby (ticha sloka x refren), stavba napeti pred dropem a drop."""
        pw = 10 ** (db_all / 10)                           # prumery z vykonu, ne z dB (mezery mezi udery)
        self.short_db.append(pw)
        self.long_db.append(pw)
        s_avg = 10 * math.log10(sum(self.short_db) / len(self.short_db) + 1e-12)
        # energie: kratkodoba hlasitost vuci hlasitym castem skladby
        if len(self.short_db) >= 24 and s_avg > self.FLOOR_DB + 6:
            if self.e_ref is None:
                self.e_ref = s_avg
            elif s_avg > self.e_ref:
                self.e_ref += (s_avg - self.e_ref) * min(1.0, dt / 0.5)
            else:                                          # dlouho uplne dole = uroven je moc vysoko -> rychleji
                self.e_ref -= dt * (1.0 if s_avg < self.e_ref - self.ENERGY_RANGE_DB - 3 else self.ENERGY_FALL_DB_S)
            e = max(0.0, min(1.0, (s_avg - (self.e_ref - self.ENERGY_RANGE_DB)) / self.ENERGY_RANGE_DB))
            self.energy += (e - self.energy) * min(1.0, dt / (0.3 if e > self.energy else 1.5))
        # basy: jsou tu, nebo vypadly (pred dropem)?
        bp = float(p[self.r_bass[0]:self.r_bass[1]].sum()) / self.norm
        self.bass_pw.append(bp)
        bl = list(self.bass_pw)
        b_1s = sum(bl[-47:]) / len(bl[-47:])
        self.bass_ref = max(b_1s, self.bass_ref * 10 ** (-0.02 * dt))         # klesa 0,2 dB/s
        gone = max(0.0, min(1.0, (10 * math.log10((self.bass_ref + 1e-12) / (b_1s + 1e-12)) - 4.0) / 6.0))
        sd = list(self.short_db)[-47:]                     # ... a to doopravdy: tvori jen maly dil vykonu
        share = b_1s / (sum(sd) / len(sd) + 1e-12)         # (tissi cast skladby s basy "bez basu" neni)
        gone = min(gone, max(0.0, min(1.0, (0.3 - share) / 0.2)))
        # stavba napeti: stredy a vysky stoupaji, bubny houstnou, basy chybi
        tdb = self._db(p, self.r_top)
        self.top_db = tdb if self.top_db is None else self.top_db + (tdb - self.top_db) * min(1.0, dt / 0.4)
        self.top_hist.append(self.top_db)
        target = 0.0
        if len(self.top_hist) == self.top_hist.maxlen and s_avg > self.FLOOR_DB + 10:
            th = list(self.top_hist)
            m0, m1, m2 = sum(th[:47]) / 47, sum(th[47:94]) / 47, sum(th[-47:]) / 47
            slope = (m2 - m0) / 2.0                        # dB/s za posledni ~3 s
            if not m0 < m1 < m2:                           # musi stoupat celou dobu, ne jen poskocit
                slope = 0.0
            n1 = sum(1 for x in self.hi_times if t - 1.0 < x <= t)
            n0 = sum(1 for x in self.hi_times if t - 2.0 < x <= t - 1.0)
            dense = max(0.0, min(1.0, (n1 - n0) / 4.0)) if n1 >= 4 else 0.0
            target = max(0.0, min(1.0, slope / self.BUILD_SLOPE_DB_S)) * (0.25 + 0.75 * gone) + 0.5 * dense * gone
            target = max(0.0, min(1.0, target))
        self.build += (target - self.build) * min(1.0, dt / (1.2 if target > self.build else 0.4))
        # drop: basy se po odmlce vrati, nebo hudba (s basy) nahle vyrazne zesili
        if len(bl) >= 100 and t - self.last_drop > self.DROP_GAP_S and s_avg > self.FLOOR_DB + 10:
            b_now = sum(bl[-12:]) / 12
            b_before = sum(bl[:-12]) / len(bl[:-12])
            back = b_now > self.DROP_BASS_RATIO * b_before and b_now > 0.35 * sum(list(self.short_db)[-12:]) / 12
            loud = False
            if len(self.long_db) > 200 and gone < 0.3 and self.build < 0.3:
                l_avg = 10 * math.log10(sum(self.long_db) / len(self.long_db) + 1e-12)
                loud = s_avg - l_avg > 4.5
            if back or loud:
                td = self.last_kick if t - self.last_kick < 0.4 else t - 0.15
                self.last_drop = t
                self.build = 0.0
                if self.g_T:                               # drop = prvni doba taktu
                    self.g_bar = (self.g_n + int(round((td - self.g_t) / self.g_T))) % 4
                    self.bar_acc = [0.0] * 4
                    self.bar_acc[self.g_bar] = 2.0
                with self.lock:
                    self.drop_n += 1
                    self.drops.append((td, self.drop_n))

    def snapshot(self, tq):
        """Snimek platny v case tq (monotonic) s vekem poslednich uderu - pro LED se zpozdenim.
        "beats" = hlavni udery (kopak nebo virbl), "kicks" / "snares" / "hats" zvlast, "beats_hi" = virbl
        i cinely. "beat_ph" = faze doby 0..1 a "bar" = doba v taktu 0..3 (rytmicka mrizka, "grid" = jeji
        jistota 0..1), "next_in" = za kolik s prijde dalsi uder (uz zachyceny diky zpozdeni svetel, jinak
        podle mrizky; None = nevi se), "energy" 0..1 = ticha cast x refren, "build" 0..1 = stavba napeti."""
        with self.lock:
            if not self.frames:
                return None
            times = [f[0] for f in self.frames]
            i = bisect.bisect_right(times, tq) - 1
            if i < 0:
                i = 0
            snap = dict(self.frames[i][1])
            ev = {}
            for name, src in (("beats", self.beats), ("kicks", self.kicks), ("snares", self.snares),
                              ("hats", self.hihats), ("beats_hi", self.hats)):
                ev[name] = [(tq - t, k, n) for t, k, n in src if t <= tq]
            future = [t - tq for t, _k, _n in self.beats if t > tq]
            drops = [n for t, n in self.drops if t <= tq]
            last_t = self.frames[-1][0]
        snap["beats"] = ev["beats"][-4:]
        snap["kicks"] = ev["kicks"][-4:]
        snap["snares"] = ev["snares"][-4:]
        snap["hats"] = ev["hats"][-6:]
        snap["beats_hi"] = ev["beats_hi"][-6:]
        snap["beat_n"] = ev["beats"][-1][2] if ev["beats"] else 0
        snap["drop_n"] = drops[-1] if drops else 0
        T = snap.pop("g_T", 0.0)
        gt, gn, gbar = snap.pop("g_t", 0.0), snap.pop("g_n", 0), snap.pop("g_bar", 0)
        nxt = min(future) if future else None
        if T:
            x = (tq - gt) / T
            snap["beat_ph"] = x % 1.0
            snap["bar"] = (gn + int(math.floor(x)) - gbar) % 4
            if nxt is None and snap.get("grid", 0.0) >= self.GRID_OK:
                nxt = (1.0 - x % 1.0) * T
        else:
            snap["beat_ph"], snap["bar"] = 0.0, 0
        snap["next_in"] = nxt
        snap["age"] = max(0.0, tq - last_t)                # stari dat (bez zpozdeni) - zachytavani vazne
        return snap


# ------------------------------------------------------------ vlakna

class Music:
    """Hudba ze Spotify pro LCD a LED. start() spusti vlakna; vse ostatni je bezpecne volat odkudkoli."""

    def __init__(self):
        self.lcd_cfg = lcd_settings(None)
        self.led_cfg = led_settings(None)
        self.player = Player()
        self.wake = threading.Event()
        self.stop_ev = threading.Event()
        self.current = None               # obrazovka "Prave hraje": dict jako u ikony programu
        self.analyzer = None
        self.error = None                 # posledni chyba (pro stav.json)
        self._errors = set()
        self._mix = 0.0
        self._mix_t = None
        self._active = False
        self._capturing = False
        self.extra_audio = False          # zvuk chce i efekt klavesnice (hudba), i bez vizualizeru ventilatoru
        self._track_n = 0
        self.state = {}
        self._threads = []

    # --- nastaveni a zivot

    def color_sens(self):
        return _num(self.led_cfg.get("citlivost_barev"), 7.0, 1.0, 10.0)

    def color_fill(self):
        return bool(self.led_cfg.get("doplnit_barvy", True))

    def update(self, lcd_cfg, led_cfg):
        old = (self.color_sens(), self.color_fill())
        self.lcd_cfg = lcd_settings(lcd_cfg)
        self.led_cfg = led_settings(led_cfg)
        tr = self.player.track
        if (self.color_sens(), self.color_fill()) != old and tr is not None and tr.get("obal") is not None:
            try:                                                # jina citlivost na barvy: paleta znovu
                tr["paleta"] = cover_palette(tr["obal"], sens=self.color_sens(), fill=self.color_fill())
            except Exception as e:
                self._err("paleta z obalu", e)
        if not self.lcd_cfg.get("zapnuto"):
            cur = self.current
            if cur is not None and not cur.get("test"):
                self.current = None

    def start(self):
        for name, fn in (("HudbaPrehravac", self._player_loop), ("HudbaZvuk", self._audio_loop)):
            th = threading.Thread(target=fn, name=name, daemon=True)
            th.start()
            self._threads.append(th)

    def stop(self):
        self.stop_ev.set()

    def _err(self, where, e):
        msg = f"{where}: {e}"
        self.error = msg
        if msg not in self._errors:
            self._errors.add(msg)
            log.warning("Hudba – %s", msg)

    # --- prehravac

    def _player_loop(self):
        try:
            import ctypes
            ctypes.WinDLL("ole32").CoInitializeEx(None, 0)          # MTA pro WinRT
        except OSError:
            pass
        import asyncio
        while not self.stop_ev.is_set():
            try:
                asyncio.run(self._player_async())
            except Exception as e:                               # nesmi shodit vlakno
                self._err("přehrávač", e)
                self.stop_ev.wait(RETRY_S)

    async def _player_async(self):
        import asyncio
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        mgr = await Manager.request_async()
        first = True
        while not self.stop_ev.is_set():
            await self._poll(mgr, first)
            first = False
            self._poll_test()
            await asyncio.sleep(POLL_S)

    async def _poll(self, mgr, first):
        pl = self.player
        sess = _spotify_session(mgr)
        now = time.monotonic()
        if sess is None:
            if pl.playing:
                pl.since = now
            pl.playing, pl.seen = False, False
            return
        pl.seen = True
        playing = int(sess.get_playback_info().playback_status) == PLAYING
        was_playing, paused_for = pl.playing, now - pl.since
        if playing != pl.playing:
            pl.playing, pl.since = playing, now
        props = await sess.try_get_media_properties_async()
        title, artist, album = (props.title or "").strip(), (props.artist or "").strip(), \
            (props.album_title or "").strip()
        tl = sess.get_timeline_properties()
        try:
            import datetime
            pos, end = tl.position.total_seconds(), tl.end_time.total_seconds()
            upd = tl.last_updated_time
            age = (datetime.datetime.now(datetime.timezone.utc) - upd).total_seconds() if upd else 0.0
            pl.pos = (pos, end, now - max(0.0, age)) if end > 0 else None
        except Exception:
            pl.pos = None
        key = (title, artist, album)
        if not title:
            return
        tr = pl.track
        if tr is None or tr["klic"] != key:
            tr = {"klic": key, "nazev": title, "interpret": artist, "album": album, "obal": None, "obal_id": None,
                  "paleta": [], "nacteno": [], "zacatek": now}
            pl.track = tr
            self._track_n += 1
            tr["n"] = self._track_n
            await self._load_cover(props, tr)
            log.info("Hudba: %s – %s (barvy z obalu: %s)", artist, title, self._palette_text(tr))
            if self.analyzer is not None:
                self.analyzer.new_track()
            if not first and playing:
                self._show(tr, now)
        elif playing and not was_playing and not first and self.lcd_cfg.get("po_pauze") and paused_for > PAUSE_SHOW_S:
            self._show(tr, now)
        # Spotify nekdy posle nazev nove skladby driv nez jeji obal (nebo jeste obal predchozi skladby):
        # dokud obal neni, zkouset kazde kolo (0,5 s) az 15 s; jinak znovu po 1, 3, 6 a 10 s
        age = now - tr["zacatek"]
        due = [d for d in COVER_RELOAD_S if age >= d and d not in tr["nacteno"]]
        if due or (tr.get("obal") is None and age < COVER_WAIT_S):
            tr["nacteno"].extend(due)
            old = (tr.get("obal_id"), list(tr["paleta"]))
            await self._load_cover(props, tr)
            if (tr.get("obal_id"), tr["paleta"]) != old:
                log.info("Hudba: obal %s – %s načten po %.1f s (barvy z obalu: %s)", artist, title, age,
                         self._palette_text(tr))

    @staticmethod
    def _palette_text(tr):
        if tr.get("obal") is None:
            return "obal zatím není"
        return " ".join(tr["paleta"]) or "žádné – obal je černobílý / šedý"

    async def _load_cover(self, props, tr):
        try:
            if not await _read_cover(props, tr, self.color_sens(), self.color_fill()):
                return
            cur = self.current
            if cur is not None and cur.get("track") is tr:
                cur["img_key"] = None                            # prekreslit s novym obalem
                self.wake.set()
        except Exception as e:
            self._err("obal alba", e)

    # --- obrazovka "Prave hraje"

    def _show(self, tr, now, secs=None, test=False):
        c = self.lcd_cfg
        if not test and not c.get("zapnuto"):
            return
        secs = _num(c.get("doba_s") if secs is None else secs, 15.0, 1.0, 120.0)
        self.current = {"track": tr, "secs": secs, "found": now, "until": None, "test": test, "img_key": None}
        self.wake.set()

    def _poll_test(self):
        if not os.path.exists(TEST_FILE):
            return
        try:
            with open(TEST_FILE, encoding="utf-8") as f:
                req = json.load(f)
        except (OSError, ValueError):
            req = {}
        finally:
            try:
                os.remove(TEST_FILE)
            except OSError:
                pass
        tr = self.player.track
        if tr is None:
            log.info("Právě hraje – test: Spotify zatím nic nehrálo.")
            return
        self._show(tr, time.monotonic(), req.get("doba_s"), test=True)
        log.info("Právě hraje – test: %s", tr["nazev"])

    def toggle_lcd(self):
        """Klavesa G: obrazovku Prave hraje ukazat na dobu z nastaveni (i kdyz je na zacatku skladby
        vypnuta), kdyz uz je na LCD, schovat. Vrati True = ukazana."""
        cur = self.lcd_active()
        if cur is not None:
            cur["until"] = 0
            self.wake.set()
            log.info("Právě hraje: schováno klávesou.")
            return False
        tr = self.player.track
        if tr is None:
            log.info("Právě hraje: Spotify zatím nic nehrálo.")
            return False
        self._show(tr, time.monotonic(), test=True)
        return True

    def lcd_active(self):
        """Zobrazovana skladba (dict) nebo None. Doba bezi od prvniho odeslani na LCD (start_lcd)."""
        cur = self.current
        if cur is None:
            return None
        now = time.monotonic()
        if cur["until"] is None:
            return cur if now - cur["found"] < 30 else None
        return cur if now < cur["until"] else None

    def progress(self):
        """(pozice s, delka s) prave hrajici skladby nebo None."""
        pl = self.player
        if pl.pos is None:
            return None
        pos, end, t = pl.pos
        if pl.playing:
            pos += time.monotonic() - t
        return max(0.0, min(end, pos)), end

    # --- zvuk

    def _want_audio(self):
        c = self.led_cfg
        pl = self.player
        if not (c.get("zapnuto") or self.extra_audio) or not pl.seen:
            return False
        return pl.playing or time.monotonic() - pl.since < 15.0      # chvili po pauze nechat bezet

    def _audio_loop(self):
        try:
            self.analyzer = Analyzer()
        except Exception as e:
            self._err("analýza zvuku (chybí numpy?)", e)
            return
        import zvuk_procesu as zp
        cap, pid, next_try, next_pid = None, None, 0.0, 0.0
        while not self.stop_ev.is_set():
            try:
                now = time.monotonic()
                want = self._want_audio()
                if want and now >= next_pid:                         # Spotify mohl skoncit / spustit se znovu
                    next_pid = now + 5.0
                    new_pid = zp.main_pid(PLAYER_EXE)
                    if cap is not None and new_pid != pid:
                        cap.close()
                        cap = None
                    pid = new_pid
                if want and cap is None and pid and now >= next_try:
                    cap = zp.ProcessCapture(pid)
                    try:
                        cap.start()
                        self.analyzer.reset()
                        self._capturing = True
                        self.error = None
                        log.info("Hudba: zachytávám zvuk Spotify (PID %d).", pid)
                    except Exception:
                        cap.close()
                        cap = None
                        next_try = now + RETRY_S
                        raise
                if not want and cap is not None:
                    cap.close()
                    cap = None
                    self._capturing = False
                if cap is None:
                    self._capturing = False
                    self.stop_ev.wait(0.5)
                    continue
                pcm = cap.read(100)
                self.analyzer.feed(pcm, time.monotonic(), _num(self.led_cfg.get("citlivost"), 5, 1, 10))
            except Exception as e:
                self._err("zachytávání zvuku Spotify", e)
                if cap is not None:
                    cap.close()
                    cap = None
                self._capturing = False
                self.stop_ev.wait(RETRY_S)
        if cap is not None:
            cap.close()

    # --- LED

    def led_snapshot(self, led_cfg=None):
        """Snimek pro vizualizer LED (zpozdeny o zpozdeni_ms), nebo None = bezny efekt.
        "mix" 0..1 = prolnuti s beznym efektem; "paleta" = barvy (z obalu / vlastni); "track_n"."""
        c = led_settings(led_cfg) if led_cfg is not None else self.led_cfg
        pl = self.player
        now = time.monotonic()
        on = bool(c.get("zapnuto"))
        if on and pl.playing and now - pl.since >= START_S:
            self._active = True
        elif not on or (not pl.playing and now - pl.since >= _num(c.get("navrat_s"), 3.0, 0.0, 60.0)):
            self._active = False
        dt = 0.0 if self._mix_t is None else min(0.5, now - self._mix_t)
        self._mix_t = now
        step = dt / FADE_S
        self._mix = min(1.0, self._mix + step) if self._active else max(0.0, self._mix - step)
        if self._mix <= 0.0:
            return None
        snap = None
        an = self.analyzer
        if an is not None and self._capturing:
            snap = an.snapshot(now - _num(c.get("zpozdeni_ms"), 0.0, 0.0, MAX_DELAY_MS) / 1000.0)
        if snap is None or snap.get("age", 0) > 1.0:                 # bez zvuku: klidna animace v barvach
            snap = {"quiet": True, "bass": 0.0, "mid": 0.0, "high": 0.0, "level": 0.0, "bands": [0.0] * 16,
                    "beats": [], "beat_n": 0, "drop_n": 0, "phase": now * 0.05, "bpm": 0.0}
        if not pl.playing:
            snap["quiet"] = True
        tr = pl.track
        snap["paleta"] = music_palette(c, tr)
        snap["track_n"] = tr["n"] if tr else 0
        snap["mix"] = self._mix
        return snap

    def kb_snapshot(self):
        """Snimek zvuku pro hudebni efekty klavesnice (nezavisle na vizualizeru ventilatoru,
        se stejnym zpozdenim), None = Spotify nehraje / bez zvuku. "paleta" = barvy z obalu."""
        an = self.analyzer
        if an is None or not self._capturing or not self.player.playing:
            return None
        snap = an.snapshot(time.monotonic() - _num(self.led_cfg.get("zpozdeni_ms"), 0.0, 0.0, MAX_DELAY_MS) / 1000.0)
        if snap is None or snap.get("age", 0) > 1.0:
            return None
        snap = dict(snap)
        snap["citlivost"] = _num(self.led_cfg.get("citlivost"), 5, 1, 10)   # s ni analyza hleda udery
        tr = self.player.track
        snap["paleta"] = music_palette(self.led_cfg, tr)                 # stejne barvy jako ventilatory
        return snap

    # --- stav pro okno nastaveni

    def status(self):
        pl = self.player
        tr = pl.track
        out = {"spotify": pl.seen, "hraje": pl.playing, "vizualizer": self._active, "zvuk": self._capturing}
        if tr:
            out.update(nazev=tr["nazev"], interpret=tr["interpret"], album=tr["album"], paleta=tr.get("paleta", []))
        if self.error:
            out["chyba"] = self.error
        an = self.analyzer
        if an is not None and self._capturing:
            s = an.snapshot(time.monotonic())
            if s:
                # float(): analyza pocita v numpy (float32) a ten json.dump neumi
                out["uroven"] = {k: round(float(s.get(k, 0.0)), 2) for k in ("bass", "mid", "high")}
                out["bpm"] = round(float(s.get("bpm", 0.0)), 1)
                out["mrizka"] = round(float(s.get("grid", 0.0)), 2)     # jistota rytmicke mrizky 0..1
                out["energie"] = round(float(s.get("energy", 1.0)), 3)  # ticha cast x refren
                out["stavba"] = round(float(s.get("build", 0.0)), 3)    # stavba napeti pred dropem
        return out


async def _read_cover(props, tr, sens=5, fill=True):
    """Nacist obal alba do tr (obal, obal_id, paleta). True = obal je novy."""
    if props.thumbnail is None:
        return False
    from winrt.windows.storage.streams import DataReader
    from PIL import Image
    st = await props.thumbnail.open_read_async()
    n = int(st.size)
    if not n:
        return False
    r = DataReader(st.get_input_stream_at(0))
    await r.load_async(n)
    data = bytes(r.read_buffer(n))
    ident = hash(data)
    if ident == tr.get("obal_id"):
        return False
    img = Image.open(io.BytesIO(data))
    img.load()
    tr["obal"] = img.convert("RGB")
    tr["obal_id"] = ident
    tr["paleta"] = cover_palette(tr["obal"], sens=sens, fill=fill)
    return True


def _spotify_session(mgr):
    for s in mgr.get_sessions():
        if PLAYER_APP in (s.source_app_user_model_id or "").lower():
            return s
    return None


SAMPLE_TRACK = {"nazev": "Ukázková skladba", "interpret": "Interpret", "album": "", "obal": None, "obal_id": None,
                "paleta": list(DEFAULT_PALETTE)}


def current_track(timeout=3.0, sens=7, fill=True):
    """Pro okno nastaveni: (skladba, (pozice s, delka s) nebo None) ze Spotify, nebo (None, None).
    Bezi v pomocnem vlakne (WinRT v MTA), nejvys timeout sekund."""
    res = {}

    def work():
        try:
            import ctypes
            ctypes.WinDLL("ole32").CoInitializeEx(None, 0)
            import asyncio
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

            async def go():
                sess = _spotify_session(await Manager.request_async())
                if sess is None:
                    return
                props = await sess.try_get_media_properties_async()
                if not (props.title or "").strip():
                    return
                tr = {"nazev": props.title.strip(), "interpret": (props.artist or "").strip(),
                      "album": (props.album_title or "").strip(), "obal": None, "obal_id": None, "paleta": []}
                await _read_cover(props, tr, sens, fill)
                res["tr"] = tr
                tl = sess.get_timeline_properties()
                end = tl.end_time.total_seconds()
                res["prog"] = (tl.position.total_seconds(), end) if end > 0 else None
            asyncio.run(go())
        except Exception as e:
            res["err"] = e
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    if "err" in res:
        raise res["err"]
    return res.get("tr"), res.get("prog")


def request_test(cfg=None):
    """Pozadat bezici aplikaci, aby na LCD ukazala prave hrajici skladbu."""
    c = lcd_settings(cfg)
    tmp = TEST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"doba_s": c.get("doba_s", 15)}, f)
    os.replace(tmp, TEST_FILE)


if __name__ == "__main__":                       # ladeni: py hudba.py = co hraje a uroven zvuku
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    m = Music()
    m.update(None, {"zapnuto": True})
    m.start()
    last_beat = 0
    try:
        while True:
            time.sleep(0.1)
            s = m.led_snapshot()
            st = m.status()
            if s is None:
                print(f"\r čeká… Spotify={st.get('spotify')} hraje={st.get('hraje')} {st.get('chyba', '')}   ",
                      end="", flush=True)
                continue
            bar = lambda v: "#" * int(v * 10) + "." * (10 - int(v * 10))  # noqa: E731
            beat = "UDER" if s.get("beat_n", 0) != last_beat else "    "
            last_beat = s.get("beat_n", 0)
            print(f"\r B {bar(s['bass'])} S {bar(s['mid'])} V {bar(s['high'])} {beat} bpm {s.get('bpm', 0):5.1f} "
                  f"mřížka {s.get('grid', 0):.2f} doba {s.get('bar', 0) + 1} energie {s.get('energy', 1):.2f} "
                  f"stavba {s.get('build', 0):.2f} drop {s.get('drop_n', 0)} ticho {int(bool(s.get('quiet')))} "
                  f"mix {s['mix']:.2f}", end="", flush=True)
    except KeyboardInterrupt:
        m.stop()
