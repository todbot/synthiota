# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# wavesynth -- wavetable polysynth on Synthiota
#
# Ported from pico_test_synth's wavesynth. A WavetableSynth: "wpos" moves
# within the loaded wavetable and morphs sounding notes live, "wsel" picks
# which .WAV in wavetables/. Two LFOs: one over the filter cutoff (lamt /
# lrate), one sweeping "wpos" up toward "wlfo" at "wrate". The wave LFO
# only advances when synth.update() is called, which the main loop does
# every pass; it is a cheap no-op while wlfo <= wpos.
#
# The 16 step pads are an 8x2 scale keyboard (see lib/harmony.py): the
# BOTTOM row is the 8 scale degrees, one note each; the TOP row plays a
# chord on the last bottom pad pressed -- root, oct, 5th, triad, 7th,
# 9th, sus, spread, all diatonic so the quality follows the key.
#
# The 8 pots edit the 8 params of the current page; the encoder turns
# pages (24 params over 3); up/down change octave. Scale and key are on
# the KEY/MOD page. HOLD the encoder button and tap a bottom pad to load
# that patch. USB and TRS MIDI play the synth; pad presses echo out both.
#
# Patches live in code only (default_patches()); there is no disk save.
#
# Needs a synthtools newer than bundle 0.5.1 (for the wave LFO and
# synth.update()); the repo installs it from lib/synthtools/*.mpy.

import microcontroller
microcontroller.cpu.frequency = 200_000_000

import os
import time
import synthio
import tmidi

import relic_synthiota
from harmony import NOTE_NAMES, Scale
from synthiota_potpage_ui import PotPageUI
from synthtools import Patch, WavetableSynth
from synthtools.paramset import Param, ParamSet

SAMPLE_RATE = 44100  # set to 22050 here if audio glitches

UI_INTERVAL = 0.05
VELOCITY = 100
WAVE_DIR = "/wavetables"

KEY_ROOT = 48  # MIDI note of scale degree 0 at key C, octave 0 (C3)
OCT_STEPS = (-24, -12, 0, 12, 24)  # up/down button index this
OCT_MID = 2  # OCT_STEPS index that means "no transpose"

# the scales offered on the KEY/MOD page, with <=5-char screen labels;
# harmony.SCALES has more (whole_tone, locrian, ...) for other callers
SCALES_USED = ("major", "minor", "dorian", "mixolydian", "lydian", "phrygian",
               "harmonic_minor", "melodic_minor", "major_pentatonic",
               "minor_pentatonic", "blues", "chromatic")
SCALE_LABELS = ("maj", "min", "dor", "mix", "lyd", "phr", "harm", "melo",
                "maj5", "min5", "blues", "chr")

# top-row pad -> harmony.DIATONIC_SHAPES key, left to right
TOP_SHAPES = ("root", "oct", "5th", "triad", "7th", "9th", "sus", "spread")

FILTER_TYPES = ("LPF", "HPF", "BPF", "NOTCH")


def wave_files():
    """The wavetable WAVs on the device, as full paths.

    Skips names starting with a dot: a hand-copied wavetables/ folder on a
    FAT drive picks up macOS "._" AppleDouble files, which are not RIFF.
    """
    try:
        names = sorted(
            f for f in os.listdir(WAVE_DIR) if f.endswith(".WAV") and not f.startswith(".")
        )
    except OSError:
        names = []
    if not names:
        raise RuntimeError("no .WAV wavetables found in " + WAVE_DIR)
    return [WAVE_DIR + "/" + n for n in names]


WAVES = wave_files()
_FULL_NAMES = [w.split("/")[-1].replace(".WAV", "") for w in WAVES]
# 5 chars is all the screen tile fits; keep the ends, which is where the
# DOS-8 wavetable names actually differ (BRAIDS01..04, PLAITS01..03).
WAVE_NAMES = [n if len(n) <= 5 else n[:2] + n[-3:] for n in _FULL_NAMES]


