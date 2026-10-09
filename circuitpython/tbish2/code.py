# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# tbish2 -- a TB-303-like acid bassline on Synthiota,
#           using synthtools' BasslineSynth
#
# Ported from pico_test_synth's tbish2, with the controls of this repo's
# tbish/: the encoder steps through three modes, "play" (pots edit the
# main 303 knobs), "edit" (pots set 8 step notes, pads toggle rests,
# accents and slides) and "more" (pots edit the rest of the synth).
# Patterns are 16 steps; the screen, pads and pots show 8 at a time.
#
#   encoder turn .............. next / previous mode
#   encoder push .............. play / pause (pause saves to /tbish2.json)
#   step pads, playing ........ transpose the pattern
#   step pads, stopped ........ play the synth
#   up / down ................. octave up / down
#   right slider, left / right end ... previous / next pattern
#   left slider, middle .............. edit steps 1-8 / 9-16
#   hold right slider end + encoder .. scroll patterns
#   hold left slider, left end + encoder ... bpm
#   hold left slider, right end + encoder .. steps per beat

import microcontroller
microcontroller.cpu.frequency = 200_000_000

import json
import os
import time
import synthio

import relic_synthiota
from synthtools import BasslineSynth, Patch
from synthtools.paramset import Param, ParamSet
from synthtools.step_sequencer import StepSequencer
from tbish2_ui import TBish2UI

#SAMPLE_RATE = 44100  # set to 22050 here if audio glitches
SAMPLE_RATE = 22050

# distortion is too expensive on an rp2040
IS_RP2350 = "rp2350" in os.uname()[0]

UI_INTERVAL = 0.05
PARAMS_FILE = "/tbish2.json"
PAD_VELOCITY = 80  # below BasslineSynth.accent_velocity, or every pad accents
GATE = 0.75  # traditional 303 gate length, as a fraction of a step
# >1 so the note is still held when the next step ties to it. Margin over
# 1.0 is how late a loop pass can be before the tie silently breaks.
TIE_GATE = 1.5
SPB_ALLOWED = (1, 2, 4, 8, 16)

MODE_PLAY, MODE_EDIT, MODE_MORE = 0, 1, 2

# touch ids, see relic_synthiota's pad defs
LSLIDE_A = 23  # left slider, left end
LSLIDE_B = 22  # left slider, middle
LSLIDE_C = 21  # left slider, right end
RSLIDE_A = 12  # right slider, left end
RSLIDE_C = 14  # right slider, right end

# waveform names, from _builders in synthtools/waves.py
WAVES = ("SAW", "SQU", "ASAW", "ASQU", "TRI", "SIN")

