# camservice.py - zastaveni sluzby NZXT CAMService pres Windows API (bez sc.exe).
# CAMService drzi rozhrani displeje Krakenu i pri zavrenem CAM, takze ji pred pripojenim
# musime zastavit. Zastaveni vyzaduje prava spravce (autostart bezi s nejvyssimi pravy).

import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger("rgb_lcd")

NAME = "CAMService"

SC_MANAGER_CONNECT = 0x0001
SERVICE_QUERY_STATUS = 0x0004
SERVICE_STOP = 0x0020
SERVICE_CONTROL_STOP = 1
ERROR_ACCESS_DENIED = 5
ERROR_SERVICE_DOES_NOT_EXIST = 1060
STATES = {1: "zastavena", 2: "spousti se", 3: "zastavuje se", 4: "bezi",
          5: "pokracuje", 6: "pozastavuje se", 7: "pozastavena"}


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [(n, wintypes.DWORD) for n in (
        "dwServiceType", "dwCurrentState", "dwControlsAccepted", "dwWin32ExitCode",
        "dwServiceSpecificExitCode", "dwCheckPoint", "dwWaitHint")]


def _api():
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    a.OpenSCManagerW.restype = wintypes.HANDLE
    a.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    a.OpenServiceW.restype = wintypes.HANDLE
    a.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
    a.ControlService.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SERVICE_STATUS)]
    a.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    return a


def _state(a, svc):
    st = SERVICE_STATUS()
    if not a.QueryServiceStatus(svc, ctypes.byref(st)):
        return None
    return st.dwCurrentState


def status():
    """Stav sluzby jako text, None kdyz neni nainstalovana (jen cteni)."""
    a = _api()
    scm = a.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        return "nezjisteno"
    try:
        svc = a.OpenServiceW(scm, NAME, SERVICE_QUERY_STATUS)
        if not svc:
            return None if ctypes.get_last_error() == ERROR_SERVICE_DOES_NOT_EXIST else "nezjisteno"
        try:
            return STATES.get(_state(a, svc), "nezjisteno")
        finally:
            a.CloseServiceHandle(svc)
    finally:
        a.CloseServiceHandle(scm)


def stop(timeout=10):
    """Zastavit CAMService, pokud bezi. Vrati True, kdyz sluzba nebezi (nebo neexistuje)."""
    if not hasattr(ctypes, "WinDLL"):
        return True
    a = _api()
    scm = a.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        log.warning("CAMService: nelze otevrit spravce sluzeb (chyba %d).", ctypes.get_last_error())
        return False
    try:
        svc = a.OpenServiceW(scm, NAME, SERVICE_QUERY_STATUS | SERVICE_STOP)
        err = ctypes.get_last_error()
        if not svc and err == ERROR_SERVICE_DOES_NOT_EXIST:
            return True
        if not svc and err == ERROR_ACCESS_DENIED:
            svc = a.OpenServiceW(scm, NAME, SERVICE_QUERY_STATUS)
            state = _state(a, svc) if svc else None
            if svc:
                a.CloseServiceHandle(svc)
            if state == 1:
                return True
            log.warning("CAMService bezi a nemam prava ji zastavit - spust aplikaci jako spravce "
                        "(autostart to dela sam).")
            return False
        if not svc:
            log.warning("CAMService: nelze otevrit (chyba %d).", err)
            return False
        try:
            state = _state(a, svc)
            if state == 1:
                return True
            if state == 4:
                st = SERVICE_STATUS()
                if not a.ControlService(svc, SERVICE_CONTROL_STOP, ctypes.byref(st)):
                    log.warning("CAMService nejde zastavit (chyba %d).", ctypes.get_last_error())
                    return False
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if _state(a, svc) == 1:
                    log.info("Sluzba CAMService zastavena.")
                    return True
                time.sleep(0.2)
            log.warning("CAMService se do %d s nezastavila.", timeout)
            return False
        finally:
            a.CloseServiceHandle(svc)
    finally:
        a.CloseServiceHandle(scm)


if __name__ == "__main__":
    print("CAMService:", status())
