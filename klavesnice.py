# klavesnice.py - klavesnice Logitech G815 (USB 046D:C33F)
#
#   - integrovana pamet (onboard profily) zapnout / vypnout: protokol HID++ 2.0, funkce
#     Onboard Profiles 0x8100 (setMode 1 = pamet klavesnice, 2 = rizeni z pocitace) - stejne
#     jako G HUB; G HUB o prepnuti z aplikace nevi (jeho prepinac zustane, jak byl)
#   - zaloha integrovane pameti (jen cteni): popis pameti + vsechny sektory do zalohy/*.json
#   - barvy z aplikace pres Logitech LED SDK z instalace G HUB (sdk_legacy_led_x64.dll):
#     funguji jen v rezimu rizeni z pocitace (v integrovane pameti si klavesnice sviti sama);
#     LogiLedShutdown vrati klavesnici G HUBu
#
# HID++ jde pres rozhrani usage page 0xFF43, usage 0x602 (dlouhe zpravy 20 B, report 0x11).
# G HUB na stejnem rozhrani posila sve prikazy (swid 0x0D) - nase maji swid 0x0A.

import ctypes
import json
import logging
import os
import threading
import time

log = logging.getLogger("rgb_lcd")

VID, PID = 0x046D, 0xC33F
NAME = "Logitech G815"
SWID = 0x0A
FEATURE_ONBOARD = 0x8100
MODE_ONBOARD, MODE_HOST = 1, 2
MODES = {MODE_ONBOARD: "integrovaná paměť", MODE_HOST: "řízení z počítače"}
SDK_DLL = r"C:\Program Files\LGHUB\sdks\sdk_legacy_led_x64.dll"
BASE = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE, "zalohy")
_lock = threading.Lock()                     # HID++ dotazy z vice vlaken okna


class HidppError(RuntimeError):
    pass


class G815:
    """Spojeni HID++ s klavesnici (jen to, co aplikace potrebuje)."""

    def __init__(self):
        import hid
        path = next((d["path"] for d in hid.enumerate(VID, PID)
                     if d["usage_page"] == 0xFF43 and d["usage"] == 0x602), None)
        if path is None:
            raise HidppError(f"{NAME} nenalezena")
        self.h = hid.device()
        self.h.open_path(path)
        self.h.set_nonblocking(True)
        self._features = {}

    def close(self):
        try:
            self.h.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def request(self, idx, func, params=(), timeout=1.0):
        """Poslat prikaz a pockat na odpoved se stejnou funkci a nasim swid."""
        fs = (func << 4) | SWID
        with _lock:
            while self.h.read(64):                 # zahodit stare zpravy (i od G HUB)
                pass
            self.h.write([0x11, 0xFF, idx, fs] + list(params) + [0] * (16 - len(params)))
            end = time.time() + timeout
            while time.time() < end:
                r = self.h.read(64)
                if r and r[0] == 0x11:
                    if r[2] == idx and r[3] == fs:
                        return r[4:20]
                    if r[2] == 0xFF and r[3] == idx and r[4] == fs:
                        raise HidppError(f"klávesnice odmítla příkaz (chyba HID++ {r[5]})")
                time.sleep(0.003)
        raise HidppError("klávesnice neodpovídá")

    def feature(self, code):
        if code not in self._features:
            r = self.request(0, 0, [code >> 8, code & 0xFF])
            if not r[0]:
                raise HidppError(f"klávesnice nemá funkci 0x{code:04X}")
            self._features[code] = r[0]
        return self._features[code]

    # ----------------------------------------------------- integrovana pamet
    def onboard_mode(self):
        return self.request(self.feature(FEATURE_ONBOARD), 2)[0]

    def set_onboard_mode(self, mode):
        self.request(self.feature(FEATURE_ONBOARD), 1, [mode])
        now = self.onboard_mode()
        if now != mode:
            raise HidppError(f"režim se nezměnil (klávesnice hlásí {MODES.get(now, now)})")

    def memory_description(self):
        d = self.request(self.feature(FEATURE_ONBOARD), 0)
        return {"model_pameti": d[0], "format_profilu": d[1], "format_maker": d[2], "profilu": d[3],
                "profilu_v_rom": d[4], "tlacitek": d[5], "sektoru": d[6], "velikost_sektoru": (d[7] << 8) | d[8],
                "rozlozeni": d[9], "dalsi": d[10]}

    def read_sector(self, sector, size):
        idx = self.feature(FEATURE_ONBOARD)
        out = []
        for off in range(0, size, 16):
            o = min(off, size - 16)               # posledni cteni nesmi prekrocit sektor
            chunk = self.request(idx, 5, [sector >> 8, sector & 0xFF, o >> 8, o & 0xFF])
            out[o:o + 16] = list(chunk)
        return out[:size]


