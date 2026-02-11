# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT
import displayio
import vectorio
import terminalio
from adafruit_display_text import bitmap_label as label
fnt = terminalio.FONT
cw = 0xFFFFFF

class TBishUI(displayio.Group):
    def __init__(self, display, num_params): 
        # params is an ordered dict of numeric parameters to change
        super().__init__()
        self.display = display   # only needed so we can refresh
        display.root_group = self
        
        self.playGroup = displayio.Group()
        self.editGroup = displayio.Group()
        self.append(self.playGroup)
        self.append(self.editGroup)
        
        self.editGroup.hidden = True

        # labels for mode
        self.labelmode = label.Label(fnt, text="mode", color=cw, x=103, y=58, scale=1)
        self.append(self.labelmode)
        
        # play group UI elements
        
        self.num_param_pairs = num_params//2
        self.curr_param_pair = 0
        
        # text of the currently editable parameters
        self.textA = label.Label(fnt, text="tA", color=cw, x=1, y=24, scale=2)
        self.textB = label.Label(fnt, text="tB", color=cw, x=75, y=24, scale=2)

        # labels for the currently editable parameters
        self.labelA = label.Label(fnt, text="lablA", color=cw, x=1, y=8, scale=1)
        self.labelB = label.Label(fnt, text="lablB", color=cw, x=75, y=8, scale=1)
        
        palette = displayio.Palette(1)
        palette[0] = cw
        #self.rect = vectorio.Rectangle(pixel_shader=palette, width=64, height=1, x=32, y=1)
        self.paramspot = vectorio.Rectangle(pixel_shader=palette, width=4, height=4, x=32, y=5)
        self.stepspot =  vectorio.Rectangle(pixel_shader=palette, width=5, height=5, x=64, y=60)
        self.playGroup.append(self.paramspot)
        self.playGroup.append(self.stepspot)
        
        for l in (self.textA, self.textB, self.labelA, self.labelB):
            self.playGroup.append(l)

        logo = label.Label(fnt, text="TBishBassSynth", color=cw, x=20, y=45)
        self.playGroup.append(logo)

        for i in range(8):
            l = label.Label(fnt, text="34", color=cw, x=10+i*10, y=45)
            self.editGroup.append(l)

        self.display.refresh()

    def next_param_pair(self):
        self.curr_param_pair = (self.curr_param_pair+1) % self.num_param_pairs
    
    def show_beat(self, step, steps_per_beat, seq_len):
        self.stepspot.x = 5 + step * 6
        
    def update_seq(self, seq):
        for i in range(8):
            pass
            
    def show_mode(self, mode):
        if mode == 0:
            self.labelmode.text = "play"
            self.playGroup.hidden = False
            self.editGroup.hidden = True
        if mode == 1:
            self.labelmode.text = "edit"
            self.playGroup.hidden = True
            self.editGroup.hidden = False

    def update_paramL(self, labelA, textA):
        self.labelA.text = labelA
        self.textA.text = textA

    def update_paramR(self, labelA, textA):
        self.labelB.text = labelB
        self.textB.text = textB
        
    def update_param_pairs(self, labelA, textA, labelB, textB):
        self.paramspot.x = 45 + 4*(self.curr_param_pair)

        self.labelA.text = labelA
        self.textA.text = textA
        self.labelB.text = labelB
        self.textB.text = textB
        
        self.display.refresh()
        
