# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# stepseq8_seq.py -- 8 tracks of synthtools StepSequencer on one clock
#
# A ninth, silent StepSequencer is the 24 PPQN master. Every track is
# triggered from the same tick count, so they can't drift apart, and
# MIDI clock in just takes the master's place. No hardware in here.

from random import randint

from adafruit_ticks import ticks_diff, ticks_ms
from synthtools.step_sequencer import StepSequencer
from tmidi import CLOCK, CONTINUE, NOTE_OFF, NOTE_ON, START, STOP

NUM_TRACKS = 8
MAX_STEPS = 32
NUM_SLOTS = 8
PPQN = 24
TICK_WRAP = 48  # common multiple of DIV_TICKS, keeps the tick count small
DIV_TICKS = (3, 4, 6, 8, 12, 16, 24)  # MIDI clocks per step
DIV_NAMES = ("32", "16T", "16", "8T", "8", "4T", "4")
DIV_16TH = 2
BPM_MIN, BPM_MAX = 30, 240
GATE_MAX = 16  # gates are stored in 16ths of a step
EXT_TIMEOUT_MS = 1000

_MAGIC = b"SSQ8"
_STEP_SIZE = 4
_TRACK_HEADER = 8
TRACK_SIZE = _TRACK_HEADER + MAX_STEPS * _STEP_SIZE
PATTERN_SIZE = 1 + NUM_TRACKS * TRACK_SIZE
_FILE_SIZE = len(_MAGIC) + (1 + NUM_SLOTS) * PATTERN_SIZE


def _nop(*_args):
    pass


def clamp(val, vmin, vmax):
    return min(max(val, vmin), vmax)


