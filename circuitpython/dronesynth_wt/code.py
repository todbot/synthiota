# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# dronesynth_wt -- eight wavetable drone oscillators on Synthiota
#
# dronesynth with a wavetable where its waveform was. The eight pots are
# still the pitches, one per oscillator, but each oscillator now also has
# its own position in one shared wavetable, and that position is what its
# wave LFO sweeps: a drone that moves in timbre rather than in tune.
#
# Eight synthio Notes pressed and released in place, not a synthtools
# Synth: a Synth's voices are keyed to midi notes and built at note_on.
#
# Both pad rows are tap-or-hold: a tap acts, a hold turns the pad into a
# modifier for the knob, the encoder or the octave buttons.
#
#   8 pots .......... oscillator pitch, 2 octaves each
#   bottom pads ..... tap: oscillator in / out
#                     hold + up/down: shift that one by an octave
#                     hold + its own pot: that oscillator's level
#   top pads ........ tap: LFO off -> wave -> volume -> both
#                     hold + encoder: the routed LFO's rate
#                     hold + encoder push: the routed LFO's shape
#                     hold + its own pot: the depth of what it drives,
#                     which on wave is how far the sweep reaches
#   both pads ....... hold + its own pot: where in the table it starts
#   encoder turn .... wavetable, when no top pad is held
#   encoder push .... pitch snap: semitones / free, when none is held
#   up / down ....... octave all eight pots reach
#   left slider ..... tap an end: filter cutoff down / up
#   right slider .... tap an end: the LFO depth master down / up
#                     either one repeats while held

import sys
import microcontroller
# CircuitPython 10.3.1 has no microcontroller.cpu.architecture
microcontroller.cpu.frequency = 200_000_000 if sys.platform == "RP2350" else 250_000_000

import gc
import math
import os
import time
import traceback
import synthio
import tmidi
import ulab.numpy as np

import relic_synthiota
from dronesynth_wt_ui import DroneUI
from synthtools.blocks import scalar_block
from wave_bank import WaveBank

SAMPLE_RATE = 32000  # set to 22050 here if audio glitches

NUM_OSC = 8
UI_INTERVAL = 0.05  # seconds between UI passes (20 Hz)
HEARTBEAT = 2.0  # TODO temp: serial proof of the loop rate and the heap
HOLD_TIME = 0.4  # a pad down longer than this is a modifier, not a tap

OCT_BASES = (12, 24, 36, 48)  # lowest note the pots reach
POT_RANGE = 24  # semitones end to end of one pot
# Starting octave per oscillator, so the eight pots cover five octaves
# between them rather than all landing in the same two.
OCT_SPREAD = (0, 0, 12, 12, 24, 24, 36, 36)
OCT_SHIFT = 24  # how far a held bottom pad can move its own oscillator
NOTE_MIN, NOTE_MAX = 12, 108  # the spread and the shifts both stop here
# Pot position IS pitch, and measured rest jitter on these muxed pots is
# about 0.004 -- 10 cents of warble over POT_RANGE on every sounding
# oscillator. So a move opens a window, and only inside it does pitch follow.
POT_MOVE = 0.01
POT_DWELL = 0.4
POT_SLEW = 0.5

# dronesynth's measured 0.3, scaled by 28000/32767: these tables are
# peak-normalized to the rail where get_wave() builds at 28000, so this is
# what puts a full-scale wave back where the saw was and keeps the eight
# riding synthio's soft knee at 86% instead of sitting on it.
OSC_AMP = 0.26

WAVE_DIR = "/wavetables"
WAVE_SIZE = 256  # samples per wave in a Serum-style table
# Where in the table each oscillator starts out, so the eight are eight
# timbres at boot rather than one in unison.
WAVE_SPREAD = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
# Waves of movement under which a refill is not worth its cost. A sweep
# always clears it, so this only gates oscillators that are sitting still.
WAVE_EPS = 0.01

