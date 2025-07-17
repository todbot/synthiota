import time
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

time.sleep(1)
print("i2c scan:")
i2c.try_lock()
print("i2c devices:", ["%02x" % a for a in i2c.scan()])
i2c.unlock()

leds.fill(0)

mpr121_addrs = (0x5a, 0x5b)
mpr121s = [adafruit_mpr121.MPR121(i2c, address=a) for a in mpr121_addrs]

while True:
   
   touched0 = mpr121s[0].touched_pins
   touched1 = mpr121s[1].touched_pins
   
   print(''.join(["%d" % t for t in touched0]), ''.join(["%d" % t for t in touched1]) )
   
   time.sleep(0.1)
