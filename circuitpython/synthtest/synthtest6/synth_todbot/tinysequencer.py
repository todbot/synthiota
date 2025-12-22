# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT

import time


class TinySequencer:
    def __init__(self, bpm=120, steps_per_beat=4, notes=None, note_on=None, note_off=None):
        # notes: list of tuples (notenum, velocity, gate)
        # bpm : beats per minute
        # steps_per_beat: 4 = 16th note, 2 = 8th note, 1 = quarter note
        self._steps_per_beat = steps_per_beat
        self.bpm = bpm
        self.next_step_time = 0
        self.gate_off_time = 0
        self.notes = notes
        self.num_steps = len(notes)
        self.i = 0  # which step we're on
        self.playing = False
        self.notenum = 0
        self.step_cb = None  # FIXME
        self.note_on_cb = note_on
        self.note_off_cb = note_off

    @property
    def steps_per_beat(self):
        return self._steps_per_beat
    
    @steps_per_beat.setter
    def steps_per_beat(self, s):
        self._steps_per_beat = s
        self._step_secs = 60 / self._bpm / self._steps_per_beat       
    
    @property
    def bpm(self):
        return self._bpm
    
    @bpm.setter
    def bpm(self, b):
        self._bpm = b
        self._step_secs = 60 / self._bpm / self._steps_per_beat

    def start(self):
        self.playing = True
        self.i = 0
        self.next_step_time = time.monotonic()

    def stop(self):
        self.playing = False
        self.note_off_cb(self.notenum, 0)

    def update(self):
        now = time.monotonic()
        
        # turn off note (not really a TB-303 thing, but a MIDI thing)
        if self.gate_off_time and self.gate_off_time - now <= 0:
            self.gate_off_time = 0
            self.note_off_cb(self.notenum, 0)

        # time for next step? 
        dt = self.next_step_time - now
        if dt <= 0:
            # add dt delta to attempt to make up for CirPy lag
            self.next_step_time = now + self._step_secs + dt  

            if not self.playing:
                return

            i = self.i
            notenum, vel, gate = self.notes[i]
            
            if notenum != 0:    # notenum == 0 = rest
                #notenum += self.transpose
                self.note_on_cb(notenum, vel)
                self.gate_off_time = now + self._step_secs * gate

            # do callback in 'shadow' of note trigger
            if self.step_cb:  # and (self.i % self._steps_per_beat)==0:
                self.step_cb(i, self.steps_per_beat)
                
            self.notenum = notenum  # save for gate off
            self.i = (i+1) % self.num_steps  # go to next step
        
            print("step", i, "note: %d vel:%3d gate:%.1f" %
                  (notenum, vel, gate), int(self._step_secs*1000), int(dt*1000))