def default_patches():
    """Nine starting patches, spread across the wavetables on the card."""
    out = []
    for i in range(9):
        out.append(
            Patch(
                name="patch%d" % (i + 1),
                synth_type="wavetable",
                wave_file=WAVES[i % len(WAVES)],
                wave_pos=0,
                filt_type="LPF",
                filt_f=2345,
                filt_q=1.1,
                amp_env=[0.01, 0.1, 0.9, 0.5],
                fenv_amount=1500,
                fenv_attack=0.2,
                fenv_release=0.6,
            )
        )
    return out


patches = default_patches()
patch = patches[3]

s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE)
# relic leaves both of these on; our redraw gating and single-show LED
# writes below only mean something with them off
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
s.mixer.voice[0].play(sio)
s.mixer.voice[0].level = 0.6

WavetableSynth.FILT_F_MAX = s.sample_rate * 0.45  # before constructing
synth = WavetableSynth(sio, patch)

# --- keyboard state --------------------------------------------------
# defined before PARAMS: the "scale"/"key" param cases below read it.
scale = Scale(root=KEY_ROOT, name="major")
key = [0]           # 0..11 chromatic offset from C
octave = OCT_MID    # index into OCT_STEPS; moved by the up/down buttons
last_deg = [0]      # bottom pad last pressed; the top row builds chords on it


def resync_root():
    scale.root = KEY_ROOT + key[0] + OCT_STEPS[octave]


def wave_idx():
    try:
        return WAVES.index(synth.wave_file)
    except ValueError:
        return 0


def wave_top():
    """Highest legal wave_pos in the file loaded right now. Per-FILE, so
    this cannot be worked out once at startup."""
    return max(synth.num_waves - 1, 1)


def sync_wave_ranges():
    """Re-range the two params that index into the wavetable (wpos and the
    wave-LFO ceiling wlfo), called when wsel loads a different file: their
    old maximum may now be off the end of it."""
    top = wave_top()
    for name in ("wpos", "wlfo"):
        q = param_set.param_for_name(name)
        q.vmax = top
        if q.val > top:
            q.val = top
            q.apply_to_obj(synth)


# --- the 24 parameters, in page order --------------------------------
# Order here IS the order on screen; PAGES slices it into knobsets of 8.
# Seeded from, and written back to, the SYNTH, not the patch (synthtools
# keeps a Patch inert), except scale/key which are app state.
# Names are <= 5 chars, which is what a screen cell holds. The params
# with no objattr (wsel, ftype, vol, scale, key, wshp, w1x) are
# special-cased in apply_param() / read_param() / param_text().
# fmt: off
PARAMS = [
    # WAVE
    Param("freq",  synth.filt_f,         60,  8000,  "%4d",   "filt_f"),
    Param("reso",  synth.filt_q,         0.6, 6.0,   "%1.2f", "filt_q"),
    Param("wpos",  synth.wave_pos,       0,   wave_top(), "%1.2f", "wave_pos"),
    Param("wsel",  wave_idx(),           0,   len(WAVES) - 1, "%.0f", None),
    # wlfo is the ceiling wpos sweeps up to; <= wpos means no sweep (0 = off)
    Param("wlfo",  synth.wave_pos_max,   0,   wave_top(), "%1.2f", "wave_pos_max"),
    Param("wrate", synth.wave_lfo_rate,  0.0, 5.0,   "%2.1f", "wave_lfo_rate"),
    Param("atk",   synth.attack_time,    0.0, 3.0,   "%1.2f", "attack_time"),
    Param("rel",   synth.release_time,   0.0, 3.0,   "%1.2f", "release_time"),

    # ENV/FILT
    Param("fatk",  synth.fenv_attack,    0.01,3.0,   "%1.2f", "fenv_attack"),
    Param("frel",  synth.fenv_release,   0.01,3.0,   "%1.2f", "fenv_release"),
    Param("famt",  synth.fenv_amount,   -4000,6000,  "%4d",   "fenv_amount"),
    Param("ftype", FILTER_TYPES.index(synth.filt_type),
                                         0, len(FILTER_TYPES) - 1, "%.0f", None),
    Param("lamt",  synth.filt_lfo_amount,0,  4000,   "%4d",   "filt_lfo_amount"),
    Param("lrate", synth.filt_lfo_rate,  0.0, 8.0,   "%2.1f", "filt_lfo_rate"),
    Param("vdep",  synth.vib_depth,      0.0, 0.05,  "%1.3f", "vib_depth"),
    Param("vol",   s.mixer.voice[0].level, 0.1, 1.0, "%1.2f", None),

    # KEY/MOD
    Param("scale", 0, 0, len(SCALES_USED) - 1, "%.0f", None),
    Param("key",   0, 0, 11,                   "%.0f", None),
    Param("wshp",  0, 0, 1,                     "%.0f", None),  # wave_lfo_shape
    Param("w1x",   0, 0, 1,                     "%.0f", None),  # wave_lfo_once
    Param("wvel",  synth.wave_lfo_vel,  0.0, 1.0,   "%1.2f", "wave_lfo_vel"),
    Param("vrate", synth.vib_rate,      0.1, 12.0,  "%2.1f", "vib_rate"),
    Param("pamt",  synth.penv_amount,  -0.5, 0.5,   "%+1.2f","penv_amount"),
    Param("ptime", synth.penv_time,     0.005, 1.0, "%1.2f", "penv_time"),
]
# fmt: on

