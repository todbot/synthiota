# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# dronesynth -- eight separately tuned drone oscillators on Synthiota
#
# Not a keyboard instrument: the eight pots ARE the pitches, one pot per
# oscillator, and the bottom pad row switches each oscillator in and out.
# The top row is that oscillator's own LFO -- tap to cycle pitch (green),
# volume (blue), off, hold and turn the encoder for its rate.
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
#   top pads ........ tap: LFO off -> pitch -> volume
#                     hold + encoder: that LFO's rate
#                     hold + its own pot: that LFO's depth
#   encoder turn .... waveform, when no top pad is held
#   encoder push .... pitch snap: semitones / free
#   up / down ....... octave all eight pots reach
#   left slider ..... filter cutoff
#   right slider .... master over all eight LFO depths

import sys
import microcontroller
# CircuitPython 10.3.1 has no microcontroller.cpu.architecture
microcontroller.cpu.frequency = 200_000_000 if sys.platform == "RP2350" else 250_000_000

import time
import traceback
import synthio
import tmidi
import ulab.numpy as np

import relic_synthiota
from dronesynth_ui import DroneUI
from synthtools.blocks import scalar_block
from synthtools.waves import get_wave

SAMPLE_RATE = 44100  # set to 22050 here if audio glitches

NUM_OSC = 8
UI_INTERVAL = 0.05  # seconds between UI passes (20 Hz)
HEARTBEAT = 2.0  # TODO temp: serial proof that the loop and the LEDs are live
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

# One oscillator is 15% FS here; eight together ride synthio's soft knee
# at 86%, no clipping. A 1/8-scale share of the bus is inaudible.
OSC_AMP = 0.3

# Mutually non-harmonic defaults, so eight free LFOs never line up.
RATES = (0.11, 0.17, 0.23, 0.31, 0.43, 0.57, 0.77, 1.03)
RATE_MIN, RATE_MAX = 0.02, 20.0
RATE_STEP = 1.15  # per encoder click

PITCH_MOD_MAX = 0.08  # octaves at depth 1.0, about a semitone either way
DEPTH_INIT = 0.3
CUT_MIN = 150.0
CUT_MAX = 6000.0  # under 0.45 * 22050, so the fallback rate is safe too
FILT_Q = 0.9

MODE_OFF, MODE_PITCH, MODE_VOL = 0, 1, 2

# waveform names, from _builders in synthtools/waves.py
WAVES = ("SIN", "TRI", "SAW", "SQU", "ASAW", "ATRI", "ASQU", "SSQU")
WAVE_SIZE = 256  # get_wave()'s own default, needed here for the buffer

# touch ids of the two slider strips, so a slider only reads as live while
# a finger is actually on it (relic's Slider.value can drift off its
# baseline; s.touched uses the MPR121's own threshold)
LSLIDE_PADS = (23, 22, 21)
RSLIDE_PADS = (12, 13, 14)

s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE)
# relic leaves both of these on; the redraw gating and single-show LED
# writes below only mean something with them off
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
s.mixer.voice[0].play(sio)
s.mixer.voice[0].level = 1.0

cut_blk = scalar_block(3000.0)
q_blk = scalar_block(FILT_Q)
# Long enough that a pad tap fades the oscillator in and out instead of
# clicking, short enough to still feel like a switch.
env = synthio.Envelope(attack_time=0.3, decay_time=0.1, sustain_level=1.0,
                       release_time=0.6)

wave_i = 2  # SAW
# One buffer all eight Notes read, written in place by set_wave(), so a
# waveform change reaches oscillators already sounding.
wave_buf = np.zeros(WAVE_SIZE, dtype=np.int16)

notes = []
lfos = []
for i in range(NUM_OSC):
    notes.append(
        synthio.Note(
            frequency=110.0,
            waveform=wave_buf,
            envelope=env,
            amplitude=OSC_AMP,
            # a Biquad per Note: filters hold state, so they cannot be
            # shared, but their cutoff and Q blocks can
            filter=synthio.Biquad(synthio.FilterMode.LOW_PASS, frequency=cut_blk,
                                  Q=q_blk),
        )
    )
    lfo = synthio.LFO(rate=RATES[i], phase_offset=i / NUM_OSC)
    lfos.append(lfo)
    # Unattached blocks freeze, so an LFO routed nowhere, or whose
    # oscillator is out, would jump phase the moment it came back.
    sio.blocks.append(lfo)

