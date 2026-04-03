# EPD2in66 MicroPython driver
# Adapted from Waveshare's Raspberry Pi driver for use with Raspberry Pi Pico
# Display: Waveshare 2.66" B&W e-Paper (296x152)

from machine import Pin, SPI
import utime

# Display resolution
EPD_WIDTH  = 152
EPD_HEIGHT = 296

# Default pin assignments - change these to match your wiring
PIN_SCK  = 10  # SPI clock
PIN_MOSI = 11  # SPI data
PIN_CS   = 9   # Chip select
PIN_DC   = 8   # Data/command
PIN_RST  = 12  # Reset
PIN_BUSY = 13  # Busy


class EPD:
    def __init__(self, sck=PIN_SCK, mosi=PIN_MOSI, cs=PIN_CS,
                 dc=PIN_DC, rst=PIN_RST, busy=PIN_BUSY):

        self.spi  = SPI(1, baudrate=4000000, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi))
        self.cs   = Pin(cs,   Pin.OUT)
        self.dc   = Pin(dc,   Pin.OUT)
        self.rst  = Pin(rst,  Pin.OUT)
        self.busy = Pin(busy, Pin.IN)

        self.width  = EPD_WIDTH
        self.height = EPD_HEIGHT

    # Partial refresh waveform lookup table
    WF_PARTIAL = [
        0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x80,0x80,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x40,0x40,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x80,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x0A,0x00,0x00,0x00,0x00,0x00,0x02,0x01,0x00,0x00,
        0x00,0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x22,0x22,0x22,0x22,0x22,0x22,
        0x00,0x00,0x00,0x22,0x17,0x41,0xB0,0x32,0x36,
    ]

    # -------------------------------------------------------------------------
    # Low-level SPI helpers
    # -------------------------------------------------------------------------

    def _send_command(self, cmd):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytes([cmd]))
        self.cs(1)

    def _send_data(self, data):
        self.dc(1)
        self.cs(0)
        if isinstance(data, int):
            self.spi.write(bytes([data]))
        else:
            # accepts list, bytearray, or bytes
            self.spi.write(bytes(data))
        self.cs(1)

    def _wait_busy(self):
        while self.busy.value() == 1:   # 1 = busy, 0 = idle
            utime.sleep_ms(20)

    def _reset(self):
        self.rst(1)
        utime.sleep_ms(200)
        self.rst(0)
        utime.sleep_ms(2)
        self.rst(1)
        utime.sleep_ms(200)

    # -------------------------------------------------------------------------
    # Initialisation
    # -------------------------------------------------------------------------

    def init(self, mode=0):
        """
        mode=0 : full refresh  (use for first draw or after sleep)
        mode=1 : partial refresh (use for animations)
        """
        self._reset()

        self._send_command(0x12)        # soft reset
        utime.sleep_ms(300)
        self._wait_busy()

        self._send_command(0x11)        # data entry mode
        self._send_data(0x03)
        self._send_command(0x44)        # set RAM X address
        self._send_data(0x01)
        self._send_data(0x13)
        self._send_command(0x45)        # set RAM Y address
        self._send_data(0x00)
        self._send_data(0x00)
        self._send_data(0x28)
        self._send_data(0x01)

        if mode == 0:                   # full refresh
            self._send_command(0x3C)
            self._send_data(0x01)

        elif mode == 1:                 # partial refresh
            self._load_lut(self.WF_PARTIAL)

            self._send_command(0x37)
            self._send_data([0x00, 0x00, 0x00, 0x00, 0x00,
                             0x40, 0x00, 0x00, 0x00, 0x00])

            self._send_command(0x3C)
            self._send_data(0x80)

            self._send_command(0x22)
            self._send_data(0xCF)
            self._send_command(0x20)
            self._wait_busy()

    def _load_lut(self, lut):
        self._send_command(0x32)
        self._send_data(lut)

    # -------------------------------------------------------------------------
    # Display update
    # -------------------------------------------------------------------------

    def _turn_on_display(self):
        self._send_command(0x20)
        self._wait_busy()

    def _set_cursor(self):
        """Reset RAM cursor to origin before writing image data."""
        self._send_command(0x4E)
        self._send_data(0x01)
        self._send_command(0x4F)
        self._send_data(0x27)
        self._send_data(0x01)

    def display(self, image):
        """
        Push a byte array (bytearray or list) to the display.
        image must be (EPD_WIDTH * EPD_HEIGHT // 8) bytes.
        1 = white, 0 = black  (matches our convert.py convention).
        """
        self._set_cursor()
        self._send_command(0x24)
        self._send_data(image)
        self._turn_on_display()

    def display_partial(self, image):
        """
        Same as display() but assumes init(mode=1) was called.
        Only changed pixels are redrawn — fast enough for animation.
        """
        self._set_cursor()
        self._send_command(0x24)
        self._send_data(image)
        self._turn_on_display()

    def clear(self, colour=0xFF):
        """
        Fill the display with a solid colour.
        colour=0xFF  →  all white (default)
        colour=0x00  →  all black
        """
        line = self.width // 8
        buf  = [colour] * (self.height * line)

        self._set_cursor()
        self._send_command(0x24)
        self._send_data(buf)
        self._send_command(0x26)
        self._send_data(buf)
        self._turn_on_display()

    # -------------------------------------------------------------------------
    # Power management
    # -------------------------------------------------------------------------

    def sleep(self):
        """Put display into deep sleep. Call init() again to wake."""
        self._send_command(0x10)
        self._send_data(0x01)
        utime.sleep_ms(2000)