PAGES = (("WAVE", 8), ("ENV/FILT", 8), ("KEY/MOD", 8))

# KNOB_SCALE: a turn always moves the value, scaled by the runway the knob
# and the value each have left, so they converge without a jump.
# knob_deadband is raised well above the ~0.004 rest jitter of a muxed
# synthiota pot (measured); the 0.002 default lets that noise nudge a
# resting knob's param. On a page turn or patch load, knob_pos_last is
# cleared so the next read re-adopts the pots with no phantom move.
param_set = ParamSet(PARAMS, num_knobs=8, knob_mode=ParamSet.KNOB_SCALE,
                     knob_deadband=0.012)


def apply_param(p):
    """Push one param onto whatever it represents.

    Discrete params select with round(), not int(): ParamSet's deadband
    leaves a full-scale knob a hair under vmax, which int() truncates to
    vmax - 1, making the last choice unreachable.
    """
    if p.name == "wsel":
        synth.wave_file = WAVES[round(p.val)]
        sync_wave_ranges()  # a new file, a new wave count
    elif p.name == "ftype":
        synth.filt_type = FILTER_TYPES[round(p.val)]
    elif p.name == "vol":
        s.mixer.voice[0].level = min(max(p.val, 0), 1)
    elif p.name == "scale":
        scale.set_scale(SCALES_USED[round(p.val)])
    elif p.name == "key":
        key[0] = round(p.val)
        resync_root()
    elif p.name == "wshp":
        synth.wave_lfo_shape = ("triangle", "saw")[round(p.val)]
    elif p.name == "w1x":
        synth.wave_lfo_once = bool(round(p.val))
    else:
        p.apply_to_obj(synth)


def read_param(p):
    """The inverse of apply_param: what does this param represent now?
    Only loading a patch needs it -- the knobs write the synth, so after
    load_patch() every value has moved and the ParamSet has no idea."""
    if p.name == "wsel":
        p.val = wave_idx()
    elif p.name == "ftype":
        p.val = FILTER_TYPES.index(synth.filt_type)
    elif p.name == "vol":
        p.val = s.mixer.voice[0].level
    elif p.name == "scale":
        p.val = SCALES_USED.index(scale.name) if scale.name in SCALES_USED else 0
    elif p.name == "key":
        p.val = key[0]
    elif p.name == "wshp":
        p.val = 0 if synth.wave_lfo_shape == "triangle" else 1
    elif p.name == "w1x":
        p.val = 1 if synth.wave_lfo_once else 0
    elif p.objattr:
        p.val = getattr(synth, p.objattr)


def param_text(p):
    if p.name == "wsel":
        return WAVE_NAMES[round(p.val)]
    if p.name == "ftype":
        return FILTER_TYPES[round(p.val)]
    if p.name == "scale":
        return SCALE_LABELS[round(p.val)]
    if p.name == "key":
        return NOTE_NAMES[round(p.val)]
    if p.name == "wshp":
        return ("tri", "saw")[round(p.val)]
    if p.name == "w1x":
        return ("rpt", "1x")[round(p.val)]
    return p.fmt % p.val


def update_params():
    for p in PARAMS:
        read_param(p)