def get_mode():
    """Rezim klavesnice (1 / 2), nebo vyjimka."""
    with G815() as k:
        return k.onboard_mode()


def set_mode(mode):
    with G815() as k:
        k.set_onboard_mode(mode)
    log.info("%s: %s.", NAME, MODES.get(mode, mode))


def backup_memory(progress=None):
    """Precist celou integrovanou pamet (uzivatelske sektory + tovarni profily v ROM) do JSON.
    Jen cteni - do klavesnice se nic nezapisuje. Vrati cestu k souboru."""
    with G815() as k:
        desc = k.memory_description()
        size = desc["velikost_sektoru"]
        sectors = list(range(desc["sektoru"])) + [0x0100 + i + 1 for i in range(desc["profilu_v_rom"])]
        data = {}
        for n, s in enumerate(sectors):
            data[f"0x{s:04X}"] = bytes(k.read_sector(s, size)).hex()
            if progress:
                progress(n + 1, len(sectors))
        mode = k.onboard_mode()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, time.strftime("g815_pamet_%Y-%m-%d_%H%M%S.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"zarizeni": NAME, "cas": time.strftime("%Y-%m-%d %H:%M:%S"), "rezim": MODES.get(mode, mode),
                   "popis": desc, "sektory": data}, f, ensure_ascii=False, indent=1)
    log.info("%s: záloha integrované paměti uložena (%s).", NAME, os.path.basename(path))
    return path


class Sdk:
    """Logitech LED SDK z G HUB - barva cele klavesnice. Kdyz G HUB nebezi nebo SDK chybi,
    ok = False a nic se neposila."""

    def __init__(self):
        self.dll = None
        self.ok = False
        self.last = None

    def start(self):
        if self.ok:
            return True
        if not os.path.exists(SDK_DLL):
            raise RuntimeError("Logitech G HUB (LED SDK) není nainstalovaný")
        if self.dll is None:
            self.dll = ctypes.CDLL(SDK_DLL)
            self.dll.LogiLedInitWithName.argtypes = [ctypes.c_char_p]
        if not self.dll.LogiLedInitWithName(b"RGB-LCD"):
            raise RuntimeError("G HUB neodpovídá (běží G HUB?)")
        self.dll.LogiLedSetTargetDevice(0x04)      # klavesnice s barvou kazde klavesy
        self.ok, self.last = True, None
        return True

    def color(self, rgb, force=False):
        """rgb 0-255 -> SDK bere procenta 0-100."""
        pct = tuple(int(round(max(0, min(255, v)) * 100 / 255)) for v in rgb)
        if self.ok and (force or pct != self.last):
            self.dll.LogiLedSetLighting(*pct)
            self.last = pct

    def stop(self):
        """Vratit klavesnici G HUBu."""
        if self.ok:
            try:
                self.dll.LogiLedShutdown()
            except Exception:
                pass
        self.ok, self.last = False, None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--zaloha" in sys.argv:
        print(backup_memory(lambda i, n: print(f"\r  sektor {i}/{n}", end="")))
    else:
        print("režim:", MODES.get(get_mode()))
