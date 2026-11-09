# klavesnice.py - klavesnice Logitech G815 (USB 046D:C33F)
#
#   - integrovana pamet (onboard profily) zapnout / vypnout: protokol HID++ 2.0, funkce
#     Onboard Profiles 0x8100 (setMode 1 = pamet klavesnice, 2 = rizeni z pocitace) - stejne
#     jako G HUB; G HUB o prepnuti z aplikace nevi (jeho prepinac zustane, jak byl)
#   - zaloha integrovane pameti (jen cteni): popis pameti + vsechny sektory do zalohy/*.json
#   - barvy z aplikace primo pres HID++ (Per-key lighting 0x8081), bez G HUB (Direct): aplikace sama
#     vypne integrovanou pamet (rezim rizeni z pocitace) a pri konci ji zase zapne. G HUB ma u G815
#     nechanou zapnutou pamet (settings.db: devices/g815/persistent_data/onboardMode/enabled), takze
#     v rezimu z pocitace nic neposila a barvy neprepisuje (overeno 9. 11. 2026). Kdyby mel pamet
#     vypnutou, posila ~20x za s sve podsviceni - aplikace to pozna a ohlasi (GHUB_BUSY).
#
# HID++ jde pres rozhrani usage page 0xFF43, usage 0x602 (dlouhe zpravy 20 B, report 0x11).
# G HUB na stejnem rozhrani posila sve prikazy (swid 0x0D) - nase maji swid 0x0A (vlakno LED)
# a 0x0B (okno nastaveni, SWID_UI), aby si odpovedi dvou procesu neprebiraly.

import json
import logging
import os
import threading
import time

log = logging.getLogger("rgb_lcd")

VID, PID = 0x046D, 0xC33F
NAME = "Logitech G815"
SWID = 0x0A
SWID_UI = 0x0B
FEATURE_ONBOARD = 0x8100
FEATURE_PERKEY = 0x8081
CHECK_S = 5                                  # jak casto overit, ze je pamet porad vypnuta
FOREIGN_S = 3                                # cizi podsviceni (G HUB) videne za posledni 3 s = konflikt
GHUB_BUSY = ("G HUB řídí podsvícení klávesnice sám (má u G815 vypnutou integrovanou paměť) a přepisoval by "
             "barvy – v G HUB u klávesnice zapni „Integrovaná paměť“, vypínat ji bude aplikace")
MODE_ONBOARD, MODE_HOST = 1, 2
MODES = {MODE_ONBOARD: "integrovaná paměť", MODE_HOST: "řízení z počítače"}
BASE = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE, "zalohy")
_lock = threading.Lock()                     # HID++ dotazy z vice vlaken okna


class HidppError(RuntimeError):
    pass


class G815:
    """Spojeni HID++ s klavesnici (jen to, co aplikace potrebuje)."""

    def __init__(self, swid=SWID_UI):
        import hid
        path = next((d["path"] for d in hid.enumerate(VID, PID)
                     if d["usage_page"] == 0xFF43 and d["usage"] == 0x602), None)
        if path is None:
            raise HidppError(f"{NAME} nenalezena")
        self.h = hid.device()
        self.h.open_path(path)
        self.h.set_nonblocking(True)
        self._features = {}
        self.swid = swid
        self.foreign_t = None                      # kdy naposled poslal podsviceni nekdo jiny (G HUB)

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
        fs = (func << 4) | self.swid
        with _lock:
            while True:                            # zahodit stare zpravy (i od G HUB)
                r = self.h.read(64)
                if not r:
                    break
                self._note(r)
            self.h.write([0x11, 0xFF, idx, fs] + list(params) + [0] * (16 - len(params)))
            end = time.time() + timeout
            while time.time() < end:
                r = self.h.read(64)
                self._note(r)
                if r and r[0] == 0x11:
                    if r[2] == idx and r[3] == fs:
                        return r[4:20]
                    if r[2] == 0xFF and r[3] == idx and r[4] == fs:
                        raise HidppError(f"klávesnice odmítla příkaz (chyba HID++ {r[5]})")
                time.sleep(0.003)
        raise HidppError("klávesnice neodpovídá")

    def _note(self, r):
        """Odpoved na cizi prikaz podsviceni po klavesach (G HUB) - zapamatovat cas."""
        if (r and r[0] == 0x11 and (r[3] & 0x0F) not in (0, self.swid, SWID, SWID_UI)
                and r[2] == self._features.get(FEATURE_PERKEY)):
            self.foreign_t = time.monotonic()

    def foreign(self, secs=FOREIGN_S):
        """Poslal nekdo jiny (G HUB) podsviceni za poslednich secs sekund?"""
        return self.foreign_t is not None and time.monotonic() - self.foreign_t < secs

    def sniff(self, secs):
        """Chvili jen poslouchat (zjisti, jestli G HUB sam posila podsviceni)."""
        end = time.monotonic() + secs
        with _lock:
            while time.monotonic() < end:
                r = self.h.read(64)
                if r:
                    self._note(r)
                else:
                    time.sleep(0.005)
        return self.foreign(secs + 0.1)

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

    # ----------------------------------------------------- podsviceni po klavesach (0x8081)
    def zones(self):
        """Zony (klavesy, logo, G-klavesy, multimedia) - bitova mapa getInfo po strankach 112 zon."""
        idx = self.feature(FEATURE_PERKEY)
        out = []
        for page in range(3):
            bm = self.request(idx, 0, [0, page])[2:]
            out += [page * 112 + i * 8 + bit for i, b in enumerate(bm) for bit in range(8) if b >> bit & 1]
        return out


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


