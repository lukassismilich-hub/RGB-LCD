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
# pasem (0..1 s automatickym zesilenim), udery (nahly narust energie basu), tempo a "drop"
# (energie vyrazne nad prumerem poslednich ~12 s). Zachytava jen kdyz Spotify hraje a vizualizer
# je zapnuty. LED (led.py) si bere snimek s nastavitelnym zpozdenim (Bluetooth sluchatka hraji
# pozdeji) - led_snapshot().
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

import led

log = logging.getLogger("rgb_lcd")

BASE = os.path.dirname(os.path.abspath(__file__))
# test z okna nastaveni ("Vyzkouset"): {"doba_s", ...} - aplikace ukaze prave hrajici skladbu na LCD
TEST_FILE = os.path.join(BASE, "hudba_test.json")

PLAYER_APP = "spotify"                 # relace Windows, jejiz AppUserModelId obsahuje tento text
PLAYER_EXE = "Spotify.exe"
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


def _num(v, default, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------ paleta z obalu alba

def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _vivid(h, s):
    """Ziva barva pro LED: plny jas, sytost aspon 0,75 (bledsi barvy LED ukazou skoro bile)."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.75 + 0.25 * s, 1.0)
    return _hex((r * 255, g * 255, b * 255))


def cover_palette(img, n=5):
    """Az n zivych barev z obalu alba, nejvyraznejsi prvni (hlavni barva, pak doplnkova).
    Vynecha cernou, bilou, sedou a hnedou (na LED vypadaji spatne). Prazdny seznam = obal je
    cernobily / sedy (pouzije se vychozi paleta)."""
    from PIL import Image
    small = img.convert("RGB").resize((40, 40), Image.BILINEAR)
    q = small.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    cand = []
    for count, idx in q.getcolors() or []:
        r, g, b = pal[idx * 3:idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.2 or s < 0.25:                          # cerna, seda, bila
            continue
        if 0.02 <= h <= 0.12 and v < 0.6 and s < 0.85:   # hneda
            continue
        cand.append((count * (0.25 + s) * (0.35 + v), h, s))
    cand.sort(reverse=True)
    hues, out = [], []
    for _score, h, s in cand:
        if any(min(abs(h - x), 1 - abs(h - x)) < 0.07 for x in hues):
            continue                                     # skoro stejny odstin uz je
        hues.append(h)
        out.append(_vivid(h, s))
        if len(out) >= n:
            break
    if len(out) == 1:                                    # jednobarevny obal: pridat pribuzne odstiny
        h, s = hues[0], cand[0][2]
        out += [_vivid(h + 0.09, s), _vivid(h - 0.09, s)]
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

class Analyzer:
    """Z PCM (int16 stereo 48 kHz) pocita snimky s casovou znackou. Vse 0..1 s automatickym
    zesilenim (spicka v dB, pomalu klesa), udery podle narustu energie basu."""

    N = 2048                              # okno FFT (~43 ms)
    HOP = 1024                            # krok (~21 ms = ~47 snimku za sekundu)
    BANDS = 16
    FLOOR_DB = -62.0                      # pod tim je ticho (dB vuci plne urovni)
    RANGE_DB = 26.0                       # rozsah od spicky dolu, ktery se mapuje na 0..1
    RELEASE_DB_S = 2.5                    # jak rychle klesa spicka automatickeho zesileni
    KEEP_S = 1.5                          # historie snimku (zpozdeni az 0,5 s + rezerva)

    def __init__(self):
        import numpy as np
        self.np = np
        from zvuk_procesu import RATE
        self.rate = RATE
        self.win = np.hanning(self.N).astype(np.float32)
        norm = (self.win.sum() / 2) ** 2                 # plna sinusovka = 0 dB
        self.norm = norm
        f = np.fft.rfftfreq(self.N, 1 / RATE)

        def rng(lo, hi):
            a, b = np.searchsorted(f, lo), np.searchsorted(f, hi)
            return (int(a), int(max(a + 1, b)))
        self.r_bass, self.r_mid, self.r_high, self.r_all = rng(30, 160), rng(160, 2000), rng(2000, 12000), \
            rng(30, 16000)
        edges = np.geomspace(40, 14000, self.BANDS + 1)
        self.r_bands = [rng(edges[i], edges[i + 1]) for i in range(self.BANDS)]
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        np = self.np
        self.buf = np.zeros(0, dtype=np.float32)
        self.ref = {}                                     # spicka (dB) pro automaticke zesileni
        self.env = {}                                     # obalky 0..1
        self.bass_hist = collections.deque(maxlen=47)     # energie basu za ~1 s
        self.prev_bass = 0.0
        self.short_db = collections.deque(maxlen=70)      # celkovy vykon ~1,5 s
        self.long_db = collections.deque(maxlen=560)      # ~12 s
        self.last_beat = -1e9
        self.last_drop = -1e9
        self.ibi = collections.deque(maxlen=8)            # intervaly mezi udery
        self.phase = 0.0
        self.quiet_since = None
        with self.lock:
            self.frames = collections.deque()             # (t, snimek)
            self.beats = collections.deque(maxlen=16)     # (t, sila, poradi)
            self.drops = collections.deque(maxlen=8)      # (t, poradi)
            self.beat_n = self.drop_n = 0

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

    def feed(self, pcm, now, sens=5):
        """Pridat PCM (bytes) zachycene ted; spocita vsechny cele kroky."""
        np = self.np
        if pcm:
            x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            x = (x[0::2] + x[1::2]) * (0.5 / 32768.0)
            self.buf = np.concatenate((self.buf, x))
        dt = self.HOP / self.rate
        gamma = 1.6 - 0.1 * max(1, min(10, sens))         # citlivost: vyssi = vyraznejsi reakce na tichsi
        beat_c = 1.7 - 0.05 * max(1, min(10, sens))       # prah uderu vuci prumeru basu
        while len(self.buf) >= self.N:
            left = len(self.buf) - self.N                 # vzorky za timto oknem (zachycene pozdeji)
            t = now - left / self.rate
            frame = self.buf[:self.N]
            self.buf = self.buf[self.HOP:]
            p = np.abs(np.fft.rfft(frame * self.win)) ** 2
            db_all = self._db(p, self.r_all)
            snap = {}
            for name, r, tau in (("bass", self.r_bass, 0.12), ("mid", self.r_mid, 0.25),
                                 ("high", self.r_high, 0.08)):
                snap[name] = self._envelope(name, self._level(name, self._db(p, r), dt, gamma), dt, tau)
            snap["level"] = self._envelope("level", self._level("all", db_all, dt, gamma), dt, 0.3)
            snap["bands"] = [round(self._envelope(f"b{i}", self._level(f"b{i}", self._db(p, r), dt, gamma), dt,
                                                  0.15), 3) for i, r in enumerate(self.r_bands)]
            # uder: energie basu nahle nad prumerem posledni sekundy a roste
            e = float(p[self.r_bass[0]:self.r_bass[1]].sum()) / self.norm
            avg = (sum(self.bass_hist) / len(self.bass_hist)) if self.bass_hist else e
            if (len(self.bass_hist) > 10 and e > avg * beat_c and e > self.prev_bass and t - self.last_beat > 0.27
                    and 10 * math.log10(e + 1e-12) > self.FLOOR_DB + 6):
                k = max(0.35, min(1.0, (e / max(avg, 1e-12) - beat_c) / beat_c + 0.5))
                if t - self.last_beat < 2.0:
                    self.ibi.append(t - self.last_beat)
                self.last_beat = t
                with self.lock:
                    self.beat_n += 1
                    self.beats.append((t, k, self.beat_n))
            self.bass_hist.append(e)
            self.prev_bass = e
            # drop / refren: kratkodoba uroven vyrazne nad dlouhodobou
            pw = 10 ** (db_all / 10)                       # prumery z vykonu, ne z dB (mezery mezi udery)
            self.short_db.append(pw)
            self.long_db.append(pw)
            if len(self.long_db) > 200 and t - self.last_drop > 8.0:
                s_avg = 10 * math.log10(sum(self.short_db) / len(self.short_db) + 1e-12)
                l_avg = 10 * math.log10(sum(self.long_db) / len(self.long_db) + 1e-12)
                if s_avg - l_avg > 4.5 and s_avg > self.FLOOR_DB + 10:
                    self.last_drop = t
                    with self.lock:
                        self.drop_n += 1
                        self.drops.append((t, self.drop_n))
            bpm = 0.0
            if len(self.ibi) >= 4:
                med = sorted(self.ibi)[len(self.ibi) // 2]
                bpm = 60.0 / med
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

    def snapshot(self, tq):
        """Snimek platny v case tq (monotonic) s vekem posledních uderu - pro LED se zpozdenim."""
        with self.lock:
            if not self.frames:
                return None
            times = [f[0] for f in self.frames]
            i = bisect.bisect_right(times, tq) - 1
            if i < 0:
                i = 0
            snap = dict(self.frames[i][1])
            beats = [(tq - t, k, n) for t, k, n in self.beats if t <= tq]
            n_beats = [n for t, _k, n in self.beats if t <= tq]
            drops = [n for t, n in self.drops if t <= tq]
            last_t = self.frames[-1][0]
        snap["beats"] = beats[-4:]
        snap["beat_n"] = n_beats[-1] if n_beats else 0
        snap["drop_n"] = drops[-1] if drops else 0
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
        self._track_n = 0
        self.state = {}
        self._threads = []

    # --- nastaveni a zivot

    def update(self, lcd_cfg, led_cfg):
        self.lcd_cfg = lcd_settings(lcd_cfg)
        self.led_cfg = led_settings(led_cfg)
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
            log.info("Hudba: %s – %s", artist, title)
            if not first and playing:
                self._show(tr, now)
        elif playing and not was_playing and not first and self.lcd_cfg.get("po_pauze") and paused_for > PAUSE_SHOW_S:
            self._show(tr, now)
        # Spotify nekdy posle nazev nove skladby driv nez jeji obal - obal nacist jeste 1 s a 3 s po zmene
        for delay in (1.0, 3.0):
            if now - tr["zacatek"] >= delay and delay not in tr["nacteno"]:
                tr["nacteno"].append(delay)
                await self._load_cover(props, tr)

    async def _load_cover(self, props, tr):
        try:
            if not await _read_cover(props, tr):
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
        if not c.get("zapnuto") or not pl.seen:
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
        if c.get("barvy") == "obal" and tr and tr.get("paleta"):
            pal = tr["paleta"]
        else:
            pal = [p for p in c.get("paleta", []) if isinstance(p, str)] or DEFAULT_PALETTE
        snap["paleta"] = pal
        snap["track_n"] = tr["n"] if tr else 0
        snap["mix"] = self._mix
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
                out["uroven"] = {k: round(s.get(k, 0.0), 2) for k in ("bass", "mid", "high")}
                out["bpm"] = s.get("bpm", 0.0)
        return out


async def _read_cover(props, tr):
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
    tr["paleta"] = cover_palette(tr["obal"])
    return True


def _spotify_session(mgr):
    for s in mgr.get_sessions():
        if PLAYER_APP in (s.source_app_user_model_id or "").lower():
            return s
    return None


SAMPLE_TRACK = {"nazev": "Ukázková skladba", "interpret": "Interpret", "album": "", "obal": None, "obal_id": None,
                "paleta": list(DEFAULT_PALETTE)}


def current_track(timeout=3.0):
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
                await _read_cover(props, tr)
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
                  f"drop {s.get('drop_n', 0)} ticho {int(bool(s.get('quiet')))} mix {s['mix']:.2f} "
                  f"{' '.join(s['paleta'][:3])}", end="", flush=True)
    except KeyboardInterrupt:
        m.stop()
