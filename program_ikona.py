# program_ikona.py - ikona spusteneho programu / hry na LCD Krakenu
#
# Vlakno Watcher kazdych 0,25 s zjisti okno v popredi. Kdyz patri programu, ktery se prave spustil
# (nebo pri kazdem prepnuti okna - podle nastaveni), vytahne z jeho .exe ikonu v nejvetsi velikosti
# (prostredky RT_GROUP_ICON / RT_ICON, typicky 256x256 PNG) a nazev (FileDescription). Hlavni smycka
# pak misto rotace obrazovek na "doba_s" sekund ukaze ikonu (render). Chyba tady nesmi zdrzet
# chlazeni - vsechno je v try/except a hlavni smycka pri chybe vykresli bezne obrazovky.
#
# config["ikona_programu"]: zapnuto, kdy ("spusteni" / "prepnuti"), jen_cela_obrazovka, doba_s,
# nazev (zobrazit nazev pod ikonou), zare (zare v barve ikony za ikonou), vynechat (seznam nazvu .exe).

import ctypes
import ctypes.wintypes as wt
import io
import json
import logging
import os
import struct
import threading
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger("rgb_lcd")

BASE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(BASE, "fonts")
# test z okna nastaveni ("Vyzkouset..."): {"exe": cesta, "doba_s", "nazev", "zare"} - aplikace ho
# do 0,25 s ukaze na LCD a soubor smaze
TEST_FILE = os.path.join(BASE, "ikona_test.json")

DEFAULTS = {"zapnuto": True, "kdy": "spusteni", "jen_cela_obrazovka": False, "doba_s": 8, "nazev": True,
            "zare": True, "vynechat": []}

# soucasti Windows a tahle aplikace - nikdy neukazovat
SYSTEM = {"explorer.exe", "python.exe", "pythonw.exe", "py.exe", "pyw.exe", "applicationframehost.exe",
          "searchhost.exe", "searchapp.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
          "shellhost.exe", "lockapp.exe", "textinputhost.exe", "consent.exe", "credentialuihost.exe",
          "logonui.exe", "dwm.exe", "sihost.exe", "ctfmon.exe", "rundll32.exe", "dllhost.exe",
          "openwith.exe", "pickerhost.exe", "widgets.exe", "systemsettingsadminflows.exe"}
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                 "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow", "ForegroundStaging",
                 "MultitaskingViewFrame", "TaskSwitcherWnd"}
POLL_S = 0.25
MAX_AGE_S = 300          # "pri spusteni": program spusteny nejvys pred 5 min (hry se nacitaji dlouho)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
version = ctypes.WinDLL("version", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
LOAD_LIBRARY_AS_DATAFILE = 0x02
LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x20
RT_ICON = 3
RT_GROUP_ICON = 14

user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = wt.HMONITOR
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
kernel32.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(wt.FILETIME)]
kernel32.LoadLibraryExW.restype = wt.HMODULE
kernel32.LoadLibraryExW.argtypes = [wt.LPCWSTR, wt.HANDLE, wt.DWORD]
kernel32.FreeLibrary.argtypes = [wt.HMODULE]
kernel32.FindResourceW.restype = ctypes.c_void_p
kernel32.FindResourceW.argtypes = [wt.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
kernel32.LoadResource.restype = ctypes.c_void_p
kernel32.LoadResource.argtypes = [wt.HMODULE, ctypes.c_void_p]
kernel32.LockResource.restype = ctypes.c_void_p
kernel32.LockResource.argtypes = [ctypes.c_void_p]
kernel32.SizeofResource.restype = wt.DWORD
kernel32.SizeofResource.argtypes = [wt.HMODULE, ctypes.c_void_p]
ENUMRESNAMEPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
kernel32.EnumResourceNamesW.argtypes = [wt.HMODULE, ctypes.c_void_p, ENUMRESNAMEPROC, ctypes.c_void_p]
version.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.DWORD)]
version.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
version.VerQueryValueW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.POINTER(wt.UINT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]


def settings(cfg):
    out = dict(DEFAULTS)
    out.update(cfg or {})
    return out


# ------------------------------------------------------------ procesy a okna

def _ft(ft):
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def now_filetime():
    ft = wt.FILETIME()
    kernel32.GetSystemTimeAsFileTime(ctypes.byref(ft))
    return _ft(ft)