# --- the patterns --------------------------------------------------------
# notes (0 = rest), velocities (>100 = accent), slides (1 = slide into this
# step from the last; on a 303 the flag is on the step BEFORE the slide)
# Famous ones from https://djjondent.blogspot.com/2020/04/famous-303-bassline-patterns-page-1.html
# fmt: off
SEQS = [
    # New Order - Confusion (Pump Panel Reconstruction, 1995), 134 BPM
    [[ 43,  43,  43,  43,   0,  31,  43,   0,    46,   0,  34,  34,  34,  46,   0,  34],
     [ 80,  80,  80,  80,  80,  80,  80,  80,    80,  80,  80,  80,  80,  80,  80,  80],
     [  0,   1,   1,   0,   0,   0,   0,   0,     0,   0,   0,   1,   0,   0,   0,   0]],

    # Phuture - Acid Tracks (1987), ~120 BPM. Only the 8 notes are
    # published; accents and slides were tweaked live, so none here.
    [[ 35,  35,  36,  48,  36,  39,  39,  48,    35,  35,  36,  48,  36,  39,  39,  48],
     [ 80,  80,  80,  80,  80,  80,  80,  80,    80,  80,  80,  80,  80,  80,  80,  80],
     [  0,   0,   0,   0,   0,   0,   0,   0,     0,   0,   0,   0,   0,   0,   0,   0]],

    # Fast Eddie - Acid Thunder (1988), BPM unknown; x0xb0x transcription
    [[ 39,  39,  42,  40,  40,  40,  43,  43,    43,  48,  48,  47,  38,  38,  39,  39],
     [ 80,  80, 127,  80,  80,  80, 127,  80,    80,  80,  80,  80,  80,  80,  80,  80],
     [  0,   1,   0,   0,   1,   1,   0,   1,     1,   0,   1,   0,   0,   1,   0,   1]],

    # Josh Wink - Higher State of Consciousness (1995), 134 BPM
    [[ 43,  55,  43,  43,  43,  43,  47,  43,    47,  43,  43,  47,  43,  43,  43,  47],
     [127, 127, 127, 127, 127, 127, 127, 127,   127, 127, 127, 127, 127, 127, 127, 127],
     [  0,   1,   0,   1,   1,   0,   0,   0,     0,   0,   1,   0,   0,   1,   1,   0]],

    # DJ Tim & Misjah - Access (1995), 134 BPM
    [[ 45,   0,  45,  57,  45,  45,  45,   0,    45,  45,  57,  45,   0,  45,  45,   0],
     [ 80,  80,  80,  80, 127,  80,  80,  80,    80,  80,  80,  80,  80,  80,  80,  80],
     [  0,   0,   0,   0,   0,   0,   0,   0,     0,   0,   0,   0,   0,   0,   0,   0]],

    # tbish's own 8-step patterns, played twice
    [[24,  36, 48, 36,  48, 48+7, 36, 48] * 2,
     [127, 80, 80, 80,  127,  80, 80, 80] * 2,
     [0,    0,  0,  0,   0,   1,  0,  1] * 2],

    [[36,   0,   0,  0,  24,    0,   0,  0] * 2,
     [127, 80,  80, 80,  127 , 80, 127, 80] * 2,
     [0,    1,   1,  0,   0,    1,   0,  1] * 2],

    [[36,  48, 36, 48,  36,  48, 36, 48] * 2,
     [127, 80, 80, 80,  127, 80, 80, 80] * 2,
     [0,    0,  1,  1,   0,   1,  0,  1] * 2],

    [[36, 36, 34, 36,  48, 48, 36, 48] * 2,
     [127, 80, 127, 80,  127, 80, 127, 80] * 2,
     [0,    0,  0,  0,   0,   0,  0,  0] * 2],

    [[36,  24,  36, 48,  36, 0, 36, 0] * 2,
     [127, 80, 80, 80,  127, 80, 127, 80] * 2,
     [0,    1,  1,  0,   0,   0,  0,  0] * 2],
]
# fmt: on
STEP_COUNT = len(SEQS[0][0])
PAGE = 8  # steps shown and edited at once

# --- the patch -----------------------------------------------------------
# `decay` (the FILTER fall) must be shorter than the gate and the amp decay
# longer, or the envmod sweep is masked and every step is just a pluck.
# fmt: off
patch = Patch(
    name="tbish2",
    synth_type="bassline",
    wave="SAW",
    filt_type="LPF",
    filt_f=2345,
    filt_q=1.8,
    envmod=0.5,
    decay=0.3,
    # long decay: a run of slides is ONE note, so it must outlast the run
    amp_env=[0.001, 1.0, 0.0, 0.02],
    fenv_curve=3,
    accent=0.5,
    accent_cutoff=4000,
    accent_q=0.8,
    amp_level=0.75,      # un-accented level, so accents have room
    slide_time=0.09,
    fx_filter_stages=1,  # one extra stage makes the voice's 12 dB/oct 24
    # STRUCTURAL: nothing can turn these on later
    fx_distortion_on=IS_RP2350,
    fx_echo_on=True,
    fx_drive=0.6,
    fx_drive_mix=0.0,
    fx_delay_ms=330.0,
    fx_delay_mix=0.0,
    fx_delay_decay=0.3,
)
# fmt: on

# mono: stereo doubles every fx buffer, and the Echo's alone (1 s at
# 44.1 kHz) is then too big to allocate
s = relic_synthiota.Synthiota(sample_rate=SAMPLE_RATE, channel_count=1)
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.3

sio = synthio.Synthesizer(sample_rate=s.sample_rate, channel_count=s.channel_count)
BasslineSynth.FILT_F_MAX = s.sample_rate * 0.45  # SUBCLASS, before constructing
bass = BasslineSynth(sio, patch)

# Without bass.output the fx chain is bypassed and the synth sounds thin.
try:
    s.mixer.voice[0].play(bass.output)
except ImportError:
    print("no audiofilters/audiodelays in this build: 12 dB/oct, no drive, no delay")
    s.mixer.voice[0].play(sio)

