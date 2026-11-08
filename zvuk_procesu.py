# zvuk_procesu.py - zachytavani zvuku jednoho programu (vcetne jeho podprocesu) na Windows 10 2004+ / 11
#
# Windows umi "process loopback": ActivateAudioInterfaceAsync s virtualnim zarizenim
# "VAD\Process_Loopback" a parametry AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS (PID + zahrnout strom procesu).
# Zachyti se jen zvuk daneho programu - hra, Discord nebo upozorneni Windows ne. Vse pres ctypes (COM),
# bez dalsich knihoven. Format si urcujeme sami (procesni loopback nema GetMixFormat):
# 48 kHz, 16 bit, stereo, Windows prevadi automaticky (AUTOCONVERTPCM).
#
# Pouziti: cap = ProcessCapture(pid); cap.start(); ... cap.read() -> bytes (int16 stereo) ...; cap.close()
# Vse volat z jednoho vlakna (COM se inicializuje v start()).

import ctypes
import ctypes.wintypes as wt
import threading
import uuid

RATE = 48000
CHANNELS = 2
BITS = 16

ole32 = ctypes.WinDLL("ole32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
mmdevapi = ctypes.WinDLL("Mmdevapi")

HRESULT = ctypes.c_long
COINIT_MULTITHREADED = 0x0
VT_BLOB = 65
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_PCM = 1
S_OK = 0
E_NOINTERFACE = ctypes.c_long(0x80004002).value
VIRTUAL_DEVICE = "VAD\\Process_Loopback"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, s):
        g = cls()
        ctypes.memmove(ctypes.byref(g), uuid.UUID(s).bytes_le, 16)
        return g

    def key(self):
        return bytes(self)