def process_info(pid):
    """(cesta k .exe, cas spusteni FILETIME) nebo (None, None)."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None, None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(len(buf))
        path = buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
        times = [wt.FILETIME() for _ in range(4)]
        created = _ft(times[0]) if kernel32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]) else None
        return path, created
    finally:
        kernel32.CloseHandle(h)


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def is_fullscreen(hwnd):
    """Okno pokryva cely monitor (hra pres celou obrazovku nebo okno bez okraju)."""
    r = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


# ------------------------------------------------------------ ikona a nazev z .exe

def _resource(h, name, typ):
    res = kernel32.FindResourceW(h, name, typ)
    if not res:
        return None
    size = kernel32.SizeofResource(h, res)
    ptr = kernel32.LockResource(kernel32.LoadResource(h, res))
    return ctypes.string_at(ptr, size) if ptr and size else None


def exe_icon(path):
    """Nejvetsi ikona z prostredku .exe jako RGBA obrazek (None, kdyz ikonu nema)."""
    h = kernel32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE)
    if not h:
        return None
    keep = []
    try:
        names = []

        def cb(_mod, _typ, name, _param):
            # ciselne ID (< 0x10000), jinak text - ukazatel plati jen v callbacku, zkopirovat
            names.append(name if name < 0x10000 else ctypes.wstring_at(name))
            return False                                  # staci prvni skupina = hlavni ikona
        kernel32.EnumResourceNamesW(h, RT_GROUP_ICON, ENUMRESNAMEPROC(cb), None)
        if not names:
            return None
        name = names[0]
        if isinstance(name, str):
            buf = ctypes.create_unicode_buffer(name)
            keep.append(buf)
            name = ctypes.addressof(buf)
        grp = _resource(h, name, RT_GROUP_ICON)
        if not grp or len(grp) < 6:
            return None
        count = struct.unpack_from("<HHH", grp)[2]
        entries = []
        for i in range(count):
            if 6 + i * 14 + 14 > len(grp):
                break
            w, hh, colors, _r, planes, bpp, size, rid = struct.unpack_from("<BBBBHHIH", grp, 6 + i * 14)
            entries.append((w or 256, bpp, hh, colors, planes, rid))
        if not entries:
            return None
        w, bpp, hh, colors, planes, rid = max(entries, key=lambda e: (e[0], e[1]))
        data = _resource(h, rid, RT_ICON)
    finally:
        kernel32.FreeLibrary(h)
    if not data:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        img = Image.open(io.BytesIO(data))
    else:                                                 # DIB bez hlavicky souboru -> jednoikonovy .ico
        ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w % 256, hh, colors, 0, planes, bpp,
                                                          len(data), 22) + data
        img = Image.open(io.BytesIO(ico))
    img.load()
    return img.convert("RGBA")


def exe_name(path):
    """Nazev programu z informaci o verzi (FileDescription / ProductName), jinak nazev souboru."""
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return stem
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buf):
            return stem
        p, n = ctypes.c_void_p(), wt.UINT()
        langs = []
        if version.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(p), ctypes.byref(n)) \
                and n.value >= 4:
            for i in range(n.value // 4):
                lang, cp = struct.unpack_from("<HH", ctypes.string_at(p.value, n.value), i * 4)
                langs.append(f"{lang:04x}{cp:04x}")
        langs += ["040904b0", "040904e4", "000004b0"]
        for key in ("FileDescription", "ProductName"):
            for lc in langs:
                if version.VerQueryValueW(buf, f"\\StringFileInfo\\{lc}\\{key}", ctypes.byref(p),
                                          ctypes.byref(n)) and n.value > 1:
                    s = ctypes.wstring_at(p.value, n.value).split("\0")[0].strip()
                    if s:
                        return s
    except OSError:
        pass
    return stem


# ------------------------------------------------------------ vykresleni na LCD

def _accent(icon):
    """Vyrazna barva ikony (prumer sytych neprusvitnych pixelu) pro zare za ikonou."""
    small = icon.resize((32, 32), Image.BILINEAR)
    tot, acc = 0.0, [0.0, 0.0, 0.0]
    for r, g, b, a in small.getdata():
        if a < 128:
            continue
        mx, mn = max(r, g, b), min(r, g, b)
        wgt = (mx - mn) / 255.0 * (mx / 255.0) + 0.02
        tot += wgt
        acc[0] += r * wgt
        acc[1] += g * wgt
        acc[2] += b * wgt
    if not tot:
        return (90, 90, 90), 0.0
    c = [v / tot for v in acc]
    k = 255.0 / max(1.0, max(c))                          # plna svetlost, jas resi zare
    c = tuple(int(v * k) for v in c)
    return c, (max(c) - min(c)) / 255.0


def is_dark(icon):
    """Tmavy tvar na pruhlednem pozadi (napr. Diablo IV: cerne "D" s tmave hnedym okrajem, kreslene
    pro svetle pozadi) - na cernem LCD by splynul. Ikony s vlastni nepruhlednou dlazdici (ctverec,
    kruh) ne: ty maji pokryti vic nez 80 % a obsah na dlazdici je videt."""
    small = icon.resize((64, 64), Image.LANCZOS)
    lum = small.convert("RGB").convert("L").getdata()
    opaque = [v for v, a in zip(lum, small.getchannel("A").getdata()) if a > 128]
    if not opaque:
        return False
    bright = sum(1 for v in opaque if v > 80) / len(opaque)           # podil viditelnych pixelu
    return bright < 0.15 and len(opaque) / (64 * 64) < 0.8


def _font(px, weight="SemiBold"):
    try:
        return ImageFont.truetype(os.path.join(FONTS, f"Montserrat-{weight}.ttf"), px)
    except OSError:
        return ImageFont.load_default()


def _fit_text(d, text, max_w, sizes):
    for px in sizes:
        f = _font(px)
        if d.textlength(text, font=f) <= max_w:
            return text, f
    f = _font(sizes[-1])
    while len(text) > 1 and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…", f


def render(icon, name="", gamma=0.65, show_name=True, glow=True):
    """Obrazek 240x240 pro LCD: ikona uprostred, volitelne se zari v jeji barve, pod ni nazev.
    Tmava ikona (is_dark) dostane svetlou zaoblenou desticku."""
    S, size = 3, 240
    W = size * S
    img = Image.new("RGB", (W, W), (0, 0, 0))
    show_name = bool(show_name and name)
    cy = (104 if show_name else 120) * S
    box = (150 if show_name else 176) * S
    color, sat = _accent(icon)

    if glow:
        mask = Image.new("L", (W, W), 0)
        r = int(box * 0.62)
        ImageDraw.Draw(mask).ellipse((W // 2 - r, cy - r, W // 2 + r, cy + r), fill=int(50 + 70 * sat))
        mask = mask.filter(ImageFilter.GaussianBlur(28 * S))
        img = Image.composite(Image.new("RGB", (W, W), color), img, mask)   # sede ikony = slabsi zare

    bb = icon.getchannel("A").getbbox() or (0, 0, icon.width, icon.height)
    ic = icon.crop(bb)                                    # bez pruhledneho okraje
    if is_dark(ic):                                       # tmava ikona: svetla zaoblena desticka
        tint = tuple(int(232 + (c - 232) * 0.12) for c in color)
        r = box // 2
        ImageDraw.Draw(img).rounded_rectangle((W // 2 - r, cy - r, W // 2 + r, cy + r), radius=int(box * 0.22),
                                              fill=tint)
        box = int(box * 0.78)
    if max(ic.size) <= 64:                                # mala ikona: ostre pixely misto rozmazani
        k = max(1, box // max(ic.size))
        ic = ic.resize((ic.width * k, ic.height * k), Image.NEAREST)
    k = box / max(ic.size)
    ic = ic.resize((max(1, round(ic.width * k)), max(1, round(ic.height * k))), Image.LANCZOS)
    img.paste(ic, (W // 2 - ic.width // 2, cy - ic.height // 2), ic)

    if show_name:
        d = ImageDraw.Draw(img)
        text, f = _fit_text(d, name, 212 * S, [px * S for px in (22, 20, 18, 16, 14)])
        d.text((W // 2, 204 * S), text, font=f, fill=(235, 238, 242), anchor="mm")

    out = img.resize((size, size), Image.LANCZOS)
    if gamma and gamma != 1.0:
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        out = out.point(lut * 3)
    return out


def request_test(path, cfg=None):
    """Pozadat bezici aplikaci, aby na LCD ukazala ikonu daneho .exe (s nastavenim cfg)."""
    c = settings(cfg)
    req = {"exe": path, "doba_s": c.get("doba_s", 8), "nazev": c.get("nazev", True), "zare": c.get("zare", True)}
    tmp = TEST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False)
    os.replace(tmp, TEST_FILE)


def render_exe(path, cfg=None, gamma=0.65):
    """Nahled pro okno nastaveni: ikona a nazev daneho .exe (None, kdyz ikonu nema)."""
    icon = exe_icon(path)
    if icon is None:
        return None
    c = settings(cfg)
    return render(icon, exe_name(path), gamma, c.get("nazev", True), c.get("zare", True))


# ------------------------------------------------------------ vlakno

class Watcher(threading.Thread):
    """Hlida okno v popredi. active() vrati zobrazovany program (dict s "icon", "name", "exe")
    po dobu doba_s; wake se nastavi, aby hlavni smycka nemusela cekat na dalsi obnovu."""

    def __init__(self):
        super().__init__(name="ProgramIkona", daemon=True)
        self.cfg = dict(DEFAULTS)
        self.wake = threading.Event()
        self.stop_ev = threading.Event()
        self.current = None
        self.state = {}                                   # posledni zobrazeny program pro stav.json
        self.start_ft = now_filetime()
        self.done = set()                                 # (pid, cas spusteni) uz vyrizene
        self.last_key = None
        self._info = {}                                   # (okno, pid) -> ((pid, cas spusteni), cesta)
        self._icons = {}                                  # cesta -> (ikona, nazev)
        self._errors = set()

    def update(self, cfg):
        self.cfg = settings(cfg)
        if not self.cfg.get("zapnuto"):
            self.current = None

    def active(self):
        """Zobrazovany program. Doba "until" se pocita az od prvniho odeslani na LCD (nastavi ji
        hlavni smycka) - pri startu hry muze byt PC vytizene a smycka se zdrzet."""
        cur = self.current
        if cur is None:
            return None
        now = time.monotonic()
        if cur["until"] is None:
            return cur if now - cur["found"] < 30 else None
        return cur if now < cur["until"] else None

    def stop(self):
        self.stop_ev.set()

    def run(self):
        try:                                              # souradnice oken bez virtualizace DPI
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        while not self.stop_ev.is_set():
            try:
                self._poll()
            except Exception as e:                        # nesmi shodit vlakno ani aplikaci
                if str(e) not in self._errors:
                    self._errors.add(str(e))
                    log.warning("Ikona programu: %s", e)
            self.stop_ev.wait(POLL_S)

    def _poll_test(self):
        """Test z okna nastaveni (TEST_FILE) - funguje i pri vypnute funkci."""
        if not os.path.exists(TEST_FILE):
            return
        try:
            with open(TEST_FILE, encoding="utf-8") as f:
                req = json.load(f)
        finally:
            try:
                os.remove(TEST_FILE)
            except OSError:
                pass
        path = str(req.get("exe", ""))
        icon = exe_icon(path) if os.path.isfile(path) else None
        if icon is None:
            log.info("Ikona programu - test: %s nema ikonu.", path)
            return
        try:
            secs = max(1.0, min(120.0, float(req.get("doba_s", 8))))
        except (TypeError, ValueError):
            secs = 8.0
        self.current = {"icon": icon, "name": exe_name(path), "exe": os.path.basename(path), "path": path,
                        "secs": secs, "found": time.monotonic(), "until": None, "img": None,
                        "nazev": bool(req.get("nazev", True)), "zare": bool(req.get("zare", True))}
        self.wake.set()
        log.info("Ikona programu - test: %s", path)

    def _poll(self):
        self._poll_test()
        c = self.cfg
        if not c.get("zapnuto"):
            return
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return
        if window_class(hwnd) in SHELL_CLASSES:
            return
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid = pid.value
        if not pid or pid == os.getpid():
            return
        launch = c.get("kdy", "spusteni") != "prepnuti"
        info = self._info.get((hwnd, pid))                # cache: neotvirat proces kazdych 0,25 s
        if info is None:
            path, created = process_info(pid)
            if len(self._info) > 200:
                self._info.clear()
            info = self._info[(hwnd, pid)] = ((pid, created), path)
        key, path = info
        if len(self.done) > 5000:                         # stare procesy by stejne neprosly MAX_AGE_S
            self.done.clear()
        if (key in self.done) if launch else (key == self.last_key):
            return
        if launch and (key[1] is None or key[1] < self.start_ft
                       or (now_filetime() - key[1]) / 1e7 > MAX_AGE_S):
            self.done.add(key)                            # bezel uz pred startem aplikace / davno
            return
        if c.get("jen_cela_obrazovka") and not is_fullscreen(hwnd):
            return                                        # pocka, az se roztahne na celou obrazovku
        self.done.add(key)
        self.last_key = key
        if not path:
            return
        exe = os.path.basename(path).lower()
        skip = {str(x).strip().lower() for x in c.get("vynechat", []) if str(x).strip()}
        if exe in SYSTEM or exe in skip or os.path.splitext(exe)[0] in skip:
            return
        if path not in self._icons:
            if len(self._icons) > 32:
                self._icons.clear()
            icon = exe_icon(path)
            self._icons[path] = (icon, exe_name(path) if icon is not None else "")
            if icon is None:                              # do logu jen jednou, ne pri kazdem prepnuti
                log.info("Ikona programu: %s nema ikonu.", path)
        icon, name = self._icons[path]
        if icon is None:
            return
        try:
            secs = max(1.0, min(120.0, float(c.get("doba_s", 8))))
        except (TypeError, ValueError):
            secs = 8.0
        self.current = {"icon": icon, "name": name, "exe": os.path.basename(path), "path": path,
                        "secs": secs, "found": time.monotonic(), "until": None, "img": None}
        self.state = {"nazev": name, "exe": os.path.basename(path), "cas": time.time()}
        self.wake.set()
        log.info("Ikona programu: %s (%s)", name, path)
