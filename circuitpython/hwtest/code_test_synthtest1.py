    
import time
import rainbowio

from synth_setup_synthiota import (display, leds,
                                   get_touched, touch_to_led,
                                   update_pots, pot_vals,
                                   synth)

dim_by = 15
last_time = 0
while True:
   leds[:] = [[max(i-dim_by,0) for i in l] for l in leds] # dim all by (dim_by,dim_by,dim_by)
   touched = get_touched()
   
   if time.monotonic() - last_time > 0.5:
      last_time = time.monotonic()
      leds[-1] = 0xff0000 
      leds[-2] = 0x00ff00
      leds[-3] = 0x0000ff
      update_pots()
      print(''.join(["%d" % t for t in touched]), [v//256 for v in pot_vals])
      synth.release_all()
      
   for i,v in enumerate(touched):
      if v:
         ledn = touch_to_led.index(i)
         #print(i,ledn)
         leds[ledn] = rainbowio.colorwheel(time.monotonic()*50)
         notenum = 36 + ledn
         synth.press(notenum)
   time.sleep(0.01)