# Mutually non-harmonic defaults, so free LFOs never line up: 10s to 3s a cycle
RATES = (0.1, 0.12, 0.14, 0.17, 0.19, 0.23, 0.27, 0.32)
RATE_MIN, RATE_MAX = 0.02, 10.0
RATE_SPAN = math.log(RATE_MAX / RATE_MIN)
# A click is this much of a step, interpolated across the range: 4% down
# at 50s a cycle, 30% at 10Hz
RATE_STEP_LO, RATE_STEP_HI = 1.04, 1.30
LFO_WAVES = ("TRI", "D10", "D30", "D50", "D70", "D90")
# fraction of the cycle each decay takes, D50 where the square used to be
LFO_DECAY = (None, 0.1, 0.3, 0.5, 0.7, 0.9)  # None is the triangle
DECAY_K = 4.0  # e-foldings over that fraction, so it ends within 2% of rest
# 128 leaves the shortest decay a dozen samples; the LFO interpolates
# between them, so a coarse table would step the modulation audibly
LFO_WAVE_SIZE = 128

WAVE_DEPTH_INIT = 0.5  # of the table
AMP_DEPTH_INIT = 0.8
CUT_MIN = 150.0
CUT_MAX = 6000.0  # under 0.45 * 22050, so the fallback rate is safe too
FILT_Q = 0.9

# one bit per destination: apply_mod and mod_color test them with &
MODE_OFF, MODE_WAVE, MODE_VOL = 0, 1, 2
MODE_BOTH = MODE_WAVE | MODE_VOL
NUM_MODES = 4
MODE_NAMES = ("OFF", "WAVE", "VOL", "BOTH")
# lfos, shapes and lfo_bufs are all indexed in this order
DEST_BITS = (MODE_WAVE, MODE_VOL)

# The strips are used as four buttons, not as positions: their continuous
# value reads too roughly on this board to play with. Touch ids from
# relic's pad defs; the middle pad of each strip is unused.
#   (pad, what it nudges, which way)
SLIDE_ENDS = ((23, "cut", -1), (21, "cut", 1), (12, "mod", -1), (14, "mod", 1))
SLIDE_DELAY = 0.35  # held this long before it starts repeating
SLIDE_REPEAT = 0.07
CUT_STEP = 0.04  # of the cutoff's 0..1 position, per nudge
MOD_STEP = 0.04
CUT_INIT = 0.8


def wave_files():
    """The wavetable WAVs on the device, as full paths.

    Skips names starting with a dot: a hand-copied wavetables/ folder on a
    FAT drive picks up macOS "._" AppleDouble files, which are not RIFF.
    """
    try:
        names = sorted(f for f in os.listdir(WAVE_DIR)
                       if f.endswith(".WAV") and not f.startswith("."))
    except OSError:
        names = []
    if not names:
        raise RuntimeError("no .WAV wavetables found in " + WAVE_DIR)
    return [WAVE_DIR + "/" + n for n in names]


TABLES = wave_files()
TABLE_NAMES = [p.split("/")[-1].replace(".WAV", "") for p in TABLES]
# Built before anything else claims the heap: the table is 32 KB in one
# block and nothing later frees enough to get it back.
bank = WaveBank(size=WAVE_SIZE)
table_i = 0
top_wave = 1  # the last wave of the loaded table, set by set_table()

s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE)
# relic leaves both of these on; the redraw gating and single-show LED
# writes below only mean something with them off
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
s.mixer.voice[0].level = 1.0

cut_blk = scalar_block(3000.0)
q_blk = scalar_block(FILT_Q)
# Long enough that a pad tap fades the oscillator in and out instead of
# clicking, short enough to still feel like a switch.
env = synthio.Envelope(attack_time=0.3, decay_time=0.1, sustain_level=1.0,
                       release_time=0.6)

notes = []
# One waveform buffer per oscillator, unlike dronesynth's single shared
# one: eight independent wave positions are eight different waves.
wave_bufs = [np.zeros(WAVE_SIZE, dtype=np.int16) for _ in range(NUM_OSC)]
# Two independent LFOs per oscillator, one per destination: one block
# holds one scale and one offset, and wave and volume want their own rate
# and shape as well.
wave_lfos = []
amp_lfos = []
lfos = (wave_lfos, amp_lfos)
shapes = ([0] * NUM_OSC, [0] * NUM_OSC)
# One buffer per LFO, written in place by set_lfo_wave(): synthio's
# LFO.waveform is read-only once the LFO is built.
lfo_bufs = tuple([np.zeros(LFO_WAVE_SIZE, dtype=np.int16) for _ in range(NUM_OSC)]
                 for _ in DEST_BITS)
