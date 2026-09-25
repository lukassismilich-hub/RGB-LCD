# systemdata.py - hodnoty, ktere HWiNFO neposila: misto na discich a sit (vlastni cteni z Windows)
#
#   @disk C: volno / obsazeno / celkem       (GB, %)          - kazdy pevny disk, obnova 10 s
#   @síť stahování / odesílání               (MB/s)           - soucet pripojenych fyzickych adapteru
#   @síť <adapter>: stahování / odesílání    (MB/s)           - kazdy pripojeny fyzicky adapter
#   @síť rychlost připojení                  (Mbps)           - nejrychlejsi pripojeny adapter
#   @wifi signál                             (dBm)            - obnova 2 s
#   @wifi kvalita                            (%)
#
# Jen Windows API pres ctypes (GetIfTable2, wlanapi), zadne dalsi balicky. Kdyz neco
# nejde precist, hodnota v datech proste chybi.

import ctypes
import shutil
import string
import time
from collections import deque
from ctypes import wintypes

DISK_EVERY_S = 10
WIFI_EVERY_S = 2
RATE_WINDOW_S = 1.0          # rychlost site z rozdilu za >= 1 s (jinak by pri 0,25 s skakala)
MB = 1024 * 1024

_cache = {"disk": (0.0, {}), "wifi": (0.0, {})}
_net_hist = {}               # alias -> deque[(cas, prijato, odeslano)]


# ------------------------------------------------------------------ disky
def _disks():
    out = {}
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << i):
            continue
        root = f"{letter}:\\"
        if k32.GetDriveTypeW(root) != 3:          # DRIVE_FIXED (ne USB klicenky, site, CD)
            continue
        try:
            u = shutil.disk_usage(root)
        except OSError:
            continue
        name = f"@disk {letter}:"
        out[f"{name} volno"] = {"value": round(u.free / 1024 ** 3, 1), "unit": "GB", "sensor": "Windows"}
        out[f"{name} celkem"] = {"value": round(u.total / 1024 ** 3, 1), "unit": "GB", "sensor": "Windows"}
        out[f"{name} obsazeno"] = {"value": round(100 * u.used / u.total, 1) if u.total else 0.0,
                                   "unit": "%", "sensor": "Windows"}
    return out


# ------------------------------------------------------------------- sit
class _NET_LUID(ctypes.Structure):
    _fields_ = [("Value", ctypes.c_uint64)]


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class MIB_IF_ROW2(ctypes.Structure):
    _fields_ = [
        ("InterfaceLuid", _NET_LUID), ("InterfaceIndex", wintypes.ULONG), ("InterfaceGuid", _GUID),
        ("Alias", wintypes.WCHAR * 257), ("Description", wintypes.WCHAR * 257),
        ("PhysicalAddressLength", wintypes.ULONG), ("PhysicalAddress", ctypes.c_ubyte * 32),
        ("PermanentPhysicalAddress", ctypes.c_ubyte * 32), ("Mtu", wintypes.ULONG), ("Type", wintypes.ULONG),
        ("TunnelType", ctypes.c_int), ("MediaType", ctypes.c_int), ("PhysicalMediumType", ctypes.c_int),
        ("AccessType", ctypes.c_int), ("DirectionType", ctypes.c_int), ("Flags", ctypes.c_ubyte),
        ("OperStatus", ctypes.c_int), ("AdminStatus", ctypes.c_int), ("MediaConnectState", ctypes.c_int),
        ("NetworkGuid", _GUID), ("ConnectionType", ctypes.c_int),
        ("TransmitLinkSpeed", ctypes.c_uint64), ("ReceiveLinkSpeed", ctypes.c_uint64),
        ("InOctets", ctypes.c_uint64), ("InUcastPkts", ctypes.c_uint64), ("InNUcastPkts", ctypes.c_uint64),
        ("InDiscards", ctypes.c_uint64), ("InErrors", ctypes.c_uint64), ("InUnknownProtos", ctypes.c_uint64),
        ("InUcastOctets", ctypes.c_uint64), ("InMulticastOctets", ctypes.c_uint64),
        ("InBroadcastOctets", ctypes.c_uint64),
        ("OutOctets", ctypes.c_uint64), ("OutUcastPkts", ctypes.c_uint64), ("OutNUcastPkts", ctypes.c_uint64),
        ("OutDiscards", ctypes.c_uint64), ("OutErrors", ctypes.c_uint64), ("OutUcastOctets", ctypes.c_uint64),
        ("OutMulticastOctets", ctypes.c_uint64), ("OutBroadcastOctets", ctypes.c_uint64),
        ("OutQLen", ctypes.c_uint64),
    ]


