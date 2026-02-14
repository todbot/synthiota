# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT
"""
`code.py`
================================================================================

This is the main code.py for a TB-like synth

8 Feb 2026 - @todbot / Tod Kurt

"""
# this reduces some of per-step latency from 10ms down to 6ms, sigh
import microcontroller
microcontroller.cpu.frequency = 200_000_000

import time, random, gc
from micropython import const
import ulab.numpy as np
import rainbowio
import synthio
from synthiota_synth_setup import (display, leds, uart, mpr121s,
                                   update_pots, encoder, encoder_sw, get_touch_events,
                                   mixer, Pads)

from mapped_pot_controller import MappedPotController, Parameter

from tbish_synth import TBishSynth, waves
from tbish_sequencer import TBishSequencer
from tbish_ui import TBishUI


bpm = 120
steps_per_beat = 4   # 4 = 16th note, 2 = 8th note, 1 = quarter note

tbsynth = TBishSynth(mixer.sample_rate, mixer.channel_count)
mixer.voice[0].play(tbsynth.audio_out)

seqs = [
    [[24,  36, 48, 36,  48, 48+7, 36, 48],    # notes: midi notenum
     [127, 80, 80, 80,  127,  80, 80, 80],    # vels: 100+ = accent, 
     [0,    0,  0,  0,   0,   1,  0,  1]],    # slides: 1 = slide
        
    [[36,   0,   0,  0,  24,    0,   0,  0],  # notes, 0 = rest
     [127, 80,  80, 80,  127 , 80, 127, 80],  
     [0,    1,   1,  0,   0,    1,   0,  1]], # slides: 1 = slide
    
    [[36,  48, 36, 48,  36,  48, 36, 48],  # notes, 0 = rest
     [127, 80, 80, 80,  127, 80, 80, 80],  # vels 100+ = accent
     [0,    0,  1,  1,   0,   1,  0,  1]], # slides: 1 = slide
    
    [[34, 36, 34, 36,  48, 48, 36, 48],      # notes, 0 = rest
     [127, 80, 127, 80,  127, 80, 127, 80],  # vels 100+ = accent
     [0,    0,  0,  0,   0,   0,  0,  0]],   # slides: 1 = slide
    
    [[36,  24,  36, 48,  36, 0, 36, 0],     # notes, 0 = rest
     [127, 80, 80, 80,  127, 80, 127, 80],  # vels 100+ = accent
     [0,    1,  1,  0,   0,   0,  0,  0]],  # slides: 1 = slide
]

myconfig = [
    [
        Parameter(100, 5000, "Freq", callback=tbsynth.set_cutoff),
        Parameter(0.0, 1.0, "EnvMod", callback=tbsynth.set_envmod),
        Parameter(0.5, 4.0, "ResQ", callback=tbsynth.set_resonance),
        Parameter(0.0, 1.0, "Decay", callback=tbsynth.set_decay),
        Parameter(0.0, 1.0, "Accent", callback=tbsynth.set_accent),
        Parameter(0,   3,   "Wave", options=["SQU", "SAW", "SW2", "SW3"], callback=tbsynth.set_wavenum),
        Parameter(0.0, 1.0, "Drive", callback=tbsynth.set_drive_mix),
        Parameter(0.0, 1.0, "Delay", callback=tbsynth.set_delay_mix),
    ],
    [
        Parameter(24, 72, 'step0'),
        Parameter(24, 72, 'step1'),
        Parameter(24, 72, 'step2'),
        Parameter(24, 72, 'step3'),
        Parameter(24, 72, 'step4'),
        Parameter(24, 72, 'step5'),
        Parameter(24, 72, 'step6'),
        Parameter(24, 72, 'step7'),
    ],   
    [
        Parameter(30, 180, "BPM"),
        Parameter(0, len(seqs)-1, "SeqNum"),
        Parameter(-2, +3, "Transpose"),
        Parameter(0.0, 1.0, "DelaylTime"),
        Parameter(0.0, 1.0, "DriveGain"),
        
        Parameter(0.0, 1.0, "DriveGain"),
        Parameter(0.0, 1.0, "DriveGain"),
        Parameter(0.0, 1.0, "DriveGain"),
        Parameter(0.0, 1.0, "DriveGain"),
    ],
]

