# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# dronesynth_wt_ui.py -- dronesynth_wt's screen for the 132x64 SH1106
#
# Eight columns laid out like the pad grid, one per oscillator: a scope of
# the wave it is reading right now, its place in the table, its note, LFO
# mode and level. While a pad is held a focus panel takes the columns'
# place, showing what that gesture is steering.
#
# One 1-bit language throughout: solid is live, dithered is out or not
# routed, a dotted line is a track and a solid one the value on it.
#
# Nothing here refreshes the display. Every setter compares before it
# draws and sets the sticky `dirty`, which whoever refreshes clears.

import bitmaptools
import displayio
import terminalio
import ulab.numpy as np
from adafruit_display_text import bitmap_label as label

FNT = terminalio.FONT
W, H = 132, 64

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MODE_CHARS = (".", "W", "V", "B")  # off, wave LFO, volume LFO, both

TOP_Y = 10  # everything under the header's rule
COL_X0, COL_DX = 2, 16
SCOPE_Y, SCOPE_W, SCOPE_H = 10, 12, 24
SCOPE_BIN = 21  # samples per scope pixel: 12 * 21 of a 256-sample wave
STRIP_Y, STRIP_W = 35, 14
LEVEL_Y = 59
NAME_Y, OCT_Y = 42, 51
TABLE_LEN = 8

BIG_X, BIG_Y = 70, 20  # the focus panel's curve / scope
BIG_W, BIG_H = 60, 30


