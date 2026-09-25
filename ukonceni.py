# ukonceni.py - zachyceni ukonceni aplikace ve Windows, aby se stihly nahrat zalozni
# krivky chlazeni do Krakenu.
#
#   - Ctrl+C                      -> KeyboardInterrupt v hlavni smycce (resi Python)
#   - Ctrl+Break, zavreni okna    -> handler konzole (SetConsoleCtrlHandler)
#   - odhlaseni, vypnuti PC       -> skryte okno (WM_ENDSESSION); proces s nactenou
#                                    user32.dll (Python ji ma vzdy) udalosti odhlaseni
#                                    a vypnuti v handleru konzole nedostane
#   - ukoncit.bat                 -> skryte okno (WM_CLOSE) - bez konzole (autostart)
#                                    jinak aplikaci nejde bezpecne ukoncit
#
# Spusteni "py ukonceni.py --ukoncit" ukonci bezici aplikaci a pocka na zalohu.
#
# Handler i okno bezi ve vlastnim vlakne: nastavi STOP a pockaji na DONE (az hlavni
# smycka nahraje zalohu). Windows proces ukonci zhruba 5 s po udalosti.

import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger("rgb_lcd")

STOP = threading.Event()     # pozadavek na ukonceni
DONE = threading.Event()     # zaloha chlazeni je hotova, proces muze skoncit
WAIT_S = 4.5

_CTRL_EVENTS = {1: "Ctrl+Break", 2: "zavreni okna", 5: "odhlaseni", 6: "vypnuti systemu"}
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
MSGFLT_ALLOW = 1
ERROR_ALREADY_EXISTS = 183
WINDOW_CLASS = "RGB_LCD_ukonceni"
MUTEX_NAME = "Local\\RGB_LCD_dashboard"

_keep = []                   # ctypes callbacky a handle musi zustat v pameti


def single_instance():
    """True, kdyz je tohle jedina bezici instance (drzi pojmenovany mutex do konce procesu)."""
    if not hasattr(ctypes, "WinDLL"):
        return True
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    h = k.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()
    if not h:
        return err != 5          # pristup odepren = mutex drzi instance s pravy spravce
    _keep.append(h)
    return err != ERROR_ALREADY_EXISTS


def request_stop(reason):
    """Pozadat hlavni smycku o ukonceni a pockat, nez preda chlazeni Krakenu."""
    if not STOP.is_set():
        log.info("Ukoncuji (%s).", reason)
    STOP.set()
    DONE.wait(WAIT_S)


def _install_console_handler():
    routine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handler(event):
        name = _CTRL_EVENTS.get(event)
        if name is None:          # Ctrl+C -> Python (KeyboardInterrupt)
            return False
        request_stop(name)
        return True
    cb = routine(handler)
    _keep.append(cb)
    if not ctypes.windll.kernel32.SetConsoleCtrlHandler(cb, True):
        log.warning("Nepodarilo se zachytit zavreni okna - ukoncuj aplikaci pres Ctrl+C.")


def _window_thread(ready):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = wintypes.LPARAM
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                 wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                      wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def proc(hwnd, msg, wparam, lparam):
        if msg == WM_CLOSE:
            request_stop("pozadavek na ukonceni")
            return 0
        if msg == WM_QUERYENDSESSION:
            return 1                                  # vypnuti neblokujeme
        if msg == WM_ENDSESSION:
            if wparam:
                request_stop("odhlaseni nebo vypnuti systemu")
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wndproc = WNDPROC(proc)
    _keep.append(wndproc)
    wc = WNDCLASSW()
    wc.lpfnWndProc = wndproc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = WINDOW_CLASS
    hwnd = None
    if user32.RegisterClassW(ctypes.byref(wc)):
        # skryte okno nejvyssi urovne (ne message-only - to broadcast o vypnuti nedostane)
        hwnd = user32.CreateWindowExW(0, WINDOW_CLASS, "RGB-LCD", 0, 0, 0, 0, 0,
                                      None, None, wc.hInstance, None)
    if hwnd:
        # aplikace bezi s pravy spravce -> WM_CLOSE z beznych procesu (ukoncit.bat) by
        # Windows jinak zahodil (UIPI)
        user32.ChangeWindowMessageFilterEx.argtypes = [wintypes.HWND, wintypes.UINT,
                                                       wintypes.DWORD, wintypes.LPVOID]
        user32.ChangeWindowMessageFilterEx(hwnd, WM_CLOSE, MSGFLT_ALLOW, None)
    ready.set()
    if not hwnd:
        log.warning("Nepodarilo se vytvorit okno pro zachyceni vypnuti PC (chyba %d).",
                    ctypes.get_last_error())
        return
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def install():
    """Zapnout zachyceni ukonceni. Mimo Windows nic nedela."""
    if not hasattr(ctypes, "windll"):
        return
    _install_console_handler()
    ready = threading.Event()
    threading.Thread(target=_window_thread, args=(ready,), name="ukonceni", daemon=True).start()
    ready.wait(2)


def close_running(timeout=15):
    """Pozadat bezici aplikaci o ukonceni (WM_CLOSE) a pockat, az jeji proces skonci.
    Vrati None = nebezi, True = ukoncena, False = neodpovida."""
    import time
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                    wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proc = kernel32.OpenProcess(0x00100000, False, pid.value)    # SYNCHRONIZE
    try:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            hwnd = user32.FindWindowW(WINDOW_CLASS, None)
            if not hwnd and not proc:
                return True
            if hwnd:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)   # opakovane - kdyby se prvni ztratila
            if proc:
                if kernel32.WaitForSingleObject(proc, 2000) == 0:       # proces skoncil
                    return True
            else:
                time.sleep(2)
        return False
    finally:
        if proc:
            kernel32.CloseHandle(proc)


def pause(seconds):
    """Cekani, ktere hned skonci pri STOP. Po kratkych usecich, aby Ctrl+C reagovalo
    okamzite (Event.wait jde v Pythonu 3.12 na Windows prerusit az po uplynuti)."""
    import time
    end = time.monotonic() + seconds
    while not STOP.is_set():
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(0.1, left))


if __name__ == "__main__":
    import sys
    if "--ukoncit" in sys.argv:
        r = close_running()
        print({None: "Aplikace nebezi.",
               True: "Aplikace ukoncena. Predani chlazeni Krakenu potvrzuje radek ZALOHA v rgb_lcd.log.",
               False: "Aplikace neodpovida - podivej se do rgb_lcd.log."}[r])
        sys.exit(0 if r is not False else 1)
