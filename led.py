# led.py - LED vsech ventilatoru: F140 RGB Core (NZXT 2023 RGB Controller) a ventilatory
# na desce (ARGB hlavicka Gigabyte RGB Fusion 2.0 / IT5701).
#
# Efekty pocita aplikace (led_efekty.py) a posila barvy kazde LED primo:
#   - NZXT: kanaly led1 a led2 = po jednom F140 (8 LED), rezim "super-fixed" (barva po LED)
#   - Gigabyte: ARGB hlavicka D_LED1 (0x58) - 2 ventilatory paralelne, kazdy 16 LED (sviti stejne);
#     D_LED2 (0x59) - 1 ventilator, 16 LED. Primy rezim: registr 0x32 = maska vypnutych vestavenych efektu
#     (D_LED1 0x01, D_LED2 0x02), barvy po LED paketem [0xCC, hlavicka, offset 2 B, pocet bajtu,
#     az 19 LED], poradi bajtu z kalibrace (GRB). Protokol podle OpenRGB.
#   - ostatni zony desky (male LED, 12V RGB) = jen jedna barva / efekt cipu pres liquidctl
# Liquidctl sam D_LED neovladne, kdyz ma hlavicka vypnute vestavene efekty (tak ji nechava GCC).
# LED desky jinak ridi Gigabyte Control Center (GCC) - pokud bezi, nastaveni prepise.
#
# Vlakno LedWorker drzi spojeni otevrena, animovane efekty posila ~30x za sekundu, staticke
# jen pri zmene. Po probuzeni PC (skok hodin) a po chybe se radice nastavi znovu.
# Chyba u LED nesmi zdrzet chlazeni - bezi mimo hlavni smycku.

import copy
import json
import logging
import threading
import time

import led_efekty as fx

log = logging.getLogger("rgb_lcd")

RETRY_S = 30
RESUME_GAP_S = 20
REFRESH_S = 10               # staticky efekt: obcas poslat znovu (kdyby radic zapomnel)
LEDS_PER_FAN = 8

# ostatni zony Gigabyte (cela zona)
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

# ARGB hlavicky desky: nazev -> (zona liquidctl, prikaz pro barvy po LED, bit masky 0x32)
ARGB_HEADERS = {"D_LED1": ("led6", 0x58, 0x01), "D_LED2": ("led7", 0x59, 0x02)}
ARGB_ZONES = {v[0] for v in ARGB_HEADERS.values()}
ARGB_MAX_LEDS = 32


