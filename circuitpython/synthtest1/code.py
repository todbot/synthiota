""""
synthiota synth1
Sep 2025 todbot / Tod Kurt

+-------------------------+
|                         |
|                         |
|                         |
|                         |
|                         |
|                         |
+-------------------------+


"""
    
import time
import rainbowio

from synth_setup_synthiota import (display, leds, mpr121s,
                                   get_touched, touch_to_led, step_pads,
                                   update_pots, pot_vals,
                                   encoder, encoder_sw,
                                   mixer)

from synthiota_gui import (setup_display, update_page, update_page_vals)

from synth_todbot.paramset import ParamSet, Param
from synth_todbot.synth1 import Synth

leds.fill(0)

params = [
    # page 1
    #      name     val,  min,  max, str,  synth.attr name
    Param("FREQ", 3000, 100, 5000, "%4d", 'filt_freq'),
    Param('ENV',  0.5,  0.0, 1.0, "%.2f", 'filt_env_depth'), 
    Param("RESQ", 1.0,  0.5, 4.0, "%.2f", 'filt_q'),
    Param('FDEC', 0.75, 0.0, 1.0, "%.2f", 'filt_decay'),
    Param("AATK", 0.01, 0, 3, "%4d", 'amp_attack_time'),
    Param("ARLS", 0.5,  0, 3, "%4d", 'amp_release_time'),
    Param("FATK", 0,    0, 3, "%f", 'filt_attack_time'),
    Param("FRLS", 0,    0, 3, "%f", 'filt_release_time'),

    # page 2
    Param("wav0",  1.0, 0.5, 4.0, "%.2f", None),
    Param('wav1', 0.75,  0.0, 1.0, "%.2f", None),
    Param("mod0",  1.0, 0.5, 4.0, "%.2f", None),
    Param('mod1', 0.75,  0.0, 1.0, "%.2f", None),
    Param("wav2",  1.0, 0.5, 4.0, "%.2f", None),
    Param('wav3', 0.75,  0.0, 1.0, "%.2f", None),
    Param("mod2",  1.0, 0.5, 4.0, "%.2f", None),
    Param('mod3', 0.75,  0.0, 1.0, "%.2f", None),

    # # page 3
    # Param("bpm", 100, 50, 180, "%3d", None),
    # Param("trans", 0, -4, 40, "%2d", None),
    # Param("vol", 100, 0, 100, "%2d", None),
    # Param("a", 0, 0, 10, "%2d", None),
    # Param("b", 0, 0, 10, "%2d", None),
    # Param("c", 0, 0, 10, "%2d", None),
    # Param("d", 0, 0, 10, "%2d", None),
    # Param("e", 0, 0, 10, "%2d", None),
]

param_set = ParamSet(params, num_knobs=8, knob_smooth=0.125)

synth = Synth(mixer.sample_rate, mixer.channel_count, )

mixer.voice[0].play(synth.synth)

dim_by = 15
last_time = 0
last_step_time = 0
last_encoder_pos = encoder.position
stepi=0

num_pages = param_set.nknobsets

pagei = 0
playing = False
pot_vals_normalized = [v/65535 for v in pot_vals]

setup_display(display, param_set)
update_page()
update_page_vals(params)

touched = get_touched()

while True:

    leds[:] = [[max(i-dim_by,0) for i in l] for l in leds] # dim all by (dim_by,dim_by,dim_by)

    last_touched = touched
    touched = get_touched()
    update_pots()
    pot_vals_normalized[:] = [v/65535 for v in pot_vals]

    param_set.update_knobs(pot_vals_normalized)
    #param_set.apply_knobset(synth)
    param_set.apply_knobset(synth.patch)

    if key := encoder_sw.events.get():
        if key.pressed:
            print("encoder button!",key)
            playing = not playing

    delta_pos = encoder.position - last_encoder_pos
    last_encoder_pos = encoder.position
    if delta_pos:
        oldi = pagei
        pagei = (pagei - delta_pos) % num_pages
        param_set.idx = pagei
        update_page(pagei, oldi)

    # display update
    if time.monotonic() - last_step_time > 0.05:
        last_step_time = time.monotonic()
        update_page_vals(params)

        if playing:
            # fakey sequencer thing
            leds[16+stepi] = 0
            stepi = (stepi+1) %8
            leds[16+stepi] = 0x666666
      
      
    if time.monotonic() - last_time > 0.5:
        last_time = time.monotonic()
      
        leds[-1] = 0xff0000   # right top LED 
        leds[-2] = 0x00ff00   # middle top LED
        leds[-3] = 0x0000ff   # left top LED

        # why was I printing this? 
        #for i in range(8,12):
        #    print(i, mpr121s[1].baseline_data(i))
      
        print(''.join(["%d" % t for t in touched]), [v//256 for v in pot_vals], encoder.position)
        #synth.release_all()

      
    for i in range(len(touched)):  # enumerate(touched):
        t = touched[i]
        lt = last_touched[i]
        if t and not lt:
            print("press!", i)
            ledn = touch_to_led.index(i)
            leds[ledn] = rainbowio.colorwheel(time.monotonic()*50)
            if i in step_pads:
                notenum = 36 + ledn
                synth.note_on(notenum)
        elif not t and lt:
            print("release!", i)
            ledn = touch_to_led.index(i)
            if i in step_pads:
                notenum = 36 + ledn
                synth.note_off(notenum)
            
    time.sleep(0.01)