update_params()
for _p in PARAMS:
    if _p.objattr and _p.objattr not in synth._PARAMS:
        raise ValueError("no such synth parameter: '%s'" % _p.objattr)
    apply_param(_p)

print("wavesynth: 8x2 scale keyboard, 8 pots / 3 pages, encoder turns pages")

ui = PotPageUI(s.display, param_set, PAGES, param_text)

held = {}  # step number -> list of midi notes that pad started
last_steps = [False] * 16
enc_last = s.encoder.position
enc_held = False
last_ui = 0.0
pair = [0]  # which pot pair (0..3) the screen shows; last pot turned wins


def oct_name():
    """Header right side: key note, plus an octave step when shifted. The
    scale is on the KEY/MOD page, not here."""
    o = octave - OCT_MID
    return NOTE_NAMES[key[0]] + ("%+d" % o if o else "")


def load_patch(idx):
    global patch
    patch = patches[idx]
    synth.all_notes_off()
    held.clear()
    synth.load_patch(patch)
    update_params()
    # pots have not moved but every param under them has; re-adopt the pot
    # positions so the next nudge is a proportional move, not a snap
    param_set.knob_pos_last = None
    param_set.is_tracking = [False] * param_set.nknobs
    pair[0] = 0
    print("loaded patch", idx + 1)


def play_pads():
    """Diff the 8x2 step grid. Bottom row (0..7) plays a scale degree;
    top row (8..15) plays a diatonic chord on the last bottom pad. A
    bottom pad tapped with the encoder button held loads that patch."""
    global last_steps
    steps = s.touched_steps
    changed = False
    for i in range(16):
        if steps[i] == last_steps[i]:
            continue
        changed = True
        if steps[i]:
            if enc_held:
                if i < 8 and i < len(patches):
                    load_patch(i)
                continue
            if i < 8:
                last_deg[0] = i
                notes = [scale.degree(i)]
            else:
                notes = scale.chord(last_deg[0], TOP_SHAPES[i - 8])
            notes = [n for n in notes if 0 <= n <= 127]
            held[i] = notes
            for n in notes:
                synth.note_on(n, VELOCITY)
                s.send_midi_message(tmidi.Message(tmidi.NOTE_ON, n, VELOCITY))
        else:
            for n in held.pop(i, ()):
                synth.note_off(n)
                s.send_midi_message(tmidi.Message(tmidi.NOTE_OFF, n, 0))
    last_steps = list(steps)
    return changed


def check_octave():
    global octave
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if d:
        octave = min(max(octave + d, 0), len(OCT_STEPS) - 1)
        resync_root()


def check_encoder():
    global enc_last, enc_held
    if s.encoder_button.pressed:
        enc_held = True
    if s.encoder_button.released:
        enc_held = False
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
            if msg.data0 == 1:  # mod wheel -> wavetable position
                synth.wave_pos = msg.data1 / 127 * wave_top()
            elif msg.data0 == 74:  # filter cutoff
                synth.filt_f = 60 + msg.data1 / 127 * 7940
            elif msg.data0 in (120, 123):
                synth.all_notes_off()
                held.clear()


# touch ids of the two slider strips, so a slider is only read as live mod
# while a finger is actually on it (relic's Slider.value can drift off its
# baseline; s.touched uses the MPR121's own threshold)
LSLIDE_PADS = (23, 22, 21)
RSLIDE_PADS = (12, 13, 14)


def apply_sliders():
    """Touch sliders as live mod: right = wave position, left nudges the
    filter cutoff. Untouched, each leaves its target alone."""
    t = s.touched
    if any(t[p] for p in RSLIDE_PADS) and (r := s.right_slider.value) is not None:
        synth.wave_pos = r * wave_top()
    if any(t[p] for p in LSLIDE_PADS) and (left := s.left_slider.value) is not None:
        synth.filt_f = 200 + left * 7000


def pot_led(p):
    """One pot LED, brightness following the PARAM value (not the raw pot):
    it stays meaningful across a page turn or patch load, and with
    KNOB_SCALE the value tracks the knob once you move it anyway."""
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
    synth.update()  # advances the wave LFO; cheap no-op while wlfo <= wpos
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
