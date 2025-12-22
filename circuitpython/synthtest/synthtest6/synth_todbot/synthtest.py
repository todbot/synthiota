"""
    Todbot Test Synth --
    Features:
    - two-voice oscillator with selectable waveforms and detune
    - filter with AHR filter envelope
    - pitch envelope with AR envelope
    . tremolo and vibrato
    . change sound via patches
"""

import ulab.numpy as np
import synthio

from synth_todbot.patch import Patch
import synth_todbot.waves
        
class Note:
    def __init__(self, synth, patch):
        self.synth = synth
        self.p = patch
        self.wave = synth_todbot.waves.wave_by_name(patch.wave)
        
        self._filt_pos = synthio.LFO(once=True, rate=1, waveform=np.array((0,32767), dtype=np.int16))
        self._filt_env = synthio.Math(synthio.MathOperation.CONSTRAINED_LERP, 500, 2000, self._filt_pos)  # FIXME 
        self._pitch_pos = synthio.LFO(once=True, rate=1, waveform=np.array((0,32767), dtype=np.int16))
        self._pitch_env = synthio.Math(synthio.MathOperation.CONSTRAINED_LERP, 500, 2000, self._pitch_pos)
        self._filter = synthio.Biquad(mode=synthio.FilterMode.LOW_PASS,
                                      frequency=self._filt_env, Q=self.p.filt_q)

        self.note1 = None
        self.note2 = None

    def press(self, midi_note, velocity=127):
        p = self.p
        # set up the filter envelope
        self._filt_env.b = p.filt_freq   # max filter freq
        self._filt_env.a = p.filt_freq * (1 - p.filt_env_depth)  # min filter freq
        self._filt_pos.rate = 1 / (p.filt_attack_time+0.001)
        self._filt_pos.retrigger()
        
        print("amp_attack_time:", p.amp_attack_time)
        amp_env = synthio.Envelope(attack_time = p.amp_attack_time,
                                   decay_time = p.amp_decay_time,
                                   sustain_level = p.amp_sustain_level,
                                   release_time = p.amp_release_time )
                                   
        self.note1 = synthio.Note( synthio.midi_to_hz(midi_note),
                                   waveform = self.wave,
                                   envelope = amp_env,
                                   filter = self._filter )
        self.note2 = synthio.Note( synthio.midi_to_hz(midi_note * (1+p.detune)),
                                   waveform = self.wave,
                                   envelope=amp_env,
                                   filter = self._filter)
        self.synth.press((self.note1, self.note2))

    def release(self):
        # p = self.p
        # self._filt_env.a = self._filt_env.b
        # self._filt_env.b = p.filt_freq * (1 - p.filt_env_depth)  # min filter freq
        # self._filt_pos.rate = 1 / (p.filt_release_time+0.001)
        # self._filt_pos.retrigger()
        self.synth.release((self.note1, self.note2))


        
class Synth:
    """"""
    def __init__(self, sample_rate=22050, channel_count=1):
        self.synth = synthio.Synthesizer(sample_rate=sample_rate,
                                         channel_count=channel_count)
        self.patch = Patch()  # default patch
        self.notes_pressed = {}

    # def __getattr__(self, attr):
    #     print("Synth getattr", attr)
    #     return getattr(self.p, attr)
    
    def __setattr__(self, attr, val):
        print("Synth setattr", attr, val)
        setattr(self.p, val)

    def note_on(self, midi_note: int, velocity=100):

        # set up the pitch envelope
        # ...
        
        # trigger the notes
        self.note_off(midi_note)  # if already sounding
        note = Note(self.synth, self.patch)  # eventually have a list of these pre-loaded
        note.press(midi_note, velocity)
        self.notes_pressed[midi_note] = note

    def note_off(self, midi_note: int, velocity=0):
        note = self.notes_pressed.get(midi_note, None)
        if note:
            note.release()

    def bend(self, bend):
        pass

    @property 
    def filt_freq(self):
        pass
    
    @filt_freq.setter
    def filt_freq(self,f):
        pass
        
    #def update_from_patch(self, patch):
        #self.patch = patch
        
        # waveform settings
        #self.wave = synth.waves.wave_by_name.get(self.p['wave'], 'SAW')
        #
