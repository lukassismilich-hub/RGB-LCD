# klavesy_stisk.py - ktera klavesa byla stisknuta (pro reakci podsviceni klavesnice G815 na psani)
#
# Hook Windows WH_KEYBOARD_LL ve vlastnim vlakne (se smyckou zprav). Uklada jen cislo LED klavesy
# (zona klavesnice_rozlozeni) do kratke fronty - zadny text, poradi ani cas se nikam nezapisuje
# a fronta drzi nejvys MAX_QUEUE stisku, ktere si vlakno LED hned vybere (drain).
# Zona = kod HID - 3 (modifikatory 0xE0-0xE7 -> 104-111); scan kod (sada 1) se na HID prevadi
# tabulkou. Klavesa vedle Enteru (scan 0x2B) je na ISO klavesnici zona 47 (#).
# Spousti se jen kdyz efekt klavesnice ma reakci na stisk (led.py) - jinak hook nebezi.

import collections
import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger("rgb_lcd")

MAX_QUEUE = 64
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10

# scan kod (sada 1) -> HID usage
_SCAN = {0x01: 0x29, 0x0C: 0x2D, 0x0D: 0x2E, 0x0E: 0x2A, 0x0F: 0x2B, 0x10: 0x14, 0x11: 0x1A, 0x12: 0x08,
         0x13: 0x15, 0x14: 0x17, 0x15: 0x1C, 0x16: 0x18, 0x17: 0x0C, 0x18: 0x12, 0x19: 0x13, 0x1A: 0x2F,
         0x1B: 0x30, 0x1C: 0x28, 0x1D: 0xE0, 0x1E: 0x04, 0x1F: 0x16, 0x20: 0x07, 0x21: 0x09, 0x22: 0x0A,
         0x23: 0x0B, 0x24: 0x0D, 0x25: 0x0E, 0x26: 0x0F, 0x27: 0x33, 0x28: 0x34, 0x29: 0x35, 0x2A: 0xE1,
         0x2B: 0x32, 0x2C: 0x1D, 0x2D: 0x1B, 0x2E: 0x06, 0x2F: 0x19, 0x30: 0x05, 0x31: 0x11, 0x32: 0x10,
         0x33: 0x36, 0x34: 0x37, 0x35: 0x38, 0x36: 0xE5, 0x37: 0x55, 0x38: 0xE2, 0x39: 0x2C, 0x3A: 0x39,
         0x46: 0x47, 0x47: 0x5F, 0x48: 0x60, 0x49: 0x61, 0x4A: 0x56, 0x4B: 0x5C, 0x4C: 0x5D, 0x4D: 0x5E,
         0x4E: 0x57, 0x4F: 0x59, 0x50: 0x5A, 0x51: 0x5B, 0x52: 0x62, 0x53: 0x63, 0x56: 0x64, 0x57: 0x44,
         0x58: 0x45}
_SCAN.update({0x02 + i: 0x1E + i for i in range(10)})          # 1 ... 0
_SCAN.update({0x3B + i: 0x3A + i for i in range(10)})          # F1 ... F10
# rozsirene (E0)
_SCAN_E0 = {0x1C: 0x58, 0x1D: 0xE4, 0x35: 0x54, 0x37: 0x46, 0x38: 0xE6, 0x47: 0x4A, 0x48: 0x52, 0x49: 0x4B,
            0x4B: 0x50, 0x4D: 0x4F, 0x4F: 0x4D, 0x50: 0x51, 0x51: 0x4E, 0x52: 0x49, 0x53: 0x4C, 0x5B: 0xE3,
            0x5C: 0xE7, 0x5D: 0x65}
# podle virtualniho kodu (scan kod je u nich nejednoznacny): NumLock, Pause, multimedia -> primo zona
_VK_HID = {0x90: 0x53, 0x13: 0x48}
_VK_ZONE = {0xB3: 155, 0xAD: 156, 0xB0: 157, 0xB1: 158}


def zone_of(vk, scan, flags):
    """Zona LED klavesy, nebo None."""
    if vk in _VK_ZONE:
        return _VK_ZONE[vk]
    if scan & 0x200:                                    # falesny LCtrl od AltGr
        return None
    usage = _VK_HID.get(vk) or (_SCAN_E0 if flags & LLKHF_EXTENDED else _SCAN).get(scan & 0xFF)
    if usage is None:
        return None
    if usage >= 0xE0:
        return usage - 0xE0 + 104
    return usage - 3


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class Watcher(threading.Thread):
    """Vlakno s hookem klavesnice. drain() vrati nove stisknute zony (kazdy stisk jednou)."""

    def __init__(self):
        super().__init__(name="klavesy_stisk", daemon=True)
        self._q = collections.deque(maxlen=MAX_QUEUE)
        self._down = set()
        self._tid = None
        self._ready = threading.Event()
        self.error = None
        self._proc = HOOKPROC(self._hook)               # odkaz drzet, jinak ho GC uvolni

    def _hook(self, code, wparam, lparam):
        try:
            if code == 0:
                k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not k.flags & LLKHF_INJECTED:
                    z = zone_of(k.vkCode, k.scanCode, k.flags)
                    if z is not None:
                        if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            if z not in self._down:      # drzena klavesa (autorepeat) jen jednou
                                self._down.add(z)
                                self._q.append(z)
                        elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                            self._down.discard(z)
        except Exception:
            pass
        return _user32.CallNextHookEx(None, code, wparam, lparam)

    def run(self):
        self._tid = _kernel32.GetCurrentThreadId()
        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.error = f"hook klávesnice nejde nastavit (chyba {ctypes.get_last_error()})"
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            _user32.UnhookWindowsHookEx(hook)

    def drain(self):
        out = []
        while self._q:
            out.append(self._q.popleft())
        return out

    def stop(self):
        if self._tid:
            _user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self.join(1.0)


_watcher = None


def start():
    """Spustit hook (jednou); vrati Watcher, nebo vyjimku."""
    global _watcher
    if _watcher is not None and _watcher.is_alive():
        return _watcher
    w = Watcher()
    w.start()
    w._ready.wait(2.0)
    if w.error:
        raise RuntimeError(w.error)
    _watcher = w
    log.info("Klávesnice: sleduji stisky kláves (reakce podsvícení).")
    return w


def stop():
    global _watcher
    if _watcher is not None:
        _watcher.stop()
        _watcher = None
        log.info("Klávesnice: sledování stisků vypnuto.")


if __name__ == "__main__":
    import time
    import klavesnice_rozlozeni as R
    names = {k[0]: k[1] for k in R.KEYS}
    w = start()
    print("Mačkej klávesy (10 s)…")
    end = time.time() + 10
    while time.time() < end:
        for z in w.drain():
            print(z, names.get(z, "?"))
        time.sleep(0.05)
    stop()
