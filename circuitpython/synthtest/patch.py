
class Patch:
    def __init__(self):
        self.wave = 'SAW'
        self.detune = 1.0
        self.glide_time = 0
        
        self.amp_attack_time = 0.01
        self.amp_decay_time = 0.01
        self.amp_release_time = 0.5
        self.amp_sustain_level = 0.8
        self.amp_attack_level = 1.0
        
        self.filt_freq = 4000
        self.filt_q = 0.7
        self.filt_env_depth = 0.5
        self.filt_attack_time = 0.3
        self.filt_release_time = 0.5