class DroneUI(displayio.Group):
    def __init__(self, display):
        super().__init__()
        #: sticky: set by any change, cleared by whoever refreshes
        self.dirty = True
        self.bmp = displayio.Bitmap(W, H, 2)
        pal = displayio.Palette(2)
        pal[1] = 0xFFFFFF
        self.append(displayio.TileGrid(self.bmp, pixel_shader=pal))
        self.cols = displayio.Group()
        self.panel = displayio.Group()
        self.panel.hidden = True
        self.append(self.cols)
        self.append(self.panel)

        def lbl(text, x, y, grp=self, scale=1):
            lb = label.Label(FNT, text=text, color=0xFFFFFF, x=x, y=y, scale=scale)
            grp.append(lb)
            return lb

        self.table = lbl(" " * TABLE_LEN, 1, 4)
        lbl("c", 52, 4)
        lbl("m", 79, 4)
        self.tune = lbl("    ", 108, 4)
        self.names, self.octs = [], []
        for i in range(8):
            x = COL_X0 + i * COL_DX + 1
            self.names.append(lbl("  ", x, NAME_Y, self.cols))
            self.octs.append(lbl("  ", x, OCT_Y, self.cols))
        self.title = lbl(" " * 21, 1, 14, self.panel)
        self.big = lbl(" " * 5, 1, 30, self.panel, scale=2)
        self.small = lbl(" " * 6, 1, 45, self.panel)
        self.dlbl = [lbl(" ", 1, y, self.panel) for y in (51, 59)]
        self.dval = [lbl("   ", 113, y, self.panel) for y in (51, 59)]

        for x in range(0, W, 2):  # the header's rule
            self.bmp[x, 8] = 1
        self._keys = {}  # what each region was last drawn from
        self._focus = None
        self._pts = None  # the focus curve, cached per LFO and shape

        display.root_group = self
        display.refresh()  # one initial paint; nothing here refreshes after

    # -- drawing --------------------------------------------------------

    def _changed(self, region, key):
        if self._keys.get(region) == key:
            return False
        self._keys[region] = key
        self.dirty = True
        return True

    def _clear(self, x0, y0, x1, y1):
        bitmaptools.fill_region(self.bmp, x0, y0, x1, y1, 0)

    def _dots(self, x0, x1, y):
        for x in range(x0 + (x0 & 1), x1, 2):
            self.bmp[x, y] = 1

    def _bar(self, x, y, w, h, v, solid=True):
        """A fill over a dotted track, the fill dithered when not live."""
        self._clear(x, y, x + w, y + h + 1)
        self._dots(x, x + w, y + h)
        n = round(min(max(v, 0.0), 1.0) * w)
        if solid:
            bitmaptools.fill_region(self.bmp, x, y, x + n, y + h, 1)
            return
        for yy in range(y, y + h):  # phase-stable on the panel, so no seams
            for xx in range(x + ((x + yy) & 1), x + n, 2):
                self.bmp[xx, yy] = 1

    def _strip(self, x, y, w, pos, span):
        """Where in the table: dotted track, solid sweep span, tick at now."""
        self._clear(x, y, x + w, y + 3)
        self._dots(x, x + w, y + 1)
        if span:
            bitmaptools.draw_line(self.bmp, x + round(span[0] * (w - 1)), y + 1,
                                  x + round(span[1] * (w - 1)), y + 1, 1)
        px = x + round(min(max(pos, 0.0), 1.0) * (w - 1))
        bitmaptools.draw_line(self.bmp, px, y, px, y + 2, 1)

    def _scope(self, x, y, w, h, buf, solid=True, gain=1.0):
        """A min/max envelope per pixel, so a busy wave doesn't alias,
        ``gain`` high."""
        self._clear(x, y, x + w, y + h)
        n = len(buf) // w
        seg = buf[: n * w].reshape((w, n))
        hs, ls = np.max(seg, axis=1), np.min(seg, axis=1)
        mid, k = y + h // 2, (h // 2 - 1) * min(max(gain, 0.0), 1.0) / 32768
        ph = pl = None
        for j in range(w):
            hi = mid - int(hs[j] * k)
            lo = mid - int(ls[j] * k)
            if ph is not None:  # join to the last bin so it stays one trace
                hi, lo = min(hi, pl), max(lo, ph)
            ph, pl = hi, lo
            if solid:
                bitmaptools.draw_line(self.bmp, x + j, hi, x + j, lo, 1)
            else:
                for yy in range(hi + ((x + j + hi) & 1), lo + 1, 2):
                    self.bmp[x + j, yy] = 1

    def _set(self, lb, text):
        if lb.text == text:
            return
        lb.text = text
        self.dirty = True

    # -- the idle screen ------------------------------------------------

    def set_header(self, table, tune, cut, mod):
        if self._changed("table", table):
            self._keys = {"table": table}  # a new table: every scope is stale
        self._set(self.table, "%-8s" % table[:TABLE_LEN])
        self._set(self.tune, "%-4s" % tune[:4])
        if self._changed("cut", round(cut * 16)):
            self._bar(59, 1, 16, 4, cut)
        if self._changed("mod", round(mod * 16)):
            self._bar(86, 1, 16, 4, mod)

    def set_osc(self, i, note, mode, on, level, gain, buf, at, pos, span):
        """``at`` is the wave the buffer holds, ``pos`` and ``span`` the
        same and the LFO's sweep as fractions of the table, ``gain`` how
        loud it is right now, 0..1."""
        n = round(note)
        self._set(self.names[i], "%-2s" % NOTE_NAMES[n % 12])
        self._set(self.octs[i], "%d%s" % (n // 12 - 1, MODE_CHARS[mode]))
        if self._focus is not None:
            return
        x = COL_X0 + i * COL_DX
        if self._changed(("scope", i), (at, on, round(gain * SCOPE_H))):
            self._scope(x + 1, SCOPE_Y, SCOPE_W, SCOPE_H, buf, on, gain)
        sp = span and (round(span[0] * STRIP_W), round(span[1] * STRIP_W))
        if self._changed(("strip", i), (round(pos * STRIP_W), sp)):
            self._strip(x, STRIP_Y, STRIP_W, pos, span)
        if self._changed(("level", i), (round(level * 14), on)):
            self._bar(x, LEVEL_Y, 14, 3, level, on)

    # -- the focus panel ------------------------------------------------

    def _enter(self, focus):
        if self._focus == focus:
            return
        self._focus = focus
        self._clear(0, TOP_Y, W, H)
        self._keys = {k: v for k, v in self._keys.items()
                      if k in ("table", "cut", "mod")}
        self.cols.hidden = focus is not None
        self.panel.hidden = focus is None
        self.dirty = True

    def focus_off(self):
        self._enter(None)

    def focus_lfo(self, i, title, big, buf, phase, depths):
        """``depths`` is ((letter, value, routed), ...) for wave and volume."""
        self._enter(("lfo", i))
        self._set(self.title, title)
        self._set(self.big, big)
        self._set(self.small, "")
        key = title  # which LFO and its shape
        if self._pts is None or self._pts[0] != key:
            mid, k = BIG_Y + BIG_H // 2, BIG_H // 2 - 2
            self._pts = (key, [mid - int(buf[j * len(buf) // BIG_W]) * k // 32768
                               for j in range(BIG_W)])
        if self._changed("panel", (key, round(phase * BIG_W))):
            ys = self._pts[1]
            self._clear(BIG_X - 1, BIG_Y, BIG_X + BIG_W + 1, BIG_Y + BIG_H)
            self._dots(BIG_X, BIG_X + BIG_W, BIG_Y + BIG_H // 2)
            for j in range(1, BIG_W):
                bitmaptools.draw_line(self.bmp, BIG_X + j - 1, ys[j - 1],
                                      BIG_X + j, ys[j], 1)
            j = min(int(phase * BIG_W), BIG_W - 1)
            bitmaptools.fill_region(self.bmp, BIG_X + j - 1, ys[j] - 1,
                                    BIG_X + j + 2, ys[j] + 2, 1)
        for r, (ch, v, live) in enumerate(depths):
            self._set(self.dlbl[r], ch)
            self._set(self.dval[r], "%3d" % round(100 * v))
            if self._changed(("depth", r), (round(v * 100), live)):
                self._bar(10, 50 + 8 * r, 100, 3, v, live)

    def focus_osc(self, i, title, big, small, buf, at, gain, level=None,
                  strip=None):
        """A volume (``level``) or a table position (``strip``, as
        (pos, start, span))."""
        self._enter(("osc", i, strip is None))
        self._set(self.title, title)
        self._set(self.big, big)
        self._set(self.small, small)
        for lb in self.dlbl + self.dval:
            self._set(lb, "")
        if self._changed("panel", (at, round(gain * BIG_H))):
            self._scope(BIG_X, BIG_Y, BIG_W, BIG_H, buf, gain=gain)
        if level is not None and self._changed(("depth", 0), round(level * 128)):
            self._bar(1, 56, 128, 4, level)
        if strip is not None:
            pos, start, span = strip
            if self._changed(("depth", 0), (round(pos * 128), round(start * 128), span)):
                self._clear(0, 54, W, 61)  # the start marker overhangs the strip
                self._strip(1, 56, 128, pos, span)
                x = 1 + round(start * 127)
                bitmaptools.fill_region(self.bmp, max(x - 1, 0), 55, x + 2, 60, 1)