def rainbow(n):
    """n barev duhy po obvodu (pro kruh s n LED)."""
    import colorsys
    out = []
    for i in range(n):
        r, g, b = colorsys.hsv_to_rgb(i / n, 1.0, 1.0)
        out.append(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")
    return out


RAINBOW = rainbow(8)


def default_config():
    zones = {f"led{i}": {"nazev": f"zóna {i}", "rezim": "off", "barva": "#ffffff", "rychlost": "normal"}
             for i in range(1, 9)}
    zones["led6"]["nazev"] = zones["led7"]["nazev"] = "ARGB hlavička"
    return {
        "zapnuto": True,
        "jas": 80,                                 # celkovy jas vsech ventilatoru (%)
        "jas_f140": 100,                           # vyrovnani jasu skupin (%)
        "jas_deska": 100,
        "stejne_pro_vse": True,                    # jeden efekt pro vsechny ventilatory
        "vlna": False,                             # efekt posunuty mezi ventilatory
        "efekt": copy.deepcopy(fx.DEFAULT_EFFECT),
        "efekt_f140": copy.deepcopy(fx.DEFAULT_EFFECT),
        "efekt_deska": copy.deepcopy(fx.DEFAULT_EFFECT),
        "nzxt_stejne": True,                       # vlastni barvy LED: F140 (2) jako F140 (1)
        "nzxt": {"led1": {"nazev": "F140 (1)", "barvy": list(RAINBOW)},
                 "led2": {"nazev": "F140 (2)", "barvy": list(RAINBOW)}},
        "argb": {
            "D_LED1": {"nazev": "2 ventilátory paralelně", "pocet_led": 16, "pouzito": True,
                       "barvy": rainbow(16)},
            "D_LED2": {"nazev": "1 ventilátor", "pocet_led": 16, "pouzito": True, "barvy": rainbow(16)},
        },
        "fusion": zones,
    }


def hex_rgb(h):
    return list(fx.hex_rgb(h))


def targets(lcfg):
    """Ventilatory: (klic, pocet LED, skupina, vlastni barvy LED)."""
    nz = lcfg.get("nzxt", {})
    c1 = nz.get("led1", {}).get("barvy", RAINBOW)
    c2 = c1 if lcfg.get("nzxt_stejne", True) else nz.get("led2", {}).get("barvy", RAINBOW)
    out = [("f140_1", LEDS_PER_FAN, "f140", c1), ("f140_2", LEDS_PER_FAN, "f140", c2)]
    for name in ARGB_HEADERS:
        h = lcfg.get("argb", {}).get(name, {})
        if h.get("pouzito", name == "D_LED1"):
            n = max(1, min(ARGB_MAX_LEDS, int(h.get("pocet_led", 16))))
            out.append((name, n, "deska", h.get("barvy", rainbow(n))))
    return out


def effect_for(lcfg, group):
    if lcfg.get("stejne_pro_vse", True):
        return lcfg.get("efekt", fx.DEFAULT_EFFECT)
    return lcfg.get(f"efekt_{group}", fx.DEFAULT_EFFECT)


def is_animated(lcfg):
    groups = {g for _k, _n, g, _c in targets(lcfg)}
    return any(effect_for(lcfg, g).get("typ") in fx.ANIMATED for g in groups)


def orientation(lcfg, key):
    """(posun LED 1, obracene poradi) ventilatoru - aby se efekt na vsech tocil stejne,
    i kdyz ma kazdy ventilator LED 1 jinde nebo LED cislovane opacnym smerem."""
    if key.startswith("f140_"):
        ch = lcfg.get("nzxt", {}).get("led" + key[-1], {})
    else:
        ch = lcfg.get("argb", {}).get(key, {})
    try:
        shift = int(ch.get("posun", 0))
    except (TypeError, ValueError):
        shift = 0
    return shift, bool(ch.get("obracene", False))


def _orient(cols, shift, reverse):
    """Fyzicka LED k dostane barvu z pozice (posun +/- k) efektu."""
    n = len(cols)
    if not n or (shift % n == 0 and not reverse):
        return cols
    sign = -1 if reverse else 1
    return [cols[(shift + sign * k) % n] for k in range(n)]


def render(engine, lcfg, t, data=None, dt=1 / fx.FPS, orient=True):
    """{klic: [[r, g, b] x pocet LED]} s jasem - pro vlakno i nahled v nastaveni.
    orient=False (nahled): bez natoceni ventilatoru, tj. tak, jak ma efekt vypadat."""
    tg = targets(lcfg)
    out = {}
    for idx, (key, n, group, custom) in enumerate(tg):
        eff = effect_for(lcfg, group)
        cols = engine.frame(eff, t, key, n, idx, len(tg), bool(lcfg.get("vlna")), custom, data, dt)
        if orient and eff.get("typ") not in ("vlastni", "vypnuto"):   # vlastni barvy jsou uz po LED
            cols = _orient(cols, *orientation(lcfg, key))
        k = float(lcfg.get("jas", 80)) * float(lcfg.get(f"jas_{group}", 100)) / 100.0
        out[key] = fx.apply_brightness(cols, k)
    return out


# ----------------------------------------------------------------- hardware

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
    for _ in range(tries):                         # Fusion obcas napoprve odpovi nesmyslem
        try:
            return dev.initialize()
        except AssertionError:
            time.sleep(0.3)
    return dev.initialize()


class Session:
    """Otevrena spojeni s obema radici a posilani snimku."""

    def __init__(self, lcfg):
        self.nzxt, self.fusion = _devices()
        self.errors = []
        self.fdev = None
        self.orders = {k: (1, 0, 2) for k in ARGB_HEADERS}
        if self.nzxt is None:
            self.errors.append("NZXT RGB Controller nenalezen")
        else:
            self.nzxt.connect()
            _init(self.nzxt)
            self.nzxt.set_color("led3", "off", [])                     # volny kanal zhasnout
        if self.fusion is None:
            self.errors.append("Gigabyte RGB Fusion nenalezen")
        else:
            self.fusion.connect()
            _init(self.fusion)
            self.fdev = self.fusion.device
            self.setup_zones(lcfg)
            report = _argb_report(self.fdev)
            if report:
                self.orders = argb_order(report)
            self.fdev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)   # D_LED1+2 primy rezim
            time.sleep(0.05)
        self.last = {}

    def setup_zones(self, lcfg):
        """Ostatni zony desky (male LED, 12V RGB) - jedna barva / efekt cipu."""
        for name, z in sorted(lcfg.get("fusion", {}).items()):
            if name in ARGB_ZONES:
                continue
            mode = z.get("rezim", "off")
            _n, takes_color, has_speed = FUSION_MODES.get(mode, FUSION_MODES["off"])
            cols = [hex_rgb(z.get("barva", "#ffffff"))] if takes_color else []
            speed = z.get("rychlost", "normal") if has_speed else "normal"
            if mode == "double-flash" and speed == "slower":
                speed = "normal"                    # v liquidctl 1.16 preklep v nazvu rychlosti
            self.fusion.set_color(name, mode, cols, speed=speed)
        self.fdev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)       # liquidctl mohl masku zmenit

    def send(self, frame, force=False):
        """Poslat jen to, co se zmenilo (force = vse)."""
        f1, f2 = frame.get("f140_1"), frame.get("f140_2")
        if self.nzxt is not None and f1 is not None:
            if force or f1 != self.last.get("f140_1") or f2 != self.last.get("f140_2"):
                if f1 == f2:
                    self.nzxt.set_color("sync", "super-fixed", f1)
                else:
                    self.nzxt.set_color("led1", "super-fixed", f1)
                    self.nzxt.set_color("led2", "super-fixed", f2)
        if self.fdev is not None:
            for name, (_zone, cmd, _bit) in ARGB_HEADERS.items():
                cols = frame.get(name)
                if cols is None:                                          # nepouzita hlavicka = zhasnout
                    if force:
                        _argb_strip(self.fdev, cmd, [[0, 0, 0]] * ARGB_MAX_LEDS, self.orders[name])
                    continue
                if force or cols != self.last.get(name):
                    pad = [[0, 0, 0]] * (ARGB_MAX_LEDS - len(cols))
                    _argb_strip(self.fdev, cmd, cols + pad, self.orders[name])
        self.last = frame

    def close(self):
        for d in (self.nzxt, self.fusion):
            if d is not None:
                try:
                    d.disconnect()
                except Exception:
                    pass