for i in range(NUM_OSC):
    notes.append(
        synthio.Note(
            frequency=110.0,
            waveform=wave_bufs[i],
            envelope=env,
            amplitude=OSC_AMP,
            # a Biquad per Note: filters hold state, so they cannot be
            # shared, but their cutoff and Q blocks can
            filter=synthio.Biquad(synthio.FilterMode.LOW_PASS, frequency=cut_blk,
                                  Q=q_blk),
        )
    )
    for d in range(len(DEST_BITS)):
        # volume takes the rates backwards, so a pair starts apart: a click
        # moves both while both are routed, and equal rates stay equal
        lfo = synthio.LFO(waveform=lfo_bufs[d][i],
                          rate=RATES[i if d == 0 else NUM_OSC - 1 - i],
                          phase_offset=i / NUM_OSC)
        lfos[d].append(lfo)
        # Nothing in synthio reads the wave LFO at all and the volume one
        # is unread while it is routed nowhere. An unattached block freezes,
        # so both have to be rooted here to keep running.
        sio.blocks.append(lfo)

# Audio only starts here: a background refill landing between a pair's
# two appends would leave them a buffer out of step for good.
s.mixer.voice[0].play(sio)

oct_i = 1
base_note = OCT_BASES[oct_i]
pitch = [0.0] * NUM_OSC  # midi note each oscillator is tuned to, maybe fractional
pot_pos = [0.0] * NUM_OSC  # smoothed pot position, 0..1
pot_raw = [0.0] * NUM_OSC
pot_until = [0.0] * NUM_OSC  # when this pot's move window closes
on = [False] * NUM_OSC
mode = [MODE_OFF] * NUM_OSC
oct_off = [0] * NUM_OSC  # per-oscillator shift, from a held bottom pad
wave_start = list(WAVE_SPREAD)  # fraction of the table each one starts at
wave_range = [WAVE_DEPTH_INIT] * NUM_OSC  # how far up the table its LFO sweeps
amp_depth = [AMP_DEPTH_INIT] * NUM_OSC  # per-oscillator volume LFO depth
level = [1.0] * NUM_OSC  # per-oscillator volume, OSC_AMP being all of it
wave_at = [-1.0] * NUM_OSC  # wave each buffer was last filled with
mod_scale = 1.0  # the right slider, over all sixteen depths at once
press_at = [0.0] * 16  # when each pad went down, by pad not by oscillator
adjusted = [False] * 16  # this press has modified something, so it is no tap
adjust = None  # oscillator whose top pad is down, the one the encoder steers
quantize = True  # free tuning warbles under pot jitter, so snap by default
cut_pos = CUT_INIT  # the cutoff as 0..1, which is what the nudges move
end_down = [False] * len(SLIDE_ENDS)
end_at = [0.0] * len(SLIDE_ENDS)  # when a held end fires next
last_steps = [False] * 16
enc_last = s.encoder.position
last_ui = 0.0


def note_hz(n):
    """Hz for a FRACTIONAL midi note: free mode tunes between semitones."""
    return 440.0 * 2 ** ((n - 69) / 12)


def set_pitch(i, pos):
    n = base_note + OCT_SPREAD[i] + oct_off[i] + pos * POT_RANGE
    n = min(max(n, NOTE_MIN), NOTE_MAX)
    if quantize:
        # hysteresis: without it a pot sitting on a boundary flips between
        # two semitones
        if abs(n - pitch[i]) < 0.6:
            return
        n = round(n)
    pitch[i] = n
    notes[i].frequency = note_hz(n)


def no_tap(p):
    """This press has done something, so its release is no tap. Both of a
    two-pad chord are spent: lifting the other one would fire its tap."""
    adjusted[p] = True
    other = p - 8 if p >= 8 else p + 8
    if last_steps[other]:
        adjusted[other] = True


def pot_grab(i, v, pad):
    """A pot steered by a held pad moves what it steers RELATIVELY, so the
    pitch neither jumps nor follows, and the press is no longer a tap."""
    pot_raw[i] = v
    pot_until[i] = 0.0
    no_tap(pad)


