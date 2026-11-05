# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# stepseq8_ui.py -- monobit-flavored screens for the SH1106
#
# All one bitmap, redrawn from the sequencer's state. Every element keeps
# what it last drew and skips the bitmap if that's unchanged, since
# displayio sends the bounding box of whatever got touched.
#
# Nothing here refreshes the display. `dirty` is sticky, whoever calls
# refresh() clears it.

import bitmaptools
import displayio
from adafruit_ticks import ticks_add, ticks_diff
from stepseq8_font import FONT_5X7
from stepseq8_seq import GATE_MAX, MAX_STEPS, NUM_TRACKS

BMP_W, HEIGHT = 132, 64
# the glass is 128 wide, and relic's colstart=3 leaves x=126 as the last we see
WIDTH = 127
PAGE_STEPS = 16

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

TITLE_W, EXT_X, BPM_X, ICON_X = 92, 94, 101, 120
RULE_Y = 8

GRID_Y, GRID_DX, GRID_DY = 10, 8, 7
CELL_W, CELL_H = 7, 6
CELL_PAST, CELL_OFF, CELL_ON, CELL_HEAD_OFF, CELL_HEAD_ON = 0, 1, 2, 3, 4

BARS_Y0, BARS_Y1 = 24, 44  # top, baseline
NOTE_LOW, NOTE_HIGH = 24, 96

POT_DX, POT_W = 16, 15
POT_LABEL_Y, POT_BAR_Y, POT_BAR_H = 46, 55, 9

ALL_DY, ALL_MUTE_X, ALL_X, ALL_DX, ALL_CHAN_X = 8, 8, 14, 3, 113
MINI_H = 5

TOAST_Y, TOAST_H = 52, 11
TOAST_MS = 1500


