# led.py - ovladani LED: ventilatory F140 RGB Core (NZXT 2023 RGB Controller) a zony
# zakladni desky (Gigabyte RGB Fusion 2.0 5702) pres liquidctl.
#
# Nastaveni: config["led"]. LED se nastavi pri startu aplikace, pri zmene nastaveni,
# po probuzeni PC (radice po uspani mohou zapomenout) a po chybe (dalsi pokus za 30 s).
# Bezi ve vlastnim vlakne - chyba u LED nesmi zdrzet chlazeni.
#
# NZXT: kanaly led1-led3, na led1 a led2 je po jednom F140 (8 LED). Rezim "super-fixed"
#   = kazda LED vlastni barvou.
# Gigabyte: zony led1-led8 = jedna barva / efekt na celou zonu (liquidctl). Zona led6 je ARGB
#   hlavicka D_LED1 a led7 hlavicka D_LED2 - ty se ridi zvlast (config["led"]["argb"]):
#   - primy rezim (kazda LED zvlast, jedna barva, vypnuto): registr 0x32 = maska vypnutych
#     vestavenych efektu (D_LED1 0x01, D_LED2 0x02) a barvy po LED prikazem 0x58 / 0x59
#     (paket [0xCC, hlavicka, offset 2 B, pocet bajtu, az 19 LED], poradi bajtu z kalibrace)
#   - vestavene efekty cipu (pulz, blikani, stridani barev): maska 0x32 bit vynulovat + efekt zony
#   Protokol podle OpenRGB (GigabyteRGBFusion2USBController). Na D_LED1 jsou 3 ventilatory
#   paralelne (rozbocovac), kazdy 16 LED - vsechny sviti stejne.
#   LED desky jinak ridi Gigabyte Control Center (GCC) - pokud bezi, nastaveni prepise.

import copy
import json
import logging
import threading
import time

log = logging.getLogger("rgb_lcd")

RETRY_S = 30
RESUME_GAP_S = 20            # skok hodin = PC se probudilo -> nastavit LED znovu
LEDS_PER_FAN = 8

# rezimy NZXT 2023 RGB Controlleru: liquidctl nazev -> (cesky nazev, min barev, max barev, rychlost)
# (covering-marquee v liquidctl 1.16 pada na chybejici rychlosti - vynechan)
NZXT_MODES = {
    "off": ("vypnuto", 0, 0, False),
    "fixed": ("jedna barva", 1, 1, False),
    "super-fixed": ("každá LED zvlášť", 1, LEDS_PER_FAN, False),
    "breathing": ("dýchání", 1, 8, True),
    "fading": ("prolínání barev", 1, 8, True),
    "pulse": ("pulz", 1, 1, True),
    "alternating": ("střídání 2 barev", 2, 2, True),
    "starry-night": ("hvězdná noc", 1, 1, True),
    "candle": ("svíčka", 1, 1, False),
    "spectrum-wave": ("spektrum – vlna", 0, 0, True),
    "rainbow-flow": ("duha – tok", 0, 0, True),
    "rainbow-pulse": ("duha – pulz", 0, 0, True),
    "super-rainbow": ("super duha", 0, 0, True),
}
NZXT_SPEEDS = {"slowest": "nejpomaleji", "slower": "pomaleji", "normal": "normálně", "faster": "rychleji",
               "fastest": "nejrychleji"}

# rezimy Gigabyte RGB Fusion 2.0 (cela zona)
FUSION_MODES = {
    "off": ("vypnuto", False, False),
    "fixed": ("jedna barva", True, False),
    "pulse": ("pulz", True, True),
    "flash": ("blikání", True, True),
    "double-flash": ("dvojité blikání", True, True),
    "color-cycle": ("střídání barev", False, True),
}
FUSION_SPEEDS = {"slowest": "nejpomaleji", "slower": "pomaleji", "normal": "normálně", "faster": "rychleji",
                 "fastest": "nejrychleji", "ludicrous": "šíleně rychle"}

RAINBOW = ["#ff0000", "#ff8000", "#ffff00", "#00ff00", "#00ffff", "#0040ff", "#8000ff", "#ff00c0"]

# ARGB hlavicky desky: nazev -> (zona pro vestavene efekty, prikaz pro barvy po LED, bit masky 0x32)
ARGB_HEADERS = {"D_LED1": ("led6", 0x58, 0x01), "D_LED2": ("led7", 0x59, 0x02)}
ARGB_ZONES = {v[0] for v in ARGB_HEADERS.values()}
ARGB_MAX_LEDS = 32
# rezimy ARGB: primy (aplikace posila barvy) a vestavene efekty cipu
ARGB_MODES = {
    "off": ("vypnuto", "primy"),
    "fixed": ("jedna barva", "primy"),
    "super-fixed": ("každá LED zvlášť", "primy"),
    "pulse": ("pulz", "efekt"),
    "flash": ("blikání", "efekt"),
    "double-flash": ("dvojité blikání", "efekt"),
    "color-cycle": ("střídání barev", "efekt"),
}