# --- the 16 synth parameters: page 0 is "play" mode, page 1 "more" --------
# fmt: off
PARAMS = [
    Param("cutoff",   patch.filt_f,        100,  4000,  "%4d",   "filt_f"),
    Param("envmod",   patch.envmod,        0.0,  1.0,   "%.2f",  "envmod"),
    # 4.0, not 6.0: an accent adds up to accent_q on top
    Param("resQ",     patch.filt_q,        0.6,  8.0,   "%.2f",  "filt_q"),
    # a 16th's gate is ~90 ms, so a longer fall is never heard
    Param("decay",    patch.decay,         0.01, 2.0,  "%.2f",  "decay"),
    Param("accent",   patch.accent,        0.0,  1.0,   "%.2f",  "accent"),
    Param("wave",     WAVES.index(patch.wave), 0, len(WAVES) - 1, "%.0f", None),
    # the mix, as tbish's Drive knob was: an amount alone is never heard
    Param("drive",    patch.fx_drive_mix,  0.0,  1.0,   "%.2f",  "fx_drive_mix"),
    Param("delaymix", patch.fx_delay_mix,  0.0,  0.5,   "%.2f",  "fx_delay_mix"),

    Param("ampdec",   patch.amp_env[1],    0.02, 3.0,   "%.2f",  "decay_time"),
    Param("amplevel", patch.amp_level,     0.1,  1.0,   "%.2f",  "amp_level"),
    Param("acctcut",  patch.accent_cutoff, 0,    6000,  "%4d",   "accent_cutoff"),
    Param("acctQ",    patch.accent_q,      0.0,  2.0,   "%.2f",  "accent_q"),
    Param("slide",    patch.slide_time,    0.01, 0.25,  "%.2f",  "slide_time"),
    Param("drvamt",   patch.fx_drive,      0.0,  1.0,   "%.2f",  "fx_drive"),
    Param("dtime",    patch.fx_delay_ms,   0,    1000,  "%4d",   "fx_delay_ms"),
    Param("dlyfeed",  patch.fx_delay_decay, 0.0, 0.9,   "%.2f",  "fx_delay_decay"),
]
# fmt: on

# knob_deadband well above a muxed synthiota pot's ~0.004 rest jitter
param_set = ParamSet(PARAMS, num_knobs=8, knob_mode=ParamSet.KNOB_SCALE,
                     knob_deadband=0.012)

# edit mode: one pot per step note, one knobset per half
NOTE_PARAMS = [Param("step%d" % (i + 1), 36, 24, 72, "%d") for i in range(STEP_COUNT)]
note_set = ParamSet(NOTE_PARAMS, num_knobs=8, knob_mode=ParamSet.KNOB_SCALE,
                    knob_deadband=0.012)


def apply_param(p):
    # round(), not int(): a full-scale knob sits a hair under vmax
    if p.name == "wave":
        bass.wave = WAVES[round(p.val)]
    else:
        p.apply_to_obj(bass)


def param_text(p):
    if p.name == "wave":
        return WAVES[round(p.val)]
    return p.fmt % p.val


# --- the sequencer -------------------------------------------------------
seqs = [[list(row) for row in seq] for seq in SEQS]
seq_num = 0
bpm = 120
spb = 4
transpose = 0
transpose_oct = 0


def on_step(note, vel, gate, on):
    if not on:  # a rest; `note` is already transposed, so it is not 0
        # a live edit can rest the step a held tie was waiting on
        bass.all_notes_off()
        return
    # .i is still this step's index, it advances after on_func
    slide = seqs[seq_num][2][sequencer.i]
    bass.note_on_step(note, slide=bool(slide), accent=vel > 100, velocity=vel)


def off_step(note, vel, gate, on):
    if on:
        bass.note_off(note)


sequencer = StepSequencer(STEP_COUNT, spb, on_func=on_step, off_func=off_step)


def load_steps():
    """Copy the current pattern into the sequencer. Call on any edit."""
    notes, vels, slides = seqs[seq_num]
    for i in range(STEP_COUNT):
        nxt = (i + 1) % STEP_COUNT
        # a tie onto a rest would leave this note with no note_off
        tie = notes[i] and notes[nxt] and slides[nxt]
        sequencer.steps[i] = [notes[i], vels[i], TIE_GATE if tie else GATE, notes[i] > 0]


def set_seq(n):
    global seq_num
    seq_num = n
    for p, note in zip(NOTE_PARAMS, seqs[n][0]):
        if note:
            p.val = note
    load_steps()


