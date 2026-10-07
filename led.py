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
#   - graficka karta RTX 5070 Eagle OC = jedna barva bocniho pasku pres I2C karty (grafika.py, NvAPI),
#     ve vlne za D_LED2 (karta je pod F140)
#   - klavesnice Logitech G815 = jedna barva cele klavesnice pres Logitech LED SDK z G HUB
#     (klavesnice.py); funguje jen pri vypnute integrovane pameti klavesnice. Zatim skryta (KEYBOARD).
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
    "grafika": ("jako grafika", False, False),   # barvu pocita aplikace stejne jako pasek grafiky
}
SYNC_ZONE = "grafika"                        # rezim zony desky, ktera sviti s grafikou (LED pasek u karty)
FUSION_SPEEDS = {"slowest": "nejpomaleji", "slower": "pomaleji", "normal": "normálně", "faster": "rychleji",
                 "fastest": "nejrychleji", "ludicrous": "šíleně rychle"}

# ARGB hlavicky desky: nazev -> (zona liquidctl, prikaz pro barvy po LED, bit masky 0x32)
ARGB_HEADERS = {"D_LED1": ("led6", 0x58, 0x01), "D_LED2": ("led7", 0x59, 0x02)}
ARGB_ZONES = {v[0] for v in ARGB_HEADERS.values()}
ARGB_MAX_LEDS = 32
KEYBOARD = False             # klavesnice G815 zatim skryta (v okne i ve vlakne), kod zustava
EXTRAS = ("grafika", "klavesnice")   # cile s jednou "LED" mimo ventilatory (bez natoceni)
EXTRA_DEFAULT = {"zapnuto": False, "efekt": "deska", "jas": 100, "barva": "#ffffff"}


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
        "vlna_smer": "dozadu",                     # "dozadu" = od predku skrine dozadu, "dopredu"
        "vlna_f140_spolu": True,                   # F140 ve vlne jako jeden ventilator
        "f140_vpredu": "led1",                     # ktery F140 je bliz predku skrine (led1 / led2)
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
        # grafika a klavesnice: rizeni z aplikace, efekt "f140" / "deska" (jako ventilatory) / "vlastni",
        # barva = klidny stav po ukonceni aplikace
        "grafika": dict(EXTRA_DEFAULT),
        "efekt_grafika": copy.deepcopy(fx.DEFAULT_EFFECT),
        "klavesnice": dict(EXTRA_DEFAULT),
        "efekt_klavesnice": copy.deepcopy(fx.DEFAULT_EFFECT),
    }


def gpu_zones(lcfg):
    """Zony desky (mimo ARGB) v rezimu "jako grafika" - sviti stejne jako pasek graficke karty."""
    return sorted(k for k, z in lcfg.get("fusion", {}).items()
                  if k not in ARGB_ZONES and z.get("rezim") == SYNC_ZONE)


def extra_on(lcfg, key):
    """Ridi aplikace grafiku / klavesnici?"""
    if key == "klavesnice" and not KEYBOARD:
        return False
    return bool(lcfg.get(key, {}).get("zapnuto"))


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
    for key in EXTRAS:                                     # grafika / klavesnice = jedna "LED"
        if extra_on(lcfg, key) or (key == "grafika" and gpu_zones(lcfg)):   # i kvuli zonam "jako grafika"
            out.append((key, 1, key, [lcfg.get(key, EXTRA_DEFAULT).get("barva", "#ffffff")]))
    return out


# rozmisteni ve skrini zepredu dozadu: D_LED1 vpredu, 2x F140 uprostred, D_LED2 vzadu; grafika je pod
# F140, ve vlne az za D_LED2 - vlna tak obehne skrin dokola (predek, nahore, zadek, dole) a navaze
# zase na predek (posuny jsou rovnomerne po kruhu 0..1)
CASE_ORDER = ("D_LED1", "F140", "D_LED2", "grafika")
NO_WAVE = ("klavesnice",)


def wave_offsets(lcfg, keys):
    """{klic: posun faze 0..1} pro vlnu podle rozmisteni ve skrini a smeru vlny.
    Vlna jde od ventilatoru s vetsim posunem k mensimu (ten je ve fazi napred)."""
    order = []
    front = "f140_1" if lcfg.get("f140_vpredu", "led1") == "led1" else "f140_2"
    for slot in CASE_ORDER:
        if slot == "F140":
            order += [k for k in (front, "f140_2" if front == "f140_1" else "f140_1") if k in keys]
        elif slot in keys:
            order.append(slot)
    order += [k for k in keys if k not in order]
    pos, n = {}, 0
    for k in order:
        if k.startswith("f140_") and lcfg.get("vlna_f140_spolu", True) and any(
                p.startswith("f140_") for p in pos):
            pos[k] = next(v for p, v in pos.items() if p.startswith("f140_"))    # F140 jako jeden
            continue
        pos[k] = n
        n += 1
    back = lcfg.get("vlna_smer", "dozadu") == "dozadu"
    return {k: ((n - 1 - v) if back else v) / max(1, n) for k, v in pos.items()}, order


