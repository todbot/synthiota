# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT
"""
`tbish_sequencer`
================================================================================

TB-303-like sequencer for CircuitPtyhon synthio. Designed for tbish_synth.
 
12 May 2025 - @todbot / Tod Kurt

Implementation Notes
--------------------

A TB-303-style step sequencer.

Sequences are represented as lists of lists. The innermost list
is a list of MIDI note numbers with a matching list of MIDI velocities,
then a list of accents, then a list of slides
e.g.::

  seq = [[24,  36, 48, 36,  48, 48+7, 36, 48],    # notes: midi notenum
         [127, 80, 80, 80,  127,  80, 80, 80],    # vels: 100+ = accent, 
         [0,    0,  0,  0,   0,   1,  0,  1]],    # slides: 1 = slide


"""



import time

class TBishSequencer:
    def __init__(self, tbsynth, steps_per_beat=4, bpm=120, seqs=None):
        self.tb = tbsynth
        self.seqs = seqs
        self._steps_per_beat = steps_per_beat   # 4 = 16th note, 2 = 8th note, 1 = quarter note
        self.bpm = bpm
        self.gate_amount = 0.75  # traditional 303 gate length
        self.next_step_time = 0
        self.gate_off_time = 0
        self.midi_note = 0   # current note being played or 0 for none
        self.seqs = seqs
        self.seq_num = 0
        self.seq_len = len(seqs[0][0])
        self.transpose = 0
        self.i = 0  # step number
        self.playing = False
        self.on_step_callback = None   # callback is func(step, steps_per_beat, seq_len)

    @property
    def steps_per_beat(self):
        return self._steps_per_beat
    
    @steps_per_beat.setter
    def steps_per_beat(self, s):
        self._steps_per_beat = s
        self._secs_per_step = 60 / self._bpm / self._steps_per_beat       
    
    @property
    def bpm(self):
        return self._bpm
    
    @bpm.setter
    def bpm(self, b):
        self._bpm = b
        self._secs_per_step = 60 / self._bpm / self._steps_per_beat

    def start(self):
        self.playing = True
        self.i = 0
        self.next_step_time = time.monotonic()

    def stop(self):
        self.playing = False
        self.tb.note_off(self.midi_note)

    def update(self):
        
        now = time.monotonic()
        i = self.i
        seq_len = self.seq_len
        
        # turn off note (not really a TB-303 thing, but a MIDI thing)
        if self.gate_off_time and self.gate_off_time - now <= 0:
            self.gate_off_time = 0
            self.tb.note_off(self.midi_note)

        # time for next step? 
        dt = (self.next_step_time - now)
        if dt <= 0:
            self.next_step_time = now + self._secs_per_step + dt  
            # add dt delta to attempt to make up for display hosing us
            
            if not self.playing:
                return

            if self.on_step_callback:  # and (self.i % self._steps_per_beat)==0:
                self.on_step_callback(i, self.steps_per_beat, seq_len)

            seq = self.seqs[self.seq_num]
            midi_note = seq[0][i]
            vel       = seq[1][i]
            slide     = seq[2][i]
            if midi_note != 0:    # midi_note == 0 = rest
                midi_note += self.transpose
                self.tb.secs_per_step = self._secs_per_step * 1.0
                #self.tb.note_on(midi_note, vel)
                self.tb.note_on_step(midi_note, vel, slide)
                self.gate_off_time = time.monotonic() + self._secs_per_step * self.gate_amount

            self.i = (i+1) % seq_len
            self.midi_note = midi_note
        
            print("tbish_seq: step %d note: %d vel:%3d" % (i, midi_note, vel),
                  int(self._secs_per_step*1000), int(dt*1000))

