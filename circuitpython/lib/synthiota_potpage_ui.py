# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# synthiota_potpage_ui.py -- two-up parameter screen for the 132x64 SH1106
# on Synthiota, in the style of tbish's UI.
#
#     from synthiota_potpage_ui import PotPageUI
#
#     PAGES = (("OSC/AMP", 8), ("FILT/MOD", 8))
#     ui = PotPageUI(display, param_set, PAGES, param_text)
#     ui.set_shown(a, b)          # two param indices 0..7 on the current page
#     ui.update("C3")
#     if ui.dirty:
#         display.refresh()
#
# All eight pots on a page are live; the screen shows just TWO params big
# -- one pair -- as name over a scale-2 value. Turning any pot snaps the
# screen to that pot's pair (pots 1-2, 3-4, 5-6 or 7-8). The caller
# decides which two params and calls set_shown(). The encoder turns
# pages; the header shows page name, page number and octave.
#
# Redraw discipline as in pico_test_synth's SynthUI: everything is built
# once, update() compares before assigning, an unchanged screen sends no
# bytes, a name is only rewritten when its slot changes param.

import displayio
import terminalio
from adafruit_display_text import bitmap_label as label

PER_PAGE = 8

HEAD_Y = 8
NAME_Y = 24
VAL_Y = 43  # scale 2; keeps a few px clear of the 64px bottom edge
COL_X = (2, 68)
VAL_MAXLEN = 5  # scale-2 chars that fit a 64px half

SEC_X = 2
POS_X = 62
OCT_X = 102  # right-side label, up to 5 chars (e.g. a key + octave "A#-2")


class PotPageUI(displayio.Group):
    """Two-up editor over a ``synthtools.paramset.ParamSet``.

    Holds the ParamSet, so whatever the pots wrote is what gets drawn.
    ``pages`` is a sequence of ``(name, 8)`` in ParamSet order.
    ``text_func(param)`` formats one value; defaults to ``p.fmt % p.val``.
    """

    def __init__(self, display, param_set, pages, text_func=None):
        super().__init__()
        if param_set.nknobs != PER_PAGE:
            raise ValueError("PotPageUI needs a ParamSet built with num_knobs=8")
        total = 0
        for name, count in pages:
            if count != PER_PAGE:
                raise ValueError("page '%s' must hold exactly 8 params" % name)
            total += count
        if total != param_set.nparams:
            raise ValueError(
                "pages cover %d params, ParamSet has %d" % (total, param_set.nparams)
            )

        self.display = display
        self.param_set = param_set
        self.pages = pages
        self.text_func = text_func or (lambda p: p.fmt % p.val)
        #: sticky: set by update(), cleared by whoever calls display.refresh()
        self.dirty = True

        self.shown = (0, 1)  # param indices within the current page
        self._seen = [None, None]
        self._seen_page = None
        self._seen_oct = None

        self.names, self.values = [], []
        for x in COL_X:
            nm = label.Label(terminalio.FONT, text=" " * 9, color=0xFFFFFF, x=x, y=NAME_Y)
            vl = label.Label(
                terminalio.FONT, text=" " * VAL_MAXLEN, color=0xFFFFFF, x=x, y=VAL_Y, scale=2
            )
            self.append(nm)
            self.append(vl)
            self.names.append(nm)
            self.values.append(vl)

        self.sec = label.Label(terminalio.FONT, text=" " * 8, color=0xFFFFFF, x=SEC_X, y=HEAD_Y)
        self.pos = label.Label(terminalio.FONT, text=" " * 3, color=0xFFFFFF, x=POS_X, y=HEAD_Y)
        self.oct = label.Label(terminalio.FONT, text=" " * 5, color=0xFFFFFF, x=OCT_X, y=HEAD_Y)
        for o in (self.sec, self.pos, self.oct):
            self.append(o)
        display.root_group = self
        self.update()
        display.refresh()  # one initial paint; update() never refreshes after this

    def set_shown(self, left, right):
        """Param indices (0..7 on the current page) for the left and right
        cells -- normally an even/odd pair (2n, 2n+1)."""
        self.shown = (left, right)

    def _set(self, lbl, text):
        if lbl.text == text:
            return False
        lbl.text = text
        return True

    def update(self, oct_name=""):
        """Redraw from the ParamSet. Returns True if anything changed.

        Does not refresh the display: the caller picks the moment.
        """
        ps = self.param_set
        page = ps.idx
        first = page * PER_PAGE
        changed = False

        if page != self._seen_page:
            self._seen_page = page
            self._seen = [None, None]
            changed |= self._set(self.sec, "%-8s" % self.pages[page][0][:8])
            changed |= self._set(self.pos, "%d/%d" % (page + 1, len(self.pages)))
            changed = True

        for slot in range(2):
            gi = self.shown[slot]
            p = ps.params[first + gi]
            seen = self._seen[slot]
            if seen is None or seen[0] is not p:
                self._seen[slot] = [p, None]
                changed |= self._set(self.names[slot], "%-9s" % ("P%d %s" % (gi + 1, p.name))[:9])
            if self._seen[slot][1] != p.val:
                self._seen[slot][1] = p.val
                changed |= self._set(
                    self.values[slot], "%-5s" % self.text_func(p)[:VAL_MAXLEN]
                )

        if oct_name != self._seen_oct:
            self._seen_oct = oct_name
            changed |= self._set(self.oct, "%-5s" % oct_name[:5])

        self.dirty = self.dirty or changed
        return changed