def effect_for(lcfg, group):
    if group in EXTRAS:                                    # vlastni efekt, nebo jako F140 / deska
        src = lcfg.get(group, {}).get("efekt", "deska")
        if src == "vlastni":
            return lcfg.get(f"efekt_{group}", fx.DEFAULT_EFFECT)
        group = "f140" if src == "f140" else "deska"
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
    wave = bool(lcfg.get("vlna"))
    offsets = wave_offsets(lcfg, [k for k, *_ in tg if k not in NO_WAVE])[0] if wave else {}
    span = max(offsets.values(), default=0.0)
    out = {}
    for idx, (key, n, group, custom) in enumerate(tg):
        eff = effect_for(lcfg, group)
        cols = engine.frame(eff, t, key, n, idx, len(tg), wave, custom, data, dt, offset=offsets.get(key, 0.0),
                            span=span)
        if orient and eff.get("typ") not in ("vlastni", "vypnuto"):   # vlastni barvy jsou uz po LED
            cols = _orient(cols, *orientation(lcfg, key))
        if group in EXTRAS:
            k = float(lcfg.get("jas", 80)) * float(lcfg.get(group, EXTRA_DEFAULT).get("jas", 100)) / 100.0
        else:
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


def _zone_fixed(dev, zone, rgb):
    """Cela zona desky (male LED, 12V RGB) jednou barvou - stejny paket jako liquidctl
    set_color(zone, "fixed"): registr 0x20+n s maskou zony, barva v poradi B G R, jas 90,
    pak 0x28 = pouzit nastaveni a znovu maska primeho rezimu ARGB (0x32), at ji to nezmeni."""
    import liquidctl.driver.rgb_fusion2 as rf
    addr1, addr2 = rf._COLOR_CHANNELS[zone]
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    data = [0xCC, addr1, addr2] + [0] * 8 + [0x01, 90, 0x00, b, g, r]
    dev.send_feature_report(data + [0] * (64 - len(data)))
    dev.send_feature_report([0xCC, 0x28, 0xFF] + [0] * 61)
    dev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)


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
    """Otevrena spojeni s radici a posilani snimku. Kazdy radic zvlast: kdyz jeden chybi
    nebo selze, druhy jede dal a chybejici se zkusi pripojit znovu (retry_missing)."""

    NAMES = {"nzxt": "NZXT RGB Controller (F140)", "fusion": "Gigabyte RGB Fusion (ventilátory na desce)",
             "grafika": "grafická karta", "klavesnice": "klávesnice G815 (G HUB)"}

    def __init__(self, lcfg):
        self.nzxt = self.fusion = self.fdev = None
        self.kbd = None                           # klavesnice.Sdk, kdyz ji aplikace ridi
        self.gpu = None                           # grafika.Gpu, kdyz ji aplikace ridi
        self.sync_zones = gpu_zones(lcfg)         # zony desky "jako grafika"
        self.orders = {k: (1, 0, 2) for k in ARGB_HEADERS}
        self.errors = {}                          # radic -> chyba
        self.last = {}
        self.retry_missing(lcfg)
        self.setup_keyboard(lcfg)
        self.setup_gpu(lcfg)

    def setup_gpu(self, lcfg):
        """LED graficke karty (I2C pres NvAPI): prevzit / pustit. Pri vypnuti rizeni zustane
        klidna barva - vlastni nastaveni karty se vrati az po restartu PC."""
        if not extra_on(lcfg, "grafika"):
            if self.gpu is not None and self.gpu.ok:
                try:
                    self.gpu.color(hex_rgb(lcfg.get("grafika", {}).get("barva", "#ffffff")), True)
                except Exception:
                    pass
                self.gpu.stop()
            self.gpu = None
            self.errors.pop("grafika", None)
            return
        if self.gpu is None:
            import grafika
            self.gpu = grafika.Gpu()
        try:
            if self.gpu.start():
                self.errors.pop("grafika", None)
                self.last.pop("grafika", None)
        except Exception as e:
            self.errors["grafika"] = str(e)

    def setup_keyboard(self, lcfg):
        """Klavesnice G815 pres Logitech LED SDK (G HUB): zapnout / vratit G HUBu."""
        want = extra_on(lcfg, "klavesnice")
        if not want:
            if self.kbd is not None:
                self.kbd.stop()                   # klavesnice zpet G HUBu
                self.kbd = None
            self.errors.pop("klavesnice", None)
            return
        if self.kbd is None:
            import klavesnice
            self.kbd = klavesnice.Sdk()
        try:
            if self.kbd.start():
                self.errors.pop("klavesnice", None)
        except Exception as e:
            self.errors["klavesnice"] = str(e)

    def retry_missing(self, lcfg):
        """Pripojit radice, ktere zatim nejedou. Vrati True, kdyz nejaky pribyl."""
        if "klavesnice" in self.errors:
            self.setup_keyboard(lcfg)
        if "grafika" in self.errors:
            self.setup_gpu(lcfg)
        if self.nzxt is not None and self.fusion is not None:
            return False
        try:
            nzxt, fusion = _devices()
        except Exception as e:
            for k in ("nzxt", "fusion"):
                if getattr(self, k) is None:
                    self.errors[k] = f"hledání řadičů: {e}"
            return False
        added = False
        if self.nzxt is None:
            if nzxt is None:
                self.errors["nzxt"] = "nenalezen"
            else:
                try:
                    nzxt.connect()
                    _init(nzxt)
                    nzxt.set_color("led3", "off", [])                     # volny kanal zhasnout
                    self.nzxt, added = nzxt, True
                    self.errors.pop("nzxt", None)
                except Exception as e:
                    self._drop_dev(nzxt)
                    self.errors["nzxt"] = str(e)
        if self.fusion is None:
            if fusion is None:
                self.errors["fusion"] = "nenalezen"
            else:
                try:
                    fusion.connect()
                    _init(fusion)
                    self.fusion, self.fdev = fusion, fusion.device
                    self.setup_zones(lcfg)
                    report = _argb_report(self.fdev)
                    if report:
                        self.orders = argb_order(report)
                    self.fdev.send_feature_report([0xCC, 0x32, 0x03] + [0] * 61)   # D_LED1+2 primy rezim
                    time.sleep(0.05)
                    added = True
                    self.errors.pop("fusion", None)
                except Exception as e:
                    self._drop_dev(fusion)
                    self.fusion = self.fdev = None
                    self.errors["fusion"] = str(e)
        if added:
            self.last = {}                        # novemu radici poslat cely snimek
        return added

    @staticmethod
    def _drop_dev(d):
        try:
            d.disconnect()
        except Exception:
            pass

    def _fail(self, which, e):
        """Chyba jednoho radice: odpojit jen ten, druhy jede dal."""
        if which in EXTRAS:
            dev = self.kbd if which == "klavesnice" else self.gpu
            if dev is not None:
                dev.stop()
            self.errors[which] = str(e)
            log.warning("LED: %s – %s, zkusím znovu za %d s.", self.NAMES[which], e, RETRY_S)
            return
        self._drop_dev(getattr(self, which))
        setattr(self, which, None)
        if which == "fusion":
            self.fdev = None
        self.errors[which] = str(e)
        log.warning("LED: %s – %s, zkusím znovu za %d s.", self.NAMES[which], e, RETRY_S)

    @property
    def running(self):
        return self.nzxt is not None or self.fusion is not None or (self.gpu is not None and self.gpu.ok)

    def error_text(self):
        return [f"{self.NAMES[k]}: {v}" for k, v in sorted(self.errors.items())]

    def setup_zones(self, lcfg):
        """Ostatni zony desky (male LED, 12V RGB) - jedna barva / efekt cipu."""
        self.sync_zones = gpu_zones(lcfg)          # "jako grafika" - barvu posila send() po snimcich
        self.last.pop("grafika", None)
        if self.fusion is None:
            return
        for name, z in sorted(lcfg.get("fusion", {}).items()):
            if name in ARGB_ZONES or name in self.sync_zones:
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
        """Poslat jen to, co se zmenilo (force = vse). Chyba jednoho radice nezastavi druhy."""
        f1, f2 = frame.get("f140_1"), frame.get("f140_2")
        if self.nzxt is not None and f1 is not None:
            if force or f1 != self.last.get("f140_1") or f2 != self.last.get("f140_2"):
                try:
                    if f1 == f2:
                        self.nzxt.set_color("sync", "super-fixed", f1)
                    else:
                        self.nzxt.set_color("led1", "super-fixed", f1)
                        self.nzxt.set_color("led2", "super-fixed", f2)
                except Exception as e:
                    self._fail("nzxt", e)
        if self.fdev is not None:
            try:
                for name, (_zone, cmd, _bit) in ARGB_HEADERS.items():
                    cols = frame.get(name)
                    if cols is None:                                      # nepouzita hlavicka = zhasnout
                        if force:
                            _argb_strip(self.fdev, cmd, [[0, 0, 0]] * ARGB_MAX_LEDS, self.orders[name])
                        continue
                    if force or cols != self.last.get(name):
                        pad = [[0, 0, 0]] * (ARGB_MAX_LEDS - len(cols))
                        _argb_strip(self.fdev, cmd, cols + pad, self.orders[name])
                gp = frame.get("grafika")                                 # zony "jako grafika"
                if gp and self.sync_zones and (force or gp != self.last.get("grafika")):
                    for zone in self.sync_zones:
                        _zone_fixed(self.fdev, zone, gp[0])
            except Exception as e:
                self._fail("fusion", e)
        kb = frame.get("klavesnice")
        if self.kbd is not None and self.kbd.ok and kb:
            try:
                self.kbd.color(kb[0], force)
            except Exception as e:
                self._fail("klavesnice", e)
        gp = frame.get("grafika")
        if self.gpu is not None and self.gpu.ok and gp:
            try:
                self.gpu.color(gp[0], force)
            except Exception as e:
                self._fail("grafika", e)
        self.last = frame

    def close(self):
        if self.gpu is not None:
            self.gpu.stop()                       # karta drzi posledni poslanou barvu
            self.gpu = None
        if self.kbd is not None:
            self.kbd.stop()                       # klavesnice zpet G HUBu
            self.kbd = None
        for d in (self.nzxt, self.fusion):
            if d is not None:
                try:
                    d.disconnect()
                except Exception:
                    pass