def rainbow(n):
    """n barev duhy po obvodu (pro kruh s n LED)."""
    import colorsys
    out = []
    for i in range(n):
        r, g, b = colorsys.hsv_to_rgb(i / n, 1.0, 1.0)
        out.append(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")
    return out


def default_config():
    fan = {"rezim": "super-fixed", "barvy": list(RAINBOW), "barvy_efekt": ["#ff0000", "#0040ff"],
           "rychlost": "normal", "obraceny_smer": False}
    zones = {f"led{i}": {"nazev": f"zóna {i}", "rezim": "off", "barva": "#ffffff", "rychlost": "normal"}
             for i in range(1, 9)}
    zones["led6"]["nazev"] = zones["led7"]["nazev"] = "ARGB hlavička – viz níže"
    argb = {
        "D_LED1": {"nazev": "ventilátory na desce (3× paralelně)", "pocet_led": 16, "rezim": "super-fixed",
                   "barvy": rainbow(16), "barva": "#8000ff", "rychlost": "normal", "obraceny_smer": False},
        "D_LED2": {"nazev": "nepřipojeno", "pocet_led": 16, "rezim": "off", "barvy": rainbow(16),
                   "barva": "#ffffff", "rychlost": "normal", "obraceny_smer": False},
    }
    return {
        "zapnuto": True,
        "nzxt_stejne": True,                       # led2 = stejne jako led1
        "nzxt": {"led1": dict(fan, nazev="F140 (1)"), "led2": dict(copy.deepcopy(fan), nazev="F140 (2)"),
                 "led3": {"nazev": "nepřipojeno", "rezim": "off", "barvy": ["#ffffff"], "rychlost": "normal"}},
        "fusion": zones,
        "argb": argb,
    }


def hex_rgb(h):
    h = str(h).lstrip("#")
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return [255, 255, 255]


def color_key(mode):
    """Barvy LED po jedne (8) a barvy efektu jsou zvlast, aby se prepnutim rezimu neztratily."""
    return "barvy" if mode == "super-fixed" else "barvy_efekt"


def _nzxt_colors(ch):
    mode = ch.get("rezim", "off")
    _name, lo, hi, _speed = NZXT_MODES.get(mode, NZXT_MODES["off"])
    cols = [hex_rgb(c) for c in ch.get(color_key(mode), [])][:hi]
    while len(cols) < lo:
        cols.append([255, 255, 255])
    if mode == "super-fixed":                      # presne 8 LED, ostatni zhasnout
        cols = (cols + [[0, 0, 0]] * LEDS_PER_FAN)[:LEDS_PER_FAN]
    return mode, cols


def argb_order(report):
    """Pozice bajtu R, G, B pro hlavicky D_LED1/2 z odpovedi na 0x60 (kalibrace, typicky GRB)."""
    import struct
    out = {}
    for name, off in (("D_LED1", 44), ("D_LED2", 48)):
        v = struct.unpack_from("<I", bytes(report), off)[0]
        order = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
        out[name] = order if sorted(order) == [0, 1, 2] else (1, 0, 2)    # nesmysl -> GRB
    return out


def _argb_report(dev):
    for _ in range(3):
        dev.send_feature_report([0xCC, 0x60] + [0] * 62)
        r = dev.get_feature_report(0xCC, 64)
        if len(r) >= 52 and r[0] in (0xCC, 0) and r[1] == 0x01:
            return r
        time.sleep(0.3)
    return None


def _argb_strip(dev, cmd, colors, order):
    """Barvy po LED na hlavicku (po 19 LED v jednom paketu)."""
    sent = 0
    for i in range(0, len(colors), 19):
        chunk = colors[i:i + 19]
        pkt = [0] * 64
        pkt[0], pkt[1], pkt[2], pkt[3], pkt[4] = 0xCC, cmd, sent & 0xFF, sent >> 8, len(chunk) * 3
        for j, (r, g, b) in enumerate(chunk):
            o = 5 + j * 3
            pkt[o + order[0]], pkt[o + order[1]], pkt[o + order[2]] = r, g, b
        dev.send_feature_report(pkt)
        sent += len(chunk) * 3


def _argb_colors(h):
    n = max(1, min(ARGB_MAX_LEDS, int(h.get("pocet_led", 16))))
    mode = h.get("rezim", "off")
    if mode == "super-fixed":
        cols = [hex_rgb(c) for c in h.get("barvy", [])][:n]
        cols += [[0, 0, 0]] * (n - len(cols))
    elif mode == "fixed":
        cols = [hex_rgb(h.get("barva", "#ffffff"))] * n
    else:
        cols = [[0, 0, 0]] * n
    return cols + [[0, 0, 0]] * (ARGB_MAX_LEDS - n)      # zbytek hlavicky zhasnout


def _devices():
    import kraken  # noqa: F401  oprava GUID pred prvnim importem liquidctl
    from liquidctl import find_liquidctl_devices
    nzxt = fusion = None
    for d in find_liquidctl_devices():
        if "NZXT 2023 RGB" in d.description:
            nzxt = d
        elif "Fusion" in d.description:
            fusion = d
    return nzxt, fusion


def _init(dev, tries=3):
    for i in range(tries):                         # Fusion obcas napoprve odpovi nesmyslem
        try:
            return dev.initialize()
        except AssertionError:
            time.sleep(0.3)
    return dev.initialize()


def apply(lcfg):
    """Nastavit LED podle config["led"]. Vrati seznam chyb (prazdny = vse OK)."""
    errors = []
    nzxt, fusion = _devices()
    if nzxt is None:
        errors.append("NZXT RGB Controller nenalezen")
    else:
        try:
            with nzxt.connect():
                _init(nzxt)
                chans = lcfg.get("nzxt", {})
                for name in ("led1", "led2", "led3"):
                    ch = chans.get(name, {})
                    if name == "led2" and lcfg.get("nzxt_stejne", True):
                        ch = chans.get("led1", {})
                    mode, cols = _nzxt_colors(ch)
                    speed = ch.get("rychlost", "normal") if NZXT_MODES.get(mode, (0, 0, 0, False))[3] else "normal"
                    nzxt.set_color(name, mode, cols, speed=speed)
        except Exception as e:
            errors.append(f"NZXT: {e}")
    if fusion is None:
        errors.append("Gigabyte RGB Fusion nenalezen")
    else:
        try:
            with fusion.connect():
                _init(fusion)
                argb = lcfg.get("argb", {})
                for name, z in sorted(lcfg.get("fusion", {}).items()):
                    if name in ARGB_ZONES:
                        continue                       # ARGB hlavicky nize
                    mode = z.get("rezim", "off")
                    _n, takes_color, has_speed = FUSION_MODES.get(mode, FUSION_MODES["off"])
                    cols = [hex_rgb(z.get("barva", "#ffffff"))] if takes_color else []
                    speed = z.get("rychlost", "normal") if has_speed else "normal"
                    if mode == "double-flash" and speed == "slower":
                        speed = "normal"               # v liquidctl 1.16 preklep v nazvu rychlosti
                    fusion.set_color(name, mode, cols, speed=speed)
                dev = fusion.device
                report = _argb_report(dev)
                orders = argb_order(report) if report else {k: (1, 0, 2) for k in ARGB_HEADERS}
                mask = 0
                for hname, (zone, cmd, bit) in ARGB_HEADERS.items():   # nejdriv efekty (maska 0)
                    h = argb.get(hname, {})
                    mode = h.get("rezim", "off")
                    if ARGB_MODES.get(mode, ("", "primy"))[1] == "primy":
                        mask |= bit
                        continue
                    speed = h.get("rychlost", "normal")
                    if mode == "double-flash" and speed == "slower":
                        speed = "normal"
                    cols = [hex_rgb(h.get("barva", "#ffffff"))] if FUSION_MODES[mode][1] else []
                    fusion.set_color(zone, mode, cols, speed=speed)
                dev.send_feature_report([0xCC, 0x32, mask] + [0] * 61)   # primy rezim tam, kde je
                time.sleep(0.05)
                for hname, (zone, cmd, bit) in ARGB_HEADERS.items():
                    if mask & bit:
                        _argb_strip(dev, cmd, _argb_colors(argb.get(hname, {})), orders[hname])
        except Exception as e:
            errors.append(f"Gigabyte: {e}")
    return errors


class LedWorker(threading.Thread):
    def __init__(self):
        super().__init__(name="led", daemon=True)
        self._lock = threading.Lock()
        self._cfg = None
        self._quit = threading.Event()
        self._wake = threading.Event()
        self.state = {"stav": "čeká"}

    def update(self, lcfg):
        with self._lock:
            self._cfg = lcfg
        self._wake.set()

    def stop(self, timeout=1.0):
        self._quit.set()
        self._wake.set()
        self.join(timeout)

    def run(self):
        applied_key, next_retry, last_wall = None, 0.0, time.time()
        while not self._quit.is_set():
            self._wake.wait(2.0)
            self._wake.clear()
            now_wall = time.time()
            resumed = now_wall - last_wall > RESUME_GAP_S
            last_wall = now_wall
            with self._lock:
                lcfg = self._cfg
            if lcfg is None:
                continue
            if not lcfg.get("zapnuto", True):
                self.state = {"stav": "vypnuto"}
                applied_key = None                     # po zapnuti znovu nastavit
                continue
            key = json.dumps(lcfg, sort_keys=True)
            if key == applied_key and not resumed:
                continue
            if key == applied_key and resumed:
                log.info("LED: PC se probudilo - nastavuji LED znovu.")
            if self.state.get("stav") == "chyba" and time.monotonic() < next_retry and key == applied_key:
                continue
            errors = apply(lcfg)
            applied_key = key
            if errors:
                if self.state.get("chyby") != errors:
                    log.warning("LED: %s", "; ".join(errors))
                self.state = {"stav": "chyba", "chyby": errors}
                next_retry = time.monotonic() + RETRY_S
                applied_key = None                     # zkusit znovu
                self._quit.wait(RETRY_S)
            else:
                if self.state.get("stav") != "nastaveno":
                    log.info("LED: nastaveno.")
                self.state = {"stav": "nastaveno"}
