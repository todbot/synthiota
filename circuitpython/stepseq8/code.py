# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# stepseq8 -- 8-track MIDI step sequencer on Synthiota, in the manner of
#             picostepseq, with tracks up to 32 steps of any length
#
#   encoder tap ............... play / pause (pause saves to /stepseq8.dat)
#   encoder long hold ......... stop and rewind
#   encoder turn .............. transpose this track
#   encoder push + turn ....... bpm
#   step pads ................. top row steps 1-8, bottom row steps 9-16
#   step pad tap, playing ..... mute / unmute step
#   step pad press, paused .... play step's note
#   hold step pad + turn ...... step's note
#   hold step pad + push+turn . step's gate
#   hold step pad + up/down ... step's velocity
#   encoder push + bottom pad . load pattern 1-8; hold pad 1 sec to save
#   up / down ................. next / previous track
#   right slider ends ......... steps 1-16 / 17-32
#   left slider ends .......... track view / all-tracks view
#   all-tracks view ........... top pads select track, bottom pads mute
#   pots ...................... LEN DIV CHN TRN VEL GAT PRB BPM of this track

import gc

import relic_synthiota
import tmidi
from adafruit_ticks import ticks_diff, ticks_ms
from stepseq8_seq import (
    BPM_MAX,
    BPM_MIN,
    DIV_NAMES,
    DIV_TICKS,
    GATE_MAX,
    MAX_STEPS,
    NUM_TRACKS,
    PPQN,
    StepSeq8,
    clamp,
)
from stepseq8_ui import PAGE_STEPS, SeqUI
from synthtools.paramset import Param, ParamSet

SAVE_FILE = "/stepseq8.dat"
SHOW_TIMING = False  # print slowest pass and clock rate, every 5 secs
INPUT_MS = 10
UI_MS = 40
UI_MAX_MS = 200  # draw even if no step fired, slow divisions leave long gaps
SAVE_MIN_MS = 20_000  # flash wears out, and the write blocks
TAP_MS = 500
HOLD_MS = 1000
POT_HELD_MS = 500
READOUT_MS = 1500
NOTE_MIN, NOTE_MAX = 1, 127
TRANSPOSE_MAX = 36
VEL_STEP = 10

VIEW_TRACK, VIEW_ALL = 0, 1

# touch ids, see relic_synthiota's pad defs
LSLIDE_A = 23  # left slider, left end
LSLIDE_C = 21  # left slider, right end
RSLIDE_A = 12  # right slider, left end
RSLIDE_C = 14  # right slider, right end

WHITE = 0x444444
SELECTED = 0x111111
TRACK_COLORS = (0x660000, 0x662200, 0x444400, 0x006600,
                0x004444, 0x000066, 0x330066, 0x660033)
TRACK_DIMS = tuple((c >> 3) & 0x1F1F1F for c in TRACK_COLORS)

s = relic_synthiota.Synthiota(channel_count=1)  # audio's unused, keep it small
s.display.auto_refresh = False
s.leds.auto_write = False
s.leds.brightness = 0.2

out_msg = tmidi.Message()


def send(mtype, data0, data1, channel):
    out_msg.type = mtype
    out_msg.data0 = data0
    out_msg.data1 = data1
    out_msg.channel = channel
    s.send_midi_message(out_msg)


eng = StepSeq8(send)
tracks = eng.tracks


def default_pattern():
    # fmt: off
    arp = (48, 55, 60, 63, 67, 63, 60, 55, 48, 55, 60, 65, 68, 65, 60, 55)
    bass = (36, 36, 48, 36, 34, 34, 46, 34, 41, 41, 53, 41, 43, 43, 55, 43)
    # fmt: on
    for steps, notes in ((tracks[0].seq.steps, arp), (tracks[1].seq.steps, bass)):
        for i, note in enumerate(notes):
            steps[i][:] = [note, 100, 0.5, True]


if not eng.read_file(SAVE_FILE):
    default_pattern()
    eng.init_slots()

# --- the pots: one knobset per track, BPM shared by them all --------------
LABELS = ("LEN", "DIV", "CHN", "TRN", "VEL", "GAT", "PRB", "BPM")
SHORT_LABELS = ("LN", "DV", "CH", "TR", "VL", "GT", "PR", "BP")
P_LEN, P_DIV, P_CHN, P_TRN, P_VEL, P_GAT, P_PRB, P_BPM = range(8)
NUM_POTS = len(LABELS)