assert ctypes.sizeof(MIB_IF_ROW2) == 1352, ctypes.sizeof(MIB_IF_ROW2)   # velikost podle Windows SDK

_iphlp = None


def _adapters():
    """[(alias, prijato_B, odeslano_B, rychlost_bps)] pro pripojene fyzicke adaptery."""
    global _iphlp
    if _iphlp is None:
        _iphlp = ctypes.WinDLL("iphlpapi")
        _iphlp.GetIfTable2.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        _iphlp.FreeMibTable.argtypes = [ctypes.c_void_p]
    ptr = ctypes.c_void_p()
    if _iphlp.GetIfTable2(ctypes.byref(ptr)) != 0:
        return []
    try:
        n = ctypes.c_ulong.from_address(ptr.value).value
        rows = (MIB_IF_ROW2 * n).from_address(ptr.value + 8)       # NumEntries + zarovnani na 8
        out = []
        for r in rows:
            hardware, filt = r.Flags & 0x01, r.Flags & 0x02
            if not hardware or filt or r.OperStatus != 1 or r.Type == 24:   # 1 = Up, 24 = loopback
                continue
            out.append((r.Alias, r.InOctets, r.OutOctets, max(r.ReceiveLinkSpeed, r.TransmitLinkSpeed)))
        return out
    finally:
        _iphlp.FreeMibTable(ptr)


def _network(now):
    out = {}
    total_in = total_out = 0.0
    speed = 0
    have = False
    for alias, rx, tx, bps in _adapters():
        hist = _net_hist.setdefault(alias, deque())
        hist.append((now, rx, tx))
        while len(hist) > 2 and now - hist[1][0] >= RATE_WINDOW_S:
            hist.popleft()
        t0, rx0, tx0 = hist[0]
        speed = max(speed, bps)
        if now - t0 <= 0:
            continue
        rin = max(0, rx - rx0) / (now - t0) / MB
        rout = max(0, tx - tx0) / (now - t0) / MB
        total_in, total_out, have = total_in + rin, total_out + rout, True
        out[f"@síť {alias}: stahování"] = {"value": round(rin, 3), "unit": "MB/s", "sensor": "Windows"}
        out[f"@síť {alias}: odesílání"] = {"value": round(rout, 3), "unit": "MB/s", "sensor": "Windows"}
    if have:
        out["@síť stahování"] = {"value": round(total_in, 3), "unit": "MB/s", "sensor": "Windows"}
        out["@síť odesílání"] = {"value": round(total_out, 3), "unit": "MB/s", "sensor": "Windows"}
    if speed:
        out["@síť rychlost připojení"] = {"value": round(speed / 1e6, 1), "unit": "Mbps", "sensor": "Windows"}
    return out


# ------------------------------------------------------------------- wifi
class _WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", _GUID), ("strInterfaceDescription", wintypes.WCHAR * 256),
                ("isState", ctypes.c_int)]


class _WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wintypes.DWORD), ("dwIndex", wintypes.DWORD),
                ("InterfaceInfo", _WLAN_INTERFACE_INFO * 1)]


class _DOT11_SSID(ctypes.Structure):
    _fields_ = [("uSSIDLength", wintypes.ULONG), ("ucSSID", ctypes.c_ubyte * 32)]


