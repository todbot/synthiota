# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# swarmsynth -- a Swarmatron-style drone machine on Synthiota
#
# Built on synthtools' SwarmSynth: eight oscillators on one pitch, fanned
# apart by a single "swarm" control. Same shell as polysynth (8 pots over
# a PotPageUI page, USB + TRS MIDI), but one page of eight knobs and a
# monophonic drone instead of a 16-note keyboard.
#
# The 8x2 pad grid is split: the BOTTOM row is eight scale degrees, the
# TOP row is eight octave/fifth transpositions of them. The right slider
# is the span ribbon, which is what the real instrument steers the swarm
# with; the left slider nudges the cutoff.
#
# Note budget: SwarmSynth is mono, so a swarm costs swarm_count Notes,
# doubling to 16 while a steal overlaps the releasing swarm with the new
# one, against synthio's 24. That is why "rel" tops out at 2.0s: rolling
# across pads with a longer tail stacks a third releasing swarm and the
# oldest one gets dropped mid-decay.

import microcontroller
microcontroller.cpu.frequency = 200_000_000

import time
import synthio
import tmidi

import relic_synthiota
from synthiota_potpage_ui import PotPageUI
from synthtools import Patch, SwarmSynth
from synthtools.paramset import Param, ParamSet

SAMPLE_RATE = 44100  # set to 22050 here if audio glitches

UI_INTERVAL = 0.05  # seconds between UI passes (20 Hz)
VELOCITY = 110  # touch pads have no velocity

OCTAVES = (24, 36, 48, 60, 72)  # C1..C5: the bottom row's root
DEGREES = (0, 2, 3, 5, 7, 8, 10, 12)  # natural minor, bottom row left to right
# Top row: the drone's transposition, in the octaves and fifths a
# Swarmatron drone lives on. Index 3 is home.
TRANSPOSE = (-24, -12, -7, 0, 7, 12, 19, 24)

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# waveform names, from _builders in synthtools/waves.py
WAVES = ("SAW", "SQU", "TRI", "SIN", "ASAW", "ATRI", "ASQU", "SSQU")

# --- the synth ---------------------------------------------------------
# A drone patch: the swarm IS the timbre, so the filter stays mostly out
# of the way and the amp envelope is long enough that a knob has time to
# move while the note is still loud.
# fmt: off
patch = Patch(name="swarm drone", synth_type="swarm", wave="SAW",
              swarm_count=8, swarm_spread=0.01, swarm_drift=0.003,
              filt_type="LPF", filt_f=2200, filt_q=0.9,
              amp_env=[0.25, 0.20, 0.9, 1.0],
              vib_rate=0.0, vib_depth=0.0,
              glide_time=0.25)
# fmt: on

s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE)
# relic leaves both of these on; our redraw gating and single-show LED
# writes below only mean something with them off
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
s.mixer.voice[0].play(sio)
# Eight detuned oscillators beat, so each Note is amplitude
# velocity/127/swarm_count to keep the worst-case alignment at 1.0. The
# level comes back here rather than in the synth.
s.mixer.voice[0].level = 0.8

SwarmSynth.FILT_F_MAX = s.sample_rate * 0.45  # SUBCLASS, before constructing
synth = SwarmSynth(sio, patch)

# --- the 8 parameters, in pot order ------------------------------------
# One page, so the two-up screen pairs are (P1,P2), (P3,P4), (P5,P6),
# (P7,P8) and each pair is one idea: the swarm, the oscillators, the
# filter, the times. Seeded from the patch so the screen matches the
# sound at boot. "wave" and "count" carry no objattr: both are discrete
# and handled by apply_param() / param_text().
# Names are <= 5 chars: that is what a screen cell holds.
# fmt: off
PARAMS = [
    Param("spred", patch.swarm_spread, 0.0,  0.4,   "%.3f", "swarm_spread"),
    Param("drift", patch.swarm_drift,  0.0,  0.02,  "%.3f", "swarm_drift"),
    Param("count", patch.swarm_count,  1,    8,     "%.0f", None),
    Param("wave",  WAVES.index(patch.wave), 0, len(WAVES) - 1, "%.0f", None),
    Param("freq",  patch.filt_f,       100,  6000,  "%.0f", "filt_f"),
    Param("reso",  patch.filt_q,       0.6,  6.0,   "%.1f", "filt_q"),
    Param("glide", patch.glide_time,   0.0,  1.5,   "%.2f", "glide_time"),
    Param("rel",   patch.amp_env[3],   0.1,  2.0,   "%.2f", "release_time"),
]
# fmt: on

