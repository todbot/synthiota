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

import time, random
import ulab.numpy as np
import synthio
from synth_setup_synthiota import (display, leds, uart, mpr121s,
                                   update_pots, encoder, encoder_sw, get_touch_events,
                                   mixer, Pads)

from mapped_pot_controller import MappedPotController, Parameter

from tbish_synth import TBishSynth, waves
from tbish_sequencer import TBishSequencer
from tbish_ui import TBishUI


bpm = 120
steps_per_beat = 4   # 4 = 16th note, 2 = 8th note, 1 = quarter note

tbsynth = TBishSynth(mixer.sample_rate, mixer.channel_count)
tb_audio = tbsynth.add_audioeffects()
mixer.voice[0].play(tb_audio)

seqs = [
    [[36, 36, 48, 36,  48, 48+7, 36, 48],  # notes, 0 = rest
     [127, 80, 80, 80,  127, 1, 30, 1]],   # vels, 1=slide, 127=accent
    
    [[36, 48, 36, 48,  36, 48, 36, 48],  # notes, 0 = rest
     [127, 80, 1, 1,  127, 1, 30, 1]],   # vels, 1=slide, 127=accent
    
    [[34, 36, 34, 36,  48, 48, 36, 48],    # notes, 0 = rest
     [127, 80, 120, 80,  127, 11, 127, 80]],  # vels 127=accent
    
    [[36, 36-12, 36, 36+12,  36, 0, 36, 0],    # notes, 0 = rest
     [127,  1,   1, 80,  127, 80, 127, 80]],  # vels 127=accent
    
    [[36, 36+12, 0, 0,  36-12, 36, 36, 0],    # notes, 0 = rest
     [127,  1,   1, 80,  127, 80, 127, 80]],  # vels 127=accent  
]

myconfig = [
    [
        Parameter(100, 5000, "Freq", callback=tbsynth.set_cutoff),
        Parameter(0.0, 1.0, "EnvMod", callback=tbsynth.set_envmod),
        Parameter(0.5, 4.0, "ResQ", callback=tbsynth.set_resonance),
        Parameter(0.0, 1.0, "Decay", callback=tbsynth.set_decay),
        Parameter(0.0, 1.0, "Accent", callback=tbsynth.set_accent),
        Parameter(0,   3,   "Wave", options=["SAW", "TRI", "SQU", "NZE"], callback=tbsynth.set_wavenum),
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
]

potctrl = MappedPotController(myconfig, mode=MappedPotController.MODE_RELATIVE)
potctrl.load_preset(0, [2345, 0.5,  1.5, 0.75,   0.2, 0.0,  0.0, 0.0])
potctrl.load_preset(1, seqs[0][0] )


tbsynth.drive = 1.0
tbsynth.delay_time = 0.33

sequencer = TBishSequencer(tbsynth, seqs=seqs)
sequencer.bpm = bpm
sequencer.steps_per_beat = steps_per_beat

last_encoder_pos = encoder.position

tb_disp = TBishUI(display, 8)
tb_disp.update_param_pairs(*potctrl.get_display_data(0), *potctrl.get_display_data(1))

sequencer.on_step_callback = tb_disp.show_beat
sequencer.stop()


print("="*80)
print("tbish synth! press button to play/pause")
print("="*80)
print("secs_per_step:%.3f" % sequencer._secs_per_step)
import gc
print("mem_free:", gc.mem_free())


#disp_mode = 1  # note edit
disp_mode = 0  # performing

tb_disp.show_mode(disp_mode)

while True:

    sequencer.update()
    
    # handle pots
    raw_potvals = update_pots()
    pot_changes = potctrl.update(raw_potvals)
    current_params = potctrl.values
    
    if pot_changes:
        print("%02x" % pot_changes, current_params)
        bank_idx = potctrl.current_bank  
        if bank_idx == 0:  # synth params
            labelL, labelR = None,None
            for i in range(8):
                if (pot_changes >> i) & 1:
                    j = (i//2) * 2   # FIXME all of this
                    labelL, textL = potctrl.get_display_data(j)
                    labelR, textR = potctrl.get_display_data(j+1)
                    tb_disp.curr_param_pair = j
                    tb_disp.update_param_pairs(labelL, textL, labelR, textR)
        elif bank_idx == 1:   # note steps
            for i in range(8):
                if (pot_changes >> i) & 1:
                    print("note:", i, potctrl.get_display_data(i))

        
    #time.sleep(0.1)

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
            #tb_disp.stop()
            # testing out save/load params
            #s = ParamSet.dump(param_set)  # dump patch to string as JSON
            #print(s)
            #ParamSet.load(s)   # load patch in as JSON
            
        else:
            #tb_disp.start()
            sequencer.start()

    # handle touch
    touch_events = get_touch_events()
    for touch in touch_events:
        i = touch.key_number
        if touch.pressed:
            n = Pads.PAD_TO_LED.index(i)
            print("touch", i, n)
            if i in Pads.STEP_PADS:
                if sequencer.playing:
                    transpose = n-8    # chromatic and lame
                    sequencer.transpose = transpose
                else:
                    tbsynth.note_on(36 + n)  # note_off automatically haappens
            elif i == Pads.PAD_RSLIDE_C:  #
                seq_num = (sequencer.seq_num + 1) % len(sequencer.seqs)
                sequencer.seq_num = seq_num
                print("** changing sequence!", seq_num)



