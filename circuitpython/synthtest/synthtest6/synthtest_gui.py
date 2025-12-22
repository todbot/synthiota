# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT
#
# synthtest_gui -- simple gui for 'synthtest' app
# 18 Dec 2025 - @todbot / Tod Kurt
#

from micropython import const
import displayio
import vectorio
import terminalio
from adafruit_display_text import bitmap_label as label
from adafruit_bitmap_font import bitmap_font

fnt = terminalio.FONT
fntsm = bitmap_font.load_font("ArkPixel10pxMlatinRegular-tod-10.bdf")

pal = displayio.Palette(2)
pal[0] = 0xffffff
pal[1] = 0x000000

max_height = 20
bx,by = 0,10

num_steps = const(8)

class SynthTestGUI:

    def __init__(self, display, num_pages, param_set, note_steps):
        self.num_pages = num_pages
        self.page_num = 0
        self.param_set = param_set
        self.note_steps = note_steps
        
        maing = displayio.Group()
        display.root_group = maing
    
        maing.append(label.Label(fntsm, text="synthtest", color=pal[0], x=0, y=5))
        pages = displayio.Group()
        maing.append(pages)
        self.pages = pages

        page0 = displayio.Group()
        page1 = displayio.Group()
        self.pages.append(page0)
        self.pages.append(page1)
        page1.hidden = True

            
        synthpot_labels = displayio.Group()
        synthpot_vals = displayio.Group()
        page0.append(synthpot_labels)
        page0.append(synthpot_vals)

        # octave & transpose info
        oct_lbl = label.Label(fntsm, text="oct:", color=pal[0], x=0, y=60)
        oct_lblval = label.Label(fntsm, text="0", color=pal[0], x=20, y=60)
        bpm_lbl = label.Label(fntsm, text="bpm:", color=pal[0], x=90, y=60)
        bpm_lblval = label.Label(fntsm, text="120", color=pal[0], x=110, y=60)
        note_lbl = label.Label(fntsm, text="note:", color=pal[0], x=0, y=50)
        note_info = label.Label(fntsm, text="--", color=pal[0], x=30, y=50)
        for l in (oct_lbl, oct_lblval, bpm_lbl, bpm_lblval, note_lbl, note_info):
            maing.append(l)
        self.oct_lblval = oct_lblval
        self.bpm_lblval = bpm_lblval
            
        # page0 synthpots layout
        for j in range(num_steps):  # num pots
            pn = 0*8 + j  # which parameter to lay out
            param = param_set.params[pn]
            h = 5 + int((param.val / param.span) * max_height) 
            vy = 10 + max_height - h # 
            vx = 5 + 15 * j
            text = label.Label(fnt, text=param.name, color=pal[0],
                               x=bx+vx+3, y=by+10,  label_direction="DWR")
            vline = vectorio.Rectangle(pixel_shader=pal, width=5, height=h,
                                       x=bx+vx, y=by+vy )
            synthpot_labels.append(text)
            synthpot_vals.append(vline)

        # page1 step sequencer layout
        steppot_notes = displayio.Group()
        steppot_gates = displayio.Group()
        page1.append(steppot_notes)
        page1.append(steppot_gates)
        for j in range(8):  # num pots
            nx = 5 + j*16 
            ny = 25
            textn = label.Label(fnt, text="33", color=pal[0], x=nx-3, y=ny)
            textg = label.Label(fnt, text="3", color=pal[0], x=nx-3, y=ny+15)
            steppot_notes.append(textn)
            steppot_gates.append(textg)

    def set_page(self, i):
        print("disp_set_page:",i)
        self.pages[self.page_num].hidden = True
        self.pages[i].hidden = False
        self.page_num = i

    def set_oct_bpm(self, o, b):
        self.oct_lblval.text = "%d" % o
        self.bpm_lblval.text = "%d" % b

    def set_note_info(self, t):
        #self.note_info.text = t
        pass

    def update_steps(self):
        steps = self.steps
        for i in range(num_steps):
            self.pages[1][0][i].text = "%2d" % steps[i][0]
            self.pages[1][1][i].text = "%2d" % (steps[i][1]*10)
            
    def update_params(self):
        param_set = self.param_set
        idx = 0
        for i in range(num_steps):
            param = param_set.params[idx*8 + i]
            vline = self.pages[idx][1][i]
            vline.height = 5 + int((param.val / param.span) * max_height)
            vline.y = by + 10 + max_height - vline.height

    def update(self):
        if self.page_num == 0:
            self.update_params()
        elif self.page_num == 1:
            self.update_steps()
            
        #disp_set_page(0)
        # disp_update_params(param_set)
        #disp_update_oct_bpm(octave, bpm)
        #disp_update_steps(note_steps)


