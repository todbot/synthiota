# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# stepseq8_play.py -- runs ON THE BOARD, via midi_capture.py --run
#
# Plays stepseq8's sequencer flat out on 8 mixed tracks: no screen, LEDs or
# pad reads, so this is its best-case timing. Needs stepseq8 on the board.

import gc

import relic_synthiota
import tmidi
from adafruit_ticks import ticks_diff, ticks_ms
from stepseq8_seq import StepSeq8

RUN_MS = 4000
LENGTHS = (16, 12, 7, 32, 5, 16, 9, 3)
DIVS = (2, 2, 2, 2, 4, 0, 2, 6)  # indexes into stepseq8_seq.DIV_TICKS

s = relic_synthiota.Synthiota(channel_count=1)
msg = tmidi.Message()


def send(mtype, data0, data1, channel):
    msg.type = mtype
    msg.data0 = data0
    msg.data1 = data1
    msg.channel = channel
    s.send_midi_message(msg)


eng = StepSeq8(send)
for n, track in enumerate(eng.tracks):
    track.length = LENGTHS[n]
    track.div = DIVS[n]
    track.set_tempo(eng.bpm)
    for i, step in enumerate(track.seq.steps):
        step[:] = [48 + n * 2 + i % 5, 90, 0.5, True]

print("free before:", gc.mem_free())
eng.play()
start = last = ticks_ms()
worst = 0
while ticks_diff(last, start) < RUN_MS:
    eng.update()
    now = ticks_ms()
    worst = max(worst, ticks_diff(now, last))
    last = now
eng.stop()
print("ticks:", eng.ticks_total, "worst pass ms:", worst, "free after:", gc.mem_free())
