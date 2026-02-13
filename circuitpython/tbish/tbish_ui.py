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
        
        palette = displayio.Palette(1)
        palette[0] = cw
        
        self.playGroup = displayio.Group()
        self.editGroup = displayio.Group()
        self.append(self.playGroup)
        self.append(self.editGroup)
        
        self.editGroup.hidden = True
       
        # Elements on all pages
        
        self.translabel = label.Label(fnt, text="+12", color=cw, x=58, y=58)
        self.modelabel = label.Label(fnt, text="mode", color=cw, x=80, y=58)
        self.seqlabel = label.Label(fnt, text="0", color=cw, x=110, y=58)
        self.stepspot =  vectorio.Rectangle(pixel_shader=palette, width=10, height=4, x=5, y=38)
        logo = label.Label(fnt, text="TBish", color=cw, x=0, y=60)
        for l in (self.modelabel, self.seqlabel, self.translabel, self.stepspot, logo):
            self.append(l)
                
        # Play group UI elements
        
        self.num_param_pairs = num_params//2
        self.curr_param_pair = 0
        
        # text of the currently editable parameters
        self.textA = label.Label(fnt, text="tA", color=cw, x=1, y=24, scale=2)
        self.textB = label.Label(fnt, text="tB", color=cw, x=75, y=24, scale=2)

        # labels for the currently editable parameters
        self.labelA = label.Label(fnt, text="lablA", color=cw, x=1, y=8)
        self.labelB = label.Label(fnt, text="lablB", color=cw, x=75, y=8)
        
        #rect = vectorio.Rectangle(pixel_shader=palette, width=64, height=1, x=32, y=1)
        self.paramspot = vectorio.Rectangle(pixel_shader=palette, width=4, height=4, x=32, y=5)
        self.playGroup.append(self.paramspot)
        
        for l in (self.textA, self.textB, self.labelA, self.labelB):
            self.playGroup.append(l)

        # Edit group UI elements
        
        bpmlabellabel = label.Label(fnt, text="bpm:", color=cw, x=1, y=8)
        self.bpmlabel = label.Label(fnt, text="123", color=cw, x=23, y=8)
        self.notelabels = displayio.Group()
        self.accentlabels = displayio.Group()
        for l in (self.notelabels, self.accentlabels, self.bpmlabel, bpmlabellabel):
            self.editGroup.append(l)
            
        for i in range(8):
            al = label.Label(fnt, text="", color=cw, x=5+i+15, y=25)
            l = label.Label(fnt, text="34", color=cw, x=5+i*15, y=30)
            self.notelabels.append(l)
            self.accentlabels.append(al)

        self.display.refresh()

    def next_param_pair(self):
        self.curr_param_pair = (self.curr_param_pair+1) % self.num_param_pairs
    
    def show_beat(self, step, steps_per_beat, seq_len):
        self.stepspot.x = 5 + step * 15

    def update_bpm(self, b):
        self.bpmlabel.text = "%3d" % b

    def update_transpose(self, t):
        self.translabel.text = "%+2d" % t

    def update_seq(self, seqs, seqnum):
        self.seqlabel.text = "%2d" % seqnum
        for i in range(8):
            self.notelabels[i].text = "%2d" % seqs[seqnum][0][i]

    def update_seq_step(self, i, notenum, vel=100):
        self.notelabels[i].text = "%2d" % notenum
            
    def show_mode(self, mode):
        if mode == 0:
            self.modelabel.text = "play"
            self.playGroup.hidden = False
            self.editGroup.hidden = True
        if mode == 1:
            self.modelabel.text = "edit"
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
        