oct_i = 1
base_note = OCT_BASES[oct_i]
pitch = [0.0] * NUM_OSC  # midi note each oscillator is tuned to, maybe fractional
pot_pos = [0.0] * NUM_OSC  # smoothed pot position, 0..1
pot_raw = [0.0] * NUM_OSC
pot_until = [0.0] * NUM_OSC  # when this pot's move window closes
on = [False] * NUM_OSC
mode = [MODE_OFF] * NUM_OSC
oct_off = [0] * NUM_OSC  # per-oscillator shift, from a held bottom pad
depth = [DEPTH_INIT] * NUM_OSC  # per-oscillator LFO depth
mod_scale = 1.0  # the right slider, over all eight depths at once
press_at = [0.0] * 16  # when each pad went down, by pad not by oscillator
adjusted = [False] * 16  # this press has modified something, so it is no tap
adjust = None  # oscillator whose top pad is down, the one a knob/encoder steers
quantize = True  # free tuning warbles under pot jitter, so snap by default
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


def read_pots():
    now = time.monotonic()
    for i, v in enumerate(s.pots):
        moved = abs(v - pot_raw[i]) > POT_MOVE
        if last_steps[8 + i]:  # held top pad: this pot is that LFO's depth
            if moved:
                # relative, so depth does not jump to wherever the pitch
                # left the knob; the pitch itself stays where it was until
                # the pot is turned again with the pad up
                set_depth(i, depth[i] + v - pot_raw[i])
                pot_raw[i] = v
                pot_until[i] = 0.0
                adjusted[8 + i] = True
            continue
        if moved:
            pot_raw[i] = v
            pot_until[i] = now + POT_DWELL
        if now > pot_until[i]:
            continue
        pot_pos[i] += (v - pot_pos[i]) * POT_SLEW
        set_pitch(i, pot_pos[i])


def apply_mod(i):
    """Route oscillator i's LFO: to pitch, to volume, or nowhere."""
    lfo, note = lfos[i], notes[i]
    d = depth[i] * mod_scale
    if mode[i] == MODE_PITCH:
        lfo.offset = 0.0
        lfo.scale = d * PITCH_MOD_MAX
        note.amplitude = OSC_AMP
        note.bend = lfo
    elif mode[i] == MODE_VOL:
        # the offset keeps the swing at or above zero: a negative amplitude
        # flips phase instead of going quiet, which tremolos at twice the rate
        lfo.scale = OSC_AMP * d / 2
        lfo.offset = OSC_AMP * (1 - d / 2)
        note.bend = 0.0
        note.amplitude = lfo
    else:
        note.bend = 0.0
        note.amplitude = OSC_AMP


def set_depth(i, v):
    depth[i] = min(max(v, 0.0), 1.0)
    apply_mod(i)


def set_mod_scale(v):
    global mod_scale
    mod_scale = min(max(v, 0.0), 1.0)
    for i in range(NUM_OSC):
        apply_mod(i)


def set_wave(i):
    global wave_i
    wave_i = i
    wave_buf[:] = get_wave(WAVES[i], WAVE_SIZE)  # cached by name and size


def set_cut(v):
    cut_blk.a = CUT_MIN * (CUT_MAX / CUT_MIN) ** min(max(v, 0.0), 1.0)


def set_on(i, v):
    on[i] = v
    if v:
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
                    mode[p - 8] = (mode[p - 8] + 1) % 3
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
            adjusted[i] = True
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
            set_wave((wave_i + d) % len(WAVES))
        else:
            lfo = lfos[adjust]
            lfo.rate = min(max(lfo.rate * RATE_STEP**d, RATE_MIN), RATE_MAX)
            adjusted[8 + adjust] = True
    if s.encoder_button.pressed:
        quantize = not quantize
        if quantize:  # snap where they stand, no waiting for a pot to move
            for i in range(NUM_OSC):
                pitch[i] = round(pitch[i])
                notes[i].frequency = note_hz(pitch[i])


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