def read_pots():
    now = time.monotonic()
    for i, v in enumerate(s.pots):
        moved = abs(v - pot_raw[i]) > POT_MOVE
        if last_steps[i] and last_steps[8 + i]:  # both of its pads: the start
            if moved:
                nudge_start(i, v - pot_raw[i])
                pot_grab(i, v, i)
            continue
        if last_steps[8 + i]:  # held top pad: this pot is that LFO's depth
            if moved:
                nudge_depth(i, v - pot_raw[i])
                pot_grab(i, v, 8 + i)
            continue
        if last_steps[i]:  # held bottom pad: that oscillator's volume
            if moved:
                nudge_level(i, v - pot_raw[i])
                pot_grab(i, v, i)
            continue
        if moved:
            pot_raw[i] = v
            pot_until[i] = now + POT_DWELL
        if now > pot_until[i]:
            continue
        pot_pos[i] += (v - pot_pos[i]) * POT_SLEW
        set_pitch(i, pot_pos[i])


def unipolar(i, d):
    """A decay shape runs 1 down to 0, the triangle -1 to 1."""
    return LFO_DECAY[shapes[d][i]] is not None


def primary(i):
    """The destination a held pad steers first: wave, unless the mode
    routes volume alone. What the screen and the white pad LED follow."""
    return 1 if mode[i] == MODE_VOL else 0


def apply_mod(i):
    """Scale both of oscillator i's LFOs, then route either, both or
    neither. Only the volume route is a synthio connection; the wave one
    is update_waves() reading the block."""
    # the sweep runs UP from the start wave whatever the shape, so the start
    # is a floor and not a midpoint
    span = wave_range[i] * mod_scale * top_wave
    uni = unipolar(i, 0)
    wave_lfos[i].scale = span if uni else span / 2
    wave_lfos[i].offset = 0.0 if uni else span / 2
    # either way the swing stays at or above zero: a negative amplitude
    # flips phase instead of going quiet, which tremolos at twice the rate
    amp = OSC_AMP * level[i]
    d = amp_depth[i] * mod_scale
    if not unipolar(i, 1):
        d /= 2
    amp_lfos[i].scale = amp * d
    amp_lfos[i].offset = amp * (1 - d)
    notes[i].amplitude = amp_lfos[i] if mode[i] & MODE_VOL else amp


def nudge_depth(i, d):
    """Move the depths oscillator i's routed LFOs carry."""
    m = mode[i] or MODE_BOTH
    if m & MODE_WAVE:
        wave_range[i] = min(max(wave_range[i] + d, 0.0), 1.0)
    if m & MODE_VOL:
        amp_depth[i] = min(max(amp_depth[i] + d, 0.0), 1.0)
    apply_mod(i)


def nudge_start(i, d):
    wave_start[i] = min(max(wave_start[i] + d, 0.0), 1.0)
    fill_wave(i)


def nudge_level(i, d):
    level[i] = min(max(level[i] + d, 0.0), 1.0)
    apply_mod(i)


def set_mod_scale(v):
    global mod_scale
    mod_scale = min(max(v, 0.0), 1.0)
    for i in range(NUM_OSC):
        apply_mod(i)


def wave_pos(i):
    """The wave oscillator i should be reading now: where it sits in the
    table, plus its own LFO when that is where the LFO points."""
    pos = wave_start[i] * top_wave
    if mode[i] & MODE_WAVE:
        pos += wave_lfos[i].value
    return min(max(pos, 0.0), top_wave)


def fill_wave(i):
    wave_at[i] = p = wave_pos(i)
    bank.fill(wave_bufs[i], p)


def update_waves():
    """A waveform is a plain buffer, not a block synthio can modulate, so
    the wave position is pushed in from here, as often as the loop comes
    round. Eight lerps is the most expensive thing in the loop; an
    oscillator that is out, or sitting still, pays nothing, and the
    heartbeat is where the real cost of it shows up."""
    for i in range(NUM_OSC):
        if not on[i]:
            continue
        p = wave_pos(i)
        if abs(p - wave_at[i]) > WAVE_EPS:
            wave_at[i] = p
            bank.fill(wave_bufs[i], p)


def set_table(i):
    global table_i, top_wave
    bank.load(TABLES[i])  # in place: see WaveBank
    table_i = i  # only once it is really loaded, or the header lies
    top_wave = bank.num_waves - 1
    for j in range(NUM_OSC):
        apply_mod(j)  # the sweeps are in waves, so they rescale with the table
        fill_wave(j)


