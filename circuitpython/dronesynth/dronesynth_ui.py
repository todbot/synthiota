# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# dronesynth_ui.py -- dronesynth's screen for the 132x64 SH1106
#
# Eight columns laid out like the pad grid, one per oscillator: the LFO
# mode letter, the note the pot is tuned to, and an underline while the
# oscillator is sounding. One status line at the bottom, written by the
# caller.
#
# Nothing here refreshes the display. Every setter compares before it
# writes and sets the sticky `dirty`, which whoever refreshes clears.

import displayio
import terminalio
from adafruit_display_text import bitmap_label as label

FNT = terminalio.FONT
WHITE = 0xFFFFFF

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MODE_CHARS = (".", "P", "V")  # off, pitch LFO, volume LFO

COL_X0, COL_DX = 5, 15
MODE_Y, NAME_Y, OCT_Y, BAR_Y = 20, 32, 42, 48
STATUS_Y = 58
STATUS_LEN = 21  # terminalio chars that fit the 132px width


class DroneUI(displayio.Group):
    def __init__(self, display):
        super().__init__()
        #: sticky: set by any change, cleared by whoever refreshes
        self.dirty = True

        def lbl(text, x, y):
            lb = label.Label(FNT, text=text, color=WHITE, x=x, y=y)
            self.append(lb)
            return lb

        lbl("DRONE", 1, 6)
        self.wave = lbl("    ", 50, 6)
        self.tune = lbl("    ", 100, 6)

        self.modes, self.names, self.octs, self.bars = [], [], [], []
        for i in range(8):
            x = COL_X0 + i * COL_DX
            self.modes.append(lbl(" ", x + 3, MODE_Y))
            self.names.append(lbl("  ", x, NAME_Y))
            self.octs.append(lbl("  ", x + 3, OCT_Y))
            self.bars.append(lbl("  ", x, BAR_Y))
        self.status = lbl(" " * STATUS_LEN, 1, STATUS_Y)

        display.root_group = self
        display.refresh()  # one initial paint; nothing here refreshes after

    def _set(self, lb, text):
        if lb.text == text:
            return
        lb.text = text
        self.dirty = True

    def set_header(self, wave, tune):
        self._set(self.wave, "%-4s" % wave[:4])
        self._set(self.tune, "%-4s" % tune[:4])

    def set_osc(self, i, note, mode, on):
        n = round(note)
        self._set(self.names[i], "%-2s" % NOTE_NAMES[n % 12])
        self._set(self.octs[i], "%-2d" % (n // 12 - 1))
        self._set(self.modes[i], MODE_CHARS[mode])
        self._set(self.bars[i], "__" if on else "  ")

    def set_status(self, text):
        self._set(self.status, "%-21s" % text[:STATUS_LEN])