P_SPREAD, P_FREQ = 0, 4  # the two the sliders steer

PAGES = (("SWARM", 8),)

# KNOB_SCALE: a turn always moves the value, scaled by how much runway the
# knob and the value each have left, so they converge without a jump.
# knob_deadband is raised well above the ~0.004 rest jitter of a muxed
# synthiota pot (measured); the 0.002 default lets that noise leak in and
# nudge a resting knob's param.
param_set = ParamSet(PARAMS, num_knobs=8, knob_mode=ParamSet.KNOB_SCALE,
                     knob_deadband=0.012)


def apply_param(p):
    """Push one param onto the synth.

    Discrete params select with round(), not int(): ParamSet's deadband
    leaves a full-scale knob a hair under vmax, which int() truncates to
    vmax - 1, making the last choice unreachable. swarm_count's own
    setter does that int(), so it must be handed a whole number.
    """
    if p.name == "wave":
        synth.wave = WAVES[round(p.val)]
    elif p.name == "count":
        synth.swarm_count = round(p.val)
    else:
        p.apply_to_obj(synth)


def param_text(p):
    if p.name == "wave":
        return WAVES[round(p.val)]
    if p.name == "count":
        return "%d" % round(p.val)
    return p.fmt % p.val


for _p in PARAMS:
    if _p.objattr and _p.objattr not in synth._PARAMS:
        raise ValueError("no such synth parameter: '%s'" % _p.objattr)
    apply_param(_p)

print("swarmsynth: bottom pads = pitch, top pads = octave/fifth, 8 pots")

ui = PotPageUI(s.display, param_set, PAGES, param_text)

oct_i = 1
base_note = OCTAVES[oct_i]
trans_i = TRANSPOSE.index(0)
held = []  # bottom pads down, in press order; last one wins (mono)
last_pad = None  # bottom pad the drone is sounding, None if MIDI drove it
sounding = None  # midi note the synth is actually playing, None if silent
latch = False  # drone keeps sounding after the pad is released
last_steps = [False] * 16
enc_last = s.encoder.position
last_ui = 0.0
pair = [0]  # which pot pair (0..3) the screen shows; last pot turned wins


