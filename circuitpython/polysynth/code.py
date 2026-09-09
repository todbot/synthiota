# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# polysynth -- a playable SubtractiveSynth on Synthiota
#
# Ported from pico_test_synth's synthtools_polysynth. The 16 step pads are
# a chromatic keyboard; the 8 pots edit the 8 params of the current page
# live; the encoder turns pages (16 params over 2 pages); the up/down
# buttons change octave. USB and TRS MIDI play the synth and pad presses
# are echoed out both.
#
# Polyphony: the patch has detune close to 1.0, so one synthio Note per
# pad, and all sixteen still fit synthio's 24-note budget. Turning detune
# up spends TWO Notes per pad; a full hand-spread then overruns the
# ceiling, audible as dropped notes.

import microcontroller
microcontroller.cpu.frequency = 200_000_000

import time
import synthio
import tmidi

import relic_synthiota
from synthiota_potpage_ui import PotPageUI
from synthtools import Patch, SubtractiveSynth
from synthtools.paramset import Param, ParamSet

SAMPLE_RATE = 44100  # set to 22050 here if audio glitches

UI_INTERVAL = 0.05  # seconds between UI passes (20 Hz)
VELOCITY = 100  # touch pads have no velocity
OCTAVES = (24, 36, 48, 60, 72)  # C1..C5: step 0's note
# A pot never reads exactly 0, and SubtractiveSynth spends a SECOND Note
# per key for any detune that isn't exactly 1.0. Below this, force it off.
DETUNE_OFF = 1.0005

# waveform names, from _builders in synthtools/waves.py
WAVES = ("SAW", "SQU", "TRI", "SIN", "ASAW", "ATRI", "ASQU", "SSQU")
FILTER_TYPES = ("LPF", "HPF", "BPF", "NOTCH")

# --- the synth ---------------------------------------------------------
# fmt: off
patch = Patch(name="touch lead", wave="ASAW", detune=1.001,
              filt_type="LPF", filt_f=1500, filt_q=1.4,
              amp_env=[0.02, 0.20, 0.7, 0.35],
              vib_rate=5.5, vib_depth=0.0,
              fenv_amount=2500, fenv_attack=0.06, fenv_release=0.35)
# fmt: on

s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE)
# relic leaves both of these on; our redraw gating and single-show LED
# writes below only mean something with them off
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
s.mixer.voice[0].play(sio)
s.mixer.voice[0].level = 0.6

SubtractiveSynth.FILT_F_MAX = s.sample_rate * 0.45  # SUBCLASS, before constructing
synth = SubtractiveSynth(sio, patch)

# --- the 16 parameters, in page order --------------------------------
# Order here IS the order on screen; PAGES slices it into knobsets of 8.
# Every one is seeded from the patch, so the screen matches the sound at
# boot. "wave" and "ftype" carry no objattr: they are INDEXES into a name
# list, handled by apply_param() / param_text().
# Names are <= 5 chars: that is what a screen cell holds.
# fmt: off
PARAMS = [
    # OSC/AMP
    Param("wave",  WAVES.index(patch.wave), 0, len(WAVES) - 1, "%.0f", None),
    Param("detun", patch.detune,      1.0,   1.01,  "%.3f", "detune"),
    Param("freq",  patch.filt_f,      20,    4000,  "%.0f", "filt_f"),
    Param("reso",  patch.filt_q,      0.6,   6.0,   "%.1f", "filt_q"),
    Param("atk",   patch.amp_env[0],  0.0,   2.0,   "%.2f", "attack_time"),
    Param("dec",   patch.amp_env[1],  0.0,   2.0,   "%.2f", "decay_time"),
    Param("sus",   patch.amp_env[2],  0.0,   1.0,   "%.2f", "sustain_level"),
    Param("rel",   patch.amp_env[3],  0.01,  3.0,   "%.2f", "release_time"),

    # FILT/MOD
    Param("ftype", FILTER_TYPES.index(patch.filt_type),
                                      0, len(FILTER_TYPES) - 1, "%.0f", None),
    Param("eamt",  patch.fenv_amount, -4000, 6000,  "%.0f", "fenv_amount"),
    Param("eatk",  patch.fenv_attack, 0.005, 1.0,   "%.3f", "fenv_attack"),
    Param("erel",  patch.fenv_release,0.005, 2.0,   "%.2f", "fenv_release"),
    Param("lamt",  patch.filt_lfo_amount, 0,   4000,"%.0f", "filt_lfo_amount"),
    Param("lrate", patch.filt_lfo_rate,   0.1, 12.0,"%.1f", "filt_lfo_rate"),
    Param("vrate", patch.vib_rate,    0.1,   12.0,  "%.1f", "vib_rate"),
    Param("vdep",  patch.vib_depth,   0.0,   0.05,  "%.3f", "vib_depth"),
]
# fmt: on

PAGES = (("OSC/AMP", 8), ("FILT/MOD", 8))

# KNOB_SCALE: a turn always moves the value, scaled by how much runway the
# knob and the value each have left, so they converge without a jump.
# knob_deadband is raised well above the ~0.004 rest jitter of a muxed
# synthiota pot (measured); the 0.002 default lets that noise leak in and
# nudge a resting knob's param. On a page turn check_encoder() also clears
# knob_pos_last so the next read re-adopts the pots instead of reading a
# phantom move from the old page's positions.
param_set = ParamSet(PARAMS, num_knobs=8, knob_mode=ParamSet.KNOB_SCALE,
                     knob_deadband=0.012)


