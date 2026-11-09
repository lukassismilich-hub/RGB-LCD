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
#   - klavesy G1-G5 (HID++ 0x8010 GKey): se softwarovym ovladanim (enableSoftwareControl) klavesnice
#     misto vlastni funkce G-klavesy posle oznameni (bitova maska stisknutych, G1 = bit 0); overeno
#     9. 11. 2026. Oznameni dostane kazdy, kdo ma rozhrani otevrene - i G HUB, ktery pak provede svou
#     funkci G-klavesy (v G HUB je nutne G1-G5 nechat bez prirazeni). Direct ovladani zapne, jen kdyz
#     ma nektera G-klavesa akci (klavesy_g.py), a pri konci ho vypne.
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
FEATURE_GKEY = 0x8010
ERR_BUSY = 8                                 # chyba HID++ 2.0: zarizeni je zaneprazdnene
BUSY_TRIES = 20                              # kolikrat pri zaneprazdneni pockat a poslat znovu (celkem ~1 s)
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


class NotFound(HidppError):
    """Klavesnice neni pripojena (hledani stoji ~0,3 ms - jde zkouset casto)."""


class GhubBusy(HidppError):
    """Podsviceni ridi G HUB sam (ma u klavesnice vypnutou pamet)."""


def present():
    """Je klavesnice pripojena? (hledani ~0,3 ms bez klavesnice, ~5 ms s ni)"""
    try:
        import hid
        return any(d["usage_page"] == 0xFF43 and d["usage"] == 0x602 for d in hid.enumerate(VID, PID))
    except Exception:
        return True


def retry_after(e):
    """(za kolik sekund zkusit klavesnici znovu, popis chyby cesky) po chybe e: nenalezena / odpojena
    2 s (nic se neprepina - po pripojeni naskoci hned), G HUB ridi podsviceni 30 s (kazdy pokus pul
    sekundy posloucha), jinak 10 s (at klavesnice neblika mezi pameti a aplikaci).
    Odpojeni za behu hidapi hlasi jako "read error" / "write error" - proto se overi, ze klavesnice je."""
    if isinstance(e, GhubBusy):
        return 30, str(e)
    if isinstance(e, NotFound):
        return 2, str(e)
    if not present():
        return 2, f"{NAME} odpojena"
    text = {"read error": "chyba čtení z klávesnice", "write error": "chyba zápisu do klávesnice"}.get(str(e), str(e))
    return 10, text


class G815:
    """Spojeni HID++ s klavesnici (jen to, co aplikace potrebuje)."""

    def __init__(self, swid=SWID_UI):
        import hid
        path = next((d["path"] for d in hid.enumerate(VID, PID)
                     if d["usage_page"] == 0xFF43 and d["usage"] == 0x602), None)
        if path is None:
            raise NotFound(f"{NAME} nenalezena")
        self.h = hid.device()
        self.h.open_path(path)
        self.h.set_nonblocking(True)
        self._features = {}
        self.swid = swid
        self.foreign_t = None                      # kdy naposled poslal podsviceni nekdo jiny (G HUB)
        self.gkeys = 0                             # stisknute G-klavesy (bitova maska z oznameni 0x8010)
        self.on_gkey = None                        # funkce(cislo G-klavesy 1-5) pri stisku

    def close(self):
        try:
            self.h.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def request(self, idx, func, params=(), timeout=0.3, tries=3, busy_tries=BUSY_TRIES):
        """Poslat prikaz a pockat na odpoved se stejnou funkci a nasim swid (odpoved trva ~2,3 ms).
        Klavesnice nesnese vic prikazu najednou (odpovedi se ztraceji) - vzdy jen jeden a cekat.
        Obcas odpoved neprijde (videno pri animaci) - prikaz se posle znovu (nastaveni barev
        a rezimu jde poslat dvakrat bez skody). Chyba HID++ 8 = klavesnice je zaneprazdnena
        (videno hned po vypnuti pameti a pri stridani efektu, 9. 11. 2026) - chvili pockat a poslat znovu."""
        fs = (func << 4) | self.swid
        msg = [0x11, 0xFF, idx, fs] + list(params) + [0] * (16 - len(params))
        busy = 0
        with _lock:
            attempt = 0
            while attempt < tries:
                attempt += 1
                while True:                        # zahodit stare zpravy (i od G HUB)
                    r = self.h.read(64)
                    if not r:
                        break
                    self._note(r)
                self.h.write(msg)
                end = time.monotonic() + timeout
                while True:
                    left = end - time.monotonic()
                    if left <= 0:
                        break
                    r = self.h.read(64, max(1, int(left * 1000)))     # ceka nejvys do konce timeoutu
                    if not r:
                        continue
                    self._note(r)
                    if r[0] == 0x11:
                        if r[2] == idx and r[3] == fs:
                            return r[4:20]
                        if r[2] == 0xFF and r[3] == idx and r[4] == fs:
                            if r[5] == ERR_BUSY and busy < busy_tries:
                                busy += 1
                                attempt -= 1               # zaneprazdneni se nepocita mezi pokusy
                                time.sleep(0.005 * busy)
                                break
                            raise HidppError(f"klávesnice odmítla příkaz (chyba HID++ {r[5]}"
                                             f"{' – zaneprázdněná' if r[5] == ERR_BUSY else ''})")
        raise HidppError("klávesnice neodpovídá")

    def _note(self, r):
        """Zprava, ktera neni odpovedi na nas prikaz: stisk G-klavesy (oznameni 0x8010), nebo odpoved
        na cizi prikaz podsviceni po klavesach (G HUB) - zapamatovat cas."""
        if not r or r[0] not in (0x10, 0x11):
            return
        if (r[3] & 0x0F) == 0 and r[2] == self._features.get(FEATURE_GKEY) and r[2]:
            mask = r[4] | (r[5] << 8)
            new = mask & ~self.gkeys
            self.gkeys = mask
            for bit in range(16):
                if new >> bit & 1 and self.on_gkey is not None:
                    self.on_gkey(bit + 1)
        elif (r[0] == 0x11 and (r[3] & 0x0F) not in (0, self.swid, SWID, SWID_UI)
                and r[2] == self._features.get(FEATURE_PERKEY)):
            self.foreign_t = time.monotonic()

    def poll(self):
        """Precist zpravy, ktere prisly mimo odpovedi (stisky G-klaves) - nic neceka."""
        with _lock:
            while True:
                r = self.h.read(64)
                if not r:
                    break
                self._note(r)

    def gkey_control(self, on):
        """Softwarove ovladani G-klaves: True = stisky hlasit aplikaci, False = vlastni funkce klaves."""
        self.request(self.feature(FEATURE_GKEY), 2, [1 if on else 0])

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