IID_IUnknown = GUID.of("00000000-0000-0000-C000-000000000046")
IID_IAgileObject = GUID.of("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")
IID_IActivateAudioInterfaceCompletionHandler = GUID.of("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_IAudioClient = GUID.of("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID.of("C8ADBD64-E71E-48A0-A4DE-185C395CD317")


class LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [("ActivationType", ctypes.c_int), ("TargetProcessId", wt.DWORD), ("ProcessLoopbackMode", ctypes.c_int)]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", wt.ULONG), ("pBlobData", ctypes.c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wt.USHORT), ("r1", wt.WORD), ("r2", wt.WORD), ("r3", wt.WORD), ("blob", BLOB),
                ("pad", ctypes.c_void_p)]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD),
                ("nAvgBytesPerSec", wt.DWORD), ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD),
                ("cbSize", wt.WORD)]


ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]
ole32.CoUninitialize.argtypes = []
mmdevapi.ActivateAudioInterfaceAsync.restype = HRESULT
mmdevapi.ActivateAudioInterfaceAsync.argtypes = [wt.LPCWSTR, ctypes.POINTER(GUID), ctypes.POINTER(PROPVARIANT),
                                                 ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _call(obj, index, *args, argtypes=()):
    """Zavolat metodu COM objektu podle poradi ve vtable. Vrati HRESULT."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[index])
    return fn(obj, *args)


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)(vtbl[2])(obj)


def _check(hr, what):
    if hr < 0:
        raise OSError(f"{what}: chyba 0x{hr & 0xFFFFFFFF:08X}")


# ------------------------------------------------- COM objekt: IActivateAudioInterfaceCompletionHandler

QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
ADDREF = ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)
COMPLETED = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p)


class _Vtbl(ctypes.Structure):
    _fields_ = [("QueryInterface", QI), ("AddRef", ADDREF), ("Release", ADDREF), ("ActivateCompleted", COMPLETED)]


class _Obj(ctypes.Structure):
    _fields_ = [("vtbl", ctypes.POINTER(_Vtbl))]


class _Handler:
    """Minimalni COM objekt pro dokonceni aktivace. Je "agilni" (IAgileObject) - Windows ho muze
    zavolat z libovolneho vlakna. Zije, dokud zije Python objekt (pocitani referenci je jen naoko)."""

    OK_IIDS = {IID_IUnknown.key(), IID_IAgileObject.key(), IID_IActivateAudioInterfaceCompletionHandler.key()}

    def __init__(self):
        self.done = threading.Event()
        self.op = None
        self._vt = _Vtbl(QI(self._qi), ADDREF(lambda _s: 1), ADDREF(lambda _s: 1), COMPLETED(self._completed))
        self.obj = _Obj(ctypes.pointer(self._vt))

    @property
    def ptr(self):
        return ctypes.addressof(self.obj)

    def _qi(self, this, riid, ppv):
        if riid and riid.contents.key() in self.OK_IIDS:
            ppv[0] = this
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE

    def _completed(self, _this, op):
        self.op = op
        self.done.set()
        return S_OK


# ------------------------------------------------- zachytavani

class ProcessCapture:
    def __init__(self, pid):
        self.pid = int(pid)
        self.client = self.capture = None
        self.event = None
        self._com = False
        self.block = CHANNELS * BITS // 8

    def start(self, timeout=3.0):
        hr = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        self._com = hr >= 0                         # S_FALSE = uz inicializovano (taky volat Uninitialize)
        params = LOOPBACK_PARAMS(AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK, self.pid,
                                 PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE)
        pv = PROPVARIANT()
        pv.vt = VT_BLOB
        pv.blob.cbSize = ctypes.sizeof(params)
        pv.blob.pBlobData = ctypes.addressof(params)
        handler = _Handler()
        op = ctypes.c_void_p()
        _check(mmdevapi.ActivateAudioInterfaceAsync(VIRTUAL_DEVICE, ctypes.byref(IID_IAudioClient), ctypes.byref(pv),
                                                    handler.ptr, ctypes.byref(op)), "ActivateAudioInterfaceAsync")
        try:
            if not handler.done.wait(timeout):
                raise OSError("aktivace zachytávání nedoběhla")
            hr_act, unk = HRESULT(), ctypes.c_void_p()
            _check(_call(op, 3, ctypes.byref(hr_act), ctypes.byref(unk),          # GetActivateResult
                         argtypes=(ctypes.POINTER(HRESULT), ctypes.POINTER(ctypes.c_void_p))), "GetActivateResult")
            _check(hr_act.value, "aktivace zachytávání")
        finally:
            _release(op)
        self.client = unk
        fmt = WAVEFORMATEX(WAVE_FORMAT_PCM, CHANNELS, RATE, RATE * self.block, self.block, BITS, 0)
        flags = (AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                 | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY)
        _check(_call(self.client, 3, AUDCLNT_SHAREMODE_SHARED, flags, ctypes.c_longlong(200_000),   # Initialize
                     ctypes.c_longlong(0), ctypes.byref(fmt), None,
                     argtypes=(ctypes.c_int, wt.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                               ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p)), "IAudioClient.Initialize")
        self.event = kernel32.CreateEventW(None, False, False, None)
        _check(_call(self.client, 13, self.event, argtypes=(wt.HANDLE,)), "SetEventHandle")
        cap = ctypes.c_void_p()
        _check(_call(self.client, 14, ctypes.byref(IID_IAudioCaptureClient), ctypes.byref(cap),     # GetService
                     argtypes=(ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))), "GetService")
        self.capture = cap
        _check(_call(self.client, 10), "IAudioClient.Start")

    def read(self, timeout_ms=100):
        """Pocka na data (nejvys timeout_ms) a vrati vse, co je k dispozici: bytes int16 stereo.
        Prazdne bytes = nic (program nehraje)."""
        kernel32.WaitForSingleObject(self.event, timeout_ms)
        out = []
        while True:
            n = wt.UINT()
            _check(_call(self.capture, 5, ctypes.byref(n), argtypes=(ctypes.POINTER(wt.UINT),)), "GetNextPacketSize")
            if not n.value:
                break
            data, frames, flags = ctypes.c_void_p(), wt.UINT(), wt.DWORD()
            _check(_call(self.capture, 3, ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None,
                         argtypes=(ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.DWORD),
                                   ctypes.c_void_p, ctypes.c_void_p)), "GetBuffer")
            size = frames.value * self.block
            if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                out.append(bytes(size))
            else:
                out.append(ctypes.string_at(data.value, size))
            _check(_call(self.capture, 4, frames.value, argtypes=(wt.UINT,)), "ReleaseBuffer")
        return b"".join(out)

    def close(self):
        if self.client:
            try:
                _call(self.client, 11)                # Stop
            except OSError:
                pass
        _release(self.capture)
        _release(self.client)
        self.capture = self.client = None
        if self.event:
            kernel32.CloseHandle(self.event)
            self.event = None
        if self._com:
            ole32.CoUninitialize()
            self._com = False


# ------------------------------------------------- procesy

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def processes():
    """[(pid, pid rodice, nazev .exe)] vsech procesu."""
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)              # TH32CS_SNAPPROCESS
    if not snap or snap == wt.HANDLE(-1).value:
        return []
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.th32ParentProcessID, e.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


def main_pid(exe):
    """PID hlavniho procesu programu (rodic neni stejny .exe), None = nebezi.
    Zachytavani se strom procesu tak zachyti i podproces, ktery zvuk skutecne prehrava."""
    exe = exe.lower()
    procs = processes()
    mine = {p for p, _pp, name in procs if name.lower() == exe}
    roots = [p for p, pp, name in procs if name.lower() == exe and pp not in mine]
    return min(roots) if roots else None


if __name__ == "__main__":                            # test: py zvuk_procesu.py [Spotify.exe] [sekundy]
    import array
    import sys
    import time
    name = sys.argv[1] if len(sys.argv) > 1 else "Spotify.exe"
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    pid = main_pid(name)
    if pid is None:
        sys.exit(f"{name} neběží.")
    print(f"Zachytávám {name} (PID {pid}) {secs:g} s...")
    cap = ProcessCapture(pid)
    cap.start()
    end, total, t_print, acc = time.monotonic() + secs, 0, time.monotonic(), []
    try:
        while time.monotonic() < end:
            b = cap.read()
            total += len(b)
            if b:
                acc.extend(array.array("h", b))
            if time.monotonic() - t_print >= 0.5:
                peak = max((abs(v) for v in acc), default=0)
                print(f"  {total // cap.block:7d} vzorků, špička {peak / 32768 * 100:5.1f} %")
                acc, t_print = [], time.monotonic()
    finally:
        cap.close()