def root_name():
    n = base_note + TRANSPOSE[trans_i]
    return "%s%d" % (NOTE_NAMES[n % 12], n // 12 - 1)


def play(pad):
    """Sound the drone at bottom-pad `pad`, gliding from wherever it is.

    No synth.note_off() first: mono note_on() steals what is sounding and
    freezes its bend on the way out, which a manual note_off would only
    duplicate. The MIDI stream still needs the matching off.
    """
    global sounding, last_pad
    last_pad = pad
    note = base_note + TRANSPOSE[trans_i] + DEGREES[pad]
    if sounding is not None:
        s.send_midi_message(tmidi.Message(tmidi.NOTE_OFF, sounding, 0))
    synth.note_on(note, VELOCITY)
    s.send_midi_message(tmidi.Message(tmidi.NOTE_ON, note, VELOCITY))
    sounding = note


def silence():
    global sounding
    if sounding is not None:
        synth.note_off(sounding)
        s.send_midi_message(tmidi.Message(tmidi.NOTE_OFF, sounding, 0))
        sounding = None


def play_pads():
    """Diff the 8x2 grid. Bottom row is the eight scale degrees, last-note
    priority so rolling a finger across them glides the drone; top row
    re-aims the same degree at another octave or fifth. Returns True on
    any change (so the UI pass can skip its display refresh)."""
    global last_steps, trans_i
    steps = s.touched_steps
    changed = False
    for i in range(16):
        if steps[i] == last_steps[i]:
            continue
        changed = True
        if i >= 8:  # top row: transposition
            if steps[i]:
                trans_i = i - 8
                # Nothing to re-aim if the drone came in over MIDI: those
                # notes are played as sent, so the new transposition waits
                # for the next pad press.
                if sounding is not None and last_pad is not None:
                    play(last_pad)  # glide the held drone to the new octave
        elif steps[i]:
            held.append(i)
            play(i)
        else:
            # `held` tracks what is physically down even while latched, so
            # the step LEDs stay honest; latch only suppresses the sound
            # change. The sounding degree is `last_pad`, not held[-1].
            if i in held:
                held.remove(i)
            if not latch:
                if held:
                    play(held[-1])  # fall back to whatever is still down
                else:
                    silence()
    last_steps = list(steps)
    return changed


def check_octave():
    global oct_i, base_note
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if d:
        oct_i = min(max(oct_i + d, 0), len(OCTAVES) - 1)
        base_note = OCTAVES[oct_i]


def check_encoder():
    """Turn is another way at the octave; the button toggles latch."""
    global enc_last, oct_i, base_note, latch
    pos = s.encoder.position
    if pos != enc_last:
        oct_i = min(max(oct_i + (pos - enc_last), 0), len(OCTAVES) - 1)
        base_note = OCTAVES[oct_i]
        enc_last = pos
    if s.encoder_button.pressed:
        latch = not latch
        if not latch and not held:  # else a latched drone rings forever
            silence()


def check_midi():
    global sounding, last_pad
    for msg in s.get_midi_messages():
        if msg.type == tmidi.NOTE_ON and msg.velocity:
            synth.note_on(msg.note, msg.velocity)
            sounding = msg.note
            last_pad = None  # no pad owns this one
        elif msg.type in (tmidi.NOTE_OFF, tmidi.NOTE_ON):
            if msg.note == sounding:
                synth.note_off(msg.note)
                sounding = None
        elif msg.type == tmidi.CC:
            if msg.data0 == 1:  # mod wheel -> the span ribbon
                slide_param(P_SPREAD, msg.data1 / 127)
            elif msg.data0 == 74:  # filter cutoff
                slide_param(P_FREQ, msg.data1 / 127)
            elif msg.data0 in (120, 123):
                synth.all_notes_off()
                del held[:]
                sounding = None


# touch ids of the two slider strips, so a slider is only read as live mod
# while a finger is actually on it (relic's Slider.value can drift off its
# baseline; s.touched uses the MPR121's own threshold)
LSLIDE_PADS = (23, 22, 21)
RSLIDE_PADS = (12, 13, 14)


def slide_param(i, v):
    """Set param `i` from a 0..1 ribbon position.

    Writes the Param, not the synth attribute, so the screen and the pot
    LED follow the slider and the pot's scaled takeover starts from where
    the slider left off instead of snapping back. Snaps the screen to the
    pair too, since update_ui() diffs values and by then this one has
    already moved.
    """
    p = PARAMS[i]
    p.val = p.vmin + p.span * min(max(v, 0.0), 1.0)
    apply_param(p)
    pair[0] = i // 2


def apply_sliders():
    """Right slider is the span ribbon (swarm spread), left nudges the
    cutoff. Untouched, each leaves its param alone."""
    t = s.touched
    if any(t[p] for p in RSLIDE_PADS) and (r := s.right_slider.value) is not None:
        slide_param(P_SPREAD, r)
    if any(t[p] for p in LSLIDE_PADS) and (left := s.left_slider.value) is not None:
        slide_param(P_FREQ, left)


def pot_led(p):
    """One pot LED, brightness following the PARAM value (not the raw
    pot), so a slider move or a MIDI CC shows up on it too."""
    lvl = int(6 + 249 * (p.val - p.vmin) / p.span)
    return (0, lvl, lvl)


def step_led(n):
    if n >= 8:
        return 0xFF6600 if n - 8 == trans_i else 0x000000
    if n in held:
        return 0x00AAFF
    if n == last_pad and sounding is not None:
        return 0x002A44  # latched, or still ringing out
    return 0x000000


def update_ui():
    knobs = list(s.pots)
    before = [q.val for q in PARAMS]
    param_set.update_knobs(knobs)
    for gi in range(param_set.nknobs):
        if PARAMS[gi].val != before[gi]:
            apply_param(PARAMS[gi])
            pair[0] = gi // 2  # snap the screen to this pot's pair
    ui.set_shown(pair[0] * 2, pair[0] * 2 + 1)
    ui.update(root_name())
    s.pot_leds = [pot_led(q) for q in PARAMS]
    s.step_leds = [step_led(n) for n in range(16)]
    s.play_led = 0x00FF33 if latch else 0x000000
    s.leds.show()


while True:
    s.update()
    touched = play_pads()
    check_octave()
    check_encoder()
    check_midi()

    now = time.monotonic()
    if now - last_ui > UI_INTERVAL:
        last_ui = now
        apply_sliders()
        update_ui()
        if ui.dirty and not touched:
            s.display.refresh()
            ui.dirty = False