def set_tempo():
    sequencer.steps_per_beat = spb
    sequencer.bpm = bpm  # derived from steps_per_beat, so set after it


def save():
    state = {
        "params": {p.name: p.val for p in PARAMS},
        "bpm": bpm, "spb": spb, "seq": seq_num, "seqs": seqs,
    }
    try:
        with open(PARAMS_FILE, "w") as f:
            json.dump(state, f)
    except OSError:
        print("could not write", PARAMS_FILE, "-- needs boot.py's remount")


def load():
    """Replace the defaults with whatever save() last wrote, if anything."""
    global bpm, spb, seq_num, seqs
    try:
        with open(PARAMS_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return
    # by name, so a file saved from an older PARAMS list can't smear
    for p in PARAMS:
        v = state["params"].get(p.name)
        if v is not None and p.vmin <= v <= p.vmax:
            p.val = v
    if 30 <= state.get("bpm", 0) <= 240:
        bpm = state["bpm"]
    if state.get("spb") in SPB_ALLOWED:
        spb = state["spb"]
    loaded = state.get("seqs")
    if loaded and all(len(seq) == 3 and all(len(row) == STEP_COUNT for row in seq)
                      for seq in loaded):
        seqs = loaded
    seq_num = min(state.get("seq", 0), len(seqs) - 1)


try:
    load()
except (AttributeError, KeyError, TypeError):
    # e.g. pico_test_synth's tbish2 saves a different shape to the same name
    print("ignoring", PARAMS_FILE, "-- not a tbish2 save")

for _p in PARAMS:
    if _p.objattr and _p.objattr not in bass._PARAMS:
        raise ValueError("no such synth parameter: '%s'" % _p.objattr)
    apply_param(_p)
set_tempo()
set_seq(seq_num)

print("tbish2: encoder turns modes, push to play/pause")

# --- the UI --------------------------------------------------------------
ui = TBish2UI(s.display, PAGE, param_text)
mode = MODE_PLAY
edit_half = 0  # which PAGE of steps edit mode works on
pat_scrolled = False  # encoder turned while a pattern pad is held
pair = 0  # which pot pair (0..3) the screen shows; last pot turned wins
enc_last = s.encoder.position
last_ui = 0.0
last_steps = s.touched_steps
last_touched = s.touched
pad_notes = {}  # step pad -> note it is playing, while stopped


def set_mode(m):
    global mode, pair
    mode = m
    pair = 0
    if mode == MODE_EDIT:
        note_set.knob_pos_last = None
    else:
        param_set.idx = 0 if mode == MODE_PLAY else 1
        param_set.knob_pos_last = None  # re-adopt pots, no phantom move
    ui.show_mode(mode)


def set_edit_half(h):
    global edit_half
    edit_half = h
    note_set.idx = h
    note_set.knob_pos_last = None


def set_transpose():
    sequencer.transpose = transpose + transpose_oct * 12


def step_pad_pressed(n):
    global transpose
    notes, vels, slides = seqs[seq_num]
    if mode == MODE_EDIT:
        i = edit_half * PAGE + n % PAGE
        if n < PAGE:  # bottom row: note <-> rest
            notes[i] = 0 if notes[i] else round(NOTE_PARAMS[i].val)
        else:  # top row: normal -> accent -> slide -> both
            state = (vels[i] > 100) + 2 * bool(slides[i])
            state = (state + 1) % 4
            vels[i] = 127 if state & 1 else 80
            slides[i] = state >> 1
        load_steps()
    elif sequencer.playing:
        transpose = n - 8
        set_transpose()
    else:
        note = 36 + n + transpose_oct * 12
        pad_notes[n] = note
        bass.note_on(note, PAD_VELOCITY)


def step_pad_released(n):
    note = pad_notes.pop(n, None)
    if note is not None:
        bass.note_off(note)


def check_pads():
    """Returns True if any pad changed, so the UI pass can skip a refresh."""
    global last_steps, last_touched, pat_scrolled
    steps = s.touched_steps
    touched = s.touched
    changed = steps != last_steps or touched != last_touched
    for n in range(16):
        if steps[n] != last_steps[n]:
            if steps[n]:
                step_pad_pressed(n)
            else:
                step_pad_released(n)
    # on release, so a hold that scrolled with the encoder doesn't also step
    for pad, d in ((RSLIDE_A, -1), (RSLIDE_C, 1)):
        if touched[pad] and not last_touched[pad]:
            pat_scrolled = False
        elif last_touched[pad] and not touched[pad] and not pat_scrolled:
            set_seq((seq_num + d) % len(seqs))
    if touched[LSLIDE_B] and not last_touched[LSLIDE_B]:
        set_edit_half(1 - edit_half)
    last_steps = steps
    last_touched = touched
    return changed


def check_buttons():
    global transpose_oct
    if s.encoder_button.pressed:
        if sequencer.playing:
            sequencer.stop()
            save()
        else:
            sequencer.start()
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if d:
        transpose_oct = min(max(transpose_oct + d, -2), 3)
        set_transpose()


def check_encoder():
    global enc_last, bpm, spb, pat_scrolled
    pos = s.encoder.position
    d = enc_last - pos  # this encoder counts down going clockwise
    enc_last = pos
    if not d:
        return
    if last_touched[LSLIDE_A]:
        bpm = min(max(bpm + d, 30), 240)
        set_tempo()
    elif last_touched[LSLIDE_C]:
        i = SPB_ALLOWED.index(spb) + d
        spb = SPB_ALLOWED[min(max(i, 0), len(SPB_ALLOWED) - 1)]
        set_tempo()
    elif last_touched[RSLIDE_A] or last_touched[RSLIDE_C]:
        pat_scrolled = True
        set_seq((seq_num + d) % len(seqs))
    else:
        set_mode((mode + d) % 3)


def update_pots():
    global pair
    knobs = s.pots
    if mode == MODE_EDIT:
        notes = seqs[seq_num][0]
        first = edit_half * PAGE
        before = [p.val for p in NOTE_PARAMS]
        note_set.update_knobs(knobs)
        moved = False
        for i in range(first, first + PAGE):
            p = NOTE_PARAMS[i]
            if p.val != before[i]:
                notes[i] = round(p.val)
                moved = True
        if moved:
            load_steps()
        return
    first = param_set.idx * param_set.nknobs
    page = PARAMS[first : first + param_set.nknobs]
    before = [p.val for p in page]
    param_set.update_knobs(knobs)
    for i, p in enumerate(page):
        if p.val != before[i]:
            apply_param(p)
            pair = i // 2
    ui.show_params(page[pair * 2], page[pair * 2 + 1])


def update_leds(half, step):
    first = half * PAGE
    notes, vels, slides = seqs[seq_num]
    leds = [0] * 16
    if mode == MODE_EDIT:
        for i in range(PAGE):
            leds[i] = 0x333333 if notes[first + i] else 0
            accent = 0x330000 if vels[first + i] > 100 else 0
            slide = 0x000033 if slides[first + i] else 0
            leds[i + PAGE] = accent | slide
    else:
        for n in range(16):
            if last_steps[n]:
                leds[n] = 0x00AAFF
    s.step_leds = leds
    pots = [0] * PAGE
    if step is not None and step // PAGE == half:
        pots[step % PAGE] = 0x333333
    s.pot_leds = pots
    s.edit_led = 0x333333 if mode == MODE_EDIT else 0
    s.mode_led = 0x333333 if mode == MODE_MORE else 0
    beat = step is not None and step % spb == 0
    s.play_led = 0x333333 if beat or not sequencer.playing else 0
    s.leds.show()


def update_ui():
    update_pots()
    step = None
    if sequencer.playing:
        step = (sequencer.i - 1) % STEP_COUNT  # .i has already advanced
    # edit mode stays on the half being edited; otherwise follow the playhead
    if mode == MODE_EDIT:
        half = edit_half
    else:
        half = 0 if step is None else step // PAGE
    first = half * PAGE
    on_page = step is not None and step // PAGE == half
    ui.show_beat(step % PAGE if on_page else None)
    ui.show_half(half)
    ui.show_status(bpm, spb, sequencer.transpose, seq_num)
    ui.show_seq(*(row[first : first + PAGE] for row in seqs[seq_num]))
    update_leds(half, step)


set_mode(MODE_PLAY)

while True:
    sequencer.update()
    s.update()
    pads_changed = check_pads()
    check_buttons()
    check_encoder()

    now = time.monotonic()
    if now - last_ui > UI_INTERVAL:
        last_ui = now
        update_ui()
        # not on a pass that just built a voice
        if ui.dirty and not pads_changed:
            s.display.refresh()
            ui.dirty = False