def encode(cols, last=None):
    """Prikazy 0x8081 pro barvy klaves {zona: (r, g, b)} - jen zmenene proti last, co nejmene prikazu
    (kazdy stoji ~2,3 ms, vic najednou klavesnice nesnese). Kazda skupina klaves stejne barvy jde
    nejlevneji z: useky zon (funkce 5, 3 useky v prikazu), vycet zon (6, az 13 zon), nebo jednotlive
    (1, 4 klavesy v prikazu - spolecne pro vsechny zbyle). Vrati [(funkce, parametry)] bez frameEnd."""
    groups = {}
    for z, c in cols.items():
        if last is None or last.get(z) != c:
            groups.setdefault(c, []).append(z)
    out, single = [], []
    for c, zs in groups.items():
        zs.sort()
        rg = _ranges(zs)
        by_range, by_list, by_one = -(-len(rg) // 3), -(-len(zs) // 13), len(zs) / 4
        if min(by_range, by_list) >= by_one:
            single += [(z, c) for z in zs]
        elif by_range <= by_list:
            for i in range(0, len(rg), 3):
                out.append((5, [v for a, b in rg[i:i + 3] for v in (a, b) + c]))
        else:
            for i in range(0, len(zs), 13):
                out.append((6, list(c) + zs[i:i + 13]))
    for i in range(0, len(single), 4):
        out.append((1, [v for z, c in single[i:i + 4] for v in (z,) + c]))
    return out


class Direct:
    """Barvy klavesnice primo pres HID++ (0x8081) - bez G HUB a bez jeho SDK.
    start() vypne integrovanou pamet (rezim rizeni z pocitace), stop() ji zase zapne - klavesnice
    pak sviti podle profilu v pameti. Posila vlastni vlakno (snimek po klavesach ~60 ms, vlakno LED
    na nej neceka): color() / keys() jen predaji posledni snimek, starsi neodeslany se zahodi.
    Chyba vlakna se ohlasi pri dalsim color() / keys(). Rezim se overuje kazdych CHECK_S s:
    po odpojeni, probuzeni PC nebo restartu G HUB se klavesnice vrati do pameti a vlakno ji prepne znovu."""

    def __init__(self):
        self.k = None
        self.ok = False
        self.last = None                           # posledni poslane barvy {zona: (r, g, b)}
        self.zones = []
        self.checked = 0.0
        self.ghub = False                          # G HUB ridi podsviceni sam - pak rezim nemenit
        self.error = None
        self._cv = threading.Condition()
        self._pending = None                       # (barvy, force) cekajici na odeslani
        self._quit = False
        self._thread = None
        self.want_g = False                        # ma nektera G-klavesa akci (ovladani G-klaves z aplikace)
        self._g_on = False                         # je softwarove ovladani G-klaves zapnute
        self._g_lock = threading.Lock()
        self._g = []                               # stisknute G-klavesy k vyzvednuti (g_drain)
        self.on_gkey = None                        # funkce bez parametru pri stisku G-klavesy (probudit vlakno LED)

    def start(self):
        if self.ok:
            return True
        k = G815(SWID)
        try:
            k.feature(FEATURE_PERKEY)
            self.zones = k.zones()
            self.ghub = k.onboard_mode() == MODE_HOST and k.sniff(0.5)
            if self.ghub:                          # G HUB ma pamet vypnutou a posila sve barvy
                raise GhubBusy(GHUB_BUSY)
            self.k = k
            k.on_gkey = self._gkey
            self._host()
        except Exception:
            k.close()
            self.k = None
            raise
        self.ok, self.last, self.error, self._pending, self._quit = True, None, None, None, False
        self._g_on, self._g = False, []
        self._thread = threading.Thread(target=self._loop, name="klavesnice_led", daemon=True)
        self._thread.start()
        return True

    def _host(self):
        """Vypnout integrovanou pamet, kdyby se mezitim zapnula."""
        if self.k.onboard_mode() != MODE_HOST:
            self.k.set_onboard_mode(MODE_HOST)
            self.last = None                       # po prepnuti poslat barvy znovu
            log.info("%s: integrovaná paměť vypnuta – podsvícení řídí aplikace.", NAME)
        self.checked = time.monotonic()

    def _gkey(self, n):
        with self._g_lock:
            self._g.append(n)
        if self.on_gkey is not None:
            self.on_gkey()

    def g_drain(self):
        """Stisknute G-klavesy (1-5) od posledniho volani."""
        with self._g_lock:
            out, self._g = self._g, []
        return out

    def _gkeys(self, force=False):
        """Softwarove ovladani G-klaves podle want_g (force = poslat znovu - po odpojeni / uspani
        se klavesnice vrati k vlastnim funkcim G-klaves a zjistit to nejde)."""
        want = bool(self.want_g)
        if want != self._g_on or (want and force):
            self.k.gkey_control(want)
            if want != self._g_on:
                log.info("%s: klávesy G1–G5 %s.", NAME, "ovládá aplikace" if want else "vráceny klávesnici")
            self._g_on = want

    def color(self, rgb, force=False):
        """Cela klavesnice jednou barvou."""
        c = tuple(int(max(0, min(255, v))) for v in rgb)
        self.keys({z: c for z in self.zones}, force)

    def keys(self, cols, force=False):
        """Barvy klaves {zona: (r, g, b)} k odeslani (zmenene; force = vse). Zony, ktere v cols
        nejsou, zustanou, jak byly. Neceka na odeslani."""
        if self.error is not None:
            raise self.error
        if not self.ok:
            return
        cols = {z: tuple(int(max(0, min(255, v))) for v in c) for z, c in cols.items()}
        with self._cv:
            if self._pending is not None:
                force = force or self._pending[1]
            self._pending = (cols, force)
            self._cv.notify()

    def _loop(self):
        try:
            while True:
                with self._cv:
                    if self._pending is None and not self._quit:
                        self._cv.wait(0.05 if self._g_on else 1.0)     # stisky G-klaves cist i bez snimku
                    if self._quit:
                        return
                    item, self._pending = self._pending, None
                if time.monotonic() - self.checked > CHECK_S:
                    if self.k.foreign():
                        self.ghub = True
                        raise GhubBusy(GHUB_BUSY)
                    self._host()
                    self._gkeys(force=True)
                else:
                    self._gkeys()
                if self._g_on:
                    self.k.poll()
                if item is not None:
                    self._send(*item)
        except Exception as e:
            self.error = e

    def _send(self, cols, force):
        cmds = encode(cols, None if force else self.last)
        if not cmds:
            return
        idx = self.k.feature(FEATURE_PERKEY)
        for func, params in cmds:
            self.k.request(idx, func, params)
        self.k.request(idx, 7, [0, 0, 0, 0])               # frameEnd = zobrazit
        if force or self.last is None:
            self.last = dict(cols)
        else:
            self.last.update(cols)

    def stop(self):
        """Zapnout zpet integrovanou pamet (klavesnice sviti podle sveho profilu) a zavrit spojeni.
        Kdyz podsviceni ridi G HUB sam, rezim se nemeni."""
        if self._thread is not None:
            with self._cv:
                self._quit = True
                self._cv.notify()
            self._thread.join(2.0)
            self._thread = None
        if self.k is not None:
            if self._g_on:
                try:
                    self.k.gkey_control(False)           # G-klavesy zase s vlastni funkci
                    log.info("%s: klávesy G1–G5 vráceny klávesnici.", NAME)
                except Exception:
                    pass
                self._g_on = False
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
