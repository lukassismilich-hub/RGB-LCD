# hlasitost.py - hlasitost Windows (vychozi vystupni zarizeni) pro efekt hlasitosti na klavesnici G815
#
# Core Audio pres ctypes (bez comtypes / pycaw): IMMDeviceEnumerator -> GetDefaultAudioEndpoint(eRender,
# eMultimedia) -> IMMDevice::Activate(IAudioEndpointVolume) -> GetMasterVolumeLevelScalar / GetMute.
# Endpoint se drzi otevreny a po REFRESH_S nebo po chybe se vezme znovu (zmena vychoziho zarizeni,
# napr. sluchatka). Volat ze stejneho vlakna (COM se inicializuje v nem pri prvnim volani).

import ctypes
import logging
import time
from ctypes import wintypes as wt

from zvuk_procesu import GUID, _call, _check, _release, ole32

log = logging.getLogger("rgb_lcd")

CLSID_MMDeviceEnumerator = GUID.of("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID.of("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioEndpointVolume = GUID.of("5CDF2C82-841E-4546-9722-0CF74078229A")
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
E_RENDER, E_MULTIMEDIA = 0, 1
REFRESH_S = 5.0                                   # znovu vzit vychozi zarizeni (mohlo se zmenit)

ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(GUID),
                                   ctypes.POINTER(ctypes.c_void_p)]
ole32.CoCreateInstance.restype = ctypes.c_long


class Volume:
    """Hlasitost vychoziho vystupu: read() -> (0..1, ztlumeno) nebo None, kdyz nejde precist."""

    def __init__(self):
        self._ep = None
        self._t = 0.0
        self._com = False

    def _open(self):
        self.close()
        if not self._com:
            ole32.CoInitializeEx(None, COINIT_MULTITHREADED)   # uz inicializovane (S_FALSE / jiny rezim) nevadi
            self._com = True
        en, dev, ep = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _check(ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                                          ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(en)),
                   "MMDeviceEnumerator")
            _check(_call(en, 4, E_RENDER, E_MULTIMEDIA, ctypes.byref(dev),
                         argtypes=(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))),
                   "GetDefaultAudioEndpoint")
            _check(_call(dev, 3, ctypes.byref(IID_IAudioEndpointVolume), CLSCTX_ALL, None, ctypes.byref(ep),
                         argtypes=(ctypes.POINTER(GUID), wt.DWORD, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p))), "Activate")
            self._ep, ep = ep, None
            self._t = time.monotonic()
        finally:
            _release(ep)
            _release(dev)
            _release(en)

    def read(self):
        try:
            if not self._ep or time.monotonic() - self._t > REFRESH_S:
                self._open()
            lvl, mute = ctypes.c_float(), wt.BOOL()
            _check(_call(self._ep, 9, ctypes.byref(lvl), argtypes=(ctypes.POINTER(ctypes.c_float),)),
                   "GetMasterVolumeLevelScalar")
            _check(_call(self._ep, 15, ctypes.byref(mute), argtypes=(ctypes.POINTER(wt.BOOL),)), "GetMute")
            return max(0.0, min(1.0, lvl.value)), bool(mute.value)
        except OSError:
            self.close()
            return None

    def close(self):
        if self._ep:
            _release(self._ep)
        self._ep = None


# ----------------------------------------------------------------- efekt hlasitosti na klavesnici

# config["led"]["hlasitost_klavesnice"] (spolecne pro M1-M3, ma prednost pred vsim): po pohybu posuvnikem
# hlasitosti / ztlumeni (klavesy_stisk.drain_volume) ukazuji vybrane klavesy hlasitost jako ukazatel
DEFAULT = {"zapnuto": False, "klavesy": [27 + i for i in range(10)], "smer": "zleva", "barva_od": "#00ff40",
           "barva_do": "#ff2000", "pozadi": "#0a0a0a", "ztlumeno": "#ff0000", "ostatni": "efekt", "doba_s": 2.0}
DIRECTIONS = [("zleva", "zleva"), ("zprava", "zprava"), ("zdola", "zdola"), ("shora", "shora")]
OTHERS = [("efekt", "svítí dál"), ("ztmavit", "ztmavit"), ("zhasnout", "zhasnout")]
OTHER_K = {"efekt": 1.0, "ztmavit": 0.2, "zhasnout": 0.0}
FADE_IN_S, FADE_OUT_S = 0.08, 0.4