def _still(lcfg, typ):
    """Staticky stav vsech ventilatoru: "vlastni" = vlastni barvy LED, "vypnuto" = zhasnuto."""
    return dict(lcfg, stejne_pro_vse=True, efekt={"typ": typ})


class LedWorker(threading.Thread):
    def __init__(self):
        super().__init__(name="led", daemon=True)
        self._lock = threading.Lock()
        self._cfg = None
        self._data = {}
        self._quit = threading.Event()
        self._wake = threading.Event()
        self._off_req = threading.Event()    # uspani: zhasnout a do probuzeni nic neposilat
        self._off_done = threading.Event()
        self._resume = threading.Event()
        self._shutdown = False               # konci Windows: LED zhasnout (ne klidny stav)
        self.state = {"stav": "čeká"}

    def update(self, lcfg, data=None):
        with self._lock:
            self._cfg = lcfg
            if data is not None:
                self._data = data
        self._wake.set()

    def blackout(self, timeout=1.5):
        """PC se uspava: zhasnout LED. Deska drzi hlavicku ARGB pod napetim i ve spanku
        a ve vypnutem PC, takze by na ventilatorech zustal zamrzly posledni snimek."""
        if not self.is_alive():
            return
        self._off_done.clear()
        self._resume.clear()
        self._off_req.set()
        self._wake.set()
        self._off_done.wait(timeout)

    def resume(self):
        self._resume.set()
        self._wake.set()

    def stop(self, timeout=1.0, off=False):
        """off=True (vypnuti PC, odhlaseni): LED zhasnout; jinak klidny stav (vlastni barvy)."""
        self._shutdown = off
        self._quit.set()
        self._wake.set()
        self.join(timeout)

    def _set_state(self, state):
        if state.get("stav") != self.state.get("stav") or state.get("chyby") != self.state.get("chyby"):
            if state.get("stav") == "chyba":
                log.warning("LED: %s", "; ".join(state.get("chyby", [])))
            elif state.get("stav") == "běží":
                log.info("LED: efekty běží.")
        self.state = state

    def run(self):
        engine = fx.Engine()
        session, hw_key, t0 = None, None, time.monotonic()
        last_wall, last_force, prev = time.time(), 0.0, time.monotonic()
        while not self._quit.is_set():
            with self._lock:
                lcfg, data = self._cfg, self._data
            if lcfg is None or not lcfg.get("zapnuto", True):
                if session:
                    session.close()
                    session = None
                if lcfg is not None:
                    self._set_state({"stav": "vypnuto"})
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            if self._off_req.is_set():
                self._off_req.clear()
                if session:
                    try:
                        session.send(render(engine, _still(lcfg, "vypnuto"), 0.0), force=True)
                    except Exception:
                        pass
                    session.close()
                    session = None
                self._off_done.set()
                log.info("LED: PC se uspava - LED zhasnute.")
                # do probuzeni nic neposilat; kdyby se uspani nepovedlo, po 2 min pokracovat
                deadline = time.time() + 120
                while not (self._quit.is_set() or self._resume.is_set()) and time.time() < deadline:
                    self._quit.wait(1.0)
                last_wall = time.time()
                continue
            now_wall, now = time.time(), time.monotonic()
            resumed = now_wall - last_wall > RESUME_GAP_S
            last_wall = now_wall
            key = json.dumps({"z": lcfg.get("fusion"), "a": lcfg.get("argb")}, sort_keys=True)
            try:
                if session is None or resumed:
                    if session:
                        session.close()
                    if resumed:
                        log.info("LED: PC se probudilo - nastavuji LED znovu.")
                    session = Session(lcfg)
                    hw_key, last_force = key, 0.0
                    if session.errors:
                        raise RuntimeError("; ".join(session.errors))
                elif key != hw_key:
                    session.setup_zones(lcfg)
                    hw_key, last_force = key, 0.0
                dt, prev = now - prev, now
                frame = render(engine, lcfg, now - t0, data, min(dt, 0.2))
                force = now - last_force > REFRESH_S
                session.send(frame, force)
                if force:
                    last_force = now
                self._set_state({"stav": "běží"})
            except Exception as e:
                if session:
                    session.close()
                    session = None
                self._set_state({"stav": "chyba", "chyby": [str(e)]})
                self._quit.wait(RETRY_S)
                continue
            if is_animated(lcfg):
                self._quit.wait(max(0.0, 1 / fx.FPS - (time.monotonic() - now)))
            else:
                self._wake.wait(1.0)
                self._wake.clear()
        # konec aplikace: klidny staticky stav (vlastni barvy LED s nastavenym jasem);
        # pri vypnuti PC zhasnout - deska drzi ARGB pod napetim i ve vypnutem PC
        if session:
            try:
                session.send(render(engine, _still(lcfg, "vypnuto" if self._shutdown else "vlastni"), 0.0),
                             force=True)
            except Exception:
                pass
            session.close()
