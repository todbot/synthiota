
#import synthio
try:
    import ulab.numpy as np
except:
    import numpy as np
    
# oscillator waveforms
def wave_saw(volume=32767, num=128):
    return np.linspace(volume, -volume, num=num, dtype=np.int16)

def wave_sine(volume=32767, num=128):
    return np.array(np.sin(np.linspace(0, 2 * np.pi, num, endpoint=False)) * volume, dtype=np.int16)

def wave_noise(volume=32767, num=128):
    return np.array([random.randint(-volume, volume) for i in range(num)], dtype=np.int16)

# def make_lfo(rate=1, once=False):
#     return synthio.LFO(once=once, rate=rate, waveform=np.array((0,32767), dtype=np.int16))
    
waves = {
    'SAW': wave_saw,
    'SINE': wave_sine,
    'NOISE': wave_noise,
}
    
def wave_by_name(name, volume=30000, num=128):
    return waves[name](volume, num)