def settings(lcfg):
    """Nastaveni efektu hlasitosti s vychozimi hodnotami (cteni, nic nezapisuje)."""
    v = (lcfg or {}).get("hlasitost_klavesnice")
    v = v if isinstance(v, dict) else {}
    return {k: v.get(k, d) for k, d in DEFAULT.items()}


def _rgb(h):
    h = str(h).lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def order(zones, smer):
    """Klavesy ukazatele v poradi plneni (podle polohy na klavesnici)."""
    import klavesnice_rozlozeni as R
    pos = {k[0]: (k[2] + k[4] / 2, k[3] + k[5] / 2) for k in R.KEYS}
    zs = [z for z in dict.fromkeys(zones or []) if z in pos]
    if smer in ("zdola", "shora"):
        zs.sort(key=lambda z: (-pos[z][1], pos[z][0]))
    else:
        zs.sort(key=lambda z: (pos[z][0], -pos[z][1]))
    return zs[::-1] if smer in ("zprava", "shora") else zs


def meter(cfg, level, muted):
    """{zona: (r, g, b)} ukazatele hlasitosti (level 0..1)."""
    zs = order(cfg["klavesy"], cfg["smer"])
    if not zs:
        return {}
    if muted:
        c = _rgb(cfg["ztlumeno"])
        return {z: c for z in zs}
    a, b, bg = _rgb(cfg["barva_od"]), _rgb(cfg["barva_do"]), _rgb(cfg["pozadi"])
    n = len(zs)
    fill = max(0.0, min(1.0, level)) * n
    out = {}
    for i, z in enumerate(zs):
        t = i / (n - 1) if n > 1 else 0.0
        col = tuple(round(a[j] + (b[j] - a[j]) * t) for j in range(3))
        k = max(0.0, min(1.0, fill - i))           # rozsvicena cast klavesy (posledni muze byt castecne)
        out[z] = tuple(round(bg[j] + (col[j] - bg[j]) * k) for j in range(3))
    return out


class Overlay:
    """Kdy a jak ukazat hlasitost: trigger() pri pohybu posuvnikem, frame() -> kb_top pro led.render."""

    def __init__(self):
        self.t = -1e9                                # posledni pohyb posuvnikem (monotonic)
        self.t0 = -1e9                               # zacatek zobrazeni (prolnuti dovnitr)
        self._hold = DEFAULT["doba_s"]

    def trigger(self, now):
        if now - self.t > self._hold + FADE_OUT_S:   # znovu od zacatku
            self.t0 = now
        self.t = now

    def alpha(self, cfg, now):
        self._hold = max(0.3, float(cfg.get("doba_s", 2.0)))
        age = now - self.t
        if age > self._hold + FADE_OUT_S:
            return 0.0
        a = min(1.0, (now - self.t0) / FADE_IN_S) if FADE_IN_S > 0 else 1.0
        if age > self._hold:
            a *= 1.0 - (age - self._hold) / FADE_OUT_S
        return max(0.0, min(1.0, a))

    def frame(self, cfg, now, level, muted):
        a = self.alpha(cfg, now)
        if a <= 0 or level is None:
            return None
        return {"barvy": meter(cfg, level, muted), "ostatni": OTHER_K.get(cfg.get("ostatni"), 1.0), "a": a}

    def busy(self, cfg, now):
        return self.alpha(cfg, now) > 0


def compose(cols, top):
    """Ukazatel hlasitosti pres barvy klavesnice (poradi klavesnice_efekty.KEYS)."""
    import klavesnice_efekty as kbfx
    a, dim, sel = top["a"], top["ostatni"], top["barvy"]
    out = list(cols)
    for z, i in kbfx.INDEX.items():
        c = out[i]
        tgt = sel.get(z)
        if tgt is None:
            if dim >= 1.0:
                continue
            tgt = tuple(v * dim for v in c)
        out[i] = tuple(c[j] + (tgt[j] - c[j]) * a for j in range(3))
    return out


if __name__ == "__main__":
    # test: hlasitost + udalosti hlasitosti z hooku klavesnice (otoc posuvnikem hlasitosti)
    import sys
    import klavesy_stisk
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    v = Volume()
    print("hlasitost:", v.read())
    w = klavesy_stisk.start()
    print(f"Toč posuvníkem hlasitosti / zmáčkni ztlumení ({secs:g} s)…", flush=True)
    end, last = time.time() + secs, None
    while time.time() < end:
        for e in w.drain_volume():
            print("klávesa:", e, "->", v.read())
        cur = v.read()
        if cur != last:
            print("  hlasitost", cur)
            last = cur
        time.sleep(0.05)
    klavesy_stisk.stop()
