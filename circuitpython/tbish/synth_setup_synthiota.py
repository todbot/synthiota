
import array
import board
import digitalio
import analogio
import rotaryio
import keypad
import busio
import displayio
import fourwire
import rainbowio
import neopixel
import adafruit_mpr121
import adafruit_displayio_sh1106

import audiobusio, audiomixer, synthio
from micropython import const

sda_pin = board.GP2
scl_pin = board.GP3
led_pin = board.GP18

disp_sclk = board.GP10
disp_mosi = board.GP11
disp_res  = board.GP12
disp_dc   = board.GP13

pot_sel_pins = (board.GP9, board.GP8, board.GP7)
pot_pin   = board.GP26

encoderA_pin  = board.GP27
encoderB_pin  = board.GP28
encoderSW_pin = board.GP19

uart_rx_pin   = board.GP17
uart_tx_pin   = board.GP16
i2s_bck_pin   = board.GP20
i2s_lck_pin   = board.GP21
i2s_dat_pin   = board.GP22

#SAMPLE_RATE = 44100
SAMPLE_RATE = 22050
CHANNEL_COUNT = 2
BUFFER_SIZE = 4096

dw, dh = 132,64 
mpr121_addrs = (0x5a, 0x5b)
num_leds = 8 * 3 + 3
num_pots = 8
num_pads = 8 * 3

# hook up external stereo I2S audio DAC board
audio = audiobusio.I2SOut(bit_clock=i2s_bck_pin, word_select=i2s_lck_pin, data=i2s_dat_pin)

# add a mixer to give us a buffer
mixer = audiomixer.Mixer(sample_rate=SAMPLE_RATE,
                         channel_count=CHANNEL_COUNT,
                         buffer_size=BUFFER_SIZE)

# make the actual synthesizer
synth = synthio.Synthesizer(sample_rate=SAMPLE_RATE, channel_count=CHANNEL_COUNT)

# plug the mixer into the audio output
audio.play(mixer)

# plug the synth into the first 'voice' of the mixer
mixer.voice[0].play(synth)
mixer.voice[0].level = 0.25  # 0.25 usually better for headphones, 1.0 for line-in

# more on this later, but makes it sound nicer
synth.envelope = synthio.Envelope(attack_time=0.0, attack_level=0.5, decay_time=0.35, sustain_level=0)

uart = busio.UART(rx=uart_rx_pin, tx=uart_tx_pin, baudrate=31250, timeout=0.001)

# i2c for MPR121 touch sensors
i2c = busio.I2C(scl=scl_pin, sda=sda_pin, frequency=400_000)
mpr121s = [adafruit_mpr121.MPR121(i2c, address=a) for a in mpr121_addrs]
# fix little buttons up top? 
#mpr121s[1]._write_register_byte(adafruit_mpr121.MPR121_CONFIG1, 0x20)  # default, 2*16uA charge current? 
mpr121s[1]._write_register_byte(adafruit_mpr121.MPR121_CONFIG1, 0x10)  # 

displayio.release_displays()
spi = busio.SPI(clock=disp_sclk, MOSI=disp_mosi)
display_bus = fourwire.FourWire(spi, command = disp_dc, reset=disp_res, baudrate=24_000_000)
display = adafruit_displayio_sh1106.SH1106(display_bus, width=dw, height=dh, colstart=3)

leds = neopixel.NeoPixel(led_pin, num_leds, brightness=0.1)
leds.fill(0x110011)

encoder = rotaryio.IncrementalEncoder(pin_a=encoderA_pin, pin_b=encoderB_pin, divisor=4)
encoder_sw = keypad.Keys((encoderSW_pin,), value_when_pressed=False, pull=True)

touched = [0] * num_pads
last_touched = [0] * num_pads

pot = analogio.AnalogIn(pot_pin)
pot_vals = array.array('H', [0] * num_pots)  # AnalogIn is always 16-bit
#pot_vals = [0] * num_pots
pot_sels = []   # digitalinout pins controlling analog mux hooked to pots

for p in pot_sel_pins:
    pot_sel = digitalio.DigitalInOut(p)
    pot_sel.switch_to_output(value=False)
    pot_sels.append(pot_sel)
   
def select_pot(n):
    """Set the analog mux to a particular pot channel"""
    for b in range(3):
        pot_sels[b].value = n & (1<<b) != 0
        
def update_pots_nosmooth():
    """Read all the pots via the mux. No smoothing is done."""
    for i in range(num_pots):
        select_pot(i)
        pot_vals[i] = pot.value
    return pot_vals

smooth_shift = 3
def update_pots():
    """Read all the pots via the mux. Smoothing is done via integer exponential moving average."""
    for i in range(num_pots):
        select_pot(i)
        raw = pot.value
        pot_vals[i] += (raw - pot_vals[i]) >> smooth_shift  # integer EMA
    return pot_vals

for i in range(50):
    update_pots()   # prime the accumulators

def get_touched():
    """Read all touchpads return list of booleans."""
    touched0 = mpr121s[0].touched_pins
    touched1 = mpr121s[1].touched_pins
    touched = touched0 + touched1
    return touched

def get_touch_events():
    """Check the touch inputs, return keypad-like Events"""
    global touched, last_touched
    last_touched = touched
    touched = get_touched()
    
    events = []
    for i,t in enumerate(touched):
        lt = last_touched[i]
        if t and not lt:      # pad pressed event
            events.append(keypad.Event(i,True))
        elif not t and lt:    # pad released event
            events.append(keypad.Event(i,False))
    return events

      
class Pads:
    # map touch id to led index
    PAD_TO_LED = (7,6,5,4,3,2,1,0, 8,9,10,11, 18,17,16,15, 23,22,21, 20, 19, 12,13,14)

    # map step pads to an index
    STEP_PADS = (7,6,5,4,3,2,1,0, 8,9,10,11,18,17,16,15)
    
    # pad defs
    PAD_OCT_DOWN = const(19)
    PAD_OCT_UP = 20
    
    PAD_RSLIDE_C = 14
    PAD_RSLIDE_B = 13
    PAD_RSLIDE_A = 12
    
    PAD_LSLIDE_C = 21
    PAD_LSLIDE_B = 22
    PAD_LSLIDE_A = 23

    # hmm need a better place for this
    LED_EDIT =  24
    LED_MODE =  25
    LED_PLAY =  26
    

