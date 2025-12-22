# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT

""""
synthiota synthtest
Sep 2025 - @todbot / Tod Kurt

NOTE: a bunch of hacks to let me play around with UI ideas quickly

"""
import sys
if sys.platform == 'RP2040':
    print("Pico1: bumping to 250 MHz")
    # note this must come before anything else, or things get weird
    import microcontroller
    microcontroller.cpu.frequency = 250_000_000  # ~100 mA for RP2040 synthiota1

import time
import rainbowio
import tmidi

from synth_todbot.paramset import ParamSet, Param
from synth_todbot.synthtest import Synth
from synth_todbot.tinysequencer import TinySequencer

from synth_setup_synthiota import (display, leds, uart, mpr121s,
                                   get_touched, update_pots, pot_vals,
                                   encoder, encoder_sw,
                                   mixer, Pads)
from synthtest_gui import SynthTestGUI

bpm = 120
steps_per_beat = 2
octave = 3

notes_default = [60, 36, 36, 36,  48, 48, 43, 43]
# notes are the sequence, list of [note, velocity, gate lenght]
note_steps = [ [n, 100, 0.25] for n in notes_default]

params = [
    # page 1
    #      name     val,  min,  max, str,  synth.attr name
    Param("Freq", 3000, 100, 5000, "%4d", 'filt_freq'),
    Param('Env',  0.5,  0.0, 1.0, "%.2f", 'filt_env_depth'), 
    Param("ResQ", 1.0,  0.5, 4.0, "%.2f", 'filt_q'),
    Param('Fdec', 0.75, 0.0, 1.0, "%.2f", 'filt_release_time'),
    Param("Aatk", 0.01, 0, 3, "%4d", 'amp_attack_time'),
    Param("Arls", 0.2,  0, 3, "%4d", 'amp_release_time'),
    Param("Fatk", 0,    0, 3, "%f", 'filt_attack_time'),
    Param("Detu", 0.001, 0.000, 0.008, "%f", 'detune'),

    # # page 2
    # Param("wav0",  1.0, 0.5, 4.0, "%.2f", None),
    # Param('wav1', 0.75,  0.0, 1.0, "%.2f", None),
    # Param("mod0",  1.0, 0.5, 4.0, "%.2f", None),
    # Param('mod1', 0.75,  0.0, 1.0, "%.2f", None),
    # Param("wav2",  1.0, 0.5, 4.0, "%.2f", None),
    # Param('wav3', 0.75,  0.0, 1.0, "%.2f", None),
    # Param("mod2",  1.0, 0.5, 4.0, "%.2f", None),
    # Param('mod3', 0.75,  0.0, 1.0, "%.2f", None),

]

param_set = ParamSet(params, num_knobs=8, knob_smooth=0.125, knob_mode=1)

#num_pages = 2   # param_set.nknobsets 
#pagei = 0  # which page of params we're looking at

gui = SynthTestGUI(display, num_pages=2, param_set=param_set, note_steps=note_steps)

# make a synth and start it
synth = Synth(mixer.sample_rate, mixer.channel_count, )
mixer.voice[0].play(synth.synth)

# set up midi ports
midi_uart = tmidi.MIDI(midi_in=uart, midi_out=uart)

curr_step = 0
def note_on(notenum, vel):
    print("note_on: ", notenum, vel)
    synth.note_on(notenum,vel)
    leds[curr_step] = 0x333333  
    
def note_off(notenum, vel):
    print("note_off:", notenum, vel)
    synth.note_off(notenum,vel)
    leds[curr_step] = 0x000000

def step(stepnum, steps_per_beat):
    global curr_step
    curr_step = stepnum
    print("-------- step:", stepnum)
    # update display here too, in the "shadow" of a played note
    gui.update()
    
seq = TinySequencer(bpm=bpm, steps_per_beat=steps_per_beat, notes = note_steps,
                    note_on = note_on, note_off = note_off)
seq.step_cb = step

leds.fill(0)  # indicate startup is done

dim_by = 10  # led fader
last_debug_time = 0
last_encoder_pos = encoder.position
touched = get_touched()
pressed_step = None  # index into note_steps
pot_vals_normalized = [0] * param_set.nknobs

#
# IDEA: a "KnobScaler" that works entirely in 0-65535 ints
#       but works like param_scaler
    
while True:
    #time.sleep(0.001)  #
    
    # run sequencer task
    seq.update()
    
    # fade leds
    leds[:] = [[max(i-dim_by,0) for i in l] for l in leds] # dim all by (dim_by,dim_by,dim_by)

    # update input state
    last_touched = touched
    touched = get_touched()
    
    update_pots()
    pot_vals_normalized[:] = [v/65535 for v in pot_vals]

    param_set.update_knobs(pot_vals_normalized)
    param_set.apply_knobset(synth.patch)

    # handle encoder push switch
    if key := encoder_sw.events.get():
        if key.pressed:
            print("encoder button!",key)
            if seq.playing:
                seq.stop()
            else:
                seq.start()
                
    # handle encoder
    delta_pos = last_encoder_pos - encoder.position 
    last_encoder_pos = encoder.position
    if delta_pos:
        print("delta pos:", delta_pos) #  pressed_step)
        if pressed_step is not None:
            print("note_steps:", pressed_step, note_steps)
            note_steps[pressed_step][0] += delta_pos
            print("note_step:", pressed_step, note_steps[pressed_step][0])
            gui.update_steps()
        else:
            if delta_pos < 0:
                gui.set_page(0)
            else:
                gui.set_page(1)

    # handle touch pads
    for i,t in enumerate(touched):
        lt = last_touched[i]
        
        if t and not lt:       # press
            n = Pads.PAD_TO_LED.index(i)
            print("press!", i, n)
            leds[n] = rainbowio.colorwheel(time.monotonic()*50)
            if i in Pads.STEP_PADS:
                notenum = (octave+1)*12 + n
                synth.note_on(notenum)
                pressed_step = n
                gui.set_note_info("%d" % notenum)
            elif i == Pads.PAD_OCT_UP:
                octave = min(5, (octave+1))
            elif i == Pads.PAD_OCT_DOWN:
                octave = max(-1, (octave-1))
            elif i == Pads.PAD_RSLIDE_C:   # tempo up
                bpm += 1
            elif i == Pads.PAD_RSLIDE_A:   # tempo down
                bpm -= 1
            gui.set_oct_bpm(octave,bpm)

        elif not t and lt:     # release
            n = Pads.PAD_TO_LED.index(i)
            print("release!", i, n)
            if i in Pads.STEP_PADS:
                notenum = (octave+1)*12 + n
                synth.note_off(notenum)
                pressed_step = None
                gui.set_note_info("--")

    while msg := midi_uart.receive():
        print("midi:", msg)
        if msg.type == tmidi.NOTE_ON and msg.velocity > 0:
            synth.note_on(msg.note, msg.velocity)
        if msg.type == tmidi.NOTE_OFF or msg.type == tmidi.NOTE_ON and msg.velocity ==0:
            synth.note_off(msg.note, msg.velocity)

    now = time.monotonic()
    # debug
    if now - last_debug_time > (60/bpm):
        last_debug_time = now

        gui.update()  # hack
        
        leds[-1] = 0xff0000   # right top LED 
        leds[-2] = 0x00ff00   # middle top LED
        leds[-3] = 0x0000ff   # left top LED
        
        #print(''.join(["%d" % t for t in touched]), [v//256 for v in pot_vals], encoder.position)
        print("step_secs: %.2f" % seq._step_secs)

    #time.sleep(0.01)