bpm_param = Param("BPM", eng.bpm, BPM_MIN, BPM_MAX, "%d")


def pot_get(t, i):
    return (t.length, t.div, t.chan + 1, t.transpose,
            t.level, t.gate, t.prob, eng.bpm)[i]  # fmt: skip


def pot_set(t, i, val):
    if i == P_LEN:
        t.length = val
    elif i == P_DIV:
        t.div = val
        t.set_tempo(eng.bpm)
    elif i == P_CHN:
        t.chan = val - 1
    elif i == P_TRN:
        t.transpose = val
    elif i == P_VEL:
        t.level = val
    elif i == P_GAT:
        t.set_gates(val)
    elif i == P_PRB:
        t.prob = val
    else:
        eng.set_bpm(val)


def pot_text(i, val):
    if i == P_DIV:
        return DIV_NAMES[val]
    if i == P_TRN:
        return "%+d" % val
    if i == P_GAT:
        return str(val * 100 // GATE_MAX)
    return str(val)


_params = []
for _t in tracks:
    _params += [
        Param("LEN", _t.length, 1, MAX_STEPS, "%d"),
        Param("DIV", _t.div, 0, len(DIV_TICKS) - 1, "%d"),
        Param("CHN", _t.chan + 1, 1, 16, "%d"),
        Param("TRN", _t.transpose, -TRANSPOSE_MAX, TRANSPOSE_MAX, "%d"),
        Param("VEL", _t.level, 0, 100, "%d"),
        Param("GAT", _t.gate, 1, GATE_MAX, "%d"),
        Param("PRB", _t.prob, 0, 100, "%d"),
        bpm_param,
    ]
# knob_deadband well above a muxed synthiota pot's ~0.004 rest jitter
param_set = ParamSet(_params, num_knobs=NUM_POTS, knob_mode=ParamSet.KNOB_SCALE,
                     knob_deadband=0.012)


def readopt_pots():
    """A value moved under the pots, so they must not jump it back."""
    param_set.is_tracking = [False] * NUM_POTS
    param_set.knob_pos_last = None


def sync_params():
    """The tracks changed, as in a pattern load, make the pots agree."""
    for n, t in enumerate(tracks):
        for i in range(NUM_POTS - 1):
            _params[n * NUM_POTS + i].val = pot_get(t, i)
    bpm_param.val = eng.bpm
    readopt_pots()


# --- the UI ---------------------------------------------------------------
ui = SeqUI(s.display)
view = VIEW_TRACK
cur = 0  # selected track
page = 0
held = None  # step on this page being held
held_edited = False
previewing = False
slot_pad = None  # bottom pad held to load / save a pattern
slot_t = 0
enc_held = False
enc_used = False  # turned or combined while down, so not a tap
enc_t = 0
enc_last = s.encoder.position
last_steps = s.touched_steps
last_touched = s.touched
pot_moved = [ticks_ms() - 10_000] * NUM_POTS
last_pot = None  # pot to title, for READOUT_MS after pot_moved
last_input = last_ui = last_save = last_timing = ticks_ms()
ever_saved = False
gc_due = False
slowest_draw = slowest_refresh = 0
ticks_counted = 0


def pad_step(n):
    """Which step of this page a pad is, relic numbers the bottom row first."""
    return (n + 8) % PAGE_STEPS


def select_track(n):
    global cur, last_pot
    cur = n
    last_pot = None
    param_set.idx = n
    param_set.knob_pos_last = None


def step_pad_pressed(n, now):
    global held, held_edited, previewing, slot_pad, slot_t, enc_used
    t = tracks[cur]
    if enc_held:
        enc_used = True
        if n < 8:
            slot_pad = n
            slot_t = now
    elif view == VIEW_ALL:
        if n >= 8:
            select_track(n - 8)
        else:
            tracks[n].muted = not tracks[n].muted
            eng.dirty = True
    elif held is None:
        held = pad_step(n)
        held_edited = False
        if not eng.playing:
            t.preview(page * PAGE_STEPS + held)
            previewing = True


def step_pad_released(n):
    global held, previewing, slot_pad
    t = tracks[cur]
    if n == slot_pad:
        slot_pad = None
        eng.load_slot(n)
        ui.toast("LOADED %d" % (n + 1), ticks_ms())
    if pad_step(n) == held:
        step = t.seq.steps[page * PAGE_STEPS + held]
        held = None
        if previewing:
            t.release()
            previewing = False
        elif not held_edited:
            step[3] = not step[3]
            eng.dirty = True


def check_pads(now):
    global last_steps, last_touched, slot_pad, view, page
    steps = s.touched_steps
    touched = s.touched
    for n in range(16):
        if steps[n] != last_steps[n]:
            if steps[n]:
                step_pad_pressed(n, now)
            else:
                step_pad_released(n)
    if touched[LSLIDE_A] and not last_touched[LSLIDE_A]:
        view = VIEW_TRACK
    if touched[LSLIDE_C] and not last_touched[LSLIDE_C]:
        view = VIEW_ALL
    if touched[RSLIDE_A] and not last_touched[RSLIDE_A]:
        page = 0
    if touched[RSLIDE_C] and not last_touched[RSLIDE_C]:
        page = 1
    last_steps = steps
    last_touched = touched
    if slot_pad is not None and ticks_diff(now, slot_t) >= HOLD_MS:
        eng.save_slot(slot_pad)
        ui.toast("SAVED %d" % (slot_pad + 1), now)
        slot_pad = None


def check_buttons(now):
    global enc_held, enc_used, enc_t, held_edited
    if s.encoder_button.pressed:
        enc_held = True
        enc_used = held is not None
        enc_t = now
    if s.encoder_button.released:
        enc_held = False
        if not enc_used and held is None and ticks_diff(now, enc_t) < TAP_MS:
            if eng.playing:
                eng.pause()
            else:
                eng.play()
    if enc_held and not enc_used and held is None and ticks_diff(now, enc_t) >= HOLD_MS:
        enc_used = True
        eng.stop()
        ui.toast("REWOUND", now)
    d = 1 if s.up_button.pressed else -1 if s.down_button.pressed else 0
    if d:
        if held is not None:
            step = tracks[cur].seq.steps[page * PAGE_STEPS + held]
            step[1] = clamp(step[1] + d * VEL_STEP, 1, 127)
            held_edited = True
            eng.dirty = True
        else:
            select_track((cur + d) % NUM_TRACKS)


def pot_touched(i, now):
    global last_pot
    pot_moved[i] = now
    last_pot = i


def check_encoder(now):
    global enc_last, enc_used, held_edited
    pos = s.encoder.position
    d = enc_last - pos  # this encoder counts down going clockwise
    enc_last = pos
    if not d:
        return
    enc_used = True
    t = tracks[cur]
    eng.dirty = True
    if held is not None:
        held_edited = True
        step = t.seq.steps[page * PAGE_STEPS + held]
        if enc_held:
            gate = round(step[2] * GATE_MAX)
            step[2] = clamp(gate + d, 1, GATE_MAX) / GATE_MAX
        else:
            step[0] = clamp(step[0] + d, NOTE_MIN, NOTE_MAX)
            if previewing:
                t.preview(page * PAGE_STEPS + held)
    elif enc_held:
        eng.set_bpm(clamp(eng.bpm + d, BPM_MIN, BPM_MAX))
        bpm_param.val = eng.bpm
        readopt_pots()
        pot_touched(P_BPM, now)
    else:
        t.transpose = clamp(t.transpose + d, -TRANSPOSE_MAX, TRANSPOSE_MAX)
        _params[cur * NUM_POTS + P_TRN].val = t.transpose
        readopt_pots()
        pot_touched(P_TRN, now)


def update_pots(now):
    if eng.loading:  # the params are stale until sync_params()
        return
    if eng.ext_clock:  # MIDI clock sets the tempo, not this param
        bpm_param.val = eng.bpm
    param_set.update_knobs(s.pots)
    t = tracks[cur]
    first = cur * NUM_POTS
    for i in range(NUM_POTS):
        # round(), not int(): a full-scale knob sits a hair under vmax
        val = round(_params[first + i].val)
        if val != pot_get(t, i):
            pot_set(t, i, val)
            pot_touched(i, now)
            eng.dirty = True


def pot_views(now):
    knobs = s.pots
    t = tracks[cur]
    first = cur * NUM_POTS
    views = []
    for i in range(NUM_POTS):
        p = _params[first + i]
        views.append((SHORT_LABELS[i], (p.val - p.vmin) / p.span, knobs[i],
                      ticks_diff(now, pot_moved[i]) < POT_HELD_MS))
    return views


def pot_readout(now):
    if last_pot is None or ticks_diff(now, pot_moved[last_pot]) >= READOUT_MS:
        return None
    text = pot_text(last_pot, pot_get(tracks[cur], last_pot))
    return LABELS[last_pot] + " " + text


def update_leds():
    t = tracks[cur]
    fired = [tr.fired for tr in tracks]
    for tr in tracks:
        tr.fired = False
    leds = [0] * 16
    if view == VIEW_TRACK:
        steps = t.seq.steps
        for n in range(16):
            i = page * PAGE_STEPS + pad_step(n)
            if pad_step(n) == held:
                leds[n] = TRACK_COLORS[cur]
            elif i == t.pos:
                leds[n] = WHITE
            elif i < t.length and steps[i][3]:
                leds[n] = TRACK_DIMS[cur]
    else:
        for n in range(NUM_TRACKS):
            if not tracks[n].muted:
                leds[n] = TRACK_COLORS[n] if fired[n] else TRACK_DIMS[n]
            leds[n + 8] = WHITE if n == cur else TRACK_DIMS[n]
    s.step_leds = leds
    s.pot_leds = [TRACK_COLORS[n] if fired[n] else SELECTED if n == cur else 0
                  for n in range(NUM_TRACKS)]
    s.play_led = WHITE if not eng.playing or eng.tick % PPQN < PPQN // 4 else 0
    s.mode_led = WHITE if eng.ext_clock else 0
    s.edit_led = WHITE if held is not None else 0
    s.leds.show()


def draw_ui(now):
    ui.expire_toast(now)
    if view == VIEW_TRACK:
        ui.draw_track(cur, tracks[cur], page, held, eng.pattern, eng.bpm, eng.playing,
                      eng.ext_clock, pot_readout(now), pot_views(now))
    else:
        ui.draw_all(tracks, cur)
    update_leds()


def maybe_save(now):
    global last_save, ever_saved
    if not eng.dirty or eng.playing:
        return
    if ever_saved and ticks_diff(now, last_save) < SAVE_MIN_MS:
        return
    ever_saved = True
    last_save = now
    try:
        eng.write_file(SAVE_FILE)
        ui.toast("SAVED", ticks_ms())  # the write blocks, don't count it against the toast
    except OSError:
        eng.dirty = False  # only ask once
        ui.toast("NOT SAVED", now)
        print("could not write", SAVE_FILE, "-- needs boot.py's remount")


print("stepseq8: tap the encoder to play")

while True:
    for msg in s.get_midi_messages():
        eng.midi_rt(msg.type)
    eng.update()

    now = ticks_ms()
    if ticks_diff(now, last_input) >= INPUT_MS:
        last_input = now
        s.update()
        check_pads(now)
        check_buttons(now)
        check_encoder(now)
        update_pots(now)
        eng.update()

    was_loading = eng.loading
    eng.service()
    if was_loading and not eng.loading:
        sync_params()

    since = ticks_diff(now, last_ui)
    if since >= UI_MS and (not eng.playing or eng.fired or since >= UI_MAX_MS):
        eng.fired = False
        last_ui = now
        draw_ui(now)
        t_drawn = ticks_ms()
        eng.update()
        if ui.dirty:
            s.display.refresh()
            ui.dirty = False
        if SHOW_TIMING:
            t_done = ticks_ms()
            slowest_draw = max(slowest_draw, ticks_diff(t_drawn, now))
            slowest_refresh = max(slowest_refresh, ticks_diff(t_done, t_drawn))
        maybe_save(now)
        gc_due = True
    elif gc_due and since >= UI_MS // 2:  # away from a step, and from the refresh
        gc_due = False
        gc.collect()

    if SHOW_TIMING and ticks_diff(now, last_timing) >= 5000:
        print("draw %d ms, refresh %d ms, %d ticks, free %d" % (slowest_draw, slowest_refresh,
                                                                eng.ticks_total - ticks_counted,
                                                                gc.mem_free()))
        last_timing = now
        slowest_draw = slowest_refresh = 0
        ticks_counted = eng.ticks_total