def _still(lcfg, typ):
    """Staticky stav vsech ventilatoru: "vlastni" = vlastni barvy LED, "vypnuto" = zhasnuto.
    Plati i pro grafiku / klavesnici (jejich vlastni efekt se pri tom nepouzije)."""
    extras = {k: dict(lcfg[k], efekt="deska") for k in EXTRAS if isinstance(lcfg.get(k), dict)}
    return dict(lcfg, stejne_pro_vse=True, efekt={"typ": typ}, **extras)


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
            elif state.get("stav") == "běží" and state.get("chyby"):
                log.warning("LED: běží jen část – %s", "; ".join(state["chyby"]))
            elif state.get("stav") == "běží":
                log.info("LED: efekty běží.")
        self.state = state

    def run(self):
        engine = fx.Engine()
        session, hw_key, t0 = None, None, time.monotonic()
        last_wall, last_force, prev, last_retry = time.time(), 0.0, time.monotonic(), time.monotonic()
        while not self._quit.is_set():
            with self._lock:
                lcfg, data = self._cfg, self._data
            if lcfg is None or not lcfg.get("zapnuto", True):
                if session:
                    # rizeni LED vypnuto: klidny stav (vlastni barvy), at nezustane zamrzly snimek
                    try:
                        session.send(render(engine, _still(lcfg, "vlastni"), 0.0), force=True)
                    except Exception:
                        pass
                    session.close()
                    session = None
                    log.info("LED: řízení vypnuto – ventilátory mají vlastní barvy LED.")
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
            key = json.dumps({"z": lcfg.get("fusion"), "a": lcfg.get("argb"),
                              "k": extra_on(lcfg, "klavesnice"), "g": extra_on(lcfg, "grafika")}, sort_keys=True)
            try:
                if session is None or resumed:
                    if session:
                        session.close()
                    if resumed:
                        log.info("LED: PC se probudilo - nastavuji LED znovu.")
                    session = Session(lcfg)
                    hw_key, last_force, last_retry = key, 0.0, now
                    if not session.running:              # nejede ani jeden radic
                        raise RuntimeError("; ".join(session.error_text()))
                elif session.errors and now - last_retry > RETRY_S:
                    last_retry = now                     # chybejici radic zkusit znovu, druhy jede dal
                    if session.retry_missing(lcfg):
                        hw_key, last_force = key, 0.0
                elif key != hw_key:
                    try:
                        session.setup_zones(lcfg)
                    except Exception as e:
                        session._fail("fusion", e)
                    session.setup_keyboard(lcfg)              # klavesnice zapnuta / vracena G HUBu
                    session.setup_gpu(lcfg)                   # grafika zapnuta / vypnuta
                    hw_key, last_force = key, 0.0
                dt, prev = now - prev, now
                frame = render(engine, lcfg, now - t0, data, min(dt, 0.2))
                force = now - last_force > REFRESH_S
                session.send(frame, force)
                if force:
                    last_force = now
                if not session.running:                  # oba radice selhaly za behu
                    raise RuntimeError("; ".join(session.error_text()))
                self._set_state({"stav": "běží", "chyby": session.error_text()} if session.errors
                                else {"stav": "běží"})
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
