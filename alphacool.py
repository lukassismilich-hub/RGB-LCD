# alphacool.py - monochromaticky Alphacool USB display (VID 060C, PID 04EB), 240x128
#
# Protokol podle serdisplib (serdisp_specific_acoolsdcm.c, serdisp_connect_usb.c):
#   vendor IN  0x47 (ALPHACOOL_DEVICE)         -> 1 bajt: 0 = 200x64, 1 = 240x128
#   vendor OUT 0x31 (ALPHACOOL_INIT)
#   vendor OUT 0x32 (GFX_WRITE_INIT) value = (y1 << 8) | x1, index = (vyska << 8) | sirka
#              x a sirka v bajtech (8 bodu), y a vyska v radcich
#   bulk  OUT  endpoint 0x03: data po radcich, 30 bajtu na radek, MSB = levy bod
#   vendor OUT 0x33 (GFX_WRITE_END)
#   vendor OUT 0x43 (BKL) value = 1/0 podsviceni, 0x3A (CLEAR) smazani
#
# Ovladac: WinUSB (Zadig). Puvodni ovladac Alphacoolu (libusb0) ma jen 32bitovou DLL.
#
# Displej bezi ve vlastnim vlakne - kdyz se zasekne nebo odpoji, rizeni chlazeni
# v hlavni smycce to nezdrzi.

import logging
import threading
import time

import mono

log = logging.getLogger("rgb_lcd")

VID, PID = 0x060C, 0x04EB
EP_OUT = 0x03
REQ_OUT, REQ_IN = 0x40, 0xC0          # vendor | device | smer
CMD_INIT, CMD_WRITE_INIT, CMD_WRITE_END = 0x31, 0x32, 0x33
CMD_CLEAR, CMD_BKL, CMD_DEVICE = 0x3A, 0x43, 0x47
TIMEOUT_MS = 1000
RETRY_S = 10


def _backend():
    import libusb_package
    import usb.backend.libusb1 as b1
    return b1.get_backend(find_library=lambda _: str(libusb_package.get_library_path()))


class AlphacoolDisplay:
    def __init__(self):
        self.dev = None
        self.size = None
        self._backlight = None

    def open(self):
        import usb.core
        import usb.util
        dev = usb.core.find(idVendor=VID, idProduct=PID, backend=_backend())
        if dev is None:
            raise RuntimeError("Alphacool displej nenalezen.")
        try:
            dev.set_configuration(1)
        except (usb.core.USBError, NotImplementedError):
            pass                                  # WinUSB konfiguraci nastavuje sam
        usb.util.claim_interface(dev, 0)
        t = dev.ctrl_transfer(REQ_IN, CMD_DEVICE, 0, 0, 1, timeout=TIMEOUT_MS)
        typ = t[0] if len(t) else None
        if typ != 1:
            usb.util.dispose_resources(dev)
            raise RuntimeError(f"Nepodporovany typ displeje ({typ}) - umim jen 240x128.")
        dev.ctrl_transfer(REQ_OUT, CMD_INIT, 0, 0, None, timeout=TIMEOUT_MS)
        self.dev = dev
        self.size = (mono.WIDTH, mono.HEIGHT)
        self._backlight = None

    def backlight(self, on):
        on = bool(on)
        if on != self._backlight:
            self.dev.ctrl_transfer(REQ_OUT, CMD_BKL, 1 if on else 0, 0, None, timeout=TIMEOUT_MS)
            self._backlight = on

    def clear(self):
        self.dev.ctrl_transfer(REQ_OUT, CMD_CLEAR, 0, 0, None, timeout=TIMEOUT_MS)

    def show(self, img):
        """img = obrazek 240x128 v rezimu "1" (1 = rozsviceny bod)."""
        w_bytes, h = mono.WIDTH // 8, mono.HEIGHT
        data = img.tobytes()                      # po radcich, MSB = levy bod
        self.dev.ctrl_transfer(REQ_OUT, CMD_WRITE_INIT, 0, (h << 8) | w_bytes, None,
                               timeout=TIMEOUT_MS)
        self.dev.write(EP_OUT, data, timeout=TIMEOUT_MS)
        self.dev.ctrl_transfer(REQ_OUT, CMD_WRITE_END, 0, 0, None, timeout=TIMEOUT_MS)

    def close(self, blank=True):
        if self.dev is None:
            return
        import usb.util
        try:
            if blank:
                self.clear()
                self.dev.ctrl_transfer(REQ_OUT, CMD_BKL, 0, 0, None, timeout=TIMEOUT_MS)
        except Exception:
            pass
        try:
            usb.util.release_interface(self.dev, 0)
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass
        self.dev = None


class AlphacoolWorker(threading.Thread):
    """Vlakno displeje: hlavni smycka jen preda data (update), vlakno kresli a posila."""

    def __init__(self):
        super().__init__(name="alphacool", daemon=True)
        self.disp = AlphacoolDisplay()
        self._lock = threading.Lock()
        self._acfg, self._data, self._hist, self._period = None, {}, {}, 1.0
        self._quit = threading.Event()
        self._wake = threading.Event()
        self.state = {"stav": "spousti se"}

    def update(self, acfg, data, hist, period):
        with self._lock:
            self._acfg, self._data, self._hist = acfg, data, hist
            self._period = max(0.25, float(period))
        self._wake.set()

    def stop(self, timeout=2.0):
        self._quit.set()
        self._wake.set()
        self.join(timeout)

    def _set_state(self, stav, msg=None, level=logging.INFO):
        if self.state.get("stav") != stav:
            log.log(level, "Alphacool: %s", msg or stav)
        self.state = {"stav": stav}

    def run(self):
        last, next_try = None, 0.0
        while not self._quit.is_set():
            self._wake.wait(1.0)
            self._wake.clear()
            with self._lock:
                acfg, data, hist, period = self._acfg, self._data, self._hist, self._period
            if acfg is None:
                continue
            if not acfg.get("zapnuto", True):
                if self.disp.dev is not None:
                    self.disp.close()
                self._set_state("vypnuto", "displej vypnut v nastaveni")
                last = None
                continue
            try:
                if self.disp.dev is None:
                    if time.monotonic() < next_try:
                        continue
                    next_try = time.monotonic() + RETRY_S
                    self.disp.open()
                    last = None
                    self._set_state("pripojen", "displej pripojen (240x128)")
                self.disp.backlight(acfg.get("podsviceni", True))
                img = mono.render(acfg, data, hist)
                b = img.tobytes()
                if b != last:
                    self.disp.show(img)
                    last = b
            except Exception as e:
                self.disp.close(blank=False)
                self._set_state("nenalezen" if "nenalezen" in str(e) else "chyba",
                                f"{e} - zkusim znovu za {RETRY_S} s", logging.WARNING)
                continue
            # dalsi snimek nejdriv za period (hodiny se meni po sekunde)
            self._quit.wait(period)
        self.disp.close()