def apply_param(p):
    """Push one param onto the synth.

    Discrete params select with round(), not int(): ParamSet's deadband
    leaves a full-scale knob a hair under vmax, which int() truncates to
    vmax - 1, making the last choice unreachable.
    """
    if p.name == "wave":
        synth.wave = WAVES[round(p.val)]
    elif p.name == "ftype":
        synth.filt_type = FILTER_TYPES[round(p.val)]
    elif p.name == "detun" and p.val < DETUNE_OFF:
        synth.detune = 1.0  # exactly 1.0 is what _make_notes tests for
    else:
        p.apply_to_obj(synth)


def param_text(p):
    if p.name == "wave":
        return WAVES[round(p.val)]
    if p.name == "ftype":
        return FILTER_TYPES[round(p.val)]
    return p.fmt % p.val


for _p in PARAMS:
    if _p.objattr and _p.objattr not in synth._PARAMS:
        raise ValueError("no such synth parameter: '%s'" % _p.objattr)
    apply_param(_p)

print("polysynth: 16 pads keyboard, 8 pots edit a page, encoder turns pages")

ui = PotPageUI(s.display, param_set, PAGES, param_text)

held = {}  # step number -> the midi note actually pressed on it
oct_i = 2
base_note = OCTAVES[oct_i]
last_steps = [False] * 16
enc_last = s.encoder.position
last_ui = 0.0
pair = [0]  # which pot pair (0..3) the screen shows; last pot turned wins


def oct_name():
    return "C%d" % (base_note // 12 - 1)


def play_pads():
    """Diff the 16 step pads for press/release edges. Returns True on any
    change (so the UI pass can skip its display refresh)."""
    global last_steps
    steps = s.touched_steps
    changed = False
    for i in range(16):
        if steps[i] == last_steps[i]:
            continue
        changed = True
        if steps[i]:
            note = base_note + i
            held[i] = note
            synth.note_on(note, VELOCITY)
            s.send_midi_message(tmidi.Message(tmidi.NOTE_ON, note, VELOCITY))
        else:
            note = held.pop(i, None)
            if note is not None:
                synth.note_off(note)
                s.send_midi_message(tmidi.Message(tmidi.NOTE_OFF, note, 0))
    last_steps = list(steps)
    return changed


def check_octave():
    global oct_i, base_note
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if d:
        oct_i = min(max(oct_i + d, 0), len(OCTAVES) - 1)
        base_note = OCTAVES[oct_i]


def check_encoder():
    global enc_last
    pos = s.encoder.position
    if pos != enc_last:
        param_set.idx = (param_set.idx + (pos - enc_last)) % param_set.nknobsets
        param_set.knob_pos_last = None  # re-adopt pot positions, no phantom move
        pair[0] = 0
        enc_last = pos


def check_midi():
    for msg in s.get_midi_messages():
        if msg.type == tmidi.NOTE_ON and msg.velocity:
            synth.note_on(msg.note, msg.velocity)
        elif msg.type in (tmidi.NOTE_OFF, tmidi.NOTE_ON):
            synth.note_off(msg.note)
        elif msg.type == tmidi.CC:
            if msg.data0 == 1:  # mod wheel -> vibrato depth
                synth.vib_depth = msg.data1 / 127 * 0.05
            elif msg.data0 == 74:  # filter cutoff
                synth.filt_f = 60 + msg.data1 / 127 * 4000
            elif msg.data0 in (120, 123):
                synth.all_notes_off()
                held.clear()


# touch ids of the two slider strips, so a slider is only read as live mod
# while a finger is actually on it (relic's Slider.value can drift off its
# baseline; s.touched uses the MPR121's own threshold)
LSLIDE_PADS = (23, 22, 21)
RSLIDE_PADS = (12, 13, 14)


def apply_sliders():
    """The two touch sliders are live mod: right = vibrato depth, left
    nudges the filter cutoff. Untouched, each leaves its target alone."""
    t = s.touched
    if any(t[p] for p in RSLIDE_PADS) and (r := s.right_slider.value) is not None:
        synth.vib_depth = r * 0.05
    if any(t[p] for p in LSLIDE_PADS) and (left := s.left_slider.value) is not None:
        synth.filt_f = 200 + left * 4000


def pot_led(p):
    """One pot LED, brightness following the PARAM value (not the raw pot):
    it stays meaningful across a page turn, and with KNOB_SCALE the value
    tracks the knob once you move it anyway."""
    lvl = int(6 + 249 * (p.val - p.vmin) / p.span)
    return (0, lvl, lvl)


def update_ui():
    knobs = list(s.pots)
    i = param_set.idx * param_set.nknobs
    page = PARAMS[i : i + param_set.nknobs]
    before = [q.val for q in page]
    param_set.update_knobs(knobs)
    for gi in range(param_set.nknobs):
        if page[gi].val != before[gi]:
            apply_param(page[gi])
            pair[0] = gi // 2  # snap the screen to this pot's pair
    ui.set_shown(pair[0] * 2, pair[0] * 2 + 1)
    ui.update(oct_name())
    s.pot_leds = [pot_led(q) for q in page]
    s.step_leds = [0x00AAFF if n in held else 0 for n in range(16)]
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