potctrl = MappedPotController(myconfig, mode=MappedPotController.MODE_RELATIVE)
# this loads a "patch" 
potctrl.load_preset(0, [2345, 0.5,  1.5, 0.5,   0.2, 0.0,  0.0, 0.0])
potctrl.load_preset(1, seqs[0][0] )

tbsynth.drive = 1.0
tbsynth.delay_time = 0.33

sequencer = TBishSequencer(tbsynth, seqs=seqs)
sequencer.bpm = bpm
sequencer.steps_per_beat = steps_per_beat

last_encoder_pos = encoder.position

tb_disp = TBishUI(display, 8)
tb_disp.update_param_pairs(*potctrl.get_display_data(0), *potctrl.get_display_data(1))
tb_disp.update_seq(seqs, sequencer.seq_num)
tb_disp.update_transpose(sequencer.transpose)

def show_step(i, steps_per_beat, seq_len):
    leds[16 + i] = 0x333333   # FIXME
    if i % steps_per_beat == 0:
        leds[Pads.LED_PLAY] = 0x333333 
    tb_disp.show_beat(i, steps_per_beat, seq_len)

sequencer.on_step_callback = show_step
sequencer.stop()

print("="*80)
print("tbish synth! press encoder button to play/pause")
print("="*80)
print("secs_per_step:%.3f" % sequencer._secs_per_step)
print("mem_free:", gc.mem_free())

#_pot_indices = tuple(range(8))  # cache the range
dim_by = const(3)
transpose = 0
transpose_oct = 0

#disp_mode = 1  # note edit
disp_mode = 0  # performing

tb_disp.show_mode(disp_mode)


