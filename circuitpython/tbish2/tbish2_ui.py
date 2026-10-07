# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# tbish2_ui.py -- tbish's play/edit screen for the 132x64 SH1106
#
# Same layout as tbish/tbish_ui.py: two params big in the middle (play
# and more modes) or 8 step notes (edit mode), a step dot, and a status
# line of bpm, steps/beat, transpose, mode and pattern number. Patterns
# longer than 8 steps are shown a page at a time, named top right.
#
# Nothing here refreshes the display. Every setter compares before it
# writes and sets the sticky `dirty`, which whoever calls refresh() clears.

import displayio
import terminalio
import vectorio
from adafruit_display_text import bitmap_label as label

FNT = terminalio.FONT
WHITE = 0xFFFFFF

MODE_NAMES = ("play", "edit", "more")
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

STEP_X0, STEP_DX = 5, 15
STATUS_Y = 58


class TBish2UI(displayio.Group):
    """``text_func(param)`` formats one value; defaults to ``p.fmt % p.val``."""

    def __init__(self, display, page_steps=8, text_func=None):
        super().__init__()
        self.text_func = text_func or (lambda p: p.fmt % p.val)
        #: sticky: set by any change, cleared by whoever refreshes
        self.dirty = True
        self._seen = [None, None]
        self._step = None

        palette = displayio.Palette(1)
        palette[0] = WHITE

        def lbl(text, x, y, group=self, scale=1):
            lb = label.Label(FNT, text=text, color=WHITE, x=x, y=y, scale=scale)
            group.append(lb)
            return lb

        self.play_group = displayio.Group()
        self.edit_group = displayio.Group()
        self.append(self.play_group)
        self.append(self.edit_group)

        lbl("TBish2", 46, 6)
        self.half = lbl("     ", 100, 6)
        self.page_steps = page_steps
        lbl("bpm", 1, STATUS_Y)
        lbl("/", 38, STATUS_Y)
        self.bpm = lbl("   ", 21, STATUS_Y)
        self.spb = lbl("  ", 44, STATUS_Y)
        self.transpose = lbl("   ", 58, STATUS_Y)
        self.mode = lbl("    ", 84, STATUS_Y)
        self.seq = lbl("  ", 114, STATUS_Y)
        self.step_dot = vectorio.Rectangle(
            pixel_shader=palette, width=10, height=4, x=STEP_X0, y=48
        )
        self.append(self.step_dot)

        self.names = [lbl(" " * 10, x, 20, self.play_group) for x in (1, 68)]
        self.values = [lbl(" " * 5, x, 36, self.play_group, 2) for x in (1, 68)]

        self.flags = []
        self.notes = []
        self.octs = []
        for i in range(page_steps):
            x = STEP_X0 + i * STEP_DX
            self.flags.append(lbl("  ", x, 20, self.edit_group))
            self.notes.append(lbl("  ", x, 30, self.edit_group))
            self.octs.append(lbl(" ", x + 5, 38, self.edit_group))

        display.root_group = self
        self.show_mode(0)

    def _set(self, lb, text):
        if lb.text != text:
            lb.text = text
            self.dirty = True

    def show_mode(self, mode):
        self._set(self.mode, MODE_NAMES[mode])
        edit = MODE_NAMES[mode] == "edit"
        if self.edit_group.hidden == edit:
            self.edit_group.hidden = not edit
            self.play_group.hidden = edit
            self.dirty = True

    def show_beat(self, step):
        """Step dot at ``step`` on the shown page, or hidden if None."""
        if step != self._step:
            self._step = step
            self.step_dot.hidden = step is None
            if step is not None:
                self.step_dot.x = STEP_X0 + step * STEP_DX
            self.dirty = True

    def show_half(self, half):
        first = half * self.page_steps + 1
        self._set(self.half, "%d-%d" % (first, first + self.page_steps - 1))

    def show_status(self, bpm, spb, transpose, seq_num):
        self._set(self.bpm, "%3d" % bpm)
        self._set(self.spb, "%-2d" % spb)
        self._set(self.transpose, "%+3d" % transpose)
        self._set(self.seq, "%2d" % seq_num)

    def show_params(self, left, right):
        """Two ``synthtools.paramset.Param`` to show big."""
        for i, p in enumerate((left, right)):
            # identity catches a pair change, the float compare a knob move
            seen = self._seen[i]
            if seen is not None and seen[0] is p and seen[1] == p.val:
                continue
            self._seen[i] = (p, p.val)
            self._set(self.names[i], "%-10s" % p.name)
            self._set(self.values[i], "%-5s" % self.text_func(p)[:5])

    def show_seq(self, notes, vels, slides):
        """Note name, octave and accent/slide flags for one page of steps."""
        for i, note in enumerate(notes):
            if note > 0:
                self._set(self.notes[i], NOTE_NAMES[note % 12])
                self._set(self.octs[i], str(note // 12 - 1))
            else:
                self._set(self.notes[i], "-")
                self._set(self.octs[i], "")
            flag = ("A" if vels[i] > 100 else "") + ("S" if slides[i] else "")
            self._set(self.flags[i], flag)
