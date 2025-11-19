import time
import random
import board
import digitalio
import analogio
import busio
import displayio
import fourwire
import rainbowio
import neopixel
import adafruit_mpr121
import adafruit_displayio_sh1106

disp_sclk = board.GP10
disp_mosi = board.GP11
disp_res  = board.GP12
disp_dc   = board.GP13

sda_pin = board.GP2
scl_pin = board.GP3
led_pin = board.GP18

pot_pin = board.GP26
pot_sel_pins = (board.GP9, board.GP8, board.GP7)

dw,dh = 132,64
num_leds = 8 * 3 + 3
num_pots = 8

i2c = busio.I2C(scl=scl_pin, sda=sda_pin, frequency=400_000)

displayio.release_displays()
spi = busio.SPI(clock=disp_sclk, MOSI=disp_mosi)
display_bus = fourwire.FourWire(spi, command = disp_dc, reset=disp_res)
display = adafruit_displayio_sh1106.SH1106(display_bus, width=dw, height=dh, colstart=3)

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
   time.sleep(0.005)
   

mpr121_addrs = (0x5a, 0x5b)
mpr121s = [adafruit_mpr121.MPR121(i2c, address=a) for a in mpr121_addrs]

pot_vals = [0] * num_pots
pot = analogio.AnalogIn(pot_pin)
pot_sels = []
for p in pot_sel_pins:
   pot_sel = digitalio.DigitalInOut(p)
   pot_sel.switch_to_output(value=False)
   pot_sels.append(pot_sel)
   
def select_pot(n):
   for b in range(3):
      pot_sels[b].value = n & (1<<b) != 0

# map touch id to led index
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
      leds[-1] = 0xff0000 
      leds[-2] = 0x00ff00
      leds[-3] = 0x0000ff
      for i in range(num_pots):
         select_pot(i)
         pot_vals[i] = pot.value
      print(''.join(["%d" % t for t in touched]), [v//256 for v in pot_vals])
      
   for i,v in enumerate(touched):
      if v:
         print("touch:",i, end=' ')
         ledn = touch_to_led.index(i)
         print("ledn:", ledn)
         leds[ledn] = rainbowio.colorwheel(time.monotonic()*50)
         
   time.sleep(0.01)
