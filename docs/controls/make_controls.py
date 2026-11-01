#!/usr/bin/env python3
"""make_controls.py -- draw a control map of the synthiota board for each
app, as docs/controls/<app>.png.

  python3 make_controls.py            # all apps
  python3 make_controls.py wavesynth  # just one

Part positions are in mm, from schematics/synthiota1/synthiota1.kicad_pcb.
The background is docs/synthiota_render_front.png, a top-down render
cropped to the board edge; without it the board is drawn.
Needs Pillow and the macOS system fonts.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

HERE = Path(__file__).resolve().parent
RENDER = HERE.parent / "synthiota_render_front.png"
FONTS = "/System/Library/Fonts/"

# board edge, mm
BX0, BY0, BX1, BY1 = 17.4, 15.4, 195.2, 129.7
S = 11  # px per mm
MARGIN = 70
TOP = 300  # title and callouts

POT_X = [36.4 + 20 * i for i in range(8)]
POT_Y = 59.9
PAD_X = POT_X
PAD_TOP_Y, PAD_BOT_Y = 96.5, 116.5
PAD = 12.7
SLIDE_L = (30.5, 78.1, 49.1, 8.0)  # x, y, w, h
SLIDE_R = (132.5, 77.9, 50.0, 8.0)
UP_XY, DOWN_XY = (98, 82.4), (114, 82.4)
ENC_XY = (140.1, 38.9)
STATUS = (("edit", 155.4), ("mode", 164.4), ("play", 173.4))
STATUS_Y = 43.2
DISP = (106.4, 32.8, 35.6, 35.5)  # centre x, y, w, h
JACKS = (("MIDI IN", 132.4), ("MIDI OUT", 147.4), ("AUDIO OUT", 164.4))
HOLES = ((19.94, 17.94), (192.66, 17.94), (19.94, 127.16), (192.66, 127.16))

PAGE_COLORS = ("#5ad1ff", "#ffc04d", "#ff7ad9")
BG = "#ececef"
BOARD = "#1b1d22"
SILK = "#d8d8d8"
TEXT = "#ffffff"
CAPTION = "#c9ced8"
BACKING = (12, 13, 16, 215)
INK = "#1b1d22"
LEADER = "#9aa0aa"


def font(size, face="cond", weight="demi"):
    files = {"cond": "Avenir Next Condensed.ttc", "sans": "Avenir Next.ttc"}
    index = {"bold": 0, "demi": 2, "medium": 5, "regular": 7}
    return ImageFont.truetype(FONTS + files[face], size, index=index[weight])


def px(x, y):
    return (MARGIN + (x - BX0) * S, TOP + (y - BY0) * S)


def mm(v):
    return v * S


# --- the apps ----------------------------------------------------------
# Board labels are short; "legend" is the README's controls list.

APPS = {
    "wavesynth": dict(
        title="wavesynth",
        subtitle="wavetable polysynth, 24 params over 3 pages",
        pages=(
            ("WAVE", "freq reso wpos wsel wlfo wrate atk rel"),
            ("ENV/FILT", "fatk frel famt ftype lamt lrate vdep vol"),
            ("KEY/MOD", "scale key dec sus vdly vrate pamt ptime"),
        ),
        top=("root", "oct", "5th", "triad", "7th", "9th", "sus", "spread"),
        top_caption="chord on the last bottom pad",
        bottom=["deg\n%d" % (i + 1) for i in range(8)],
        bottom_caption="scale degrees, one note each",
        up="octave\nup", down="octave\ndown",
        lslider="filter cutoff",
        rslider="wavetable position",
        encoder=("turn: previous / next page",
                 "hold + bottom pad: load patch 1-8"),
        screen="page +\nlast-turned pair",
        legend=(
            ("bottom pads (1-8)", "the 8 scale degrees, one note each"),
            ("top pads (9-16)", "chord on the last bottom pad: root, oct, "
             "5th, triad, 7th, 9th, sus, spread (all diatonic)"),
            ("8 pots", "8 params at once; screen shows the last-turned pair"),
            ("encoder turn", "previous / next page"),
            ("encoder HOLD + bottom pad", "load patch 1..8"),
            ("up / down buttons", "octave down / up"),
            ("left slider", "nudge filter cutoff (while touched)"),
            ("right slider", "wavetable position (while touched)"),
            ("pot LEDs", "all 8 param values on this page"),
            ("step LEDs", "currently held pads"),
        ),
    ),
    "polysynth": dict(
        title="polysynth",
        subtitle="two-oscillator subtractive polysynth, 16 params over 2 pages",
        pages=(
            ("OSC/AMP", "wave detun freq reso atk dec sus rel"),
            ("FILT/MOD", "ftype eamt eatk erel lamt lrate vrate vdep"),
        ),
        top=("G#", "A", "A#", "B", "C", "C#", "D", "D#"),
        top_caption="the keyboard continues",
        bottom=("C", "C#", "D", "D#", "E", "F", "F#", "G"),
        bottom_caption="chromatic keyboard, 16 notes",
        up="octave\nup", down="octave\ndown",
        lslider="filter cutoff",
        rslider="vibrato depth",
        encoder=("turn: previous / next page",),
        screen="page +\nlast-turned pair",
        legend=(
            ("step pads", "chromatic keyboard (16 notes)"),
            ("8 pots", "8 params at once; screen shows the last-turned pair"),
            ("encoder turn", "previous / next page"),
            ("up / down buttons", "octave down / up (C1 .. C5)"),
            ("left slider", "nudge filter cutoff (while touched)"),
            ("right slider", "vibrato depth (while touched)"),
            ("pot LEDs", "all 8 param values on this page"),
            ("step LEDs", "currently held notes"),
        ),
    ),
    "swarmsynth": dict(
        title="swarmsynth",
        subtitle="Swarmatron-style drone: eight oscillators on one pitch",
        pages=(("SWARM", "spred drift count wave freq reso glide rel"),),
        top=("-24", "-12", "-7", "home", "+7", "+12", "+19", "+24"),
        top_caption="transpose the drone, in semitones",
        bottom=["deg\n%d" % (i + 1) for i in range(8)],
        bottom_caption="scale degrees (natural minor)",
        up="octave\nup", down="octave\ndown",
        lslider="filter cutoff",
        rslider="swarm spread",
        encoder=("turn: octave down / up", "press: latch on / off"),
        status=("play: lit while latched",),
        screen="last-turned pair",
        legend=(
            ("bottom pads (1-8)", "the 8 scale degrees (natural minor), one note each"),
            ("top pads (9-16)", "transpose the drone: -24 -12 -7 0 +7 +12 +19 +24 "
             "semitones (pad 12 is home)"),
            ("8 pots", "8 params at once; screen shows the last-turned pair"),
            ("up / down buttons", "octave down / up (C1 .. C5)"),
            ("encoder turn", "octave down / up (same as the buttons)"),
            ("encoder press", "latch on / off -- the drone keeps sounding after "
             "you let go, so both hands are free for the knobs"),
            ("left slider", "nudge filter cutoff (while touched)"),
            ("right slider", "the span ribbon: swarm spread (while touched)"),
            ("pot LEDs", "all 8 param values"),
            ("step LEDs", "held / latched degree, and the chosen transposition"),
            ("play LED", "lit while latched"),
        ),
    ),
    "dronesynth": dict(
        title="dronesynth",
        subtitle="eight drone oscillators, each tuned by its own knob",
        pages=(
            ("turn", ["osc %d pitch" % (i + 1) for i in range(8)]),
            ("+ hold top pad", ["LFO depth"] * 8),
        ),
        top=["LFO\n%d" % (i + 1) for i in range(8)],
        top_caption="tap: LFO off -> pitch -> volume -> both",
        bottom=["osc\n%d" % (i + 1) for i in range(8)],
        bottom_caption="tap: osc in / out;  hold + up / down: its octave",
        up="start\noctave up", down="start\noctave down",
        lslider="tap end: cutoff - / +",
        rslider="tap end: depth master - / +",
        encoder=("turn: waveform", "press: pitch snap on / off",
                 "hold top pad + turn: LFO rate", "hold top pad + press: LFO shape"),
        status=("mode: pitch snap on", "edit: a pad is steering",
                "play: any osc in"),
        screen="osc notes\n+ LFO modes",
        legend=(
            ("8 pots", "oscillator pitch, 2 octaves per pot"),
            ("bottom pads", "tap: oscillator in / out; hold + up/down: shift that "
             "oscillator by an octave, up to two either way"),
            ("top pads", "tap: LFO off -> pitch -> volume -> both -> off; "
             "hold + encoder turn: that LFO's rate; hold + encoder press: that "
             "LFO's shape, cycling TRI D10 D30 D50 D70 D90; hold + its own pot: "
             "the depth of what that LFO drives, or both depths while it is off"),
            ("encoder turn", "waveform, when no top pad is held"),
            ("encoder press", "pitch snap: semitones / free, no top pad held"),
            ("up / down", "the octave all eight pots start from; oscillator 1-2 "
             "lands on C0, C1, C2 or C3 and the rest sit above it"),
            ("left slider", "tap an end: filter cutoff down / up"),
            ("right slider", "tap an end: the depth master, over all sixteen "
             "depths at once, down / up; hold either end and it repeats"),
            ("bottom LEDs", "amber where an oscillator is in"),
            ("top LEDs", "green pitch LFO, blue volume LFO, cyan both, pulsing at "
             "its own rate; white while a knob or the encoder is steering it"),
            ("pot LEDs", "the eight pot positions, magenta on the one knob that is "
             "setting a depth, showing that depth"),
            ("mode LED", "lit while pitch snap is on"),
            ("edit LED", "lit while a held pad is steering an LFO"),
            ("play LED", "lit while any oscillator is in"),
        ),
    ),
    "dronesynth_wt": dict(
        title="dronesynth_wt",
        subtitle="dronesynth with each oscillator in its own place in a wavetable",
        pages=(
            ("turn", ["osc %d pitch" % (i + 1) for i in range(8)]),
            ("+ hold bottom pad", ["volume"] * 8),
            ("+ hold top pad", ["LFO depth"] * 8),
        ),
        top=["LFO\n%d" % (i + 1) for i in range(8)],
        top_caption="tap: LFO off -> wave -> volume -> both",
        bottom=["osc\n%d" % (i + 1) for i in range(8)],
        bottom_caption="tap: osc in / out;  hold + up / down: its octave",
        up="start\noctave up", down="start\noctave down",
        lslider="tap end: cutoff - / +",
        rslider="tap end: depth master - / +",
        encoder=("turn: wavetable", "press: pitch snap on / off",
                 "hold top pad + turn: LFO rate", "hold top pad + press: LFO shape"),
        status=("mode: pitch snap on", "edit: a pad is steering",
                "play: any osc in"),
        screen="wavetable,\nosc notes + LFOs",
        legend=(
            ("8 pots", "oscillator pitch, 2 octaves per pot"),
            ("bottom pads", "tap: oscillator in / out; hold + its own pot: that "
             "oscillator's volume; hold + up/down: shift that oscillator by an "
             "octave, up to two either way"),
            ("top pads", "tap: LFO off -> wave -> volume -> both -> off; hold + "
             "encoder turn: the rate of the LFO that oscillator drives, or both "
             "while it is off; hold + encoder press: that LFO's shape, cycling "
             "TRI D10 D30 D50 D70 D90; hold + its own pot: the depth of what that "
             "LFO drives, or both of them while it is off"),
            ("both pads", "hold + its own pot: where in the table that oscillator "
             "starts"),
            ("encoder turn", "the wavetable, when no top pad is held"),
            ("encoder press", "pitch snap: semitones / free, no top pad held"),
            ("up / down", "the octave all eight pots start from; oscillator 1-2 "
             "lands on C0, C1, C2 or C3 and the rest sit above it"),
            ("left slider", "tap an end: filter cutoff down / up"),
            ("right slider", "tap an end: the depth master, over all sixteen "
             "depths at once, down / up; hold either end and it repeats"),
            ("bottom LEDs", "amber where an oscillator is in"),
            ("top LEDs", "green wave LFO, blue volume LFO, cyan both, each pulsing "
             "at its own rate; white while a knob or the encoder is steering it"),
            ("pot LEDs", "where each oscillator is in the table, white on the one "
             "knob that is moving where it starts, amber on the one setting a "
             "volume, magenta on the one setting a depth"),
            ("mode LED", "lit while pitch snap is on"),
            ("edit LED", "lit while a held pad is steering"),
            ("play LED", "lit while any oscillator is in"),
        ),
    ),
    "tbish2": dict(
        title="tbish2",
        subtitle="TB-303-style acid bassline with a 16-step sequencer",
        pages=(
            ("play mode", "cutoff envmod resQ decay accent wave drive delaymix"),
            ("more mode", "ampdec amplevel acctcut acctQ slide drvamt dtime dlyfeed"),
            ("edit mode", ["note %d" % (i + 1) for i in range(8)]),
        ),
        top=["step %d" % (i + 1) for i in range(8)],
        top_caption="edit: normal -> accent -> slide -> both;  playing: transpose (pad 9 home)",
        bottom=["step %d" % (i + 1) for i in range(8)],
        bottom_caption="edit: step note <-> rest;  stopped: play the synth",
        up="transpose\noctave up", down="transpose\noctave down",
        lslider="bpm | 1-8 / 9-16 | steps/beat",
        rslider="prev | next pattern",
        encoder=("turn: next / previous mode", "push: play / pause (saves)"),
        status=("edit: edit mode", "mode: more mode", "play: the beat"),
        screen="mode, pattern\n+ last-turned pair",
        legend=(
            ("encoder turn", "next / previous mode"),
            ("encoder push", "play / pause; pausing saves to /tbish2.json"),
            ("step pads, playing", "transpose the pattern (pad 9 is home)"),
            ("step pads, stopped", "play the synth"),
            ("step pads, edit mode", "bottom row: step note <-> rest; top row: "
             "normal -> accent -> slide -> both"),
            ("up / down buttons", "transpose up / down an octave"),
            ("right slider, left end", "previous pattern"),
            ("right slider, right end", "next pattern"),
            ("hold either right slider end, turn encoder", "scroll patterns"),
            ("left slider, middle", "edit steps 1-8 / 9-16"),
            ("hold left slider left end, turn encoder", "bpm"),
            ("hold left slider right end, turn encoder", "steps per beat"),
            ("pot LEDs", "current step, if on the shown half"),
            ("step LEDs", "held pads; in edit mode, the pattern (white = note, "
             "red = accent, blue = slide)"),
        ),
    ),
    "tbish": dict(
        title="tbish",
        subtitle="TB-303-style synth, the original technology demo",
        pages=(
            ("play page", "Freq EnvMod ResQ Decay Accent Wave Drive Delay"),
            ("edit page", ["note %d" % (i + 1) for i in range(8)]),
        ),
        top=["step %d" % (i + 1) for i in range(8)],
        top_caption="edit: normal -> accent -> slide -> both;  playing: transpose (pad 9 home)",
        bottom=["step %d" % (i + 1) for i in range(8)],
        bottom_caption="edit: step on <-> rest;  stopped: play the synth",
        up="octave\nup", down="octave\ndown",
        lslider="bpm  |  steps/beat",
        rslider="next pattern",
        encoder=("turn: play / edit page", "push: play / stop"),
        screen="pattern\n+ params",
        legend=(
            ("encoder turn", "switch between the play and edit pages"),
            ("encoder push", "play / stop"),
            ("step pads, playing", "transpose the pattern (pad 9 is home)"),
            ("step pads, stopped", "play the synth"),
            ("step pads, edit page", "bottom row: step note on <-> rest; top "
             "row: normal -> accent -> slide -> both"),
            ("up / down buttons", "transpose up / down an octave"),
            ("right slider, right end", "next pattern"),
            ("hold left slider left end, turn encoder", "bpm"),
            ("hold left slider right end, turn encoder", "steps per beat"),
        ),
    ),
}


# --- drawing -------------------------------------------------------------

def label(d, xy, lines, fnt, fill, anchor="mm", spacing=1.12, backing=True):
    """Lines centred (or left/right anchored) on xy, on a dark backing."""
    if isinstance(lines, str):
        lines = lines.split("\n")
    h = fnt.size * spacing
    w = max(fnt.getlength(ln) for ln in lines)
    x, y = xy
    y0 = y - h * len(lines) / 2
    x0 = {"l": x, "m": x - w / 2, "r": x - w}[anchor[0]]
    if backing:
        pad = fnt.size * 0.3
        d.rounded_rectangle((x0 - pad, y0 - pad * 0.5, x0 + w + pad, y0 + h * len(lines) + pad * 0.5),
                            radius=pad, fill=BACKING)
    for i, ln in enumerate(lines):
        d.text((x, y0 + h * (i + 0.5)), ln, font=fnt, fill=fill, anchor=anchor[0] + "m")


def rrect(d, x, y, w, h, r, **kw):
    """Rounded rect from a top-left corner in mm."""
    x0, y0 = px(x, y)
    d.rounded_rectangle((x0, y0, x0 + mm(w), y0 + mm(h)), radius=mm(r), **kw)


def draw_board(img, d):
    x0, y0 = px(BX0, BY0)
    x1, y1 = px(BX1, BY1)
    if RENDER.exists():
        bg = Image.open(RENDER).convert("RGB").resize((round(x1 - x0), round(y1 - y0)), Image.LANCZOS)
        bg = ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(0.55)).enhance(0.8)
        mask = Image.new("L", bg.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *bg.size), radius=mm(2.54), fill=255)
        img.paste(bg, (round(x0), round(y0)), mask)
        return
    d.rounded_rectangle((x0, y0, x1, y1), radius=mm(2.54), fill=BOARD)
    for hx, hy in HOLES:
        cx, cy = px(hx, hy)
        d.ellipse((cx - mm(1.4), cy - mm(1.4), cx + mm(1.4), cy + mm(1.4)), fill=BG)
    rrect(d, 18.5, 22.8, 52, 21, 1, fill="#24432c", outline="#3d6b48", width=2)
    cx, cy, w, h = DISP
    rrect(d, cx - w / 2, cy - h / 2, w, h, 1.5, fill="#22324a", outline="#3a5a85", width=2)
    rrect(d, cx - 15, cy - 11, 30, 16, 0.5, fill="#07090c")
    rrect(d, 157.2, 15.8, 31.8, 17.6, 1, fill="#2a2d33", outline="#3c4049", width=2)
    f = font(20)
    for name, jx in JACKS:
        rrect(d, jx - 3, 15.6, 6, 9, 1, fill="#0d0e10", outline="#555", width=2)
        label(d, px(jx, 26.8), name, f, CAPTION, backing=False)
    cx, cy = px(*ENC_XY)
    r = mm(6)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#30333a", outline="#777", width=3)
    for name, lx in STATUS:
        rrect(d, lx - 1.2, STATUS_Y - 1.2, 2.4, 2.4, 0.3, fill="#eeeeee")
        label(d, px(lx, STATUS_Y + 3.4), name, f, CAPTION, backing=False)
    for x in POT_X:
        cx, cy = px(x, POT_Y)
        r = mm(4.6)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#0b0c0e", outline="#666", width=3)
        rrect(d, x - 1.2, 73.4 - 1.2, 2.4, 2.4, 0.3, fill="#eeeeee")
    for x, y, w, h in (SLIDE_L, SLIDE_R):
        rrect(d, x, y, w, h, 1.2, outline=SILK, width=2)
    for x, y in (UP_XY, DOWN_XY):
        rrect(d, x - 3.5, y - 3.5, 7, 7, 1, outline=SILK, width=2)
    for y in (PAD_TOP_Y, PAD_BOT_Y):
        for x in PAD_X:
            rrect(d, x - PAD / 2, y - PAD / 2, PAD, PAD, 2, outline=SILK, width=2)


def callout(d, anchor_mm, box_xy, lines, title, stop_mm=6.5):
    """A label in the top margin with a leader line down to the part."""
    f_t = font(34, "sans", "bold")
    f = font(32, "sans", "regular")
    bx, by = box_xy
    d.text((bx, by), title, font=f_t, fill=INK, anchor="lt")
    for i, ln in enumerate(lines):
        d.text((bx, by + 46 + i * 40), ln, font=f, fill=INK, anchor="lt")
    # straight down, so it passes between the jacks
    ax, ay = px(*anchor_mm)
    ly = by + 46 + len(lines) * 40 + 10
    d.line((bx - 14, by + 6, bx - 14, ly, ax, ly, ax, ay - mm(stop_mm)), fill=LEADER, width=4)


def wrap(text, f, width):
    lines, ln = [], ""
    for word in text.split():
        t = (ln + " " + word).strip()
        if f.getlength(t) > width and ln:
            lines.append(ln)
            t = word
        ln = t
    return lines + [ln]


def legend_cols(app, width_px, f, f_b):
    """The legend as two columns of (key_w, [(key, [lines])])."""
    items = app["legend"]
    half = (len(items) + 1) // 2
    cols = []
    for part in (items[:half], items[half:]):
        # a key longer than this sits on its own line, over its text
        cap = width_px * 0.4
        key_w = max((f_b.getlength(k) for k, _ in part if f_b.getlength(k) <= cap), default=0) + 24
        cols.append((key_w, [(k, wrap(v, f, width_px - key_w)) for k, v in part]))
    return cols


def draw_app(name, app):
    board_w = mm(BX1 - BX0)
    board_h = mm(BY1 - BY0)
    f_leg, f_leg_b = font(30, "sans", "regular"), font(30, "sans", "demi")
    col_w = (board_w - 60) / 2
    cols = legend_cols(app, col_w, f_leg, f_leg_b)
    line_h = 42
    n_lines = max(sum(len(v) + (f_leg_b.getlength(k) > key_w - 24) for k, v in rows)
                  for key_w, rows in cols)
    leg_h = (n_lines + 2) * line_h + 50

    W = round(board_w + 2 * MARGIN)
    H = round(TOP + board_h + leg_h + 40)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")

    d.text((MARGIN, 40), app["title"], font=font(76, "sans", "bold"), fill=INK, anchor="lt")
    d.text((MARGIN, 140), app["subtitle"], font=font(36, "sans", "regular"), fill=INK, anchor="lt")
    pages = app.get("pages", ())
    if len(pages) > 1:
        f = font(32, "sans", "demi")
        x, y = MARGIN, 214
        lead = "pot labels:"
        d.text((x, y), lead, font=f, fill=INK, anchor="lm")
        x += f.getlength(lead) + 20
        for (pname, _), col in zip(pages, PAGE_COLORS):
            w = f.getlength(pname)
            d.rounded_rectangle((x, y - 26, x + w + 28, y + 26), radius=8, fill=BOARD)
            d.text((x + 14, y), pname, font=f, fill=col, anchor="lm")
            x += w + 44

    draw_board(img, d)

    callout(d, ENC_XY, (px(114, 0)[0], 40), app["encoder"], "encoder")
    if app.get("status"):
        callout(d, (STATUS[1][1], STATUS_Y), (px(166, 0)[0], 40), app["status"], "LEDs", 2.0)

    if app.get("screen"):
        label(d, px(DISP[0], 30.0), app["screen"], font(34), "#9fd0ff")

    # pots: one line per page, in the page colours, under the pot
    f = font(36)
    n = len(pages)
    for i, x in enumerate(POT_X):
        lines = [(lab.split()[i] if isinstance(lab, str) else lab[i]) for _, lab in pages]
        h = f.size * 1.05
        cx, cy = px(x, 72.0)
        w = max(f.getlength(t) for t in lines)
        pad = 10
        d.rounded_rectangle((cx - w / 2 - pad, cy - h * n / 2 - 4, cx + w / 2 + pad, cy + h * n / 2 + 4),
                            radius=10, fill=BACKING)
        for j, t in enumerate(lines):
            d.text((cx, cy - h * n / 2 + h * (j + 0.5)), t, font=f, fill=PAGE_COLORS[j % 3], anchor="mm")

    # pads
    f_pad = font(38)
    for row, y in ((app["top"], PAD_TOP_Y), (app["bottom"], PAD_BOT_Y)):
        for lab, x in zip(row, PAD_X):
            label(d, px(x, y), lab, f_pad, TEXT)
    f_cap = font(30, weight="medium")
    for cap, y in ((app.get("top_caption"), PAD_TOP_Y), (app.get("bottom_caption"), PAD_BOT_Y)):
        if cap:
            label(d, px(PAD_X[0] - PAD / 2, y + PAD / 2 + 3.4), cap, f_cap, CAPTION, anchor="lm",
                  backing=False)

    # sliders + up/down
    f_sl = font(38)
    for (x, y, w, h), lab in ((SLIDE_L, app["lslider"]), (SLIDE_R, app["rslider"])):
        label(d, px(x + w / 2, y + h / 2), lab, f_sl, TEXT)
    f_ud = font(30)
    label(d, px(UP_XY[0] - 5, UP_XY[1]), app["up"], f_ud, TEXT, anchor="rm")
    label(d, px(DOWN_XY[0] + 5, DOWN_XY[1]), app["down"], f_ud, TEXT, anchor="lm")

    # legend
    y0 = TOP + board_h + 40
    d.text((MARGIN, y0), "controls", font=font(40, "sans", "bold"), fill=INK, anchor="lt")
    y0 += 64
    for c, (key_w, rows) in enumerate(cols):
        x, y = MARGIN + c * (col_w + 60), y0
        for k, vals in rows:
            d.text((x, y), k, font=f_leg_b, fill=INK, anchor="lt")
            if f_leg_b.getlength(k) > key_w - 24:
                y += line_h
            for v in vals:
                d.text((x + key_w, y), v, font=f_leg, fill=INK, anchor="lt")
                y += line_h

    out = HERE / (name + ".png")
    img.save(out, optimize=True)
    print(out, img.size)


def main():
    names = sys.argv[1:] or list(APPS)
    for n in names:
        draw_app(n, APPS[n])


if __name__ == "__main__":
    main()
