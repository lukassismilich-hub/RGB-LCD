# grafika.py - LED graficke karty Gigabyte RTX 5070 Eagle OC (SFF), PCI 10DE:2F04 / 1458:417D
#
# Radic LED je na sbernici I2C karty (port 1), pristup pres NvAPI z ovladace NVIDIA (nvapi64.dll).
# Protokol podle OpenRGB (GigabyteRGBFusion2BlackwellGPUController), pakety po 64 B na adresu 0x75:
#   - identifikace: zapis [0x10, 0x01], cteni 4 B -> 01 01/02 01 xx (jinak se nic dalsiho neposila)
#   - prima barva:  [0x16, 0x01, 0x00, 0x00, jas 1-10, R, G, B, 0x00, zona 0, 0 barev]
#     (otestovano 7. 10. 2026: ~370 zapisu/s bez chyby, barvu karta drzi)
#   - 0x12 = vestavene rezimy (nejvys ~9 zmen/s), 0x13 = ulozeni do pameti karty - NEPOUZIVA SE
# Jedna zona (bocni svetelny pasek) = jedna "LED". Do pameti karty se nic neuklada: po restartu PC
# karta sviti podle sveho ulozeneho nastaveni, dokud ji aplikace neprevezme.
# Jine karty se nepodporuji - na sbernici I2C jsou i dalsi cipy, naslepo se nezapisuje nic.

import ctypes
import logging

log = logging.getLogger("rgb_lcd")

# (device_id, subsystem_id) z NvAPI_GPU_GetPCIIdentifiers -> (nazev, adresa I2C)
SUPPORTED = {(0x2F0410DE, 0x417D1458): ("RTX 5070 Eagle OC", 0x75)}
PORT = 1
BRIGHTNESS_MAX = 0x0A


class I2CInfo(ctypes.Structure):
    """NV_I2C_INFO_V3"""
    _fields_ = [("version", ctypes.c_uint32), ("display_mask", ctypes.c_uint32),
                ("is_ddc_port", ctypes.c_uint8), ("i2c_dev_address", ctypes.c_uint8),
                ("i2c_reg_address", ctypes.POINTER(ctypes.c_uint8)), ("reg_addr_size", ctypes.c_uint32),
                ("data", ctypes.POINTER(ctypes.c_uint8)), ("size", ctypes.c_uint32),
                ("i2c_speed", ctypes.c_uint32), ("i2c_speed_khz", ctypes.c_int32),
                ("port_id", ctypes.c_uint8), ("is_port_id_set", ctypes.c_uint32)]


_api = None


def _nvapi():
    """Funkce NvAPI (nacte se jednou za beh)."""
    global _api
    if _api is None:
        try:
            dll = ctypes.WinDLL("nvapi64.dll")
        except OSError:
            raise RuntimeError("ovladač NVIDIA (nvapi64.dll) nenalezen")
        qi = dll.nvapi_QueryInterface
        qi.restype = ctypes.c_void_p
        qi.argtypes = [ctypes.c_uint32]

        def fn(id_, *args):
            addr = qi(id_)
            if not addr:
                raise RuntimeError(f"NvAPI nemá funkci 0x{id_:08X}")
            return ctypes.CFUNCTYPE(ctypes.c_int, *args)(addr)
        api = {
            "init": fn(0x0150E828),
            "enum": fn(0xE5AC921F, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int32)),
            "pci": fn(0x2DDFB66E, ctypes.c_void_p, *[ctypes.POINTER(ctypes.c_uint32)] * 4),
            "write": fn(0x283AC65A, ctypes.c_void_p, ctypes.POINTER(I2CInfo), ctypes.POINTER(ctypes.c_uint32)),
            "read": fn(0x4D7B0709, ctypes.c_void_p, ctypes.POINTER(I2CInfo), ctypes.POINTER(ctypes.c_uint32)),
        }
        res = api["init"]()
        if res != 0:
            raise RuntimeError(f"NvAPI se nespustilo (chyba {res})")
        _api = api
    return _api


class Gpu:
    """LED grafiky jako jedna "LED". ok = False, dokud karta neprojde identifikaci."""

    def __init__(self):
        self.ok = False
        self.handle = None
        self.addr = None
        self.name = None
        self.last = None

    def _info(self, buf, size):
        x = I2CInfo()
        x.version = ctypes.sizeof(I2CInfo) | (3 << 16)
        x.i2c_dev_address = self.addr << 1
        x.data = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
        x.size = size
        x.i2c_speed = 0xFFFF                       # vychozi rychlost sbernice
        x.port_id = PORT
        x.is_port_id_set = 1
        return x

    def _write(self, pkt):
        buf = (ctypes.c_uint8 * 64).from_buffer_copy(bytes(pkt) + bytes(64 - len(pkt)))
        unk = ctypes.c_uint32(0)
        res = _nvapi()["write"](self.handle, ctypes.byref(self._info(buf, 64)), ctypes.byref(unk))
        if res != 0:
            raise RuntimeError(f"zápis do karty selhal (NvAPI {res})")

    def _read(self, size):
        buf = (ctypes.c_uint8 * size)()
        x = self._info(buf, size)
        unk = ctypes.c_uint32(0)
        res = _nvapi()["read"](self.handle, ctypes.byref(x), ctypes.byref(unk))
        if res != 0:
            raise RuntimeError(f"čtení z karty selhalo (NvAPI {res})")
        return bytes(buf[:x.size])

    def start(self):
        """Najit podporovanou kartu a overit radic LED. Vyjimka = karta nejde ridit."""
        if self.ok:
            return True
        api = _nvapi()
        handles = (ctypes.c_void_p * 64)()
        n = ctypes.c_int32()
        api["enum"](handles, ctypes.byref(n))
        for i in range(n.value):
            ids = [ctypes.c_uint32() for _ in range(4)]
            if api["pci"](handles[i], *[ctypes.byref(v) for v in ids]) != 0:
                continue
            hit = SUPPORTED.get((ids[0].value, ids[1].value))
            if hit:
                self.handle, (self.name, self.addr) = handles[i], hit
                break
        else:
            raise RuntimeError("podporovaná karta (RTX 5070 Eagle OC) nenalezena")
        self._write([0x10, 0x01])
        ans = self._read(4)
        if len(ans) < 3 or ans[0] != 0x01 or ans[1] not in (0x01, 0x02) or ans[2] != 0x01:
            raise RuntimeError(f"řadič LED na kartě neodpovídá podle očekávání ({ans.hex(' ')})")
        self.ok, self.last = True, None
        return True

    def color(self, rgb, force=False):
        """Barva celeho pasku (0-255). Jas resi aplikace v barve, jas karty je naplno."""
        rgb = tuple(max(0, min(255, int(v))) for v in rgb)
        if self.ok and (force or rgb != self.last):
            self._write([0x16, 0x01, 0x00, 0x00, BRIGHTNESS_MAX, *rgb, 0x00, 0x00, 0x00])
            self.last = rgb

    def stop(self):
        self.ok, self.last = False, None


if __name__ == "__main__":
    import sys
    g = Gpu()
    g.start()
    print("karta:", g.name, f"adresa 0x{g.addr:02X}")
    if len(sys.argv) > 1:                          # py grafika.py ff0000
        h = sys.argv[1].lstrip("#")
        g.color((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
        print("barva", "#" + h)