def set_lfo_wave(i, d, w):
    shapes[d][i] = w
    buf = lfo_bufs[d][i]
    dec = LFO_DECAY[w]
    for j in range(LFO_WAVE_SIZE):
        p = j / LFO_WAVE_SIZE
        if dec is None:
            p *= 4.0
            v = p if p < 1 else 2 - p if p < 3 else p - 4
        else:
            v = math.exp(-DECAY_K * p / dec)
        buf[j] = int(32767 * v)
    apply_mod(i)


def routed(i):
    """The destinations oscillator i's held pad steers: whichever its mode
    routes, or both while it is off, where the knob would have nothing to
    do otherwise."""
    m = mode[i] or MODE_BOTH
    return [d for d, bit in enumerate(DEST_BITS) if m & bit]


def cycle_shape(i):
    """Step the shape of the routed LFOs. In both mode they step together
    from the wave one's, so shapes are set apart in wave or volume."""
    rt = routed(i)
    w = (shapes[rt[0]][i] + 1) % len(LFO_WAVES)
    for d in rt:
        set_lfo_wave(i, d, w)


def set_rate(i, clicks):
    """Move the routed LFOs by clicks encoder clicks, each in steps that
    shrink as it slows, so a pair at different rates stays apart."""
    for d in routed(i):
        lfo = lfos[d][i]
        frac = min(max(math.log(lfo.rate / RATE_MIN) / RATE_SPAN, 0.0), 1.0)
        step = RATE_STEP_LO + (RATE_STEP_HI - RATE_STEP_LO) * frac
        lfo.rate = min(max(lfo.rate * step**clicks, RATE_MIN), RATE_MAX)


def set_cut(v):
    global cut_pos
    cut_pos = min(max(v, 0.0), 1.0)
    cut_blk.a = CUT_MIN * (CUT_MAX / CUT_MIN) ** cut_pos


def set_on(i, v):
    on[i] = v
    if v:
        fill_wave(i)  # update_waves() skips an oscillator that is out
        sio.press(notes[i])
    else:
        sio.release(notes[i])


def check_pads():
    """Both rows act on RELEASE, and only on a tap: a held pad is a
    modifier, so it must not also switch an oscillator or cycle a mode."""
    global last_steps, adjust
    steps = s.touched_steps
    now = time.monotonic()
    for p in range(16):
        if steps[p] == last_steps[p]:
            continue
        if steps[p]:
            press_at[p] = now
            adjusted[p] = False
            if p >= 8:
                adjust = p - 8
        else:
            if not adjusted[p] and now - press_at[p] < HOLD_TIME:
                if p < 8:
                    set_on(p, not on[p])
                else:
                    mode[p - 8] = (mode[p - 8] + 1) % NUM_MODES
                    apply_mod(p - 8)
            if p >= 8 and adjust == p - 8:
                adjust = None
    last_steps = list(steps)


def check_octave():
    global oct_i, base_note
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if not d:
        return
    one = False
    for i in range(NUM_OSC):
        if last_steps[i]:  # a held bottom pad keeps the shift for itself
            oct_off[i] = min(max(oct_off[i] + 12 * d, -OCT_SHIFT), OCT_SHIFT)
            no_tap(i)
            set_pitch(i, pot_pos[i])
            one = True
    if one:
        return
    oct_i = min(max(oct_i + d, 0), len(OCT_BASES) - 1)
    base_note = OCT_BASES[oct_i]
    for i in range(NUM_OSC):
        set_pitch(i, pot_pos[i])


def check_encoder():
    global enc_last, quantize
    pos = s.encoder.position
    if pos != enc_last:
        d = enc_last - pos  # this encoder counts down going clockwise
        enc_last = pos
        if adjust is None:
            set_table((table_i + d) % len(TABLES))
        else:
            set_rate(adjust, d)
            no_tap(8 + adjust)
    if s.encoder_button.pressed:
        if adjust is None:
            quantize = not quantize
        else:
            cycle_shape(adjust)
            no_tap(8 + adjust)