class Track:
    """One StepSequencer, plus what it takes to speak MIDI safely."""

    def __init__(self, num, send):
        self.send = send
        self.seq = StepSequencer(MAX_STEPS, 4, on_func=self._on, off_func=self._off)
        self.seq.external_clock = True
        for step in self.seq.steps:
            step[:] = [60, 100, 0.5, False]
        self.div = DIV_16TH
        self.ticks = DIV_TICKS[DIV_16TH]
        self.chan = num  # 0-15
        self.level = 100  # percent of each step's velocity
        self.gate = 8  # last value set for the whole track
        self.prob = 100
        self.muted = False
        self.pos = -1  # step last played, -1 after a rewind
        self.fired = False  # played a note, cleared by whoever shows it
        self.note = None  # what's sounding, as sent: edits can't strand it
        self.note_chan = 0
        self.length = 16

    @property
    def length(self):
        return self.seq.step_count

    @length.setter
    def length(self, val):
        self.seq.step_count = clamp(val, 1, MAX_STEPS)

    @property
    def transpose(self):
        return self.seq.transpose

    @transpose.setter
    def transpose(self, val):
        self.seq.transpose = val

    def set_tempo(self, bpm):
        self.ticks = DIV_TICKS[self.div]
        self.seq.steps_per_beat = PPQN / self.ticks
        self.seq.bpm = bpm  # derived from steps_per_beat, so set after it

    def set_gates(self, gate):
        self.gate = gate
        for step in self.seq.steps:  # all of them, not just to the current length
            step[2] = gate / GATE_MAX

    def release(self):
        if self.note is not None:
            self.send(NOTE_OFF, self.note, 0, self.note_chan)
            self.note = None

    def sound(self, note, vel):
        self.release()
        self.note = clamp(note, 0, 127)
        self.note_chan = self.chan
        self.send(NOTE_ON, self.note, clamp(vel * self.level // 100, 1, 127), self.chan)

    def preview(self, step):
        note, vel, _gate, _on = self.seq.steps[step]
        self.sound(note + self.seq.transpose, vel)

    def _on(self, note, vel, _gate, on):
        self.pos = self.seq.i  # still this step's index, it advances after on_func
        self.release()  # a late step's gate can outlast it
        if on and not self.muted and (self.prob >= 100 or randint(0, 99) < self.prob):
            self.sound(note, vel)
            self.fired = True

    def _off(self, _note, _vel, _gate, _on):
        self.release()

    def pack(self, buf, base):
        buf[base] = self.length
        buf[base + 1] = self.div
        buf[base + 2] = self.chan
        buf[base + 3] = self.transpose + 64
        buf[base + 4] = self.level
        buf[base + 5] = self.gate
        buf[base + 6] = self.prob
        buf[base + 7] = self.muted
        base += _TRACK_HEADER
        for note, vel, gate, on in self.seq.steps:
            buf[base] = note
            buf[base + 1] = vel
            buf[base + 2] = round(gate * GATE_MAX)
            buf[base + 3] = on
            base += _STEP_SIZE

    def unpack(self, buf, base, bpm):
        self.length = buf[base]
        self.div = clamp(buf[base + 1], 0, len(DIV_TICKS) - 1)
        self.chan = buf[base + 2] & 15
        self.transpose = buf[base + 3] - 64
        self.level = buf[base + 4]
        self.gate = buf[base + 5]
        self.prob = buf[base + 6]
        self.muted = bool(buf[base + 7])
        self.set_tempo(bpm)
        base += _TRACK_HEADER
        for step in self.seq.steps:
            step[0] = buf[base]
            step[1] = buf[base + 1]
            step[2] = buf[base + 2] / GATE_MAX
            step[3] = bool(buf[base + 3])
            base += _STEP_SIZE


class StepSeq8:
    """``send(mtype, data0, data1, channel)`` sends one MIDI message."""

    def __init__(self, send):
        self.send = send
        self.tracks = [Track(i, send) for i in range(NUM_TRACKS)]
        self.master = StepSequencer(1, PPQN, on_func=self._master_tick, off_func=_nop)
        self.master.steps[0][:] = [0, 0, 0.5, False]
        # a lost tick would drag the tempo, and a slow screen refresh can span one
        self.master.catch_up_steps = PPQN
        self.bpm = 120
        self.playing = False
        self.rewound = True
        self.tick = 0
        self.ticks_total = 0  # never wraps, for checking clock rate
        self.fired = False  # a track stepped, so the next one is furthest away
        self.ext_clock = False
        self._clock_last = 0
        self._clock_count = 0
        self._clock_mark = None
        self.dirty = False  # unsaved changes
        self.pattern = 0  # slot last loaded or saved, for show
        self.slots = bytearray(NUM_SLOTS * PATTERN_SIZE)
        self._job_track = NUM_TRACKS
        self._job_base = 0
        self._job_load = False
        self.set_bpm(self.bpm)

    @property
    def loading(self):
        return self._job_load and self._job_track < NUM_TRACKS

    def set_bpm(self, bpm):
        self.bpm = bpm
        self.master.bpm = bpm
        for t in self.tracks:
            t.set_tempo(bpm)

    # --- transport ---------------------------------------------------------

    def _start_all(self):
        self.playing = True
        for t in self.tracks:
            t.seq.start()
        if not self.ext_clock:
            self.master.start()

    def _pause_all(self):
        self.playing = False
        self.master.pause()
        for t in self.tracks:
            t.seq.pause()
            t.release()

    def _rewind(self):
        self.tick = 0
        self.rewound = True
        for t in self.tracks:
            t.seq.stop()
            t.pos = -1

    def _send_rt(self, mtype):
        if not self.ext_clock:
            self.send(mtype, 0, 0, 0)

    def play(self):
        self._send_rt(START if self.rewound else CONTINUE)
        self._start_all()

    def pause(self):
        self._pause_all()
        self._send_rt(STOP)

    def stop(self):
        self.pause()
        self._rewind()

    def midi_rt(self, mtype):
        """Handle a message from MIDI in, ignoring the ones we don't follow."""
        if mtype == CLOCK:
            self._midi_clock()
        elif mtype == START:
            self._follow(ticks_ms())
            self._pause_all()
            self._rewind()
            self._start_all()
        elif mtype == CONTINUE:
            self._follow(ticks_ms())
            self._start_all()
        elif mtype == STOP:
            self._pause_all()

    def _follow(self, now):
        # Start comes before the first clock, and the master mustn't fill the gap
        self._clock_last = now
        if not self.ext_clock:
            self.ext_clock = True
            self._clock_mark = None
            self.master.pause()

    def _midi_clock(self):
        now = ticks_ms()
        self._follow(now)
        if self._clock_count == 0:
            if self._clock_mark is not None:
                bpm = 60_000 // max(ticks_diff(now, self._clock_mark), 1)
                # +-1 is just clock jitter, and each set_bpm walks every track
                if abs(bpm - self.bpm) > 1:
                    self.set_bpm(clamp(bpm, BPM_MIN, BPM_MAX))
            self._clock_mark = now
        self._clock_count = (self._clock_count + 1) % PPQN
        if self.playing:
            self._tick(now)

    def _master_tick(self, _note, _vel, _gate, _on):
        self.send(CLOCK, 0, 0, 0)
        self._tick(ticks_ms())

    def _tick(self, now):
        self.rewound = False
        for t in self.tracks:
            if self.tick % t.ticks == 0:
                t.seq.trigger(now)
                self.fired = True
        self.tick = (self.tick + 1) % TICK_WRAP
        self.ticks_total += 1

    def update(self):
        """Call as often as possible."""
        for t in self.tracks:
            t.seq.update()
        if not self.ext_clock:
            self.master.update()
        elif ticks_diff(ticks_ms(), self._clock_last) > EXT_TIMEOUT_MS:
            self.ext_clock = False
            if self.playing:
                self.master.start()

    # --- patterns ----------------------------------------------------------
    # A track at a time, from service(), so a load doesn't hold up a step.

    def _begin_job(self, slot, load):
        while self.service():  # finish any job still going
            pass
        self.pattern = slot
        self._job_base = slot * PATTERN_SIZE
        self._job_load = load
        self._job_track = 0
        if load:
            self.set_bpm(clamp(self.slots[self._job_base], BPM_MIN, BPM_MAX))
        else:
            self.slots[self._job_base] = self.bpm
        self.dirty = True

    def load_slot(self, slot):
        self._begin_job(slot, True)

    def save_slot(self, slot):
        self._begin_job(slot, False)

    def service(self):
        """Do one track of a pattern load or save. True while there's more."""
        i = self._job_track
        if i >= NUM_TRACKS:
            return False
        base = self._job_base + 1 + i * TRACK_SIZE
        if self._job_load:
            self.tracks[i].unpack(self.slots, base, self.bpm)
        else:
            self.tracks[i].pack(self.slots, base)
        self._job_track = i + 1
        return True

    def init_slots(self):
        for slot in range(NUM_SLOTS):
            base = slot * PATTERN_SIZE
            self.slots[base] = self.bpm
            for i, t in enumerate(self.tracks):
                t.pack(self.slots, base + 1 + i * TRACK_SIZE)

    def write_file(self, path):
        """Write the working pattern and all slots. Blocks, so not while playing."""
        work = bytearray(PATTERN_SIZE)
        work[0] = self.bpm
        for i, t in enumerate(self.tracks):
            t.pack(work, 1 + i * TRACK_SIZE)
        with open(path, "wb") as f:
            f.write(_MAGIC)
            f.write(work)
            f.write(self.slots)
        self.dirty = False

    def read_file(self, path):
        """Returns False, changing nothing, if the file isn't a good one."""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return False
        if len(data) != _FILE_SIZE or data[:len(_MAGIC)] != _MAGIC:
            return False
        base = len(_MAGIC)
        self.set_bpm(clamp(data[base], BPM_MIN, BPM_MAX))
        for i, t in enumerate(self.tracks):
            t.unpack(data, base + 1 + i * TRACK_SIZE, self.bpm)
        self.slots[:] = data[base + PATTERN_SIZE :]
        return True
