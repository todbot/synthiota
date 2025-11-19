import time
import random
import board
import busio
import rainbowio
import neopixel
import adafruit_mpr121

sda_pin = board.GP2
scl_pin = board.GP3
led_pin = board.GP18
num_leds = 8 * 3 + 3

i2c = busio.I2C(scl=scl_pin, sda=sda_pin, frequency=400_000)

leds = neopixel.NeoPixel(led_pin, num_leds, brightness=0.1)
leds.fill(0xff00ff)

time.sleep(0.3)
print("i2c scan:")
i2c.try_lock()
print("i2c devices:", ["%02x" % a for a in i2c.scan()])
i2c.unlock()

leds.fill(0)
for i in range(num_leds):
   leds[i] = 0xff00ff
   time.sleep(0.01)
   leds[i] = 0
   time.sleep(0.01)
   

mpr121_addrs = (0x5a, 0x5b)
mpr121s = [adafruit_mpr121.MPR121(i2c, address=a) for a in mpr121_addrs]

touch_to_led = (7,6,5,4,3,2,1,0, 8,9,10,11, 18,17,16,15, 23,22,21, 20, 19, 12,13,14)

dim_by = 15
last_time = 0
while True:
   leds[:] = [[max(i-dim_by,0) for i in l] for l in leds] # dim all by (dim_by,dim_by,dim_by)
   
   touched0 = mpr121s[0].touched_pins
   touched1 = mpr121s[1].touched_pins
   #print(''.join(["%d" % t for t in touched0]), ''.join(["%d" % t for t in touched1]) )
   touched = touched0 + touched1
   
   if time.monotonic() - last_time > 0.5:
      last_time = time.monotonic()
      print(''.join(["%d" % t for t in touched]))
      leds[-1] = 0xff0000 
      leds[-2] = 0x00ff00
      leds[-3] = 0x0000ff
      
   for i,v in enumerate(touched):
      if v:
         print("touch:",i, end=' ')
         ledn = touch_to_led.index(i)
         print("ledn:", ledn)
         leds[ledn] = rainbowio.colorwheel(time.monotonic()*50)
         
   time.sleep(0.01)
