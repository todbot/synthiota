import time
import random
import board
import audiobusio, audiomixer, synthio

i2s_bck_pin = board.GP20
i2s_lck_pin = board.GP21
i2s_dat_pin = board.GP22
i2c_scl_pin   = board.GP19
i2c_sda_pin   = board.GP18
uart_rx_pin   = board.GP17
uart_tx_pin   = board.GP16


SAMPLE_RATE = 44100
CHANNEL_COUNT = 2
BUFFER_SIZE = 2048


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
synth.envelope = synthio.Envelope(attack_time=0.05, attack_level=0.8, release_time=0.6)

while True:
   n = random.randint(32,60) 
   print("boop:",n)
   synth.press( n )
   time.sleep(0.3)
   synth.release(n) 
   time.sleep(0.5)