class _WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("dot11Ssid", _DOT11_SSID), ("dot11BssType", ctypes.c_int), ("dot11Bssid", ctypes.c_ubyte * 6),
                ("dot11PhyType", ctypes.c_int), ("uDot11PhyIndex", wintypes.ULONG),
                ("wlanSignalQuality", wintypes.ULONG), ("ulRxRate", wintypes.ULONG), ("ulTxRate", wintypes.ULONG)]


class _WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("isState", ctypes.c_int), ("wlanConnectionMode", ctypes.c_int),
                ("strProfileName", wintypes.WCHAR * 256),
                ("wlanAssociationAttributes", _WLAN_ASSOCIATION_ATTRIBUTES)]


_wlan = {"dll": None, "handle": None}
WLAN_OPCODE_CURRENT_CONNECTION = 7
WLAN_OPCODE_RSSI = 0x10000102


def _wifi():
    if _wlan["dll"] is None:
        dll = ctypes.WinDLL("wlanapi")
        dll.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                       ctypes.POINTER(wintypes.HANDLE)]
        dll.WlanEnumInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        dll.WlanQueryInterface.argtypes = [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.c_int, ctypes.c_void_p,
                                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.c_void_p]
        dll.WlanFreeMemory.argtypes = [ctypes.c_void_p]
        ver, h = wintypes.DWORD(), wintypes.HANDLE()
        if dll.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(h)) != 0:
            raise OSError("WlanOpenHandle")
        _wlan["dll"], _wlan["handle"] = dll, h
    dll, h = _wlan["dll"], _wlan["handle"]
    lst = ctypes.c_void_p()
    if dll.WlanEnumInterfaces(h, None, ctypes.byref(lst)) != 0:
        return {}
    out = {}
    try:
        count = _WLAN_INTERFACE_INFO_LIST.from_address(lst.value).dwNumberOfItems
        infos = (_WLAN_INTERFACE_INFO * count).from_address(lst.value + 8)
        for info in infos:
            if info.isState != 1:                       # 1 = pripojeno
                continue
            guid = info.InterfaceGuid
            size, data = wintypes.DWORD(), ctypes.c_void_p()
            if dll.WlanQueryInterface(h, ctypes.byref(guid), WLAN_OPCODE_CURRENT_CONNECTION, None,
                                      ctypes.byref(size), ctypes.byref(data), None) == 0:
                attrs = _WLAN_CONNECTION_ATTRIBUTES.from_address(data.value).wlanAssociationAttributes
                out["@wifi kvalita"] = {"value": float(attrs.wlanSignalQuality), "unit": "%", "sensor": "Windows"}
                out["@wifi rychlost"] = {"value": round(attrs.ulRxRate / 1000, 1), "unit": "Mbps",
                                         "sensor": "Windows"}
                dll.WlanFreeMemory(data)
            if dll.WlanQueryInterface(h, ctypes.byref(guid), WLAN_OPCODE_RSSI, None,
                                      ctypes.byref(size), ctypes.byref(data), None) == 0:
                out["@wifi signál"] = {"value": float(ctypes.c_long.from_address(data.value).value),
                                       "unit": "dBm", "sensor": "Windows"}
                dll.WlanFreeMemory(data)
            break                                       # prvni pripojene Wi-Fi staci
    finally:
        dll.WlanFreeMemory(lst)
    return out


# -------------------------------------------------------------------- vstup
def _cached(key, every, fn, now):
    t, val = _cache[key]
    if now - t >= every:
        try:
            val = fn()
        except Exception:
            val = {}
        _cache[key] = (now, val)
    return val


def read():
    """Vsechny vlastni hodnoty jako {nazev: {"value", "unit", "sensor"}}."""
    now = time.monotonic()
    out = {}
    out.update(_cached("disk", DISK_EVERY_S, _disks, now))
    try:
        out.update(_network(now))
    except Exception:
        pass
    out.update(_cached("wifi", WIFI_EVERY_S, _wifi, now))
    return out


if __name__ == "__main__":
    read()
    time.sleep(1.2)
    for k, v in sorted(read().items()):
        print(f"{k:40s} {v['value']:>10} {v['unit']}")