def check_midi():
    """CC only: the pitches belong to the pots, so notes have nowhere to go."""
    for msg in s.get_midi_messages():
        if msg.type != tmidi.CC:
            continue
        if msg.data0 == 74:
            set_cut(msg.data1 / 127)
        elif msg.data0 == 1:
            set_mod_scale(msg.data1 / 127)
        elif msg.data0 in (120, 123):
            for i in range(NUM_OSC):
                if on[i]:
                    set_on(i, False)


def nudge(what, d):
    if what == "cut":
        set_cut(cut_pos + d * CUT_STEP)
    else:
        set_mod_scale(mod_scale + d * MOD_STEP)


def check_sliders():
    """Each strip is two buttons: a tap on an end nudges, holding repeats."""
    t = s.touched
    now = time.monotonic()
    for k, (pad, what, d) in enumerate(SLIDE_ENDS):
        if not t[pad]:
            end_down[k] = False
        elif not end_down[k]:
            end_down[k] = True
            end_at[k] = now + SLIDE_DELAY
            nudge(what, d)
        elif now >= end_at[k]:
            end_at[k] = now + SLIDE_REPEAT
            nudge(what, d)


def steering(off):
    """The oscillator whose pot a held pad in this row has taken over, once
    the press is too old to still turn into a tap. The top row steers its
    LFO, the bottom row its volume, the two together its place in the
    table."""
    now = time.monotonic()
    for i in range(NUM_OSC):
        p = off + i
        if last_steps[p] and (adjusted[p] or now - press_at[p] > HOLD_TIME):
            return i
    return None


def steers():
    """(both, lfo, osc): which oscillator each held-pad gesture has a knob
    of, both pads of one column beating either of them alone."""
    lfo, osc = steering(8), steering(0)
    if lfo is not None and lfo == osc:
        return lfo, None, None
    return None, lfo, osc


def pulse(i, d):
    """0.3 to 1 following that LFO's shape, flat while it has no swing to
    show, so a rate adjust reads on the pad as well as the screen."""
    lfo = lfos[d][i]
    if not lfo.scale:
        return 1.0
    v = (lfo.value - lfo.offset) / lfo.scale  # back to the raw shape
    return 0.3 + 0.35 * (1.0 + (v * 2 - 1 if unipolar(i, d) else v))


def mod_color(i, steer):
    """Top-pad LED: green wave, blue volume, each pulsing at its own rate,
    white while that pad is the one steering."""
    if mode[i] == MODE_OFF and i != steer:
        return (0, 0, 0)
    if i == steer:
        b = pulse(i, primary(i))
        return (int(255 * b),) * 3
    g = 255 if mode[i] & MODE_WAVE else 40
    bl = 255 if mode[i] & MODE_VOL else 40
    return (0, int(g * pulse(i, 0)), int(bl * pulse(i, 1)))