def note_name(note):
    """60 is C3, as picostepseq has it."""
    return NOTE_NAMES[note % 12] + str(note // 12 - 2)


def _make_font(rows, ink):
    """A strip of 5x7 glyphs. Paper is 1 - ink."""
    count = len(rows) // 7
    bmp = displayio.Bitmap(count * 5, 7, 2)
    bmp.fill(1 - ink)
    for g in range(count):
        for y in range(7):
            row = rows[g * 7 + y]
            for x in range(5):
                if row & (1 << (4 - x)):
                    bmp[g * 5 + x, y] = ink
    return bmp


class SeqUI(displayio.Group):
    def __init__(self, display):
        super().__init__()
        self.dirty = True
        self.bmp = displayio.Bitmap(BMP_W, HEIGHT, 2)
        pal = displayio.Palette(2)
        pal[0] = 0x000000
        pal[1] = 0xFFFFFF
        self.append(displayio.TileGrid(self.bmp, pixel_shader=pal))
        display.root_group = self

        self.font = _make_font(FONT_5X7, 1)
        self.font_ink = _make_font(FONT_5X7, 0)  # for on white

        # 50% checker = "not held", 1-in-4 diagonal = "unavailable", both
        # phase-locked to the panel so neighbors line up
        self.dither = displayio.Bitmap(BMP_W, HEIGHT, 2)
        self.hatch = displayio.Bitmap(BMP_W, HEIGHT, 2)
        for y in range(HEIGHT):
            for x in range(BMP_W):
                self.dither[x, y] = (x + y) & 1 ^ 1
                self.hatch[x, y] = 1 if (x + y) & 3 == 0 else 0

        self._toast_until = None
        self.view = None
        self._reset()

    def _reset(self):
        self.bmp.fill(0)
        self.dirty = True
        self._title = self._bpm = self._ext = self._icon = None
        self._cells = bytearray(b"\xff" * (NUM_TRACKS * MAX_STEPS))
        self._page = None
        self._bars = [None] * PAGE_STEPS
        self._pots = [None] * NUM_TRACKS
        self._rows = [None] * NUM_TRACKS
        if self.view == "track":
            self._texture(self.dither, 0, RULE_Y, WIDTH, 1)
            self._texture(self.dither, 0, BARS_Y1, WIDTH, 1)

    # --- monobit's primitives ----------------------------------------------

    def _fill(self, x, y, w, h, color=1):
        bitmaptools.fill_region(self.bmp, x, y, x + w, y + h, color)
        self.dirty = True

    def _rect(self, x, y, w, h):
        self._fill(x, y, w, 1)
        self._fill(x, y + h - 1, w, 1)
        self._fill(x, y, 1, h)
        self._fill(x + w - 1, y, 1, h)

    def _texture(self, tex, x, y, w, h):
        bitmaptools.blit(self.bmp, tex, x, y, x1=x, y1=y, x2=x + w, y2=y + h)
        self.dirty = True

    def _text(self, font, x, y, text):
        for ch in text:
            g = ord(ch) - 32
            bitmaptools.blit(self.bmp, font, x, y, x1=g * 5, y1=0, x2=(g + 1) * 5, y2=7)
            x += 6
        self.dirty = True

    # --- status bar --------------------------------------------------------

    def _status(self, title, bpm, playing, ext):
        if title != self._title:
            self._title = title
            self._fill(0, 0, TITLE_W, RULE_Y, 0)
            self._text(self.font, 0, 0, title)
        if ext != self._ext:
            self._ext = ext
            self._fill(EXT_X, 0, 5, 7, 0)
            if ext:
                self._text(self.font, EXT_X, 0, "E")
        if bpm != self._bpm:
            self._bpm = bpm
            self._fill(BPM_X, 0, ICON_X - BPM_X, RULE_Y, 0)
            self._text(self.font, BPM_X, 0, "%3d" % bpm)
        if playing != self._icon:
            self._icon = playing
            self._fill(ICON_X, 0, 7, 7, 0)
            if playing:
                for i in range(4):
                    self._fill(ICON_X + 1 + i, i, 1, 7 - 2 * i)
            else:
                self._fill(ICON_X + 1, 0, 2, 7)
                self._fill(ICON_X + 4, 0, 2, 7)

    # --- track view --------------------------------------------------------

    def _cell(self, i, x, y, state):
        if self._cells[i] == state:
            return
        self._cells[i] = state
        self._fill(x, y, CELL_W, CELL_H, 0)
        if state == CELL_PAST:
            self._texture(self.hatch, x, y, CELL_W, CELL_H)
        elif state == CELL_HEAD_ON:
            self._fill(x, y, CELL_W, CELL_H)
        elif state == CELL_HEAD_OFF:
            self._texture(self.dither, x, y, CELL_W, CELL_H)
        else:
            self._rect(x, y, CELL_W, CELL_H)
            if state == CELL_ON:
                self._fill(x + 2, y + 2, 3, 2)

    def _grid(self, track, page):
        steps = track.seq.steps
        for i in range(MAX_STEPS):
            if i >= track.length:
                state = CELL_PAST
            elif i == track.pos:
                state = CELL_HEAD_ON if steps[i][3] else CELL_HEAD_OFF
            else:
                state = CELL_ON if steps[i][3] else CELL_OFF
            self._cell(i, GRID_DX * (i % PAGE_STEPS), GRID_Y + GRID_DY * (i // PAGE_STEPS), state)
        if page != self._page:
            self._page = page
            for row in range(2):  # underlines the row the pads are on
                self._fill(0, GRID_Y + CELL_H + GRID_DY * row, WIDTH, 1, int(row == page))

    def _bars_draw(self, track, page, held):
        """Height is pitch, width is gate. Solid while held, else dithered."""
        span = BARS_Y1 - BARS_Y0
        for n in range(PAGE_STEPS):
            note, _vel, gate, on = track.seq.steps[page * PAGE_STEPS + n]
            is_held = n == held
            key = None
            if on or is_held:
                note = min(max(note + track.transpose, NOTE_LOW), NOTE_HIGH)
                h = 1 + (note - NOTE_LOW) * (span - 1) // (NOTE_HIGH - NOTE_LOW)
                w = 1 + int(gate * GATE_MAX) * (CELL_W - 1) // GATE_MAX
                key = (h, w, is_held)
            if key == self._bars[n]:
                continue
            self._bars[n] = key
            x = GRID_DX * n
            self._fill(x, BARS_Y0, CELL_W, span, 0)
            if key:
                if is_held:
                    self._fill(x, BARS_Y1 - h, w, h)
                else:
                    self._texture(self.dither, x, BARS_Y1 - h, w, h)

    def _pot(self, i, label, frac, knob, held):
        """A value and where the pot really is, monobit's level and target."""
        fill = int(frac * (POT_W - 2) + 0.5)
        mark = int(knob * (POT_W - 3) + 0.5)
        key = (fill, mark, held)
        if key == self._pots[i]:
            return
        x = POT_DX * i
        if self._pots[i] is None:
            self._text(self.font, x + 2, POT_LABEL_Y, label)
        self._pots[i] = key
        self._fill(x, POT_BAR_Y, POT_W, POT_BAR_H, 0)
        self._rect(x, POT_BAR_Y, POT_W, POT_BAR_H)
        if fill:
            if held:
                self._fill(x + 1, POT_BAR_Y + 1, fill, POT_BAR_H - 2)
            else:
                self._texture(self.dither, x + 1, POT_BAR_Y + 1, fill, POT_BAR_H - 2)
        # flips color to read on either side of the fill
        self._fill(x + 1 + mark, POT_BAR_Y + 1, 1, POT_BAR_H - 2, 0 if mark < fill else 1)

    def draw_track(self, num, track, page, held, pattern, bpm, playing, ext, readout, pots):
        """``held`` is a step on this page. ``readout`` is a param to title,
        or None. ``pots`` is 8 of (label, value 0-1, knob 0-1, held)."""
        self._set_view("track")
        if held is not None:
            step = page * PAGE_STEPS + held
            note, vel, gate, _on = track.seq.steps[step]
            title = "%02d %s V%d G%d" % (step + 1, note_name(note + track.transpose), vel,
                                         round(gate * GATE_MAX))
        else:
            title = readout or "TRACK %d P%d" % (num + 1, pattern + 1)
        self._status(title, bpm, playing, ext)
        self._grid(track, page)
        self._bars_draw(track, page, held)
        if self._toast_until is None:
            for i, (label, frac, knob, is_held) in enumerate(pots):
                self._pot(i, label, frac, knob, is_held)

    # --- all-tracks view ---------------------------------------------------

    def _mini_cell(self, i, x, y, state):
        if self._cells[i] == state:
            return
        self._cells[i] = state
        self._fill(x, y, ALL_DX - 1, MINI_H, 0)
        if state == CELL_HEAD_ON:
            self._fill(x, y, ALL_DX - 1, MINI_H)
        elif state == CELL_ON:
            self._fill(x, y + 2, ALL_DX - 1, MINI_H - 2)
        elif state == CELL_OFF:
            self._fill(x, y + MINI_H - 1, 1, 1)

    def draw_all(self, tracks, selected):
        """A row per track: number, M if muted, its steps, its MIDI channel."""
        self._set_view("all")
        # the toast sits over the last rows
        last_row = NUM_TRACKS - 2 if self._toast_until is not None else NUM_TRACKS
        for r in range(last_row):
            t = tracks[r]
            y = r * ALL_DY
            key = (r == selected, t.muted, t.chan)
            if key != self._rows[r]:
                self._rows[r] = key
                self._fill(0, y, ALL_X - 1, 7, 0)
                self._fill(ALL_CHAN_X, y, WIDTH - ALL_CHAN_X, 7, 0)
                if r == selected:
                    self._fill(0, y, 7, 7)
                self._text(self.font_ink if r == selected else self.font, 1, y, str(r + 1))
                if t.muted:
                    self._text(self.font, ALL_MUTE_X, y, "M")
                self._text(self.font, ALL_CHAN_X, y, "%2d" % (t.chan + 1))
            steps = t.seq.steps
            for i in range(MAX_STEPS):
                if i >= t.length:
                    state = CELL_PAST
                elif i == t.pos:
                    state = CELL_HEAD_ON
                else:
                    state = CELL_ON if steps[i][3] else CELL_OFF
                self._mini_cell(r * MAX_STEPS + i, ALL_X + i * ALL_DX, y + 1, state)

    def _set_view(self, view):
        if view != self.view:
            self.view = view
            self._reset()

    # --- toast -------------------------------------------------------------

    def toast(self, text, now):
        """Dark halo, white pill, dark text, along the bottom edge."""
        self._toast_until = ticks_add(now, TOAST_MS)
        w = len(text) * 6 + 8
        x = (WIDTH - w) // 2
        self._fill(x - 1, TOAST_Y - 1, w + 2, TOAST_H + 1, 0)
        self._fill(x + 1, TOAST_Y, w - 2, TOAST_H)
        self._fill(x, TOAST_Y + 1, w, TOAST_H - 2)
        self._text(self.font_ink, x + 4, TOAST_Y + 2, text)

    def expire_toast(self, now):
        if self._toast_until is not None and ticks_diff(now, self._toast_until) >= 0:
            self._toast_until = None
            self._reset()