def slider_value(slider, pads, touched):
    """None unless a finger is on the strip. relic's Slider.value divides by
    a sum of two pad readings, which can land on zero as a finger lifts."""
    if not any(touched[p] for p in pads):
        return None
    try:
        return slider.value
    except ZeroDivisionError:
        return None


def apply_sliders():
    t = s.touched
    if (v := slider_value(s.left_slider, LSLIDE_PADS, t)) is not None:
        set_cut(v)
    if (v := slider_value(s.right_slider, RSLIDE_PADS, t)) is not None:
        set_mod_scale(v)


def steering():
    """The oscillator the encoder is steering the rate of, if the pad has
    been down long enough that it is no longer a tap waiting to happen."""
    if adjust is None:
        return None
    if adjusted[8 + adjust] or time.monotonic() - press_at[8 + adjust] > HOLD_TIME:
        return adjust
    return None


def mod_color(i, steer):
    """Top-pad LED, pulsing at its own LFO's rate so a rate adjust shows up
    on the pad as well as the screen."""
    if mode[i] == MODE_OFF and i != steer:
        return (0, 0, 0)
    lfo = lfos[i]
    b = 1.0
    if lfo.scale:  # zero depth leaves nothing to pulse with
        b = 0.3 + 0.35 * (1.0 + (lfo.value - lfo.offset) / lfo.scale)
    if i == steer:
        return (int(255 * b),) * 3
    if mode[i] == MODE_PITCH:
        return (0, int(255 * b), int(40 * b))
    return (0, int(40 * b), int(255 * b))


def pot_color(i, steer):
    """Pot LED: its pitch, or magenta for its LFO depth while that is what
    the knob is doing."""
    lvl = int(6 + 249 * (depth[i] if i == steer else pot_pos[i]))
    return (lvl, 0, lvl) if i == steer else (0, lvl, lvl)


def update_leds():
    steer = steering()
    s.step_leds = [(255, 60, 0) if on[i] else (0, 0, 0) for i in range(NUM_OSC)] + [
        mod_color(i, steer) for i in range(NUM_OSC)
    ]
    s.pot_leds = [pot_color(i, steer) for i in range(NUM_OSC)]
    s.mode_led = 0x002222 if quantize else 0x000000
    s.edit_led = 0x222200 if steer is not None else 0x000000
    s.play_led = 0x003311 if any(on) else 0x000000
    s.leds.show()


def update_ui():
    ui.set_header(WAVES[wave_i], "semi" if quantize else "free")
    for i in range(NUM_OSC):
        ui.set_osc(i, pitch[i], mode[i], on[i])
    steer = steering()
    if steer is not None:
        ui.set_status("LFO%d %5.2fHz d%.2f" % (steer + 1, lfos[steer].rate, depth[steer]))
    else:
        ui.set_status("cut %4d  mod %.2f" % (cut_blk.a, mod_scale))


for _i, _v in enumerate(s.pots):  # relic primes the ADCs, so these are good now
    pot_pos[_i] = pot_raw[_i] = _v  # pot_raw too, or the first move reads as a huge jump
    set_pitch(_i, _v)

set_wave(wave_i)
set_on(0, True)  # one oscillator sounding at boot, so the audio chain shows

ui = DroneUI(s.display)

s.step_leds = [(255, 60, 0)] * 16  # hello, and a look at the whole LED chain
s.pot_leds = [(0, 128, 128)] * 8
s.leds.show()
time.sleep(0.4)

print("dronesynth: pots = pitch, bottom pads = osc in/out, top pads = LFO")

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
        check_midi()

        now = time.monotonic()
        if now - last_ui > UI_INTERVAL:
            last_ui = now
            read_pots()
            apply_sliders()
            update_leds()
            update_ui()
            if ui.dirty:
                s.display.refresh()
                ui.dirty = False
            if now - last_beat > HEARTBEAT:  # TODO temp
                print("%.0f Hz errs %d on %d led0 %s pot0 %s cut %.0f"
                      % (passes / (now - last_beat), errs, sum(on),
                         s.leds[0], s.leds[16], cut_blk.a))
                passes, last_beat = 0, now
    except Exception as e:  # TODO temp: report instead of dying mid-play
        errs += 1
        if errs < 4:
            traceback.print_exception(e)