def _ranges(ids):
    """Souvisle useky zon [(prvni, posledni)]."""
    out = []
    for z in sorted(ids):
        if out and z == out[-1][1] + 1:
            out[-1][1] = z
        else:
            out.append([z, z])
    return [tuple(r) for r in out]


class Direct:
    """Barva cele klavesnice primo pres HID++ (0x8081) - bez G HUB a bez jeho SDK.
    start() vypne integrovanou pamet (rezim rizeni z pocitace), stop() ji zase zapne - klavesnice
    pak sviti podle profilu v pameti. Rezim se overuje kazdych CHECK_S s: po odpojeni, probuzeni PC
    nebo restartu G HUB se klavesnice vrati do pameti a aplikace ji prepne znovu."""

    def __init__(self):
        self.k = None
        self.ok = False
        self.last = None
        self.ranges = []
        self.checked = 0.0
        self.ghub = False                          # G HUB ridi podsviceni sam - pak rezim nemenit

    def start(self):
        if self.ok:
            return True
        k = G815(SWID)
        try:
            k.feature(FEATURE_PERKEY)
            self.ranges = _ranges(k.zones())
            self.ghub = k.onboard_mode() == MODE_HOST and k.sniff(0.5)
            if self.ghub:                          # G HUB ma pamet vypnutou a posila sve barvy
                raise HidppError(GHUB_BUSY)
            self.k = k
            self._host()
        except Exception:
            k.close()
            self.k = None
            raise
        self.ok, self.last = True, None
        return True

    def _host(self):
        """Vypnout integrovanou pamet, kdyby se mezitim zapnula."""
        if self.k.onboard_mode() != MODE_HOST:
            self.k.set_onboard_mode(MODE_HOST)
            self.last = None                       # po prepnuti poslat barvy znovu
            log.info("%s: integrovaná paměť vypnuta – podsvícení řídí aplikace.", NAME)
        self.checked = time.monotonic()

    def color(self, rgb, force=False):
        if not self.ok:
            return
        if time.monotonic() - self.checked > CHECK_S:
            if self.k.foreign():
                self.ghub = True
                raise HidppError(GHUB_BUSY)
            self._host()
        rgb = tuple(int(max(0, min(255, v))) for v in rgb)
        if force or rgb != self.last:
            idx = self.k.feature(FEATURE_PERKEY)
            for i in range(0, len(self.ranges), 3):            # setRangeRgbZones: 3 useky v prikazu
                self.k.request(idx, 5, [v for a, b in self.ranges[i:i + 3] for v in (a, b) + rgb])
            self.k.request(idx, 7, [0, 0, 0, 0])               # frameEnd = zobrazit
            self.last = rgb

    def stop(self):
        """Zapnout zpet integrovanou pamet (klavesnice sviti podle sveho profilu) a zavrit spojeni.
        Kdyz podsviceni ridi G HUB sam, rezim se nemeni."""
        if self.k is not None:
            if not self.ghub:
                try:
                    self.k.set_onboard_mode(MODE_ONBOARD)
                    log.info("%s: integrovaná paměť zapnuta.", NAME)
                except Exception:
                    pass
            self.k.close()
        self.k, self.ok, self.last = None, False, None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--zaloha" in sys.argv:
        print(backup_memory(lambda i, n: print(f"\r  sektor {i}/{n}", end="")))
    else:
        print("režim:", MODES.get(get_mode()))