while True:

    sequencer.update()

    # handle LEDs
    leds[:] = [[max(i-dim_by,0) for i in l] for l in leds] # dim all by (dim_by,dim_by,dim_by)
    #               (fixme: use np to speed this fade up)

    if disp_mode == 0:  # PLAY mode
        if not sequencer.playing:
            leds[Pads.LED_PLAY] = 0x333333

    elif disp_mode == 1:  # EDIT sequence mode
        leds[Pads.LED_EDIT] = 0x333333
        seq = seqs[sequencer.seq_num]
        for i in range(8):
            note  = seq[0][i]
            vel   = seq[1][i]
            slide = seq[2][i]
            if slide and vel > 100:
                leds[i+8] = 0x330033
            elif slide:
                leds[i+8] = 0x000033
            elif vel > 100: 
                leds[i+8] = 0x330000
            leds[i] = 0x333333 if note > 0 else 0  # show note on or muted
                       
    leds.show()    # auto-write is off, so we must explicitly show
    
    # handle pots
    raw_potvals = update_pots()  # get real pot values (smoothed)
    pot_changes = potctrl.update(raw_potvals)  # detect changes w/ hysteresis
    current_params = potctrl.values  # get mapped real values
    
    if pot_changes:
        #print("%02x" % pot_changes, current_params, time.monotonic())
        bank_idx = potctrl.current_bank
        if bank_idx == 0:  # synth params
            labelL, labelR = None,None
            for i in range(8):
                if (pot_changes >> i) & 1:
                    j = (i//2) * 2   # FIXME all of this
                    print(i, j, potctrl.get_display_data(i), potctrl.get_display_data(j))
                    labelL, textL = potctrl.get_display_data(j)
                    labelR, textR = potctrl.get_display_data(j+1)
                    tb_disp.curr_param_pair = j
                    tb_disp.update_param_pairs(labelL, textL, labelR, textR)

        elif bank_idx == 1:   # note steps
            for i in range(8):
                if (pot_changes >> i) & 1:
                    notenum = potctrl.values[i]
                    print("note:", i, notenum, sequencer.seq_num)
                    seqs[sequencer.seq_num][0][i] = notenum
                    tb_disp.update_seq_step(i, notenum, 100)

        elif bank_idx == 2:   # secondary parameters
            pass

    # handle encoder
    delta_pos = last_encoder_pos - encoder.position 
    last_encoder_pos = encoder.position
    if delta_pos:
        disp_mode = (disp_mode + 1) % 2
        print("delta pos:", delta_pos, disp_mode)
        tb_disp.show_mode(disp_mode)
        potctrl.switch_bank(disp_mode, raw_potvals)
        
    # handle encoder push switch
    key = encoder_sw.events.get()
    if key and key.pressed:
        if sequencer.playing:
            sequencer.stop()
            # testing out save/load params
            #s = ParamSet.dump(param_set)  # dump patch to string as JSON
            #ParamSet.load(s)   # load patch in as JSON
        else:
            sequencer.start()

    # handle touchpads
    touch_events = get_touch_events()
    for touch in touch_events:
        i = touch.key_number
        if touch.pressed:
            n = Pads.PAD_TO_LED.index(i)
            leds[n] = rainbowio.colorwheel(time.monotonic()*50)
            print("touch", i, n)
            if i in Pads.STEP_PADS:
                if disp_mode == 0:
                    if sequencer.playing:
                        transpose = n-8    # chromatic and lame
                        sequencer.transpose = transpose + transpose_oct*12
                        tb_disp.update_transpose(sequencer.transpose)
                    else:
                        tbsynth.note_on(36 + n + transpose_oct*12)  # note_off automatically haappens
                elif disp_mode == 1: # sequence edit mode
                    seq = seqs[sequencer.seq_num]
                    if n < 8:  # lower pads: step on -> accent -> mute
                        note  = seq[0][n]
                        vel   = seq[1][n]
                        if note > 0:
                            note = 0
                        else:
                            note = potctrl.values[n]
                            vel = 80
                        seq[0][n] = note 
                        seq[1][n] = vel
                    elif n < 16:
                        n = n - 8  # get to sequence range
                        vel   = seq[1][n]
                        slide = seq[2][n]
                        print(vel,slide)
                        # four states: normal note -> accent -> slide -> slide+accent -> norm
                        if vel <= 100 and slide == 0:  # no accent + no slide; go to
                            vel = 127   # accent 
                            slide = 0   # no slide
                        elif vel > 100 and slide == 0: # accent + no slide; go to 
                            vel = 80    # no accent
                            slide = 1   # slide
                        elif vel <= 100 and slide == 1: # no accent + slide; go to
                            vel = 127   # accent 
                            slide = 1   # slide
                        else:
                            vel = 80    # no accent 
                            slide = 0   # no slide
                        seq[1][n] = vel
                        seq[2][n] = slide
                        print(vel, slide, seq)
                        
                tb_disp.update_seq(seqs, sequencer.seq_num)
                        
                    
            elif i == Pads.PAD_OCT_UP:
                transpose_oct = min(transpose_oct+1, 3)
                sequencer.transpose = transpose + transpose_oct*12
                tb_disp.update_transpose(sequencer.transpose)
                
            elif i == Pads.PAD_OCT_DOWN:
                transpose_oct = max(transpose_oct-1, -2)
                sequencer.transpose = transpose + transpose_oct*12                
                tb_disp.update_transpose(sequencer.transpose)
                
            elif i == Pads.PAD_RSLIDE_C:  # change sequence on top-right pad press
                seq_num = (sequencer.seq_num + 1) % len(sequencer.seqs)
                sequencer.seq_num = seq_num
                tb_disp.update_seq( seqs, seq_num )
                print("** changing sequence!", seq_num)
                
            elif i == Pads.PAD_LSLIDE_A:   # left slider, left edge
                bpm -= 1
                sequencer.bpm = bpm
                tb_disp.update_bpm(bpm)
                
            elif i == Pads.PAD_LSLIDE_C:   # left slider, right edge
                bpm += 1
                sequencer.bpm = bpm
                tb_disp.update_bpm(bpm)