def pot_color(i, st):
    """Pot LED: the wave that oscillator is reading, white while the knob
    is moving where it starts, magenta for a depth, amber for its volume."""
    both, lfo_steer, osc_steer = st
    if i == both:
        lvl = int(6 + 249 * wave_start[i])
        return (lvl, lvl, lvl)
    if i == lfo_steer:
        lvl = int(6 + 249 * (amp_depth[i] if primary(i) else wave_range[i]))
        return (lvl, 0, lvl)
    if i == osc_steer:
        lvl = int(6 + 249 * level[i])
        return (lvl, lvl // 3, 0)
    lvl = int(6 + 249 * wave_pos(i) / top_wave)
    return (0, lvl, lvl)


def update_leds():
    st = steers()
    both, lfo_steer, osc_steer = st
    top = both if lfo_steer is None else lfo_steer
    s.step_leds = [(255, 60, 0) if on[i] else (0, 0, 0) for i in range(NUM_OSC)] + [
        mod_color(i, top) for i in range(NUM_OSC)
    ]
    s.pot_leds = [pot_color(i, st) for i in range(NUM_OSC)]
    s.mode_led = 0x002222 if quantize else 0x000000
    s.edit_led = 0x222200 if any(x is not None for x in st) else 0x000000
    s.play_led = 0x003311 if any(on) else 0x000000
    s.leds.show()


def rate_text(r):
    """Hz once it is fast, seconds a cycle below that: a 30s swell reads
    as 0.03Hz either way you nudge it."""
    if r >= 9.95:  # five characters is all the focus panel's big text has
        return "%dHz" % round(r)
    return "%.1fHz" % r if r >= 1.0 else "%.1fs" % (1.0 / r)


def sweep_span(i):
    """The stretch of the table oscillator i's wave LFO sweeps, as
    fractions of it, or None while that LFO is routed elsewhere."""
    if not mode[i] & MODE_WAVE:
        return None
    return wave_start[i], min(wave_start[i] + wave_range[i] * mod_scale, 1.0)


def gain(i):
    """How loud oscillator i is right now, as a fraction of OSC_AMP."""
    return (amp_lfos[i].value if mode[i] & MODE_VOL else OSC_AMP * level[i]) / OSC_AMP


def update_ui():
    ui.set_header(TABLE_NAMES[table_i], "semi" if quantize else "free",
                  cut_pos, mod_scale)
    # focus first: leaving it clears the columns, which set_osc then redraws
    both, lfo_steer, osc_steer = steers()
    if both is not None:
        i = both
        ui.focus_osc(i, "OSC %d  START" % (i + 1),
                     "%.1f" % (wave_start[i] * top_wave), "of %d" % top_wave,
                     wave_bufs[i], wave_at[i], gain(i),
                     strip=(wave_at[i] / top_wave, wave_start[i], sweep_span(i)))
    elif lfo_steer is not None:
        i = lfo_steer
        d = primary(i)
        m = mode[i] or MODE_BOTH  # what routed() steers
        lfo = lfos[d][i]
        # .phase runs from -phase_offset; the waveform is read offset from it
        at = (lfo.phase + lfo.phase_offset) % 1.0
        ui.focus_lfo(i, "LFO %d  %s  %s" % (i + 1, MODE_NAMES[mode[i]],
                                            LFO_WAVES[shapes[d][i]]),
                     rate_text(lfo.rate), lfo_bufs[d][i], at,
                     (("W", wave_range[i], bool(m & MODE_WAVE)),
                      ("V", amp_depth[i], bool(m & MODE_VOL))))
    elif osc_steer is not None:
        i = osc_steer
        ui.focus_osc(i, "OSC %d  VOLUME" % (i + 1), "%d%%" % round(100 * level[i]),
                     "", wave_bufs[i], wave_at[i], gain(i), level=level[i])
    else:
        ui.focus_off()
    for i in range(NUM_OSC):
        ui.set_osc(i, pitch[i], mode[i], on[i], level[i], gain(i), wave_bufs[i],
                   wave_at[i], wave_at[i] / top_wave, sweep_span(i))


for _i, _v in enumerate(s.pots):  # relic primes the ADCs, so these are good now
    pot_pos[_i] = pot_raw[_i] = _v  # pot_raw too, or the first move reads as a huge jump
    set_pitch(_i, _v)

set_table(table_i)  # fills every buffer, so nothing starts on a silent one
for _i in range(NUM_OSC):
    for _d in range(len(DEST_BITS)):
        set_lfo_wave(_i, _d, 0)
set_cut(CUT_INIT)
set_on(0, True)  # one oscillator sounding at boot, so the audio chain shows

ui = DroneUI(s.display)

s.step_leds = [(255, 60, 0)] * 16  # hello, and a look at the whole LED chain
s.pot_leds = [(0, 128, 128)] * 8
s.leds.show()
time.sleep(0.4)

print("dronesynth_wt: %d tables, %d waves each; pots = pitch, bottom pads ="
      " osc in/out" % (len(TABLES), bank.num_waves))

errs = 0
passes = 0
last_beat = 0.0
while True:
    try:
        passes += 1
        s.update()
        check_pads()
        check_octave()
        check_encoder()
        check_sliders()
        check_midi()
        update_waves()

        now = time.monotonic()
        if now - last_ui > UI_INTERVAL:
            last_ui = now
            read_pots()
            update_leds()
            update_ui()
            if ui.dirty:
                s.display.refresh()
                ui.dirty = False
            if now - last_beat > HEARTBEAT:  # TODO temp
                print("%.0f Hz errs %d on %d free %d cut %.0f"
                      % (passes / (now - last_beat), errs, sum(on),
                         gc.mem_free(), cut_blk.a))
                passes, last_beat = 0, now
    except Exception as e:  # TODO temp: report instead of dying mid-play
        errs += 1
        if errs < 4:
            traceback.print_exception(e)
