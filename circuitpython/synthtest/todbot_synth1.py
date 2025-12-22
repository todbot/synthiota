"""
    TodbotSynth --
    Features:
    - two-voice oscillator with selectable waveforms and detune
    - filter with AHR filter envelope
    - pitch envelope with AR envelope
    - tremolo and vibrato
    - change sound via patches
"""

import ulab.numpy as np
import synthio

import waves
from patch import Patch
        
class Note:
    def __init__(self, synth, patch):
        self.synth = synth
        self.p = patch
        self._filt_pos = synthio.LFO(once=True, rate=1, waveform=np.array((0,32767), dtype=np.int16))
        self._filt_env = synthio.Math(synthio.MathOperation.CONSTRAINED_LERP, 500, 2000, self._filt_pos)
        self._pitch_pos = synthio.LFO(once=True, rate=1, waveform=np.array((0,32767), dtype=np.int16))
        self._pitch_env = synthio.Math(synthio.MathOperation.CONSTRAINED_LERP, 500, 2000, self._pitch_pos)
        self.note1 = None
        self.note2 = None

    def press(self, midi_note, velocity=127):
        p = self.p
        # set up the filter envelope
        self._filt_env.b = p.filt_freq   # max filter freq
        self._filt_env.a = p.filt_freq * (1 - p.filt_env_depth)  # min filter freq
        self._filt_pos.rate = 1 / p.filt_attack_time
        self._filt_pos.retrigger()
        
        amp_env = synthio.Envelope(attack_time = p.amp_attack_time,
                                   decay_time = p.amp_decay_time,
                                   sustain_level = p.amp_sustain_level,
                                   release_time = p.amp_release_time )
                                   
        self.note1 = synthio.Note( synthio.midi_to_hz(midi_note),
                                   envelope=amp_env,
                                   filter = self._filt_env )
        self.note2 = synthio.Note( syntio.midi_to_hz(midi_note * p.detune),
                                   envelope=amp_env,
                                   filter=filt_env)

    def release(self):
        self.synth.release((self.note1, self.note2))

        
class Synth:
    """"""
    def __init__(self, synth: synthio.Synthesizer, patch: Patch):
        self.synth = synth
        self.p = patch
        self.notes_pressed = {}

    def __getattr__(self, attr):
        return getattar(self.p, attr)
    
    def __setattr__(self, attr, val):
        setattr(self.p, val)

    def press(self, midi_note: int, velocity=100):

        # set up the pitch envelope
        # ...
        
        # trigger the notes
        self.release(midi_note)  # if already sounding
        note = Note(synth, patch)
        note.press(midi_note, velocity)
        self.notes_pressed[midi_note] = (note1,note2)

    def release(self, midi_note: int, velocity=0):
        pass

    def bend(self, bend):
        pass
    
    def update_from_patch(self, patch):
        self.p = patch
        
        # waveform settings
        self.wave = waves.wave_by_name.get(self.p['wave'], 'SAW')
        
